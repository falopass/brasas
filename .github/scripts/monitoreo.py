"""Monitoreo programado de la ingesta en producción (OPS-01).

Uso: python monitoreo.py [payload.json]

Sin argumentos hace una sonda GET a /api/status?history=3 en producción (se puede apuntar a otra
URL con BRASA_STATUS_URL); con un archivo JSON usa ese payload, para probar los veredictos sin red.

Veredictos de alerta (cualquiera basta):
  a) freshness.stale == true      — los datos llevan más de 30 min; el umbral lo decide el servidor
  b) last_cycle.risk_error == true — el riesgo de hoy no se recalculó en el último ciclo
  c) risk_computed_at con más de 6 h — dos ciclos de 3 h sin recalcular; si la marca falta o no se
     puede leer, no hay veredicto por esta vía
  d) un producto de history con   — exige al menos 3 registros de ese producto
     sus 3 últimas ejecuciones
     con ok=false
  e) last_cycle.backup == false   — falló el respaldo de brasa.db a R2
  f) last_cycle.work_backup == false — falló el respaldo de work.db; solo con false explícito

Con alerta escribe alerta.md (cuerpo del issue) y deja alerta=true y titulo en GITHUB_OUTPUT para
que el workflow lo publique; sin alerta solo deja constancia en el log. Si la consulta falla (red,
HTTP distinto de 200 o JSON inválido) sale con 1: sin datos no hay veredicto y el run queda en rojo.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATUS_URL = os.environ.get("BRASA_STATUS_URL", "https://brasa-chile.ddiegosebastianbb.workers.dev/api/status?history=3")
UA = {"User-Agent": "BRASA-Chile monitoreo (+https://github.com/falopass/brasas)"}
RIESGO_VIEJO_H = 6  # el riesgo se calcula cada 3 h: 6 h son dos ciclos perdidos


def _momento(valor: object) -> datetime | None:
    """Lee una marca ISO-8601 del payload; None si falta o no se puede leer."""
    if not isinstance(valor, str):
        return None
    try:
        marca = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return marca if marca.tzinfo else marca.replace(tzinfo=timezone.utc)


def edad_riesgo_h(p: dict) -> float | None:
    """Horas entre risk_computed_at y time_utc (o ahora, si el payload no trae time_utc)."""
    riesgo = _momento(p.get("risk_computed_at"))
    if riesgo is None:
        return None
    return ((_momento(p.get("time_utc")) or datetime.now(timezone.utc)) - riesgo).total_seconds() / 3600


def productos_caidos(p: dict) -> dict[str, list]:
    """Productos de history cuyas 3 últimas ejecuciones fallaron (exige al menos 3 registros)."""
    return {prod: runs[:3] for prod, runs in (p.get("history") or {}).items() if len(runs) >= 3 and all(not r.get("ok") for r in runs[:3])}


def veredictos(p: dict) -> list[tuple[str, str]]:
    """Condiciones de alerta que se cumplen: una tupla (etiqueta corta, detalle) por cada una."""
    razones: list[tuple[str, str]] = []
    fresh = p.get("freshness") or {}
    if fresh.get("stale") is True:
        razones.append(
            (
                "datos estancados",
                f"freshness.stale=true: last_ingest_at={p.get('last_ingest_at')} "
                f"(age_seconds={fresh.get('age_seconds')}, umbral={fresh.get('stale_after_s')} s)",
            )
        )
    ciclo = p.get("last_cycle") if isinstance(p.get("last_cycle"), dict) else {}
    if ciclo.get("risk_error") is True:
        razones.append(
            (
                "riesgo sin recalcular",
                f"last_cycle.risk_error=true: el riesgo de hoy no se recalculó (finished_at={ciclo.get('finished_at')})",
            )
        )
    edad = edad_riesgo_h(p)
    if edad is not None and edad > RIESGO_VIEJO_H:
        razones.append(
            (
                "riesgo viejo",
                f"risk_computed_at={p.get('risk_computed_at')} tiene {edad:.1f} h "
                f"(umbral {RIESGO_VIEJO_H} h): el peligro de hoy está desactualizado",
            )
        )
    for prod, runs in sorted(productos_caidos(p).items()):
        marcas = ", ".join(str(r.get("started_at") or "?") for r in runs)
        razones.append((f"3 fallos seguidos: {prod}", f"sus 3 últimas ejecuciones tienen ok=false (started_at: {marcas})"))
    if ciclo.get("backup") is False:
        razones.append(
            ("respaldo falló", f"last_cycle.backup=false: brasa.db no se respaldó a R2 (finished_at={ciclo.get('finished_at')})")
        )
    if ciclo.get("work_backup") is False:
        razones.append(
            ("respaldo de work.db falló", f"last_cycle.work_backup=false: work.db no se respaldó (finished_at={ciclo.get('finished_at')})")
        )
    return razones


def cuerpo_issue(p: dict, razones: list[tuple[str, str]], ahora: str) -> str:
    fresh = p.get("freshness") or {}
    ciclo = p.get("last_cycle") if isinstance(p.get("last_cycle"), dict) else {}
    caidos = ", ".join(productos_caidos(p)) or "—"
    edad = edad_riesgo_h(p)
    edad_txt = f"{edad:.1f} h" if edad is not None else "—"
    run = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run = f"\nCorrida: {os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    condiciones = "\n".join(f"- **{corta}** — {detalle}" for corta, detalle in razones)
    return f"""## Alerta de ingesta en producción

El monitoreo programado (OPS-01) encontró {len(razones)} condición(es) de alerta:

{condiciones}

**Valores observados**
- `last_ingest_at`: {p.get("last_ingest_at")}
- `freshness.age_seconds`: {fresh.get("age_seconds")} s (umbral {fresh.get("stale_after_s")} s)
- `last_cycle.backup`: {ciclo.get("backup", "sin last_cycle")}
- `last_cycle.work_backup`: {ciclo.get("work_backup", "sin last_cycle")}
- `last_cycle.risk_error`: {ciclo.get("risk_error", "sin last_cycle")}
- `risk_computed_at`: {p.get("risk_computed_at")} (edad {edad_txt}; umbral {RIESGO_VIEJO_H} h)
- Productos con 3 fallos seguidos: {caidos}

Hora UTC de la sonda: {ahora}
Sonda: {STATUS_URL}{run}

Mientras este issue siga abierto el monitoreo no crea otros; ciérralo cuando la condición se resuelva."""


def sondar(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return json.loads(r.read(2_000_000).decode("utf-8", "replace"))


def main() -> int:
    if len(sys.argv) > 1:
        origen = sys.argv[1]
        try:
            payload = json.loads(Path(origen).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"::error::No se pudo leer {origen}: {e}")
            return 1
    else:
        origen = STATUS_URL
        try:
            payload = sondar(origen)
        except Exception as e:
            print(f"::error::La sonda a {origen} no respondió: {type(e).__name__}: {e}")
            return 1
    if not isinstance(payload, dict):
        print("::error::La sonda no devolvió un objeto JSON")
        return 1
    razones = veredictos(payload)
    out = os.environ.get("GITHUB_OUTPUT")
    if not razones:
        print(f"sano ({origen}): last_ingest_at={payload.get('last_ingest_at')} — sin condiciones de alerta")
        if out:
            Path(out).open("a").write("alerta=false\n")
        return 0
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    titulo = ("[monitoreo] " + " + ".join(corta for corta, _ in razones)).replace("\n", " ")[:200]
    Path("alerta.md").write_text(cuerpo_issue(payload, razones, ahora), encoding="utf-8")
    for corta, detalle in razones:
        print(f"::warning::{corta} — {detalle}")
    if out:
        with Path(out).open("a", encoding="utf-8") as f:
            f.write(f"alerta=true\ntitulo={titulo}\n")
    else:
        print(f"titulo: {titulo}\n---\n{Path('alerta.md').read_text(encoding='utf-8')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
