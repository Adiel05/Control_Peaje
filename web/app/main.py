"""Punto de entrada FastAPI: montaje de routers, estáticos, sesión y arranque de BD."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.routers import api, web
from app.seed import ejecutar_seed
from app.tiempo_real import broadcaster

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    broadcaster.set_loop(asyncio.get_running_loop())
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ejecutar_seed(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="API Sistema de Control de Peaje",
    description=(
        "Backend web, API REST v1, tiempo real (SSE) y agente conversacional "
        "para el Sistema Inteligente de Control de Peaje."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    https_only=settings.cookie_segura,
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api.router)
app.include_router(web.router)
