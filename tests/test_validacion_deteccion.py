"""QA-03: la validación contra CONAF sobre una base temporal creada en la prueba."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "validar_deteccion", Path(__file__).resolve().parents[1] / "scripts" / "validar_deteccion.py")
validar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validar)

DET = "2026-01-10T15:00:00Z"  # hora de detección de CONAF en el escenario


def _fire(db, fid, detected, area, season="2025-2026", lat=-33.0, lon=-71.0):
    db.execute("INSERT INTO official_fires(id, name, status, status_raw, started_at, area_ha, lat, lon, "
               "detected_at, season, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (fid, fid, "confirmado", "En combate", DET, area, lat, lon, detected, season, DET, DET))


def _obs(db, oid, observed_at, lat=-33.0, lon=-71.0):
    db.execute("INSERT INTO observations(id, source, lat, lon, observed_at, ingested_at) VALUES (?,?,?,?,?,?)",
               (oid, "GOES19_FDCF", lat, lon, observed_at, observed_at))


def _incident(db, iid, status="posible", lat=-33.0, lon=-71.0):
    db.execute("INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
               "min_lat, max_lat, min_lon, max_lon, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (iid, status, DET, DET, DET, lat, lon, lat - 0.01, lat + 0.01, lon - 0.01, lon + 0.01, DET))


def make_db(tmp_path: Path) -> Path:
    """Escenario: A detectado 30 min antes, B sin observación en ventana/radio, C detectado 2 h después,
    D sin hora de detección (se excluye) y E de otra temporada. Un incidente «posible» lejos de todo
    incendio oficial y otro junto a A."""
    from backend.db import Database

    db = Database(tmp_path / "brasa.db", tmp_path / "work.db")
    _fire(db, "inc-a", DET, 5.0)                                 # 1-10 ha, detectado (-30 min)
    _fire(db, "inc-b", DET, 0.5, lat=-35.0, lon=-72.0)           # <1 ha, no detectado
    _fire(db, "inc-c", DET, 200.0, lat=-36.0, lon=-72.5)         # >100 ha, detectado (+120 min)
    _fire(db, "inc-d", None, 50.0)                               # sin f_deteccion: no entra en la cuenta
    _fire(db, "inc-e", DET, 8.0, season="2024-2025")             # otra temporada
    _obs(db, "obs-a", "2026-01-10T14:30:00Z")                    # 30 min antes de A
    _obs(db, "obs-c", "2026-01-10T17:00:00Z", lat=-36.0, lon=-72.5)  # 2 h después (dentro de la ventana)
    _obs(db, "obs-lejos-b", "2026-01-10T16:00:00Z", lat=-35.5, lon=-72.0)  # ~55 km de B: fuera del radio
    _obs(db, "obs-tarde-b", "2026-01-11T02:00:00Z", lat=-35.0, lon=-72.0)  # a 0 km pero +11 h: fuera de ventana
    _incident(db, "cercano", "posible")                          # junto al incendio A: no sobra
    _incident(db, "lejano", "posible", lat=-40.0)                # sin CONAF cerca: candidato
    _incident(db, "confirmado", "confirmado", lat=-40.0)         # estado cerrado: no es abierto
    db.close_all()
    return tmp_path / "brasa.db"


def test_deteccion_si_y_no_por_tramo(tmp_path):
    result = validar.validate(make_db(tmp_path), season="2025-2026")
    tramos = {t["tramo"]: t for t in result["tramos"]}
    assert tramos["1-10 ha"]["n"] == 1 and tramos["1-10 ha"]["detectados"] == 1
    assert tramos["<1 ha"]["n"] == 1 and tramos["<1 ha"]["detectados"] == 0
    assert tramos[">100 ha"]["n"] == 1 and tramos[">100 ha"]["detectados"] == 1
    assert tramos["sin superficie"]["n"] == 0
    assert result["resumen"]["n"] == 3 and result["resumen"]["detectados"] == 2


def test_ventaja_negativa_y_positiva(tmp_path):
    result = validar.validate(make_db(tmp_path), season="2025-2026")
    fires = {f["id"]: f for f in result["incendios"]}
    assert fires["inc-a"]["ventaja_min"] == -30    # BRASA llegó antes
    assert fires["inc-c"]["ventaja_min"] == 120    # CONAF informó primero
    assert fires["inc-b"]["ventaja_min"] is None


def test_incendio_sin_detected_at_se_excluye(tmp_path):
    result = validar.validate(make_db(tmp_path), season="2025-2026")
    assert {f["id"] for f in result["incendios"]} == {"inc-a", "inc-b", "inc-c"}


def test_filtro_por_temporada(tmp_path):
    result = validar.validate(make_db(tmp_path), season="2024-2025")
    assert result["resumen"]["n"] == 1 and result["por_temporada"][0]["temporada"] == "2024-2025"


def test_candidatos_a_falso_positivo(tmp_path):
    result = validar.validate(make_db(tmp_path), season="2025-2026")
    assert result["incidentes_abiertos"] == 2 and result["candidatos_falso_positivo"] == 1


def test_json_es_valido(tmp_path, capsys):
    code = validar.main(["--db", str(make_db(tmp_path)), "--season", "2025-2026", "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["resumen"]["detectados"] == 2 and len(data["tramos"]) == 5


def test_sin_datos_mensaje_claro_y_salida_2(tmp_path, capsys):
    from backend.db import Database

    db = Database(tmp_path / "brasa.db", tmp_path / "work.db")
    _fire(db, "sin-fecha", None, 5.0)
    db.close_all()
    assert validar.main(["--db", str(tmp_path / "brasa.db")]) == 2
    assert "No hay incendios con hora de detección" in capsys.readouterr().err
