"""QA-02 (medida publicada): el replay del caso Viña 2024 produce un resumen estable.

Corre `scripts/replay_case.py` con un --limit chico sobre el JSON real del caso y
comprueba que la medida que se publica en docs/VALIDACION.md no se pudra en silencio:
el resumen trae las claves documentadas («incidentes», «con_posible»,
«minutos_hasta_posible» con min/mediana/max) y cada incidente que llega a «posible»
lo hace en o después de su primera detección. Si el resumen perdiera esas claves la
prueba falla (verificado a mano borrando «con_posible» del dict). Nada de tiempos de
reloj en las aserciones.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("replay_case", ROOT / "scripts" / "replay_case.py")
replay_case = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay_case)

GOES = ROOT / "web" / "data" / "cases" / "vina-del-mar-2024.goes.json"
LIMIT = 40  # barridos: suficiente para que el motor forme incidentes reales


def test_resumen_del_caso_tiene_las_claves_documentadas(tmp_path):
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
