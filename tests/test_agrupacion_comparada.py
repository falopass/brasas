"""DET-09 — la comparación de agrupación no cambia la regla vigente ni toca la base real.

- `incidents.update` sin `linker` sigue usando el enlace simple (`LINKER`) y produce el
  mismo estado que la implementación por consulta congelada en FIX-15.
- Con un conjunto sintético, ambas estrategias —enlace simple y DBSCAN espacio-tiempo—
  dejan cada detección en exactamente un incidente.
- `scripts/comparar_agrupacion.py` corre sobre bases desechables: nunca `data/brasa.db`.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from backend import incidents
from backend.db import Database
from backend.settings import ROOT
from scripts.comparar_agrupacion import compare, dbscan_linker
from tests.test_incidents_perf import NOW, _reference_update, _run, _state
from tests.test_incidents_props import batch_sizes, chunks, generate, insert_obs

T0 = datetime(2030, 2, 3, 12, 0, tzinfo=timezone.utc)
AT0 = T0.strftime("%Y-%m-%dT%H:%M:%SZ")
KM_LAT = 1 / 111.0


def feed(db: Database, rows: list[dict], linker=None) -> None:
    for row in rows:
        insert_obs(db, row)
    for batch in chunks(sorted(rows, key=lambda r: r["observed_at"]),
                        batch_sizes(random.Random(5), len(rows))):
        incidents.update(db, batch, NOW, linker=linker)


def partition(db: Database) -> set[frozenset]:
    groups: dict[str, set] = {}
    for r in db.query("SELECT observation_id, incident_id FROM incident_observations"):
        groups.setdefault(r["incident_id"], set()).add(r["observation_id"])
    return {frozenset(g) for g in groups.values()}


# --- la regla por defecto no cambia ---

def test_update_sin_linker_sigue_siendo_el_enlace_simple_de_siempre(tmp_path):
    """`update` sin `linker` usa `LINKER` (enlace simple) y da el mismo estado que la
    implementación por consulta congelada en test_incidents_perf."""
    assert incidents.LINKER is incidents.single_link
    rng = random.Random(11)
    rows, _ = generate(2024)
    batches = chunks(sorted(rows, key=lambda r: r["observed_at"]), batch_sizes(rng, len(rows)))
    ref = Database(tmp_path / "ref" / "brasa.db")
    _run(ref, rows, batches, _reference_update, NOW)
    for name, fn in (("defecto", incidents.update),
                     ("explicito", partial(incidents.update, linker=incidents.single_link))):
        cur = Database(tmp_path / name / "brasa.db")
        _run(cur, rows, batches, fn, NOW)
        assert _state(cur) == _state(ref)


def test_el_linker_global_es_el_que_usa_update_por_defecto(tmp_path, monkeypatch):
    """El script intercambia `incidents.LINKER`: sin `linker`, `update` usa el global vigente."""
    rows, _ = generate(321)
    via_param = Database(tmp_path / "param" / "brasa.db")
    feed(via_param, rows, dbscan_linker)
    monkeypatch.setattr(incidents, "LINKER", dbscan_linker)
    via_global = Database(tmp_path / "global" / "brasa.db")
    feed(via_global, rows)  # sin linker: debe tomar LINKER, aquí DBSCAN
    assert partition(via_global) == partition(via_param)


# --- ambas estrategias asignan cada detección a exactamente un incidente ---

def test_ambas_estrategias_dejan_cada_deteccion_en_un_solo_incidente(tmp_path):
    rows, _ = generate(5150)
    for name, linker in (("enlace", incidents.single_link), ("dbscan", dbscan_linker)):
        db = Database(tmp_path / name / "brasa.db")
        feed(db, rows, linker)
        links = db.query("SELECT observation_id, incident_id FROM incident_observations")
        assert len(links) == len({l["observation_id"] for l in links}) == len(rows)
        live = {r["id"] for r in db.query("SELECT id FROM incidents")}
        assert {l["incident_id"] for l in links} <= live


# --- la estrategia DBSCAN difiere donde debe: no encadena puentes aislados ---

def test_dbscan_no_une_un_puente_aislado_y_si_un_grupo_denso():
    """A nivel de linker: un miembro solo no es núcleo (no hay toque); la detección que
    completa MIN_SAMPLES vecinos a eps sí lo es (toca al incidente)."""
    solo = [("i1", [(-33.5, -70.8, 2000, AT0)])]
    assert dbscan_linker(solo, -33.51, -70.8, 2000, AT0) == set()
    denso = [("i1", [(-33.5, -70.8, 2000, AT0), (-33.51, -70.8, 2000, AT0)])]
    assert dbscan_linker(denso, -33.505, -70.8, 2000, AT0) == {"i1"}


def test_dbscan_fragmenta_una_cadena_de_detecciones_aisladas(tmp_path):
    """a—b—c a 3 km en línea: el enlace simple las encadena en un incidente; DBSCAN parte
    la cadena porque ningún punto ve MIN_SAMPLES vecinos hasta que llega la tercera."""
    def cuenta(linker) -> int:
        db = Database(tmp_path / f"n{linker.__name__}" / "brasa.db")
        for i, km in enumerate((0.0, 3.0, 6.0)):
            row = {"id": f"p{i}", "source": "gen", "sensor": "ABI", "satellite": "GOES",
                   "resolution_m": 2000, "lat": -33.5 - km * KM_LAT, "lon": -70.8,
                   "observed_at": (T0 + timedelta(minutes=10 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "frp_mw": 10.0, "confidence": "alta", "comuna_code": 13101}
            insert_obs(db, row)
            incidents.update(db, [row], T0 + timedelta(minutes=10 * i), linker=linker)
        return db.one("SELECT COUNT(*) AS n FROM incidents")["n"]

    assert cuenta(incidents.single_link) == 1
    assert cuenta(dbscan_linker) == 2


# --- el script corre sobre bases desechables, nunca data/brasa.db ---

def _mini_case(path: Path) -> Path:
    minutes = (0, 10, 20, 30)
    rows = [
        [0, -38.352, -72.737, 30.0, 320.0, 2],
        [10, -38.353, -72.738, 34.0, 322.0, 2],
        [20, -38.352, -72.736, 28.0, 318.0, 1],
        [20, -38.355, -72.740, 25.0, 315.0, 2],
        [30, -38.354, -72.739, 31.0, 321.0, 2],
        [0, -36.900, -73.100, 22.0, 310.0, 1],  # otro foco lejano
        [20, -36.902, -73.101, 24.0, 312.0, 2],
    ]
    case = {"case_id": "sintetico-det09", "source": "NOAA GOES-16 ABI L2 FDCF",
            "start_utc": AT0, "fields": ["minute", "lat", "lon", "frp_mw", "brightness_k", "confidence"],
            "scans": [{"t": (T0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ"), "n": i}
                      for i, m in enumerate(minutes)],
            "rows": rows}
    path.write_text(json.dumps(case), encoding="utf-8")
    return path


def test_el_banco_corre_en_bases_desechables_sin_tocar_brasa_db(tmp_path):
    goes = _mini_case(tmp_path / "sintetico.goes.json")
    data = ROOT / "data"
    antes = {p.name: p.stat().st_mtime_ns for p in data.glob("brasa.db*")} if data.exists() else {}
    antes.update({p.name: p.stat().st_mtime_ns for p in data.glob("work.db*")} if data.exists() else {})
    out = compare(goes, tmp_path, limit=None)
    despues = {p.name: p.stat().st_mtime_ns for p in data.glob("brasa.db*")} if data.exists() else {}
    despues.update({p.name: p.stat().st_mtime_ns for p in data.glob("work.db*")} if data.exists() else {})
    assert antes == despues
    assert set(out) == {"enlace simple", "dbscan espacio-tiempo"}
    for entry in out.values():
        assert entry["summary"]["asignadas"] == 7
