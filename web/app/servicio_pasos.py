"""Orquestación de registro de pasos, dedup, saldos, alertas y SSE."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import inferencia
from app.config import settings
from app.estados import a_utc, formatear_fecha_lp, resumen_global_hoy
from app.evidencias import guardar_evidencia
from app.models import Alerta, Caseta, Paso, Usuario, Vehiculo
from app.placas import formato_valido, normalizar
from app.tarifas import calcular_monto
from app.tiempo_real import broadcaster


def serializar_paso(paso: Paso, caseta_nombre: str | None = None) -> dict:
    fecha_iso, fecha_legible = formatear_fecha_lp(paso.created_at)
    return {
        "id": paso.id,
        "placa_leida": paso.placa_leida,
        "placa_normalizada": paso.placa_normalizada,
        "confianza_ocr": paso.confianza_ocr,
        "categoria_detectada": paso.categoria_detectada,
        "ejes_detectados": paso.ejes_detectados,
        "monto": float(paso.monto),
        "caseta_id": paso.caseta_id,
        "caseta_nombre": caseta_nombre or (paso.caseta.nombre if paso.caseta else f"Caseta {paso.caseta_id}"),
        "imagen_url": paso.imagen_url,
        "estado": paso.estado,
        "pasajeros": paso.pasajeros,
        "latencia_ms": paso.latencia_ms,
        "fecha_iso": fecha_iso,
        "fecha_legible": fecha_legible,
    }


def procesar_frame(db: Session, usuario: Usuario | None, caseta_id: int, imagen_bytes: bytes) -> dict:
    """Procesa un frame capturado desde la caseta y registra el paso si corresponde."""
    caseta = db.get(Caseta, caseta_id)
    if not caseta:
        raise ValueError(f"Caseta {caseta_id} no encontrada")

    res = inferencia.inferir(db, imagen_bytes, modo="completo")
    placa_raw = res.get("placa_texto_crudo") or res.get("placa") or ""
    placa_norm = normalizar(res.get("placa") or placa_raw)

    meta_visual = {
        "imagen_anotada": res.get("imagen_anotada"),
        "categoria": res.get("categoria"),
        "ejes": res.get("ejes"),
        "ruedas": res.get("ruedas"),
        "pasajeros": res.get("pasajeros"),
        "latencia_ms": res.get("latencia_ms"),
        "latencias": res.get("latencias"),
        "mock": bool(res.get("mock", False)),
        "aviso": res.get("aviso"),
    }

    if not placa_norm:
        return {"registrado": False, "motivo": "sin_placa", **meta_visual, "inferencia": res}

    conf = float(res.get("confianza") or 0.0)
    if not formato_valido(placa_norm) and conf < 0.7:
        return {
            "registrado": False,
            "motivo": "lectura_dudosa",
            "placa": placa_norm,
            **meta_visual,
            "inferencia": res,
        }

    ahora = datetime.now(timezone.utc)
    ultimo_misma_placa = db.execute(
        select(Paso)
        .where(Paso.placa_normalizada == placa_norm, Paso.caseta_id == caseta_id)
        .order_by(Paso.created_at.desc(), Paso.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if ultimo_misma_placa is not None:
        delta = ahora - a_utc(ultimo_misma_placa.created_at)
        if delta < timedelta(seconds=settings.dedup_segundos):
            return {
                "registrado": False,
                "motivo": "duplicado",
                "placa": placa_norm,
                **meta_visual,
                "paso": serializar_paso(ultimo_misma_placa, caseta.nombre),
            }

    vehiculo = db.execute(
        select(Vehiculo).where(Vehiculo.placa == placa_norm)
    ).scalar_one_or_none()

    categoria = res.get("categoria") or (vehiculo.categoria if vehiculo else "auto")
    ejes_raw = res.get("ejes")
    ejes = int(ejes_raw) if ejes_raw is not None else (vehiculo.ejes if vehiculo else 2)
    monto = calcular_monto(db, categoria, ejes)

    tipo_alerta: str | None = None
    if vehiculo is None:
        estado = "NO_REGISTRADA"
        tipo_alerta = "NO_REGISTRADA"
    elif not vehiculo.activo or Decimal(vehiculo.saldo) < monto:
        estado = "SIN_SALDO"
        tipo_alerta = "SIN_SALDO"
    else:
        estado = "OK"
        vehiculo.saldo = Decimal(vehiculo.saldo) - monto

    paso = Paso(
        placa_leida=str(placa_raw)[:32] or placa_norm,
        placa_normalizada=placa_norm,
        confianza_ocr=round(conf, 4) if res.get("confianza") is not None else None,
        categoria_detectada=categoria,
        ejes_detectados=ejes,
        monto=monto,
        caseta_id=caseta_id,
        usuario_id=usuario.id if usuario else None,
        imagen_url=None,
        estado=estado,
        pasajeros=res.get("pasajeros"),
        latencia_ms=int(res["latencia_ms"]) if res.get("latencia_ms") is not None else None,
        created_at=ahora,
    )
    db.add(paso)
    db.flush()

    paso.imagen_url = guardar_evidencia(
        db,
        paso.id,
        res.get("imagen_anotada"),
    )

    alerta_creada: Alerta | None = None
    if tipo_alerta:
        alerta_creada = Alerta(paso_id=paso.id, tipo=tipo_alerta, atendida=False, created_at=ahora)
        db.add(alerta_creada)
        db.flush()

    db.commit()
    db.refresh(paso)

    paso_dict = serializar_paso(paso, caseta.nombre)
    broadcaster.publicar("paso", paso_dict)
    if alerta_creada is not None:
        broadcaster.publicar(
            "alerta",
            {
                "id": alerta_creada.id,
                "paso_id": paso.id,
                "tipo": alerta_creada.tipo,
                "placa": paso.placa_normalizada,
                "caseta": caseta.nombre,
                "monto": float(paso.monto),
                "fecha_legible": paso_dict["fecha_legible"],
            },
        )
    broadcaster.publicar("contadores", resumen_global_hoy(db))

    return {
        "registrado": True,
        "paso": paso_dict,
        "placa": paso.placa_normalizada,
        "categoria": paso.categoria_detectada,
        "ejes": paso.ejes_detectados,
        "monto": float(paso.monto),
        "estado": paso.estado,
        "pasajeros": paso.pasajeros,
        "saldo_restante": float(vehiculo.saldo) if vehiculo else None,
        "latencia_ms": paso.latencia_ms,
        "latencias": res.get("latencias"),
        "imagen_anotada": res.get("imagen_anotada"),
        "mock": bool(res.get("mock", False)),
        "aviso": res.get("aviso"),
    }
