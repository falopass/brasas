"""Ingesta de GOES: procesa los barridos pendientes de los últimos 40 minutos (FIX-02).

Antes se miraba solo `latest_scan`: si un ciclo se atrasaba, fallaba o el contenedor se reiniciaba,
los barridos intermedios se perdían para siempre. Aquí se prueba que se listan las horas necesarias,
se descartan los ya procesados, se atienden en orden, se respeta el tope y que un barrido ilegible
—o un listado caído— no se lleve por delante lo que sí se pudo leer.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import services as services_mod
from backend.providers import goes

# Claves reales de noaa-goes19 (ABI-L2-FDCF) del 2026-10-21: el día en que producción dejó de
# recibir detecciones GOES. El fixture fija el formato S3 que debe reconocer el relleno.
REAL_KEYS = json.loads((Path(__file__).parent / "data" / "goes19_fdcf_20261021.json").read_text(encoding="utf-8"))


def key_for(moment: datetime) -> str:
    """Clave S3 con el formato que entiende `goes.key_start`."""
    doy = moment.timetuple().tm_yday
    return (f"ABI-L2-FDCF/{moment:%Y}/{doy:03d}/{moment:%H}/"
            f"OR_ABI-L2-FDCF-M6_G19_s{moment.year}{doy:03d}{moment:%H%M%S}0_e.nc")


@pytest.fixture
def fake_goes(monkeypatch):
    """Sustituye red y parseo. `by_hour` guarda las claves por hora, a propósito desordenadas."""
    state = {"by_hour": {}, "seen": [], "fail": set(), "fail_hours": set(), "parse_fail": set(),
             "listed": [], "now": None}

    async def fake_list(client, satellite, hour):
        state["listed"].append(hour.hour)
        if hour.hour in state["fail_hours"]:
            raise goes.GoesError("listado caído")
        return list(state["by_hour"].get(hour.hour, []))

    async def fake_download(client, satellite, key):
        if key in state["fail"]:
            raise goes.GoesError("barrido corrupto")
        return key.encode()

    def fake_parse(content, satellite, window=None):
        key = content.decode()
        if key in state["parse_fail"]:
            raise KeyError("variable esperada ausente en el HDF5")
        state["seen"].append(key)
        return [{"id": f"goes:{key}", "lat": -33.0, "lon": -71.5, "source": "GOES19_FDCF",
                 "sensor": "ABI", "satellite": "GOES-19", "resolution_m": 2000,
                 "observed_at": state["now"].strftime("%Y-%m-%dT%H:%M:%SZ"), "confidence": "alta"}]

    monkeypatch.setattr(goes, "list_keys", fake_list)
    monkeypatch.setattr(goes, "download", fake_download)
    monkeypatch.setattr(goes, "parse_fdc", fake_parse)
    return state


def prepare(state, now: datetime, minutes: list[int]) -> list[str]:
    """Coloca las claves en su hora real, insertadas de la más nueva a la más vieja (desordenadas)."""
    state["now"] = now
    state["by_hour"] = {}
    keys = []
    for minutes_ago in sorted(minutes, reverse=True):   # al revés: el orden de listado no es el cronológico
        moment = now - timedelta(minutes=minutes_ago)
        key = key_for(moment)
        state["by_hour"].setdefault(moment.hour, []).append(key)
        keys.append(key)
    return sorted(keys)


def clock(monkeypatch, moment: datetime) -> None:
    monkeypatch.setattr(services_mod, "utcnow", lambda: moment)


def test_three_pending_sweeps_are_processed_in_order(make_client, fake_goes, monkeypatch):
    now = datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc)   # la ventana cruza a las 02:xx
    keys = prepare(fake_goes, now, [35, 20, 5])
    clock(monkeypatch, now)
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert len(asyncio.run(svc.ingest_goes())) == 3
        assert fake_goes["seen"] == keys, "se procesan del más viejo al más nuevo"
        runs = svc.db.query("SELECT source_ref, ok FROM ingest_runs WHERE provider = 'NOAA GOES' ORDER BY id")
        assert [row["source_ref"] for row in runs] == keys
        assert all(row["ok"] for row in runs)


@pytest.mark.parametrize("now, minutes, listed, seen_ago", [
    # 03:50 → la ventana empieza 03:10: todo en la misma hora, no hace falta listar la anterior.
    (datetime(2026, 10, 18, 3, 50, tzinfo=timezone.utc), [30, 5], [3], [30, 5]),
    # 03:10 → la ventana empieza 02:30: hay que mirar las dos horas.
    (datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc), [35, 5], [3, 2], [35, 5]),
    # 00:05 con la ventana abriendo a las 23:25: hay que listar las horas 23 y 0.
    (datetime(2026, 10, 19, 0, 5, tzinfo=timezone.utc), [35, 3], [0, 23], [35, 3]),
    # 31 dic 23:5x → 1 ene 00:0x: el barrido del año anterior se procesa igual.
    (datetime(2027, 1, 1, 0, 5, tzinfo=timezone.utc), [30, 3], [0, 23], [30, 3]),
    # Dos barridos fuera de los 40 minutos se ignoran; el reciente entra.
    (datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc), [120, 90, 5], [3, 2], [5]),
])
def test_the_window_lists_only_the_hours_it_needs(make_client, fake_goes, monkeypatch, now, minutes, listed, seen_ago):
    prepare(fake_goes, now, minutes)
    clock(monkeypatch, now)
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        fake_goes["listed"].clear()
        result = asyncio.run(svc.ingest_goes())
        assert fake_goes["listed"] == listed
        assert len(result) == len(seen_ago)
        assert fake_goes["seen"] == sorted(key_for(now - timedelta(minutes=m)) for m in seen_ago)


def test_a_failed_listing_of_the_previous_hour_does_not_discard_the_current_one(make_client, fake_goes, monkeypatch):
    now = datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc)
    keys = prepare(fake_goes, now, [35, 8, 5])        # una en la hora 2, dos en la hora 3
    current = [key for key in keys if "/03/" in key]
    clock(monkeypatch, now)
    fake_goes["fail_hours"] = {2}                     # la hora anterior no se puede listar
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        stored = asyncio.run(svc.ingest_goes())
        assert len(stored) == 2, "los barridos de la hora actual sí se procesan"
        assert fake_goes["seen"] == current
        # Y la hora caída queda registrada con su nombre: si no, el estado no puede mostrar el hueco.
        failed = svc.db.one("SELECT source_ref, ok, message FROM ingest_runs WHERE ok = 0")
        assert failed["source_ref"] == "listado S3" and "T02Z" in failed["message"]


def test_everything_fails_when_no_hour_can_be_listed(make_client, fake_goes, monkeypatch):
    now = datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc)
    prepare(fake_goes, now, [35, 5])
    clock(monkeypatch, now)
    fake_goes["fail_hours"] = {2, 3}
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert asyncio.run(svc.ingest_goes()) == []
        status = client.get("/api/status").json()
        assert any(r["product"] == "ABI-L2-FDCF" and not r["ok"] for r in status["runs"])


@pytest.mark.parametrize("minutes, first, second", [
    ([15, 5], 2, 0),                    # ya procesados: el ciclo siguiente no los repite
    ([35, 30, 25, 20, 15, 5], 4, 2),    # seis pendientes: 4 por ciclo, los dos restantes después
])
def test_each_cycle_takes_at_most_four_sweeps_and_never_repeats(make_client, fake_goes, monkeypatch, minutes, first, second):
    now = datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc)
    prepare(fake_goes, now, minutes)
    clock(monkeypatch, now)
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert len(asyncio.run(svc.ingest_goes())) == first
        assert len(fake_goes["seen"]) == first
        assert len(asyncio.run(svc.ingest_goes())) == second
        assert len(fake_goes["seen"]) == first + second


def test_a_broken_sweep_does_not_block_the_others(make_client, fake_goes, monkeypatch):
    now = datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc)
    keys = prepare(fake_goes, now, [25, 15, 5])
    clock(monkeypatch, now)
    fake_goes["fail"] = {keys[1]}                          # el del medio no se puede descargar
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


def test_a_parse_error_keeps_the_previous_sweeps(make_client, fake_goes, monkeypatch):
    """Un HDF5 con un campo inesperado lanza KeyError, no GoesError: no puede tirar lo ya leído."""
    now = datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc)
    keys = prepare(fake_goes, now, [25, 15, 5])
    clock(monkeypatch, now)
    fake_goes["parse_fail"] = {keys[1]}
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        stored = asyncio.run(svc.ingest_goes())
        assert len(stored) == 2, "los barridos buenos se devuelven igual"
        assert [row["id"] for row in stored] == [f"goes:{keys[0]}", f"goes:{keys[2]}"]
        failed = svc.db.query("SELECT source_ref, message FROM ingest_runs WHERE provider = 'NOAA GOES' AND ok = 0")
        assert [row["source_ref"] for row in failed] == [keys[1]]
        assert "KeyError" in failed[0]["message"]
        # El ciclo siguiente ya no repite los buenos: quedaron con ok=1.
        assert asyncio.run(svc.ingest_goes()) == []


def test_goes_disabled_does_nothing(make_client, fake_goes, monkeypatch):
    now = datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc)
    clock(monkeypatch, now)
    prepare(fake_goes, now, [5])
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        assert asyncio.run(svc.ingest_goes()) == []


def test_status_shows_the_last_sweeps_so_a_gap_can_be_seen(make_client):
    """DET-13: un fallo intermedio no puede desaparecer porque el último barrido salió bien."""
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        for index, ok in enumerate([1, 0, 1]):       # falla el del medio
            svc.db.execute("INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, "
                           "message, source_ref) VALUES (?,?,?,?,?,?,?,?,?)",
                           ("NOAA GOES", "GOES19_FDCF", f"2026-10-18T03:0{index}:00Z", f"2026-10-18T03:0{index}:40Z",
                            ok, 10, 10, "", f"barrido-{index}"))
        sweeps = client.get("/api/status").json()["goes_sweeps"]
        assert [s["source_ref"] for s in sweeps] == ["barrido-2", "barrido-1", "barrido-0"]
        assert [s["ok"] for s in sweeps] == [True, False, True]


def goes_run(db, sweep_minutes_ago: int, ok: int = 1, run_minutes_ago: int | None = None) -> None:
    """Un barrido de GOES en ingest_runs: `source_ref` lleva la hora del barrido (clave S3 real) y
    `started_at` la de la corrida, que en el relleno inicial puede ser mucho más reciente."""
    started = datetime.now(timezone.utc) - timedelta(minutes=sweep_minutes_ago if run_minutes_ago is None else run_minutes_ago)
    at = started.strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute("INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, "
               "message, source_ref) VALUES (?,?,?,?,?,?,?,?,?)",
               ("NOAA GOES", "GOES19_FDCF", at, at, ok, 10, 10, "",
                key_for(datetime.now(timezone.utc) - timedelta(minutes=sweep_minutes_ago))))


def test_status_derives_the_goes_gap_of_the_last_hour(make_client):
    """DET-13: el hueco lo decide el servidor: faltan más de 2 de los 6 barridos esperados por hora."""
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        body = client.get("/api/status").json()          # sin barridos todavía: el hueco es total
        assert body["goes_missing"] == 6 and body["goes_gap"] is True

        for index in range(6):                           # la hora completa, un barrido cada 10 min
            goes_run(svc.db, 55 - index * 10)
        body = client.get("/api/status").json()
        assert body["goes_missing"] == 0 and body["goes_gap"] is False

        svc.db.execute("DELETE FROM ingest_runs")
        for index in range(3):                           # solo 3 llegaron: faltan 3
            goes_run(svc.db, 50 - index * 10)
        goes_run(svc.db, 5, ok=0)                        # un fallo no cuenta como llegado
        goes_run(svc.db, 70)                             # fuera de la última hora tampoco
        goes_run(svc.db, 90, run_minutes_ago=2)          # relleno: barrido viejo recién ingerido no cuenta
        body = client.get("/api/status").json()
        assert body["goes_missing"] == 3 and body["goes_gap"] is True


def test_the_backfill_does_not_swallow_the_last_minutes(make_client, fake_goes, monkeypatch):
    """El relleno no toma los barridos de la ventana del ciclo: esos tienen que avisar."""
    now = datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc)
    prepare(fake_goes, now, [5, 120])                # uno reciente y uno de hace dos horas
    clock(monkeypatch, now)
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        # El relleno pide barridos en la rejilla de media hora: ninguno de los dos cae ahí.
        added = asyncio.run(svc.backfill_goes(hours=6, every_min=30))
        assert added == 0
        assert fake_goes["seen"] == []
        # El ciclo normal sí procesa el reciente.
        assert len(asyncio.run(svc.ingest_goes())) == 1


def test_tests_run_without_the_background_scheduler(make_client):
    """Las pruebas corren con BRASA_SCHEDULER=0: sin bucles de fondo, el relleno lo llama cada prueba
    a mano. Si eso cambiara, estas pruebas dejarían de ser deterministas."""
    with make_client() as client:
        assert client.app.state.services.settings.scheduler_enabled is False


def test_two_ingest_calls_do_not_run_at_the_same_time(make_client, monkeypatch):
    """Los puntos de entrada públicos toman el lock: dos llamadas (cron y arranque) se serializan."""
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        events: list[str] = []

        async def slow_body():
            events.append("inicio")
            await asyncio.sleep(0.05)
            events.append("fin")
            return []

        monkeypatch.setattr(svc, "_ingest_firms", slow_body)

        async def both():
            await asyncio.gather(svc.ingest_firms(), svc.ingest_firms())

        asyncio.run(both())
        assert events == ["inicio", "fin", "inicio", "fin"], "sin lock se solaparían"


def test_the_backfill_marks_its_detections_as_evaluated(make_client, fake_goes, monkeypatch):
    """El relleno llena el mapa, no despierta: sus detecciones no vuelven a la recuperación de avisos."""
    now = datetime(2026, 10, 18, 3, 10, tzinfo=timezone.utc)
    sweep = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)   # 02:00, en la rejilla
    fake_goes["by_hour"] = {sweep.hour: [key_for(sweep)]}
    fake_goes["now"] = now
    clock(monkeypatch, now)
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert asyncio.run(svc.backfill_goes(hours=6, every_min=30)) == 1
        assert svc.pending_alert_observations() == [], "el relleno no deja pendientes de aviso"


def seed_goes_observation(db, observed_at: str) -> None:
    """Última detección GOES guardada: la referencia para medir el hueco del relleno."""
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, confidence, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("goes:viejo", "GOES19_FDCF", "ABI", "GOES-19", 2000, -33.0, -71.5, observed_at, "alta", observed_at),
    )


def test_goes_backfill_hours_covers_the_gap_with_a_cap():
    now = datetime(2026, 10, 22, 4, 30, tzinfo=timezone.utc)
    assert services_mod.goes_backfill_hours(None, now) == 6
    assert services_mod.goes_backfill_hours("2026-10-22T03:30:00Z", now) == 6
    assert services_mod.goes_backfill_hours("2026-10-21T20:00:21Z", now) == 9
    assert services_mod.goes_backfill_hours("2026-10-20T22:00:21Z", now) == 24
    assert services_mod.goes_backfill_hours("2026-10-18T00:00:00Z", now) == 24


def test_the_backfill_recovers_the_gap_since_the_last_goes_observation(make_client, fake_goes, monkeypatch):
    """Con work.db restaurado de un respaldo viejo, el relleno fijo de 6 h no alcanza el hueco.

    Producción quedó 30 h sin barridos nuevos (contenedor caído y work.db restaurado): el relleno
    de 6 h solo miraba las últimas horas, así que las detecciones del 21-oct se perdían. Con las
    claves reales del barrido de las 18:00, el relleno debe medir el hueco y procesarlas.
    """
    now = datetime(2026, 10, 22, 4, 30, tzinfo=timezone.utc)
    clock(monkeypatch, now)
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        seed_goes_observation(svc.db, "2026-10-20T22:00:21Z")
        fake_goes["by_hour"] = {18: REAL_KEYS["2026-10-21T18"]}
        fake_goes["now"] = now
        assert asyncio.run(svc.backfill_goes(hours=6)) == 0, "la ventana fija no llega al 21-oct 18:00"
        assert fake_goes["seen"] == []
        assert asyncio.run(svc.backfill_goes()) == 2, "el relleno derivado sí procesa el barrido"
        assert fake_goes["seen"] == REAL_KEYS["2026-10-21T18"][::3]


def test_a_failed_backfill_hour_does_not_discard_the_others(make_client, fake_goes, monkeypatch):
    now = datetime(2026, 10, 22, 4, 30, tzinfo=timezone.utc)
    clock(monkeypatch, now)
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        seed_goes_observation(svc.db, "2026-10-20T22:00:21Z")
        fake_goes["by_hour"] = {18: REAL_KEYS["2026-10-21T18"]}
        fake_goes["fail_hours"] = {22}
        fake_goes["now"] = now
        assert asyncio.run(svc.backfill_goes()) == 2, "un listado caído no tira el resto del relleno"
        assert fake_goes["seen"] == REAL_KEYS["2026-10-21T18"][::3]
        # La hora caída no queda solo en el log: /api/status debe poder mostrar el hueco.
        failed = svc.db.one("SELECT source_ref, ok, message FROM ingest_runs WHERE ok = 0")
        assert failed["source_ref"] == "listado S3" and "T22Z" in failed["message"]
