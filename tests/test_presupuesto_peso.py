"""Presupuesto de peso del frontend (UX-33): umbrales sobre proyectos temporales.

Ninguna prueba toca el web/ real: cada una arma su propio proyecto en tmp_path
y ajusta los umbrales con monkeypatch para no depender de los números del repo.
El contenido aleatorio (randbytes con semilla) no comprime, así los tamaños
gzip son estables.
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
    raiz = hacer_web(tmp_path, {
        "js/app.js": aleatorio(500),
        "css/app.css": aleatorio(300),
        "index.html": aleatorio(200),
        "manifest.webmanifest": b"{}",
    })
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 0


def test_total_excedido_falla(tmp_path, monkeypatch, capsys):
    raiz = hacer_web(tmp_path, {
        "js/app.js": aleatorio(3000),
        "css/app.css": aleatorio(2000),
        "index.html": b"<html></html>",
    })
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_TOTAL_KB", 3)
    monkeypatch.setattr(presupuesto_peso, "PRESUPUESTO_ARCHIVO_KB", 50)
    assert presupuesto_peso.main(["--raiz", str(raiz)]) == 1
    salida = capsys.readouterr().out
    assert "supera el presupuesto de 3 KB" in salida
    assert "presupuesto_peso.py" in salida


def test_archivo_suelto_excede_su_tope(tmp_path, monkeypatch, capsys):
    raiz = hacer_web(tmp_path, {
        "js/enorme.js": aleatorio(5000),
        "index.html": b"<html></html>",
    })
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
