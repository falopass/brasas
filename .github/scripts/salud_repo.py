"""Salud del propio repositorio (OPS-28): cada etapa de `dev.py check` por separado.

Corre las cinco etapas imitando cmd_check —ruff, pytest, presupuesto de peso, node --check
de cada web/**/*.js y node --test tests/js— sin abortar en la primera que falla. Imprime
una línea por etapa (OK / FALLÓ + duración) y, con --issue, abre o comenta el issue con
etiqueta «salud-repo»; si el informe sale todo OK y hay issue abierto, lo cierra.

    python .github/scripts/salud_repo.py --dry-run   # solo el plan, sale 0
    python .github/scripts/salud_repo.py             # corre las etapas
    python .github/scripts/salud_repo.py --issue     # corre y publica el informe en GitHub

Solo biblioteca estándar. Nunca imprime variables de entorno ni secretos.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOPE_S = 900  # cada etapa tiene su propio tope; una etapa colgada no mata el informe

ETAPAS = [
    ("ruff", ["ruff", "check", "backend", "tests"]),
    ("pytest", ["python", "-m", "pytest", "-q"]),
    ("presupuesto de peso", ["python", "scripts/local/presupuesto_peso.py"]),
    # node --check revisa un solo archivo por llamada: el -e recorre la lista y corta en el primero que falle.
    ("node --check", ["node", "-e", "const {execFileSync}=require('child_process');for(const f of process.argv.slice(1))execFileSync(process.execPath,['--check',f],{stdio:'inherit'})", *sorted(str(p) for p in ROOT.glob("web/**/*.js"))]),
    ("node --test", ["node", "--test", "tests/js"]),
]


def correr(etapas=ETAPAS, run=subprocess.run) -> list[dict]:
    """Corre cada etapa con su tope; devuelve un dict por etapa con estado y cola del log."""
    informe = []
    for nombre, cmd in etapas:
        t0 = time.perf_counter()
        try:
            r = run(cmd, capture_output=True, text=True, timeout=TOPE_S, cwd=ROOT)
            cola = (r.stdout + r.stderr).strip().splitlines()[-20:]
            informe.append({"etapa": nombre, "ok": r.returncode == 0,
                            "s": round(time.perf_counter() - t0, 1), "log": "\n".join(cola)})
        except subprocess.TimeoutExpired:
            informe.append({"etapa": nombre, "ok": False,
                            "s": float(TOPE_S), "log": f"superó el tope de {TOPE_S} s"})
    return informe


def fallidas(informe: list[dict]) -> list[str]:
    return [e["etapa"] for e in informe if not e["ok"]]


def cuerpo_issue(informe: list[dict], sha: str, run_url: str = "") -> str:
    filas = "\n".join(
        f"| {e['etapa']} | {'OK' if e['ok'] else 'FALLÓ'} | {e['s']} s |" for e in informe)
    colas = "\n\n".join(f"### {e['etapa']}\n\n```\n{e['log']}\n```" for e in informe if not e["ok"])
    return (f"## Salud del repo · `{sha}`\n\n"
            f"{'Corrida: ' + run_url + chr(10) + chr(10) if run_url else ''}"
            f"| Etapa | Resultado | Duración |\n|---|---|---|\n{filas}\n\n{colas}\n")


def decision(fallaron: list[str], issues_abiertos: list[dict]) -> str:
    """Qué hacer con el issue: crear, comentar, cerrar o nada."""
    if fallaron and not issues_abiertos:
        return "crear"
    if fallaron and issues_abiertos:
        return "comentar"
    if not fallaron and issues_abiertos:
        return "cerrar"
    return "nada"


def _gh(*args, run=subprocess.run) -> subprocess.CompletedProcess:
    return run(["gh", *args], capture_output=True, text=True, cwd=ROOT)


def publicar(informe: list[dict], sha: str, run_url: str) -> None:
    """Issue con etiqueta salud-repo según la decisión; errores de gh se informan, no abortan."""
    lista = _gh("issue", "list", "--label", "salud-repo", "--state", "open",
                "--json", "number", "--jq", ".[].number")
    abiertos = [{"number": int(n)} for n in lista.stdout.split()] if lista.returncode == 0 else []
    malas = fallidas(informe)
    accion = decision(malas, abiertos)
    with open("informe.md", "w", encoding="utf-8") as fh:
        fh.write(cuerpo_issue(informe, sha, run_url))
    titulo = f"Salud del repo: {len(malas)} etapa(s) en rojo ({sha[:7]})" if malas else ""
    if accion == "crear":
        r = _gh("issue", "create", "--label", "salud-repo", "--title", titulo, "--body-file", "informe.md")
    elif accion == "comentar":
        r = _gh("issue", "comment", str(abiertos[0]["number"]), "--body-file", "informe.md")
    elif accion == "cerrar":
        _gh("issue", "comment", str(abiertos[0]["number"]), "--body", "La corrida volvió en verde.")
        r = _gh("issue", "close", str(abiertos[0]["number"]))
    else:
        return
    if r.returncode != 0:
        print(f"::warning::gh devolvió {r.returncode} en la acción «{accion}» del issue")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--issue", action="store_true")
    args = ap.parse_args(argv)
    if args.dry_run:
        for nombre, _ in ETAPAS:
            print(f"· {nombre}")
        return 0
    informe = correr()
    for e in informe:
        print(f"{'OK' if e['ok'] else 'FALLÓ':6} {e['etapa']} ({e['s']} s)")
        if not e["ok"] and e["log"]:
            print("  " + "\n  ".join(e["log"].splitlines()[-20:]))
    if args.issue:
        import os
        sha = _gh("rev-parse", "main", "--short").stdout.strip() or os.environ.get("GITHUB_SHA", "desconocido")
        url = f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
        publicar(informe, sha, url)
    return 1 if fallidas(informe) else 0


if __name__ == "__main__":
    sys.exit(main())
