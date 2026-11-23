"""Cliente HTTP hacia el endpoint remoto de inferencia (Colab/RunPod) con respaldo mock."""
from __future__ import annotations

import base64
import random
import time

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Configuracion

# JPEG 1x1 válido en base64 para el modo mock cuando no hay imagen anotada real
_TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////"
    "////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
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
            "latencia_ms": 25,
            "latencias": {"m1": 25, "m2": 0, "m3": 0, "pasajeros": 0},
            "fuente_m2": "mock",
            "mock": True,
        }
    return {
        "placa": placa,
        "placa_texto_crudo": placa,
        "confianza": 0.94,
        "confianza_deteccion": 0.92,
        "formato_valido": True,
        "categoria": cat,
        "confianza_categoria": 0.91,
        "ejes": ejes,
        "ruedas": ejes,
        "pasajeros": random.randint(1, 3),
        "imagen_anotada": data_url,
        "latencia_ms": 48,
        "latencias": {"m1": 18, "m2": 14, "m3": 8, "pasajeros": 8},
        "fuente_m2": "mock",
        "mock": True,
    }


def inferir(db: Session, imagen_bytes: bytes, modo: str = "completo") -> dict:
    """Envía una imagen al endpoint de inferencia remoto o usa el modo mock."""
    url = url_efectiva(db)
    if url.lower() == "mock":
        return _mock_resultado(imagen_bytes, modo)

    headers = {}
    if settings.inference_api_key:
        headers["X-API-Key"] = settings.inference_api_key

    destino = f"{url.rstrip('/')}/infer"
    try:
        with httpx.Client(timeout=settings.inference_timeout) as client:
            resp = client.post(
                destino,
                files={"imagen": ("frame.jpg", imagen_bytes, "image/jpeg")},
                data={"modo": modo},
                headers=headers,
            )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=503,
                detail=f"Endpoint de inferencia no disponible (HTTP {resp.status_code})",
            )
        return resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Endpoint de inferencia no disponible: {exc}",
        ) from exc


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
        lat_ms = round((time.perf_counter() - inicio) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "url": url, "latencia_ms": lat_ms, "detalle": resp.json()}
        return {
            "ok": False,
            "url": url,
            "latencia_ms": lat_ms,
            "error": f"HTTP {resp.status_code}",
        }
    except Exception as exc:
        lat_ms = round((time.perf_counter() - inicio) * 1000)
        return {"ok": False, "url": url, "latencia_ms": lat_ms, "error": str(exc)}
