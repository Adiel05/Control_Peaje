"""Cálculo de tarifas según categoría de vehículo y número de ejes."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CATEGORIAS_CANONICAS, Tarifa

CATEGORIAS_CON_EJES = {"camion", "bus"}


def calcular_monto(db: Session, categoria: str | None, ejes: int | None) -> Decimal:
    """Calcula la tarifa aplicable en Bs según la tabla tarifas."""
    cat = (categoria or "auto").strip().lower()
    if cat not in CATEGORIAS_CANONICAS:
        cat = "auto"

    ejes_consulta = (ejes or 2) if cat in CATEGORIAS_CON_EJES else 2

    filas = db.execute(
        select(Tarifa).where(Tarifa.categoria == cat).order_by(Tarifa.ejes.asc())
    ).scalars().all()

    if not filas:
        filas = db.execute(
            select(Tarifa).where(Tarifa.categoria == "auto").order_by(Tarifa.ejes.asc())
        ).scalars().all()

    if not filas:
        return Decimal("5.00")

    for fila in filas:
        if fila.ejes == ejes_consulta:
            return Decimal(fila.monto)

    if ejes_consulta > filas[-1].ejes:
        return Decimal(filas[-1].monto)

    return Decimal(filas[0].monto)
