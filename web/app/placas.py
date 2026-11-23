"""Normalización, validación, corrección por confusión OCR y sugerencias de placas."""
from __future__ import annotations

import re
from collections.abc import Iterable

FORMATO_BOLIVIA = re.compile(r"^\d{3,4}[A-Z]{3}$")
REGEX_CANDIDATO_TEXTO = re.compile(r"\b([0-9A-Z]{3,4})[\s-]?([0-9A-Z]{3})\b")

CONFUSIONES: dict[str, str] = {
    "O": "0",
    "0": "O",
    "I": "1",
    "1": "I",
    "B": "8",
    "8": "B",
    "S": "5",
    "5": "S",
    "Z": "2",
    "2": "Z",
    "G": "6",
    "6": "G",
}

A_DIGITO = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "G": "6", "B": "8"}
A_LETRA = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}


def normalizar(texto: str | None) -> str:
    """Convierte a mayúsculas y elimina guiones, espacios y símbolos."""
    if not texto:
        return ""
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


def formato_valido(placa: str) -> bool:
    """Verifica el formato de placa boliviana: 3 o 4 dígitos seguidos de 3 letras."""
    return bool(FORMATO_BOLIVIA.match(placa))


def corregir_por_posicion(placa: str) -> str:
    """Corrige caracteres ambiguos según la posición esperada en placas de 6 o 7 caracteres."""
    p = normalizar(placa)
    if len(p) not in (6, 7):
        return p
    corte = len(p) - 3
    numeros = "".join(A_DIGITO.get(c, c) for c in p[:corte])
    letras = "".join(A_LETRA.get(c, c) for c in p[corte:])
    return numeros + letras


def variantes(placa: str) -> list[str]:
    """Genera variantes de una placa con hasta 2 sustituciones de confusión OCR."""
    p = normalizar(placa)
    if not p:
        return []
    posiciones = [(i, CONFUSIONES[c]) for i, c in enumerate(p) if c in CONFUSIONES]
    vistas: set[str] = set()
    resultado: list[str] = []

    def _agregar(cand: str) -> None:
        if cand != p and cand not in vistas:
            vistas.add(cand)
            resultado.append(cand)

    for i, alt in posiciones:
        _agregar(p[:i] + alt + p[i + 1:])

    n = len(posiciones)
    for a in range(n):
        i1, alt1 = posiciones[a]
        for b in range(a + 1, n):
            i2, alt2 = posiciones[b]
            if i1 == i2:
                continue
            chars = list(p)
            chars[i1] = alt1
            chars[i2] = alt2
            _agregar("".join(chars))

    return resultado


def levenshtein(a: str, b: str) -> int:
    """Distancia de edición de Levenshtein entre dos cadenas."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            costo = 0 if ca == cb else 1
            curr.append(min(curr[-1] + 1, prev[j] + 1, prev[j - 1] + costo))
        prev = curr
    return prev[-1]


def sugerencias(placa: str, universo: Iterable[str], max_sugerencias: int = 3) -> list[str]:
    """Sugiere placas cercanas en el universo usando confusiones OCR y distancia <= 2."""
    p = normalizar(placa)
    if not p:
        return []
    univ_set = {normalizar(u) for u in universo if normalizar(u) and normalizar(u) != p}
    if not univ_set:
        return []

    elegidas: list[str] = []

    corregida = corregir_por_posicion(p)
    if corregida != p and corregida in univ_set:
        elegidas.append(corregida)

    for v in variantes(p):
        if v in univ_set and v not in elegidas:
            elegidas.append(v)
            if len(elegidas) >= max_sugerencias:
                return elegidas

    cercanas = sorted(
        ((levenshtein(p, u), u) for u in univ_set if u not in elegidas),
        key=lambda item: (item[0], item[1]),
    )
    for dist, u in cercanas:
        if dist <= 2:
            elegidas.append(u)
            if len(elegidas) >= max_sugerencias:
                break

    return elegidas


def extraer_placas_de_texto(mensaje: str | None) -> list[str]:
    """Extrae candidatos a placa de un mensaje libre en español."""
    if not mensaje:
        return []
    texto = mensaje.upper()
    encontradas: list[str] = []
    vistas: set[str] = set()
    for parte1, parte2 in REGEX_CANDIDATO_TEXTO.findall(texto):
        cand = normalizar(parte1 + parte2)
        if not any(ch.isdigit() for ch in cand):
            continue
        if cand not in vistas:
            vistas.add(cand)
            encontradas.append(cand)
    return encontradas
