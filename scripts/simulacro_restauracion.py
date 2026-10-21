#!/usr/bin/env python3
"""Simulacro de restauración desde R2 (OPS-10): un respaldo que nunca se restauró no es un respaldo.

    python3 scripts/simulacro_restauracion.py [--dir CARPETA] [--informe RUTA]

ESTE es el simulacro que corre en CI: .github/workflows/simulacro-restauracion.yml lo ejecuta
solo el día 3 de cada mes (y a mano con «Run workflow»). La versión de escritorio, que baja el
respaldo por URL, es scripts/local/simulacro_restauracion.py: mismo nombre, otro contrato.

Baja los respaldos reales del bucket «brasa-chile-datos» con wrangler a una carpeta local y
verifica su integridad:

- db/brasa.db   → SQLite íntegro y con las tablas de las personas (lugares, alertas, reportes).
- db/work.db.gz → descomprime y verifica SQLite íntegro y las tablas principales de trabajo.

Al terminar escribe un informe en docs/SIMULACRO.md (se cambia con --informe) para que la
corrida mensual deje constancia.

Credenciales: las mismas del despliegue — CLOUDFLARE_API_TOKEN y CLOUDFLARE_ACCOUNT_ID en el
entorno (en CI viven en Settings → Secrets and variables → Actions). Si falta alguna, el
script lo dice y termina sin llamar a wrangler. wrangler se busca primero en
deploy/cloudflare/node_modules (corre `npm ci` ahí) y después en el PATH.
"""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFORME = ROOT / "docs" / "SIMULACRO.md"
BUCKET = "brasa-chile-datos"
KEYS = ["db/brasa.db", "db/work.db.gz"]
SECRETOS = ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]

# Las tablas que hacen útil cada respaldo: sin ellas restaurar es igual a partir de cero.
BRASA_TABLES = {"subscribers", "places", "alerts", "reports", "kv"}
WORK_TABLES = {"ingest_runs", "observations", "incidents", "risk_daily"}
BRASA_COUNTS = ["subscribers", "places", "reports", "alerts"]
WORK_COUNTS = ["observations", "ingest_runs", "incidents", "risk_daily"]


@dataclass
class Revision:
    nombre: str
    bytes_descargados: int = 0
    bytes_sqlite: int = 0
    integridad: str = "no verificada"
    tablas: dict[str, int | None] = field(default_factory=dict)
    problemas: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problemas


def wrangler_cmd() -> list[str]:
    local = ROOT / "deploy" / "cloudflare" / "node_modules" / ".bin" / "wrangler"
    if local.exists():
        return [str(local)]
    found = shutil.which("wrangler")
    if found:
        return [found]
    sys.exit("✗ No se encontró wrangler: corre `npm ci` en deploy/cloudflare o instala wrangler.")


def fetch(key: str, dest: Path) -> None:
    cmd = wrangler_cmd() + ["r2", "object", "get", f"{BUCKET}/{key}", "--remote", "--file", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        detail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["sin detalle"]
        sys.exit(
            f"✗ No se pudo bajar {key}: {detail[0]}\n"
            "  ¿Credenciales? Exporta CLOUDFLARE_API_TOKEN y CLOUDFLARE_ACCOUNT_ID "
            "(las del despliegue)."
        )


def verificar(path: Path, nombre: str, tables: set[str], counts: list[str]) -> Revision:
    revision = Revision(nombre, path.stat().st_size, path.stat().st_size, tablas={tabla: None for tabla in counts})
    data = path.read_bytes()
    if not data.startswith(b"SQLite format 3"):
        revision.problemas.append(f"{nombre}: el archivo no es una base SQLite")
        return revision
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        revision.problemas.append(f"{nombre}: no abre como SQLite ({exc})")
        return revision
    try:
        try:
            revision.integridad = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            revision.problemas.append(f"{nombre}: el SQLite está dañado o truncado ({exc})")
            return revision
        if revision.integridad != "ok":
            revision.problemas.append(f"{nombre}: integrity_check dice «{revision.integridad}»")
        presentes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        faltantes = tables - presentes
        if faltantes:
            revision.problemas.append(f"{nombre}: faltan tablas {sorted(faltantes)}")
        for tabla in counts:
            if tabla in presentes:
                revision.tablas[tabla] = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
    except sqlite3.Error as exc:
        revision.problemas.append(f"{nombre}: no abre como SQLite ({exc})")
    finally:
        conn.close()
    return revision


def _tamano(bytes_: int) -> str:
    if bytes_ >= 1024 * 1024:
        return f"{bytes_ / (1024 * 1024):.1f} MB"
    return f"{bytes_ / 1024:.0f} KB"


def imprimir(revision: Revision) -> None:
    if revision.ok:
        conteo = ", ".join(f"{tabla}={filas}" for tabla, filas in revision.tablas.items() if filas is not None)
        print(f"  ✓ {revision.nombre}: íntegra ({_tamano(revision.bytes_sqlite)}, {conteo})")
    for problema in revision.problemas:
        print(f"  ✗ {problema}")


def escribir_informe(revisiones: list[Revision], destino: Path, ahora: datetime) -> None:
    ok = all(r.ok for r in revisiones)
    lineas = [
        "# Simulacro de restauración",
        "",
        f"- Fecha: {ahora.strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Origen: r2://{BUCKET} ({', '.join(KEYS)})",
        "",
    ]
    for revision in revisiones:
        lineas.append(f"## {revision.nombre}")
        lineas.append("")
        lineas.append(f"- Descargado: {_tamano(revision.bytes_descargados)}")
        lineas.append(f"- SQLite: {_tamano(revision.bytes_sqlite)}")
        lineas.append(f"- Integridad: {revision.integridad}")
        if revision.tablas:
            lineas.extend(["", "| Tabla | Filas |", "|---|---:|"])
            for tabla, filas in revision.tablas.items():
                lineas.append(f"| {tabla} | {'—' if filas is None else filas} |")
        if revision.problemas:
            lineas.append("")
            lineas.extend(f"- ✗ {problema}" for problema in revision.problemas)
        lineas.append("")
    lineas.append(f"**Resultado: {'superado' if ok else 'fallido'}**")
    lineas.append("")
    lineas.append("Generado por `scripts/simulacro_restauracion.py` (el simulacro que corre en CI).")
    lineas.append("")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulacro de restauración de los respaldos R2 de BRASA (el que corre en CI).")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(tempfile.mkdtemp(prefix="brasa-restauracion-")),
        help="carpeta donde bajar los respaldos (defecto: una temporal)",
    )
    parser.add_argument("--informe", type=Path, default=INFORME, help="dónde escribir el informe (defecto: docs/SIMULACRO.md)")
    args = parser.parse_args(argv)

    faltantes = [nombre for nombre in SECRETOS if not os.environ.get(nombre)]
    if faltantes:
        print("✗ Faltan secretos en el entorno: " + ", ".join(faltantes))
        print("  Son los mismos del despliegue. En CI viven en Settings → Secrets and variables")
        print("  → Actions; en local hay que exportarlos antes. Sin ellos wrangler no llega a R2.")
        return 1

    args.dir.mkdir(parents=True, exist_ok=True)
    print(f"» Bajando respaldos de r2://{BUCKET} a {args.dir}")
    for key in KEYS:
        dest = args.dir / key.split("/")[-1]
        fetch(key, dest)
        print(f"  · {key}: {dest.stat().st_size / 1024:.0f} KB")

    revisiones: list[Revision] = []
    print("» Verificando db/brasa.db (datos de las personas)")
    brasa = verificar(args.dir / "brasa.db", "brasa.db", BRASA_TABLES, BRASA_COUNTS)
    revisiones.append(brasa)
    imprimir(brasa)

    print("» Verificando db/work.db.gz (observaciones e incidentes; se reconstruye, pero duele partir de cero)")
    try:
        work_bytes = gzip.decompress((args.dir / "work.db.gz").read_bytes())
        work = args.dir / "work.db"
        work.write_bytes(work_bytes)
        print(f"  · descomprimido: {len(work_bytes) / 1024:.0f} KB")
    except (OSError, EOFError) as exc:
        revision = Revision("work.db.gz", (args.dir / "work.db.gz").stat().st_size, 0, problemas=[f"work.db.gz: no descomprime ({exc})"])
        revisiones.append(revision)
        imprimir(revision)
    else:
        revision = verificar(work, "work.db", WORK_TABLES, WORK_COUNTS)
        revision.bytes_descargados = (args.dir / "work.db.gz").stat().st_size
        revisiones.append(revision)
        imprimir(revision)

    ahora = datetime.now(timezone.utc)
    try:
        escribir_informe(revisiones, args.informe, ahora)
        print(f"  Informe: {args.informe}")
    except OSError as exc:
        print(f"  ✗ No se pudo escribir el informe en {args.informe}: {exc}")
        return 1

    if not all(r.ok for r in revisiones):
        print("\n✗ El simulacro FALLÓ. Un respaldo malo hay que tratarlo como si no existiera:")
        print("  1. Revisa el último ciclo: /api/status → last_cycle.backup y work_backup.")
        print("  2. Para brasa.db hay copia diaria: en R2 copia db/diario/AAAA-MM-DD.db sobre db/brasa.db")
        print("     y reinicia el contenedor (un despliegue lo hace).")
        print("  3. work.db se reconstruye con la ingesta; si el .gz está malo bórralo para que el")
        print("     contenedor no lo restaure en el próximo arranque.")
        return 1
    print("\n✓ Simulacro superado: ambos respaldos descargan, abren y están íntegros.")
    print("  Nada se escribió en R2; las copias locales quedaron en", args.dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
