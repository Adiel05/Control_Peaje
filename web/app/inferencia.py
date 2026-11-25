"""Cliente hacia el endpoint único de inferencia en la nube, con respaldo M1 real local y modo mock."""
from __future__ import annotations

import base64
import random
import sys
import threading
import time
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Configuracion

# JPEG válido mínimo 1x1 gris para evidencias en modo mock cuando la entrada no es JPEG
_TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////"
    "////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAA"
    "AAAAAAAAAAAAAP/aAAgBAQABPxA="
)

_MOCK_PLACAS = ["1234ABC", "2345BCD", "3456CDE", "4567DEF", "5678EFG", "6789FGH", "9999ZZZ", "0000XYZ"]
_MOCK_CATEGORIAS = {
    "1234ABC": ("auto", 2),
    "2345BCD": ("camion", 3),
    "3456CDE": ("auto", 2),
    "4567DEF": ("moto", 2),
    "5678EFG": ("bus", 3),
    "6789FGH": ("minibus", 2),
    "9999ZZZ": ("auto", 2),
    "0000XYZ": ("camion", 4),
}

_lock_m1_local = threading.Lock()
_lector_m1_local = None
_m1_local_intentado = False


def _obtener_m1_local():
    """Carga perezosa de M1 (YOLOv9 ONNX + fast-plate-ocr) en el servidor web si está disponible."""
    global _lector_m1_local, _m1_local_intentado
    if _m1_local_intentado:
        return _lector_m1_local
    with _lock_m1_local:
        if _m1_local_intentado:
            return _lector_m1_local
        _m1_local_intentado = True
        try:
            raiz_repo = Path(__file__).resolve().parents[2]
            if str(raiz_repo) not in sys.path:
                sys.path.insert(0, str(raiz_repo))
            carpeta_m1 = raiz_repo / "inferencia" / "modelos" / "m1"
            if carpeta_m1.is_dir():
                from inferencia.m1_placas import LectorPlacas

                _lector_m1_local = LectorPlacas(carpeta_modelos=carpeta_m1)
        except Exception:
            _lector_m1_local = None
    return _lector_m1_local


def _inferir_m1_local(imagen_bytes: bytes, modo: str, aviso: str) -> dict | None:
    """Ejecuta M1 real en CPU local cuando Colab está desconectado (sin inventar placas falsas)."""
    lector = _obtener_m1_local()
    if lector is None:
        return None
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(imagen_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        t0 = time.perf_counter()
        res_m1 = lector.leer(img)
        t_m1 = round((time.perf_counter() - t0) * 1000)

        anotada = img.copy()
        if res_m1["caja"]:
            px1, py1, px2, py2 = res_m1["caja"]
            cv2.rectangle(anotada, (px1, py1), (px2, py2), (0, 235, 64), 3)
            texto = f"M1 PLACA: {res_m1['placa'] or '?'}"
            (tw, th), base = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            y_top = max(0, py1 - th - base - 8)
            cv2.rectangle(anotada, (px1, y_top), (min(anotada.shape[1] - 1, px1 + tw + 12), y_top + th + base + 8), (0, 165, 45), -1)
            cv2.putText(anotada, texto, (px1 + 6, y_top + th + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

        hud = anotada.copy()
        cv2.rectangle(hud, (0, 0), (anotada.shape[1], 32), (15, 23, 42), -1)
        cv2.addWeighted(hud, 0.78, anotada, 0.22, 0, anotada)
        cv2.putText(
            anotada,
            f"M1 Local: {res_m1['placa'] or 'Buscando placa...'} (Activa Colab para M2+M3+Pasajeros)",
            (10, 21),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (255, 220, 120),
            1,
            cv2.LINE_AA,
        )

        h, w = anotada.shape[:2]
        if w > 960:
            esc = 960 / w
            anotada = cv2.resize(anotada, (960, max(1, int(h * esc))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", anotada, [cv2.IMWRITE_JPEG_QUALITY, 76])
        data_url = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii") if ok else ""

        es_solo_placa = modo == "placa"
        return {
            **res_m1,
            "categoria": None if es_solo_placa else ("auto" if res_m1["placa"] else None),
            "confianza_categoria": None,
            "ejes": None if es_solo_placa else (2 if res_m1["placa"] else None),
            "ruedas": None,
            "pasajeros": None if es_solo_placa else (1 if res_m1["placa"] else 0),
            "imagen_anotada": data_url,
            "latencia_ms": t_m1,
            "latencias": {"m1": t_m1, "m2": 0, "m3": 0, "pasajeros": 0},
            "fuente_m2": "m1_local",
            "mock": False,
            "modo_m1_local": True,
            "aviso": aviso,
        }
    except Exception:
        return None


def url_efectiva(db: Session | None = None) -> str:
    """Lee INFERENCE_URL desde la tabla configuracion o desde el entorno."""
    if db is not None:
        fila = db.get(Configuracion, "INFERENCE_URL")
        if fila and fila.valor.strip():
            return fila.valor.strip()
    return settings.inference_url


def _mock_resultado(imagen_bytes: bytes, modo: str) -> dict:
    placa = random.choice(_MOCK_PLACAS)
    cat, ejes = _MOCK_CATEGORIAS.get(placa, ("auto", 2))
    data_url = (
        "data:image/jpeg;base64," + base64.b64encode(imagen_bytes).decode()
        if imagen_bytes[:2] == b"\xff\xd8"
        else f"data:image/jpeg;base64,{_TINY_JPEG_B64}"
    )
    if modo == "placa":
        return {
            "placa": placa,
            "placa_texto_crudo": placa,
            "confianza": 0.94,
            "confianza_deteccion": 0.92,
            "formato_valido": True,
            "categoria": None,
            "confianza_categoria": None,
            "ejes": None,
            "ruedas": None,
            "pasajeros": None,
            "imagen_anotada": data_url,
            "latencia_ms": 18,
            "latencias": {"m1": 18, "m2": 0, "m3": 0, "pasajeros": 0},
            "fuente_m2": "mock",
            "mock": True,
        }

    return {
        "placa": placa,
        "placa_texto_crudo": placa,
        "confianza": 0.95,
        "confianza_deteccion": 0.93,
        "formato_valido": True,
        "categoria": cat,
        "confianza_categoria": 0.91,
        "ejes": ejes,
        "ruedas": ejes,
        "pasajeros": random.choice([1, 2, 3]),
        "imagen_anotada": data_url,
        "latencia_ms": 48,
        "latencias": {"m1": 18, "m2": 14, "m3": 8, "pasajeros": 8},
        "fuente_m2": "mock",
        "mock": True,
    }


def inferir(db: Session, imagen_bytes: bytes, modo: str = "completo") -> dict:
    """Envía una imagen al endpoint de inferencia remoto (Colab), usa M1 local si Colab se desconectó, o mock explícito."""
    url = url_efectiva(db)
    if not url or url.lower() == "mock":
        return _mock_resultado(imagen_bytes, modo)

    if url.lower() == "local":
        res_local = _inferir_m1_local(imagen_bytes, modo, "Modo M1 local activo (enciende Colab para M2/M3/Pasajeros)")
        if res_local is not None:
            return res_local
        return _mock_resultado(imagen_bytes, modo)

    headers = {}
    if settings.inference_api_key:
        headers["X-API-Key"] = settings.inference_api_key

    destino = f"{url.rstrip('/')}/infer"
    try:
        with httpx.Client(timeout=min(settings.inference_timeout, 25.0)) as client:
            resp = client.post(
                destino,
                files={"imagen": ("frame.jpg", imagen_bytes, "image/jpeg")},
                data={"modo": modo},
                headers=headers,
            )
        if resp.status_code == 401 and headers:
            # Si Colab arrancó sin API_KEY o con otra clave, reintentar sin cabecera antes de caer a respaldo
            with httpx.Client(timeout=min(settings.inference_timeout, 20.0)) as client:
                resp = client.post(
                    destino,
                    files={"imagen": ("frame.jpg", imagen_bytes, "image/jpeg")},
                    data={"modo": modo},
                )
        if resp.status_code >= 400:
            aviso = f"Colab devolvió HTTP {resp.status_code}; ejecutando M1 real en servidor web (reinicia Colab para M2/M3)"
            res_local = _inferir_m1_local(imagen_bytes, modo, aviso)
            if res_local is not None:
                return res_local
            mock_res = _mock_resultado(imagen_bytes, modo)
            mock_res["aviso"] = f"Inferencia remota HTTP {resp.status_code}, usando respaldo mock"
            return mock_res
        data = resp.json()
        data.setdefault("mock", False)
        return data
    except Exception as exc:
        aviso = (
            f"Túnel de Colab desconectado ({type(exc).__name__}). "
            "M1 Placas+OCR está funcionando en local; vuelve a correr servidor_colab.ipynb para activar M2, M3 y Pasajeros."
        )
        res_local = _inferir_m1_local(imagen_bytes, modo, aviso)
        if res_local is not None:
            return res_local
        mock_res = _mock_resultado(imagen_bytes, modo)
        mock_res["aviso"] = f"Inferencia remota no disponible ({type(exc).__name__}); usando respaldo mock"
        return mock_res


def health(db: Session) -> dict:
    """Consulta /health del endpoint de inferencia configurado."""
    url = url_efectiva(db)
    if url.lower() == "mock":
        return {
            "ok": True,
            "url": "mock",
            "latencia_ms": 1,
            "detalle": {
                "status": "ok",
                "modo": "mock",
                "modelos": {"m1": True, "m2": True, "m3": True, "pasajeros": True},
                "fuente_m2": "mock",
            },
        }

    inicio = time.perf_counter()
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(f"{url.rstrip('/')}/health")
        ms = round((time.perf_counter() - inicio) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "url": url, "latencia_ms": ms, "detalle": resp.json()}
        return {"ok": False, "url": url, "latencia_ms": ms, "error": f"HTTP {resp.status_code}"}
    except Exception as exc:
        ms = round((time.perf_counter() - inicio) * 1000)
        return {"ok": False, "url": url, "latencia_ms": ms, "error": str(exc)}
