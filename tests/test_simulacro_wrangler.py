"""OPS-47: simulacro de restauración que corre en CI (scripts/simulacro_restauracion.py).

Sin red ni credenciales: ``wrangler_cmd`` se reemplaza por un ``wrangler`` falso
(un script Python en ``tmp_path``) que copia los «respaldos» desde una carpeta que
hace de bucket R2. Los SQLite se crean de verdad; el informe se desvía con
``--informe`` para no tocar ``docs/SIMULACRO.md``.
"""

from __future__ import annotations

import gzip
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "simulacro_restauracion.py"
_spec = importlib.util.spec_from_file_location("simulacro_restauracion_wrangler", _SCRIPT)
simulacro = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = simulacro
_spec.loader.exec_module(simulacro)

_WRANGLER_FALSO = """\
import os
import shutil
import sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["BRASA_FAKE_LLAMADAS"], "a") as registro:
    registro.write(" ".join(args) + "\\n")
key = args[3].split("/", 1)[1]  # brasa-chile-datos/db/brasa.db -> db/brasa.db
dest = Path(args[args.index("--file") + 1])
src = Path(os.environ["BRASA_FAKE_R2"]) / key
if not src.exists():
    print(f"no existe {key} en el bucket falso", file=sys.stderr)
    sys.exit(1)
shutil.copyfile(src, dest)
"""


def crear_brasa(path: Path) -> Path:
    """SQLite mínimo con las tablas de las personas que revisa el simulacro."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE subscribers (id TEXT PRIMARY KEY);
        CREATE TABLE places (id TEXT PRIMARY KEY);
        CREATE TABLE alerts (id TEXT PRIMARY KEY);
        CREATE TABLE reports (id TEXT PRIMARY KEY);
        CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT);
        """
    )
    conn.executemany("INSERT INTO subscribers VALUES (?)", [("s1",), ("s2",)])
    conn.executemany("INSERT INTO places VALUES (?)", [("p1",), ("p2",), ("p3",)])
    conn.execute("INSERT INTO alerts VALUES ('a1')")
    conn.execute("INSERT INTO reports VALUES ('r1')")
    conn.execute("INSERT INTO kv VALUES ('k1', 'v1')")
    conn.commit()
    conn.close()
    return path


def crear_work(path: Path) -> Path:
    """SQLite mínimo con las tablas de trabajo que revisa el simulacro."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE ingest_runs (id TEXT PRIMARY KEY);
        CREATE TABLE observations (id TEXT PRIMARY KEY);
        CREATE TABLE incidents (id TEXT PRIMARY KEY);
        CREATE TABLE risk_daily (id TEXT PRIMARY KEY);
        """
    )
    conn.execute("INSERT INTO ingest_runs VALUES ('i1')")
    conn.executemany("INSERT INTO observations VALUES (?)", [("o1",), ("o2",)])
    conn.execute("INSERT INTO incidents VALUES ('n1')")
    conn.execute("INSERT INTO risk_daily VALUES ('d1')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def r2_falso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Bucket R2 falso + wrangler falso; devuelve (carpeta del bucket, registro de llamadas)."""
    bucket = tmp_path / "r2"
    (bucket / "db").mkdir(parents=True)
    wrangler = tmp_path / "wrangler_falso.py"
    wrangler.write_text(_WRANGLER_FALSO, encoding="utf-8")
    llamadas = tmp_path / "llamadas_wrangler.txt"
    monkeypatch.setenv("BRASA_FAKE_R2", str(bucket))
    monkeypatch.setenv("BRASA_FAKE_LLAMADAS", str(llamadas))
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-de-prueba")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "cuenta-de-prueba")
    monkeypatch.setattr(simulacro, "wrangler_cmd", lambda: [sys.executable, str(wrangler)])
    return bucket, llamadas


def poblar_bucket(bucket: Path, brasa: bytes | None = None, work_gz: bytes | None = None) -> None:
    if brasa is not None:
        (bucket / "db" / "brasa.db").write_bytes(brasa)
    if work_gz is not None:
        (bucket / "db" / "work.db.gz").write_bytes(work_gz)


def test_base_integra_pasa_y_escribe_el_informe(r2_falso: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bucket, _ = r2_falso
    brasa = crear_brasa(tmp_path / "brasa_src.db")
    work = crear_work(tmp_path / "work_src.db")
    poblar_bucket(bucket, brasa.read_bytes(), gzip.compress(work.read_bytes()))
    informe = tmp_path / "SIMULACRO.md"

    codigo = simulacro.main(["--dir", str(tmp_path / "descarga"), "--informe", str(informe)])

    salida = capsys.readouterr().out
    assert codigo == 0
    assert "Simulacro superado" in salida
    texto = informe.read_text(encoding="utf-8")
    assert "## brasa.db" in texto
    assert "## work.db" in texto
    assert "Integridad: ok" in texto
    assert "| places | 3 |" in texto
    assert "| subscribers | 2 |" in texto
    assert "| observations | 2 |" in texto
    assert "**Resultado: superado**" in texto


def test_brasa_truncada_falla_con_mensaje_en_palabras(
    r2_falso: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bucket, _ = r2_falso
    brasa = crear_brasa(tmp_path / "brasa_src.db")
    work = crear_work(tmp_path / "work_src.db")
    poblar_bucket(bucket, brasa.read_bytes()[:1024], gzip.compress(work.read_bytes()))
    informe = tmp_path / "SIMULACRO.md"

    codigo = simulacro.main(["--dir", str(tmp_path / "descarga"), "--informe", str(informe)])

    captura = capsys.readouterr()
    assert codigo == 1
    assert "simulacro FALLÓ" in captura.out
    assert "dañado o truncado" in captura.out
    assert "Traceback" not in captura.out
    assert captura.err == ""
    texto = informe.read_text(encoding="utf-8")
    assert "dañado o truncado" in texto
    assert "**Resultado: fallido**" in texto


def test_work_gz_corrupto_no_tumba_el_informe_de_brasa(
    r2_falso: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bucket, _ = r2_falso
    brasa = crear_brasa(tmp_path / "brasa_src.db")
    poblar_bucket(bucket, brasa.read_bytes(), b"esto no es gzip")
    informe = tmp_path / "SIMULACRO.md"

    codigo = simulacro.main(["--dir", str(tmp_path / "descarga"), "--informe", str(informe)])

    salida = capsys.readouterr().out
    assert codigo == 1
    assert "no descomprime" in salida
    texto = informe.read_text(encoding="utf-8")
    assert "## brasa.db" in texto
    assert "Integridad: ok" in texto
    assert "| places | 3 |" in texto
    assert "no descomprime" in texto
    assert "**Resultado: fallido**" in texto


def test_sin_api_token_explica_el_secreto_y_no_llama_a_wrangler(
    r2_falso: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, llamadas = r2_falso
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")

    def prohibido() -> list[str]:
        raise AssertionError("sin CLOUDFLARE_API_TOKEN no debe llamarse a wrangler")

    monkeypatch.setattr(simulacro, "wrangler_cmd", prohibido)

    codigo = simulacro.main(["--dir", str(tmp_path / "descarga"), "--informe", str(tmp_path / "SIMULACRO.md")])

    salida = capsys.readouterr().out
    assert codigo == 1
    assert "CLOUDFLARE_API_TOKEN" in salida
    assert not llamadas.exists()
    assert not (tmp_path / "descarga" / "brasa.db").exists()
