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
  g) una página pública caída o lenta (AUTO-04) — status distinto de 200, content-type que no
     calza o más de 2,5 s en las siete rutas de arranque del sitio

Con alerta escribe alerta.md (cuerpo del issue) y deja alerta=true y titulo en GITHUB_OUTPUT para
que el workflow lo publique; sin alerta solo deja constancia en el log. Si la consulta falla (red,
HTTP distinto de 200 o JSON inválido) sale con 1: sin datos no hay veredicto y el run queda en rojo.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

STATUS_URL = os.environ.get("BRASA_STATUS_URL", "https://brasa-chile.ddiegosebastianbb.workers.dev/api/status?history=3")
BASE_URL = os.environ.get("BRASA_BASE_URL", "")
UA = {"User-Agent": "BRASA-Chile monitoreo (+https://github.com/falopass/brasas)"}
RIESGO_VIEJO_H = 6  # el riesgo se calcula cada 3 h: 6 h son dos ciclos perdidos
LENTA_MS = 2500  # una página pública sobre 2,5 s ya se siente caída en un celular
RUTAS_PUBLICAS = (
    "/web/index.html",
    "/web/datos.html",
    "/web/preguntas.html",
    "/web/respuesta.html",
    "/web/lista.html",
    "/web/manifest.webmanifest",
    "/web/sw.js",
)


def rutas_publicas(base: str) -> list[str]:
    """Las siete rutas de arranque del sitio, absolutas bajo `base` (sin barra final duplicada)."""
    return [f"{base.rstrip('/')}{ruta}" for ruta in RUTAS_PUBLICAS]


def _tipo_esperado(ruta: str) -> tuple[str, ...]:
    """Content-type aceptable por ruta: HTML para las páginas, JSON para el manifest y JS para el worker."""
    if ruta.endswith("/sw.js"):
        return ("javascript",)
    if ruta.endswith("/manifest.webmanifest"):
        return ("application/manifest+json", "json")
    return ("text/html",)


def evaluar_paginas(resultados: list[dict]) -> list[tuple[str, str]]:
    """Veredictos de las páginas: caída por status/content-type y lentitud por encima de `LENTA_MS`.

    `resultados` es una lista de `{ruta, status, content_type, ms, error}`; sin datos no hay
    veredictos (el modo con archivo JSON no inventa una sonda que no corrió).
    """
    razones: list[tuple[str, str]] = []
    for r in resultados or []:
        ruta = str(r.get("ruta") or "?")
        error = r.get("error")
        if error:
            razones.append((f"pagina_caida:{ruta}", f"{ruta}: {error}"))
            continue
        status = r.get("status")
        tipo = str(r.get("content_type") or "").split(";")[0].strip().lower()
        if status != 200:
            razones.append((f"pagina_caida:{ruta}", f"{ruta}: HTTP {status}"))
        elif not any(esperado in tipo for esperado in _tipo_esperado(ruta)):
            razones.append(
                (f"pagina_caida:{ruta}", f"{ruta}: content-type «{tipo or 'sin content-type'}» donde se esperaba {_tipo_esperado(ruta)[0]}")
            )
        ms = r.get("ms")
        if isinstance(ms, (int, float)) and ms > LENTA_MS:
            razones.append((f"pagina_lenta:{ruta}", f"{ruta}: {ms:.0f} ms (umbral {LENTA_MS} ms)"))
    return razones


def sondar_paginas(base: str) -> list[dict]:
    """GET a cada página pública, con el tiempo que tardó; un fallo de red queda como `error`."""
    resultados: list[dict] = []
    for ruta in rutas_publicas(base):
        inicio = time.monotonic()
        try:
            with urllib.request.urlopen(urllib.request.Request(ruta, headers={**UA, "Accept-Encoding": "identity"}), timeout=10) as r:
                resultados.append(
                    {
                        "ruta": ruta,
                        "status": r.status,
                        "content_type": r.headers.get("Content-Type", ""),
                        "ms": (time.monotonic() - inicio) * 1000,
                        "error": None,
                    }
                )
        except Exception as e:
            resultados.append(
                {
                    "ruta": ruta,
                    "status": None,
                    "content_type": "",
                    "ms": (time.monotonic() - inicio) * 1000,
                    "error": f"{type(e).__name__}: {e}",
                }
            )
    return resultados


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


def cuerpo_issue(p: dict, razones: list[tuple[str, str]], ahora: str, paginas: list[dict] | None = None) -> str:
    fresh = p.get("freshness") or {}
    ciclo = p.get("last_cycle") if isinstance(p.get("last_cycle"), dict) else {}
    caidos = ", ".join(productos_caidos(p)) or "—"
    edad = edad_riesgo_h(p)
    edad_txt = f"{edad:.1f} h" if edad is not None else "—"
    run = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run = f"\nCorrida: {os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    condiciones = "\n".join(f"- **{corta}** — {detalle}" for corta, detalle in razones)
    paginas_txt = ""
    if paginas:
        filas = "\n".join(
            f"- `{r.get('ruta')}`: {'error ' + str(r.get('error')) if r.get('error') else 'HTTP ' + str(r.get('status'))} · {r.get('ms') or 0:.0f} ms"
            for r in paginas
        )
        paginas_txt = f"\n**Páginas públicas**\n{filas}\n"
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
{paginas_txt}
Hora UTC de la sonda: {ahora}
Sonda: {STATUS_URL}{run}

Mientras este issue siga abierto el monitoreo no crea otros; ciérralo cuando la condición se resuelva."""


def sondar(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return json.loads(r.read(2_000_000).decode("utf-8", "replace"))


def _base_de(url: str) -> str:
    """Origen (esquema + host) de una URL, para derivar las páginas del mismo sitio."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def main() -> int:
    paginas: list[dict] | None = None
    if len(sys.argv) > 1:
        origen = sys.argv[1]
        try:
            payload = json.loads(Path(origen).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"::error::No se pudo leer {origen}: {e}")
            return 1
        # El payload de prueba puede traer `pages`; si no viene, no se inventan veredictos.
        if isinstance(payload, dict) and isinstance(payload.get("pages"), list):
            paginas = payload["pages"]
    else:
        origen = STATUS_URL
        try:
            payload = sondar(origen)
        except Exception as e:
            print(f"::error::La sonda a {origen} no respondió: {type(e).__name__}: {e}")
            return 1
        base = BASE_URL or _base_de(origen)
        if base:
            paginas = sondar_paginas(base)
    if not isinstance(payload, dict):
        print("::error::La sonda no devolvió un objeto JSON")
        return 1
    razones = veredictos(payload)
    if paginas is not None:
        razones += evaluar_paginas(paginas)
    out = os.environ.get("GITHUB_OUTPUT")
    if not razones:
        print(f"sano ({origen}): last_ingest_at={payload.get('last_ingest_at')} — sin condiciones de alerta")
        if out:
            Path(out).open("a").write("alerta=false\n")
        return 0
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    titulo = ("[monitoreo] " + " + ".join(corta for corta, _ in razones)).replace("\n", " ")[:200]
    Path("alerta.md").write_text(cuerpo_issue(payload, razones, ahora, paginas), encoding="utf-8")
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
