#!/usr/bin/env python3
"""Simulacro de restauración desde R2 (OPS-10): un respaldo que nunca se restauró no es un respaldo.

    python3 scripts/simulacro_restauracion.py [--dir CARPETA]

Baja los respaldos reales del bucket «brasa-chile-datos» con wrangler a una carpeta local y
verifica su integridad:

- db/brasa.db   → SQLite íntegro y con las tablas de las personas (lugares, alertas, reportes).
- db/work.db.gz → descomprime y verifica SQLite íntegro y las tablas principales de trabajo.

Pensado para correr una vez al mes: .github/workflows/simulacro-restauracion.yml lo hace solo
(día 3) y también a mano con «Run workflow».

Credenciales: las mismas del despliegue — CLOUDFLARE_API_TOKEN y CLOUDFLARE_ACCOUNT_ID en el
entorno, o una sesión abierta con `npx wrangler login`. wrangler se busca primero en
deploy/cloudflare/node_modules (corre `npm ci` ahí) y después en el PATH.
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUCKET = "brasa-chile-datos"
KEYS = ["db/brasa.db", "db/work.db.gz"]

# Las tablas que hacen útil cada respaldo: sin ellas restaurar es igual a partir de cero.
BRASA_TABLES = {"subscribers", "places", "alerts", "reports", "kv"}
WORK_TABLES = {"ingest_runs", "observations", "incidents", "risk_daily"}
BRASA_COUNTS = ["subscribers", "places", "reports", "alerts"]
WORK_COUNTS = ["observations", "ingest_runs", "incidents", "risk_daily"]


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
        sys.exit(f"✗ No se pudo bajar {key}: {detail[0]}\n"
                 "  ¿Credenciales? Exporta CLOUDFLARE_API_TOKEN y CLOUDFLARE_ACCOUNT_ID "
                 "(las del despliegue) o corre `npx wrangler login`.")


def check_db(path: Path, nombre: str, tables: set[str], counts: list[str]) -> list[str]:
    data = path.read_bytes()
    if not data.startswith(b"SQLite format 3"):
        return [f"✗ {nombre}: el archivo no es una base SQLite"]
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        problemas = []
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            problemas.append(f"✗ {nombre}: integrity_check dice «{ok}»")
        presentes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        faltantes = tables - presentes
        if faltantes:
            problemas.append(f"✗ {nombre}: faltan tablas {sorted(faltantes)}")
        lineas = []
        for tabla in counts:
            if tabla in presentes:
                lineas.append(f"{tabla}={conn.execute(f'SELECT COUNT(*) FROM {tabla}').fetchone()[0]}")
        if not problemas:
            lineas.insert(0, f"✓ {nombre}: íntegra ({path.stat().st_size / 1024:.0f} KB, {', '.join(lineas)})")
            return lineas
        return problemas
    except sqlite3.Error as exc:
        return [f"✗ {nombre}: no abre como SQLite ({exc})"]
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulacro de restauración de los respaldos R2 de BRASA.")
    parser.add_argument("--dir", type=Path, default=Path(tempfile.mkdtemp(prefix="brasa-restauracion-")),
                        help="carpeta donde bajar los respaldos (defecto: una temporal)")
    args = parser.parse_args()
    args.dir.mkdir(parents=True, exist_ok=True)

    print(f"» Bajando respaldos de r2://{BUCKET} a {args.dir}")
    for key in KEYS:
        dest = args.dir / key.split("/")[-1]
        fetch(key, dest)
        print(f"  · {key}: {dest.stat().st_size / 1024:.0f} KB")

    problemas = []
    brasa = args.dir / "brasa.db"
    print("» Verificando db/brasa.db (datos de las personas)")
    for linea in check_db(brasa, "brasa.db", BRASA_TABLES, BRASA_COUNTS):
        print(f"  {linea}")
        if linea.startswith("✗"):
            problemas.append(linea)

    print("» Verificando db/work.db.gz (observaciones e incidentes; se reconstruye, pero duele partir de cero)")
    try:
        work_bytes = gzip.decompress((args.dir / "work.db.gz").read_bytes())
        work = args.dir / "work.db"
        work.write_bytes(work_bytes)
        print(f"  · descomprimido: {len(work_bytes) / 1024:.0f} KB")
    except (OSError, EOFError) as exc:
        problemas.append(f"✗ work.db.gz: no descomprime ({exc})")
    else:
        for linea in check_db(work, "work.db", WORK_TABLES, WORK_COUNTS):
            print(f"  {linea}")
            if linea.startswith("✗"):
                problemas.append(linea)

    if problemas:
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
