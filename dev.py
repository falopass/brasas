#!/usr/bin/env python3
"""Tareas de desarrollo local de BRASA Chile (Windows, macOS y Linux, sin dependencias extra).

    python dev.py setup [--e2e]     crea .venv, instala dependencias y copia .env.example → .env
    python dev.py run [--port 8000] [--demo] [--no-reload]
                                    servidor con recarga automática (--demo: datos de ejemplo, sin ingesta)
    python dev.py seed              carga datos de ejemplo en data/demo (incidente, CONAF, Botón Rojo)
    python dev.py test [args]       pruebas (pytest); los argumentos extra pasan a pytest
    python dev.py check             pruebas + sintaxis JS + reglas de diseño + paleta (lo mismo que el CI)
    python dev.py e2e [--url URL]   revisión en navegador: errores, CSP y textos cortados (requiere setup --e2e)
    python dev.py clean             borra cachés y la base de demostración (no toca data/brasa.db)

Todo corre con el Python de .venv; `setup` es lo único que usa el Python del sistema.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
DEMO_DIR = ROOT / "data" / "demo"
LINT = ROOT / ".claude" / "skills" / "design-taste-frontend" / "scripts" / "lint.mjs"
PALETTE = ROOT / "scripts" / "local" / "validate_palette.mjs"


def say(text: str) -> None:
    print(f"\033[1m» {text}\033[0m" if sys.stdout.isatty() else f"» {text}", flush=True)


def run(cmd: list[str], env: dict[str, str] | None = None, check: bool = True) -> int:
    code = subprocess.call(cmd, cwd=ROOT, env={**os.environ, **(env or {})})
    if check and code:
        sys.exit(code)
    return code


def need_venv() -> None:
    if not PY.exists():
        sys.exit("No existe .venv. Ejecuta primero:  python dev.py setup")


def cmd_setup(args: argparse.Namespace) -> None:
    if sys.version_info < (3, 12):
        sys.exit("Se necesita Python 3.12 o superior.")
    if not PY.exists():
        say("Creando entorno en .venv")
        run([sys.executable, "-m", "venv", str(VENV)])
    reqs = "requirements-e2e.txt" if args.e2e else "requirements-dev.txt"
    say(f"Instalando {reqs}")
    run([str(PY), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", reqs])
    if args.e2e:
        say("Descargando Chromium para Playwright")
        run([str(PY), "-m", "playwright", "install", "chromium"])
    env_file = ROOT / ".env"
    if not env_file.exists():
        shutil.copy(ROOT / ".env.example", env_file)
        say("Creado .env a partir de .env.example (agrega tu FIRMS_MAP_KEY si tienes una)")
    if not shutil.which("node"):
        print("  Aviso: no se encontró Node.js. Es opcional, pero `check` lo usa para revisar el JavaScript.")
    install_pre_commit_hook()
    say("Listo. Siguiente paso:  python dev.py run   (o  python dev.py run --demo)")


def install_pre_commit_hook() -> None:
    """Instala .git/hooks/pre-commit (corre `dev.py check`); nunca pisa un gancho existente."""
    code = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"], cwd=ROOT, capture_output=True, text=True
    )
    if code.returncode or not code.stdout.strip():
        print("  Aviso: no se pudo ubicar el directorio de ganchos de git; sin gancho pre-commit.")
        return
    hooks_dir = Path(code.stdout.strip())
    if not hooks_dir.is_absolute():
        hooks_dir = ROOT / hooks_dir
    hook = hooks_dir / "pre-commit"
    if hook.exists():
        print(f"  Aviso: ya existe {hook}; no lo toqué.")
        return
    hooks_dir.mkdir(parents=True, exist_ok=True)
    # En worktrees los ganchos son compartidos: el gancho corre contra el worktree que
    # commitea (git ya lo ejecuta con cwd en su raíz), no contra el que lo instaló.
    py_rel = ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
    hook.write_text(
        "#!/bin/sh\n"
        "# Instalado por `python dev.py setup` (BRASA Chile). Corre `dev.py check` antes de cada commit.\n"
        "# Para desactivarlo: borra este archivo (o usa `git commit --no-verify` en un commit puntual).\n"
        'cd "$(git rev-parse --show-toplevel)" || exit 1\n'
        f'"{py_rel}" dev.py check || exit 1\n'
    )
    hook.chmod(hook.stat().st_mode | 0o111)
    say(f"Gancho pre-commit instalado en {hook} (corre `dev.py check` antes de cada commit)")


def cmd_run(args: argparse.Namespace) -> None:
    need_venv()
    env: dict[str, str] = {}
    if args.demo:
        if not (DEMO_DIR / "brasa.db").exists():
            cmd_seed(args)
        # Datos de ejemplo congelados: sin ingesta automática para que no se mezclen con datos reales.
        env.update({"BRASA_DATA_DIR": str(DEMO_DIR), "BRASA_SCHEDULER": "0", "ADMIN_TOKEN": os.getenv("ADMIN_TOKEN") or "demo-admin-token-local"})
        say(f"Modo demostración: datos en {DEMO_DIR} · /admin con el token «{env['ADMIN_TOKEN']}»")
    cmd = [str(PY), "-m", "uvicorn", "backend.main:app", "--host", args.host, "--port", str(args.port)]
    if not args.no_reload:
        cmd += ["--reload", "--reload-dir", "backend"]
    say(f"BRASA Chile en http://{args.host}:{args.port}  (Ctrl+C para salir)")
    run(cmd, env=env, check=False)


def cmd_seed(args: argparse.Namespace) -> None:
    need_venv()
    say(f"Cargando datos de ejemplo en {DEMO_DIR}")
    run([str(PY), "scripts/local/seed_demo.py", str(DEMO_DIR)], env={"BRASA_SCHEDULER": "0"})


def cmd_test(args: argparse.Namespace, extra: list[str]) -> None:
    need_venv()
    run([str(PY), "-m", "pytest", "-q", *extra], env={"BRASA_SCHEDULER": "0"})


def cmd_check(args: argparse.Namespace) -> None:
    need_venv()
    if subprocess.call([str(PY), "-c", "import ruff"], cwd=ROOT, stderr=subprocess.DEVNULL):
        print("  Sin ruff: se omite el lint de Python (instálalo con: pip install -r requirements-dev.txt).")
    else:
        say("Lint Python (ruff)")
        run([str(PY), "-m", "ruff", "check", "backend", "tests"])
    say("Pruebas")
    run([str(PY), "-m", "pytest", "-q"], env={"BRASA_SCHEDULER": "0"})
    say("Presupuesto de peso del frontend")
    run([str(PY), "scripts/local/presupuesto_peso.py"])
    run([str(PY), "scripts/local/peso_arranque.py"])
    node = shutil.which("node")
    if not node:
        print("  Sin Node.js: se omiten la sintaxis JS, las reglas de diseño y la paleta.")
        return
    say("Sintaxis JavaScript")
    files = sorted((ROOT / "web").rglob("*.js"))
    bad = [f for f in files if subprocess.call([node, "--check", str(f)], cwd=ROOT) != 0]
    if bad:
        sys.exit(f"Errores de sintaxis en: {', '.join(str(b.relative_to(ROOT)) for b in bad)}")
    print(f"  {len(files)} archivos sin errores")
    say("Pruebas JavaScript")
    run([node, "--test", "tests/js"])
    if LINT.exists():
        say("Reglas de diseño (design-taste-frontend)")
        run([node, str(LINT), "web/index.html", "web/admin.html", "web/css/app.css", "web/js"])
    if PALETTE.exists():
        say("Paleta apta para daltonismo")
        run([node, str(PALETTE)])
    else:
        print("  Sin scripts/local/validate_palette.mjs: se omite la paleta.")
    say("Todo en orden")


def cmd_e2e(args: argparse.Namespace) -> None:
    need_venv()
    code = subprocess.call([str(PY), "-c", "import playwright"], cwd=ROOT, stderr=subprocess.DEVNULL)
    if code:
        sys.exit("Falta Playwright. Ejecuta:  python dev.py setup --e2e")
    run([str(PY), "scripts/local/browser_checks.py", "--url", args.url, "--out", str(ROOT / "data" / "shots")])


def cmd_clean(args: argparse.Namespace) -> None:
    for path in [DEMO_DIR, ROOT / "data" / "shots", ROOT / ".pytest_cache"]:
        shutil.rmtree(path, ignore_errors=True)
    for cache in ROOT.rglob("__pycache__"):
        if ".venv" not in cache.parts:
            shutil.rmtree(cache, ignore_errors=True)
    say("Limpio (data/brasa.db y data/work.db se conservan)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup", help="crea .venv e instala dependencias")
    p.add_argument("--e2e", action="store_true", help="también Playwright y Chromium para `e2e`")
    p = sub.add_parser("run", help="servidor local con recarga")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--demo", action="store_true", help="datos de ejemplo en data/demo, sin ingesta")
    p.add_argument("--no-reload", action="store_true")
    sub.add_parser("seed", help="datos de ejemplo en data/demo")
    sub.add_parser("test", help="pytest (argumentos extra pasan a pytest)")
    sub.add_parser("check", help="pruebas + JS + reglas de diseño + paleta")
    p = sub.add_parser("e2e", help="revisión en navegador")
    p.add_argument("--url", default="http://127.0.0.1:8000")
    sub.add_parser("clean", help="borra cachés y la base de demostración")
    args, extra = parser.parse_known_args()
    if args.cmd == "test":
        cmd_test(args, extra)
    elif extra:
        parser.error(f"argumentos desconocidos: {' '.join(extra)}")
    else:
        {"setup": cmd_setup, "run": cmd_run, "seed": cmd_seed, "check": cmd_check, "e2e": cmd_e2e, "clean": cmd_clean}[args.cmd](args)


if __name__ == "__main__":
    main()
