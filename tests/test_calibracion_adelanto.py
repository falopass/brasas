"""Guarda de la medida de adelanto publicada (QA-03): web/data/calibracion.json.

Valida la forma del JSON que genera scripts/local/medir_adelanto.py y que la vista Calidad
consume, y que las cifras citadas en docs/CALIBRACION.md («mediana de N min», «el más lento
tardó N min») coinciden con el resumen del JSON — guarda contra desfase entre el dato y el
documento. No corre el replay: el dato ya viene calculado.
"""

import json
import re
import statistics
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data" / "calibracion.json"
DOC = ROOT / "docs" / "CALIBRACION.md"


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


def _cifra(doc, patron):
    """Extrae «N min» del patrón citado en el documento; None si no aparece."""
    match = re.search(patron, doc)
    return float(match.group(1).replace(",", ".")) if match else None


def test_doc_cita_las_cifras_del_json():
    """docs/CALIBRACION.md cita la mediana y el peor caso del JSON (guarda contra desfase)."""
    summary = _load()["summary"]
    doc = DOC.read_text(encoding="utf-8")
    mediana = _cifra(doc, r"mediana de \*\*(\d+(?:[.,]\d+)?) min\*\*")
    peor = _cifra(doc, r"más lento tardó \*\*(\d+(?:[.,]\d+)?) min\*\*")
    assert mediana is not None, "CALIBRACION.md no cita «mediana de **N min**»"
    assert peor is not None, "CALIBRACION.md no cita «el más lento tardó **N min**»"
    assert mediana == summary["median_min"], (
        f"el doc dice {mediana} min y el JSON {summary['median_min']}: re-corre medir_adelanto.py o corrige el doc"
    )
    assert peor == summary["max_min"], f"el doc dice {peor} min y el JSON {summary['max_min']}: re-corre medir_adelanto.py o corrige el doc"
