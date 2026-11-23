"""Datos iniciales idempotentes (docente admin, casetas, tarifas, 22 vehículos y pasos base)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Alerta, Caseta, Paso, Tarifa, Usuario, Vehiculo

VEHICULOS_SEED = [
    ("1234ABC", "Carlos Mendoza", "auto", 2, Decimal("100.00"), True),
    ("2345BCD", "Transportes Andinos SRL", "camion", 3, Decimal("200.00"), True),
    ("3456CDE", "Lucía Quispe", "auto", 2, Decimal("0.00"), True),
    ("4567DEF", "Marco Rojas", "moto", 2, Decimal("50.00"), True),
    ("5678EFG", "Flota Bolívar SA", "bus", 3, Decimal("180.00"), True),
    ("6789FGH", "Sindicato 16 de Noviembre", "minibus", 2, Decimal("80.00"), True),
    ("7890GHI", "Andrea Vargas", "auto", 2, Decimal("60.00"), True),
    ("8901HIJ", "Jorge Mamani", "camion", 4, Decimal("250.00"), True),
    ("9012IJK", "Sofía Paredes", "auto", 2, Decimal("45.00"), True),
    ("1122JKL", "Pedro Flores", "moto", 2, Decimal("30.00"), True),
    ("2233KLM", "Expreso El Dorado", "bus", 2, Decimal("150.00"), True),
    ("3344LMN", "Cooperativa Vallegrande", "minibus", 2, Decimal("95.00"), True),
    ("4455MNO", "Logística Oriente", "camion", 5, Decimal("320.00"), True),
    ("5566NOP", "Elena Gutiérrez", "auto", 2, Decimal("75.00"), True),
    ("6677OPQ", "Roberto Chávez", "camion", 2, Decimal("110.00"), True),
    ("7788PQR", "Diana Morales", "auto", 2, Decimal("40.00"), True),
    ("8899QRS", "Trans Copacabana", "bus", 3, Decimal("210.00"), True),
    ("9900RST", "Fernando Torrez", "minibus", 2, Decimal("64.00"), True),
    ("1020STU", "Miguel Ángel Paz", "moto", 2, Decimal("25.00"), True),
    ("2030TUV", "Carga Pesada Sur", "camion", 6, Decimal("400.00"), True),
    ("3040UVW", "Valeria Justiniano", "auto", 2, Decimal("55.00"), True),
    ("4050VWX", "Héctor Salvatierra", "minibus", 2, Decimal("72.00"), True),
]

TARIFAS_SEED = [
    ("moto", 2, Decimal("3.00")),
    ("auto", 2, Decimal("5.00")),
    ("minibus", 2, Decimal("8.00")),
    ("camion", 2, Decimal("15.00")),
    ("camion", 3, Decimal("20.00")),
    ("camion", 4, Decimal("25.00")),
    ("camion", 5, Decimal("30.00")),
    ("camion", 6, Decimal("35.00")),
    ("bus", 2, Decimal("15.00")),
    ("bus", 3, Decimal("20.00")),
]

CASETAS_SEED = [
    ("Caseta Norte - Av. Banzer", "Km 12 Carretera al Norte"),
    ("Caseta Sur - Doble Vía La Guardia", "Km 14 Doble Vía La Guardia"),
    ("Caseta Este - Carretera a Cotoca", "Km 10 Carretera a Cotoca"),
]


def ejecutar_seed(db: Session) -> None:
    """Siembra usuarios admin, casetas, tarifas, vehículos y pasos iniciales si faltan."""
    for correo in settings.admin_emails:
        existe = db.execute(
            select(Usuario).where(Usuario.email_google == correo)
        ).scalar_one_or_none()
        if not existe:
            nombre = "Docente Administrador" if correo == settings.DOCENTE_EMAIL else "Administrador"
            db.add(Usuario(email_google=correo, nombre=nombre, rol="admin", activo=True))
        elif existe.rol != "admin" or not existe.activo:
            existe.rol = "admin"
            existe.activo = True

    if db.execute(select(func.count()).select_from(Caseta)).scalar_one() == 0:
        for nombre, ubicacion in CASETAS_SEED:
            db.add(Caseta(nombre=nombre, ubicacion=ubicacion))

    for cat, ejes, monto in TARIFAS_SEED:
        existe_tarifa = db.get(Tarifa, (cat, ejes))
        if not existe_tarifa:
            db.add(Tarifa(categoria=cat, ejes=ejes, monto=monto))

    for placa, prop, cat, ejes, saldo, activo in VEHICULOS_SEED:
        existe_v = db.execute(select(Vehiculo).where(Vehiculo.placa == placa)).scalar_one_or_none()
        if not existe_v:
            db.add(
                Vehiculo(
                    placa=placa,
                    propietario=prop,
                    categoria=cat,
                    ejes=ejes,
                    saldo=saldo,
                    activo=activo,
                )
            )

    db.flush()

    if db.execute(select(func.count()).select_from(Paso)).scalar_one() == 0:
        casetas = db.execute(select(Caseta).order_by(Caseta.id.asc())).scalars().all()
        c1 = casetas[0].id
        c2 = casetas[1].id if len(casetas) > 1 else c1
        ahora = datetime.now(timezone.utc)

        pasos_iniciales = [
            Paso(
                placa_leida="1234ABC",
                placa_normalizada="1234ABC",
                confianza_ocr=0.96,
                categoria_detectada="auto",
                ejes_detectados=2,
                monto=Decimal("5.00"),
                caseta_id=c1,
                imagen_url=None,
                estado="OK",
                pasajeros=2,
                latencia_ms=310,
                created_at=ahora - timedelta(hours=3),
            ),
            Paso(
                placa_leida="1234ABC",
                placa_normalizada="1234ABC",
                confianza_ocr=0.94,
                categoria_detectada="auto",
                ejes_detectados=2,
                monto=Decimal("5.00"),
                caseta_id=c2,
                imagen_url=None,
                estado="OK",
                pasajeros=1,
                latencia_ms=295,
                created_at=ahora - timedelta(hours=1),
            ),
            Paso(
                placa_leida="2345BCD",
                placa_normalizada="2345BCD",
                confianza_ocr=0.93,
                categoria_detectada="camion",
                ejes_detectados=3,
                monto=Decimal("20.00"),
                caseta_id=c1,
                imagen_url=None,
                estado="OK",
                pasajeros=1,
                latencia_ms=350,
                created_at=ahora - timedelta(hours=2),
            ),
            Paso(
                placa_leida="2345BCD",
                placa_normalizada="2345BCD",
                confianza_ocr=0.91,
                categoria_detectada="camion",
                ejes_detectados=3,
                monto=Decimal("20.00"),
                caseta_id=c2,
                imagen_url=None,
                estado="OK",
                pasajeros=2,
                latencia_ms=340,
                created_at=ahora - timedelta(minutes=45),
            ),
        ]
        for p in pasos_iniciales:
            db.add(p)

        paso_no_reg = Paso(
            placa_leida="9999ZZZ",
            placa_normalizada="9999ZZZ",
            confianza_ocr=0.89,
            categoria_detectada="auto",
            ejes_detectados=2,
            monto=Decimal("5.00"),
            caseta_id=c1,
            imagen_url=None,
            estado="NO_REGISTRADA",
            pasajeros=1,
            latencia_ms=320,
            created_at=ahora - timedelta(minutes=25),
        )
        db.add(paso_no_reg)
        db.flush()
        db.add(Alerta(paso_id=paso_no_reg.id, tipo="NO_REGISTRADA", atendida=False, created_at=paso_no_reg.created_at))

    db.commit()
