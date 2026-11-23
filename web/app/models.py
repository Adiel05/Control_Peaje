"""Modelos ORM de la base de datos del peaje."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

CATEGORIAS_CANONICAS = ("moto", "auto", "minibus", "camion", "bus")


def utcnow() -> datetime:
    """Devuelve la fecha y hora actual con zona horaria UTC."""
    return datetime.now(timezone.utc)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email_google: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), default="", nullable=False)
    rol: Mapped[str] = mapped_column(String(20), default="operador", nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Vehiculo(Base):
    __tablename__ = "vehiculos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    placa: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    propietario: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria: Mapped[str] = mapped_column(String(20), nullable=False)
    ejes: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    saldo: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Caseta(Base):
    __tablename__ = "casetas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    ubicacion: Mapped[str] = mapped_column(String(200), default="", nullable=False)


class Tarifa(Base):
    __tablename__ = "tarifas"

    categoria: Mapped[str] = mapped_column(String(20), primary_key=True)
    ejes: Mapped[int] = mapped_column(Integer, primary_key=True)
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class Paso(Base):
    __tablename__ = "pasos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    placa_leida: Mapped[str] = mapped_column(String(32), nullable=False)
    placa_normalizada: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    confianza_ocr: Mapped[float | None] = mapped_column(Float, nullable=True)
    categoria_detectada: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ejes_detectados: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    caseta_id: Mapped[int] = mapped_column(ForeignKey("casetas.id"), nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    imagen_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    pasajeros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latencia_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)

    caseta: Mapped[Caseta] = relationship("Caseta")
    usuario: Mapped[Usuario | None] = relationship("Usuario")
    evidencia: Mapped[Evidencia | None] = relationship("Evidencia", back_populates="paso", uselist=False)


class Alerta(Base):
    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paso_id: Mapped[int] = mapped_column(ForeignKey("pasos.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    atendida: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    paso: Mapped[Paso] = relationship("Paso")


class Evidencia(Base):
    __tablename__ = "evidencias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paso_id: Mapped[int] = mapped_column(ForeignKey("pasos.id"), unique=True, nullable=False)
    contenido: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    mime: Mapped[str] = mapped_column(String(50), default="image/jpeg", nullable=False)

    paso: Mapped[Paso] = relationship("Paso", back_populates="evidencia")


class Configuracion(Base):
    __tablename__ = "configuracion"

    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(Text, default="", nullable=False)
