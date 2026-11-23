"""Almacenamiento de imágenes de evidencia anotadas en PostgreSQL/SQLite."""
from __future__ import annotations

import base64

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Evidencia


def decodificar_data_url(data_url: str | None) -> tuple[bytes, str]:
    """Extrae los bytes y MIME de un data URL base64."""
    if not data_url:
        return b"", "image/jpeg"
    if data_url.startswith("data:") and "," in data_url:
        cabecera, cuerpo = data_url.split(",", 1)
        mime = cabecera[5:].split(";")[0] or "image/jpeg"
        try:
            return base64.b64decode(cuerpo), mime
        except Exception:
            return b"", mime
    try:
        return base64.b64decode(data_url), "image/jpeg"
    except Exception:
        return b"", "image/jpeg"


def guardar_evidencia(
    db: Session,
    paso_id: int,
    imagen_anotada: str | None,
) -> str | None:
    """Guarda únicamente la imagen anotada (con máscaras opacas); nunca el frame original."""
    contenido, mime = decodificar_data_url(imagen_anotada)
    if not contenido:
        return None
    db.add(Evidencia(paso_id=paso_id, contenido=contenido, mime=mime))
    prefijo = settings.base_url.rstrip("/") if settings.base_url else ""
    return f"{prefijo}/evidencias/{paso_id}.jpg"
