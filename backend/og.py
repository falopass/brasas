"""Tarjeta de vista previa al compartir un incidente (UX-05).

La app enruta por fragmento (#/incendio/<id>) y los rastreadores de WhatsApp, Telegram y
otras apps no lo reciben: sin esta ruta, toda ficha compartida mostraba la tarjeta genérica
del sitio. `/i/<id>` sirve la misma página con las etiquetas Open Graph del incidente y una
redirección hacia la ficha; `/og/incident/<id>.png` dibuja la imagen 1200×630 con Pillow.

Solo se usan campos ya públicos de /api/incidents/{id}: id, estado, comuna, primera hora,
número de detecciones y la ficha CONAF enlazada (nombre, estado y superficie). Nada nuevo
sobre personas.
"""

from __future__ import annotations

import html as html_mod
import io
import json
import re
from functools import lru_cache
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from PIL import Image, ImageDraw, ImageFont

from backend import cases as cases_mod
from backend import incidents as incidents_mod
from backend.routes.common import services
from backend.routes.public import INCIDENT_ID, _incident_public
from backend.services import Services
from backend.settings import ROOT

router = APIRouter(include_in_schema=False)

INDEX_HTML = ROOT / "web" / "index.html"
REGIONES = ROOT / "web" / "data" / "regiones.geojson"
OG_TAG = re.compile(r'\s*<meta property="og:[^"]*"[^>]*/>')
CHILE_TZ = ZoneInfo("America/Santiago")
NO_OFICIAL = "No es una alerta oficial: sigue a SENAPRED (senapred.cl)."

# Títulos del mismo tono que la ficha (INCIDENT en web/js/views/incendio.js), cortos para la tarjeta.
STATUS_TITLE = {
    "anomalia": "Señal de calor",
    "posible": "Posible incendio",
    "reportado": "Posible incendio visto por vecinos",
    "confirmado": "Incendio informado por CONAF",
    "controlado": "Incendio controlado según CONAF",
    "extinguido": "Sin calor nuevo",
}
FIXED_TITLE = "Calor de una fuente fija"

# La tarjeta solo cambia cuando cambia el incidente: la clave lleva todo lo que dibuja
# (estado, comuna, detecciones y última señal); sin la comuna, un incendio que CONAF
# rebautiza o reubica seguía sirviendo el texto viejo hasta el desalojo (FIX-44).
_CARDS: dict[tuple, bytes] = {}
_CARDS_MAX = 256

# Paleta de la app (web/css/app.css): fondo, tinta, apagado y brasa.
BG, INK, MUTED, BRASA = "#0d0c0b", "#ede7dd", "#a39a8d", "#ff4b1f"
SURFACE_2, ASH = "#1e1b18", "#3a352f"

# Chile continental (oeste, sur, este, norte): encuadre fijo del minimapa.
MAP_BOUNDS = (-76.5, -56.5, -66.0, -17.0)


def _incident_row(db, incident_id: str) -> dict | None:
    """La fila vigente del incidente: un enlace viejo puede traer un id ya fusionado (alias)."""
    if not INCIDENT_ID.match(incident_id):
        return None
    return db.one("SELECT * FROM incidents WHERE id = ?", (incident_id,)) or incidents_mod.resolve_merge(db, incident_id)


def _headline(inc: dict) -> tuple[str, str]:
    """(estado en palabras sencillas, «comuna, región» o vacío fuera del territorio)."""
    status = FIXED_TITLE if inc["fixed_source"] else STATUS_TITLE.get(inc["status"], STATUS_TITLE["anomalia"])
    return status, f"{inc['comuna']}, {inc['region']}" if inc["comuna"] else ""


def _detail(inc: dict) -> str:
    n = inc["n_obs"]
    detecciones = "1 detección satelital" if n == 1 else f"{n} detecciones satelitales"
    cuando = cases_mod.parse_utc(inc["first_seen_at"]).astimezone(CHILE_TZ).strftime("%d/%m %H:%M")
    return f"{detecciones} · primera señal {cuando} (hora Chile)"


def _official(svc: Services, inc: dict) -> dict | None:
    """La ficha de CONAF detrás del incidente; solo cuenta si tiene nombre (UX-54):
    el producto nunca inventa uno."""
    if not inc.get("official_ref"):
        return None
    row = svc.db.one("SELECT name, area_ha, status_raw FROM official_fires WHERE id = ?", (inc["official_ref"],))
    return row if row and row["name"] else None


def _official_line(official: dict) -> str:
    """«CONAF: En combate · 1200,5 ha»; sin la superficie cuando CONAF no la informa."""
    line = f"CONAF: {official['status_raw'] or 'informado'}"
    area = official.get("area_ha")
    if area:
        line += f" · {area:.1f} ha".replace(".", ",")
    return line


@router.get("/i/{incident_id}")
def share_page(incident_id: str, request: Request, svc: Services = Depends(services)):
    """La página de siempre, pero con la tarjeta del incidente para quien la rastrea.

    Las personas caen en la ficha real gracias a la redirección al fragmento; si el id no
    existe (o ya se fusionó y no quedó alias) se sirve la página tal cual.
    """
    row = _incident_row(svc.db, incident_id)
    if row is None:
        return FileResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})
    inc = _incident_public(row)
    base = (svc.public_url or str(request.base_url)).rstrip("/")
    status, where = _headline(inc)
    official = _official(svc, inc)
    head = f"Incendio «{official['name']}»" if official else status
    title = f"BRASA · {head}" + (f" en {where}" if where else "")
    esc = lambda v: html_mod.escape(v, quote=True)
    tags = "\n".join(
        f'  <meta property="{k}" content="{esc(v)}" />'
        for k, v in [
            ("og:type", "website"),
            ("og:title", title),
            ("og:description", f"{_detail(inc)}. {NO_OFICIAL}"),
            ("og:url", f"{base}/i/{inc['id']}"),
            ("og:image", f"{base}/og/incident/{inc['id']}.png"),
            ("og:image:width", "1200"),
            ("og:image:height", "630"),
            ("og:image:alt", f"{title}. {NO_OFICIAL}"),
        ]
    )
    tags += f'\n  <meta http-equiv="refresh" content="0; url=/#/incendio/{inc["id"]}" />'
    page = OG_TAG.sub("", INDEX_HTML.read_text(encoding="utf-8"))
    return HTMLResponse(page.replace("</head>", f"{tags}\n</head>", 1), headers={"Cache-Control": "public, max-age=60"})


@lru_cache(maxsize=8)
def _font(size: int, bold: bool = False):
    """DejaVu o FreeSans si el sistema las trae; el contenedor (python:slim) no tiene
    fuentes, así que el respaldo es la que incluye Pillow."""
    for pattern in ("/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf", "/usr/share/fonts/truetype/freefont/FreeSans{}.ttf"):
        try:
            return ImageFont.truetype(pattern.format("Bold" if bold else ""), size)
        except OSError:
            pass
    return ImageFont.load_default(size)


@lru_cache(maxsize=1)
def _chile_rings() -> list[list]:
    """El anillo exterior de cada región, para el minimapa de la tarjeta."""
    data = json.loads(REGIONES.read_text(encoding="utf-8"))
    rings = []
    for feature in data["features"]:
        polygons = feature["geometry"]["coordinates"]
        if feature["geometry"]["type"] == "Polygon":
            polygons = [polygons]
        rings.extend(poly[0] for poly in polygons if poly)
    return rings


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and font.getlength(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + [current]


def _render(inc: dict, official: dict | None = None) -> bytes:
    img = Image.new("RGB", (1200, 630), BG)
    draw = ImageDraw.Draw(img, "RGBA")

    # Minimapa a la derecha: regiones en gris oscuro y el punto del incidente con halo.
    lon_w, lat_s, lon_e, lat_n = MAP_BOUNDS
    panel = (850, 40, 1160, 590)
    scale = min((panel[2] - panel[0]) / (lon_e - lon_w), (panel[3] - panel[1]) / (lat_n - lat_s))
    cx = (panel[0] + panel[2]) / 2 - (lon_w + lon_e) / 2 * scale
    cy = (panel[1] + panel[3]) / 2 + (lat_s + lat_n) / 2 * scale

    def px(lon: float, lat: float) -> tuple[float, float]:
        lon = min(max(lon, lon_w), lon_e)
        lat = min(max(lat, lat_s), lat_n)
        return cx + lon * scale, cy - lat * scale

    for ring in _chile_rings():
        step = max(1, len(ring) // 400)
        points = [px(lon, lat) for lon, lat in ring[::step]]
        if len(points) > 2:
            draw.polygon(points, fill=SURFACE_2, outline=ASH)
    x, y = px(inc["lon"], inc["lat"])
    for radius, alpha in ((34, 36), (20, 90), (9, 255)):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 75, 31, alpha))

    status, where = _headline(inc)
    brand = _font(52, bold=True)
    draw.text((70, 58), "BRASA", font=brand, fill=BRASA)
    draw.text((70 + draw.textlength("BRASA", font=brand) + 16, 58), "Chile", font=_font(52), fill=MUTED)
    draw.rectangle((70, 140, 150, 146), fill=BRASA)

    y_text = 190
    for line in _wrap(status, _font(66, bold=True), 740)[:2]:
        draw.text((70, y_text), line, font=_font(66, bold=True), fill=INK)
        y_text += 78
    if official:
        draw.text((70, y_text + 6), _official_line(official), font=_font(34), fill=MUTED)
        y_text += 52
    if where:
        draw.text((70, y_text + 10), where, font=_font(40), fill=INK)
        y_text += 60
    draw.text((70, y_text + 16), _detail(inc), font=_font(30), fill=MUTED)

    small = _font(27)
    draw.text((70, 524), NO_OFICIAL, font=small, fill=MUTED)
    draw.text((70, 566), "Emergencias: 132 Bomberos · 130 CONAF", font=small, fill=MUTED)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


@router.get("/og/incident/{name}")
def share_image(name: str, svc: Services = Depends(services)):
    """La imagen de la tarjeta: estado, comuna, hora y el aviso de que no es fuente oficial."""
    if not name.endswith(".png"):
        raise HTTPException(404, "Incidente no encontrado.")
    row = _incident_row(svc.db, name[:-4])
    if row is None:
        raise HTTPException(404, "Incidente no encontrado.")
    inc = _incident_public(row)
    official = _official(svc, inc)
    # La clave lleva todo lo que se dibuja, ficha CONAF incluida: un incendio rebautizado o
    # remido no puede seguir sirviendo la tarjeta vieja (mismo defecto que FIX-44).
    key = (
        row["id"],
        row["comuna_code"],
        row["status"],
        row["n_obs"],
        row["last_seen_at"],
        row["fixed_source"],
        row["official_ref"],
        official and (official["name"], official["area_ha"], official["status_raw"]),
    )
    png = _CARDS.get(key)
    if png is None:
        png = _render(inc, official)
        if len(_CARDS) >= _CARDS_MAX:
            _CARDS.pop(next(iter(_CARDS)))
        _CARDS[key] = png
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=600"})
