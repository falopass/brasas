"""Pronóstico de material particulado (PM2,5 y PM10) del modelo CAMS, vía Open-Meteo.

Misma fuente y condiciones que el pronóstico meteorológico (`docs/SOSTENIBILIDAD.md`):
API gratuita para uso no comercial, licencia CC BY 4.0. Se pide en hora local de Chile:
`hourly.time` llega como «AAAA-MM-DDTHH:MM» y cada concentración en µg/m³ puede venir
en null — un valor ausente queda `None`, nunca 0 («sin dato» no es «sin humo»).

BRASA muestra el valor pronosticado y su hora, sin inventar umbrales ni categorías de
salud propias; la medición oficial del aire en Chile es la red SINCA del MMA.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from backend.providers import _retry, weather

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
SOURCE = "CAMS vía Open-Meteo"
SOURCE_URL = "https://air-quality-api.open-meteo.com/"
LICENSE = "CC BY 4.0"

TIMEOUT_S = 3.0  # la ruta promete responder en 4 s: un solo intento dentro de ese margen


class AirError(Exception):
    pass


async def hourly(client: httpx.AsyncClient, lat: float, lon: float) -> list[dict[str, Any]]:
    """Serie horaria [{t, pm2_5, pm10}] del pronóstico de 2 días, en hora local del punto."""
    weather._count(AIR_URL)
    try:
        response = await _retry.get(
            client,
            AIR_URL,
            timeout=TIMEOUT_S,
            delays=(),
            params={
                "latitude": f"{lat:.4f}",
                "longitude": f"{lon:.4f}",
                "hourly": "pm2_5,pm10",
                "forecast_days": 2,
                "timezone": "America/Santiago",
            },
        )
        data = response.json()
    except _retry.Failure as exc:
        raise AirError(f"Open-Meteo Air Quality no respondió ({type(exc.cause).__name__}).") from exc
    except ValueError as exc:
        raise AirError(f"Open-Meteo Air Quality no respondió ({type(exc).__name__}).") from exc
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        raise AirError("Open-Meteo Air Quality no devolvió serie horaria.")
    return [{"t": t, "pm2_5": pm, "pm10": p10} for t, pm, p10 in zip(times, hourly.get("pm2_5") or [], hourly.get("pm10") or [])]


def next_24h(series: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Las próximas 24 horas desde `now` (hora de Chile): la serie empieza a medianoche local."""
    mark = (now or datetime.now(weather.CHILE_TZ)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    out = []
    for row in series:
        try:
            t = datetime.fromisoformat(str(row.get("t") or ""))
        except ValueError:
            continue
        if t.tzinfo is None and t >= mark:
            out.append(row)
            if len(out) >= 24:
                break
    return out
