"""QA-03: números de la validación contra CONAF sobre una base sintética."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # el script importa backend.geo

spec = importlib.util.spec_from_file_location("validar_deteccion", ROOT / "scripts" / "validar_deteccion.py")
validar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validar)

FIRE_COLS = ("id, name, status, status_raw, started_at, area_ha, lat, lon, comuna, region, "
             "detected_at, alerted_at, season, first_fetched_at, fetched_at")
INC_COLS = ("id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
            "min_lat, max_lat, min_lon, max_lon, updated_at")


def make_db(tmp_path: Path) -> Path:
    """Cinco incendios CONAF y cinco incidentes:

    - A: detectado por BRASA 20 min antes de f_deteccion (y 50 antes de f_aviso).
    - B: detectado 120 min después de f_deteccion (60 después de f_aviso).
    - C: sin incidente cercano y con una comuna que no existe («Narnia»).
    - D: sin f_deteccion; se evalúa aparte sobre f_inicio.
    - i5: incidente «posible» sin incendio de CONAF a ≤ 5 km en ±24 h (candidato a falsa alarma).
    """
    from backend.db import Database

    db = Database(tmp_path / "brasa.db")
    fires = [
        ("inc-a", "Foco A", "confirmado", "En combate", "2026-01-10T10:30:00Z", 0.5,
         -34.98, -71.24, "Curicó", "Maule", "2026-01-10T12:00:00Z", "2026-01-10T12:30:00Z"),
        ("inc-b", "Foco B", "controlado", "Controlado", "2026-01-11T11:00:00Z", 50.0,
         -35.00, -71.40, "Hualañé", "Maule", "2026-01-11T12:00:00Z", "2026-01-11T13:00:00Z"),
        ("inc-c", "Foco C", "extinguido", "Extinguido", "2026-01-12T09:00:00Z", 200.0,
         -35.50, -71.00, "Narnia", "Maule", "2026-01-12T12:00:00Z", None),
        ("inc-d", "Foco D", "confirmado", "En combate", "2026-01-13T12:00:00Z", 5.0,
         -35.10, -71.30, "Pencahue", "Maule", None, None),
    ]
    for row in fires:
        db.execute(f"INSERT INTO work.official_fires({FIRE_COLS}) VALUES ({','.join('?' * 15)})",
                   (*row, "2025-2026", "2026-01-15T00:00:00Z", "2026-01-15T00:00:00Z"))
    incidents = [
        ("i1", "confirmado", -34.98, -71.24, "2026-01-10T11:40:00Z"),
        ("i2", "posible", -35.00, -71.40, "2026-01-11T14:00:00Z"),
        ("i4", "anomalia", -35.10, -71.30, "2026-01-13T13:00:00Z"),
        ("i5", "posible", -33.40, -70.60, "2026-01-15T10:00:00Z"),
    ]
    for inc_id, status, lat, lon, first in incidents:
        db.execute(f"INSERT INTO work.incidents({INC_COLS}) VALUES ({','.join('?' * 12)})",
                   (inc_id, status, first, first, first, lat, lon, lat, lat, lon, lon, first))
        db.execute("INSERT INTO work.observations(id, source, lat, lon, observed_at, ingested_at) "
                   "VALUES (?, 'test', ?, ?, ?, ?)", (f"obs-{inc_id}", lat, lon, first, first))
        db.execute("INSERT INTO work.incident_observations(observation_id, incident_id) VALUES (?, ?)",
                   (f"obs-{inc_id}", inc_id))
    return tmp_path / "work.db"


def test_numeros_exactos_de_la_validacion(tmp_path):
    result = validar.validate(make_db(tmp_path))
    assert result["resumen"] == {"n": 3, "detectados": 2, "pct": 67}
    tramos = {t["tramo"]: t for t in result["tramos"]}
    assert tramos["<1 ha"] == {"tramo": "<1 ha", "n": 1, "detectados": 1, "pct": 100}
    assert tramos["10-100 ha"]["n"] == 1 and tramos["10-100 ha"]["detectados"] == 1
    assert tramos[">=100 ha"]["n"] == 1 and tramos[">=100 ha"]["detectados"] == 0
    assert tramos["1-10 ha"]["n"] == 0 and tramos["sin superficie"]["n"] == 0
    # Ventajas contra f_deteccion [-20, +120] y contra f_aviso [-50, +60].
    assert result["ventaja_min"]["vs_deteccion"] == {"n": 2, "p50": 50.0, "p90": 106.0}
    assert result["ventaja_min"]["vs_aviso"] == {"n": 2, "p50": 5.0, "p90": 49.0}
    assert result["sin_hora_conaf"]["n"] == 1 and result["sin_hora_conaf"]["detectados"] == 1
    assert result["incidentes_abiertos"] == 3 and len(result["candidatos_falsa_alarma"]) == 1
    assert result["candidatos_falsa_alarma"][0]["id"] == "i5"
    assert result["sin_comuna_reconocida"] == ["Narnia"]
    assert [f["id"] for f in result["sin_incidente_cercano"]] == ["inc-c"]
    a = next(f for f in result["incendios"] if f["id"] == "inc-a")
    assert a["detected"] and a["ventaja_deteccion_min"] == -20.0 and a["ventaja_aviso_min"] == -50.0
    assert a["comuna_code"] is not None and a["anchor_kind"] == "detected_at"


def test_render_imprime_la_tabla_y_json_escribe(tmp_path, capsys):
    db = make_db(tmp_path)
    out_json = tmp_path / "salida.json"
    assert validar.main(["--db", str(db), "--json", str(out_json)]) == 0
    text = capsys.readouterr().out
    assert "| <1 ha | 1 | 1 | 100% |" in text
    assert "| **Total (con f_deteccion)** | 3 | 2 | 67% |" in text
    assert "| f_deteccion | 2 | 50 | 106 |" in text
    assert "| f_aviso | 2 | 5 | 49 |" in text
    assert "sin incendio de CONAF a ≤ 5 km en ±24 h: 1" in text
    assert "Sin comuna reconocida" in text and "Narnia" in text
    assert "inc-c" in text
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["resumen"]["pct"] == 67 and data["db"] == str(db)


def test_base_sin_incendios_conaf_sale_con_codigo_2(tmp_path):
    from backend.db import Database

    Database(tmp_path / "brasa.db")
    assert validar.main(["--db", str(tmp_path / "work.db")]) == 2
    assert validar.main(["--db", str(tmp_path / "no-existe.db")]) == 2


def test_filtro_por_temporada(tmp_path):
    """Con --season solo entran los incendios de esa temporada; otra da una base vacía."""
    db = make_db(tmp_path)
    result = validar.validate(db, season="2025-2026")
    assert result["resumen"]["n"] == 3 and result["season"] == "2025-2026"
    assert validar.validate(db, season="1900-1901") is None
