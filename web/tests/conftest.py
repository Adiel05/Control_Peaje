"""Fixtures de pytest usando SQLite temporal e inferencia mock."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

RAIZ_WEB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_WEB))

_TMP_DB = Path(tempfile.gettempdir()) / "control_peaje_pytest.sqlite"
if _TMP_DB.exists():
    _TMP_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ["INFERENCE_URL"] = "mock"
os.environ["GEMINI_API_KEY"] = ""
os.environ["ADMIN_EMAILS"] = "doc.alvaro.pinto.ma@unifranz.edu.bo,admin.test@gmail.com"
os.environ["COOKIE_SEGURA"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Usuario  # noqa: E402
from app.seguridad import crear_jwt  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
    if _TMP_DB.exists():
        try:
            _TMP_DB.unlink()
        except OSError:
            pass


@pytest.fixture()
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def admin_headers(client, db_session):
    admin = db_session.execute(
        select(Usuario).where(Usuario.email_google == "doc.alvaro.pinto.ma@unifranz.edu.bo")
    ).scalar_one()
    tok = crear_jwt(admin)
    return {"Authorization": f"Bearer {tok}"}
