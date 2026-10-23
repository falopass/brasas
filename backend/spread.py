"""Escenario estimado de propagación armado desde el clima guardado de la comuna (FUEGO-02, FUEGO-24).

Es la misma función que usa la ficha (`routes/public.py`) y los avisos (`alerts.py`): el
escenario que el vecino lee en el aviso y el que ve al abrir la ficha deben ser el mismo
dato, con la misma frescura. Solo lee lo que la ingesta ya calculó (`fwi_daily` y
`risk_hourly`); no hace llamadas nuevas ni simula nada. La pendiente del punto llega por
`terrain` (resuelta por `providers/elevation.slope_aspect`) o por la caché permanente que
esa consulta deja: `estimate` nunca llama a la red por su cuenta.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend import fwi
from backend.db import Database
from backend.providers import elevation

CHILE_TZ = ZoneInfo("America/Santiago")

# Un pronóstico cuya hora más cercana queda a más de esto ya no describe el clima del incendio.
MAX_WIND_HOURS = 6


def _age_es(hours: float) -> str:
    """Edad de un insumo en palabras: «menos de 1 h», «3 h», «2 días»."""
    if hours < 1:
        return "menos de 1 h"
    if hours < 47:
        return f"{round(hours)} h"
    days = round(hours / 24)
    return f"{days} {'día' if days == 1 else 'días'}"


def estimate(db: Database, row: dict[str, Any], now: datetime | None = None,
             terrain: tuple[float, float] | None = None) -> dict[str, Any] | None:
    """Escenario estimado de propagación del incidente con el clima guardado de su comuna.

    Usa el viento pronosticado que ya calcula `compute_risk` (`risk_hourly`, centro de la comuna)
    en la hora más cercana a ahora, y el FFMC más reciente de la comuna (`fwi_daily`, nunca una
    fecha futura). Si la hora más cercana del pronóstico está a más de MAX_WIND_HOURS, el dato
    quedó viejo y no hay escenario — mostrarlo diría «el clima de ahora» con condiciones de días
    atrás. La nota siempre dice de cuándo es cada insumo.

    `terrain` es `(slope_deg, aspect_deg)` ya resuelto del punto —por
    `providers/elevation.slope_aspect`, que hace la llamada al DEM— o None. Sin `terrain` se
    mira la caché permanente de relieve (`slope:<lat>:<lon>`), así un punto ya consultado llega
    igual al escenario del aviso; sin dato, el escenario queda en terreno plano y lo declara.
    """
    code = row["comuna_code"]
    if code is None:
        return None
    now = now or datetime.now(timezone.utc)
    today_cl = now.astimezone(CHILE_TZ).date()
    fwi_row = db.one(
        "SELECT ffmc, date FROM fwi_daily WHERE comuna_code = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (code, today_cl.isoformat()),
    )
    hourly = db.one("SELECT payload, computed_at FROM risk_hourly WHERE comuna_code = ?", (code,))
    if not fwi_row or not hourly:
        return None
    best, best_t, gap = None, None, float("inf")
    for hour in json.loads(hourly["payload"]):
        if hour.get("wind") is None or not hour.get("time"):
            continue
        try:
            t = datetime.fromisoformat(str(hour["time"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        diff = abs((t - now).total_seconds())
        if diff < gap:
            best, best_t, gap = hour, t, diff
    if best is None or gap > MAX_WIND_HOURS * 3600:
        return None
    if terrain is None and row.get("lat") is not None and row.get("lon") is not None:
        cached = db.cache_get(elevation.cache_key(row["lat"], row["lon"]))
        if cached:
            terrain = (float(cached[0]), float(cached[1]))
    scenario = fwi.propagation_scenario(
        fwi_row["ffmc"], best["wind"], best.get("dir"),
        slope_deg=terrain[0] if terrain else None,
        aspect_deg=terrain[1] if terrain else None,
    )
    if scenario is None:
        return None
    ffmc_day = date.fromisoformat(fwi_row["date"])
    ffmc_age_days = (today_cl - ffmc_day).days
    wind_local = best_t.astimezone(CHILE_TZ)
    when = f"{wind_local:%H:%M} del {wind_local.day}-{wind_local.month:02d}"
    wind_src = (
        f"viento del pronóstico para las {when}" if best_t > now else f"viento del pronóstico de las {when} (hace {_age_es(gap / 3600)})"
    )
    ffmc_src = f"combustible fino del {ffmc_day.day}-{ffmc_day.month:02d}"
    if ffmc_age_days:
        ffmc_src += f" (hace {_age_es(ffmc_age_days * 24)})"
    return {
        **scenario,
        "wind_at": best["time"],
        "wind_hours_away": round(gap / 3600, 1),
        "wind_computed_at": hourly["computed_at"],
        "ffmc_date": fwi_row["date"],
        "ffmc_age_days": ffmc_age_days,
        "assumptions": [f"Viento y combustible fino (FFMC) del centro de la comuna, no del punto exacto del fuego; {wind_src}; {ffmc_src}."]
        + scenario["assumptions"],
        "note": f"Escenario estimado con {wind_src} y {ffmc_src}: no es una predicción ni el perímetro del incendio.",
    }
