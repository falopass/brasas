"""QA-02: el banco de reproducción con un caso sintético (sin tocar los .goes.json reales)
y con el caso Viña 2024, cuya medida publicada en docs/VALIDACION.md no puede podrirse.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("replay_case", ROOT / "scripts" / "replay_case.py")
replay_case = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay_case)

KM_LAT = 1 / 111.0
GOES = ROOT / "web" / "data" / "cases" / "vina-del-mar-2024.goes.json"
LIMIT = 40  # barridos: suficiente para que el motor forme incidentes reales


def synthetic(tmp_path: Path) -> Path:
    """Dos focos que terminan en dos incidentes: uno se fusiona y llega a «posible», otro queda
    en «anomalia» (su segunda detección es de confianza baja y no suma evidencia confiable)."""
    path = tmp_path / "synthetic.goes.json"
    path.write_text(json.dumps({
        "case_id": "synthetic", "source": "NOAA GOES-19 ABI L2 FDCF (sintético)",
        "start_utc": "2027-02-01T12:00:00Z",
        "scans": [{"t": f"2027-02-01T{12 + i // 6:02d}:{(i % 6) * 10:02d}:00Z", "n": 1} for i in range(6)],
        "rows": [
            [0, -36.80, -73.0, 30.0, None, 2],          # incidente A (anomalía)
            [10, -36.80 + 0.5 * KM_LAT, -73.0, 35.0, None, 2],   # se une a A → «posible» al min 10
            [20, -36.80 + 5 * KM_LAT, -73.0, 40.0, None, 2],     # incidente C, separado de A
            [30, -36.80 + 2.8 * KM_LAT, -73.0, 45.0, None, 2],   # puente: fusiona C dentro de A
            [40, -33.5, -70.8, 50.0, None, 1],          # incidente B, lejos
            [50, -33.5, -70.8, 55.0, None, 0],          # confianza baja: se une a B sin subirlo
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_replay_mide_minutos_a_posible_y_fusiones(tmp_path):
    result = replay_case.replay(synthetic(tmp_path), tmp_path / "replay.db")
    assert result["scans"] == 6 and result["detections"] == 6 and result["merges"] == 1
    [fire, anomaly] = result["incidents"]
    assert fire["status"] == "posible" and fire["n_obs"] == 4 and fire["minutes_to_posible"] == 10
    assert anomaly["status"] == "anomalia" and anomaly["n_obs"] == 2 and anomaly["minutes_to_posible"] is None


def test_replay_la_base_es_desechable(tmp_path):
    """Repetir sobre la misma ruta no acumula: la base se recrea en cada corrida."""
    result = replay_case.replay(synthetic(tmp_path), tmp_path / "replay.db")
    again = replay_case.replay(synthetic(tmp_path), tmp_path / "replay.db")
    without_id = lambda rows: [{k: v for k, v in r.items() if k != "id"} for r in rows]
    assert without_id(again["incidents"]) == without_id(result["incidents"]) and again["merges"] == 1


def test_limit_procesa_solo_los_primeros_barridos(tmp_path):
    result = replay_case.replay(synthetic(tmp_path), tmp_path / "replay.db", limit=2)
    assert result["scans"] == 2 and result["detections"] == 2 and result["merges"] == 0
    assert [i["status"] for i in result["incidents"]] == ["posible"]


def test_resumen_del_caso_real_tiene_las_claves_documentadas(tmp_path):
    """El resumen que publica docs/VALIDACION.md conserva sus claves y su orden.

    Si el resumen perdiera esas claves la prueba falla (verificado a mano borrando
    «con_posible» del dict). Nada de tiempos de reloj en las aserciones."""
    result = replay_case.replay(GOES, tmp_path / "replay.db", limit=LIMIT)
    assert result["case_id"] == "vina-del-mar-2024" and result["scans"] == LIMIT

    incidents = result["incidents"]
    assert 0 < len(incidents) <= result["detections"]

    resumen = result["resumen"]
    assert set(resumen) == {"incidentes", "con_posible", "minutos_hasta_posible"}
    assert resumen["incidentes"] == len(incidents) and resumen["con_posible"] <= resumen["incidentes"]
    medida = resumen["minutos_hasta_posible"]
    if resumen["con_posible"]:
        assert set(medida) == {"min", "mediana", "max"} and medida["min"] <= medida["mediana"] <= medida["max"]
    else:
        assert medida is None

    # «posible» no puede llegar antes de la primera detección del incidente.
    for inc in incidents:
        if inc["minutes_to_posible"] is not None:
            assert inc["minutes_to_posible"] >= 0
