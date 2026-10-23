"""SEO-05: páginas HTML indexables por comuna (`/comuna/<slug>`).

Cada comuna responde a la búsqueda «riesgo de incendio en <comuna>» con HTML renderizado
en el servidor, sin JS obligatorio: nombre, región, riesgo del día con fuente y hora,
Botón Rojo si aplica, enlaces a la app y los teléfonos de emergencia. Indexable solo si la
comuna tiene datos de riesgo del día; sin datos → `noindex` y texto honesto. El código
numérico redirige 301 al slug. Todo el contenido dinámico va escapado.
"""
from __future__ import annotations

import html
import json
import os
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.geo import territory
from backend.routes.common import services
from backend.services import Services

router = APIRouter()
CHILE_TZ = ZoneInfo("America/Santiago")
PUBLIC_BASE = (os.environ.get("PUBLIC_BASE_URL") or "https://brasa-chile.ddiegosebastianbb.workers.dev").rstrip("/")
NOT_OFFICIAL = "BRASA no es una alerta oficial: si ves fuego o humo llama al 130 (CONAF) o al 132 (Bomberos)."

_NIVEL = {"bajo": "bajo", "moderado": "moderado", "alto": "alto", "extremo": "extremo"}


def slug(name: str) -> str:
    """Slug de URL: minúsculas, sin tildes, espacios como guiones (p. ej. «San José de Maipo» → san-jose-de-maipo)."""
    folded = unicodedata.normalize("NFKD", name.casefold())
    limpio = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", limpio)).strip("-")


_slug = slug  # alias: dentro de la ruta el parámetro también se llama «slug»


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


def _pagina(comuna, riesgo, boton_rojo, hoy: str) -> str:
    name = _esc(comuna.name)
    region = _esc(comuna.region)
    canon = f"{PUBLIC_BASE}/comuna/{slug(comuna.name)}"
    con_datos = riesgo is not None
    nivel = _NIVEL.get(riesgo["level"] or "", riesgo["level"]) if con_datos else None
    title = f"Riesgo de incendio en {comuna.name} hoy — BRASA"
    desc = (
        f"Peligro de incendio hoy en {comuna.name} ({comuna.region}): nivel {nivel} según el "
        "pronóstico de BRASA con datos de Open-Meteo y CONAF. No es una alerta oficial."
        if con_datos else
        f"BRASA aún no tiene el riesgo de hoy para {comuna.name} ({comuna.region}). "
        "No es una alerta oficial: si ves fuego, 130 o 132."
    )[:160]
    robots = "index,follow" if con_datos else "noindex,follow"
    jsonld = {
        "@context": "https://schema.org", "@type": "Place", "name": comuna.name,
        "containedInPlace": {"@type": "AdministrativeArea", "name": f"Región {comuna.region}, Chile"},
        "geo": {"@type": "GeoCoordinates", "latitude": comuna.center[1], "longitude": comuna.center[0]},
        "url": canon,
    }
    cuerpo_riesgo = ""
    if con_datos:
        filas = [f"<strong>Nivel {_esc(nivel)}</strong> (puntaje {int(riesgo['score'])})"]
        if riesgo["tmax"] is not None:
            filas.append(f"hasta {riesgo['tmax']:.0f} °C")
        if riesgo["rhmin"] is not None:
            filas.append(f"humedad {riesgo['rhmin']:.0f} %")
        if riesgo["windmax"] is not None:
            filas.append(f"viento {riesgo['windmax']:.0f} km/h")
        if riesgo["fwi"] is not None:
            filas.append(f"FWI {riesgo['fwi']:.0f} ({_esc(riesgo['fwi_level'] or '—')})")
        cuerpo_riesgo = (
            f"<p>{' · '.join(filas)}.</p>"
            f"<p><small>Pronóstico calculado a las {_esc(riesgo['computed_at'])} UTC · fuente: Open-Meteo, cálculo BRASA.</small></p>"
        )
        if boton_rojo:
            cuerpo_riesgo += (
                f"<p><strong>Botón Rojo de CONAF:</strong> {int(boton_rojo['hours'])} horas de condición "
                "pronosticada hoy. Son condiciones favorables para incendios, no un incendio en curso.</p>"
            )
    else:
        cuerpo_riesgo = (
            "<p>Todavía no hay pronóstico de riesgo para esta comuna hoy. Que BRASA no muestre datos "
            "no significa que no haya peligro ni fuego.</p>"
        )
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{_esc(canon)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{_esc(canon)}">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")}</script>
</head>
<body>
<main>
<p><a href="/">← BRASA</a></p>
<h1>Riesgo de incendio en {name}</h1>
<p>Región {region} · hoy {_esc(hoy)}</p>
{cuerpo_riesgo}
<ul>
<li><a href="/#/riesgo">Ver el mapa de riesgo por comuna</a></li>
<li><a href="/focos">Ver los focos de calor recientes</a></li>
</ul>
<p><strong>{_esc(NOT_OFFICIAL)}</strong></p>
<footer><small><a href="/web/datos.html">Datos abiertos</a> · <a href="/web/preguntas.html">Preguntas frecuentes</a></small></footer>
</main>
</body>
</html>"""


def _hoy() -> str:
    return datetime.now(CHILE_TZ).date().isoformat()


def _riesgo_hoy(svc: Services, code: int, hoy: str):
    return svc.db.one(
        "SELECT * FROM risk_daily WHERE comuna_code = ? AND date = ?", (code, hoy))


@router.get("/comuna/{slug}", include_in_schema=False)
def pagina_comuna(slug: str, svc: Services = Depends(services)) -> HTMLResponse | RedirectResponse:
    t = territory()
    if slug.isdecimal() and len(slug) < 8:  # el código numérico resuelve y redirige al slug canónico
        c = t.by_code.get(int(slug))
        if c is None:
            raise HTTPException(404, "No existe una comuna con ese código.")
        return RedirectResponse(f"/comuna/{_slug(c.name)}", status_code=301)
    slug = _slug(slug)
    comuna = next((c for c in t.comunas if _slug(c.name) == slug), None)
    if comuna is None:
        raise HTTPException(404, f"No conocemos una comuna «{slug}». Revisa el nombre o usa el mapa.")
    hoy = _hoy()
    riesgo = _riesgo_hoy(svc, comuna.code, hoy)
    boton = svc.db.one("SELECT * FROM boton_rojo WHERE comuna_code = ? AND date = ?", (comuna.code, hoy)) if riesgo else None
    return HTMLResponse(
        _pagina(comuna, riesgo, boton, hoy),
        headers={"Cache-Control": "public, max-age=1800"},
    )


@router.get("/sitemap-comunas.xml", include_in_schema=False)
def sitemap_comunas(svc: Services = Depends(services)) -> HTMLResponse:
    """Sitemap de las páginas por comuna: solo las que tienen riesgo del día (indexables)."""
    hoy = _hoy()
    t = territory()
    con_datos = {r["comuna_code"] for r in svc.db.query("SELECT comuna_code FROM risk_daily WHERE date = ?", (hoy,))}
    urls = [
        f"  <url><loc>{PUBLIC_BASE}/comuna/{_slug(c.name)}</loc><lastmod>{hoy}</lastmod></url>"
        for c in t.comunas if c.code in con_datos
    ]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"
    return HTMLResponse(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


_slug = slug  # alias interno para no confundir con el parámetro de ruta
