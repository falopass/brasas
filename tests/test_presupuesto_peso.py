"""Presupuesto de peso de las páginas bajo demanda (DEBT-07).

Ninguna prueba toca el web/ real: cada una arma su propio proyecto en tmp_path
y ajusta los umbrales con monkeypatch para no depender de los números del repo.
El contenido aleatorio (randbytes con semilla) no comprime, así los tamaños
gzip son estables.

La portada del proyecto de juguete referencia app.css y app.js: esos archivos
son arranque (los mide peso_arranque.py) y no suman al total bajo demanda.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import presupuesto_peso  # noqa: E402

PORTADA = b'<html><head><link rel="stylesheet" href="/web/css/app.css"><script type="module" src="/web/js/app.js"></script></head></html>'


def hacer_web(tmp_path: Path, archivos: dict[str, bytes]) -> Path:
    archivos = {
        "index.html": PORTADA,
        "css/app.css": b"body{}",
        "js/app.js": b"export const a = 1;",
        **archivos,
    }
    for rel, datos in archivos.items():
        ruta = tmp_path / "web" / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)
    return tmp_path


def aleatorio(n: int) -> bytes:
    return random.Random(20261019).randbytes(n)


def js_pesado(n: int) -> bytes:
    """JS válido y poco comprimible: el arranque lee los módulos como texto."""
    return aleatorio(n).hex().encode()


def test_proyecto_chico_pasa(tmp_path):
    raiz = hacer_web(
        tmp_path,
        {
            "lite.html": b"<html></html>",
            "js/lite.js": aleatorio(300),
            "manifest.webmanifest": b"{}",
        },
    )
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 0


def test_total_excedido_nombra_el_tope_y_el_archivo(tmp_path, monkeypatch, capsys):
    raiz = hacer_web(
        tmp_path,
        {
            "pantalla.html": aleatorio(500),
            "js/pantalla.js": aleatorio(3000),
        },
    )
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_PAGINAS_KB", 2)
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_ARCHIVO_KB", 50)
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 1
    salida = capsys.readouterr().out
    assert "páginas bajo demanda" in salida
    assert "superan el tope de 2 KB" in salida
    assert "web/js/pantalla.js" in salida
    assert "presupuesto_peso.py" in salida


def test_el_arranque_no_cuenta_para_las_paginas(tmp_path, monkeypatch):
    """El punto de DEBT-07: un arranque grande no empuja el tope de las páginas."""
    raiz = hacer_web(
        tmp_path,
        {
            "js/app.js": js_pesado(5000),
            "css/app.css": aleatorio(3000),
            "lite.html": b"<html></html>",
            "js/lite.js": aleatorio(500),
        },
    )
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_PAGINAS_KB", 1)
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_ARCHIVO_KB", 50)
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 0


def test_archivo_suelto_excede_su_tope(tmp_path, monkeypatch, capsys):
    raiz = hacer_web(tmp_path, {"js/enorme.js": aleatorio(5000)})
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_PAGINAS_KB", 50)
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_ARCHIVO_KB", 4)
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 1
    salida = capsys.readouterr().out
    assert "[bajo demanda] web/js/enorme.js" in salida
    assert "tope por archivo de 4 KB" in salida


def test_tope_por_archivo_tambien_cubre_el_arranque(tmp_path, monkeypatch, capsys):
    """El tope por archivo suelto sigue vigilando app.js y app.css."""
    raiz = hacer_web(tmp_path, {"js/app.js": js_pesado(5000)})
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_PAGINAS_KB", 50)
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_ARCHIVO_KB", 4)
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 1
    assert "[arranque] web/js/app.js" in capsys.readouterr().out


def test_informe_muestra_solo_las_paginas(tmp_path, monkeypatch, capsys):
    raiz = hacer_web(tmp_path, {"js/lite.js": aleatorio(5000)})
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_PAGINAS_KB", 1)
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_ARCHIVO_KB", 1)
    assert presupuesto_peso.main(["--raiz", str(raiz), "--informe"]) == 0
    salida = capsys.readouterr().out
    assert "web/js/lite.js" in salida
    assert "TOTAL BAJO DEMANDA" in salida
    assert "web/js/app.js" not in salida


def test_json_separa_arranque_y_paginas(tmp_path, capsys):
    raiz = hacer_web(tmp_path, {"js/lite.js": aleatorio(500)})
    assert presupuesto_peso.main(["--raiz", str(raiz), "--json"]) == 0
    datos = json.loads(capsys.readouterr().out)
    por_archivo = {f["archivo"]: f for f in datos["archivos"]}
    assert por_archivo["web/js/app.js"]["presupuesto"] == "arranque"
    assert por_archivo["web/js/lite.js"]["presupuesto"] == "bajo demanda"
    assert datos["total_gzip"] == por_archivo["web/js/lite.js"]["gzip"]
    assert datos["arranque_gzip"] > 0
    # Los dos presupuestos cubren todo lo propio, sin contar nada dos veces.
    assert datos["total_gzip"] + datos["arranque_gzip"] == sum(f["gzip"] for f in datos["archivos"])


def test_tope_documentado_en_paginas_md():
    """El número de docs/PAGINAS.md coincide con el del script."""
    doc = (Path(__file__).resolve().parents[1] / "docs" / "PAGINAS.md").read_text(encoding="utf-8")
    assert f"{presupuesto_peso.PRESUPUESTO_PAGINAS_KB} KB" in doc
