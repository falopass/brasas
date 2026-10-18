"""Ingesta de GOES: procesa los barridos pendientes de los últimos 40 minutos (FIX-02).

Antes se miraba solo `latest_scan`: si un ciclo se atrasaba, fallaba o el contenedor se reiniciaba,
los barridos intermedios se perdían para siempre. Aquí se prueba que se listan las dos horas, se
descartan los ya procesados, se atienden en orden y se respeta el tope por ciclo.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.providers import goes


def keys_ago(now: datetime, minutes: list[int]) -> list[str]:
    """Claves S3 con el formato que entiende `goes.key_start`, a N minutos de `now`."""
    out = []
    for minutes_ago in minutes:
        moment = now - timedelta(minutes=minutes_ago)
        doy = moment.timetuple().tm_yday
        out.append(f"ABI-L2-FDCF/{moment:%Y}/{doy:03d}/{moment:%H}/"
                   f"OR_ABI-L2-FDCF-M6_G19_s{moment.year}{doy:03d}{moment:%H%M%S}0_e.nc")
    return out


@pytest.fixture
def fake_goes(monkeypatch):
    """Sustituye red y parseo: las claves que se descargan quedan anotadas en orden."""
    state = {"keys": [], "seen": [], "fail": set()}

    async def fake_list(client, satellite, hour):
        # Las dos horas devuelven las mismas claves: lo que se prueba es el filtro de ingesta
        # (ventana, ya procesados, tope), no cómo reparte S3 los barridos entre horas.
        return list(state["keys"])

    async def fake_download(client, satellite, key):
        if key in state["fail"]:
            raise goes.GoesError("barrido corrupto")
        return key.encode()

    def fake_parse(content, satellite, window=None):
        key = content.decode()
        state["seen"].append(key)
        return [{"id": f"goes:{key}", "lat": -33.0, "lon": -71.5, "source": "GOES19_FDCF",
                 "sensor": "ABI", "satellite": "GOES-19", "resolution_m": 2000,
                 "observed_at": state["now"].strftime("%Y-%m-%dT%H:%M:%SZ"), "confidence": "alta"}]

    monkeypatch.setattr(goes, "list_keys", fake_list)
    monkeypatch.setattr(goes, "download", fake_download)
    monkeypatch.setattr(goes, "parse_fdc", fake_parse)
    return state


def prepare(state, minutes: list[int]) -> list[str]:
    now = datetime.now(timezone.utc)
    state["now"] = now
    state["hour"] = now
    state["keys"] = keys_ago(now, minutes)
    return state["keys"]


def test_three_pending_sweeps_are_processed_in_order(make_client, fake_goes):
    keys = prepare(fake_goes, [25, 15, 5])
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert len(asyncio.run(svc.ingest_goes())) == 3
        assert fake_goes["seen"] == keys, "se procesan del más viejo al más nuevo"
        runs = svc.db.query("SELECT source_ref, ok FROM ingest_runs WHERE provider = 'NOAA GOES' ORDER BY id")
        assert [row["source_ref"] for row in runs] == keys
        assert all(row["ok"] for row in runs)


def test_the_same_sweeps_are_not_processed_twice(make_client, fake_goes):
    prepare(fake_goes, [15, 5])
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert len(asyncio.run(svc.ingest_goes())) == 2
        assert asyncio.run(svc.ingest_goes()) == []       # ya están en ingest_runs con ok=1
        assert len(fake_goes["seen"]) == 2


def test_at_most_four_sweeps_per_cycle(make_client, fake_goes):
    prepare(fake_goes, [35, 30, 25, 20, 15, 5])           # seis pendientes, dentro de la ventana
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert len(asyncio.run(svc.ingest_goes())) == 4
        assert len(fake_goes["seen"]) == 4
        # Los dos restantes se toman en el ciclo siguiente.
        asyncio.run(svc.ingest_goes())
        assert len(fake_goes["seen"]) == 6


def test_sweeps_older_than_the_window_are_ignored(make_client, fake_goes):
    prepare(fake_goes, [120, 90, 5])                      # dos fuera de los 40 minutos
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert len(asyncio.run(svc.ingest_goes())) == 1
        assert len(fake_goes["seen"]) == 1


def test_a_broken_sweep_does_not_block_the_others(make_client, fake_goes):
    keys = prepare(fake_goes, [25, 15, 5])
    fake_goes["fail"] = {keys[1]}                         # el del medio no se puede leer
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert len(asyncio.run(svc.ingest_goes())) == 2
        assert fake_goes["seen"] == [keys[0], keys[2]]
        failed = svc.db.query("SELECT source_ref FROM ingest_runs WHERE provider = 'NOAA GOES' AND ok = 0")
        assert [row["source_ref"] for row in failed] == [keys[1]]
        # El barrido roto no queda marcado como hecho: el ciclo siguiente lo reintenta y, si ya
        # se puede leer, entra.
        fake_goes["fail"] = set()
        assert len(asyncio.run(svc.ingest_goes())) == 1
        assert fake_goes["seen"][-1] == keys[1]


def test_goes_disabled_does_nothing(make_client, fake_goes):
    prepare(fake_goes, [5])
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        assert asyncio.run(svc.ingest_goes()) == []
