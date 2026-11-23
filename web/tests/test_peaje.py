"""Pruebas integrales de placas, estados, tarifas, pasos, auth, agente y páginas."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app import inferencia, seguridad
from app.estados import consultar_estado_placa
from app.models import Alerta, Vehiculo
from app.placas import formato_valido, normalizar, sugerencias
from app.tarifas import calcular_monto


def test_normalizar_formato_y_sugerencias():
    assert normalizar("1234-abc") == "1234ABC"
    assert formato_valido("1234ABC") is True
    assert formato_valido("123ABC") is True
    assert formato_valido("ABCD123") is False
    sugs = sugerencias("I234A8C", ["1234ABC", "2345BCD"])
    assert "1234ABC" in sugs


def test_cuatro_estados_sembrados(client, db_session):
    e1 = consultar_estado_placa(db_session, "1234-abc")
    assert e1["estado"] == "REGISTRADA_CON_PASO"
    assert e1["ultimo_paso"] is not None

    e2 = consultar_estado_placa(db_session, "7890GHI")
    assert e2["estado"] == "REGISTRADA_SIN_PASO"
    assert e2["ultimo_paso"] is None

    e3 = consultar_estado_placa(db_session, "9999ZZZ")
    assert e3["estado"] == "IDENTIFICADA_NO_REGISTRADA"

    e4 = consultar_estado_placa(db_session, "8888XXX")
    assert e4["estado"] == "NO_EXISTE"


def test_calcular_monto_tarifas(client, db_session):
    assert calcular_monto(db_session, "camion", 3) == Decimal("20.00")
    assert calcular_monto(db_session, "auto", 4) == Decimal("5.00")
    assert calcular_monto(db_session, "camion", 9) == Decimal("35.00")


def test_flujo_pasos_frame(client, db_session, admin_headers, monkeypatch):
    v_ok = db_session.execute(select(Vehiculo).where(Vehiculo.placa == "1234ABC")).scalar_one()
    saldo_inicial = Decimal(v_ok.saldo)

    def _fake_infer(placa: str, cat: str = "auto", ejes: int = 2, pasajeros: int = 2):
        def _fn(db, imagen_bytes, modo="completo"):
            return {
                "placa": placa,
                "placa_texto_crudo": placa,
                "confianza": 0.95,
                "confianza_deteccion": 0.92,
                "formato_valido": bool(placa),
                "categoria": cat,
                "ejes": ejes,
                "pasajeros": pasajeros,
                "latencia_ms": 42,
                "latencias": {"m1": 15, "m2": 15, "m3": 6, "pasajeros": 6},
                "imagen_anotada": None,
            }
        return _fn

    # 1. Paso OK en caseta 3 (distinta de las sembradas) descuenta saldo
    monkeypatch.setattr(inferencia, "inferir", _fake_infer("1234ABC", "auto", 2, 2))
    r1 = client.post(
        "/api/v1/pasos/frame",
        headers=admin_headers,
        data={"caseta_id": 3},
        files={"imagen": ("f.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["registrado"] is True
    assert d1["estado"] == "OK"
    assert d1["monto"] == 5.0
    db_session.expire_all()
    v_ok_after = db_session.execute(select(Vehiculo).where(Vehiculo.placa == "1234ABC")).scalar_one()
    assert Decimal(v_ok_after.saldo) == saldo_inicial - Decimal("5.00")

    # 2. Segunda llamada inmediata en misma caseta -> duplicado
    r_dup = client.post(
        "/api/v1/pasos/frame",
        headers=admin_headers,
        data={"caseta_id": 3},
        files={"imagen": ("f.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert r_dup.status_code == 200
    assert r_dup.json()["registrado"] is False
    assert r_dup.json()["motivo"] == "duplicado"

    # 3. 3456CDE -> SIN_SALDO + alerta
    alertas_antes = db_session.execute(select(func.count()).select_from(Alerta)).scalar_one()
    monkeypatch.setattr(inferencia, "inferir", _fake_infer("3456CDE", "auto", 2, 1))
    r_sin = client.post(
        "/api/v1/pasos/frame",
        headers=admin_headers,
        data={"caseta_id": 3},
        files={"imagen": ("f.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert r_sin.status_code == 200
    assert r_sin.json()["estado"] == "SIN_SALDO"

    # 4. Placa no registrada -> NO_REGISTRADA + alerta
    monkeypatch.setattr(inferencia, "inferir", _fake_infer("7777XYZ", "auto", 2, 3))
    r_nr = client.post(
        "/api/v1/pasos/frame",
        headers=admin_headers,
        data={"caseta_id": 3},
        files={"imagen": ("f.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert r_nr.status_code == 200
    assert r_nr.json()["estado"] == "NO_REGISTRADA"
    db_session.expire_all()
    alertas_despues = db_session.execute(select(func.count()).select_from(Alerta)).scalar_one()
    assert alertas_despues == alertas_antes + 2

    # 5. Sin placa -> sin_placa
    monkeypatch.setattr(inferencia, "inferir", _fake_infer("", "auto", 2, 0))
    r_sp = client.post(
        "/api/v1/pasos/frame",
        headers=admin_headers,
        data={"caseta_id": 3},
        files={"imagen": ("f.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert r_sp.status_code == 200
    assert r_sp.json()["registrado"] is False
    assert r_sp.json()["motivo"] == "sin_placa"


@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/casetas"),
        ("POST", "/api/v1/pasos/frame"),
        ("POST", "/api/v1/placas/consultar"),
        ("POST", "/api/v1/placas/consultar-imagen"),
        ("GET", "/api/v1/placas/1234ABC/historial"),
        ("GET", "/api/v1/casetas/1/resumen"),
        ("POST", "/api/v1/agente/chat"),
        ("GET", "/api/v1/panel/resumen"),
        ("GET", "/api/v1/estado/inferencia"),
        ("GET", "/api/v1/diagnostico"),
    ],
)
def test_rutas_api_exigen_autenticacion(client, metodo, ruta):
    resp = client.request(metodo, ruta)
    assert resp.status_code == 401


def test_auth_google_lista_blanca(client, monkeypatch):
    def _mock_google(tok: str) -> dict:
        if tok == "tok-no-autorizado":
            return {"email": "intruso@gmail.com", "email_verified": True, "name": "Intruso"}
        if tok == "tok-admin":
            return {"email": "doc.alvaro.pinto.ma@unifranz.edu.bo", "email_verified": True, "name": "Alvaro"}
        raise HTTPException(status_code=401, detail="Token inválido")

    monkeypatch.setattr(seguridad, "verificar_token_google", _mock_google)

    r_403 = client.post("/api/v1/auth/google", json={"id_token": "tok-no-autorizado"})
    assert r_403.status_code == 403

    r_ok = client.post("/api/v1/auth/google", json={"id_token": "tok-admin"})
    assert r_ok.status_code == 200
    body = r_ok.json()
    assert body["access_token"]
    assert body["usuario"]["rol"] == "admin"


def test_agente_chat_fallback_y_sin_placa(client, admin_headers, monkeypatch):
    r_txt = client.post(
        "/api/v1/agente/chat",
        headers=admin_headers,
        data={"mensaje": "Consulta la placa 7890GHI por favor"},
    )
    assert r_txt.status_code == 200
    d_txt = r_txt.json()
    assert d_txt["estado"] == "REGISTRADA_SIN_PASO"
    assert d_txt["fuente"] == "reglas"

    monkeypatch.setattr(
        inferencia,
        "inferir",
        lambda db, img, modo="placa": {"placa": "", "placa_texto_crudo": "", "confianza": 0.0},
    )
    r_img = client.post(
        "/api/v1/agente/chat",
        headers=admin_headers,
        files={"imagen": ("vacio.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert r_img.status_code == 200
    assert r_img.json()["estado"] == "SIN_PLACA_LEGIBLE"


def test_paginas_web_redirigen_sin_sesion_y_abren_con_bearer(client, admin_headers):
    rutas = ["/", "/vehiculos", "/pasos", "/alertas", "/chat", "/estado", "/admin"]
    for ruta in rutas:
        r_anon = client.get(ruta, follow_redirects=False)
        assert r_anon.status_code in (303, 307)
        assert r_anon.headers["location"].endswith("/login")

        r_auth = client.get(ruta, headers=admin_headers)
        assert r_auth.status_code == 200
