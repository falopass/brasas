"""Sonda de producción de BRASA (OPS-01, QA-08).

Recorre en un comando lo que ve un vecino en producción y dice qué está fallando y qué hacer.
Solo hace peticiones GET y no escribe nada.

Uso:
    python scripts/local/smoke_produccion.py [--url URL] [--json]

Sondas: páginas y assets, /api/status (frescura y fallas de ingesta), /api/observations,
/api/incidents, /api/panorama y el sitemap. Cada una mide milisegundos y queda OK, LENTA
(> 2000 ms) o ERROR (HTTP distinto de 200, content-type inesperado, JSON inválido o red caída).
Al final imprime `RESULTADO: ...` y, si hay problemas, el texto para una persona y el arreglo
sugerido. Sale 0 solo si todo está en verde; con --json imprime un objeto JSON (sin la línea
RESULTADO, que va en el campo `resultado`).

La API publica las detecciones en `points` (docs/API.md), no en `features`, y el sitemap vive
en /web/sitemap.xml, que es a donde apunta robots.txt.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

URL_DEFECTO = "https://brasa-chile.ddiegosebastianbb.workers.dev"
UA = {"User-Agent": "BRASA-Chile sonda (+https://github.com/falopass/brasas)"}
TIMEOUT_S = 8
MAX_BYTES = 8_000_000
LENTA_MS = 2000
EDAD_MAX_S = 1800
# Productos cuya caída no cambia lo que ve un vecino: las condiciones de CONAF son contexto
# del riesgo y no ocultan detecciones, incidentes ni avisos.
PRODUCTOS_SIN_IMPACTO = {"CONAF_CONDICIONES"}


@dataclass
class Problema:
    texto: str
    arreglo: str


@dataclass
class Sonda:
    nombre: str
    ruta: str
    estado: str
    ms: int
    detalle: str
    problemas: list[Problema] = field(default_factory=list)


def pedir(url: str, opener: Callable[..., Any]) -> tuple[int, str, bytes, str]:
    """GET sin cuerpo. Devuelve (status, content-type, cuerpo, error); status 0 = sin respuesta."""
    req = urllib.request.Request(url, headers=UA, method="GET")
    try:
        with opener(req, timeout=TIMEOUT_S) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(MAX_BYTES), ""
    except urllib.error.HTTPError as e:
        return e.code, (e.headers.get("Content-Type", "") if e.headers else ""), b"", ""
    except Exception as e:  # URLError, timeout, DNS, TLS…
        return 0, "", b"", f"sin respuesta ({type(e).__name__})"


def _agregar(s: Sonda, texto: str, arreglo: str) -> None:
    s.problemas.append(Problema(texto, arreglo))
    s.estado = "error"


def _base(nombre: str, ruta: str, base: str, opener: Callable[..., Any], reloj: Callable[[], float]) -> tuple[Sonda, int, str, bytes, str]:
    t0 = reloj()
    status, ct, body, error = pedir(base + ruta, opener)
    ms = max(0, int(round((reloj() - t0) * 1000)))
    s = Sonda(nombre, ruta, "ok", ms, "")
    if error:
        s.detalle = error
        _agregar(
            s,
            f"{ruta} no responde ({error})",
            "revisa la red y el estado del Worker; confirma /api/health desde tu equipo",
        )
    elif status != 200:
        s.detalle = f"HTTP {status}"
        _agregar(
            s,
            f"{ruta} responde HTTP {status}",
            "revisa el despliegue y los logs del Worker/contenedor; si es 5xx, mira /api/status y el diagnóstico de Cloudflare",
        )
    elif not body:
        s.detalle = "respuesta vacía"
        _agregar(s, f"{ruta} responde vacío", "revisa el archivo en web/ y el despliegue")
    else:
        s.detalle = f"HTTP 200 · {ct or 'sin content-type'} · {len(body)} B"
        if ms > LENTA_MS:
            s.estado = "lenta"
            s.problemas.append(
                Problema(
                    f"{ruta} tardó {ms} ms (umbral {LENTA_MS} ms)",
                    "revisa la caché del borde (OPS-03), el contenedor y la base; si es una página, el peso",
                )
            )
    return s, status, ct, body, error


def _tipo_ok(ct: str, esperados: tuple[str, ...]) -> bool:
    ct = ct.lower()
    return any(e in ct for e in esperados)


def _json(body: bytes) -> Any | None:
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None


def _json_valido(s: Sonda, ruta: str, ct: str, body: bytes) -> Any | None:
    if not _tipo_ok(ct, ("application/json",)):
        _agregar(
            s,
            f"{ruta} responde {ct or 'sin content-type'}: se esperaba application/json",
            "revisa la ruta y los logs del contenedor",
        )
        return None
    data = _json(body)
    if data is None:
        _agregar(s, f"{ruta} no devuelve JSON válido", "revisa la ruta y los logs del contenedor")
    return data


def sonda_pagina(
    nombre: str, ruta: str, base: str, opener: Callable[..., Any], reloj: Callable[[], float], esperado: tuple[str, ...]
) -> Sonda:
    s, status, ct, body, error = _base(nombre, ruta, base, opener, reloj)
    if status != 200 or error or not body:
        return s
    if not _tipo_ok(ct, esperado):
        _agregar(
            s,
            f"{ruta} responde {ct or 'sin content-type'}: se esperaba {' o '.join(esperado)}",
            "revisa la ruta estática y el despliegue de web/",
        )
    return s


def sonda_status(base: str, opener: Callable[..., Any], reloj: Callable[[], float]) -> Sonda:
    ruta = "/api/status"
    s, status, ct, body, error = _base("estado", ruta, base, opener, reloj)
    if status != 200 or error or not body:
        return s
    data = _json_valido(s, ruta, ct, body)
    if not isinstance(data, dict):
        if data is not None:
            _agregar(s, f"{ruta} devuelve JSON que no es un objeto", "revisa la ruta y los logs del contenedor")
        return s
    fresh = data.get("freshness")
    if not isinstance(fresh, dict):
        _agregar(s, f"{ruta} no trae freshness", "revisa el backend y el despliegue")
    else:
        age = fresh.get("age_seconds")
        stale = fresh.get("stale")
        if stale is True or (isinstance(age, (int, float)) and age >= EDAD_MAX_S):
            if isinstance(age, (int, float)):
                texto = f"datos de hace {int(age // 60)} min (freshness.age_seconds={age}, stale={stale})"
            else:
                texto = f"datos marcados como estancados (freshness.stale={stale}, sin age_seconds)"
            _agregar(s, texto, "revisa el workflow monitoreo y el ciclo de ingesta (OPS-01)")
        elif not isinstance(age, (int, float)):
            _agregar(s, f"{ruta} no trae freshness.age_seconds", "revisa el backend y el despliegue")
    fallas = data.get("failures_24h")
    if isinstance(fallas, dict):
        if fallas.get("error") is True:
            _agregar(
                s,
                f"{ruta} no pudo leer el historial de fallas (failures_24h.error=true)",
                "revisa la base y los logs del contenedor",
            )
        for producto, info in sorted(fallas.items()):
            if producto == "error" or producto in PRODUCTOS_SIN_IMPACTO or not isinstance(info, dict):
                continue
            fallidas = info.get("failed")
            if isinstance(fallidas, (int, float)) and fallidas > 0:
                _agregar(
                    s,
                    f"falla la ingesta de {producto}: {fallidas} de {info.get('runs')} corridas en 24 h "
                    f"(último error: {info.get('last_error') or 'sin mensaje'})",
                    "revisa la fuente y el workflow monitoreo (OPS-01)",
                )
    elif fallas is not None:
        _agregar(s, f"{ruta} devuelve failures_24h que no es un objeto", "revisa el backend y el despliegue")
    return s


def sonda_observaciones(base: str, opener: Callable[..., Any], reloj: Callable[[], float]) -> Sonda:
    ruta = "/api/observations?bbox=-75,-56,-66,-17"
    s, status, ct, body, error = _base("detecciones", ruta, base, opener, reloj)
    if status != 200 or error or not body:
        return s
    data = _json_valido(s, ruta, ct, body)
    if not isinstance(data, dict):
        if data is not None:
            _agregar(s, f"{ruta} devuelve JSON que no es un objeto", "revisa la ruta y los logs del contenedor")
        return s
    puntos = data.get("points")
    if not isinstance(puntos, list) or not puntos:
        _agregar(
            s,
            f"{ruta} responde sin detecciones (points vacío)",
            "revisa la ingesta GOES/FIRMS y el ciclo de ingesta; confirma /api/status",
        )
    return s


def sonda_json(nombre: str, ruta: str, base: str, opener: Callable[..., Any], reloj: Callable[[], float]) -> Sonda:
    s, status, ct, body, error = _base(nombre, ruta, base, opener, reloj)
    if status != 200 or error or not body:
        return s
    data = _json_valido(s, ruta, ct, body)
    if data is not None and not isinstance(data, dict):
        _agregar(s, f"{ruta} devuelve JSON que no es un objeto", "revisa la ruta y los logs del contenedor")
    return s


def sonda_sitemap(base: str, opener: Callable[..., Any], reloj: Callable[[], float]) -> Sonda:
    ruta = "/web/sitemap.xml"
    s, status, ct, body, error = _base("sitemap", ruta, base, opener, reloj)
    if status != 200 or error or not body:
        return s
    if not _tipo_ok(ct, ("xml",)):
        _agregar(
            s,
            f"{ruta} responde {ct or 'sin content-type'}: se esperaba XML",
            "revisa web/sitemap.xml y el despliegue",
        )
    return s


def main(
    argv: list[str] | None = None,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    reloj: Callable[[], float] = time.monotonic,
) -> int:
    parser = argparse.ArgumentParser(description="Sonda GET de producción de BRASA (OPS-01, QA-08).")
    parser.add_argument("--url", default=URL_DEFECTO, help=f"origen a sondar (por defecto {URL_DEFECTO})")
    parser.add_argument("--json", action="store_true", help="salida JSON para máquinas")
    args = parser.parse_args(argv)
    base = args.url.rstrip("/")
    sondas = [
        sonda_pagina("portada", "/", base, opener, reloj, ("text/html",)),
        sonda_pagina("app.js", "/web/js/app.js", base, opener, reloj, ("javascript",)),
        sonda_pagina("manifest", "/manifest.webmanifest", base, opener, reloj, ("manifest+json", "application/json")),
        sonda_status(base, opener, reloj),
        sonda_observaciones(base, opener, reloj),
        sonda_json("incidentes", "/api/incidents", base, opener, reloj),
        sonda_json("panorama", "/api/panorama", base, opener, reloj),
        sonda_sitemap(base, opener, reloj),
    ]
    problemas = [p for s in sondas for p in s.problemas]
    total_ms = sum(s.ms for s in sondas)
    if problemas:
        rutas = sorted({s.ruta for s in sondas if s.problemas})
        resultado = f"{len(problemas)} problema(s) en {len(sondas)} sondas: {', '.join(rutas)}"
    else:
        resultado = "todo en verde"
    if args.json:
        print(
            json.dumps(
                {
                    "url": base,
                    "ok": not problemas,
                    "total_ms": total_ms,
                    "resultado": resultado,
                    "sondas": [
                        {
                            "nombre": s.nombre,
                            "ruta": s.ruta,
                            "estado": s.estado,
                            "ms": s.ms,
                            "detalle": s.detalle,
                            "problemas": [{"texto": p.texto, "arreglo": p.arreglo} for p in s.problemas],
                        }
                        for s in sondas
                    ],
                    "problemas": [{"texto": p.texto, "arreglo": p.arreglo} for p in problemas],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Sonda de producción de BRASA · {base}")
        for s in sondas:
            print(f"  {s.estado.upper():5} {s.ruta:44} {s.ms:5} ms  {s.detalle}")
        if problemas:
            print("\nProblemas:")
            for p in problemas:
                print(f"  - {p.texto}")
                print(f"    Arreglo: {p.arreglo}")
        print(f"\nRESULTADO: {resultado} · {total_ms} ms")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
