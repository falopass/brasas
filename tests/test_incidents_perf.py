"""FIX-15 — equivalencia y presupuesto de rendimiento de `incidents.update`.

- Equivalencia: el `update` con cuadrícula en memoria y caché de miembros produce
  exactamente el mismo estado (incidentes, vínculos, fusiones) que la versión con
  consulta por detección, aquí congelada como `_reference_update`. Los uuid se fijan
  con un contador para que los ids sean comparables entre corridas.
- Presupuesto: ~2 000 detecciones repartidas en ~200 focos en un solo ciclo terminan
  en menos de 5 segundos.
"""
from __future__ import annotations

import itertools
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend import incidents
from backend.db import Database
from backend.geo import haversine_km
from tests.test_incidents_props import batch_sizes, chunks, generate, insert_obs

T0 = datetime(2027, 1, 20, 18, 0, tzinfo=timezone.utc)
NOW = T0 + timedelta(hours=49)


# --- referencia congelada: la regla de agrupación vigente escrita con consulta por
# detección (era «update antes de FIX-15»; en FIX-53/QA-07 la regla cambió —ventana
# temporal por miembro y ficha de incidente al día dentro del ciclo— y la referencia
# se re-congeló sobre la regla nueva para seguir verificando la maquinaria de FIX-15) ---

def _reference_candidates(db: Database, obs: dict, when: datetime) -> list[dict]:
    pad = 0.06
    since = incidents._stamp(when - timedelta(hours=incidents.ACTIVE_HOURS))
    until = incidents._stamp(when + timedelta(hours=incidents.ACTIVE_HOURS))
    return db.query(
        f"SELECT * FROM incidents WHERE status IN ({','.join('?' * len(incidents.OPEN_STATES))}) AND last_seen_at >= ? "
        "AND first_seen_at <= ? "
        "AND min_lat - ? <= ? AND max_lat + ? >= ? AND min_lon - ? <= ? AND max_lon + ? >= ? ORDER BY first_seen_at",
        (*incidents.OPEN_STATES, since, until, pad, obs["lat"], pad, obs["lat"], pad, obs["lon"], pad, obs["lon"]))


def _reference_update(db: Database, observations: list[dict], now: datetime) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    touched: set[str] = set()
    window = timedelta(hours=incidents.ACTIVE_HOURS)
    for obs in sorted(observations, key=lambda o: o["observed_at"]):
        if db.one("SELECT 1 FROM incident_observations WHERE observation_id = ?", (obs["id"],)):
            continue
        when = incidents._t(obs["observed_at"])
        matches = [inc for inc in _reference_candidates(db, obs, when)
                   if any(haversine_km(m["lat"], m["lon"], obs["lat"], obs["lon"])
                          <= incidents.link_km(m.get("resolution_m"), obs.get("resolution_m"))
                          and abs(incidents._t(m["observed_at"]) - when) <= window
                          for m in incidents._members(db, inc["id"]))]
        lat0, lat1 = obs["lat"], obs["lat"]
        lon0, lon1 = obs["lon"], obs["lon"]
        first, last = obs["observed_at"], obs["observed_at"]
        if matches:
            target = matches[0]["id"]
            for other in matches[1:]:
                db.execute("UPDATE incident_observations SET incident_id = ? WHERE incident_id = ?", (target, other["id"]))
                db.execute("INSERT OR REPLACE INTO incident_merges(dead_id, live_id, merged_at) VALUES (?,?,?)",
                           (other["id"], target, incidents._stamp(now)))
                db.execute("DELETE FROM incidents WHERE id = ?", (other["id"],))
                touched.discard(other["id"])
                lat0, lat1 = min(lat0, other["min_lat"]), max(lat1, other["max_lat"])
                lon0, lon1 = min(lon0, other["min_lon"]), max(lon1, other["max_lon"])
                first, last = min(first, other["first_seen_at"]), max(last, other["last_seen_at"])
        else:
            target = uuid.uuid4().hex[:12]
            stamp = obs["observed_at"]
            db.execute("INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, min_lat, max_lat, "
                       "min_lon, max_lon, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (target, "anomalia", incidents._stamp(now), stamp, stamp, obs["lat"], obs["lon"], obs["lat"], obs["lat"],
                        obs["lon"], obs["lon"], incidents._stamp(now)))
        db.execute("INSERT OR IGNORE INTO incident_observations(observation_id, incident_id) VALUES (?, ?)", (obs["id"], target))
        # La ficha del incidente refleja a los miembros ya enlazados dentro de la misma corrida
        # (QA-07/FIX-53): sin esto, qué candidatos ve cada detección depende del orden de llegada.
        db.execute("UPDATE incidents SET min_lat = MIN(min_lat, ?), max_lat = MAX(max_lat, ?), "
                   "min_lon = MIN(min_lon, ?), max_lon = MAX(max_lon, ?), "
                   "first_seen_at = MIN(first_seen_at, ?), last_seen_at = MAX(last_seen_at, ?) WHERE id = ?",
                   (lat0, lat1, lon0, lon1, first, last, target))
        touched.add(target)
    return [incidents._refresh(db, incident_id, now) for incident_id in touched]


def _run(db: Database, rows: list[dict], batches: list[list[dict]], update_fn, now: datetime) -> None:
    """Inserta las detecciones y corre la función de agrupación con uuid deterministas."""
    for row in rows:
        insert_obs(db, row)
    seq = itertools.count()
    with patch("uuid.uuid4", new=lambda: SimpleNamespace(hex=f"{next(seq):012x}{'0' * 20}")):
        for batch in batches:
            update_fn(db, batch, now)


def _state(db: Database) -> tuple:
    return (db.query("SELECT * FROM incidents ORDER BY id"),
            db.query("SELECT * FROM incident_observations ORDER BY observation_id"),
            db.query("SELECT * FROM incident_merges ORDER BY dead_id"))


@pytest.mark.parametrize("seed", (1234, 7, 42, 99))
def test_update_matches_the_previous_query_based_implementation(tmp_path, seed):
    rng = random.Random(seed + 1)
    rows, _ = generate(seed)
    batches = chunks(sorted(rows, key=lambda r: r["observed_at"]), batch_sizes(rng, len(rows)))
    batches.append([rng.choice(rows) for _ in range(len(rows) // 10)])  # el feed repite detecciones
    reference = Database(tmp_path / "ref" / "brasa.db")
    current = Database(tmp_path / "new" / "brasa.db")
    _run(reference, rows, batches, _reference_update, NOW)
    _run(current, rows, batches, incidents.update, NOW)
    assert _state(current) == _state(reference)


def test_update_matches_reference_on_a_merge_chain_with_first_seen_ties(tmp_path):
    """Empates de first_seen_at + puentes que fusionan en cadena: fija el orden de candidatos."""
    rng = random.Random(2023)

    def row(oid, km_south, minutes):
        return {"id": oid, "source": "gen", "sensor": "VIIRS", "satellite": "GEN", "resolution_m": 375,
                "lat": -33.5 - km_south / 111.0, "lon": -70.8,
                "observed_at": (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "frp_mw": 10.0, "confidence": "nominal", "comuna_code": 13101}

    bases = [row(f"i{i}", 4.0 * i, 0) for i in range(6)]          # 6 incidentes, mismo segundo
    bridges = [row(f"b{i}", 4.0 * i - 2.0, 10) for i in range(1, 6)]  # puentes entre vecinos
    rng.shuffle(bases)
    batches = [bases, bridges]
    reference = Database(tmp_path / "ref" / "brasa.db")
    current = Database(tmp_path / "new" / "brasa.db")
    _run(reference, bases + bridges, batches, _reference_update, NOW)
    _run(current, bases + bridges, batches, incidents.update, NOW)
    assert _state(current) == _state(reference)
    assert db_merges(current) == db_merges(reference) > 0  # hubo fusiones y coinciden


def db_merges(db: Database) -> int:
    return db.one("SELECT COUNT(*) AS n FROM incident_merges")["n"]


def test_update_matches_reference_when_detections_arrive_late_out_of_order(tmp_path):
    """Una detección vieja que llega después entra a mitad de la lista de miembros:
    los agregados en memoria deben replicar el orden exacto de _members."""
    def row(oid, minutes):
        return {"id": oid, "source": "gen", "sensor": "VIIRS", "satellite": "GEN", "resolution_m": 375,
                "lat": -33.5 + rng.gauss(0, 0.001), "lon": -70.8 + rng.gauss(0, 0.001),
                "observed_at": (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "frp_mw": 10.0, "confidence": "nominal", "comuna_code": 13101}

    rng = random.Random(31)
    rows = [row("a", 0), row("b", 60), row("c", 30), row("d", 30), row("e", 90)]
    batches = [[rows[0], rows[1]], [rows[2]], [rows[3], rows[4]]]  # c y d llegan tarde, d empata a c
    reference = Database(tmp_path / "ref" / "brasa.db")
    current = Database(tmp_path / "new" / "brasa.db")
    _run(reference, rows, batches, _reference_update, NOW)
    _run(current, rows, batches, incidents.update, NOW)
    assert _state(current) == _state(reference)


def test_update_matches_reference_across_a_prune(tmp_path):
    """La retención borra observaciones y vínculos entre ciclos: el estado persistente
    debe invalidarse (prune) y reconstruirse igual que la versión por consulta."""
    rng = random.Random(8080)
    rows = sorted(generate(8080)[0], key=lambda r: r["observed_at"])
    cutoff = "2027-01-21T00:00:00Z"  # T0 del generador + 24 h
    batches = chunks(rows, batch_sizes(rng, len(rows)))
    half = next(i for i, b in enumerate(batches) if b[0]["observed_at"] >= cutoff)
    reference = Database(tmp_path / "ref" / "brasa.db")
    current = Database(tmp_path / "new" / "brasa.db")
    for db, fn in ((reference, _reference_update), (current, incidents.update)):
        for row in rows:
            insert_obs(db, row)
        seq = itertools.count()
        with patch("uuid.uuid4", new=lambda: SimpleNamespace(hex=f"{next(seq):012x}{'0' * 20}")):
            for batch in batches[:half]:
                fn(db, batch, NOW)
            db.execute("DELETE FROM observations WHERE observed_at < ?", (cutoff,))
            incidents.prune(db, cutoff)
            for batch in batches[half:]:
                fn(db, batch, NOW)
    assert _state(current) == _state(reference)


def test_update_marks_a_fixed_source_like_the_query_based_version(tmp_path):
    """Patrón ≥ 8 días en 30 con reparto de semanas: el índice de días del ciclo debe
    producir el mismo fixed_source y la misma fixed_reason que la consulta por miembro."""
    pattern_days = ["2026-12-25", "2026-12-28", "2027-01-01", "2027-01-05", "2027-01-09",
                    "2027-01-13", "2027-01-17", "2027-01-19"]
    rows = [{"id": f"f{i}", "source": "gen", "sensor": "VIIRS", "satellite": "GEN", "resolution_m": 375,
             "lat": -34.2 + (i % 3) * 0.001, "lon": -70.5 + (i % 2) * 0.001,
             "observed_at": f"{day}T12:00:00Z", "frp_mw": 5.0, "confidence": "alta", "comuna_code": 13101}
            for i, day in enumerate(pattern_days)]
    batches = [rows[:4], rows[4:]]
    reference = Database(tmp_path / "ref" / "brasa.db")
    current = Database(tmp_path / "new" / "brasa.db")
    _run(reference, rows, batches, _reference_update, NOW)
    _run(current, rows, batches, incidents.update, NOW)
    ref, cur = _state(reference), _state(current)
    assert cur == ref
    assert cur[0][0]["fixed_source"] == 1  # el ejercicio realmente cubrió el patrón
    assert cur[0][0]["fixed_reason"]


# --- presupuesto: ~2 000 detecciones, ~200 incidentes, un solo ciclo ---

def test_two_thousand_detections_over_two_hundred_incidents_in_one_cycle(tmp_path):
    rng = random.Random(202302)
    centers: list[tuple[float, float]] = []
    while len(centers) < 200:
        cand = (rng.uniform(-38.0, -33.0), rng.uniform(-73.5, -70.0))
        if all(haversine_km(cand[0], cand[1], c[0], c[1]) >= 15 for c in centers):
            centers.append(cand)  # ≥ 15 km entre focos: no hay cadena posible entre ellos
    db = Database(tmp_path / "brasa.db")
    batch = []
    for i in range(2000):
        lat = centers[i % 200][0] + rng.gauss(0, 0.002)
        lon = centers[i % 200][1] + rng.gauss(0, 0.002)
        at = (T0 + timedelta(minutes=(i // 200) * 10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = {"id": f"p{i}", "source": "gen", "sensor": "ABI", "satellite": "GOES", "resolution_m": 2000,
               "lat": lat, "lon": lon, "observed_at": at, "frp_mw": 8.0, "confidence": "alta", "comuna_code": 13101}
        insert_obs(db, row)
        batch.append(row)
    clock = time.monotonic()
    touched = incidents.update(db, batch, NOW)
    elapsed = time.monotonic() - clock
    assert elapsed < 5.0, f"{elapsed:.1f} s excede el presupuesto de 5 s"
    assert len(touched) == 200
    assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 200
    assert db.one("SELECT COUNT(*) AS n FROM incident_observations")["n"] == 2000
