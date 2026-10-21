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
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from PIL import Image, ImageDraw, ImageFont

from backend import cases as cases_mod
from backend import geo
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
FUERA_DE_CHILE = "Fuera de Chile"
NO_ALERTA = "no es una alerta de BRASA"

# Títulos del mismo tono que la ficha (INCIDENT en web/js/views/incendio.js), cortos para la tarjeta.
STATUS_TITLE = {
    "anomalia": "Señal de calor",
    "posible": "Posible incendio",
    "reportado": "Posible incendio visto por vecinos",
    "confirmado": "Incendio informado por CONAF",
    "controlado": "Incendio controlado según CONAF",
    "extinguido": "Sin calor nuevo",
    "descartado": "Descartado",
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


def _en_chile(inc: dict) -> bool:
    """El punto cae en una comuna chilena (el mismo índice territorial que usa la ingesta)."""
    return geo.territory().locate(inc["lat"], inc["lon"]) is not None


def _headline(inc: dict) -> tuple[str, str]:
    """(estado en palabras sencillas, «comuna, región» o «fuera de Chile»)."""
    status = FIXED_TITLE if inc["fixed_source"] else STATUS_TITLE.get(inc["status"], STATUS_TITLE["anomalia"])
    if not _en_chile(inc):
        return status, "fuera de Chile"
    return status, f"{inc['comuna']}, {inc['region']}" if inc["comuna"] else ""


def _hace(delta: timedelta) -> str:
    """Edad en palabras para la tarjeta: «hace 10 minutos», «hace 3 horas», «hace 2 días»."""
    minutes = max(0.0, delta.total_seconds() / 60)
    if minutes < 60:
        n, unit = max(1, round(minutes)), "minuto"
    elif minutes < 24 * 60:
        n, unit = round(minutes / 60), "hora"
    else:
        n, unit = round(minutes / (60 * 24)), "día"
    return f"hace {n} {unit}" + ("s" if n != 1 else "")


def _detail(inc: dict) -> str:
    n = inc["n_obs"]
    detecciones = "1 detección satelital" if n == 1 else f"{n} detecciones satelitales"
    first = cases_mod.parse_utc(inc["first_seen_at"])
    cuando = first.astimezone(CHILE_TZ).strftime("%d/%m %H:%M")
    line = f"{detecciones} · primera señal {cuando} (hora Chile)"
    # COMPARTIR-02: la tarjeta también dice desde cuándo no hay calor nuevo, para que un
    # incendio de hace tres días no se comparta como si estuviera pasando ahora.
    last_raw = inc.get("last_seen_at")
    if not last_raw:
        return line
    last = cases_mod.parse_utc(last_raw)
    age = datetime.now(timezone.utc) - last
    if inc["status"] == "extinguido" or age > timedelta(hours=6):
        return f"{line} · sin calor nuevo {_hace(age)}"
    if last - first > timedelta(minutes=30):
        return f"{line} · última señal {_hace(age)}"
    return line


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
    en_chile = _en_chile(inc)
    status, where = _headline(inc)
    official = _official(svc, inc)
    head = f"Incendio «{official['name']}»" if official else status
    if en_chile:
        title = f"BRASA · {head}" + (f" en {where}" if where else "")
        aviso = ""
    else:
        title = f"BRASA · {FUERA_DE_CHILE} · {head}"
        aviso = f"Este punto no está en territorio chileno: {NO_ALERTA}. "
    esc = lambda v: html_mod.escape(v, quote=True)
    tags = "\n".join(
        f'  <meta property="{k}" content="{esc(v)}" />'
        for k, v in [
            ("og:type", "website"),
            ("og:title", title),
            ("og:description", f"{_detail(inc)}. {aviso}{NO_OFICIAL}"),
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
    en_chile = _en_chile(inc)
    if en_chile:
        x, y = px(inc["lon"], inc["lat"])
        for radius, alpha in ((34, 36), (20, 90), (9, 255)):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 75, 31, alpha))

    status, where = _headline(inc)
    brand = _font(52, bold=True)
    draw.text((70, 58), "BRASA", font=brand, fill=BRASA)
    draw.text((70 + draw.textlength("BRASA", font=brand) + 16, 58), "Chile", font=_font(52), fill=MUTED)
    draw.rectangle((70, 140, 150, 146), fill=BRASA)

    status_lines = _wrap(status, _font(66, bold=True), 740)[:2]
    detail_lines = _wrap(_detail(inc), _font(30), 740)
    # El pie es fijo (y=524 y 566): si el detalle crece a más de una línea, todo el
    # bloque sube lo justo para que la última quede sobre él en vez de pisarlo.
    header = 78 * len(status_lines) + (52 if official else 0) + (60 if where else 0)
    y_text = min(190, 470 - header - 36 * (len(detail_lines) - 1))
    for line in status_lines:
        draw.text((70, y_text), line, font=_font(66, bold=True), fill=INK)
        y_text += 78
    if official:
        draw.text((70, y_text + 6), _official_line(official), font=_font(34), fill=MUTED)
        y_text += 52
    if where:
        # 34 px para la frase larga: a 40 px se metería bajo el minimapa (empieza en x=850).
        line, size = (where, 40) if en_chile else (f"{FUERA_DE_CHILE} · {NO_ALERTA}", 34)
        draw.text((70, y_text + 10), line, font=_font(size), fill=INK)
        y_text += 60
    for line in detail_lines:
        draw.text((70, y_text + 16), line, font=_font(30), fill=MUTED)
        y_text += 36

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
        # «hace 10 minutos» envejece aunque la fila no cambie: la frase en la clave
        # regenera la tarjeta justo cuando su texto cambiaría (COMPARTIR-02).
        _detail(inc),
    )
    png = _CARDS.get(key)
    if png is None:
        png = _render(inc, official)
        if len(_CARDS) >= _CARDS_MAX:
            _CARDS.pop(next(iter(_CARDS)))
        _CARDS[key] = png
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=600"})
