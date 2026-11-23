"""Lógica de estados de placas, historial y resúmenes por caseta y globales."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import Alerta, Caseta, Paso, Vehiculo
from app.placas import formato_valido, normalizar, sugerencias

ZONA_LA_PAZ = ZoneInfo(settings.zona_horaria)


def a_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def a_la_paz(dt: datetime) -> datetime:
    return a_utc(dt).astimezone(ZONA_LA_PAZ)


def formatear_fecha_lp(dt: datetime) -> tuple[str, str]:
    lp = a_la_paz(dt)
    return lp.isoformat(), lp.strftime("%d/%m/%Y %H:%M:%S")


def _rango_utc_para_fecha(fecha: date | None = None) -> tuple[date, datetime, datetime]:
    if fecha is None:
        fecha = datetime.now(ZONA_LA_PAZ).date()
    inicio_lp = datetime.combine(fecha, time.min, tzinfo=ZONA_LA_PAZ)
    fin_lp = inicio_lp + timedelta(days=1)
    return fecha, inicio_lp.astimezone(timezone.utc), fin_lp.astimezone(timezone.utc)


def _universo_placas(db: Session) -> list[str]:
    placas_v = db.execute(select(Vehiculo.placa)).scalars().all()
    placas_p = db.execute(select(Paso.placa_normalizada).distinct()).scalars().all()
    return list({*placas_v, *placas_p})


def _serializar_paso_resumen(paso: Paso) -> dict:
    fecha_iso, fecha_legible = formatear_fecha_lp(paso.created_at)
    return {
        "id": paso.id,
        "fecha_iso": fecha_iso,
        "fecha_legible": fecha_legible,
        "caseta_id": paso.caseta_id,
        "caseta": paso.caseta.nombre if paso.caseta else f"Caseta {paso.caseta_id}",
        "categoria": paso.categoria_detectada,
        "ejes": paso.ejes_detectados,
        "monto": float(paso.monto),
        "estado": paso.estado,
        "pasajeros": paso.pasajeros,
        "imagen_url": paso.imagen_url,
    }


def consultar_estado_placa(db: Session, texto: str) -> dict:
    """Evalúa los cuatro estados posibles de una placa en el sistema."""
    placa_norm = normalizar(texto)
    valido = formato_valido(placa_norm)

    vehiculo = (
        db.execute(select(Vehiculo).where(Vehiculo.placa == placa_norm)).scalar_one_or_none()
        if placa_norm
        else None
    )

    pasos = (
        db.execute(
            select(Paso)
            .options(joinedload(Paso.caseta))
            .where(Paso.placa_normalizada == placa_norm)
            .order_by(Paso.created_at.desc(), Paso.id.desc())
        )
        .scalars()
        .all()
        if placa_norm
        else []
    )

    total_pasos = len(pasos)
    ultimo_paso = _serializar_paso_resumen(pasos[0]) if pasos else None
    vehiculo_dict = (
        {
            "id": vehiculo.id,
            "placa": vehiculo.placa,
            "propietario": vehiculo.propietario,
            "categoria": vehiculo.categoria,
            "ejes": vehiculo.ejes,
            "saldo": float(vehiculo.saldo),
            "activo": vehiculo.activo,
        }
        if vehiculo
        else None
    )

    sugs: list[str] = []
    if vehiculo and pasos:
        estado = "REGISTRADA_CON_PASO"
        mensaje = (
            f"La placa {placa_norm} está registrada ({vehiculo.categoria}, saldo Bs {float(vehiculo.saldo):.2f}) "
            f"y tiene {total_pasos} paso(s). Último paso el {ultimo_paso['fecha_legible']} "
            f"en {ultimo_paso['caseta']} ({ultimo_paso['categoria']}, Bs {ultimo_paso['monto']:.2f})."
        )
    elif vehiculo and not pasos:
        estado = "REGISTRADA_SIN_PASO"
        mensaje = (
            f"La placa {placa_norm} está registrada a nombre de {vehiculo.propietario} "
            f"({vehiculo.categoria}, saldo Bs {float(vehiculo.saldo):.2f}), pero nunca pasó por el peaje."
        )
    elif not vehiculo and pasos:
        estado = "IDENTIFICADA_NO_REGISTRADA"
        mensaje = (
            f"Alerta: la placa {placa_norm} fue identificada por la cámara ({total_pasos} paso(s)), "
            f"pero NO está registrada en el sistema (posible evasión). Último registro el "
            f"{ultimo_paso['fecha_legible']} en {ultimo_paso['caseta']}."
        )
    else:
        estado = "NO_EXISTE"
        sugs = sugerencias(placa_norm, _universo_placas(db)) if placa_norm else []
        if not placa_norm:
            mensaje = "No se proporcionó una placa válida para consultar."
        elif not valido:
            mensaje = (
                f"La placa '{placa_norm}' no cumple el formato boliviano (3 o 4 dígitos y 3 letras) "
                "y no existe ningún registro en el sistema."
            )
        else:
            mensaje = f"No existe ningún registro de la placa {placa_norm} en vehículos ni en pasos."
        if sugs:
            mensaje += f" ¿Quisiste decir {', '.join(sugs)}?"

    if not valido and not sugs and placa_norm and estado != "NO_EXISTE":
        sugs = sugerencias(placa_norm, _universo_placas(db))

    return {
        "placa_consultada": texto,
        "placa_normalizada": placa_norm,
        "formato_valido": valido,
        "estado": estado,
        "mensaje": mensaje,
        "vehiculo": vehiculo_dict,
        "ultimo_paso": ultimo_paso,
        "total_pasos": total_pasos,
        "sugerencias": sugs,
    }


def historial_placa(db: Session, placa: str, limite: int = 50) -> dict:
    """Devuelve el historial de pasos de una placa normalizada."""
    placa_norm = normalizar(placa)
    pasos = (
        db.execute(
            select(Paso)
            .options(joinedload(Paso.caseta))
            .where(Paso.placa_normalizada == placa_norm)
            .order_by(Paso.created_at.desc(), Paso.id.desc())
            .limit(limite)
        )
        .scalars()
        .all()
    )
    return {
        "placa_normalizada": placa_norm,
        "total": len(pasos),
        "pasos": [_serializar_paso_resumen(p) for p in pasos],
    }


def resumen_caseta(db: Session, caseta_id: int, fecha: date | None = None) -> dict | None:
    """Calcula el conteo de pasos, recaudación y alertas de una caseta en una fecha (hora La Paz)."""
    caseta = db.get(Caseta, caseta_id)
    if not caseta:
        return None
    fecha_ref, inicio_utc, fin_utc = _rango_utc_para_fecha(fecha)
    pasos = (
        db.execute(
            select(Paso).where(
                Paso.caseta_id == caseta_id,
                Paso.created_at >= inicio_utc,
                Paso.created_at < fin_utc,
            )
        )
        .scalars()
        .all()
    )

    recaudacion = Decimal("0.00")
    por_categoria: dict[str, int] = {}
    for p in pasos:
        if p.estado == "OK":
            recaudacion += Decimal(p.monto)
        cat = p.categoria_detectada or "sin_categoria"
        por_categoria[cat] = por_categoria.get(cat, 0) + 1

    alertas_total = db.execute(
        select(func.count())
        .select_from(Alerta)
        .join(Paso, Alerta.paso_id == Paso.id)
        .where(
            Paso.caseta_id == caseta_id,
            Paso.created_at >= inicio_utc,
            Paso.created_at < fin_utc,
        )
    ).scalar_one()

    alertas_pend = db.execute(
        select(func.count())
        .select_from(Alerta)
        .join(Paso, Alerta.paso_id == Paso.id)
        .where(
            Paso.caseta_id == caseta_id,
            Alerta.atendida.is_(False),
            Paso.created_at >= inicio_utc,
            Paso.created_at < fin_utc,
        )
    ).scalar_one()

    return {
        "caseta_id": caseta.id,
        "caseta_nombre": caseta.nombre,
        "fecha": fecha_ref.isoformat(),
        "total_pasos": len(pasos),
        "recaudacion_bs": float(recaudacion),
        "por_categoria": por_categoria,
        "alertas_generadas": int(alertas_total),
        "alertas_pendientes": int(alertas_pend),
    }


def resumen_global_hoy(db: Session) -> dict:
    """Devuelve contadores globales del día (hora La Paz) para el panel en tiempo real."""
    fecha_ref, inicio_utc, fin_utc = _rango_utc_para_fecha(None)
    pasos_hoy = db.execute(
        select(func.count())
        .select_from(Paso)
        .where(Paso.created_at >= inicio_utc, Paso.created_at < fin_utc)
    ).scalar_one()

    recaudacion_hoy = db.execute(
        select(func.coalesce(func.sum(Paso.monto), 0)).where(
            Paso.created_at >= inicio_utc,
            Paso.created_at < fin_utc,
            Paso.estado == "OK",
        )
    ).scalar_one()

    alertas_pendientes = db.execute(
        select(func.count()).select_from(Alerta).where(Alerta.atendida.is_(False))
    ).scalar_one()

    return {
        "fecha": fecha_ref.isoformat(),
        "pasos_hoy": int(pasos_hoy),
        "recaudacion_hoy": float(recaudacion_hoy or 0),
        "alertas_pendientes": int(alertas_pendientes),
    }
