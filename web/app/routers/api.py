"""API REST v1 documentada en OpenAPI/Swagger (/docs)."""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import agente, diagnostico, inferencia, seguridad, servicio_pasos
from app.db import get_db
from app.estados import consultar_estado_placa, historial_placa, resumen_caseta, resumen_global_hoy
from app.models import Caseta, Usuario
from app.placas import normalizar
from app.seguridad import crear_jwt, requiere_admin, usuario_api

router = APIRouter(prefix="/api/v1", tags=["API Peaje v1"])


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., description="ID token de Google Sign-In obtenido en la app móvil")


class ConsultarPlacaRequest(BaseModel):
    placa: str = Field(..., description="Texto de placa a consultar (ej. 1234ABC o 1234-ABC)")


@router.post("/auth/google", summary="Autenticar con Google Sign-In y emitir JWT")
def auth_google(body: GoogleAuthRequest, db: Session = Depends(get_db)):
    info = seguridad.verificar_token_google(body.id_token)
    email = info["email"].strip().lower()
    usuario = db.execute(
        select(Usuario).where(Usuario.email_google == email)
    ).scalar_one_or_none()

    if not usuario or not usuario.activo:
        raise HTTPException(status_code=403, detail="Acceso denegado: cuenta no autorizada")

    if not usuario.nombre and info.get("name"):
        usuario.nombre = str(info["name"])[:150]
        db.commit()
        db.refresh(usuario)

    token = crear_jwt(usuario)
    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": {
            "id": usuario.id,
            "email": usuario.email_google,
            "nombre": usuario.nombre,
            "rol": usuario.rol,
        },
    }


@router.get("/auth/me", summary="Perfil del usuario autenticado")
def auth_me(usuario: Usuario = Depends(usuario_api)):
    return {
        "id": usuario.id,
        "email": usuario.email_google,
        "nombre": usuario.nombre,
        "rol": usuario.rol,
        "activo": usuario.activo,
    }


@router.get("/casetas", summary="Listar casetas de peaje disponibles")
def listar_casetas(usuario: Usuario = Depends(usuario_api), db: Session = Depends(get_db)):
    casetas = db.execute(select(Caseta).order_by(Caseta.id.asc())).scalars().all()
    return [{"id": c.id, "nombre": c.nombre, "ubicacion": c.ubicacion} for c in casetas]


@router.post("/pasos/frame", summary="Enviar frame desde caseta móvil para inferencia y registro")
async def registrar_frame(
    caseta_id: int = Form(...),
    imagen: UploadFile = File(...),
    usuario: Usuario = Depends(usuario_api),
    db: Session = Depends(get_db),
):
    caseta = db.get(Caseta, caseta_id)
    if not caseta:
        raise HTTPException(status_code=404, detail=f"Caseta {caseta_id} no encontrada")

    contenido = await imagen.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="La imagen enviada está vacía")

    return servicio_pasos.procesar_frame(db, usuario, caseta_id, contenido)


@router.post("/placas/consultar", summary="Consultar estado de una placa por texto")
def consultar_placa_texto(
    body: ConsultarPlacaRequest,
    usuario: Usuario = Depends(usuario_api),
    db: Session = Depends(get_db),
):
    return consultar_estado_placa(db, body.placa)


@router.post("/placas/consultar-imagen", summary="Consultar estado de una placa desde una imagen")
async def consultar_placa_imagen(
    imagen: UploadFile = File(...),
    usuario: Usuario = Depends(usuario_api),
    db: Session = Depends(get_db),
):
    contenido = await imagen.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="La imagen enviada está vacía")

    res_inf = inferencia.inferir(db, contenido, modo="placa")
    placa_norm = normalizar(res_inf.get("placa") or res_inf.get("placa_texto_crudo") or "")
    if not placa_norm:
        raise HTTPException(
            status_code=422,
            detail="imagen sin placa legible, envía otra imagen más nítida",
        )

    consulta = consultar_estado_placa(db, placa_norm)
    return {
        "inferencia": {
            "placa": placa_norm,
            "confianza": res_inf.get("confianza"),
            "formato_valido": consulta["formato_valido"],
        },
        "consulta": consulta,
    }


@router.get("/placas/{placa}/historial", summary="Historial de pasos de una placa")
def obtener_historial_placa(
    placa: str,
    limite: int = 50,
    usuario: Usuario = Depends(usuario_api),
    db: Session = Depends(get_db),
):
    limite_acotado = max(1, min(limite, 200))
    return historial_placa(db, placa, limite=limite_acotado)


@router.get("/casetas/{caseta_id}/resumen", summary="Conteo y recaudación del día en una caseta")
def obtener_resumen_caseta(
    caseta_id: int,
    fecha: date | None = None,
    usuario: Usuario = Depends(usuario_api),
    db: Session = Depends(get_db),
):
    res = resumen_caseta(db, caseta_id, fecha=fecha)
    if res is None:
        raise HTTPException(status_code=404, detail=f"Caseta {caseta_id} no encontrada")
    return res


@router.post("/agente/chat", summary="Consultar al agente conversacional por texto y/o imagen")
async def chat_agente(
    mensaje: str | None = Form(None),
    imagen: UploadFile | None = File(None),
    historial: str | None = Form(None),
    usuario: Usuario = Depends(usuario_api),
    db: Session = Depends(get_db),
):
    img_bytes = await imagen.read() if imagen is not None else None
    if img_bytes == b"":
        img_bytes = None

    if not (mensaje and mensaje.strip()) and not img_bytes:
        raise HTTPException(
            status_code=400,
            detail="Debes enviar un mensaje de texto o una imagen de placa.",
        )

    hist_lista: list[dict] | None = None
    if historial:
        try:
            parsed = json.loads(historial)
            if isinstance(parsed, list):
                hist_lista = parsed
        except Exception:
            hist_lista = None

    return agente.responder(
        db=db,
        usuario=usuario,
        mensaje=mensaje,
        imagen_bytes=img_bytes,
        historial=hist_lista,
    )


@router.get("/panel/resumen", summary="Resumen global del día para el panel")
def obtener_panel_resumen(usuario: Usuario = Depends(usuario_api), db: Session = Depends(get_db)):
    return resumen_global_hoy(db)


@router.get("/estado/inferencia", summary="Verificar conectividad y salud del endpoint de inferencia")
def estado_inferencia(usuario: Usuario = Depends(usuario_api), db: Session = Depends(get_db)):
    return inferencia.health(db)


@router.get("/diagnostico", summary="Diagnóstico del entorno del servidor web (solo admin)")
def obtener_diagnostico(usuario: Usuario = Depends(requiere_admin)):
    return diagnostico.info()
