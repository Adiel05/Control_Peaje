"""Difusión de eventos en tiempo real vía Server-Sent Events (SSE)."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator


class Broadcaster:
    """Administra suscriptores SSE y permite publicar desde hilos síncronos."""

    def __init__(self) -> None:
        self._suscriptores: list[asyncio.Queue[tuple[str, dict]]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publicar(self, evento: str, datos: dict) -> None:
        if self._loop is None or not self._loop.is_running():
            return
        for cola in list(self._suscriptores):
            self._loop.call_soon_threadsafe(self._poner, cola, (evento, datos))

    @staticmethod
    def _poner(cola: asyncio.Queue[tuple[str, dict]], item: tuple[str, dict]) -> None:
        if cola.full():
            try:
                cola.get_nowait()
            except asyncio.QueueEmpty:
                pass
        cola.put_nowait(item)

    async def suscribirse(self) -> AsyncGenerator[str, None]:
        cola: asyncio.Queue[tuple[str, dict]] = asyncio.Queue(maxsize=100)
        self._suscriptores.append(cola)
        try:
            yield ": conectado\n\n"
            while True:
                try:
                    evento, datos = await asyncio.wait_for(cola.get(), timeout=15.0)
                    payload = json.dumps(datos, ensure_ascii=False, default=str)
                    yield f"event: {evento}\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            if cola in self._suscriptores:
                self._suscriptores.remove(cola)


broadcaster = Broadcaster()
