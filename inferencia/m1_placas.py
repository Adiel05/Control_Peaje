"""M1: Detección de placas (YOLOv9-t ONNX) + OCR (fast-plate-ocr) con zoom adaptativo."""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from fast_plate_ocr import LicensePlateRecognizer

CARPETA_M1_DEFECTO = Path(__file__).resolve().parent / "modelos" / "m1"
LADO_ENTRADA = 384
FORMATO_BOLIVIA = re.compile(r"^\d{3,4}[A-Z]{3}$")


def limpiar_placa(texto: str | None) -> str:
    """Normaliza el texto de una placa a mayúsculas alfanuméricas sin espacios ni guiones."""
    if not texto:
        return ""
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


class LectorPlacas:
    """Carga los modelos ONNX de detección y OCR una sola vez para baja latencia."""

    def __init__(self, carpeta_modelos: Path | str = CARPETA_M1_DEFECTO, umbral: float = 0.20) -> None:
        carpeta = Path(carpeta_modelos)
        self.umbral = umbral
        self.modelo_det = carpeta / "yolo-v9-t-384-license-plates-end2end.onnx"
        self.modelo_ocr = carpeta / "cct_xs_v2_global.onnx"
        self.config_ocr = carpeta / "cct_xs_v2_global_plate_config.yaml"

        disponibles = ort.get_available_providers()
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if "CUDAExecutionProvider" in disponibles
            else ["CPUExecutionProvider"]
        )
        opciones = ort.SessionOptions()
        opciones.intra_op_num_threads = 2
        opciones.inter_op_num_threads = 2
        opciones.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.sesion = ort.InferenceSession(str(self.modelo_det), sess_options=opciones, providers=providers)
        self.input_name = self.sesion.get_inputs()[0].name
        self.lector_ocr = LicensePlateRecognizer(
            onnx_model_path=self.modelo_ocr,
            plate_config_path=self.config_ocr,
        )

    def detectar_cajas(self, imagen_bgr: np.ndarray, umbral: float | None = None) -> list[tuple[int, int, int, int, float]]:
        """Detecta cajas de placas (x1, y1, x2, y2, confianza) en coordenadas originales."""
        alto, ancho = imagen_bgr.shape[:2]
        if alto < 16 or ancho < 16:
            return []
        umb = self.umbral if umbral is None else umbral
        escala = min(LADO_ENTRADA / alto, LADO_ENTRADA / ancho)
        nuevo_ancho, nuevo_alto = max(1, round(ancho * escala)), max(1, round(alto * escala))
        margen_x, margen_y = (LADO_ENTRADA - nuevo_ancho) / 2, (LADO_ENTRADA - nuevo_alto) / 2

        lienzo = cv2.resize(imagen_bgr, (nuevo_ancho, nuevo_alto), interpolation=cv2.INTER_LINEAR)
        lienzo = cv2.copyMakeBorder(
            lienzo,
            round(margen_y - 0.1),
            round(margen_y + 0.1),
            round(margen_x - 0.1),
            round(margen_x + 0.1),
            cv2.BORDER_CONSTANT,
            value=(114, 114, 114),
        )
        entrada = (lienzo[:, :, ::-1].transpose(2, 0, 1) / 255.0).astype(np.float32)[None]
        salida = self.sesion.run(None, {self.input_name: entrada})[0]

        cajas: list[tuple[int, int, int, int, float]] = []
        for _, x1, y1, x2, y2, _, confianza in salida:
            if float(confianza) < umb:
                continue
            rx1 = int(max(0, (float(x1) - margen_x) / escala))
            ry1 = int(max(0, (float(y1) - margen_y) / escala))
            rx2 = int(min(ancho, (float(x2) - margen_x) / escala))
            ry2 = int(min(alto, (float(y2) - margen_y) / escala))
            if (rx2 - rx1) >= 12 and (ry2 - ry1) >= 6:
                cajas.append((rx1, ry1, rx2, ry2, float(confianza)))
        return cajas

    def _ocr_recorte(self, recorte_bgr: np.ndarray, conf_det: float) -> tuple[str, str, float]:
        recorte_rgb = cv2.cvtColor(recorte_bgr, cv2.COLOR_BGR2RGB)
        pred = self.lector_ocr.run_one(recorte_rgb, return_confidence=True)
        texto_crudo = getattr(pred, "plate", str(pred))
        char_probs = getattr(pred, "char_probs", None)
        conf_ocr = float(char_probs.mean()) if char_probs is not None else float(conf_det)
        placa_limpia = limpiar_placa(texto_crudo)

        # Segundo intento con mejora de contraste si hay reflejo de pantalla o baja nitidez
        if not FORMATO_BOLIVIA.match(placa_limpia) or conf_ocr < 0.72:
            lab = cv2.cvtColor(recorte_bgr, cv2.COLOR_BGR2LAB)
            l_ch, a_ch, b_ch = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(4, 4))
            mejorada_bgr = cv2.cvtColor(cv2.merge((clahe.apply(l_ch), a_ch, b_ch)), cv2.COLOR_LAB2BGR)
            mejorada_rgb = cv2.cvtColor(mejorada_bgr, cv2.COLOR_BGR2RGB)
            pred2 = self.lector_ocr.run_one(mejorada_rgb, return_confidence=True)
            texto2 = getattr(pred2, "plate", str(pred2))
            probs2 = getattr(pred2, "char_probs", None)
            conf2 = float(probs2.mean()) if probs2 is not None else float(conf_det)
            limpia2 = limpiar_placa(texto2)
            es_valida1 = bool(FORMATO_BOLIVIA.match(placa_limpia))
            es_valida2 = bool(FORMATO_BOLIVIA.match(limpia2))
            if (es_valida2 and not es_valida1) or (es_valida2 == es_valida1 and conf2 > conf_ocr):
                return limpia2, texto2, conf2

        return placa_limpia, texto_crudo, conf_ocr

    def leer(
        self,
        imagen_bgr: np.ndarray,
        caja_vehiculo: tuple[float, float, float, float] | None = None,
    ) -> dict:
        """Detecta la placa (con zoom al vehículo o centro si está pequeña) y ejecuta OCR."""
        alto, ancho = imagen_bgr.shape[:2]
        cajas = self.detectar_cajas(imagen_bgr)

        # Si hay caja de vehículo (M2) y no se halló placa clara, hacer zoom al vehículo
        if caja_vehiculo is not None and (not cajas or max(c[4] for c in cajas) < 0.55):
            vx1 = max(0, int(caja_vehiculo[0]))
            vy1 = max(0, int(caja_vehiculo[1]))
            vx2 = min(ancho, int(caja_vehiculo[2]))
            vy2 = min(alto, int(caja_vehiculo[3]))
            if (vx2 - vx1) >= 40 and (vy2 - vy1) >= 40:
                sub = imagen_bgr[vy1:vy2, vx1:vx2]
                for cx1, cy1, cx2, cy2, cconf in self.detectar_cajas(sub, umbral=0.18):
                    cajas.append((vx1 + cx1, vy1 + cy1, vx1 + cx2, vy1 + cy2, cconf + 0.05))

        # Si sigue sin encontrarse (ej. foto vertical de pantalla), hacer zoom al 65% central
        if not cajas and min(alto, ancho) >= 240:
            mx, my = int(ancho * 0.15), int(alto * 0.18)
            sub_c = imagen_bgr[my : alto - my, mx : ancho - mx]
            for cx1, cy1, cx2, cy2, cconf in self.detectar_cajas(sub_c, umbral=0.18):
                cajas.append((mx + cx1, my + cy1, mx + cx2, my + cy2, cconf))

        if not cajas:
            return {
                "placa": "",
                "placa_texto_crudo": "",
                "confianza": 0.0,
                "confianza_deteccion": 0.0,
                "formato_valido": False,
                "caja": None,
            }

        x1, y1, x2, y2, conf_det = max(cajas, key=lambda c: c[4])
        conf_det = min(1.0, conf_det)
        # Ligero margen alrededor de la placa para no cortar caracteres extremos
        px = max(2, int((x2 - x1) * 0.04))
        py = max(2, int((y2 - y1) * 0.06))
        rx1, ry1 = max(0, x1 - px), max(0, y1 - py)
        rx2, ry2 = min(ancho, x2 + px), min(alto, y2 + py)

        placa_limpia, texto_crudo, conf_ocr = self._ocr_recorte(imagen_bgr[ry1:ry2, rx1:rx2], conf_det)
        return {
            "placa": placa_limpia,
            "placa_texto_crudo": texto_crudo,
            "confianza": round(conf_ocr, 4),
            "confianza_deteccion": round(conf_det, 4),
            "formato_valido": bool(FORMATO_BOLIVIA.match(placa_limpia)),
            "caja": [x1, y1, x2, y2],
        }
