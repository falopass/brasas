"""QA-20 / RISK-13: calibración de los niveles de riesgo contra incendios CONAF, base sintética."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "calibrar_riesgo", Path(__file__).resolve().parents[1] / "scripts" / "calibrar_riesgo.py")
calibrar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calibrar)

from backend.geo import territory  # noqa: E402

A = territory().by_code[5101]    # Valparaíso, región 5 → macrozona centro
B = territory().by_code[15101]   # Arica, región 15 → macrozona norte

LEVELS_A = {"2026-01-10": "alto", "2026-01-11": "alto",
            "2026-01-12": "moderado", "2026-01-13": "moderado", "2026-01-14": "moderado",
            "2026-01-15": "bajo", "2026-01-16": "bajo", "2026-01-17": "bajo",
            "2026-01-18": "bajo", "2026-01-19": "bajo"}


def _risk(db, code, date, level, combined="bajo", fwi="bajo"):
    db.execute("INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
               "level_combined, fwi_level, computed_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (code, date, level, 50, 0, 0, combined, fwi, "2026-01-20T00:00:00Z"))


def _fire(db, fid, comuna, started, region=None):
    db.execute("INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, "
               "comuna, region, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
               (fid, fid, "confirmado", "En combate", started, -33.0, -71.6, comuna, region,
                "2026-01-20T00:00:00Z", "2026-01-20T00:00:00Z"))


def _br(db, code, date, hours):
    db.execute("INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) "
               "VALUES (?,?,?,?,?,?)", (code, date, hours, 100.0, 0.5, "2026-01-10T00:00:00Z"))


def make_db(tmp_path: Path) -> Path:
    """Escenario: comuna A (centro) con 10 días —2 «alto» con incendio, 0 incendios en «bajo»—
    y comuna B (norte) con 3 días «bajo» y 1 incendio. Un incendio a las 02:00 UTC cae en el día
    anterior en Chile; dos incendios el mismo día en A se agrupan; uno sin fila de riesgo, uno sin
    comuna y uno con comuna inexistente prueban los descartes."""
    from backend.db import Database

    db = Database(tmp_path / "brasa.db", tmp_path / "work.db")
    for date, level in LEVELS_A.items():
        combined = "extremo" if level == "alto" else "bajo"
        fwi = None if date == "2026-01-19" else ("alto" if level == "alto" else "bajo")
        _risk(db, A.code, date, level, combined=combined, fwi=fwi)
    for date in ("2026-01-10", "2026-01-11", "2026-01-12"):
        _risk(db, B.code, date, "bajo")
    _fire(db, "f1", A.name, "2026-01-10T18:00:00Z")   # día 10 en Chile
    _fire(db, "f2", A.name, "2026-01-10T20:00:00Z")   # mismo comuna-día que f1: se agrupa
    _fire(db, "f3", A.name, "2026-01-12T02:00:00Z")   # UTC 12 ene = 11 ene 23:00 en Chile
    _fire(db, "f4", B.name, "2026-01-10T15:00:00Z")
    _fire(db, "f5", A.name, "2026-02-05T15:00:00Z")   # día sin fila en risk_daily
    _fire(db, "f6", None, "2026-01-10T15:00:00Z")     # sin comuna: descartado
    _fire(db, "f7", "Comuna Inexistente", "2026-01-10T15:00:00Z", region="Otra")  # sin calce
    for date in ("2026-01-10", "2026-01-11", "2026-01-12", "2026-01-20"):
        _br(db, A.code, date, 4)
    db.close_all()
    return tmp_path / "work.db"


def _by_level(rows):
    return {(r["macrozona"], r["nivel"]): r for r in rows}


def test_conteo_de_filas_usadas_y_descartadas(tmp_path):
    c = calibrar.calibrate(make_db(tmp_path))["conteo"]
    assert c["incendios_conaf"] == 7
    assert c["incendios_usados"] == 5
    assert c["eventos_comuna_dia"] == 4 and c["agrupados_mismo_dia"] == 1
    assert c["descartados_sin_comuna"] == 1 and c["sin_calce_comuna"] == 1
    assert c["eventos_sin_dato_riesgo"] == 1        # f5 cayó en un día sin fila de riesgo
    assert c["dias_riesgo"] == 13 and c["dias_boton_rojo"] == 4


def test_nivel_3030_por_macrozona(tmp_path):
    rows = _by_level(calibrar.calibrate(make_db(tmp_path))["niveles"]["level"])
    assert rows[("centro", "alto")] == {"macrozona": "centro", "nivel": "alto", "dias": 2,
                                       "con_incendio": 2, "tasa": 1.0, "lift": 5.0}
    assert rows[("centro", "moderado")]["con_incendio"] == 0   # f3 cayó en el día 11, no en el 12
    assert rows[("centro", "bajo")]["dias"] == 5 and rows[("centro", "bajo")]["con_incendio"] == 0
    assert rows[("centro", "(base)")]["tasa"] == 0.2           # 2 eventos / 10 días
    assert rows[("norte", "bajo")]["tasa"] == round(1 / 3, 4) and rows[("norte", "bajo")]["lift"] == 1.0


def test_combinado_y_fwi(tmp_path):
    result = calibrar.calibrate(make_db(tmp_path))
    combinado = _by_level(result["niveles"]["level_combined"])
    assert combinado[("centro", "extremo")]["con_incendio"] == 2
    assert combinado[("centro", "bajo")]["dias"] == 8
    fwi = _by_level(result["niveles"]["fwi_level"])
    assert fwi[("centro", "alto")] == {"macrozona": "centro", "nivel": "alto", "dias": 2,
                                      "con_incendio": 2, "tasa": 1.0, "lift": round(1 / (2 / 9), 2)}
    assert fwi[("centro", "(base)")]["dias"] == 9              # el día 19 no tiene fwi_level
    assert result["dias_sin_dato"]["fwi_level"] == {"centro": 1}


def test_concordancia_boton_rojo(tmp_path):
    rows = {r["macrozona"]: r for r in calibrar.calibrate(make_db(tmp_path))["boton_rojo"]}
    assert rows["centro"]["dias_con_br"] == 4 and rows["centro"]["con_incendio_br"] == 2
    assert rows["centro"]["tasa_con_br"] == 0.5
    assert rows["centro"]["dias_sin_br"] == 7 and rows["centro"]["con_incendio_sin"] == 0
    assert rows["centro"]["lift"] is None                      # sin incendios fuera de BR no hay razón
    assert rows["norte"]["dias_sin_br"] == 3 and rows["norte"]["con_incendio_sin"] == 1


def test_comunas_sin_calce_se_informan(tmp_path):
    result = calibrar.calibrate(make_db(tmp_path))
    assert result["comunas_sin_calce"] == [{"comuna": "Comuna Inexistente", "region": "Otra", "incendios": 1}]


def test_main_imprime_tablas_y_escribe_json(tmp_path, capsys):
    db = make_db(tmp_path)
    out_json = tmp_path / "reporte.json"
    assert calibrar.main(["--db", str(db), "--json", str(out_json)]) == 0
    out = capsys.readouterr().out
    for title in ("Nivel 30-30-30", "Nivel combinado (30-30-30 + FWI)", "Clase FWI",
                  "Concordancia con el Botón Rojo", "comuna no reconocida"):
        assert title in out
    assert "| centro | alto | 2 | 2 | 100.0% | 5 |" in out
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["conteo"]["eventos_comuna_dia"] == 4


def test_db_inexistente_salida_2(tmp_path, capsys):
    assert calibrar.main(["--db", str(tmp_path / "no.db")]) == 2
    assert "No existe" in capsys.readouterr().err
