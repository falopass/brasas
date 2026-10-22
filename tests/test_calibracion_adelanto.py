"""Guarda de la medida de adelanto publicada (QA-03): web/data/calibracion.json.

Valida la forma del JSON que genera scripts/local/medir_adelanto.py y que la vista Calidad
consume, incluida la lista de casos corridos y la cobertura de la medida. No corre el
replay: el dato ya viene calculado.
"""

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data" / "calibracion.json"

sys.path.insert(0, str(ROOT / "scripts" / "local"))
import medir_adelanto  # noqa: E402


def _load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def _parse_ts(value, context):
    assert isinstance(value, str) and value, f"{context}: timestamp vacío"
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert moment.tzinfo is not None, f"{context}: timestamp sin zona ({value!r})"
    return moment


def test_esquema_calibracion():
    data = _load()
    assert isinstance(data.get("case_id"), str) and data["case_id"], "sin case_id"
    _parse_ts(data.get("generated_at"), "generated_at")
    assert data.get("source"), "sin source"
    assert data.get("method"), "sin method"

    incidents = data.get("incidents")
    assert isinstance(incidents, list) and incidents, "incidents debe ser lista no vacía"
    for inc in incidents:
        ctx = f"incidente {inc.get('id', '?')}"
        assert inc.get("id"), "incidente sin id"
        _parse_ts(inc.get("first_seen_at"), ctx)
        mins = inc.get("min_to_posible")
        assert mins is None or (isinstance(mins, (int, float)) and not isinstance(mins, bool) and mins >= 0), (
            f"{ctx}: min_to_posible inválido ({mins!r})"
        )
        assert isinstance(inc.get("n_obs"), int) and inc["n_obs"] >= 1, f"{ctx}: n_obs inválido"

    summary = data.get("summary")
    assert isinstance(summary, dict), "sin summary"
    assert summary.get("n_incidents") == len(incidents), "n_incidents no calza con incidents"
    medidos = [i["min_to_posible"] for i in incidents if i["min_to_posible"] is not None]
    if medidos:
        assert summary["median_min"] == statistics.median(medidos), "median_min no es la mediana"
        assert summary["max_min"] == max(medidos), "max_min no es el peor caso"
    else:
        assert summary["median_min"] is None and summary["max_min"] is None

    cases = data.get("cases")
    assert isinstance(cases, list) and cases, "sin cases"
    vistos = 0
    for caso in cases:
        assert caso.get("case_id"), "caso sin case_id"
        assert caso["summary"]["n_incidents"] == len(caso["incidents"]), f"{caso['case_id']}: n_incidents no calza con sus incidents"
        vistos += len(caso["incidents"])
    assert vistos == len(incidents), "la lista plana no reúne los incidentes de todos los casos"

    coverage = data.get("coverage")
    assert isinstance(coverage, dict), "sin coverage"
    assert coverage["n_incidentes"] == len(incidents)
    assert coverage["n_medidos"] == len(medidos)
    assert coverage["n_sin_posible"] == len(incidents) - len(medidos)


def _inc(inc_id, mins):
    return {"id": inc_id, "first_seen_at": "2026-01-01T00:00:00Z", "min_to_posible": mins, "n_obs": 5}


def _caso(case_id, minutos):
    medidos = [m for m in minutos if m is not None]
    return {
        "case_id": case_id,
        "source": "NOAA GOES-16 FDC · dominio público",
        "incidents": [_inc(f"{case_id}-{i}", m) for i, m in enumerate(minutos)],
        "summary": {
            "n_incidents": len(minutos),
            "median_min": statistics.median(medidos) if medidos else None,
            "max_min": max(medidos) if medidos else None,
        },
    }


def test_combinar_dos_casos_sinteticos():
    """combine() junta casos: mediana del conjunto completo y cobertura con los «sin posible»."""
    resultado = medir_adelanto.combine([_caso("caso-a", [10, None]), _caso("caso-b", [40, 50])])
    assert resultado["case_id"] == "varios-casos"
    assert resultado["summary"]["n_incidents"] == len(resultado["incidents"]) == 4
    assert resultado["summary"]["median_min"] == statistics.median([10, 40, 50])
    assert resultado["summary"]["max_min"] == 50
    assert resultado["coverage"] == {"n_incidentes": 4, "n_medidos": 3, "n_sin_posible": 1}
    assert [c["case_id"] for c in resultado["cases"]] == ["caso-a", "caso-b"]


def _caso_goes(tmp_path, case_id="caso-sintetico"):
    """Caso GOES mínimo: dos barridos con una detección en el mismo punto."""
    goes = tmp_path / f"{case_id}.goes.json"
    goes.write_text(
        json.dumps(
            {
                "case_id": case_id,
                "source": "NOAA GOES-19 FDC",
                "start_utc": "2026-01-02T00:00:00Z",
                "scans": [{"t": "2026-01-02T00:00:00Z", "n": 1}, {"t": "2026-01-02T00:10:00Z", "n": 1}],
                "rows": [[0, -38.7, -72.6, 12.0, 320.0, 2], [10, -38.7, -72.6, 15.0, 322.0, 2]],
            }
        ),
        encoding="utf-8",
    )
    return goes


def test_caso_unico_conserva_el_esquema_de_antes(tmp_path):
    """Medir un caso solo no agrega cases ni coverage, y dos corridas dan el mismo archivo."""
    goes = _caso_goes(tmp_path)
    primero = medir_adelanto.measure(goes)
    assert primero["case_id"] == "caso-sintetico"
    assert "cases" not in primero and "coverage" not in primero
    assert primero["summary"]["n_incidents"] == len(primero["incidents"]) == 1
    incidente = primero["incidents"][0]
    assert incidente["id"] == "caso-sintetico-001"
    assert incidente["min_to_posible"] == 10
    assert incidente["n_obs"] == 2
    assert primero["summary"]["median_min"] == primero["summary"]["max_min"] == 10
    # El id es estable: volver a medir no reescribe el archivo (el uuid del replay sí cambiaría).
    assert medir_adelanto.measure(goes)["incidents"] == primero["incidents"]
