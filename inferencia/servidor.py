"""Servidor único de inferencia (M1 placas+OCR, M2 segmentación, M3 ejes y pasajeros)."""
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

_lock_inferencia = threading.Lock()
_modelos: dict = {}


def _normalizar_categoria(nombre: str, es_propio: bool = False) -> str | None:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", nombre.strip().lower()) if unicodedata.category(c) != "Mn"
    )
    limpio = sin_tildes.replace(" ", "").replace("-", "").replace("_", "")
    if limpio in MAPA_CATEGORIAS:
        return MAPA_CATEGORIAS[limpio]
    # Si el dataset propio de Roboflow usa nombres compuestos o índices numéricos
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

    m3_path = os.getenv("M3_PESOS", "").strip()
    m3 = YOLO(m3_path) if (m3_path and Path(m3_path).is_file()) else None

    # Respaldo preciso de centros de ruedas (GPU YOLO-World) si m3_pose detecta menos ruedas
    m3_world = None
    try:
        m3_world = YOLO("yolov8s-worldv2.pt")
        m3_world.set_classes(["car wheel", "truck wheel", "vehicle wheel", "tire"])
    except Exception:
        m3_world = None

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
            "m3_world": m3_world,
            "pasajeros": pasajeros_modelo,
        }
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _cargar_modelos()
    yield


app = FastAPI(title="Endpoint de Inferencia Peaje IA", version="1.1.0", lifespan=lifespan)


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


def _estimar_ejes(ruedas_pts: list[tuple[int, int]], categoria: str | None) -> int | None:
    n = len(ruedas_pts)
    if n == 0:
        return None
    if categoria == "moto":
        return 2
    if categoria in ("auto", "minibus") or categoria is None:
        return 2
    # Para camiones o buses: si hay 3 o más posiciones longitudinales distintas
    xs = sorted(p[0] for p in ruedas_pts)
    ancho_span = max(1, xs[-1] - xs[0])
    umbral_x = max(18.0, ancho_span * 0.16)
    grupos_x: list[float] = []
    for x in xs:
        if not grupos_x or abs(x - grupos_x[-1]) > umbral_x:
            grupos_x.append(float(x))
    if len(grupos_x) >= 3:
        return min(6, len(grupos_x))
    return max(2, min(4, round(n / 2))) if n >= 4 else max(2, n)


@app.get("/health")
def health():
    if not _modelos:
        _cargar_modelos()
    return {
        "status": "ok",
        "modelos": {
            "m1": _modelos.get("m1") is not None,
            "m2": _modelos.get("m2") is not None,
            "m3": _modelos.get("m3") is not None or _modelos.get("m3_world") is not None,
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
            }

        # 1. M2: Segmentación de instancias de vehículos (estilo máscara rosa Roboflow)
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

            # Pintar máscaras estilo Roboflow (rosa fucsia vibrante en principal y suave en secundarios)
            capa_mask = anotada.copy()
            for idx_v, inst in enumerate(reversed(instancias_v[:5])):
                es_prin = idx_v == len(instancias_v[:5]) - 1
                color_relleno = (147, 20, 255) if es_prin else (190, 110, 255)
                if inst["poly"] is not None:
                    cv2.fillPoly(capa_mask, [inst["poly"]], color_relleno)
                else:
                    bx1, by1, bx2, by2 = [int(v) for v in inst["caja"]]
                    cv2.rectangle(capa_mask, (bx1, by1), (bx2, by2), color_relleno, -1)
            cv2.addWeighted(capa_mask, 0.46, anotada, 0.54, 0, anotada)

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

        # 2. M1: Detección de placa + OCR (guiada también por la caja del vehículo principal)
        t0 = time.perf_counter()
        res_m1 = _modelos["m1"].leer(img, caja_vehiculo=vehiculo_caja)
        t_m1 = round((time.perf_counter() - t0) * 1000)

        # 3. M3: Keypoints de ruedas + líneas conectoras estilo Pose Roboflow
        t0 = time.perf_counter()
        ruedas_pts: list[tuple[int, int]] = []

        def _agregar_rueda(rx: float, ry: float, radio_dedup: float = 24.0) -> None:
            if rx <= 1 or ry <= 1:
                return
            if vehiculo_caja is not None and not _dentro_caja(rx, ry, vehiculo_caja, margen=0.12):
                return
            for ex, ey in ruedas_pts:
                if math.hypot(rx - ex, ry - ey) < radio_dedup:
                    return
            ruedas_pts.append((int(round(rx)), int(round(ry))))

        if _modelos["m3"] is not None:
            res_m3 = _modelos["m3"](img, verbose=False, conf=0.22)[0]
            if res_m3.keypoints is not None and res_m3.keypoints.xy is not None:
                kps_xy = res_m3.keypoints.xy.cpu().numpy()
                kps_conf = res_m3.keypoints.conf.cpu().numpy() if res_m3.keypoints.conf is not None else None
                for i in range(len(kps_xy)):
                    for k in range(len(kps_xy[i])):
                        kx, ky = float(kps_xy[i][k][0]), float(kps_xy[i][k][1])
                        kc = float(kps_conf[i][k]) if (kps_conf is not None and k < len(kps_conf[i])) else 1.0
                        if kc > 0.30:
                            _agregar_rueda(kx, ky)

        if len(ruedas_pts) < 2 and _modelos.get("m3_world") is not None:
            res_w = _modelos["m3_world"](img, verbose=False, conf=0.14)[0]
            if res_w.boxes is not None and len(res_w.boxes) > 0:
                for b in res_w.boxes:
                    x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
                    bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
                    if 0.32 <= (bw / bh) <= 2.7:
                        _agregar_rueda((x1 + x2) / 2.0, (y1 + y2) / 2.0)

        t_m3 = round((time.perf_counter() - t0) * 1000)

        tiene_motor_m3 = _modelos.get("m3") is not None or _modelos.get("m3_world") is not None
        ruedas = len(ruedas_pts) if tiene_motor_m3 else None
        ejes = _estimar_ejes(ruedas_pts, categoria)

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

        # Dibujar esqueleto y keypoints de ruedas M3 (estilo Roboflow Pose: líneas + puntos blancos)
        if ruedas_pts:
            pts_ord = sorted(ruedas_pts, key=lambda p: p[0])
            if len(pts_ord) >= 2:
                for idx_p in range(len(pts_ord) - 1):
                    cv2.line(anotada, pts_ord[idx_p], pts_ord[idx_p + 1], (20, 20, 20), 5, cv2.LINE_AA)
                    cv2.line(anotada, pts_ord[idx_p], pts_ord[idx_p + 1], (255, 235, 80), 2, cv2.LINE_AA)
            for rx, ry in pts_ord:
                cv2.circle(anotada, (rx, ry), 9, (15, 15, 15), -1, cv2.LINE_AA)
                cv2.circle(anotada, (rx, ry), 6, (255, 255, 255), -1, cv2.LINE_AA)

        # Dibujar caja y etiqueta de placa M1 encima de las máscaras para máxima nitidez
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

        # Barra superior HUD con resumen de todos los modelos
        hud = anotada.copy()
        cv2.rectangle(hud, (0, 0), (anotada.shape[1], 34), (15, 23, 42), -1)
        cv2.addWeighted(hud, 0.78, anotada, 0.22, 0, anotada)
        resumen_hud = (
            f"Placa: {res_m1['placa'] or '---'} | "
            f"Tipo: {categoria or '---'} | "
            f"Ejes: {ejes or '-'} ({len(ruedas_pts)} ruedas) | "
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
        }
