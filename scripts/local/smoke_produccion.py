"""Sonda de producción de BRASA (OPS-01, QA-08).

Recorre en un comando lo que ve un vecino en producción y dice qué está fallando y qué hacer.
Solo hace peticiones GET y no escribe nada.

Uso:
    python scripts/local/smoke_produccion.py [--url URL] [--json] [--sin-version]

Sondas: páginas y assets (incluida la liviana de /web/lite.html), /api/health (estado y versión),
/api/status (frescura, fallas de ingesta, respaldo y errores del ciclo, y edad del riesgo),
/api/observations,
/api/incidents (con chequeo territorial), /api/panorama, el sitemap y, con el primer incidente
abierto, el enlace de compartir /i/<id> y su tarjeta /og/incident/<id>.png.
Cada una mide milisegundos y queda OK, LENTA (> 2000 ms) o ERROR (HTTP distinto de 200,
content-type inesperado, JSON inválido o red caída). La versión que publica /api/health se compara
con la de backend/version.py en el repo; --sin-version omite esa comparación para sondear un
entorno que no sigue a main.
Al final imprime `RESULTADO: ...` y, si hay problemas, el texto para una persona y el arreglo
sugerido. Sale 0 solo si todo está en verde; con --json imprime un objeto JSON (sin la línea
RESULTADO, que va en el campo `resultado`).

La API publica las detecciones en `points` (docs/API.md), no en `features`, y el sitemap vive
en /web/sitemap.xml, que es a donde apunta robots.txt.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

URL_DEFECTO = "https://brasa-chile.ddiegosebastianbb.workers.dev"
VERSION_PY = Path(__file__).resolve().parents[2] / "backend" / "version.py"
VERSION_RE = re.compile(r'^VERSION\s*=\s*"([^"]+)"', re.MULTILINE)
UA = {"User-Agent": "BRASA-Chile sonda (+https://github.com/falopass/brasas)"}
TIMEOUT_S = 8
MAX_BYTES = 8_000_000
LENTA_MS = 2000
# El riesgo por comuna se recalcula cada risk_interval_min (180 min por defecto): al doble
# de ese ritmo no es un retraso sino un estancamiento — «el peligro de hoy» quedó sin calcular.
RIESGO_MAX_S = 6 * 3600
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


def version_repo() -> str | None:
    """VERSION declarada en backend/version.py, leída con regex para no importar el paquete."""
    try:
        texto = VERSION_PY.read_text(encoding="utf-8")
    except OSError:
        return None
    m = VERSION_RE.search(texto)
    return m.group(1) if m else None


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


def sonda_health(base: str, opener: Callable[..., Any], reloj: Callable[[], float]) -> tuple[Sonda, str | None]:
    """GET /api/health: exige status "ok" y devuelve la versión publicada (None si no la trae)."""
    ruta = "/api/health"
    s, status, ct, body, error = _base("salud", ruta, base, opener, reloj)
    if status != 200 or error or not body:
        return s, None
    data = _json_valido(s, ruta, ct, body)
    if not isinstance(data, dict):
        if data is not None:
            _agregar(s, f"{ruta} devuelve JSON que no es un objeto", "revisa la ruta y los logs del contenedor")
        return s, None
    if data.get("status") != "ok":
        _agregar(
            s,
            f'{ruta} devuelve status={data.get("status")!r}: se esperaba "ok"',
            "revisa el estado del contenedor y los logs",
        )
    version = data.get("version")
    if not isinstance(version, str) or not version:
        _agregar(s, f"{ruta} no trae version", "revisa backend/version.py y el despliegue")
        return s, None
    return s, version


def comparar_version(s: Sonda, publicada: str, repo: str) -> None:
    # shortcut: dos commits con la misma VERSION dan verde aunque producción no sea el último;
    # mejorar cuando /api/health publique el commit del despliegue.
    if publicada != repo:
        _agregar(
            s,
            f"producción publica {publicada} y el repositorio dice {repo}",
            "vuelve a desplegar y confirma el commit del Worker; si ya desplegaste, revisa la caché del borde",
        )


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
    ciclo = data.get("last_cycle")
    if isinstance(ciclo, dict):
        caidos = [k for k in ("backup", "work_backup") if ciclo.get(k) is False]
        if caidos:
            detalle = str(ciclo.get("backup_error") or "sin mensaje")[:200]
            _agregar(
                s,
                f"el respaldo de la base a R2 falló (last_cycle.{', '.join(caidos)}=false; backup_error: {detalle})",
                "revisa DB_ENC_KEY y el almacenamiento del Worker; la misma señal la vigila monitoreo.yml",
            )
        # OPS-42: los *_error del ciclo no entran en failures_24h (que solo cuenta corridas de
        # producto), así que un risk_error crónico pasaba inadvertido. `backup_error` ya salió
        # con el detalle del respaldo y conaf_cond no le cambia nada al vecino (PRODUCTOS_SIN_IMPACTO).
        for k in sorted(ciclo):
            if not (k == "error" or k.endswith("_error")) or k in ("backup_error", "conaf_cond_error"):
                continue
            _agregar(
                s,
                f"el último ciclo terminó con {k}: {str(ciclo[k])[:200]}",
                "revisa el cupo de Open-Meteo (open_meteo en /api/status, RISK-04) y los logs del contenedor"
                if k == "risk_error"
                else "revisa los logs del contenedor y el workflow monitoreo (OPS-01)",
            )
    riesgo_at = data.get("risk_computed_at")
    if not isinstance(riesgo_at, str) or not riesgo_at:
        _agregar(s, f"{ruta} no trae risk_computed_at", "revisa el backend y el despliegue")
    else:
        try:
            edad = (datetime.now(timezone.utc) - datetime.fromisoformat(riesgo_at.replace("Z", "+00:00"))).total_seconds()
        except ValueError:
            _agregar(s, f"{ruta} trae un risk_computed_at inválido: {riesgo_at!r}", "revisa el backend y el despliegue")
        else:
            if edad >= RIESGO_MAX_S:
                _agregar(
                    s,
                    f"el peligro por comuna no se recalcula hace {int(edad // 3600)} h (risk_computed_at={riesgo_at})",
                    "revisa risk_error en el último ciclo y el cupo de Open-Meteo (RISK-04)",
                )
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


# ------------------------------------------------------- territorio chileno (SONDA-01)
#
# La referencia es backend.geo.territory() (shapely + comunas BCN), la misma que usa la API.
# Cuando no se puede importar —la sonda corre también en un runner sin dependencias— se cae
# a un punto-en-polígono mínimo sobre web/data/comunas.geojson, con la misma tolerancia que
# `locate` (0.02°) para la costa simplificada. Si ni eso está, la revisión se omite.

COMUNAS_GEOJSON = Path(__file__).resolve().parents[2] / "web" / "data" / "comunas.geojson"
_TERRITORIO: tuple[str, Any] | None = None


def _comunas_geojson() -> list[tuple[tuple[float, float, float, float], list]]:
    """web/data/comunas.geojson como (bbox, polígonos); lista vacía si no se puede leer."""
    try:
        data = json.loads(COMUNAS_GEOJSON.read_text(encoding="utf-8"))
    except OSError:
        return []
    comunas = []
    for feature in data.get("features", []):
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or []
        polys = coords if geom.get("type") == "MultiPolygon" else [coords]
        polys = [[[(float(x), float(y)) for x, y in ring] for ring in poly] for poly in polys if poly]
        if not polys:
            continue
        xs = [p[0] for poly in polys for ring in poly for p in ring]
        ys = [p[1] for poly in polys for ring in poly for p in ring]
        comunas.append(((min(xs), min(ys), max(xs), max(ys)), polys))
    return comunas


def _territorio() -> tuple[str, Any]:
    global _TERRITORIO
    if _TERRITORIO is None:
        try:
            repo = str(Path(__file__).resolve().parents[2])
            if repo not in sys.path:
                sys.path.insert(0, repo)
            from backend.geo import territory

            _TERRITORIO = ("geo", territory())
        except Exception:
            _TERRITORIO = ("geojson", _comunas_geojson())
    return _TERRITORIO


def _en_anillo(lat: float, lon: float, ring: list[tuple[float, float]]) -> bool:
    """Punto dentro del anillo (ray casting); los vértices vienen como (lon, lat)."""
    dentro = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def _dist_segmento(lat: float, lon: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Distancia en grados del punto al segmento; para la tolerancia alcanza con equirect."""
    dx, dy = bx - ax, by - ay
    if not dx and not dy:
        return math.hypot(lon - ax, lat - ay)
    t = max(0.0, min(1.0, ((lon - ax) * dx + (lat - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(lon - (ax + t * dx), lat - (ay + t * dy))


def _en_geojson(lat: float, lon: float, comunas: list, tol: float = 0.02) -> bool:
    for (w, s, e, n), polys in comunas:
        if not (w - tol <= lon <= e + tol and s - tol <= lat <= n + tol):
            continue
        for poly in polys:
            if _en_anillo(lat, lon, poly[0]) and not any(_en_anillo(lat, lon, hueco) for hueco in poly[1:]):
                return True
            for ring in poly:
                for i in range(len(ring)):
                    if _dist_segmento(lat, lon, *ring[i - 1], *ring[i]) <= tol:
                        return True
    return False


def _en_chile(lat: float, lon: float) -> bool | None:
    """True/False según la referencia disponible; None si no hay ninguna (revisión omitida)."""
    kind, terr = _territorio()
    if kind == "geo":
        return terr.locate(lat, lon) is not None
    if not terr:
        return None
    return _en_geojson(lat, lon, terr)


def sonda_incidentes(base: str, opener: Callable[..., Any], reloj: Callable[[], float]) -> tuple[Sonda, list[dict]]:
    """GET /api/incidents: exige JSON con la lista, revisa el territorio y la devuelve para las sondas que la reusan."""
    ruta = "/api/incidents"
    s, status, ct, body, error = _base("incidentes", ruta, base, opener, reloj)
    if status != 200 or error or not body:
        return s, []
    data = _json_valido(s, ruta, ct, body)
    if not isinstance(data, dict):
        if data is not None:
            _agregar(s, f"{ruta} devuelve JSON que no es un objeto", "revisa la ruta y los logs del contenedor")
        return s, []
    incidentes = data.get("incidents")
    if not isinstance(incidentes, list):
        _agregar(s, f"{ruta} no trae la lista incidents", "revisa la ruta y los logs del contenedor")
        return s, []
    incidentes = [i for i in incidentes if isinstance(i, dict)]
    fuera = []
    revisados = 0
    for inc in incidentes:
        lat, lon = inc.get("lat"), inc.get("lon")
        if isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        en = _en_chile(float(lat), float(lon))
        if en is None:
            continue
        revisados += 1
        if not en:
            fuera.append(f"{inc.get('id') or 'sin id'} ({lat}, {lon})")
    if fuera:
        muestra = ", ".join(fuera[:5]) + (f" y {len(fuera) - 5} más" if len(fuera) > 5 else "")
        _agregar(
            s,
            f"{len(fuera)} incidente{'s' if len(fuera) != 1 else ''} fuera de Chile: {muestra}",
            "revisa el filtro territorial de /api/incidents y la ingesta: un punto fuera de Chile no es un incendio de BRASA",
        )
    elif revisados:
        s.detalle += f" · {revisados} dentro de Chile"
    return s, incidentes


def sonda_compartir(base: str, opener: Callable[..., Any], reloj: Callable[[], float], inc_id: str) -> Sonda:
    """GET /i/<id>: el enlace que se comparte debe traer la página con las etiquetas og:* (OPS-35)."""
    ruta = f"/i/{inc_id}"
    s, status, ct, body, error = _base("compartir", ruta, base, opener, reloj)
    if status != 200 or error or not body:
        return s
    if not _tipo_ok(ct, ("text/html",)):
        _agregar(
            s,
            f"{ruta} responde {ct or 'sin content-type'}: se esperaba text/html",
            "revisa el enrutado del Worker: /i/ tiene que ir al backend, no a los assets",
        )
        return s
    faltan = [tag for tag in ("og:title", "og:image") if tag not in body.decode("utf-8", "replace")]
    if faltan:
        _agregar(
            s,
            f"{ruta} no trae {' ni '.join(faltan)}: WhatsApp no muestra la tarjeta del incidente",
            "revisa backend/og.py y el enrutado del Worker",
        )
    return s


def sonda_tarjeta(base: str, opener: Callable[..., Any], reloj: Callable[[], float], inc_id: str) -> Sonda:
    """GET /og/incident/<id>.png: la imagen de la tarjeta de vista previa (OPS-35)."""
    ruta = f"/og/incident/{inc_id}.png"
    s, status, ct, body, error = _base("tarjeta", ruta, base, opener, reloj)
    if status != 200 or error or not body:
        return s
    if not _tipo_ok(ct, ("image/png",)):
        _agregar(
            s,
            f"{ruta} responde {ct or 'sin content-type'}: se esperaba image/png",
            "revisa el enrutado del Worker: /og/ tiene que ir al backend, no a los assets",
        )
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
    parser.add_argument("--sin-version", action="store_true", help="omite comparar la versión publicada con backend/version.py")
    args = parser.parse_args(argv)
    base = args.url.rstrip("/")
    sondas = [
        sonda_pagina("portada", "/", base, opener, reloj, ("text/html",)),
        sonda_pagina("app.js", "/web/js/app.js", base, opener, reloj, ("javascript",)),
        sonda_pagina("manifest", "/manifest.webmanifest", base, opener, reloj, ("manifest+json", "application/json")),
        sonda_pagina("liviana", "/web/lite.html", base, opener, reloj, ("text/html",)),
    ]
    salud, publicada = sonda_health(base, opener, reloj)
    incidentes_s, incidentes = sonda_incidentes(base, opener, reloj)
    sondas += [
        salud,
        sonda_status(base, opener, reloj),
        sonda_observaciones(base, opener, reloj),
        incidentes_s,
        sonda_json("panorama", "/api/panorama", base, opener, reloj),
        sonda_sitemap(base, opener, reloj),
    ]
    inc_id = next((i["id"] for i in incidentes if isinstance(i.get("id"), str) and i["id"]), None)
    if inc_id:
        sondas += [sonda_compartir(base, opener, reloj, inc_id), sonda_tarjeta(base, opener, reloj, inc_id)]
    version = None
    if not args.sin_version:
        repo = version_repo()
        if repo is None:
            _agregar(
                salud,
                "no se pudo leer la versión del repositorio (backend/version.py)",
                "corre la sonda desde el repositorio completo",
            )
        elif publicada is not None:
            comparar_version(salud, publicada, repo)
            version = {"publicada": publicada, "repo": repo, "coincide": publicada == repo}
    problemas = [p for s in sondas for p in s.problemas]
    total_ms = sum(s.ms for s in sondas)
    lenta = max(sondas, key=lambda s: s.ms)
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
                    "mas_lenta": {"ruta": lenta.ruta, "ms": lenta.ms},
                    "version": version,
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
        if version:
            print(f"versión: publicada {version['publicada']} · repo {version['repo']}")
        print(f"más lenta: {lenta.ruta} ({lenta.ms} ms)")
        if problemas:
            print("\nProblemas:")
            for p in problemas:
                print(f"  - {p.texto}")
                print(f"    Arreglo: {p.arreglo}")
        print(f"\nRESULTADO: {resultado} · {total_ms} ms")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
