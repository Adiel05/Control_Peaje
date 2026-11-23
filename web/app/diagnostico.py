"""Copia del módulo de diagnóstico de entorno para despliegue en Render (/web)."""
from __future__ import annotations

import json
import platform
import sys
from importlib import metadata


def _version_paquete(nombre: str) -> str:
    try:
        return metadata.version(nombre)
    except metadata.PackageNotFoundError:
        return "no instalado"


def info() -> dict:
    """Recopila versiones de Python, librerías clave y estado de GPU/CUDA."""
    datos: dict = {
        "python": sys.version.split()[0],
        "python_completo": sys.version,
        "plataforma": platform.platform(),
        "ejecutable": sys.executable,
    }

    try:
        import torch  # type: ignore

        cuda_ok = bool(torch.cuda.is_available())
        datos["torch"] = getattr(torch, "__version__", "desconocida")
        datos["cuda_version"] = torch.version.cuda or "N/A"
        datos["cuda_disponible"] = cuda_ok
        datos["gpu_nombre"] = torch.cuda.get_device_name(0) if cuda_ok else "CPU"
    except Exception:
        datos["torch"] = "no instalado"
        datos["cuda_version"] = "no instalado"
        datos["cuda_disponible"] = False
        datos["gpu_nombre"] = "no instalado"

    for mod, dist in [
        ("ultralytics", "ultralytics"),
        ("onnxruntime", "onnxruntime"),
        ("fastapi", "fastapi"),
        ("numpy", "numpy"),
        ("fast_plate_ocr", "fast-plate-ocr"),
    ]:
        try:
            importado = __import__(mod)
            datos[mod] = getattr(importado, "__version__", _version_paquete(dist))
        except Exception:
            datos[mod] = "no instalado"

    return datos


if __name__ == "__main__":
    print(json.dumps(info(), indent=2, ensure_ascii=False))
