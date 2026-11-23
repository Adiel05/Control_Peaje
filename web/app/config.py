"""Configuración centralizada leída desde variables de entorno."""
from __future__ import annotations

import os


def _normalizar_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _bool_env(nombre: str, defecto: bool = False) -> bool:
    val = os.getenv(nombre)
    if val is None:
        return defecto
    return val.strip().lower() in {"1", "true", "yes", "si", "on"}


class Settings:
    """Configuración del servicio web."""

    DOCENTE_EMAIL = "doc.alvaro.pinto.ma@unifranz.edu.bo"

    def __init__(self) -> None:
        self.database_url: str = _normalizar_db_url(
            os.getenv("DATABASE_URL", "sqlite:///./peaje_dev.db")
        )
        self.session_secret: str = os.getenv(
            "SESSION_SECRET", "dev-session-secret-control-peaje-no-usar-en-prod"
        )
        self.jwt_secret: str = os.getenv(
            "JWT_SECRET", "dev-jwt-secret-control-peaje-no-usar-en-prod"
        )
        self.jwt_horas: int = int(os.getenv("JWT_HORAS", "12"))

        self.google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
        self.google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.base_url: str = os.getenv("BASE_URL", "").rstrip("/")

        admins_raw = os.getenv("ADMIN_EMAILS", self.DOCENTE_EMAIL)
        correos = [c.strip().lower() for c in admins_raw.split(",") if c.strip()]
        if self.DOCENTE_EMAIL not in correos:
            correos.append(self.DOCENTE_EMAIL)
        self.admin_emails: list[str] = correos

        self.inference_url: str = os.getenv("INFERENCE_URL", "mock").strip() or "mock"
        self.inference_api_key: str = os.getenv("INFERENCE_API_KEY", "")
        self.inference_timeout: float = float(os.getenv("INFERENCE_TIMEOUT", "40"))

        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

        self.cookie_segura: bool = _bool_env("COOKIE_SEGURA", False)
        self.dedup_segundos: int = int(os.getenv("DEDUP_SEGUNDOS", "30"))
        self.zona_horaria: str = os.getenv("ZONA_HORARIA", "America/La_Paz")


settings = Settings()
