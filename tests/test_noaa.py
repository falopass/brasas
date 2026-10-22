"""Pruebas del índice ONI de la NOAA CPC (RISK-06): parseo, frescura, umbrales y endpoint.

El fixture `ONI_TAIL` es real: encabezado y últimas 10 líneas de
https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt capturadas el 19-10-2026.
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from backend.providers import _retry, noaa

ONI_TAIL = """ SEAS  YR   TOTAL   ANOM
  OND 2025  26.04  -0.61
  NDJ 2025  25.96  -0.60
  DJF 2026  26.15  -0.39
  JFM 2026  26.57  -0.21
  FMA 2026  27.34   0.11
  MAM 2026  28.09   0.46
  AMJ 2026  28.74   0.95
  MJJ 2026  29.02   1.39
  JJA 2026  29.09   1.80
  JAS 2026  29.12   2.16
"""

CAPTURA = date(2026, 10, 19)  # día en que se bajó ONI_TAIL: el fixture queda «fresco»


def _cola_vigente(hoy: date | None = None) -> str:
    """Tabla con la última fila en el trimestre centrado en el mes de `hoy`,
    para que las pruebas que descargan la tabla no envejezcan con el calendario."""
    hoy = hoy or date.today()
    code = next(c for c, (m, _) in noaa.SEASONS.items() if m[1] == hoy.month)
    return f" SEAS  YR   TOTAL   ANOM\n  {code} {hoy.year}  29.12   2.16\n"


def test_parse_oni_reads_the_last_row():
    reading = noaa.parse_oni(ONI_TAIL, now=CAPTURA)
    assert (reading.season, reading.year) == ("JAS", 2026)
    assert reading.sst == 29.12 and reading.oni == 2.16


def test_parse_oni_skips_a_corrupt_last_row():
    """Una última línea cortada se salta y queda la fila legible anterior."""
    reading = noaa.parse_oni(ONI_TAIL + "  ASO 2026  29.20   roto\n", now=CAPTURA)
    assert (reading.season, reading.year) == ("JAS", 2026)


def test_parse_oni_rejects_garbage():
    with pytest.raises(noaa.NoaaError):
        noaa.parse_oni("<html>404 no encontrado</html>")


@pytest.mark.parametrize(
    ("tabla", "now", "match"),
    [
        (" SEAS  YR   TOTAL   ANOM\n  SON 2024  27.01   0.30\n", date(2025, 11, 15), "SON 2024.*septiembre–noviembre.*OND 2025"),
        (ONI_TAIL, date(2026, 11, 1), "JAS 2026"),
    ],
    ids=["tabla-congelada", "tres-trimestres"],
)
def test_una_lectura_atrasada_no_se_publica(tabla, now, match):
    """La última fila de hace un año, o de tres trimestres atrás, no pasa como la del mes en curso."""
    with pytest.raises(noaa.NoaaError, match=match):
        noaa.parse_oni(tabla, now=now)


def test_dos_trimestres_atras_todavia_pasa():
    assert noaa.parse_oni(ONI_TAIL, now=date(2026, 10, 31)).season == "JAS"


@pytest.mark.parametrize(
    ("code", "label", "months"),
    [("JAS", "julio–septiembre", (7, 8, 9)), ("DJF", "diciembre–febrero", (12, 1, 2)), ("AMJ", "abril–junio", (4, 5, 6))],
)
def test_season_label_y_months_salen_del_codigo(code, label, months):
    reading = noaa.OniReading(code, 2026, 28.0, 0.0)
    assert reading.season_label == label and reading.season_months == months


def test_phase_thresholds():
    assert noaa.phase_of(2.16) == "nino"
    assert noaa.phase_of(0.5) == "nino"  # el límite mismo ya es El Niño
    assert noaa.phase_of(0.49) == "neutral"
    assert noaa.phase_of(0.0) == "neutral"
    assert noaa.phase_of(-0.49) == "neutral"
    assert noaa.phase_of(-0.5) == "nina"  # el límite mismo ya es La Niña
    assert noaa.phase_of(-1.3) == "nina"


def _fetch(handler) -> noaa.OniReading:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await noaa.fetch_oni(client)

    return asyncio.run(go())


@pytest.fixture
def no_sleeps(monkeypatch):
    """Reintentos sin espera real, como en `test_retry`."""

    async def fake_sleep(seconds: float) -> None:
        pass

    monkeypatch.setattr(_retry.asyncio, "sleep", fake_sleep)


def test_fetch_oni_survives_a_transient_failure(no_sleeps):
    calls = []
    body = _cola_vigente()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("se cayó la red", request=request)
        return httpx.Response(200, text=body)

    reading = _fetch(handler)
    assert reading.oni == 2.16 and len(calls) == 2


def test_fetch_oni_raises_noaaerror_when_cpc_stays_down(no_sleeps):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="caído")

    with pytest.raises(noaa.NoaaError, match="El CPC de la NOAA no respondió"):
        _fetch(handler)
