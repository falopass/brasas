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
_NIVEL = {"bajo": "bajo", "moderado": "moderado", "alto": "alto", "extremo": "extremo"}


def slug(name: str) -> str:
    """Slug de URL: minúsculas, sin tildes, espacios como guiones (p. ej. «San José de Maipo» → san-jose-de-maipo)."""
    folded = unicodedata.normalize("NFKD", name.casefold())
    limpio = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", limpio)).strip("-")


_slug = slug  # alias: dentro de la ruta el parámetro también se llama «slug»


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


_CSS = """
@font-face { font-family: "Anybody"; src: url("/web/vendor/fonts/anybody-latin-standard-normal.woff2") format("woff2"); font-weight: 600 900; font-stretch: 60% 130%; font-display: swap; }
@font-face { font-family: "Public Sans"; src: url("/web/vendor/fonts/public-sans-latin-wght-normal.woff2") format("woff2"); font-weight: 300 900; font-display: swap; }
:root { color-scheme: dark;
  --bg: #0d0c0b; --surface: #151311; --surface-2: #1e1b18; --surface-3: #2a2622;
  --ink: #ede7dd; --muted: #a39a8d; --brasa: #ff4b1f;
  --risk-bajo: #1a7f46; --risk-moderado: #8f7a00; --risk-alto: #c2571e; --risk-extremo: #e50d06; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font-family: "Public Sans", system-ui, sans-serif; font-size: 1rem; line-height: 1.45;
  -webkit-font-smoothing: antialiased; }
a { color: inherit; }
:focus-visible { outline: 3px solid var(--brasa); outline-offset: 2px; }
.top { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  max-width: 640px; margin: 0 auto; padding: 16px 20px 0; }
.brand { font-family: "Anybody", "Arial", sans-serif; font-weight: 800; font-stretch: 112%;
  font-size: 1.25rem; letter-spacing: .02em; text-decoration: none; color: var(--brasa); }
.top .tag { font-size: .75rem; font-weight: 600; color: var(--muted); }
.wrap { max-width: 640px; margin: 0 auto; padding: 20px 20px 40px; }
.eyebrow { margin: 0; font-size: .75rem; font-weight: 650; letter-spacing: .08em;
  text-transform: uppercase; color: var(--muted); }
h1 { margin: 6px 0 0; font-family: "Anybody", "Arial", sans-serif; font-weight: 800;
  font-stretch: 112%; font-size: clamp(1.75rem, 1.4rem + 1.8vw, 2.4rem); line-height: 1.08; }
.level { margin: 22px 0 0; }
.level .word { margin: 0; font-family: "Anybody", "Arial", sans-serif; font-weight: 800;
  font-size: clamp(2.6rem, 13vw, 3.6rem); line-height: 1; color: var(--rc, var(--muted)); }
.level .score { margin: 6px 0 0; font-size: .9375rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.lv-bajo { --rc: var(--risk-bajo); } .lv-moderado { --rc: var(--risk-moderado); }
.lv-alto { --rc: var(--risk-alto); } .lv-extremo { --rc: var(--risk-extremo); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px;
  margin: 22px 0 0; padding: 0; }
.stats div { background: var(--surface); border-radius: 14px; padding: 12px 14px; }
.stats dt { font-size: .75rem; font-weight: 650; color: var(--muted); }
.stats dd { margin: 4px 0 0; font-family: "Anybody", "Arial", sans-serif; font-weight: 800;
  font-stretch: 68%; font-size: 1.5rem; line-height: 1; font-variant-numeric: tabular-nums; }
.stats dd small { font-family: "Public Sans", system-ui, sans-serif; font-stretch: 100%;
  font-size: .8rem; font-weight: 600; color: var(--muted); }
.meta { margin: 14px 0 0; font-size: .8125rem; color: var(--muted); }
.boton-rojo { margin: 16px 0 0; padding: 12px 14px; border: 2px solid var(--risk-extremo);
  border-radius: 14px; font-size: .9375rem; }
.boton-rojo strong { color: var(--risk-extremo); }
.empty { margin: 22px 0 0; padding: 14px; background: var(--surface); border-radius: 14px; }
.links { display: grid; gap: 10px; margin: 26px 0 0; }
.card-link { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  min-height: 52px; padding: 12px 16px; background: var(--surface-2); border-radius: 14px;
  font-weight: 650; text-decoration: none; }
.card-link span { color: var(--brasa); font-weight: 800; }
.card-link:active { background: var(--surface-3); }
.emergency { margin: 28px 0 0; padding: 14px 16px; border: 2px solid var(--brasa);
  border-radius: 14px; }
.emergency p { margin: 0; font-size: .9375rem; }
.emergency .tels { display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.emergency .tels a { display: inline-flex; align-items: baseline; gap: 8px; min-height: 48px;
  padding: 8px 18px; background: var(--brasa); border-radius: 999px; color: #120c09;
  font-family: "Anybody", "Arial", sans-serif; font-weight: 800; font-size: 1.3rem;
  text-decoration: none; }
.emergency .tels a span { font-family: "Public Sans", system-ui, sans-serif;
  font-size: .8rem; font-weight: 700; }
.foot { max-width: 640px; margin: 0 auto; padding: 0 20px 28px; font-size: .8125rem; color: var(--muted); }
.foot a { text-underline-offset: 3px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
@media print { body { background: #fff; color: #000; }
  .stats div, .empty, .card-link { background: #f2efe9; }
  .eyebrow, .meta, .stats dt, .level .score, .foot { color: #444; } }
"""


def _pagina(comuna, riesgo, boton_rojo, hoy: str) -> str:
    name = _esc(comuna.name)
    region = _esc(comuna.region)
    canon = f"{PUBLIC_BASE}/comuna/{slug(comuna.name)}"
    con_datos = riesgo is not None
    nivel = _NIVEL.get(riesgo["level"] or "", riesgo["level"]) if con_datos else None
    # Solo los cuatro niveles conocidos reciben clase de color: cualquier otro valor cae al estilo base.
    nivel_css = nivel if nivel in _NIVEL.values() else "otro"
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
        stats = []
        if riesgo["tmax"] is not None:
            stats.append(f"<div><dt>Máxima</dt><dd>{riesgo['tmax']:.0f}<small> °C</small></dd></div>")
        if riesgo["rhmin"] is not None:
            stats.append(f"<div><dt>Humedad mín.</dt><dd>{riesgo['rhmin']:.0f}<small> %</small></dd></div>")
        if riesgo["windmax"] is not None:
            stats.append(f"<div><dt>Viento máx.</dt><dd>{riesgo['windmax']:.0f}<small> km/h</small></dd></div>")
        if riesgo["fwi"] is not None:
            stats.append(f"<div><dt>FWI</dt><dd>{riesgo['fwi']:.0f}<small> {_esc(riesgo['fwi_level'] or '—')}</small></dd></div>")
        cuerpo_riesgo = (
            f'<section class="level lv-{nivel_css}">'
            f'<p class="word">{_esc(str(nivel).capitalize())}</p>'
            f'<p class="score">puntaje {int(riesgo["score"])}</p></section>'
            + (f'<dl class="stats">{"".join(stats)}</dl>' if stats else "")
            + f'<p class="meta">Pronóstico calculado a las {_esc(riesgo["computed_at"])} UTC · fuente: Open-Meteo, cálculo BRASA.</p>'
        )
        if boton_rojo:
            cuerpo_riesgo += (
                f'<p class="boton-rojo"><strong>Botón Rojo de CONAF:</strong> {int(boton_rojo["hours"])} horas de condición '
                "pronosticada hoy. Son condiciones favorables para incendios, no un incendio en curso.</p>"
            )
    else:
        cuerpo_riesgo = (
            '<p class="empty">Todavía no hay pronóstico de riesgo para esta comuna hoy. '
            "Que BRASA no muestre datos no significa que no haya peligro ni fuego.</p>"
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
<meta property="og:image" content="{PUBLIC_BASE}/web/icons/og.png">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")}</script>
<style>{_CSS}</style>
</head>
<body>
<header class="top">
<a class="brand" href="/">BRASA</a>
<span class="tag">Riesgo por comuna</span>
</header>
<main class="wrap">
<p class="eyebrow">Región {region} · hoy {_esc(hoy)}</p>
<h1>Riesgo de incendio en {name}</h1>
{cuerpo_riesgo}
<nav class="links">
<a class="card-link" href="/#/riesgo">Ver el mapa de riesgo por comuna<span aria-hidden="true">→</span></a>
<a class="card-link" href="/focos">Ver los focos de calor recientes<span aria-hidden="true">→</span></a>
</nav>
<aside class="emergency">
<p><strong>BRASA no es una alerta oficial.</strong> Si ves fuego o humo, llama:</p>
<p class="tels"><a href="tel:130">130 <span>CONAF</span></a><a href="tel:132">132 <span>Bomberos</span></a></p>
</aside>
</main>
<footer class="foot"><a href="/web/datos.html">Datos abiertos</a> · <a href="/web/preguntas.html">Preguntas frecuentes</a></footer>
</body>
</html>"""


def _hoy() -> str:
    return datetime.now(CHILE_TZ).date().isoformat()


def _riesgo_hoy(svc: Services, code: int, hoy: str):
    return svc.db.one(
        "SELECT * FROM risk_daily WHERE comuna_code = ? AND date = ?", (code, hoy))


@router.get("/comuna/{slug}", include_in_schema=False)
def pagina_comuna(slug: str, svc: Services = Depends(services)):
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
