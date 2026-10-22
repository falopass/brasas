"""Pruebas del verificador semanal de enlaces vivos (.github/scripts/enlaces_vivos.py).

Sin red: la extracción lee los archivos reales y los veredictos usan respuestas simuladas o un
JSON ya calculado con `--from`. La sonda real solo corre en el workflow semanal.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
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
    assert set(por_url["https://senapred.cl/kit-de-emergencia/"]) == {"web/js/views/preparate.js", "docs/FUENTES.md"}


def test_extraccion_no_toma_plantillas():
    # La plantilla de la API de FIRMS ([MAP_KEY], [PRODUCTO]) no es una URL sondeable.
    assert all("[" not in e["url"] and "{" not in e["url"] for e in ev.extraer_todos())


@pytest.mark.parametrize(
    ("code", "final", "estado"),
    [
        (200, "https://x.cl/a", "OK"),
        (404, "https://x.cl/a", "FALLA"),
        (403, "https://x.cl/a", "OJO"),
        (200, "https://otro.cl/a", "OJO"),
        (200, "https://www.x.cl/a", "OK"),
    ],
    ids=["200", "404", "403", "otro-dominio", "www"],
)
def test_veredicto_por_respuesta(code, final, estado):
    assert ev.veredicto("https://x.cl/a", code, final)[0] == estado


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


@pytest.mark.parametrize(("estados", "codigo"), [(["OK", "FALLA"], 1), (["OK", "OJO"], 0)], ids=["con-falla", "ok-y-ojo"])
def test_main_sale_con_1_solo_si_hay_falla(tmp_path, monkeypatch, capsys, estados, codigo):
    assert _from(tmp_path, monkeypatch, estados) == codigo
    if codigo:
        assert "::error::" in capsys.readouterr().out
        assert (tmp_path / "alerta.md").exists()


def test_workflow_declara_agenda_y_dispatch():
    wf = yaml.safe_load((RAIZ / ".github" / "workflows" / "enlaces-vivos.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))  # PyYAML 1.1 lee «on» como booleano
    assert "schedule" in on and "workflow_dispatch" in on
    perms = wf.get("permissions") or wf["jobs"]["enlaces"]["permissions"]
    assert perms == {"contents": "read", "issues": "write"}
