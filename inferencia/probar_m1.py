"""Prueba rápida local del modelo M1 (detección + fast-plate-ocr) sobre una imagen."""
from __future__ import annotations

import json
import sys

import cv2

from m1_placas import LectorPlacas


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Uso: python probar_m1.py ruta/imagen.jpg")

    img = cv2.imread(sys.argv[1])
    if img is None:
        sys.exit(f"No se pudo leer la imagen: {sys.argv[1]}")

    lector = LectorPlacas()
    resultado = lector.leer(img)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
