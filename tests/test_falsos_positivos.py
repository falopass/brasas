"""DET-08: conteos de «anomalia» por región sobre una base sintética.

En enero Chile está en UTC-3, así que 15:00Z son las 12:00 locales (diurna: 08-19 h) y
04:00Z son la 01:00 local (nocturna).
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # el script importa backend.geo

spec = importlib.util.spec_from_file_location("medir_falsos_positivos", ROOT / "scripts" / "local" / "medir_falsos_positivos.py")
medir = importlib.util.module_from_spec(spec)
spec.loader.exec_module(medir)

INC_COLS = "id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, min_lat, max_lat, min_lon, max_lon, updated_at"


def make_db(tmp_path: Path) -> Path:
    """Ocho detecciones:

    - Antofagasta (2101): o1 y o2 «anomalia» de día, o3 «anomalia» de noche, o4 «confirmado»
      de noche, o8 sin incidente enlazado (de día).
    - Valparaíso (5101): o5 «posible» de día, o6 «anomalia» de noche.
    - Sin comuna (mar): o7 «anomalia» de día.
    """
    from backend.db import Database

    db = Database(tmp_path / "brasa.db")
    obs = [
        ("o1", "ABI", 2101, -23.65, -70.40, "2026-01-10T15:00:00Z"),
        ("o2", "ABI", 2101, -23.65, -70.40, "2026-01-10T18:00:00Z"),
        ("o3", "VIIRS", 2101, -23.65, -70.40, "2026-01-11T04:00:00Z"),
        ("o4", "VIIRS", 2101, -23.65, -70.40, "2026-01-11T04:30:00Z"),
        ("o5", "ABI", 5101, -33.04, -71.63, "2026-01-12T13:00:00Z"),
        ("o6", "VIIRS", 5101, -33.04, -71.63, "2026-01-12T05:00:00Z"),
        ("o7", "ABI", None, -30.00, -75.00, "2026-01-12T16:00:00Z"),
        ("o8", "VIIRS", 2101, -23.65, -70.40, "2026-01-12T16:00:00Z"),
    ]
    for oid, sensor, code, lat, lon, stamp in obs:
        db.execute(
            "INSERT INTO work.observations(id, source, sensor, lat, lon, observed_at, "
            "comuna_code, ingested_at) VALUES (?, 'test', ?, ?, ?, ?, ?, ?)",
            (oid, sensor, lat, lon, stamp, code, stamp),
        )
    incidents = [
        ("i1", "anomalia"),
        ("i2", "anomalia"),
        ("i3", "anomalia"),
        ("i4", "confirmado"),
        ("i5", "posible"),
        ("i6", "anomalia"),
        ("i7", "anomalia"),
    ]
    for iid, status in incidents:
        db.execute(
            f"INSERT INTO work.incidents({INC_COLS}) VALUES ({','.join('?' * 12)})",
            (
                iid,
                status,
                "2026-01-10T00:00:00Z",
                "2026-01-10T00:00:00Z",
                "2026-01-12T00:00:00Z",
                -23.0,
                -70.0,
                -23.0,
                -23.0,
                -70.0,
                -70.0,
                "2026-01-12T00:00:00Z",
            ),
        )
    for oid, iid in (("o1", "i1"), ("o2", "i2"), ("o3", "i3"), ("o4", "i4"), ("o5", "i5"), ("o6", "i6"), ("o7", "i7")):
        db.execute("INSERT INTO work.incident_observations(observation_id, incident_id) VALUES (?, ?)", (oid, iid))
    return tmp_path / "work.db"


def make_db_territorio(tmp_path: Path) -> Path:
    """Tres detecciones: una con comuna, una chilena sin comuna (Talca) y una en Argentina."""
    from backend.db import Database

    db = Database(tmp_path / "brasa.db")
    obs = [
        ("t1", "ABI", 2101, -23.65, -70.40, "2026-01-10T15:00:00Z"),
        ("t2", "VIIRS", None, -35.40, -71.60, "2026-01-10T16:00:00Z"),  # Talca: chilena sin comuna
        ("t3", "MODIS", None, -38.40, -63.00, "2026-01-10T17:00:00Z"),  # Argentina
    ]
    for oid, sensor, code, lat, lon, stamp in obs:
        db.execute(
            "INSERT INTO work.observations(id, source, sensor, lat, lon, observed_at, "
            "comuna_code, ingested_at) VALUES (?, 'test', ?, ?, ?, ?, ?, ?)",
            (oid, sensor, lat, lon, stamp, code, stamp),
        )
    for iid in ("j1", "j2"):
        db.execute(
            f"INSERT INTO work.incidents({INC_COLS}) VALUES ({','.join('?' * 12)})",
            (
                iid,
                "anomalia",
                "2026-01-10T00:00:00Z",
                "2026-01-10T00:00:00Z",
                "2026-01-10T00:00:00Z",
                -23.0,
                -70.0,
                -23.0,
                -23.0,
                -70.0,
                -70.0,
                "2026-01-10T00:00:00Z",
            ),
        )
    for oid, iid in (("t1", "j1"), ("t2", "j2")):  # t3 queda sin incidente enlazado
        db.execute("INSERT INTO work.incident_observations(observation_id, incident_id) VALUES (?, ?)", (oid, iid))
    return tmp_path / "work.db"


def by_region(result: dict) -> dict:
    return {r["region"]: r for r in result["regiones"]}


def test_conteos_y_porcentajes_exactos(tmp_path):
    result = medir.measure(make_db(tmp_path))
    assert result["total"] == 8
    regiones = by_region(result)
    assert list(regiones) == ["Antofagasta", "Valparaíso", "(sin comuna)"]  # norte a sur
    ant = regiones["Antofagasta"]
    assert (ant["n"], ant["pct_diurnas"], ant["anomalia"], ant["pct_anomalia"]) == (5, 60.0, 3, 60.0)
    assert (ant["pct_anomalia_dia"], ant["pct_anomalia_noche"]) == (66.7, 50.0)
    assert ant["sin_incidente"] == 1
    val = regiones["Valparaíso"]
    assert (val["n"], val["pct_diurnas"], val["pct_anomalia"]) == (2, 50.0, 50.0)
    assert (val["pct_anomalia_dia"], val["pct_anomalia_noche"]) == (0.0, 100.0)
    assert (regiones["(sin comuna)"]["n"], regiones["(sin comuna)"]["pct_anomalia"]) == (1, 100.0)
    total = result["totales"]
    assert (total["n"], total["pct_diurnas"], total["anomalia"], total["pct_anomalia"]) == (8, 62.5, 5, 62.5)
    assert [(c["comuna"], c["anomalia"], c["n"]) for c in result["comunas_top"]] == [
        ("Antofagasta", 3, 5),
        ("Valparaíso", 1, 2),
        ("(sin comuna)", 1, 1),
    ]


def test_filtros_de_fecha_y_sensor(tmp_path):
    db = make_db(tmp_path)
    assert medir.measure(db, desde="2026-01-11")["total"] == 6
    assert medir.measure(db, hasta="2026-01-11")["total"] == 4  # la fecha sola incluye el día
    assert medir.measure(db, desde="2026-01-11", hasta="2026-01-11")["total"] == 2
    assert medir.measure(db, desde="2026-01-10T14:00:00Z", hasta="2026-01-10T16:00:00Z")["total"] == 1  # instantes: inclusivos
    solo_viirs = medir.measure(db, sensor="VIIRS")
    assert solo_viirs["total"] == 4
    assert by_region(solo_viirs)["Antofagasta"]["n"] == 3


def test_sin_comuna_separa_chile_y_extranjero(tmp_path):
    """Un punto chileno sin comuna y uno en Argentina no comparten la misma cubeta."""
    result = medir.measure(make_db_territorio(tmp_path))
    total = result["totales"]
    assert (total["sin_comuna"], total["sin_comuna_en_chile"], total["fuera_de_chile"]) == (2, 1, 1)
    assert (total["pct_sin_comuna"], total["pct_sin_comuna_en_chile"], total["pct_fuera_de_chile"]) == (66.7, 33.3, 33.3)
    sin = by_region(result)["(sin comuna)"]
    assert (sin["n"], sin["sin_comuna"], sin["sin_comuna_en_chile"], sin["fuera_de_chile"]) == (2, 2, 1, 1)
    assert [(s["sensor"], s["n"], s["anomalia"], s["pct_anomalia"]) for s in result["sensores"]] == [
        ("ABI", 1, 1, 100.0),
        ("VIIRS", 1, 1, 100.0),
        ("Otros", 1, 0, 0.0),
    ]


def test_base_vacia_da_mensaje_y_cero(tmp_path, capsys):
    from backend.db import Database

    Database(tmp_path / "brasa.db")
    assert medir.main(["--db", str(tmp_path / "work.db")]) == 0
    assert "No hay detecciones" in capsys.readouterr().err


def test_render_imprime_las_tablas(tmp_path, capsys):
    assert medir.main(["--db", str(make_db(tmp_path / "base"))]) == 0
    text = capsys.readouterr().out
    assert "| Antofagasta | 5 | 60.0% | 3 | 60.0% | 66.7% | 50.0% |" in text
    assert "sin incidente enlazado: 1" in text
    assert "NO equivale a falso positivo" in text
    assert medir.main(["--db", str(make_db_territorio(tmp_path / "territorio"))]) == 0
    text = capsys.readouterr().out
    assert "2 (100.0%) | 1 (50.0%) | 1 (50.0%) |" in text  # fila «(sin comuna)»
    assert "| Sensor | Detecciones | «anomalia» | % «anomalia» |" in text
