"""AUTO-59: veredicto de la exploración de fuentes oficiales (.github/scripts/explorar.py).

Sin red: `get()` se reemplaza por un doble y el JSON se escribe en tmp_path. Los casos son los
del criterio de listo: un grupo entero caído devuelve 2, una sola sonda caída deja el grupo en
`dudoso` y nombra la URL, y todo respondiendo bien queda `ok` y en 0.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.request
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "explorar.py"
_CAMPOS = {"grupo", "url", "status", "content_type", "bytes", "veredicto"}
_TRES = ("https://fuente.cl/a", "https://fuente.cl/b", "https://fuente.cl/c")


def cargar():
    spec = importlib.util.spec_from_file_location("explorar_fuentes", _SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


explorar = cargar()


def doble(respuestas):
    """get() de mentira: (status, content-type, cuerpo) por URL; lo no listado queda caído."""

    def get(url, n=600_000):
        return respuestas.get(url, (0, "", "sin respuesta"))

    return get


def correr(monkeypatch, tmp_path, respuestas, sondas=_TRES):
    def grupo():
        for url in sondas:
            explorar.sonda(url)

    monkeypatch.setitem(explorar.GRUPOS, "web", grupo)
    monkeypatch.setattr(explorar, "SALIDA", tmp_path)
    monkeypatch.setattr(explorar, "get", doble(respuestas))
    return explorar.main(["web"])


def leer(tmp_path):
    return json.loads((tmp_path / "explorar-web.json").read_text(encoding="utf-8"))


def test_grupo_entero_caido_devuelve_2(monkeypatch, tmp_path):
    assert correr(monkeypatch, tmp_path, {}) == 2
    datos = leer(tmp_path)
    assert datos["veredicto"] == "caido"
    assert datos["resumen"] == {"ok": 0, "dudoso": 0, "caido": 3, "total": 3}
    assert all(s["veredicto"] == "caido" for s in datos["sondas"])
    assert all(s["bytes"] == 0 for s in datos["sondas"]), "sin respuesta no hay bytes"


def test_una_sonda_caida_deja_dudoso_devuelve_0_y_nombra_la_url(monkeypatch, tmp_path):
    respuestas = {url: (200, "text/html", "<html>aviso</html>") for url in _TRES[:2]}
    assert correr(monkeypatch, tmp_path, respuestas) == 0
    datos = leer(tmp_path)
    assert datos["veredicto"] == "dudoso"
    assert datos["resumen"] == {"ok": 2, "dudoso": 0, "caido": 1, "total": 3}
    assert [s["url"] for s in datos["sondas"] if s["veredicto"] == "caido"] == [_TRES[2]]


def test_todo_ok_devuelve_0(monkeypatch, tmp_path):
    respuestas = {url: (200, "text/html", "<html>aviso</html>") for url in _TRES}
    assert correr(monkeypatch, tmp_path, respuestas) == 0
    datos = leer(tmp_path)
    assert datos["veredicto"] == "ok"
    assert datos["resumen"] == {"ok": 3, "dudoso": 0, "caido": 0, "total": 3}


def test_json_en_el_archivo_esperado_sin_tokens_ni_credenciales(monkeypatch, tmp_path):
    sondas = (
        "https://fuente.cl/datos?token=secreto123&f=json",
        "https://vecino:clave@fuente.cl/privado",
        "https://fuente.cl/capa?f=json&_fields=link,modified",
    )
    respuestas = {url: (200, "application/json", '{"ok": true}') for url in sondas}
    assert correr(monkeypatch, tmp_path, respuestas, sondas) == 0
    texto = (tmp_path / "explorar-web.json").read_text(encoding="utf-8")
    assert "token" not in texto
    assert "secreto123" not in texto
    assert "vecino:clave@" not in texto
    assert "https://fuente.cl/capa?f=json&_fields=link,modified" in texto
    assert json.loads(texto)["resumen"]["total"] == 3


def test_importar_no_hace_ninguna_llamada_de_red(monkeypatch):
    def bomba(*args, **kwargs):
        raise AssertionError("el módulo hizo red al importarse")

    monkeypatch.setattr(urllib.request, "urlopen", bomba)
    assert cargar().GRUPOS["web"].__name__ == "grupo_web"


def test_grupo_desconocido_lo_dice_sin_reventar(capsys):
    assert explorar.main(["no-existe"]) == 1
    assert "grupo desconocido" in capsys.readouterr().err


def test_los_grupos_del_workflow_existen_y_dejan_sus_sondas(monkeypatch, tmp_path):
    assert {"boton2", "dmc2", "dmc", "web"} <= set(explorar.GRUPOS)
    monkeypatch.setattr(explorar, "SALIDA", tmp_path)
    monkeypatch.setattr(explorar, "get", lambda url, n=600_000: (200, "text/html; charset=utf-8", "<html>aviso</html>"))
    assert explorar.main(["web"]) == 0
    datos = leer(tmp_path)
    assert datos["resumen"]["total"] >= 9
    assert datos["fecha"].endswith("Z")
    assert all(set(s) == _CAMPOS for s in datos["sondas"])


@pytest.mark.parametrize(
    ("url", "status", "body", "esperado"),
    [
        ("https://fuente.cl/", 200, "<html>aviso</html>", "ok"),
        ("https://fuente.cl/", 200, "", "dudoso"),
        ("https://fuente.cl/", 200, "   \n", "dudoso"),
        ("https://fuente.cl/", 404, "no existe", "caido"),
        ("https://fuente.cl/", 503, "mantenimiento", "caido"),
        ("https://fuente.cl/", 0, "timed out", "caido"),
        ("https://servicios.cl/capa/0?f=json", 200, '{"error": {"code": 404}}', "dudoso"),
        ("https://servicios.cl/capa/0?f=json", 200, "<html>mantención</html>", "dudoso"),
        ("https://servicios.cl/capa/0?f=json", 200, '{"fields": []}', "ok"),
        ("https://archivos.cl/aviso_cap.xml", 200, "<html>error</html>", "dudoso"),
        ("https://archivos.cl/aviso_cap.xml", 200, "<?xml version='1.0'?><alert/>", "ok"),
    ],
)
def test_veredicto_por_sonda(url, status, body, esperado):
    assert explorar.veredicto(url, status, body) == esperado
