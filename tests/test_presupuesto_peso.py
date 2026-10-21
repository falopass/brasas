"""Presupuesto de peso del frontend (UX-33): umbrales sobre proyectos temporales.

La mayoría arma su propio proyecto en tmp_path y ajusta los umbrales con
monkeypatch para no depender de los números del repo. El contenido aleatorio
(randbytes con semilla) no comprime, así los tamaños gzip son estables.
Las dos del final miden el web/ real: la holgura del presupuesto y la
consistencia con docs/PAGINAS.md.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import presupuesto_peso  # noqa: E402


def hacer_web(tmp_path: Path, archivos: dict[str, bytes]) -> Path:
    web = tmp_path / "web"
    for rel, datos in archivos.items():
        ruta = web / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)
    return tmp_path


def aleatorio(n: int) -> bytes:
    return random.Random(20261019).randbytes(n)


def test_proyecto_chico_pasa(tmp_path):
    raiz = hacer_web(
        tmp_path,
        {
            "js/app.js": aleatorio(500),
            "css/app.css": aleatorio(300),
            "index.html": aleatorio(200),
            "manifest.webmanifest": b"{}",
        },
    )
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 0


def test_total_excedido_falla(tmp_path, monkeypatch, capsys):
    raiz = hacer_web(
        tmp_path,
        {
            "js/app.js": aleatorio(3000),
            "css/app.css": aleatorio(2000),
            "index.html": b"<html></html>",
        },
    )
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_TOTAL_KB", 3)
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_ARCHIVO_KB", 50)
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 1
    salida = capsys.readouterr().out
    assert "supera el presupuesto de 3 KB" in salida
    assert "presupuesto_peso.py" in salida


def test_archivo_suelto_excede_su_tope(tmp_path, monkeypatch, capsys):
    raiz = hacer_web(
        tmp_path,
        {
            "js/enorme.js": aleatorio(5000),
            "index.html": b"<html></html>",
        },
    )
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_TOTAL_KB", 50)
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_ARCHIVO_KB", 4)
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 1
    salida = capsys.readouterr().out
    assert "web/js/enorme.js" in salida
    assert "tope por archivo de 4 KB" in salida


def test_informe_nunca_falla(tmp_path, monkeypatch, capsys):
    raiz = hacer_web(tmp_path, {"js/app.js": aleatorio(5000)})
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_TOTAL_KB", 1)
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_ARCHIVO_KB", 1)
    assert presupuesto_peso.main(["--raiz", str(raiz), "--informe"]) == 0
    assert "web/js/app.js" in capsys.readouterr().out


ROOT = Path(__file__).resolve().parents[1]


def test_web_real_con_cuatro_kb_de_holgura():
    """El total propio no vive al borde del presupuesto: deja 4 KB libres para
    que la próxima subida sea planificada y no un main en rojo (PESO-01)."""
    total = sum(f["gzip"] for f in presupuesto_peso.medir(ROOT / "web"))
    tope = (presupuesto_peso.PRESUPUESTO_TOTAL_KB - 4) * 1024
    assert total <= tope, f"el frontend propio mide {total / 1024:.1f} KB gzip y el tope con holgura es {tope / 1024:.0f} KB"


def test_umbral_documentado_en_paginas_md():
    """docs/PAGINAS.md nombra el presupuesto vigente, no un número viejo."""
    doc = (ROOT / "docs" / "PAGINAS.md").read_text(encoding="utf-8")
    assert f"{presupuesto_peso.PRESUPUESTO_TOTAL_KB} KB" in doc
