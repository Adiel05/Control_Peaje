"""Rutas HTML (Jinja2), autenticación web Google OAuth, SSE y evidencias."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app import inferencia
from app.config import settings
from app.db import get_db
from app.estados import formatear_fecha_lp, resumen_global_hoy
from app.models import (
    CATEGORIAS_CANONICAS,
    Alerta,
    Caseta,
    Configuracion,
    Evidencia,
    Paso,
    Tarifa,
    Usuario,
    Vehiculo,
)
from app.placas import formato_valido, normalizar
from app.seguridad import crear_jwt, usuario_opcional
from app.tiempo_real import broadcaster

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

oauth = OAuth()
if settings.google_client_id and settings.google_client_secret:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "prompt": "select_account",
        },
    )

router = APIRouter(include_in_schema=False)


def _redir_login() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


def _ctx_base(request: Request, usuario: Usuario, pagina: str, **extra) -> dict:
    return {
        "request": request,
        "usuario": usuario,
        "pagina": pagina,
        "categorias": CATEGORIAS_CANONICAS,
        **extra,
    }


@router.get("/login")
def pagina_login(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    cambiar = request.query_params.get("cambiar") == "1"
    if cambiar and "session" in request.scope:
        request.session.clear()
        usuario = None

    oauth_listo = bool(settings.google_client_id and settings.google_client_secret)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "oauth_listo": oauth_listo,
            "usuario": usuario,
            "admin_emails": settings.admin_emails,
        },
    )


@router.get("/auth/google/login")
async def google_login(request: Request):
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(
            status_code=503,
            detail="Google OAuth no configurado (faltan GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)",
        )
    redirect_uri = (
        f"{settings.base_url}/auth/callback"
        if settings.base_url
        else str(request.url_for("auth_callback"))
    )
    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
        prompt="select_account",
    )


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(status_code=503, detail="Google OAuth no configurado")

    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = await oauth.google.userinfo(token=token)

    email = (userinfo.get("email") or "").strip().lower()
    usuario = db.execute(
        select(Usuario).where(Usuario.email_google == email)
    ).scalar_one_or_none()

    if not usuario or not usuario.activo:
        if email in settings.admin_emails:
            usuario = Usuario(
                email_google=email,
                nombre=userinfo.get("name") or "Administrador",
                rol="admin",
                activo=True,
            )
            db.add(usuario)
            db.commit()
            db.refresh(usuario)
        else:
            return templates.TemplateResponse(
                request,
                "acceso_denegado.html",
                {"email": email or "desconocido"},
                status_code=403,
            )

    if not usuario.nombre and userinfo.get("name"):
        usuario.nombre = str(userinfo["name"])[:150]
        db.commit()

    request.session["usuario_id"] = usuario.id
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login?cambiar=1", status_code=303)


@router.get("/")
def panel_principal(
    request: Request,
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()

    resumen = resumen_global_hoy(db)
    pasos_orm = (
        db.execute(
            select(Paso)
            .options(joinedload(Paso.caseta))
            .order_by(Paso.created_at.desc(), Paso.id.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    pasos = []
    for p in pasos_orm:
        _, fecha_legible = formatear_fecha_lp(p.created_at)
        pasos.append({"obj": p, "fecha_legible": fecha_legible})

    alertas_orm = (
        db.execute(
            select(Alerta)
            .options(joinedload(Alerta.paso).joinedload(Paso.caseta))
            .order_by(Alerta.atendida.asc(), Alerta.created_at.desc())
            .limit(12)
        )
        .scalars()
        .all()
    )
    alertas = []
    for a in alertas_orm:
        _, fecha_legible = formatear_fecha_lp(a.created_at)
        alertas.append({"obj": a, "fecha_legible": fecha_legible})

    return templates.TemplateResponse(
        request,
        "panel.html",
        _ctx_base(request, usuario, "panel", resumen=resumen, pasos=pasos, alertas=alertas),
    )


@router.get("/vehiculos")
def pagina_vehiculos(
    request: Request,
    q: str = "",
    msg: str = "",
    err: str = "",
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()

    stmt = select(Vehiculo).order_by(Vehiculo.id.desc())
    termino = q.strip()
    if termino:
        norm = normalizar(termino)
        like_term = f"%{termino}%"
        like_norm = f"%{norm}%" if norm else like_term
        stmt = stmt.where(
            or_(
                Vehiculo.placa.ilike(like_norm),
                Vehiculo.propietario.ilike(like_term),
            )
        )
    vehiculos = db.execute(stmt).scalars().all()
    return templates.TemplateResponse(
        request,
        "vehiculos.html",
        _ctx_base(request, usuario, "vehiculos", vehiculos=vehiculos, q=q, msg=msg, err=err),
    )


@router.post("/vehiculos")
def crear_vehiculo(
    placa: str = Form(...),
    propietario: str = Form(...),
    categoria: str = Form(...),
    ejes: int = Form(2),
    saldo: str = Form("0"),
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    placa_norm = normalizar(placa)
    if not formato_valido(placa_norm):
        return RedirectResponse(
            url="/vehiculos?err=Formato+de+placa+inv%C3%A1lido+(use+3-4+d%C3%ADgitos+y+3+letras,+ej.+1234ABC)",
            status_code=303,
        )

    existe = db.execute(select(Vehiculo).where(Vehiculo.placa == placa_norm)).scalar_one_or_none()
    if existe:
        return RedirectResponse(url=f"/vehiculos?err=La+placa+{placa_norm}+ya+existe", status_code=303)

    try:
        saldo_dec = Decimal(saldo)
    except InvalidOperation:
        saldo_dec = Decimal("0.00")

    cat = categoria if categoria in CATEGORIAS_CANONICAS else "auto"
    db.add(
        Vehiculo(
            placa=placa_norm,
            propietario=propietario.strip()[:150],
            categoria=cat,
            ejes=max(2, min(ejes, 8)),
            saldo=saldo_dec,
            activo=True,
        )
    )
    db.commit()
    return RedirectResponse(url=f"/vehiculos?msg=Veh%C3%ADculo+{placa_norm}+registrado", status_code=303)


@router.post("/vehiculos/{vehiculo_id}/editar")
def editar_vehiculo(
    vehiculo_id: int,
    propietario: str = Form(...),
    categoria: str = Form(...),
    ejes: int = Form(2),
    saldo: str = Form("0"),
    activo: str | None = Form(None),
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    v = db.get(Vehiculo, vehiculo_id)
    if not v:
        return RedirectResponse(url="/vehiculos?err=Veh%C3%ADculo+no+encontrado", status_code=303)

    try:
        v.saldo = Decimal(saldo)
    except InvalidOperation:
        pass
    v.propietario = propietario.strip()[:150]
    if categoria in CATEGORIAS_CANONICAS:
        v.categoria = categoria
    v.ejes = max(2, min(ejes, 8))
    v.activo = activo == "on"
    db.commit()
    return RedirectResponse(url=f"/vehiculos?msg=Veh%C3%ADculo+{v.placa}+actualizado", status_code=303)


@router.post("/vehiculos/{vehiculo_id}/eliminar")
def eliminar_vehiculo(
    vehiculo_id: int,
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    v = db.get(Vehiculo, vehiculo_id)
    if v:
        db.delete(v)
        db.commit()
    return RedirectResponse(url="/vehiculos?msg=Veh%C3%ADculo+eliminado", status_code=303)


@router.get("/pasos")
def pagina_pasos(
    request: Request,
    placa: str = "",
    pagina: int = 1,
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()

    por_pagina = 50
    pagina_actual = max(1, pagina)
    filtro = normalizar(placa)

    base_stmt = select(Paso).options(joinedload(Paso.caseta))
    count_stmt = select(func.count()).select_from(Paso)
    if filtro:
        base_stmt = base_stmt.where(Paso.placa_normalizada.ilike(f"%{filtro}%"))
        count_stmt = count_stmt.where(Paso.placa_normalizada.ilike(f"%{filtro}%"))

    total = db.execute(count_stmt).scalar_one()
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    offset = (pagina_actual - 1) * por_pagina

    pasos_orm = (
        db.execute(base_stmt.order_by(Paso.created_at.desc(), Paso.id.desc()).offset(offset).limit(por_pagina))
        .scalars()
        .all()
    )
    pasos = []
    for p in pasos_orm:
        _, fecha_legible = formatear_fecha_lp(p.created_at)
        pasos.append({"obj": p, "fecha_legible": fecha_legible})

    return templates.TemplateResponse(
        request,
        "pasos.html",
        _ctx_base(
            request,
            usuario,
            "pasos",
            pasos=pasos,
            placa=placa,
            pagina_actual=pagina_actual,
            total_paginas=total_paginas,
            total=total,
        ),
    )


@router.get("/alertas")
def pagina_alertas(
    request: Request,
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()

    alertas_orm = (
        db.execute(
            select(Alerta)
            .options(joinedload(Alerta.paso).joinedload(Paso.caseta))
            .order_by(Alerta.atendida.asc(), Alerta.created_at.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    alertas = []
    for a in alertas_orm:
        _, fecha_legible = formatear_fecha_lp(a.created_at)
        alertas.append({"obj": a, "fecha_legible": fecha_legible})

    return templates.TemplateResponse(
        request,
        "alertas.html",
        _ctx_base(request, usuario, "alertas", alertas=alertas),
    )


@router.post("/alertas/{alerta_id}/atender")
def atender_alerta(
    alerta_id: int,
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()

    alerta = db.get(Alerta, alerta_id)
    if alerta:
        alerta.atendida = True
        db.commit()
        broadcaster.publicar("contadores", resumen_global_hoy(db))
    return RedirectResponse(url="/alertas", status_code=303)


@router.get("/chat")
def pagina_chat(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    if not usuario:
        return _redir_login()
    return templates.TemplateResponse(
        request,
        "chat.html",
        _ctx_base(request, usuario, "chat", gemini_activo=bool(settings.gemini_api_key)),
    )


@router.get("/estado")
def pagina_estado(
    request: Request,
    msg: str = "",
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()

    salud = inferencia.health(db)
    bd_ok = True
    try:
        db.execute(select(func.count()).select_from(Caseta)).scalar_one()
    except Exception:
        bd_ok = False

    return templates.TemplateResponse(
        request,
        "estado.html",
        _ctx_base(
            request,
            usuario,
            "estado",
            salud=salud,
            inference_url=inferencia.url_efectiva(db),
            gemini_configurado=bool(settings.gemini_api_key),
            gemini_modelo=settings.gemini_model,
            bd_ok=bd_ok,
            msg=msg,
        ),
    )


@router.post("/estado/inferencia")
def actualizar_inference_url(
    inference_url: str = Form(...),
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    nueva_url = inference_url.strip() or "mock"
    cfg = db.get(Configuracion, "INFERENCE_URL")
    if cfg:
        cfg.valor = nueva_url
    else:
        db.add(Configuracion(clave="INFERENCE_URL", valor=nueva_url))
    db.commit()
    return RedirectResponse(url="/estado?msg=URL+de+inferencia+actualizada", status_code=303)


@router.post("/estado/token")
def generar_token_api(usuario: Usuario | None = Depends(usuario_opcional)):
    if not usuario:
        raise HTTPException(status_code=401, detail="No autenticado")
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")
    return JSONResponse({"token": crear_jwt(usuario), "expira_horas": settings.jwt_horas})


@router.get("/admin")
def pagina_admin(
    request: Request,
    msg: str = "",
    err: str = "",
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol de administrador")

    tarifas = db.execute(select(Tarifa).order_by(Tarifa.categoria.asc(), Tarifa.ejes.asc())).scalars().all()
    casetas = db.execute(select(Caseta).order_by(Caseta.id.asc())).scalars().all()
    usuarios = db.execute(select(Usuario).order_by(Usuario.id.asc())).scalars().all()
    return templates.TemplateResponse(
        request,
        "admin.html",
        _ctx_base(
            request,
            usuario,
            "admin",
            tarifas=tarifas,
            casetas=casetas,
            usuarios=usuarios,
            msg=msg,
            err=err,
        ),
    )


@router.post("/admin/tarifas")
def guardar_tarifa(
    categoria: str = Form(...),
    ejes: int = Form(...),
    monto: str = Form(...),
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    cat = categoria if categoria in CATEGORIAS_CANONICAS else "auto"
    ejes_val = max(2, min(ejes, 10))
    try:
        monto_dec = Decimal(monto)
    except InvalidOperation:
        return RedirectResponse(url="/admin?err=Monto+inv%C3%A1lido", status_code=303)

    tarifa = db.get(Tarifa, (cat, ejes_val))
    if tarifa:
        tarifa.monto = monto_dec
    else:
        db.add(Tarifa(categoria=cat, ejes=ejes_val, monto=monto_dec))
    db.commit()
    return RedirectResponse(url="/admin?msg=Tarifa+guardada", status_code=303)


@router.post("/admin/tarifas/eliminar")
def eliminar_tarifa(
    categoria: str = Form(...),
    ejes: int = Form(...),
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    tarifa = db.get(Tarifa, (categoria, ejes))
    if tarifa:
        db.delete(tarifa)
        db.commit()
    return RedirectResponse(url="/admin?msg=Tarifa+eliminada", status_code=303)


@router.post("/admin/casetas")
def crear_caseta(
    nombre: str = Form(...),
    ubicacion: str = Form(""),
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    db.add(Caseta(nombre=nombre.strip()[:120], ubicacion=ubicacion.strip()[:200]))
    db.commit()
    return RedirectResponse(url="/admin?msg=Caseta+creada", status_code=303)


@router.post("/admin/casetas/{caseta_id}/editar")
def editar_caseta(
    caseta_id: int,
    nombre: str = Form(...),
    ubicacion: str = Form(""),
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    c = db.get(Caseta, caseta_id)
    if c:
        c.nombre = nombre.strip()[:120]
        c.ubicacion = ubicacion.strip()[:200]
        db.commit()
    return RedirectResponse(url="/admin?msg=Caseta+actualizada", status_code=303)


@router.post("/admin/usuarios")
def agregar_usuario(
    email_google: str = Form(...),
    nombre: str = Form(""),
    rol: str = Form("operador"),
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    correo = email_google.strip().lower()
    if "@" not in correo:
        return RedirectResponse(url="/admin?err=Correo+inv%C3%A1lido", status_code=303)

    rol_val = "admin" if rol == "admin" else "operador"
    existente = db.execute(select(Usuario).where(Usuario.email_google == correo)).scalar_one_or_none()
    if existente:
        existente.rol = rol_val
        existente.activo = True
        if nombre.strip():
            existente.nombre = nombre.strip()[:150]
    else:
        db.add(Usuario(email_google=correo, nombre=nombre.strip()[:150], rol=rol_val, activo=True))
    db.commit()
    return RedirectResponse(url="/admin?msg=Usuario+autorizado", status_code=303)


@router.post("/admin/usuarios/{usuario_id}/toggle")
def toggle_usuario(
    usuario_id: int,
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    objetivo = db.get(Usuario, usuario_id)
    if objetivo and objetivo.email_google != settings.DOCENTE_EMAIL and objetivo.id != usuario.id:
        objetivo.activo = not objetivo.activo
        db.commit()
    return RedirectResponse(url="/admin?msg=Estado+de+usuario+actualizado", status_code=303)


@router.post("/admin/usuarios/{usuario_id}/rol")
def cambiar_rol_usuario(
    usuario_id: int,
    rol: str = Form(...),
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        return _redir_login()
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    objetivo = db.get(Usuario, usuario_id)
    if objetivo and objetivo.email_google != settings.DOCENTE_EMAIL:
        objetivo.rol = "admin" if rol == "admin" else "operador"
        db.commit()
    return RedirectResponse(url="/admin?msg=Rol+actualizado", status_code=303)


@router.get("/eventos")
async def stream_eventos(usuario: Usuario | None = Depends(usuario_opcional)):
    if not usuario:
        raise HTTPException(status_code=401, detail="No autenticado")
    return StreamingResponse(
        broadcaster.suscribirse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/evidencias/{paso_id}.jpg")
def ver_evidencia(
    paso_id: int,
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    if not usuario:
        raise HTTPException(status_code=401, detail="No autenticado")
    ev = db.execute(select(Evidencia).where(Evidencia.paso_id == paso_id)).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    return Response(content=ev.contenido, media_type=ev.mime)
