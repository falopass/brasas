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
from datetime import date

import httpx

from backend.providers import _retry

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
SOURCE = "NOAA · Climate Prediction Center (CPC)"
SOURCE_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"

# Los doce trimestres móviles del CPC: código → ((meses), etiqueta en español). El mes
# central es el del año de la etiqueta (JAS 2026 = julio–septiembre con agosto de 2026
# al centro; NDJ 2025 = noviembre 2025–enero 2026 con diciembre de 2025 al centro).
SEASONS = {
    "DJF": ((12, 1, 2), "diciembre–febrero"),
    "JFM": ((1, 2, 3), "enero–marzo"),
    "FMA": ((2, 3, 4), "febrero–abril"),
    "MAM": ((3, 4, 5), "marzo–mayo"),
    "AMJ": ((4, 5, 6), "abril–junio"),
    "MJJ": ((5, 6, 7), "mayo–julio"),
    "JJA": ((6, 7, 8), "junio–agosto"),
    "JAS": ((7, 8, 9), "julio–septiembre"),
    "ASO": ((8, 9, 10), "agosto–octubre"),
    "SON": ((9, 10, 11), "septiembre–noviembre"),
    "OND": ((10, 11, 12), "octubre–diciembre"),
    "NDJ": ((11, 12, 1), "noviembre–enero"),
}


class NoaaError(Exception):
    pass


@dataclass
class OniReading:
    season: str  # trimestre móvil en código del CPC: «JAS» = julio–septiembre
    year: int
    sst: float  # temperatura absoluta del mar en Niño 3.4 (columna TOTAL), °C
    oni: float  # anomalía de 3 meses (columna ANOM): el índice ONI propiamente tal, °C

    @property
    def season_months(self) -> tuple[int, int, int]:
        return SEASONS[self.season][0]

    @property
    def season_label(self) -> str:
        """El trimestre en palabras: «JAS» → «julio–septiembre»."""
        return SEASONS[self.season][1]


def parse_oni(body: str, now: date | None = None) -> OniReading:
    """Última fila legible de la tabla ONI: temporada, año, TSM y anomalía.

    Una tabla atrasada —su último trimestre queda más de dos trimestres detrás del
    centrado en el mes de `now` (por omisión, hoy)— levanta NoaaError: el CPC la
    actualiza cada trimestre y BRASA no publica una vieja como si fuera la vigente.
    """
    last = None
    for line in body.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[0].upper() not in SEASONS:
            continue  # encabezado «SEAS YR TOTAL ANOM», líneas dañadas y códigos ajenos se saltan
        try:
            last = OniReading(parts[0].upper(), int(parts[1]), float(parts[2]), float(parts[3]))
        except ValueError:
            continue
    if last is None:
        raise NoaaError("La tabla ONI del CPC no trajo ninguna fila legible.")
    hoy = now or date.today()
    if (hoy.year * 12 + hoy.month) - (last.year * 12 + last.season_months[1]) > 2:
        esperado = next(c for c, (m, _) in SEASONS.items() if m[1] == hoy.month)
        raise NoaaError(
            f"La tabla ONI del CPC llegó atrasada: su última lectura es {last.season} {last.year} "
            f"({last.season_label}) y se esperaba {esperado} {hoy.year} o un trimestre cercano."
        )
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
