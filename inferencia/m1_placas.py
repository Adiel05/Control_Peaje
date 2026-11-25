"""M1: Detección de placas (YOLOv9-t ONNX) + OCR (fast-plate-ocr) sin dependencia de ultralytics."""
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

    def __init__(self, carpeta_modelos: Path | str = CARPETA_M1_DEFECTO, umbral: float = 0.28) -> None:
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

    def detectar_cajas(self, imagen_bgr: np.ndarray) -> list[tuple[int, int, int, int, float]]:
        """Detecta cajas de placas (x1, y1, x2, y2, confianza) en coordenadas originales."""
        alto, ancho = imagen_bgr.shape[:2]
        escala = min(LADO_ENTRADA / alto, LADO_ENTRADA / ancho)
        nuevo_ancho, nuevo_alto = round(ancho * escala), round(alto * escala)
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
            if float(confianza) < self.umbral:
                continue
            rx1 = int(max(0, (float(x1) - margen_x) / escala))
            ry1 = int(max(0, (float(y1) - margen_y) / escala))
            rx2 = int(min(ancho, (float(x2) - margen_x) / escala))
            ry2 = int(min(alto, (float(y2) - margen_y) / escala))
            if rx2 > rx1 and ry2 > ry1:
                cajas.append((rx1, ry1, rx2, ry2, float(confianza)))
        return cajas

    def leer(self, imagen_bgr: np.ndarray) -> dict:
        """Detecta la placa principal y ejecuta OCR sobre el recorte."""
        cajas = self.detectar_cajas(imagen_bgr)
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
        recorte_rgb = cv2.cvtColor(imagen_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
        pred = self.lector_ocr.run_one(recorte_rgb, return_confidence=True)
        texto_crudo = getattr(pred, "plate", str(pred))
        char_probs = getattr(pred, "char_probs", None)
        conf_ocr = float(char_probs.mean()) if char_probs is not None else float(conf_det)

        placa_limpia = limpiar_placa(texto_crudo)
        return {
            "placa": placa_limpia,
            "placa_texto_crudo": texto_crudo,
            "confianza": round(conf_ocr, 4),
            "confianza_deteccion": round(conf_det, 4),
            "formato_valido": bool(FORMATO_BOLIVIA.match(placa_limpia)),
            "caja": [x1, y1, x2, y2],
        }
