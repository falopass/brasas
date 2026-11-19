"""SEO-05: páginas HTML indexables por comuna (`/comuna/<slug>`).

Cada comuna responde a la búsqueda «riesgo de incendio en <comuna>» con HTML renderizado
en el servidor, sin JS obligatorio: nombre, región, riesgo del día con fuente y hora,
Botón Rojo si aplica, enlaces a la app y los teléfonos de emergencia. Indexable solo si la
comuna tiene datos de riesgo del día; sin datos → `noindex` y texto honesto. El código
numérico redirige 301 al slug. Todo el contenido dinámico va escapado.

PROD-07: en el piloto Biobío se agrega el estado mensual del Calendario de Quemas 2026-2027
de CONAF, solo como información oficial y siempre con enlace para consultar o avisar.
"""
from __future__ import annotations

import html
import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.geo import territory
from backend.providers import conaf
from backend.routes.common import services
from backend.services import Services

router = APIRouter()
CHILE_TZ = ZoneInfo("America/Santiago")
PUBLIC_BASE = (os.environ.get("PUBLIC_BASE_URL") or "https://brasa-chile.ddiegosebastianbb.workers.dev").rstrip("/")
_NIVEL = {"bajo": "bajo", "moderado": "moderado", "alto": "alto", "extremo": "extremo"}

# PROD-07 · Calendario de Quemas CONAF 2026-2027, Región del Bío Bío (resolución N° 1148,
# publicada en Las Últimas Noticias el 14-10-2026; PDF verificado el 19-11-2026). Solo se
# muestra el estado mensual oficial: nunca atribuye un foco a una quema ni autoriza fuego.
_QUEMAS_MESES = ("octubre", "noviembre", "diciembre", "enero", "febrero", "marzo",
                 "abril", "mayo", "junio", "julio", "agosto", "septiembre")
_QUEMAS_INICIO = date(2026, 10, 1)
_QUEMAS_FIN = date(2027, 9, 30)
_QUEMAS_REGION_URL = "https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/region-del-bio-bio/"
_QUEMAS_PDF_URL = "https://www.conafprevencionincendios.cl/wp-content/uploads/Biobio.pdf"
_QUEMAS_AVISO_URL = "https://www.conaf.cl/incendios/prevencion-y-mitigacion/uso-del-fuego/"
_QUEMAS_GRUPOS = {
    "arauco": {
        "comunas": (8201, 8202, 8203, 8204, 8205, 8206, 8207),
        "estados": ("A", "A", "A", "R", "R", "A", "A", "V", "V", "V", "V", "A"),
    },
    "concepcion_metropolitano": {
        "comunas": (8101, 8102, 8103, 8105, 8106, 8107, 8108, 8110, 8111, 8112),
        "estados": ("A", "A", "A", "R", "R", "A", "R", "R", "R", "R", "R", "R"),
    },
    "florida_santa_juana": {
        "comunas": (8104, 8109),
        "estados": ("A", "A", "A", "R", "R", "A", "A", "V", "V", "V", "V", "A"),
    },
    "provincia_biobio": {
        "comunas": (8302, 8303, 8304, 8305, 8306, 8307, 8308, 8309, 8310, 8311, 8312, 8313, 8314),
        "estados": ("A", "A", "A", "R", "R", "A", "A", "V", "V", "V", "V", "A"),
    },
    "los_angeles": {
        "comunas": (8301,),
        "estados": ("A", "A", "A", "R", "R", "A", "A", "R", "R", "R", "R", "R"),
    },
}
_QUEMAS_PILOTO = {code: (clave, grupo) for clave, grupo in _QUEMAS_GRUPOS.items() for code in grupo["comunas"]}
_QUEMAS_NOTA_LA = "Prohibido Quemar D.S. 4/2019 desde el 15 de abril al 30 de septiembre"

FIRES_WINDOW_DAYS = 30  # mismo criterio que la API de comuna (OFI-29)
INCENDIOS_CACHE_TTL_S = 300


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _fmt_ha(v: float) -> str:
    """Hectáreas al estilo de la app: un decimal bajo 10 ha, separador de miles con punto."""
    dec = 1 if v < 10 else 0
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fecha_cl(stamp: str | None) -> str:
    """Marca ISO a «dd-mm HH:MM» en hora de Chile; sin marca legible devuelve «sin dato»."""
    if not stamp:
        return "sin dato"
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(CHILE_TZ)
    except ValueError:
        return "sin dato"
    return dt.strftime("%d-%m %H:%M")


def slug(name: str) -> str:
    """Slug de URL: minúsculas, sin tildes, espacios como guiones (p. ej. «San José de Maipo» → san-jose-de-maipo)."""
    folded = unicodedata.normalize("NFKD", name.casefold())
    limpio = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", limpio)).strip("-")


_slug = slug  # alias: dentro de la ruta el parámetro también se llama «slug»


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


def _quema_estado(comuna, hoy: str) -> dict | None:
    """Estado del mes en curso para una comuna piloto; None fuera del piloto Biobío."""
    try:
        fecha = date.fromisoformat(hoy)
    except (TypeError, ValueError):
        return None
    pilot = _QUEMAS_PILOTO.get(comuna.code)
    if pilot is None:
        return None
    clave, grupo = pilot
    if fecha < _QUEMAS_INICIO:
        return {"fuera": "antes"}
    if fecha > _QUEMAS_FIN:
        return {"fuera": "despues"}
    idx = (fecha.year * 12 + fecha.month) - (_QUEMAS_INICIO.year * 12 + _QUEMAS_INICIO.month)
    estado = grupo["estados"][idx]
    if clave == "los_angeles" and idx == 6:  # abril de Los Ángeles está partido por el D.S. 4/2019
        estado = "A" if fecha.day <= 14 else "R"
    return {"clave": clave, "mes": _QUEMAS_MESES[idx], "mes_idx": idx, "dia": fecha.day, "estado": estado}


def _quema_nota(info: dict) -> str:
    """Texto legal que la celda roja del calendario muestra para ese periodo."""
    idx = info["mes_idx"]
    if idx in (3, 4):  # enero y febrero: D.S. 276/1980 en todos los grupos piloto
        return "Prohibido Quemar D.S. 276/1980"
    if info["clave"] == "concepcion_metropolitano" and idx >= 6:
        return "Prohibido Quemar D.S. 6/2018 desde el 01 abril al 30 de septiembre"
    if info["clave"] == "los_angeles" and ((idx == 6 and info["dia"] >= 15) or idx > 6):
        return _QUEMAS_NOTA_LA
    return ""


def _cuerpo_quemas(comuna, hoy: str) -> str:
    """Sección «Uso del fuego y quemas»: solo piloto Biobío y solo como calendario oficial."""
    info = _quema_estado(comuna, hoy)
    if info is None:
        return ""
    partes = [
        '<section class="quemas" aria-labelledby="quemas-h">',
        '<h2 id="quemas-h">Uso del fuego y quemas</h2>',
    ]
    if info.get("fuera") == "despues":
        partes.append(
            "<p>El calendario de CONAF 2026-2027 ya venció: cubre de octubre de 2026 a septiembre de 2027. "
            "BRASA no tiene el calendario siguiente, así que confirma el estado vigente en CONAF.</p>"
        )
    elif info.get("fuera") == "antes":
        partes.append(
            "<p>El calendario de CONAF 2026-2027 todavía no está vigente. Confirma el estado actual en CONAF.</p>"
        )
    elif info["clave"] == "los_angeles" and info["mes_idx"] == 6:
        partes.append(
            "<p>En abril, el calendario de CONAF 2026-2027 divide esta comuna: del 1 al 14 marca restricciones "
            f"para quemas y del 15 al 30 prohíbe el uso del fuego ({_esc(_QUEMAS_NOTA_LA)}).</p>"
        )
    else:
        mes = _esc(info["mes"])
        if info["estado"] == "R":
            texto = f"En {mes}, el calendario de CONAF 2026-2027 prohíbe el uso del fuego para quemas en esta comuna."
        elif info["estado"] == "A":
            texto = f"En {mes}, el calendario de CONAF 2026-2027 marca restricciones para quemas en esta comuna."
        else:
            texto = f"En {mes}, el calendario de CONAF 2026-2027 no marca una restricción adicional para quemas en esta comuna."
        nota = _quema_nota(info)
        if nota:
            texto += f" Nota del calendario: {_esc(nota)}."
        partes.append(f"<p>{texto}</p>")
    partes.append(
        "<p>CONAF puede suspender el uso del fuego según el clima y los incendios. La autorización la da CONAF "
        "o el municipio: antes de quemar, hay que consultar y confirmar en CONAF.</p>"
    )
    partes.append(
        '<p class="fuentes">Fuentes: '
        f'<a href="{_esc(_QUEMAS_REGION_URL)}" target="_blank" rel="noopener">CONAF: calendario de quemas, Región del Bío Bío</a> · '
        f'<a href="{_esc(_QUEMAS_PDF_URL)}" target="_blank" rel="noopener">Calendario 2026-2027 (PDF)</a> · '
        f'<a href="{_esc(_QUEMAS_AVISO_URL)}" target="_blank" rel="noopener">CONAF: uso del fuego y aviso de quema</a>.</p>'
    )
    partes.append("</section>")
    return "".join(partes)


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
.quemas { margin: 22px 0 0; padding: 14px; background: var(--surface); border-radius: 14px; }
.quemas h2 { margin: 0 0 8px; font-family: "Anybody", "Arial", sans-serif; font-weight: 800;
  font-stretch: 112%; font-size: 1.25rem; line-height: 1.15; }
.quemas p { margin: 8px 0 0; font-size: .9375rem; }
.quemas .fuentes { font-size: .8125rem; color: var(--muted); }
.incendios { margin: 24px 0 0; }
.incendios h2 { margin: 0; font-family: "Anybody", "Arial", sans-serif; font-weight: 800;
  font-stretch: 112%; font-size: 1.35rem; line-height: 1.15; }
.incendios > p { margin: 10px 0 0; font-size: .9375rem; }
.fires { margin: 6px 0 0; padding: 0; list-style: none; }
.fires li { padding: 8px 0; border-bottom: 1px solid var(--surface-3); font-size: .9375rem; }
.fires li:last-child { border-bottom: 0; }
.fires li small { color: var(--muted); }
.incendios .fuentes { font-size: .8125rem; color: var(--muted); }
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


def _incendios_comuna(svc: Services, comuna) -> dict:
    """Incendios de la comuna para la página: los de CONAF y las señales satelitales de hoy.

    Dos bloques con fuentes distintas: `conaf` son los incendios que CONAF informa (se
    muestran tal cual, con su estado oficial, nunca «confirmados» por BRASA) y `satelite`
    cuenta los incidentes de BRASA con señal hoy — calor visto por satélite, no un incendio
    confirmado. Caché de 5 min por comuna: la página es pública y no debe repetir el filtro
    geográfico en cada visita de un crawler.
    """
    key = f"comuna-incendios:v1:{comuna.code}"
    cached = svc.db.cache_get(key)
    if cached:
        return cached
    since = (datetime.now(timezone.utc) - timedelta(days=FIRES_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    w, s, e, n = comuna.bbox
    rows = svc.db.query(
        "SELECT name, status, status_raw, started_at, area_ha, lat, lon FROM official_fires "
        "WHERE started_at >= ? AND status != 'extinguido' "
        "AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? ORDER BY started_at DESC",
        (since, s, n, w, e),
    )
    t = territory()
    matches = [
        r for r in rows
        if r["status"] != "extinguido"
        and (hit := t.locate(r["lat"], r["lon"])) and hit.code == comuna.code
    ]
    fires = [
        {
            "name": r["name"],
            "status": r["status"],
            "status_raw": r["status_raw"],
            "started_at": r["started_at"],
            "area_ha": r["area_ha"],
        }
        for r in matches[:10]
    ]
    hoy_start = datetime.now(CHILE_TZ).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    inc = svc.db.one(
        "SELECT COUNT(*) AS n, MAX(last_seen_at) AS ultima FROM incidents "
        "WHERE comuna_code = ? AND fixed_source = 0 AND status NOT IN ('extinguido', 'descartado') "
        "AND last_seen_at >= ?",
        (comuna.code, hoy_start),
    )
    conaf_run = svc.db.one("SELECT MAX(finished_at) AS t FROM ingest_runs WHERE product = 'CONAF_INCENDIOS' AND ok = 1")
    block = {
        "conaf": {"total": len(matches), "fires": fires, "actualizado": conaf_run["t"] if conaf_run else None},
        "satelite": {"n": inc["n"] or 0, "ultima": _fecha_cl(inc["ultima"]), "ingesta": svc.db.kv_get("last_ingest_at")},
    }
    svc.db.cache_set(key, block, INCENDIOS_CACHE_TTL_S)
    return block


def _cuerpo_incendios(comuna, bloque: dict) -> str:
    """Sección «Incendios en <comuna>»: qué informa CONAF y qué ve el satélite hoy."""
    name = _esc(comuna.name)
    fires = bloque["conaf"]["fires"]
    total = bloque["conaf"]["total"]
    partes = [
        '<section class="incendios" aria-labelledby="incendios-h">',
        f'<h2 id="incendios-h">Incendios en {name}</h2>',
    ]
    if fires:
        items = []
        for f in fires:
            estado = _esc(f.get("status_raw") or f["status"])
            cuando = _esc(_fecha_cl(f["started_at"]))
            ha = f" · {_esc(_fmt_ha(f['area_ha']))} ha" if f.get("area_ha") else ""
            items.append(f"<li><strong>{_esc(f['name'])}</strong> — {estado}, {cuando}{ha}</li>")
        if total > len(fires):
            items.append(f"<li>… y {total - len(fires)} más</li>")
        partes.append(
            f"<p><strong>CONAF informa {_esc(total)} {_esc(_plural(total, 'incendio activo', 'incendios activos'))} "
            f"en los últimos {FIRES_WINDOW_DAYS} días:</strong></p>"
        )
        partes.append('<ul class="fires">' + "".join(items) + "</ul>")
    else:
        if bloque["conaf"]["actualizado"]:
            partes.append(
                f"<p>CONAF no informa incendios activos en esta comuna en los últimos {FIRES_WINDOW_DAYS} días. "
                "Que no aparezca no significa que no haya fuego: sigue los avisos de SENAPRED.</p>"
            )
        else:
            partes.append(
                "<p>BRASA aún no recibe el reporte de incendios de CONAF; no podemos decir si hay "
                "incendios en la comuna. Ante la duda, llama al 130 o al 132.</p>"
            )
    n = bloque["satelite"]["n"]
    if bloque["satelite"]["ingesta"]:
        if n:
            partes.append(
                f"<p><strong>Satélite (BRASA):</strong> {n} {_esc(_plural(n, 'incidente con señal de calor', 'incidentes con señal de calor'))} hoy en la comuna. "
                "Los satélites ven calor, no confirman incendios.</p>"
            )
        else:
            partes.append("<p><strong>Satélite (BRASA):</strong> ningún incidente con señal de calor hoy en la comuna.</p>")
    else:
        partes.append(
            "<p><strong>Satélite (BRASA):</strong> BRASA aún no tiene datos satelitales de hoy para esta comuna.</p>"
        )
    partes.append(
        f'<p class="fuentes">CONAF actualizado {_esc(_fecha_cl(bloque["conaf"]["actualizado"]))} · '
        f'Satélite: última señal {_esc(bloque["satelite"]["ultima"])}, ingesta {_esc(_fecha_cl(bloque["satelite"]["ingesta"]))} (hora de Chile). '
        f'Fuente CONAF: <a href="{_esc(conaf.FIRES_PAGE_URL)}">{_esc(conaf.FIRES_SOURCE)}</a>.</p>'
    )
    partes.append("</section>")
    return "".join(partes)


def _pagina(comuna, riesgo, boton_rojo, hoy: str, incendios: dict) -> str:
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
    cuerpo_incendios = _cuerpo_incendios(comuna, incendios)
    cuerpo_quemas = _cuerpo_quemas(comuna, hoy)
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
<meta property="og:site_name" content="BRASA Chile">
<meta property="og:locale" content="es_CL">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{_esc(canon)}">
<meta property="og:image" content="{PUBLIC_BASE}/og/comuna/{comuna.code}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/png">
<meta property="og:image:alt" content="BRASA Chile — riesgo de incendio en {name}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/web/icons/favicon.ico" sizes="16x16 32x32 48x48">
<link rel="icon" href="/web/icons/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/web/icons/apple-touch-icon.png" sizes="180x180">
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
{cuerpo_incendios}
{cuerpo_quemas}
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
    incendios = _incendios_comuna(svc, comuna)
    return HTMLResponse(
        _pagina(comuna, riesgo, boton, hoy, incendios),
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
