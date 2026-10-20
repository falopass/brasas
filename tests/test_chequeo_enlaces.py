"""Chequeo de enlaces externos (AUTO-08): extracción, clasificación e informe, sin red.

Las respuestas HTTP se simulan con el JSON de `--desde`; ninguna prueba sale a internet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import chequeo_enlaces  # noqa: E402


def proyecto(tmp_path: Path, archivos: dict[str, str]) -> Path:
    for relativa, texto in archivos.items():
        ruta = tmp_path / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
    return tmp_path


def correr(raiz: Path, respuestas: dict, *extra: str) -> tuple[int, str]:
    fixture = raiz / "respuestas.json"
    fixture.write_text(json.dumps(respuestas), encoding="utf-8")
    salida = raiz / "docs" / "ENLACES.md"
    codigo = chequeo_enlaces.main(["--raiz", str(raiz), "--offline", "--desde", str(fixture), "--salida", str(salida), *extra])
    return codigo, salida.read_text(encoding="utf-8")


def test_extraccion_deduplica_y_guarda_todas_las_ubicaciones(tmp_path):
    raiz = proyecto(
        tmp_path,
        {
            "web/index.html": '<a href="https://senapred.cl/">SENAPRED</a>\n',
            "web/js/aviso.js": "const fuente = 'https://senapred.cl/';\n",
            "docs/FUENTES.md": "Ver <https://www.conaf.cl/>.\n",
        },
    )
    enlaces = chequeo_enlaces.extraer_enlaces(raiz)
    assert list(enlaces) == ["https://senapred.cl/", "https://www.conaf.cl/"]
    assert enlaces["https://senapred.cl/"] == ["web/index.html:1", "web/js/aviso.js:1"]


def test_descarta_internas_ejemplo_plantillas_e_investigacion(tmp_path):
    raiz = proyecto(
        tmp_path,
        {
            "web/index.html": "\n".join(
                [
                    "http://localhost:8000/api",
                    "https://brasa-chile.ddiegosebastianbb.workers.dev/web/icons/og.png",
                    "https://example.com/demo",
                    "https://tiles.openfreemap.org/{z}/{x}/{y}.png",
                    "http://www.w3.org/2000/svg",
                    "https://www.openstreetmap.org/?mlat=${lat}",
                    "https://senapred.cl/incendios-forestales/",
                ]
            ),
            "docs/investigacion/INV-01.md": "Cita histórica: https://sitio-antiguo.cl/x\n",
        },
    )
    assert list(chequeo_enlaces.extraer_enlaces(raiz)) == ["https://senapred.cl/incendios-forestales/"]


def test_no_se_escanea_a_si_mismo(tmp_path):
    raiz = proyecto(tmp_path, {"docs/ENLACES.md": "https://senapred.cl/\n"})
    assert chequeo_enlaces.extraer_enlaces(raiz) == {}


@pytest.mark.parametrize(
    ("codigo", "estado"),
    [
        (200, "ok"),
        (206, "ok"),
        (301, "ok"),
        (404, "roto"),
        (410, "roto"),
        (401, "bloqueado"),
        (403, "bloqueado"),
        (429, "bloqueado"),
        (500, "error"),
        (503, "error"),
    ],
)
def test_clasificacion(codigo, estado):
    assert chequeo_enlaces.clasificar(codigo) == estado


def test_respuestas_simuladas(tmp_path):
    respuestas = {
        "https://organismo.cl/ok": {"status": 200},
        "https://organismo.cl/roto": {"status": 404},
        "https://organismo.cl/bloqueado": {"status": 403},
        "https://organismo.cl/timeout": {"error": "timeout"},
    }
    enlaces = {url: ["web/js/x.js:1"] for url in respuestas}
    resultados = chequeo_enlaces.consultar_todos(enlaces, tmp_path, respuestas)
    assert [r["estado"] for r in resultados] == ["ok", "roto", "bloqueado", "error"]
    assert resultados[3]["codigo"] is None
    assert resultados[3]["detalle"] == "timeout"


def test_bloqueado_no_hace_fallar(tmp_path):
    raiz = proyecto(tmp_path, {"web/js/calor.js": "https://senapred.cl/alertas/\n"})
    codigo, informe = correr(raiz, {"https://senapred.cl/alertas/": {"status": 403}})
    assert codigo == 0
    assert "| https://senapred.cl/alertas/ | bloqueado | 403 |" in informe
    assert "1 bloqueado" in informe


def test_informe_propone_reemplazo_del_mismo_organismo(tmp_path):
    raiz = proyecto(
        tmp_path,
        {
            "web/js/calor.js": "url: 'https://senapred.cl/kit-de-emergencia/'\n",
            "docs/FUENTES.md": "SENAPRED: <https://senapred.cl/> y <https://senapred.cl/incendios-forestales/>.\n",
        },
    )
    codigo, informe = correr(raiz, {"https://senapred.cl/kit-de-emergencia/": {"status": 404}})
    assert codigo == 1
    assert "| https://senapred.cl/kit-de-emergencia/ | roto | 404 | `web/js/calor.js:1` | https://senapred.cl/ |" in informe


def test_sin_reemplazo_conocido(tmp_path):
    raiz = proyecto(tmp_path, {"web/index.html": "https://organismo-desconocido.cl/x\n"})
    codigo, informe = correr(raiz, {"https://organismo-desconocido.cl/x": {"status": 410}})
    assert codigo == 1
    assert chequeo_enlaces.SIN_REEMPLAZO_TXT in informe


def test_solo_rotos_y_json(tmp_path, capsys):
    raiz = proyecto(tmp_path, {"web/index.html": "https://organismo.cl/ok\nhttps://organismo.cl/roto\n"})
    codigo, informe = correr(
        raiz,
        {"https://organismo.cl/ok": {"status": 200}, "https://organismo.cl/roto": {"status": 404}},
        "--solo-rotos",
        "--json",
    )
    assert codigo == 1
    assert "https://organismo.cl/ok" not in informe
    datos = json.loads(capsys.readouterr().out)
    assert [e["url"] for e in datos["enlaces"]] == ["https://organismo.cl/roto"]
    assert datos["resumen"] == {"ok": 1, "roto": 1, "bloqueado": 0, "error": 0}
