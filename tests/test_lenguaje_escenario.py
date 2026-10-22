"""Guarda de lenguaje (QA-79): la propagación y los escenarios de BRASA se
rotulan como «escenario estimado», nunca como una predicción.

Corre el chequeo sobre el repositorio y, con fixtures en tmp_path, comprueba
que cada fórmula prohibida se detecta y que las negaciones válidas
(«no es una predicción») no se marcan.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import chequeo_lenguaje  # noqa: E402


def proyecto(tmp_path: Path, archivos: dict[str, str]) -> Path:
    for relativa, texto in archivos.items():
        ruta = tmp_path / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
    return tmp_path


def test_repositorio_sin_hallazgos():
    encontrados = chequeo_lenguaje.hallazgos(chequeo_lenguaje.ROOT)
    assert not encontrados, "Fórmulas de predicción en textos visibles:\n" + "\n".join(encontrados)


@pytest.mark.parametrize(
    ("frase", "formula"),
    [
        ("El fuego llegará al pueblo.", "llegará"),  # el patrón cubre el plural
        ("El fuego va a llegar al pueblo.", "va a llegar"),
        ("Se quemará el cerro.", "se quemará"),
        ("El fuego quemará el bosque.", "quemará"),
        ("El fuego se propagará a la quebrada.", "se propagará a"),
        ("El modelo predice el avance.", "predice"),
        ("El control está garantizado.", "garantizado"),
        ("La predicción no tiene fuente.", "predicción"),
    ],
)
def test_detecta_cada_formula(tmp_path, frase, formula):
    raiz = proyecto(tmp_path, {"web/js/aviso.js": f"const texto = '{frase}';\n"})
    encontrados = chequeo_lenguaje.hallazgos(raiz)
    assert encontrados, f"no se detectó: {frase}"
    assert formula in encontrados[0].lower(), encontrados[0]


def test_no_marca_escenario_estimado_ni_negaciones(tmp_path):
    raiz = proyecto(
        tmp_path,
        {
            "web/index.html": "<p>Escenario estimado con las condiciones de ahora.</p>\n",
            "web/js/aviso.js": "\n".join(
                [
                    "const a = 'No es una predicción: es un escenario estimado.';",
                    "const b = 'Esto no es predicción: es un escenario estimado.';",
                ]
            )
            + "\n",
            "backend/routes/public.py": 'NOTA = "Escenario estimado: no es una predicción."\n',
        },
    )
    assert chequeo_lenguaje.hallazgos(raiz) == []


def test_solo_literales_en_python(tmp_path):
    raiz = proyecto(tmp_path, {"backend/ejemplo.py": "# el fuego llegará al pueblo\nVAR = 1\n"})
    assert chequeo_lenguaje.hallazgos(raiz) == []


def test_literal_python_multilinea(tmp_path):
    raiz = proyecto(
        tmp_path,
        {"backend/ejemplo.py": 'NOTA = """\nEscenario estimado.\nEl fuego llegará al pueblo.\n"""\n'},
    )
    encontrados = chequeo_lenguaje.hallazgos(raiz)
    assert len(encontrados) == 1
    assert encontrados[0].startswith("backend/ejemplo.py:3:")
    assert "llegará" in encontrados[0]


def test_exclusiones(tmp_path):
    raiz = proyecto(
        tmp_path,
        {
            "web/vendor/x.js": "const t = 'el fuego llegará';\n",
            "web/data/x.js": "const t = 'el fuego llegará';\n",
            "docs/investigacion/x.md": "el fuego llegará\n",
            "tests/x.py": "NOTA = 'el fuego llegará'\n",
        },
    )
    assert chequeo_lenguaje.hallazgos(raiz) == []


@pytest.mark.parametrize(
    ("contenido", "fragmento"),
    [
        ('{"texto": "El fuego llegará al pueblo."}\n', "llegará"),
        ('{"caso": {"items": [{"texto": "Se quemará el cerro."}]}}\n', "Se quemará"),
    ],
)
def test_json_se_revisa_por_valores_con_archivo_y_linea(tmp_path, contenido, fragmento):
    raiz = proyecto(tmp_path, {"web/data/casos.json": contenido})
    [encontrado] = chequeo_lenguaje.hallazgos(raiz)
    assert encontrado.startswith("web/data/casos.json:1:")
    assert fragmento in encontrado


def test_json_no_marca_las_claves_ni_las_negaciones(tmp_path):
    raiz = proyecto(
        tmp_path,
        {
            "web/data/fichas.json": '{"prediccion": "escenario estimado", "detalle": "todo en orden"}\n',
            "web/data/notas.json": '{"nota": "No es una predicción: es un escenario estimado."}\n',
        },
    )
    assert chequeo_lenguaje.hallazgos(raiz) == []


def test_html_y_linea(tmp_path):
    raiz = proyecto(
        tmp_path,
        {"web/index.html": "<p>Escenario estimado.</p>\n<p>El fuego se propagará a la quebrada.</p>\n"},
    )
    encontrados = chequeo_lenguaje.hallazgos(raiz)
    assert len(encontrados) == 1
    assert encontrados[0].startswith("web/index.html:2:")


@pytest.mark.parametrize(
    ("html", "codigo", "salida"),
    [
        ("<p>Escenario estimado.</p>\n", 0, "Sin hallazgos"),
        ("<p>El fuego llegará.</p>\n", 1, "web/index.html:1"),
    ],
)
def test_main_codigo_y_salida(tmp_path, capsys, html, codigo, salida):
    raiz = proyecto(tmp_path, {"web/index.html": html})
    assert chequeo_lenguaje.main(["--raiz", str(raiz)]) == codigo
    assert salida in capsys.readouterr().out
