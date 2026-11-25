"""Servidor único de inferencia (M1 placas+OCR, M2 segmentación, M3 pose llantas y pasajeros)."""
from __future__ import annotations

import base64
import math
import os
import sys
import threading
import time
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
import torch
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from ultralytics import YOLO

RAIZ_REPO = Path(__file__).resolve().parent.parent
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from inferencia.m1_placas import LectorPlacas  # noqa: E402
from scripts import diagnostico  # noqa: E402

M3_PESOS_REPO = Path(__file__).resolve().parent / "modelos" / "m3" / "m3_llantas.pt"

MAPA_CATEGORIAS = {
    "moto": "moto",
    "motorcycle": "moto",
    "motorbike": "moto",
    "motorcycles": "moto",
    "motocicleta": "moto",
    "twowheeler": "moto",
    "auto": "auto",
    "autos": "auto",
    "car": "auto",
    "cars": "auto",
    "automovil": "auto",
    "sedan": "auto",
    "suv": "auto",
    "vagoneta": "auto",
    "hatchback": "auto",
    "pickup": "auto",
    "camioneta": "auto",
    "vehicle": "auto",
    "vehicles": "auto",
    "vehiculo": "auto",
    "minibus": "minibus",
    "van": "minibus",
    "minivan": "minibus",
    "furgoneta": "minibus",
    "trufi": "minibus",
    "micro": "minibus",
    "coaster": "minibus",
    "camion": "camion",
    "camiones": "camion",
    "truck": "camion",
    "trucks": "camion",
    "lorry": "camion",
    "trailer": "camion",
    "heavytruck": "camion",
    "bus": "bus",
    "buses": "bus",
    "autobus": "bus",
    "flota": "bus",
}
CLASES_COCO_VEHICULO = {"car", "motorcycle", "bus", "truck"}
NOMBRES_CLASE_RUEDA = {"llanta", "llantas", "rueda", "ruedas", "wheel", "wheels", "tire", "tyre"}

_lock_inferencia = threading.Lock()
_modelos: dict = {}


def _normalizar_categoria(nombre: str, es_propio: bool = False) -> str | None:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", nombre.strip().lower()) if unicodedata.category(c) != "Mn"
    )
    limpio = sin_tildes.replace(" ", "").replace("-", "").replace("_", "")
    if limpio in MAPA_CATEGORIAS:
        return MAPA_CATEGORIAS[limpio]
    for clave, destino in MAPA_CATEGORIAS.items():
        if len(clave) >= 3 and clave in limpio:
            return destino
    if es_propio and limpio.isdigit():
        return "auto"
    return None


def _cargar_modelos() -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    lector_m1 = LectorPlacas()

    coco_seg = YOLO("yolo11s-seg.pt")

    m2_path = os.getenv("M2_PESOS", "").strip()
    if m2_path and Path(m2_path).is_file():
        m2 = YOLO(m2_path)
        fuente_m2 = "propio"
    else:
        m2 = coco_seg
        fuente_m2 = "coco"

    m3_env = os.getenv("M3_PESOS", "").strip()
    if m3_env and Path(m3_env).is_file():
        m3 = YOLO(m3_env)
        fuente_m3 = "propio"
    elif M3_PESOS_REPO.is_file():
        m3 = YOLO(str(M3_PESOS_REPO))
        fuente_m3 = "propio_m3_llantas"
    else:
        m3 = None
        fuente_m3 = None

    pas_path = os.getenv("PASAJEROS_PESOS", "").strip()
    if pas_path and Path(pas_path).is_file():
        pasajeros_modelo = YOLO(pas_path)
    else:
        pasajeros_modelo = coco_seg

    _modelos.update(
        {
            "device": device,
            "m1": lector_m1,
            "m2": m2,
            "coco_seg": coco_seg,
            "fuente_m2": fuente_m2,
            "m3": m3,
            "fuente_m3": fuente_m3,
            "pasajeros": pasajeros_modelo,
        }
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _cargar_modelos()
    yield


app = FastAPI(title="Endpoint de Inferencia Peaje IA", version="1.2.0", lifespan=lifespan)


def _verificar_api_key(x_api_key: str | None) -> None:
    esperada = os.getenv("API_KEY", "").strip()
    if esperada and x_api_key != esperada:
        raise HTTPException(status_code=401, detail="X-API-Key inválida o faltante")


def _codificar_anotada(imagen_bgr: np.ndarray) -> str:
    h, w = imagen_bgr.shape[:2]
    if w > 960:
        escala = 960 / w
        imagen_bgr = cv2.resize(imagen_bgr, (960, max(1, int(h * escala))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", imagen_bgr, [cv2.IMWRITE_JPEG_QUALITY, 78])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _dentro_caja(cx: float, cy: float, caja: tuple[float, float, float, float], margen: float = 0.0) -> bool:
    x1, y1, x2, y2 = caja
    dx = (x2 - x1) * margen
    dy = (y2 - y1) * margen
    return (x1 - dx) <= cx <= (x2 + dx) and (y1 - dy) <= cy <= (y2 + dy)


def _dibujar_etiqueta(
    img: np.ndarray,
    texto: str,
    x: int,
    y: int,
    bg_bgr: tuple[int, int, int],
    fg_bgr: tuple[int, int, int] = (255, 255, 255),
    escala: float = 0.62,
) -> None:
    (tw, th), base = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, escala, 2)
    y_top = max(0, y - th - base - 8)
    x_right = min(img.shape[1] - 1, x + tw + 12)
    cv2.rectangle(img, (max(0, x), y_top), (x_right, y_top + th + base + 8), bg_bgr, -1)
    cv2.putText(
        img,
        texto,
        (max(0, x) + 6, y_top + th + 3),
        cv2.FONT_HERSHEY_SIMPLEX,
        escala,
        fg_bgr,
        2,
        cv2.LINE_AA,
    )


def _extraer_instancias_vehiculos(res_yolo, es_propio: bool) -> list[dict]:
    instancias: list[dict] = []
    if res_yolo.boxes is None or len(res_yolo.boxes) == 0:
        return instancias
    nombres = res_yolo.names
    for i in range(len(res_yolo.boxes)):
        cls_id = int(res_yolo.boxes.cls[i].item())
        nombre_raw = str(nombres.get(cls_id, ""))
        if not es_propio and nombre_raw.lower() not in CLASES_COCO_VEHICULO:
            continue
        cat_norm = _normalizar_categoria(nombre_raw, es_propio=es_propio)
        if cat_norm is None:
            continue
        x1, y1, x2, y2 = [float(v) for v in res_yolo.boxes.xyxy[i].tolist()]
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        conf = round(float(res_yolo.boxes.conf[i].item()), 4)
        poly = None
        if res_yolo.masks is not None and i < len(res_yolo.masks.xy):
            pts = res_yolo.masks.xy[i].astype(np.int32)
            if len(pts) > 2:
                poly = pts
        instancias.append(
            {
                "caja": (x1, y1, x2, y2),
                "area": area,
                "categoria": cat_norm,
                "conf": conf,
                "poly": poly,
            }
        )
    instancias.sort(key=lambda d: d["area"], reverse=True)
    return instancias


def _estimar_ejes(
    ruedas_pts: list[tuple[int, int]],
    categoria: str | None,
    vehiculo_caja: tuple[float, float, float, float] | None,
) -> int | None:
    n = len(ruedas_pts)
    if n == 0:
        return None
    if categoria == "moto":
        return 2

    # Agrupar ruedas que corresponden al mismo eje cuando el vehículo se ve en ángulo 3/4
    xs = sorted(p[0] for p in ruedas_pts)
    ancho_ref = (vehiculo_caja[2] - vehiculo_caja[0]) if vehiculo_caja is not None else max(80.0, float(xs[-1] - xs[0]))
    umbral_mismo_eje = max(18.0, ancho_ref * 0.14)
    grupos_eje: list[float] = []
    for x in xs:
        if not grupos_eje or abs(x - grupos_eje[-1]) > umbral_mismo_eje:
            grupos_eje.append(float(x))

    if categoria in ("auto", "minibus"):
        return 2
    # Para vehículos pesados (camion / bus) o sin categoría previa: cada eje lateral cuenta
    return max(2, min(6, len(grupos_eje)))


@app.get("/health")
def health():
    if not _modelos:
        _cargar_modelos()
    return {
        "status": "ok",
        "modelos": {
            "m1": _modelos.get("m1") is not None,
            "m2": _modelos.get("m2") is not None,
            "m3": _modelos.get("m3") is not None,
            "pasajeros": _modelos.get("pasajeros") is not None,
        },
        "fuente_m2": _modelos.get("fuente_m2"),
        "fuente_m3": _modelos.get("fuente_m3"),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "diagnostico": diagnostico.info(),
    }


@app.post("/infer")
def inferir(
    imagen: UploadFile = File(...),
    modo: str = Form("completo"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _verificar_api_key(x_api_key)
    if not _modelos:
        _cargar_modelos()

    raw = imagen.file.read()
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="No se pudo decodificar la imagen")

    inicio_total = time.perf_counter()
    with _lock_inferencia:
        anotada = img.copy()

        if modo == "placa":
            t0 = time.perf_counter()
            res_m1 = _modelos["m1"].leer(img)
            t_m1 = round((time.perf_counter() - t0) * 1000)
            if res_m1["caja"]:
                px1, py1, px2, py2 = res_m1["caja"]
                cv2.rectangle(anotada, (px1, py1), (px2, py2), (0, 230, 64), 3)
                _dibujar_etiqueta(anotada, f"PLACA: {res_m1['placa'] or '?'}", px1, py1, (0, 170, 40))
            total_ms = round((time.perf_counter() - inicio_total) * 1000)
            return {
                **res_m1,
                "categoria": None,
                "confianza_categoria": None,
                "ejes": None,
                "ruedas": None,
                "pasajeros": None,
                "imagen_anotada": _codificar_anotada(anotada),
                "latencia_ms": total_ms,
                "latencias": {"m1": t_m1, "m2": 0, "m3": 0, "pasajeros": 0},
                "fuente_m2": _modelos["fuente_m2"],
                "fuente_m3": _modelos.get("fuente_m3"),
            }

        # 1. M2: Segmentación de instancias de vehículos (máscara rosa estilo Roboflow)
        t0 = time.perf_counter()
        es_propio = _modelos["fuente_m2"] == "propio"
        res_m2 = _modelos["m2"](img, verbose=False, conf=0.26)[0]
        instancias_v = _extraer_instancias_vehiculos(res_m2, es_propio=es_propio)
        if not instancias_v and es_propio and _modelos.get("coco_seg") is not None:
            res_coco = _modelos["coco_seg"](img, classes=[2, 3, 5, 7], verbose=False, conf=0.25)[0]
            instancias_v = _extraer_instancias_vehiculos(res_coco, es_propio=False)
        t_m2 = round((time.perf_counter() - t0) * 1000)

        vehiculo_caja: tuple[float, float, float, float] | None = None
        categoria: str | None = None
        conf_categoria: float | None = None

        if instancias_v:
            principal = instancias_v[0]
            vehiculo_caja = principal["caja"]
            categoria = principal["categoria"]
            conf_categoria = principal["conf"]

            capa_mask = anotada.copy()
            for idx_v, inst in enumerate(reversed(instancias_v[:5])):
                es_prin = idx_v == len(instancias_v[:5]) - 1
                color_relleno = (147, 20, 255) if es_prin else (190, 110, 255)
                if inst["poly"] is not None:
                    cv2.fillPoly(capa_mask, [inst["poly"]], color_relleno)
                else:
                    bx1, by1, bx2, by2 = [int(v) for v in inst["caja"]]
                    cv2.rectangle(capa_mask, (bx1, by1), (bx2, by2), color_relleno, -1)
            cv2.addWeighted(capa_mask, 0.45, anotada, 0.55, 0, anotada)

            for idx_v, inst in enumerate(instancias_v[:5]):
                es_prin = idx_v == 0
                color_borde = (180, 40, 255) if es_prin else (210, 140, 255)
                if inst["poly"] is not None:
                    cv2.polylines(anotada, [inst["poly"]], True, color_borde, 3 if es_prin else 2, cv2.LINE_AA)
                else:
                    bx1, by1, bx2, by2 = [int(v) for v in inst["caja"]]
                    cv2.rectangle(anotada, (bx1, by1), (bx2, by2), color_borde, 2)
                if es_prin:
                    vx1, vy1, _, _ = [int(v) for v in inst["caja"]]
                    _dibujar_etiqueta(
                        anotada,
                        f"M2 {inst['categoria'].upper()} {(inst['conf'] * 100):.0f}%",
                        vx1,
                        max(35, vy1),
                        (147, 20, 220),
                    )

        # 2. M1: Detección de placa + OCR (con zoom guiado por la caja del vehículo)
        t0 = time.perf_counter()
        res_m1 = _modelos["m1"].leer(img, caja_vehiculo=vehiculo_caja)
        t_m1 = round((time.perf_counter() - t0) * 1000)

        # 3. M3: Modelo YOLO11s-pose de llantas (m3_llantas.pt: 1 caja por llanta + hasta 5 keypoints)
        t0 = time.perf_counter()
        ruedas_pts: list[tuple[int, int]] = []
        llantas_detalle: list[dict] = []

        if _modelos["m3"] is not None:
            res_m3 = _modelos["m3"](img, verbose=False, conf=0.22)[0]
            nombres_m3 = res_m3.names or {}
            boxes_m3 = res_m3.boxes
            kps_xy = (
                res_m3.keypoints.xy.cpu().numpy()
                if (res_m3.keypoints is not None and res_m3.keypoints.xy is not None)
                else None
            )
            kps_conf = (
                res_m3.keypoints.conf.cpu().numpy()
                if (res_m3.keypoints is not None and res_m3.keypoints.conf is not None)
                else None
            )

            n_det = len(boxes_m3) if boxes_m3 is not None else (len(kps_xy) if kps_xy is not None else 0)
            for i in range(n_det):
                cls_id = int(boxes_m3.cls[i].item()) if boxes_m3 is not None else 0
                nombre_cls = str(nombres_m3.get(cls_id, "llanta")).strip().lower()
                bx1, by1, bx2, by2 = (
                    [float(v) for v in boxes_m3.xyxy[i].tolist()] if boxes_m3 is not None else [0.0, 0.0, 0.0, 0.0]
                )

                pts_validos: list[tuple[int, int]] = []
                if kps_xy is not None and i < len(kps_xy):
                    for k in range(len(kps_xy[i])):
                        kx, ky = float(kps_xy[i][k][0]), float(kps_xy[i][k][1])
                        kc = float(kps_conf[i][k]) if (kps_conf is not None and k < len(kps_conf[i])) else 1.0
                        if kc >= 0.25 and kx > 1.0 and ky > 1.0:
                            pts_validos.append((int(round(kx)), int(round(ky))))

                es_modelo_por_llanta = (nombre_cls in NOMBRES_CLASE_RUEDA) or (
                    kps_xy is not None and i < len(kps_xy) and len(kps_xy[i]) in (1, 5)
                )

                if es_modelo_por_llanta:
                    # Cada detección representa 1 llanta; su centro es el promedio de sus keypoints (o centro de caja)
                    if pts_validos:
                        cx_r = sum(p[0] for p in pts_validos) / len(pts_validos)
                        cy_r = sum(p[1] for p in pts_validos) / len(pts_validos)
                    elif bx2 > bx1 and by2 > by1:
                        cx_r, cy_r = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
                    else:
                        continue

                    if vehiculo_caja is not None and not _dentro_caja(cx_r, cy_r, vehiculo_caja, margen=0.15):
                        continue
                    if any(math.hypot(cx_r - ex, cy_r - ey) < 22.0 for ex, ey in ruedas_pts):
                        continue

                    centro_int = (int(round(cx_r)), int(round(cy_r)))
                    ruedas_pts.append(centro_int)
                    llantas_detalle.append(
                        {
                            "centro": centro_int,
                            "caja": (int(bx1), int(by1), int(bx2), int(by2)) if bx2 > bx1 else None,
                            "kpts": pts_validos,
                        }
                    )
                else:
                    # Respaldo por si se usa un modelo donde 1 caja = vehículo completo y cada keypoint = 1 rueda
                    for pkx, pky in pts_validos:
                        if vehiculo_caja is not None and not _dentro_caja(pkx, pky, vehiculo_caja, margen=0.15):
                            continue
                        if any(math.hypot(pkx - ex, pky - ey) < 22.0 for ex, ey in ruedas_pts):
                            continue
                        ruedas_pts.append((pkx, pky))
                        llantas_detalle.append({"centro": (pkx, pky), "caja": None, "kpts": [(pkx, pky)]})

        t_m3 = round((time.perf_counter() - t0) * 1000)

        ruedas = len(ruedas_pts) if _modelos.get("m3") is not None else None
        ejes = _estimar_ejes(ruedas_pts, categoria, vehiculo_caja)

        # 4. Pasajeros (+5): segmentación clase person (0) con máscaras OPACAS de privacidad
        t0 = time.perf_counter()
        res_pas = _modelos["pasajeros"](img, classes=[0], verbose=False, conf=0.30)[0]
        t_pas = round((time.perf_counter() - t0) * 1000)

        pasajeros = 0
        if res_pas.boxes is not None and len(res_pas.boxes) > 0:
            for i in range(len(res_pas.boxes)):
                px1, py1, px2, py2 = [float(v) for v in res_pas.boxes.xyxy[i].tolist()]
                cx, cy = (px1 + px2) / 2.0, (py1 + py2) / 2.0
                en_vehiculo = vehiculo_caja is not None and _dentro_caja(cx, cy, vehiculo_caja, margen=0.05)
                color_priv = (210, 60, 120) if en_vehiculo else (140, 70, 140)
                if res_pas.masks is not None and i < len(res_pas.masks.xy):
                    poly_p = res_pas.masks.xy[i].astype(np.int32)
                    if len(poly_p) > 2:
                        cv2.fillPoly(anotada, [poly_p], color_priv)
                        cv2.polylines(anotada, [poly_p], True, (255, 255, 255), 1, cv2.LINE_AA)
                    else:
                        cv2.rectangle(anotada, (int(px1), int(py1)), (int(px2), int(py2)), color_priv, -1)
                else:
                    cv2.rectangle(anotada, (int(px1), int(py1)), (int(px2), int(py2)), color_priv, -1)

                if en_vehiculo:
                    pasajeros += 1

        # Dibujar llantas, sus 5 keypoints y la línea de ejes (estilo Roboflow Pose)
        for det_ll in llantas_detalle:
            cx_l, cy_l = det_ll["centro"]
            if det_ll["caja"] is not None:
                lx1, ly1, lx2, ly2 = det_ll["caja"]
                cv2.rectangle(anotada, (lx1, ly1), (lx2, ly2), (255, 210, 0), 2)
            for kx_i, ky_i in det_ll["kpts"]:
                cv2.line(anotada, (cx_l, cy_l), (kx_i, ky_i), (255, 210, 0), 1, cv2.LINE_AA)
                cv2.circle(anotada, (kx_i, ky_i), 4, (255, 220, 0), -1, cv2.LINE_AA)

        if ruedas_pts:
            pts_ord = sorted(ruedas_pts, key=lambda p: p[0])
            if len(pts_ord) >= 2:
                for idx_p in range(len(pts_ord) - 1):
                    cv2.line(anotada, pts_ord[idx_p], pts_ord[idx_p + 1], (20, 20, 20), 5, cv2.LINE_AA)
                    cv2.line(anotada, pts_ord[idx_p], pts_ord[idx_p + 1], (255, 235, 80), 2, cv2.LINE_AA)
            for rx, ry in pts_ord:
                cv2.circle(anotada, (rx, ry), 8, (15, 15, 15), -1, cv2.LINE_AA)
                cv2.circle(anotada, (rx, ry), 5, (255, 255, 255), -1, cv2.LINE_AA)

        # Dibujar caja y etiqueta de placa M1 encima de las máscaras
        if res_m1["caja"]:
            px1, py1, px2, py2 = res_m1["caja"]
            cv2.rectangle(anotada, (px1, py1), (px2, py2), (0, 235, 64), 3)
            _dibujar_etiqueta(
                anotada,
                f"M1 PLACA: {res_m1['placa'] or '?'}",
                px1,
                py1,
                (0, 165, 45),
            )

        # Barra superior HUD con resumen completo
        hud = anotada.copy()
        cv2.rectangle(hud, (0, 0), (anotada.shape[1], 34), (15, 23, 42), -1)
        cv2.addWeighted(hud, 0.78, anotada, 0.22, 0, anotada)
        resumen_hud = (
            f"Placa: {res_m1['placa'] or '---'} | "
            f"Tipo: {categoria or '---'} | "
            f"Ejes: {ejes or '-'} ({len(ruedas_pts)} llantas) | "
            f"Pasajeros: {pasajeros}"
        )
        cv2.putText(
            anotada,
            resumen_hud,
            (12, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.56,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        total_ms = round((time.perf_counter() - inicio_total) * 1000)
        return {
            **res_m1,
            "categoria": categoria,
            "confianza_categoria": conf_categoria,
            "ejes": ejes,
            "ruedas": ruedas,
            "pasajeros": pasajeros,
            "imagen_anotada": _codificar_anotada(anotada),
            "latencia_ms": total_ms,
            "latencias": {"m1": t_m1, "m2": t_m2, "m3": t_m3, "pasajeros": t_pas},
            "fuente_m2": _modelos["fuente_m2"],
            "fuente_m3": _modelos.get("fuente_m3"),
        }
