"""QA-07 — pruebas de propiedades de la agrupación de incidentes (sin dependencias nuevas).

`incidents.update` se ataca con detecciones generadas por `random.Random` (semillas fijas):
2-3 focos que derivan en 48 h, sensores/resoluciones/confianzas mezclados, empates de
minuto a propósito, duplicados en el feed y lotes en desorden. Sobre el resultado se
verifican los invariantes del ítem del backlog:

1. cada detección queda en exactamente un incidente;
2. la caja del incidente contiene a todos sus miembros y los campos derivados calzan;
3. al fusionar sobrevive el incidente más antiguo y el id borrado queda como alias;
4. el orden de llegada no cambia la partición final de detecciones (FIX-53: el vínculo es
   por par de detecciones —distancia y ventana ACTIVE_HOURS por miembro—, así que la
   partición es el cierre transitivo de un grafo que no depende del orden);
5. detecciones de focos distintos (sin cadena posible) nunca comparten incidente.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import incidents
from backend.db import Database
from backend.geo import haversine_km

T0 = datetime(2027, 1, 20, 0, 0, tzinfo=timezone.utc)
HORIZON_MIN = 48 * 60
NOW = T0 + timedelta(hours=49)
SEEDS = (1234, 7, 42, 99, 2026, 555, 8080, 31415)
SENSORS = (("VIIRS", 375), ("MODIS", 1000), ("ABI", 2000))
CONFIDENCES = ("alta", "nominal", "media", "baja")
KM_LAT = 1 / 111.0  # grados de latitud por km


def generate(seed: int) -> tuple[list[dict], list[int]]:
    """N detecciones (50-200) en 2-3 focos a ≥ 120 km entre sí, repartidas en 48 h.

    Cada foco deriva unos kilómetros durante el horizonte (el fuego se mueve, así se
    forman cadenas), con jitter de ~1 km. Devuelve las filas y el foco de cada una.
    """
    rng = random.Random(seed)
    n_focos = rng.randint(2, 3)
    focos: list[tuple[float, float]] = []
    while len(focos) < n_focos:
        cand = (rng.uniform(-38.0, -33.0), rng.uniform(-73.5, -70.0))
        if all(haversine_km(cand[0], cand[1], f[0], f[1]) > 120 for f in focos):
            focos.append(cand)
    drift = [(rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05)) for _ in focos]
    rows, foco = [], []
    for i in range(rng.randint(50, 200)):
        f = rng.randrange(n_focos)
        minutes = rng.uniform(0, HORIZON_MIN)
        if rng.random() < 0.3:
            minutes = round(minutes / 10) * 10  # GOES barre cada 10 min: empates a propósito
        sensor, resolution = rng.choice(SENSORS)
        rows.append({
            "id": f"{seed}-{i}", "source": "gen", "sensor": sensor, "satellite": "GEN",
            "resolution_m": resolution,
            "lat": focos[f][0] + drift[f][0] * (minutes / HORIZON_MIN) + rng.gauss(0, 0.008),
            "lon": focos[f][1] + drift[f][1] * (minutes / HORIZON_MIN) + rng.gauss(0, 0.008),
            "observed_at": (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "frp_mw": rng.choice([None, round(rng.uniform(1, 80), 1)]),
            "confidence": rng.choice(CONFIDENCES), "comuna_code": 13101,
        })
        foco.append(f)
    return rows, foco


def insert_obs(db: Database, row: dict) -> dict:
    db.execute("INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
               "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
               (row["id"], row["source"], row["sensor"], row["satellite"], row["resolution_m"], row["lat"],
                row["lon"], row["observed_at"], row["frp_mw"], row["confidence"], row["comuna_code"],
                row["observed_at"]))
    return row


def spy_on_merges(db: Database) -> list[dict]:
    """Envuelve `db.execute` y registra cada fusión con el first_seen_at de ambos en ese instante.

    El INSERT a incident_merges corre antes del DELETE del incidente absorbido, así que
    todavía se puede leer su fila y comprobar que el sobreviviente era el más antiguo.
    """
    real_execute = db.execute
    seen: list[dict] = []

    def wrapped(sql, params=()):
        if "incident_merges" in sql:
            dead_id, live_id = params[0], params[1]
            seen.append({"dead_id": dead_id, "live_id": live_id,
                         "dead_first": db.one("SELECT first_seen_at AS f FROM incidents WHERE id = ?", (dead_id,))["f"],
                         "live_first": db.one("SELECT first_seen_at AS f FROM incidents WHERE id = ?", (live_id,))["f"]})
        return real_execute(sql, params)

    db.execute = wrapped
    return seen


def batch_sizes(rng: random.Random, total: int, lo: int = 15, hi: int = 40) -> list[int]:
    sizes, left = [], total
    while left:
        sizes.append(min(left, rng.randint(lo, hi)))
        left -= sizes[-1]
    return sizes


def chunks(rows: list[dict], sizes: list[int]) -> list[list[dict]]:
    out, i = [], 0
    for size in sizes:
        out.append(rows[i:i + size])
        i += size
    return out


def run_scenario(path: Path, rows: list[dict], batches: list[list[dict]]) -> tuple[Database, list[dict]]:
    """Inserta las detecciones, corre `incidents.update` por lotes y devuelve la base y las fusiones."""
    db = Database(path / "brasa.db")
    for row in rows:
        insert_obs(db, row)
    merges = spy_on_merges(db)
    for batch in batches:
        incidents.update(db, batch, NOW)
    return db, merges


def memberships(db: Database) -> dict[str, str]:
    return {r["observation_id"]: r["incident_id"] for r in db.query("SELECT * FROM incident_observations")}


def partition(db: Database) -> set[frozenset]:
    """Los incidentes como conjuntos de ids de detección: comparable sin importar los uuids."""
    groups: dict[str, set] = {}
    for oid, iid in memberships(db).items():
        groups.setdefault(iid, set()).add(oid)
    return {frozenset(g) for g in groups.values()}


def obs(db: Database, oid: str, lat: float, lon: float, minutes: float = 0) -> dict:
    return insert_obs(db, {"id": oid, "source": "gen", "sensor": "VIIRS", "satellite": "GEN",
                           "resolution_m": 375, "lat": lat, "lon": lon,
                           "observed_at": (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "frp_mw": 10.0, "confidence": "nominal", "comuna_code": 13101})


# --- Invariante 1: cada detección queda en exactamente un incidente ---

@pytest.mark.parametrize("seed", SEEDS)
def test_every_detection_ends_in_exactly_one_incident(tmp_path, seed):
    rng = random.Random(seed + 1)
    rows, _ = generate(seed)
    batches = chunks(sorted(rows, key=lambda r: r["observed_at"]), batch_sizes(rng, len(rows)))
    batches.append([rng.choice(rows) for _ in range(len(rows) // 10)])  # el feed repite detecciones ya vistas
    db, _ = run_scenario(tmp_path / "db", rows, batches)
    links = memberships(db)
    assert set(links) == {r["id"] for r in rows}  # observation_id es PK: una fila por detección
    live = {r["id"] for r in db.query("SELECT id FROM incidents")}
    assert set(links.values()) <= live  # ninguna membresía queda apuntando a un incidente borrado


# --- Invariante 2: la caja contiene a los miembros y los campos derivados calzan ---

@pytest.mark.parametrize("seed", SEEDS)
def test_the_bbox_covers_every_member_and_derived_fields_match(tmp_path, seed):
    rng = random.Random(seed + 1)
    rows, _ = generate(seed)
    batches = chunks(sorted(rows, key=lambda r: r["observed_at"]), batch_sizes(rng, len(rows)))
    db, _ = run_scenario(tmp_path / "db", rows, batches)
    for inc in db.query("SELECT * FROM incidents"):
        members = incidents.members(db, inc["id"])
        assert inc["n_obs"] == len(members) > 0
        lats = [m["lat"] for m in members]
        lons = [m["lon"] for m in members]
        times = [m["observed_at"] for m in members]
        assert (inc["min_lat"], inc["max_lat"]) == (min(lats), max(lats))
        assert (inc["min_lon"], inc["max_lon"]) == (min(lons), max(lons))
        assert inc["lat"] == pytest.approx(sum(lats) / len(lats))
        assert inc["lon"] == pytest.approx(sum(lons) / len(lons))
        assert inc["first_seen_at"] == min(times) and inc["last_seen_at"] == max(times)
        assert inc["n_reliable"] == sum(1 for m in members if (m["confidence"] or "") in incidents.RELIABLE)


# --- Invariante 3: la fusión conserva al más antiguo y deja alias que resuelven ---

@pytest.mark.parametrize("seed", SEEDS)
def test_merges_keep_the_oldest_incident_and_leave_working_aliases(tmp_path, seed):
    rng = random.Random(seed + 1)
    rows, _ = generate(seed)
    batches = chunks(sorted(rows, key=lambda r: r["observed_at"]), batch_sizes(rng, len(rows)))
    db, merges = run_scenario(tmp_path / "db", rows, batches)
    live = {r["id"] for r in db.query("SELECT id FROM incidents")}
    for m in merges:
        assert m["live_first"] <= m["dead_first"], "el sobreviviente debe ser el más antiguo"
        assert m["dead_id"] not in live
    for alias in db.query("SELECT dead_id FROM incident_merges"):
        resolved = incidents.resolve_merge(db, alias["dead_id"])
        assert resolved is not None and resolved["id"] in live  # la cadena termina en un incidente vivo


def test_a_merge_chain_resolves_each_dead_id_to_the_oldest_survivor(tmp_path):
    """X(-30 min) absorbe a A, que ya había absorbido a B: cadena B→A→X en incident_merges."""
    db = Database(tmp_path / "db" / "brasa.db")
    x = obs(db, "x", -33.5 - 3 * KM_LAT, -70.8, minutes=-30)
    a = obs(db, "a", -33.5, -70.8)
    b = obs(db, "b", -33.5 + 4 * KM_LAT, -70.8, minutes=10)
    incidents.update(db, [x, a, b], T0)  # a 3-4 km entre sí: tres incidentes separados
    incidents.update(db, [obs(db, "p1", -33.5 + 2 * KM_LAT, -70.8, minutes=20)], T0 + timedelta(minutes=25))
    incidents.update(db, [obs(db, "p2", -33.5 - 1.5 * KM_LAT, -70.8, minutes=30)], T0 + timedelta(minutes=35))
    merges = {r["dead_id"]: r["live_id"] for r in db.query("SELECT dead_id, live_id FROM incident_merges")}
    survivor = db.one("SELECT i.id FROM incidents i JOIN incident_observations io ON io.incident_id = i.id "
                      "WHERE io.observation_id = 'x'")["id"]
    assert len(merges) == 2 and db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 1
    for dead in merges:
        assert incidents.resolve_merge(db, dead)["id"] == survivor


def test_a_tie_in_first_seen_still_merges_into_a_single_incident(tmp_path):
    """Dos incidentes con el mismo first_seen_at: el empate se resuelve, sobrevive uno solo."""
    db = Database(tmp_path / "db" / "brasa.db")
    incidents.update(db, [obs(db, "a", -33.5, -70.8), obs(db, "b", -33.5 + 4 * KM_LAT, -70.8)], T0)
    incidents.update(db, [obs(db, "m", -33.5 + 2 * KM_LAT, -70.8, minutes=10)], T0 + timedelta(minutes=15))
    assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 1
    [dead] = db.query("SELECT dead_id FROM incident_merges")
    assert incidents.resolve_merge(db, dead["dead_id"])["n_obs"] == 3


# --- Invariante 4: el orden de llegada no cambia la partición final ---
#
# Hallazgo QA-07, corregido en FIX-53: `update` es incremental y causal —una detección vieja
# que llegaba tarde encontraba «activos» a incidentes cuyo last_seen_at era posterior a su
# observed_at y actuaba de puente que los fusionaba. En estas 8 semillas el desorden engrosaba
# la partición (12→3, 5→3, 11→2, 11→3, 4→2, 7→2, 13→10, 18→4 incidentes). La corrección no fue
# reclustering sino volver el vínculo una propiedad del par: ventana ACTIVE_HOURS por miembro
# (no por incidente) y rango del incidente contiguo a la ventana de la detección. Con eso la
# partición es el cierre transitivo de aristas que no dependen del orden de procesamiento.


@pytest.mark.parametrize("seed", SEEDS)
def test_arrival_order_does_not_change_the_final_partition(tmp_path, seed):
    rng = random.Random(seed + 1)
    rows, _ = generate(seed)
    sizes = batch_sizes(rng, len(rows))
    ordered = chunks(sorted(rows, key=lambda r: r["observed_at"]), sizes)
    db_ordered, _ = run_scenario(tmp_path / "ordered", rows, ordered)
    shuffled = rows[:]
    rng.shuffle(shuffled)
    db_shuffled, _ = run_scenario(tmp_path / "shuffled", rows, chunks(shuffled, sizes))
    assert partition(db_ordered) == partition(db_shuffled)


def test_a_single_update_call_is_input_order_independent(tmp_path):
    """La parte del invariante 4 que sí vale: `update` ordena por observed_at, así que una
    lista desordenada en una sola corrida produce la misma partición que la ordenada."""
    rng = random.Random(SEEDS[0] + 1)
    rows, _ = generate(SEEDS[0])
    db_ordered, _ = run_scenario(tmp_path / "ordered", rows, [sorted(rows, key=lambda r: r["observed_at"])])
    shuffled = rows[:]
    rng.shuffle(shuffled)
    db_shuffled, _ = run_scenario(tmp_path / "shuffled", rows, [shuffled])
    assert partition(db_ordered) == partition(db_shuffled)


def test_a_late_detection_can_join_an_incident_time_order_kept_apart(tmp_path):
    """a(t=0) y c(t=7h) en el mismo punto: en orden son dos incidentes (a las 7 h el de `a`
    ya no estaba activo); si `c` llega primero y `a` después, `a` se une al incidente vivo."""
    ordered = Database(tmp_path / "ordered" / "brasa.db")
    a1 = obs(ordered, "a", -33.5, -70.8)
    c1 = obs(ordered, "c", -33.5, -70.8, minutes=7 * 60)
    incidents.update(ordered, [a1], T0)
    incidents.update(ordered, [c1], T0 + timedelta(hours=7))
    shuffled = Database(tmp_path / "shuffled" / "brasa.db")
    a2 = obs(shuffled, "a", -33.5, -70.8)
    c2 = obs(shuffled, "c", -33.5, -70.8, minutes=7 * 60)
    incidents.update(shuffled, [c2], T0 + timedelta(hours=7))
    incidents.update(shuffled, [a2], T0 + timedelta(hours=8))
    assert partition(ordered) == partition(shuffled)


# --- Invariante 5: focos separados y sin cadena nunca comparten incidente ---

@pytest.mark.parametrize("seed", SEEDS)
def test_separate_focus_never_mix_and_every_incident_stays_connected(tmp_path, seed):
    rng = random.Random(seed + 1)
    rows, foco = generate(seed)
    foco_de = {r["id"]: f for r, f in zip(rows, foco)}
    batches = chunks(sorted(rows, key=lambda r: r["observed_at"]), batch_sizes(rng, len(rows)))
    db, _ = run_scenario(tmp_path / "db", rows, batches)
    for inc in db.query("SELECT * FROM incidents"):
        members = incidents.members(db, inc["id"])
        assert len({foco_de[m["id"]] for m in members}) == 1  # focos a ≥ 120 km no se mezclan
        # cada miembro alcanza al resto por una cadena de saltos de ≤ link_km
        cluster, pending = members[:1], members[1:]
        while pending:
            nxt = next((m for m in pending if any(
                haversine_km(m["lat"], m["lon"], c["lat"], c["lon"])
                <= incidents.link_km(m.get("resolution_m"), c.get("resolution_m")) for c in cluster)), None)
            assert nxt is not None, f"{inc['id']}: miembro sin cadena de ≤ link_km hacia el resto"
            cluster.append(nxt)
            pending.remove(nxt)


def test_two_detections_far_and_apart_in_time_get_separate_incidents(tmp_path):
    """Caso dirigido del invariante 5: mismo punto no alcanza si hay > 6 h de por medio."""
    db = Database(tmp_path / "db" / "brasa.db")
    a = obs(db, "a", -33.5, -70.8)
    b = obs(db, "b", -33.5, -70.8, minutes=7 * 60)
    c = obs(db, "c", -33.5 - 30 * KM_LAT, -70.8, minutes=30)  # lejos y dentro de la ventana de a
    incidents.update(db, [a, b, c], NOW)
    ids = {incidents.incident_of(db, oid)["id"] for oid in ("a", "b", "c")}
    assert len(ids) == 3
