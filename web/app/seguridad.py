"""Autenticación con Google ID token, JWT para la app móvil y sesiones web."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Usuario

bearer_scheme = HTTPBearer(auto_error=False)


def crear_jwt(usuario: Usuario) -> str:
    """Emite un JWT firmado con HS256 para autenticar peticiones de la app móvil."""
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario.id),
        "email": usuario.email_google,
        "rol": usuario.rol,
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + timedelta(hours=settings.jwt_horas)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decodificar_jwt(token: str) -> dict | None:
    """Valida y decodifica el JWT propio; devuelve None si es inválido o expiró."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception:
        return None


def verificar_token_google(token: str) -> dict:
    """Valida un Google id_token y exige que el correo esté verificado."""
    try:
        audience = settings.google_client_id or None
        info = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Token de Google inválido: {exc}") from exc

    if not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="Correo de Google no verificado")
    if not info.get("email"):
        raise HTTPException(status_code=401, detail="El token de Google no contiene correo")
    return info


def usuario_opcional(
    request: Request,
    credenciales: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario | None:
    """Resuelve al usuario autenticado por sesión web o por Bearer JWT."""
    usuario_id = None
    if "session" in request.scope:
        usuario_id = request.session.get("usuario_id")
    if usuario_id is not None:
        usuario = db.get(Usuario, int(usuario_id))
        if usuario and usuario.activo:
            return usuario

    if credenciales and credenciales.credentials:
        payload = decodificar_jwt(credenciales.credentials)
        if payload and payload.get("sub"):
            usuario = db.get(Usuario, int(payload["sub"]))
            if usuario and usuario.activo:
                return usuario
    return None


def usuario_api(usuario: Usuario | None = Depends(usuario_opcional)) -> Usuario:
    """Exige autenticación válida para rutas de la API."""
    if usuario is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    return usuario


def requiere_admin(usuario: Usuario = Depends(usuario_api)) -> Usuario:
    """Exige rol de administrador."""
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol de administrador")
    return usuario
