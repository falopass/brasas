"""Estado de El Niño / La Niña (ENSO) según el índice ONI de la NOAA.

Fuente pública del Climate Prediction Center (CPC) de la NOAA: la tabla ASCII del Oceanic
Niño Index (ONI), publicada en https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
(verificada en octubre de 2026). Son datos del gobierno de EE. UU.: dominio público, sin clave.

El ONI es la media móvil de 3 meses de la anomalía de temperatura del mar en la región
Niño 3.4 (columna ANOM de la tabla). La fase se calcula con el umbral estándar del CPC
sobre el último trimestre publicado: ONI ≥ +0,5 °C → El Niño; ONI ≤ −0,5 °C → La Niña;
entre medio → neutral. (El CPC declara un episodio formal solo si el umbral se sostiene
varios trimestres con respuesta atmosférica; aquí se muestra el valor vigente del índice,
que es lo que el panel explica.)

BRASA lo muestra como contexto de la temporada, no como pronóstico: el ONI inclina las
probabilidades del clima (más o menos lluvia, más o menos calor) pero no dice cuántos
incendios habrá.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from backend.providers import _retry

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
SOURCE = "NOAA · Climate Prediction Center (CPC)"
SOURCE_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"


class NoaaError(Exception):
    pass


@dataclass
class OniReading:
    season: str  # trimestre móvil en código del CPC: «JAS» = julio–septiembre
    year: int
    sst: float   # temperatura absoluta del mar en Niño 3.4 (columna TOTAL), °C
    oni: float   # anomalía de 3 meses (columna ANOM): el índice ONI propiamente tal, °C


def parse_oni(body: str) -> OniReading:
    """Última fila legible de la tabla ONI: temporada, año, TSM y anomalía."""
    last = None
    for line in body.splitlines():
        parts = line.split()
        if len(parts) != 4 or not parts[0].isalpha():
            continue  # encabezado «SEAS YR TOTAL ANOM» y líneas dañadas se saltan
        try:
            last = OniReading(parts[0].upper(), int(parts[1]), float(parts[2]), float(parts[3]))
        except ValueError:
            continue
    if last is None:
        raise NoaaError("La tabla ONI del CPC no trajo ninguna fila legible.")
    return last


def phase_of(oni: float) -> str:
    """Fase ENSO por umbral del CPC sobre el ONI: ±0,5 °C."""
    if oni >= 0.5:
        return "nino"
    if oni <= -0.5:
        return "nina"
    return "neutral"


async def fetch_oni(client: httpx.AsyncClient) -> OniReading:
    """Descarga la tabla ONI del CPC y devuelve su última lectura."""
    try:
        response = await _retry.get(client, ONI_URL)
    except _retry.Failure as exc:
        raise NoaaError(f"El CPC de la NOAA no respondió ({exc.detail}).") from exc.cause
    return parse_oni(response.text)
