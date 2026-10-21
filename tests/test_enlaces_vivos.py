"""Pruebas del verificador semanal de enlaces vivos (.github/scripts/enlaces_vivos.py).

Sin red: la extracción lee los archivos reales y los veredictos usan respuestas simuladas o un
JSON ya calculado con `--from`. La sonda real solo corre en el workflow semanal.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
_SCRIPT = RAIZ / ".github" / "scripts" / "enlaces_vivos.py"
_spec = importlib.util.spec_from_file_location("enlaces_vivos", _SCRIPT)
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def test_extraccion_archivos_reales_sin_duplicados():
    enlaces = ev.extraer_todos()
    urls = [e["url"] for e in enlaces]
    assert len(urls) >= 9, f"se esperaban al menos 9 enlaces, se extrajeron {len(urls)}"
    assert len(urls) == len(set(urls)), "hay URLs repetidas en la extracción"
    assert all(u.startswith("https://") for u in urls)
    assert all(e["fuentes"] for e in enlaces), "cada enlace debe anotar su archivo de origen"


def test_extraccion_anota_origen_y_deduplica():
    por_url = {e["url"]: e["fuentes"] for e in ev.extraer_todos()}
    mascotas = (
        "https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/3342/"
        "01_kit_emergencia_mascotas_SENAPRED%202023.pdf?sequence=5&isAllowed=y"
    )
    assert por_url[mascotas] == ["web/js/views/preparate.js"]
    # Citado en Prepárate y en docs/FUENTES.md: una sola entrada, con ambos orígenes.
    kit = "https://senapred.cl/kit-de-emergencia/"
    assert set(por_url[kit]) == {"web/js/views/preparate.js", "docs/FUENTES.md"}


def test_extraccion_no_toma_plantillas():
    # La plantilla de la API de FIRMS ([MAP_KEY], [PRODUCTO]) no es una URL sondeable.
    assert all("[" not in e["url"] and "{" not in e["url"] for e in ev.extraer_todos())


def test_200_es_ok():
    assert ev.veredicto("https://x.cl/a", 200, "https://x.cl/a")[0] == "OK"


def test_404_es_falla():
    assert ev.veredicto("https://x.cl/a", 404, "https://x.cl/a")[0] == "FALLA"


def test_403_es_ojo():
    assert ev.veredicto("https://x.cl/a", 403, "https://x.cl/a")[0] == "OJO"


def test_redireccion_a_otro_dominio_es_ojo():
    assert ev.veredicto("https://x.cl/a", 200, "https://otro.cl/a")[0] == "OJO"


def test_redireccion_a_www_del_mismo_dominio_es_ok():
    assert ev.veredicto("https://x.cl/a", 200, "https://www.x.cl/a")[0] == "OK"


def test_timeout_es_falla():
    def sonda(url):
        raise TimeoutError("timed out")

    (resultado,) = ev.revisar([{"url": "https://x.cl/a", "fuentes": ["x.js"]}], sonda=sonda)
    assert resultado["estado"] == "FALLA"
    assert "TimeoutError" in resultado["detalle"]


def _from(tmp_path, monkeypatch, estados):
    datos = [{"url": f"https://x.cl/{i}", "fuentes": ["x.js"], "estado": estado, "detalle": "simulado"} for i, estado in enumerate(estados)]
    ruta = tmp_path / "veredictos.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    return ev.main(["--from", str(ruta)])


def test_una_falla_sale_con_1(tmp_path, monkeypatch, capsys):
    assert _from(tmp_path, monkeypatch, ["OK", "FALLA"]) == 1
    assert "::error::" in capsys.readouterr().out
    assert (tmp_path / "alerta.md").exists()


def test_ok_y_ojo_salen_con_0(tmp_path, monkeypatch):
    assert _from(tmp_path, monkeypatch, ["OK", "OJO"]) == 0


def test_workflow_declara_agenda_y_dispatch():
    wf = yaml.safe_load((RAIZ / ".github" / "workflows" / "enlaces-vivos.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))  # PyYAML 1.1 lee «on» como booleano
    assert "schedule" in on and "workflow_dispatch" in on
    perms = wf.get("permissions") or wf["jobs"]["enlaces"]["permissions"]
    assert perms == {"contents": "read", "issues": "write"}
