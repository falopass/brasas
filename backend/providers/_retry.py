"""Reintentos ante errores transitorios de red para los proveedores.

Un timeout o un 5xx de S3 no debe dar por perdido un barrido completo (GOES llega
cada 10 minutos): cada pedido se reintenta hasta dos veces con esperas cortas
fijas. Un 404 (u otro 4xx) no se reintenta: el archivo no existe y esperar no lo
va a crear. Mismo patrón que `firms.request_firms`, extraído para GOES y GLM.
"""
from __future__ import annotations

import asyncio

import httpx

RETRY_DELAYS = (0.5, 1.5)  # 3 intentos en total, ~2 s de espera máxima por pedido
ATTEMPTS = len(RETRY_DELAYS) + 1


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


async def get(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """GET que reintenta `RequestError`, 429 y 5xx; devuelve la respuesta 2xx."""
    for attempt in range(ATTEMPTS):
        try:
            response = await client.get(url, **kwargs)
            if (response.status_code == 429 or response.status_code >= 500) and attempt < len(RETRY_DELAYS):
                await asyncio.sleep(RETRY_DELAYS[attempt])
                continue
            response.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.RequestError) and attempt < len(RETRY_DELAYS):
                await asyncio.sleep(RETRY_DELAYS[attempt])
                continue
            raise Failure(exc, attempt + 1) from exc
        return response
    raise AssertionError("unreachable")
