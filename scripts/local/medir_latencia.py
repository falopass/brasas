"""Presupuesto de tiempo de las páginas públicas (UX-15, la mitad que faltaba).

`presupuesto_peso.py` vigila cuántos KB baja un vecino; este script vigila
cuánto tarda. Recorre las páginas públicas de `web/` y las rutas públicas de
la API con peticiones GET, repite cada una `--repeticiones` veces (por
defecto 3) y resume p50, p95 y máximo en milisegundos. Si el p95 de una ruta
supera `--umbral-ms` (por defecto 2500) o la ruta no respondió en ningún
intento, sale con 1 —la señal que usa `.github/workflows/experiencia.yml`
para abrir o actualizar el issue «monitoreo»—.

Solo hace GET: contra producción es una sonda, no escribe nada. `--dry-run`
no toca la red: lee las muestras de `--desde`, un JSON `{"ruta": [ms, ...]}`
o la salida de `--json` de una corrida anterior (mismo formato por ruta).

    python scripts/local/medir_latencia.py                        # producción
    python scripts/local/medir_latencia.py --url http://127.0.0.1:8000 --repeticiones 5
    python scripts/local/medir_latencia.py --json latencia.json   # guarda la medición
    python scripts/local/medir_latencia.py --dry-run --desde tests/data/latencia_muestra.json

Imprime el informe en markdown por stdout (el workflow lo redirige a
`latencia.md`, que sirve de resumen del job y de cuerpo del issue) y, con
GITHUB_OUTPUT en el entorno, deja `alerta` y `titulo` —el mismo convenio de
.github/scripts/monitoreo.py— con la ruta más lenta.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

URL_DEFECTO = "https://brasa-chile.ddiegosebastianbb.workers.dev"
UA = {"User-Agent": "BRASA-Chile medir-latencia (+https://github.com/falopass/brasas)"}
TIMEOUT_S = 15
MAX_BYTES = 8_000_000
UMBRAL_MS = 2500.0
REPETICIONES = 3

# Las páginas públicas (SPA + hojas bajo /web/, la misma lista de páginas
# estáticas de browser_checks.py) y las rutas públicas de la API que pide la
# app al abrirse (las de la sonda smoke_produccion.py más /api/config y el
# riesgo de la comuna de referencia 5801). Sin /i/<id> ni /og/...: piden un
# incidente abierto.
RUTAS = [
    "/",
    "/web/lite.html",
    "/web/pantalla.html?comuna=5801",
    "/web/lista.html",
    "/web/respuesta.html",
    "/web/plan.html",
    "/web/datos.html",
    "/web/sitemap.xml",
    "/api/health",
    "/api/config",
    "/api/status",
    "/api/risk/5801",
    "/api/incidents",
    "/api/observations?bbox=-75,-56,-66,-17",
    "/api/panorama",
]


def percentil(muestras: list[float], p: float) -> float | None:
    """Percentil por rango más cercano: p95 de [a, b, c] es el mayor de los tres.

    None si no hay muestras (la ruta no respondió en ningún intento).
    """
    if not muestras:
        return None
    ordenadas = sorted(muestras)
    return ordenadas[min(math.ceil(len(ordenadas) * p / 100) - 1, len(ordenadas) - 1)]


def medir(
    base: str,
    rutas: list[str],
    repeticiones: int,
    opener: Callable = urllib.request.urlopen,
    reloj: Callable[[], float] = time.monotonic,
) -> list[dict]:
    """GET por ruta, `repeticiones` veces: {ruta, muestras (ms), fallos, error}.

    Los intentos fallidos no aportan muestra pero quedan contados en `fallos`;
    `error` conserva el último motivo. Una ruta que responde a veces no se
    descarta: su p95 se calcula con las respuestas que llegaron.
    """
    filas = []
    for ruta in rutas:
        muestras: list[float] = []
        error = None
        for _ in range(repeticiones):
            inicio = reloj()
            try:
                with opener(urllib.request.Request(base + ruta, headers=UA), timeout=TIMEOUT_S) as r:
                    r.read(MAX_BYTES)
                muestras.append((reloj() - inicio) * 1000)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
        filas.append({"ruta": ruta, "muestras": muestras, "fallos": repeticiones - len(muestras), "error": error})
    return filas


def resumen(filas: list[dict], umbral_ms: float) -> list[dict]:
    """Agrega n, p50, p95, máx y las marcas `lenta` (p95 sobre el umbral) y
    `caida` (ninguna muestra). Sobre `filas` de `medir` o de `leer_desde`."""
    salida = []
    for f in filas:
        muestras = [float(m) for m in f.get("muestras") or []]
        p95 = percentil(muestras, 95)
        salida.append(
            {
                "ruta": f["ruta"],
                "n": len(muestras),
                "fallos": int(f.get("fallos") or 0),
                "error": f.get("error"),
                "p50": percentil(muestras, 50),
                "p95": p95,
                "max": max(muestras) if muestras else None,
                "lenta": p95 is not None and p95 > umbral_ms,
                "caida": not muestras,
            }
        )
    return salida


def veredicto(filas: list[dict], umbral_ms: float) -> tuple[int, str | None]:
    """(código de salida, título de issue): 1 si hay ruta lenta o caída.

    El título nombra la peor ruta: la caída pesa más que cualquier p95.
    """
    malas = [f for f in filas if f["lenta"] or f["caida"]]
    if not malas:
        return 0, None
    peor = max(malas, key=lambda f: f["p95"] if f["p95"] is not None else float("inf"))
    if peor["p95"] is None:
        return 1, f"[latencia] {peor['ruta']} sin respuesta"
    return 1, f"[latencia] {peor['ruta']} con p95 {peor['p95']:.0f} ms (umbral {umbral_ms:.0f} ms)"


def _ms(valor: float | None) -> str:
    return f"{valor:.0f} ms" if valor is not None else "—"


def tabla_markdown(filas: list[dict]) -> str:
    """La tabla ruta × n × p50 × p95 × máx × estado; sirve en consola, en el
    resumen del job y en el cuerpo del issue."""
    lineas = [
        "| ruta | n | p50 | p95 | máx | estado |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for f in filas:
        if f["n"]:
            estado = "lenta" if f["lenta"] else ("ok" if not f["fallos"] else f"ok ({f['fallos']} fallo(s))")
        else:
            error = str(f["error"] or "sin muestras").splitlines()[0].replace("|", "/")[:80]
            estado = f"sin respuesta ({error})"
        lineas.append(f"| `{f['ruta']}` | {f['n']} | {_ms(f['p50'])} | {_ms(f['p95'])} | {_ms(f['max'])} | {estado} |")
    if not filas:
        lineas.append("| _sin rutas medidas_ | 0 | — | — | — | — |")
    return "\n".join(lineas)


def informe(filas: list[dict], base: str, umbral_ms: float, repeticiones: int) -> str:
    """El informe completo en markdown: encabezado, tabla y qué hacer si falla."""
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    codigo, _ = veredicto(filas, umbral_ms)
    veredicto_txt = (
        f"**{sum(1 for f in filas if f['lenta'] or f['caida'])} ruta(s) fuera del presupuesto de {umbral_ms:.0f} ms**"
        if codigo
        else "todas las rutas dentro del presupuesto"
    )
    run = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run = f"\nCorrida: {os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return f"""## Latencia de las páginas públicas

{tabla_markdown(filas)}

{veredicto_txt}. Base: {base} · {repeticiones} repetición(es) por ruta · hora UTC {ahora}.{run}

Si una ruta quedó lenta: revisa primero la caché del borde (miss del Worker),
después el peso de la vista (`python scripts/local/presupuesto_peso.py`) y por
último la consulta que la alimenta. Detalles en docs/LATENCIA.md. Mientras un
issue «[latencia] …» siga abierto, este monitoreo lo actualiza en vez de crear otro."""


def leer_desde(path: Path) -> list[dict]:
    """Filas {ruta, muestras, fallos, error} desde un JSON: `{"ruta": [ms, ...]}`
    o la salida de `--json` (`{"rutas": {"ruta": {"muestras": [...], ...}}}`)."""
    datos = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(datos, dict):
        datos = datos.get("rutas", datos)
    if not isinstance(datos, dict):
        raise ValueError("se esperaba un objeto JSON con las rutas como claves")
    filas = []
    for ruta, valor in datos.items():
        if isinstance(valor, dict):
            filas.append(
                {
                    "ruta": ruta,
                    "muestras": valor.get("muestras") or [],
                    "fallos": valor.get("fallos") or 0,
                    "error": valor.get("error"),
                }
            )
        else:
            filas.append({"ruta": ruta, "muestras": valor or [], "fallos": 0, "error": None})
    return filas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=URL_DEFECTO, help=f"base a medir (por defecto {URL_DEFECTO})")
    p.add_argument("--repeticiones", type=int, default=REPETICIONES, help=f"GETs por ruta (por defecto {REPETICIONES})")
    p.add_argument("--umbral-ms", type=float, default=UMBRAL_MS, help=f"p95 máximo permitido (por defecto {UMBRAL_MS:.0f})")
    p.add_argument("--json", type=Path, metavar="SALIDA", help="guarda la medición y el resumen en JSON")
    p.add_argument("--dry-run", action="store_true", help="sin red: usa las muestras de --desde")
    p.add_argument("--desde", type=Path, metavar="ARCHIVO", help="JSON con muestras por ruta (con --dry-run)")
    args = p.parse_args(argv)

    if args.dry_run:
        if not args.desde:
            print("--dry-run necesita --desde <archivo.json>", file=sys.stderr)
            return 2
        try:
            filas = leer_desde(args.desde)
        except Exception as e:
            print(f"No se pudo leer {args.desde}: {e}", file=sys.stderr)
            return 2
        base = f"muestra {args.desde}"
    else:
        if args.repeticiones < 1:
            print("--repeticiones debe ser al menos 1", file=sys.stderr)
            return 2
        base = args.url.rstrip("/")
        filas = medir(base, RUTAS, args.repeticiones)

    resultado = resumen(filas, args.umbral_ms)
    codigo, titulo = veredicto(resultado, args.umbral_ms)
    print(informe(resultado, base, args.umbral_ms, args.repeticiones))
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "base": base,
                    "umbral_ms": args.umbral_ms,
                    "repeticiones": args.repeticiones,
                    "rutas": {
                        r["ruta"]: {
                            "muestras": f.get("muestras", []),
                            "fallos": r["fallos"],
                            "n": r["n"],
                            "p50": r["p50"],
                            "p95": r["p95"],
                            "max": r["max"],
                            "lenta": r["lenta"],
                            "caida": r["caida"],
                            "error": r["error"],
                        }
                        for f, r in zip(filas, resultado)
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with Path(out).open("a", encoding="utf-8") as f:
            f.write(f"alerta={'true' if codigo else 'false'}\n")
            if titulo:
                f.write(f"titulo={titulo}\n")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
