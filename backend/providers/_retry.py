"""Reintentos ante errores transitorios de red para los proveedores.

Un timeout o un 5xx de S3 no debe dar por perdido un barrido completo (GOES llega
cada 10 minutos): cada pedido se reintenta hasta dos veces con esperas cortas
fijas. Un 404 (u otro 4xx) no se reintenta: el archivo no existe y esperar no lo
va a crear. Es el único patrón de reintento de los proveedores (GOES, GLM, FIRMS,
Overpass); cada uno decide las esperas vía `delays`.

FIX-64: en un 429 o un 503 la cabecera `Retry-After` manda sobre la espera fija
cuando viene en segundos (Open-Meteo la usa para repartir su cupo); un valor en
fecha HTTP o ilegible se ignora y se espera lo normal. `MAX_RETRY_AFTER_S` es el
tope duro: un valor absurdo no puede congelar el ciclo de ingesta.
"""
from __future__ import annotations

import asyncio

import httpx

RETRY_DELAYS = (0.5, 1.5)  # 3 intentos en total, ~2 s de espera máxima por pedido
# Tope duro para la espera que pide el servidor: `Retry-After: 3600` espera esto, no una hora.
MAX_RETRY_AFTER_S = 10.0


class Failure(Exception):
    """Un pedido falló: agotó sus reintentos o el error no era transitorio."""

    def __init__(self, cause: httpx.HTTPError, attempts: int) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.attempts = attempts

    @property
    def detail(self) -> str:
        """Tipo de error y cuenta real de intentos, para el mensaje del proveedor."""
        plural = "" if self.attempts == 1 else "s"
        return f"{type(self.cause).__name__}, tras {self.attempts} intento{plural}"


def _wait_seconds(response: httpx.Response, fallback: float) -> float:
    """Espera del reintento: el `Retry-After` en segundos de un 429/503, acotado al tope."""
    if response.status_code in (429, 503):
        try:
            return min(max(float(response.headers["Retry-After"]), 0.0), MAX_RETRY_AFTER_S)
        except (KeyError, ValueError):
            pass
    return fallback


async def request(client: httpx.AsyncClient, method: str, url: str,
                  delays: tuple[float, ...] | None = None, **kwargs) -> httpx.Response:
    """Pedido que reintenta `RequestError`, 429 y 5xx; devuelve la respuesta 2xx."""
    waits = RETRY_DELAYS if delays is None else delays
    for attempt in range(len(waits) + 1):
        try:
            response = await client.request(method, url, **kwargs)
            if (response.status_code == 429 or response.status_code >= 500) and attempt < len(waits):
                await asyncio.sleep(_wait_seconds(response, waits[attempt]))
                continue
            response.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.RequestError) and attempt < len(waits):
                await asyncio.sleep(waits[attempt])
                continue
            raise Failure(exc, attempt + 1) from exc
        return response
    raise AssertionError("unreachable")


async def get(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """GET que reintenta `RequestError`, 429 y 5xx; devuelve la respuesta 2xx."""
    return await request(client, "GET", url, **kwargs)
