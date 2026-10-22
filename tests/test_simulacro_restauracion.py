"""OPS-10: simulacro de restauración por URL (scripts/local/simulacro_restauracion.py).

Sin red: los respaldos se sirven con URLs ``file://`` sobre SQLite mínimos en ``tmp_path``
y el informe se desvía a una ruta temporal para no tocar ``docs/SIMULACRO.md``.
"""

from __future__ import annotations

import gzip
import importlib.util
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "local" / "simulacro_restauracion.py"
_spec = importlib.util.spec_from_file_location("simulacro_restauracion_local", _SCRIPT)
simulacro = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = simulacro
_spec.loader.exec_module(simulacro)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def crear_respaldo(path: Path, observado: datetime | None = None) -> Path:
    """SQLite mínimo con las cuatro tablas que revisa el simulacro."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE observations (id TEXT PRIMARY KEY, observed_at TEXT NOT NULL);
        CREATE TABLE incidents (id TEXT PRIMARY KEY);
        CREATE TABLE places (id TEXT PRIMARY KEY);
        CREATE TABLE alerts (id TEXT PRIMARY KEY);
        """
    )
    if observado is not None:
        conn.executemany(
            "INSERT INTO observations VALUES (?, ?)",
            [("obs-1", iso(observado)), ("obs-2", iso(observado))],
        )
    conn.execute("INSERT INTO incidents VALUES ('inc-1')")
    conn.executemany("INSERT INTO places VALUES (?)", [("p1",), ("p2",), ("p3",)])
    conn.execute("INSERT INTO alerts VALUES ('a1')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def informe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    destino = tmp_path / "SIMULACRO.md"
    monkeypatch.setattr(simulacro, "INFORME", destino)
    monkeypatch.delenv("BRASA_BACKUP_URL", raising=False)
    return destino


def test_respaldo_integro_pasa_y_escribe_el_informe(tmp_path: Path, informe: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = crear_respaldo(tmp_path / "work.db", datetime.now(timezone.utc) - timedelta(hours=1))

    codigo = simulacro.main(["--url", db.as_uri(), "--max-edad-h", "24"])

    salida = capsys.readouterr().out
    assert codigo == 0
    assert "RESULTADO: superado" in salida
    texto = informe.read_text(encoding="utf-8")
    assert "Resultado: superado" in texto
    assert "| observations | 2 |" in texto
    assert "| incidents | 1 |" in texto
    assert "| places | 3 |" in texto
    assert "| alerts | 1 |" in texto
    assert "Integridad: ok" in texto
    assert "max(observed_at)" in texto


def test_respaldo_gz_se_descomprime(tmp_path: Path, informe: Path) -> None:
    db = crear_respaldo(tmp_path / "work.db", datetime.now(timezone.utc))
    comprimido = tmp_path / "work.db.gz"
    comprimido.write_bytes(gzip.compress(db.read_bytes()))

    codigo = simulacro.main(["--url", comprimido.as_uri()])

    assert codigo == 0
    texto = informe.read_text(encoding="utf-8")
    assert "| observations | 2 |" in texto
    assert "SQLite:" in texto


def test_respaldo_truncado_falla_con_mensaje_claro(tmp_path: Path, informe: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = crear_respaldo(tmp_path / "work.db", datetime.now(timezone.utc))
    roto = tmp_path / "roto.db"
    roto.write_bytes(db.read_bytes()[:1024])

    codigo = simulacro.main(["--url", roto.as_uri()])

    salida = capsys.readouterr().out
    assert codigo == 1
    assert "RESULTADO: fallido" in salida
    assert "dañado o truncado" in salida
    assert "Resultado: fallido" in informe.read_text(encoding="utf-8")


def test_entrada_que_no_es_un_respaldo_falla(tmp_path: Path, informe: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ajeno = tmp_path / "ajeno.db"
    conn = sqlite3.connect(ajeno)
    conn.execute("CREATE TABLE otra (x)")
    conn.commit()
    conn.close()
    no_gzip = tmp_path / "work.db.gz"
    no_gzip.write_bytes(b"esto no es gzip")

    for archivo, mensaje in ((ajeno, "tablas de BRASA"), (no_gzip, "no descomprime")):
        assert simulacro.main(["--url", archivo.as_uri()]) == 1
        assert mensaje in capsys.readouterr().out
    assert "Resultado: fallido" in informe.read_text(encoding="utf-8")


def test_sin_url_no_toca_nada_y_explica_el_uso(informe: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def prohibido(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("sin URL no debe abrir conexiones")

    monkeypatch.setattr(urllib.request, "urlopen", prohibido)

    codigo = simulacro.main([])

    salida = capsys.readouterr().out
    assert codigo == 0
    assert "--url" in salida
    assert "BRASA_BACKUP_URL" in salida
    assert not informe.exists()


@pytest.mark.parametrize("desde_entorno", [False, True], ids=["ruta-local", "entorno"])
def test_toma_la_url_del_argumento_o_del_entorno(
    tmp_path: Path, informe: Path, monkeypatch: pytest.MonkeyPatch, desde_entorno: bool
) -> None:
    db = crear_respaldo(tmp_path / "work.db", datetime.now(timezone.utc))
    if desde_entorno:
        monkeypatch.setenv("BRASA_BACKUP_URL", db.as_uri())
        codigo = simulacro.main([])
    else:
        codigo = simulacro.main(["--url", str(db)])

    assert codigo == 0
    assert informe.exists()


def test_dato_mas_viejo_que_el_maximo_falla(tmp_path: Path, informe: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = crear_respaldo(tmp_path / "work.db", datetime.now(timezone.utc) - timedelta(hours=30))

    codigo = simulacro.main(["--url", db.as_uri(), "--max-edad-h", "24"])

    salida = capsys.readouterr().out
    assert codigo == 1
    assert "frescura" in salida
    assert "30" in salida and "24" in salida
    assert "Resultado: fallido" in informe.read_text(encoding="utf-8")


def test_url_visible_oculta_credenciales() -> None:
    visible = simulacro.url_visible("https://usuario:clave@ejemplo.test/ruta.db?token=abc#parte")

    assert visible == "https://ejemplo.test/ruta.db"
    assert "clave" not in visible
    assert "token" not in visible
