"""Servidor único de inferencia (M1 placas+OCR, M2 segmentación, M3 ejes y pasajeros)."""
from __future__ import annotations

import base64
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

MAPA_CATEGORIAS = {
    "moto": "moto",
    "motorcycle": "moto",
    "motocicleta": "moto",
    "auto": "auto",
    "car": "auto",
    "automovil": "auto",
    "minibus": "minibus",
    "van": "minibus",
    "camion": "camion",
    "truck": "camion",
    "bus": "bus",
    "autobus": "bus",
}
CLASES_COCO_VEHICULO = {"car", "motorcycle", "bus", "truck"}

_lock_inferencia = threading.Lock()
_modelos: dict = {}


def _normalizar_categoria(nombre: str) -> str | None:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", nombre.strip().lower()) if unicodedata.category(c) != "Mn"
    )
    limpio = sin_tildes.replace(" ", "").replace("-", "").replace("_", "")
    return MAPA_CATEGORIAS.get(limpio)


def _cargar_modelos() -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    lector_m1 = LectorPlacas()

    m2_path = os.getenv("M2_PESOS", "").strip()
    if m2_path and Path(m2_path).is_file():
        m2 = YOLO(m2_path)
        fuente_m2 = "propio"
    else:
        m2 = YOLO("yolo11s-seg.pt")
        fuente_m2 = "coco"

    m3_path = os.getenv("M3_PESOS", "").strip()
    m3 = YOLO(m3_path) if (m3_path and Path(m3_path).is_file()) else None

    pas_path = os.getenv("PASAJEROS_PESOS", "yolo11s-seg.pt").strip()
    if not (pas_path and Path(pas_path).is_file()):
        pas_path = "yolo11s-seg.pt"
    pasajeros_modelo = YOLO(pas_path)

    _modelos.update(
        {
            "device": device,
            "m1": lector_m1,
            "m2": m2,
            "fuente_m2": fuente_m2,
            "m3": m3,
            "pasajeros": pasajeros_modelo,
        }
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _cargar_modelos()
    yield


app = FastAPI(title="Endpoint de Inferencia Peaje IA", version="1.0.0", lifespan=lifespan)


def _verificar_api_key(x_api_key: str | None) -> None:
    esperada = os.getenv("API_KEY", "").strip()
    if esperada and x_api_key != esperada:
        raise HTTPException(status_code=401, detail="X-API-Key inválida o faltante")


def _codificar_anotada(imagen_bgr: np.ndarray) -> str:
    h, w = imagen_bgr.shape[:2]
    if w > 960:
        escala = 960 / w
        imagen_bgr = cv2.resize(imagen_bgr, (960, max(1, int(h * escala))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", imagen_bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _dentro_caja(cx: float, cy: float, caja: tuple[float, float, float, float], margen: float = 0.0) -> bool:
    x1, y1, x2, y2 = caja
    dx = (x2 - x1) * margen
    dy = (y2 - y1) * margen
    return (x1 - dx) <= cx <= (x2 + dx) and (y1 - dy) <= cy <= (y2 + dy)


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
        # 1. M1: Detección de placa + OCR
        t0 = time.perf_counter()
        res_m1 = _modelos["m1"].leer(img)
        t_m1 = round((time.perf_counter() - t0) * 1000)

        anotada = img.copy()
        if res_m1["caja"]:
            px1, py1, px2, py2 = res_m1["caja"]
            cv2.rectangle(anotada, (px1, py1), (px2, py2), (0, 220, 0), 3)
            cv2.putText(
                anotada,
                res_m1["placa"] or "?",
                (px1, max(25, py1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.85,
                (0, 220, 0),
                2,
                cv2.LINE_AA,
            )

        if modo == "placa":
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
            }

        # 2. M2: Segmentación de instancias del vehículo principal
        t0 = time.perf_counter()
        res_m2 = _modelos["m2"](img, verbose=False, conf=0.35)[0]
        t_m2 = round((time.perf_counter() - t0) * 1000)

        vehiculo_caja: tuple[float, float, float, float] | None = None
        categoria: str | None = None
        conf_categoria: float | None = None
        mejor_area = -1.0
        mejor_idx = -1

        if res_m2.boxes is not None and len(res_m2.boxes) > 0:
            nombres = res_m2.names
            for i in range(len(res_m2.boxes)):
                cls_id = int(res_m2.boxes.cls[i].item())
                nombre_raw = str(nombres.get(cls_id, ""))
                if _modelos["fuente_m2"] == "coco" and nombre_raw.lower() not in CLASES_COCO_VEHICULO:
                    continue
                cat_norm = _normalizar_categoria(nombre_raw)
                if cat_norm is None:
                    continue
                x1, y1, x2, y2 = [float(v) for v in res_m2.boxes.xyxy[i].tolist()]
                area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
                if area > mejor_area:
                    mejor_area = area
                    mejor_idx = i
                    vehiculo_caja = (x1, y1, x2, y2)
                    categoria = cat_norm
                    conf_categoria = round(float(res_m2.boxes.conf[i].item()), 4)

        if mejor_idx >= 0 and vehiculo_caja is not None:
            vx1, vy1, vx2, vy2 = [int(v) for v in vehiculo_caja]
            if res_m2.masks is not None and mejor_idx < len(res_m2.masks.xy):
                poly = res_m2.masks.xy[mejor_idx].astype(np.int32)
                if len(poly) > 2:
                    overlay = anotada.copy()
                    cv2.fillPoly(overlay, [poly], (255, 160, 0))
                    cv2.addWeighted(overlay, 0.35, anotada, 0.65, 0, anotada)
            cv2.rectangle(anotada, (vx1, vy1), (vx2, vy2), (255, 160, 0), 2)
            cv2.putText(
                anotada,
                f"{categoria} ({(conf_categoria or 0) * 100:.0f}%)",
                (vx1, max(25, vy1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 160, 0),
                2,
                cv2.LINE_AA,
            )

        # 3. M3: Keypoints de ruedas -> número de ejes
        t0 = time.perf_counter()
        ruedas_pts: list[tuple[int, int]] = []
        if _modelos["m3"] is not None:
            res_m3 = _modelos["m3"](img, verbose=False, conf=0.25)[0]
            if res_m3.keypoints is not None and res_m3.keypoints.xy is not None:
                kps_xy = res_m3.keypoints.xy.cpu().numpy()
                kps_conf = res_m3.keypoints.conf.cpu().numpy() if res_m3.keypoints.conf is not None else None
                for i in range(len(kps_xy)):
                    if len(kps_xy[i]) == 0:
                        continue
                    kx, ky = float(kps_xy[i][0][0]), float(kps_xy[i][0][1])
                    kc = float(kps_conf[i][0]) if kps_conf is not None else 1.0
                    if kc <= 0.35 or (kx == 0 and ky == 0):
                        continue
                    if vehiculo_caja is None or _dentro_caja(kx, ky, vehiculo_caja, margen=0.10):
                        ruedas_pts.append((int(kx), int(ky)))
                        cv2.circle(anotada, (int(kx), int(ky)), 9, (0, 255, 255), -1)
                        cv2.circle(anotada, (int(kx), int(ky)), 12, (0, 0, 255), 2)
        t_m3 = round((time.perf_counter() - t0) * 1000)

        ruedas = len(ruedas_pts) if _modelos["m3"] is not None else None
        ejes = len(ruedas_pts) if len(ruedas_pts) > 0 else None

        # 4. Pasajeros (+5): segmentación clase person (0) con máscaras OPACAS (sin rostros)
        t0 = time.perf_counter()
        res_pas = _modelos["pasajeros"](img, classes=[0], verbose=False, conf=0.35)[0]
        t_pas = round((time.perf_counter() - t0) * 1000)

        pasajeros = 0
        if res_pas.boxes is not None and len(res_pas.boxes) > 0:
            for i in range(len(res_pas.boxes)):
                px1, py1, px2, py2 = [float(v) for v in res_pas.boxes.xyxy[i].tolist()]
                if res_pas.masks is not None and i < len(res_pas.masks.xy):
                    poly_p = res_pas.masks.xy[i].astype(np.int32)
                    if len(poly_p) > 2:
                        # Máscara opaca para preservar privacidad en toda persona detectada (sin rostros)
                        cv2.fillPoly(anotada, [poly_p], (200, 50, 200))
                    else:
                        cv2.rectangle(anotada, (int(px1), int(py1)), (int(px2), int(py2)), (200, 50, 200), -1)
                else:
                    cv2.rectangle(anotada, (int(px1), int(py1)), (int(px2), int(py2)), (200, 50, 200), -1)

                cx, cy = (px1 + px2) / 2.0, (py1 + py2) / 2.0
                if vehiculo_caja is not None and _dentro_caja(cx, cy, vehiculo_caja, margen=0.0):
                    pasajeros += 1

        cv2.putText(
            anotada,
            f"Pasajeros: {pasajeros}",
            (16, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.95,
            (255, 255, 255),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            anotada,
            f"Pasajeros: {pasajeros}",
            (16, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.95,
            (200, 50, 200),
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
        }
