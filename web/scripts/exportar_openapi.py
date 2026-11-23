"""Exporta la especificación OpenAPI de la aplicación web a docs/openapi.json."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RAIZ_WEB = Path(__file__).resolve().parent.parent
RAIZ_REPO = RAIZ_WEB.parent
sys.path.insert(0, str(RAIZ_WEB))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.main import app  # noqa: E402


def main() -> None:
    destino = RAIZ_REPO / "docs" / "openapi.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OpenAPI exportado en {destino}")


if __name__ == "__main__":
    main()
