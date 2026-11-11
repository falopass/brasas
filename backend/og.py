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
import math
import random
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
CANON_TAG = re.compile(r'\s*<link rel="canonical"[^>]*/>')
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

# Paleta de marca E (ICON-E-01): fondo, crema y brasa exactos; el apagado es el de la app.
BG, INK, MUTED, BRASA = "#0d0c0b", "#f4efe7", "#a39a8d", "#ff4b1f"
CREMA = INK
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
    line = f"{detecciones} · primera señal {cuando} (hora de Chile continental)"
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


def _fire_summary(fire: dict) -> str:
    """og:description de la ficha CONAF: «CONAF informa: En combate · 1200,5 ha · comenzó
    24/10 18:30 (hora de Chile continental)»; omite lo que CONAF no haya publicado."""
    parts = [f"CONAF informa: {fire['status_raw']}"] if fire["status_raw"] else []
    if fire["area_ha"]:
        parts.append(f"{fire['area_ha']:.1f} ha".replace(".", ","))
    if fire["started_at"]:
        cuando = cases_mod.parse_utc(fire["started_at"]).astimezone(CHILE_TZ)
        parts.append(f"comenzó {cuando.strftime('%d/%m %H:%M')} (hora de Chile continental)")
    return " · ".join(parts)


def _fire_detail(fire: dict) -> str:
    """La línea de detalle de la tarjeta de la ficha: cuándo lo informó CONAF."""
    if not fire["started_at"]:
        return "Informado por CONAF"
    cuando = cases_mod.parse_utc(fire["started_at"]).astimezone(CHILE_TZ)
    return f"Informado por CONAF el {cuando.strftime('%d/%m %H:%M')} (hora de Chile continental)"


@router.get("/i/{incident_id}")
def share_page(incident_id: str, request: Request, svc: Services = Depends(services)):
    """La página de siempre, pero con la tarjeta del incidente para quien la rastrea.

    Las personas caen en la ficha real gracias a la redirección al fragmento; si el id no
    existe (o ya se fusionó y no quedó alias) se sirve la página tal cual.
    """
    row = _incident_row(svc.db, incident_id)
    if row is None:
        return FileResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})
    return _share_html(row, request, svc)


@router.get("/i/conaf/{fire_id}")
def share_official(fire_id: str, request: Request, svc: Services = Depends(services)):
    """Compartir un incendio CONAF desde el popup del mapa: con incidente enlazado se sirve
    su tarjeta (que ya dibuja el nombre); sin enlace, la ficha oficial dibuja la suya —
    CONAF suele informar un incendio antes de que el satélite agrupe un incidente, justo
    cuando más se comparte. Sin nombre no se inventa nada (igual que `_official`): la
    página genérica de siempre."""
    row = svc.db.one("SELECT * FROM incidents WHERE official_ref = ?", (fire_id,))
    if row is not None:
        return _share_html(row, request, svc)
    fire = svc.db.one("SELECT * FROM official_fires WHERE id = ?", (fire_id,))
    if fire is None or not fire["name"]:
        return FileResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})
    return _fire_share_html(fire, request, svc)


def _share_html(row: dict, request: Request, svc: Services):
    """index.html con las etiquetas Open Graph del incidente y la redirección a su ficha."""
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
    # La página de index quedaría con el canonical de la portada y sin twitter:image:
    # la ficha compartida declara los suyos, propios del incidente.
    tags += (
        f'\n  <meta name="twitter:image" content="{esc(base)}/og/incident/{inc["id"]}.png" />'
        f'\n  <link rel="canonical" href="{esc(base)}/i/{inc["id"]}" />'
        f'\n  <meta http-equiv="refresh" content="0; url=/#/incendio/{inc["id"]}" />'
    )
    page = CANON_TAG.sub("", OG_TAG.sub("", INDEX_HTML.read_text(encoding="utf-8")))
    return HTMLResponse(page.replace("</head>", f"{tags}\n</head>", 1), headers={"Cache-Control": "public, max-age=60"})


def _fire_share_html(fire: dict, request: Request, svc: Services):
    """index.html con las etiquetas Open Graph de un incendio CONAF sin incidente enlazado:
    nombre, estado y superficie ya están en la ficha oficial. La persona cae a su punto
    en el mapa."""
    base = (svc.public_url or str(request.base_url)).rstrip("/")
    en_chile = _en_chile(fire)
    head = f"Incendio «{fire['name']}»"
    where = ", ".join(p for p in (fire["comuna"], fire["region"]) if p)
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
            ("og:description", f"{_fire_summary(fire)}. {aviso}{NO_OFICIAL}"),
            ("og:url", f"{base}/i/conaf/{fire['id']}"),
            ("og:image", f"{base}/og/fire/{fire['id']}.png"),
            ("og:image:width", "1200"),
            ("og:image:height", "630"),
            ("og:image:alt", f"{title}. {NO_OFICIAL}"),
        ]
    )
    destino = f"/#/mapa?lat={fire['lat']}&lon={fire['lon']}&z=12&conaf={fire['id']}"
    tags += (
        f'\n  <meta name="twitter:image" content="{esc(base)}/og/fire/{esc(fire["id"])}.png" />'
        f'\n  <link rel="canonical" href="{esc(base)}/i/conaf/{esc(fire["id"])}" />'
        f'\n  <meta http-equiv="refresh" content="0; url={esc(destino)}" />'
    )
    page = CANON_TAG.sub("", OG_TAG.sub("", INDEX_HTML.read_text(encoding="utf-8")))
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


# ---- Motivo de marca E (ICON-E-01): mapa topográfico cenital oscuro, curvas
# finas naranjas asimétricas y un foco satelital luminoso. No es cartografía real:
# es textura de marca dibujada con un campo de alturas suave y determinista.

_TOPO_SEED = 20261110

# Marching squares: esquinas a=NO(8), b=NE(4), c=SE(2), d=SO(1) → tramos entre bordes
# (norte, este, sur, oeste). Los casos 5 y 10 son sillas: se resuelven con pareo fijo.
_MS = {
    1: (("o", "s"),), 2: (("e", "s"),), 3: (("o", "e"),),
    4: (("n", "e"),), 5: (("n", "e"), ("o", "s")), 6: (("n", "s"),),
    7: (("o", "n"),), 8: (("o", "n"),), 9: (("n", "s"),),
    10: (("o", "n"), ("e", "s")), 11: (("n", "e"),), 12: (("o", "e"),),
    13: (("e", "s"),), 14: (("o", "s"),),
}


def _topo_field(grid: int, seed: int) -> list[list[float]]:
    """Campo de alturas suave y determinista: lomajes gaussianos más una pendiente leve."""
    rng = random.Random(seed)
    bumps = [
        (rng.uniform(-0.25, 1.25), rng.uniform(-0.25, 1.25), rng.uniform(0.12, 0.30),
         rng.uniform(0.4, 1.0) * (1.0 if rng.random() > 0.22 else -0.5))
        for _ in range(7)
    ]
    tx, ty = rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4)
    field = []
    for j in range(grid):
        y = j / (grid - 1)
        row = []
        for i in range(grid):
            x = i / (grid - 1)
            v = x * tx + y * ty
            for bx, by, s, a in bumps:
                d2 = (x - bx) ** 2 + (y - by) ** 2
                if d2 < 9 * s * s:
                    v += a * math.exp(-d2 / (2 * s * s))
            row.append(v)
        field.append(row)
    return field


def _borde(p: tuple[float, float], q: tuple[float, float], v0: float, v1: float, level: float) -> tuple[float, float]:
    t = (level - v0) / (v1 - v0) if v1 != v0 else 0.5
    t = min(1.0, max(0.0, t))
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def _contour_lines(field: list[list[float]], level: float) -> list[list[tuple[float, float]]]:
    """Una iso-línea del campo como cadenas de puntos, en coordenadas de celda."""
    h, w = len(field), len(field[0])
    adj: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for j in range(h - 1):
        f0, f1 = field[j], field[j + 1]
        for i in range(w - 1):
            a, b, c, d = f0[i], f0[i + 1], f1[i + 1], f1[i]
            case = (a > level) * 8 | (b > level) * 4 | (c > level) * 2 | (d > level)
            if case in (0, 15):
                continue
            pts = {
                "n": _borde((i, j), (i + 1, j), a, b, level),
                "e": _borde((i + 1, j), (i + 1, j + 1), b, c, level),
                "s": _borde((i, j + 1), (i + 1, j + 1), d, c, level),
                "o": _borde((i, j), (i, j + 1), a, d, level),
            }
            for e1, e2 in _MS[case]:
                p, q = pts[e1], pts[e2]
                adj.setdefault(p, []).append(q)
                adj.setdefault(q, []).append(p)
    lines: list[list[tuple[float, float]]] = []
    seen: set[frozenset] = set()
    for k0, nbrs in adj.items():
        for p1 in nbrs:
            if frozenset((k0, p1)) in seen:
                continue
            line = [k0, p1]
            seen.add(frozenset((k0, p1)))
            prev, cur = k0, p1
            while True:
                nxt = next((p for p in adj.get(cur, []) if p != prev and frozenset((cur, p)) not in seen), None)
                if nxt is None:
                    break
                line.append(nxt)
                seen.add(frozenset((cur, nxt)))
                if nxt == k0:
                    break
                prev, cur = cur, nxt
            lines.append(line)
    return lines


def _topo_levels(field: list[list[float]], n: int) -> list[float]:
    """Niveles de iso-línea repartidos entre el 8 % y el 92 % del rango del campo."""
    vals = sorted(v for row in field for v in row)
    lo, hi = vals[int(len(vals) * 0.08)], vals[int(len(vals) * 0.92)]
    if hi <= lo:
        return []
    step = (hi - lo) / (n + 1)
    return [lo + step * (i + 1) for i in range(n)]


def _suaviza(pts: list[tuple[float, float]], iters: int = 2) -> list[tuple[float, float]]:
    """Curva Chaikin: cada tramo deja dos puntos; la línea cerrada se suaviza circular."""
    if len(pts) < 3:
        return pts
    closed = math.dist(pts[0], pts[-1]) < 1e-6
    for _ in range(iters):
        out = [] if closed else [pts[0]]
        for i in range(len(pts) - 1):
            p, q = pts[i], pts[i + 1]
            out += [(p[0] * 0.75 + q[0] * 0.25, p[1] * 0.75 + q[1] * 0.25),
                    (p[0] * 0.25 + q[0] * 0.75, p[1] * 0.25 + q[1] * 0.75)]
        if closed:
            p, q = pts[-1], pts[0]
            out += [(p[0] * 0.75 + q[0] * 0.25, p[1] * 0.75 + q[1] * 0.25),
                    (p[0] * 0.25 + q[0] * 0.75, p[1] * 0.25 + q[1] * 0.75)]
        else:
            out.append(pts[-1])
        pts = out
    return pts


def _topo_polylines(box: tuple[float, float, float, float], seed: int, levels: int,
                    grid: int | None = None, smooth: int = 2) -> list[tuple[int, list[tuple[float, float]]]]:
    """Curvas de nivel dentro de `box` en coordenadas de píxel: pares (nivel, puntos)."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    grid = grid or max(16, min(150, round(max(w, h) / 9)))
    field = _topo_field(grid, seed)
    out: list[tuple[int, list[tuple[float, float]]]] = []
    for li, level in enumerate(_topo_levels(field, levels)):
        for line in _contour_lines(field, level):
            pts = [(x0 + px / (grid - 1) * w, y0 + py / (grid - 1) * h) for px, py in line]
            if len(pts) > 2:
                out.append((li, _suaviza(pts, smooth)))
    return out


def _draw_topografia(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], *,
                     seed: int = _TOPO_SEED, levels: int = 8, width: int = 2,
                     alpha: int = 14, index_every: int = 4, index_alpha: int = 28,
                     grid: int | None = None) -> None:
    """El relieve E: curvas finas naranjas sobre el fondo oscuro; cada `index_every`
    sube de intensidad, como las curvas maestras de un mapa."""
    for li, pts in _topo_polylines(box, seed, levels, grid):
        a = index_alpha if li % index_every == 0 else alpha
        draw.line(pts, fill=(255, 75, 31, a), width=width, joint="curve")


def _satellite_dot(draw: ImageDraw.ImageDraw, x: float, y: float, r: float) -> None:
    """El foco satelital: brillo anaranjado por capas y centro caliente crema."""
    for radius, alpha in ((r * 2.4, 20), (r * 1.55, 55), (r * 1.15, 110)):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 75, 31, alpha))
    draw.ellipse((x - r, y - r, x + r, y + r), fill=BRASA)
    inner = r * 0.42
    draw.ellipse((x - inner, y - inner, x + inner, y + inner), fill=CREMA)


def _marca(draw: ImageDraw.ImageDraw) -> None:
    """El bloque de marca de siempre arriba a la izquierda."""
    brand = _font(52, bold=True)
    draw.text((70, 58), "BRASA", font=brand, fill=BRASA)
    draw.text((70 + draw.textlength("BRASA", font=brand) + 16, 58), "Chile", font=_font(52), fill=MUTED)
    draw.rectangle((70, 140, 150, 146), fill=BRASA)


def _pie(draw: ImageDraw.ImageDraw) -> None:
    """El pie fijo de toda tarjeta: el aviso de que no es fuente oficial y los teléfonos."""
    small = _font(27)
    draw.text((70, 524), NO_OFICIAL, font=small, fill=MUTED)
    draw.text((70, 566), "Emergencias: 132 Bomberos · 130 CONAF", font=small, fill=MUTED)


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


def _render_incident(inc: dict, official: dict | None = None) -> bytes:
    """La tarjeta del incidente: el nombre CONAF de titular si existe, si no el estado."""
    status, where = _headline(inc)
    return _render(
        lat=inc["lat"],
        lon=inc["lon"],
        en_chile=_en_chile(inc),
        headline=official["name"] if official else status,
        conaf=_official_line(official) if official else None,
        where=where,
        detail=_detail(inc),
    )


def _render_fire(fire: dict) -> bytes:
    """La misma tarjeta desde la ficha oficial, sin incidente enlazado: el nombre es el
    titular y el detalle dice cuándo lo informó CONAF."""
    en_chile = _en_chile(fire)
    where = ", ".join(p for p in (fire["comuna"], fire["region"]) if p) if en_chile else FUERA_DE_CHILE
    return _render(
        lat=fire["lat"],
        lon=fire["lon"],
        en_chile=en_chile,
        headline=fire["name"],
        conaf=_official_line(fire),
        where=where,
        detail=_fire_detail(fire),
    )


def _render(*, lat: float, lon: float, en_chile: bool, headline: str, conaf: str | None, where: str, detail: str) -> bytes:
    """El lienzo 1200×630 con los textos ya resueltos: marca, titular, línea «CONAF: …»,
    lugar, detalle, minimapa con el punto y el pie fijo."""
    img = Image.new("RGB", (1200, 630), BG)
    draw = ImageDraw.Draw(img, "RGBA")

    # Relieve de marca tenue de fondo y más presente dentro del minimapa.
    _draw_topografia(draw, (0, 0, 1200, 630), levels=9, width=2, alpha=12, index_alpha=24)

    # Minimapa a la derecha: regiones en gris oscuro y el foco del incidente con brillo.
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
    _draw_topografia(draw, (panel[0] + 6, panel[1] + 6, panel[2] - 6, panel[3] - 6),
                     seed=77, levels=7, width=1, alpha=30, index_alpha=50)
    if en_chile:
        x, y = px(lon, lat)
        _satellite_dot(draw, x, y, 9)

    _marca(draw)

    # Con nombre oficial el titular es el incendio («Las Máquinas»): la línea «CONAF: …»
    # bajo él ya dice su estado. Máximo dos líneas; si no cabe, la última cierra con «...»
    # (la fuente de respaldo de Pillow solo cubre Latin-1: «…» no existe ahí).
    headline_lines = _wrap(headline, _font(66, bold=True), 740)
    status_lines = headline_lines[:2]
    if len(headline_lines) > 2:
        status_lines[-1] = status_lines[-1].rstrip(" ,.;:") + "..."
    detail_lines = _wrap(detail, _font(30), 740)
    # El pie es fijo (y=524 y 566): si el detalle crece a más de una línea, todo el
    # bloque sube lo justo para que la última quede sobre él en vez de pisarlo.
    header = 78 * len(status_lines) + (52 if conaf else 0) + (60 if where else 0)
    y_text = min(190, 470 - header - 36 * (len(detail_lines) - 1))
    for line in status_lines:
        draw.text((70, y_text), line, font=_font(66, bold=True), fill=INK)
        y_text += 78
    if conaf:
        draw.text((70, y_text + 6), conaf, font=_font(34), fill=MUTED)
        y_text += 52
    if where:
        # 34 px para la frase larga: a 40 px se metería bajo el minimapa (empieza en x=850).
        line, size = (where, 40) if en_chile else (f"{FUERA_DE_CHILE} · {NO_ALERTA}", 34)
        draw.text((70, y_text + 10), line, font=_font(size), fill=INK)
        y_text += 60
    for line in detail_lines:
        draw.text((70, y_text + 16), line, font=_font(30), fill=MUTED)
        y_text += 36

    _pie(draw)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def _comuna_geom(comuna: geo.Comuna):
    """La geometría real de la comuna en el índice territorial, para realzarla en el minimapa."""
    t = geo.territory()
    for i, c in enumerate(t.comunas):
        if c.code == comuna.code:
            return t._geoms[i]
    return None


def _comuna_bounds(comuna: geo.Comuna) -> tuple[float, float, float, float]:
    """Encuadre del minimapa de comuna: su caja con contexto, sin salir del marco de Chile."""
    w, s, e, n = comuna.bbox
    cx, cy = (w + e) / 2, (s + n) / 2
    lon_w, lat_s, lon_e, lat_n = MAP_BOUNDS
    # El panel es alto (310×550): la comuna con aire lateral, mínimo ~3° de contexto.
    half_lon = min(max((e - w) * 1.6, (n - s) * 0.95, 1.5), (lon_e - lon_w) / 2)
    half_lat = min(half_lon * 1.7, (lat_n - lat_s) / 2)
    cx = min(max(cx, lon_w + half_lon), lon_e - half_lon)
    cy = min(max(cy, lat_s + half_lat), lat_n - half_lat)
    return (cx - half_lon, cy - half_lat, cx + half_lon, cy + half_lat)


def _render_comuna(comuna: geo.Comuna) -> bytes:
    """La tarjeta de una página de comuna: su nombre y región reales, su silueta
    realzada en el minimapa y el mismo pie. Sin cifras: la comuna no se inventa."""
    img = Image.new("RGB", (1200, 630), BG)
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_topografia(draw, (0, 0, 1200, 630), levels=9, width=2, alpha=12, index_alpha=24)

    lon_w, lat_s, lon_e, lat_n = _comuna_bounds(comuna)
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
    _draw_topografia(draw, (panel[0] + 6, panel[1] + 6, panel[2] - 6, panel[3] - 6),
                     seed=77, levels=7, width=1, alpha=30, index_alpha=50)
    geom = _comuna_geom(comuna)
    if geom is not None:
        for poly in ([geom] if geom.geom_type == "Polygon" else list(geom.geoms)):
            points = [px(lon, lat) for lon, lat in poly.exterior.coords]
            if len(points) > 2:
                draw.polygon(points, fill=(255, 75, 31, 26), outline=BRASA, width=2)
    x, y = px(*comuna.center)
    _satellite_dot(draw, x, y, 9)

    _marca(draw)
    draw.text((70, 178), "Riesgo de incendio por comuna", font=_font(30), fill=MUTED)
    name_lines = _wrap(comuna.name, _font(66, bold=True), 740)[:2]
    y = 216
    for line in name_lines:
        draw.text((70, y), line, font=_font(66, bold=True), fill=INK)
        y += 78
    draw.text((70, y + 8), f"{comuna.provincia} · Región {comuna.region}", font=_font(40), fill=INK)
    draw.text((70, y + 74), "Focos de calor satelitales y peligro de incendio del día.",
              font=_font(30), fill=MUTED)

    _pie(draw)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def _card(key: tuple, draw) -> bytes:
    """La tarjeta desde la caché de `_CARDS`, o dibujada y guardada con desalojo del más viejo."""
    png = _CARDS.get(key)
    if png is None:
        png = draw()
        if len(_CARDS) >= _CARDS_MAX:
            _CARDS.pop(next(iter(_CARDS)))
        _CARDS[key] = png
    return png


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
    png = _card(key, lambda: _render_incident(inc, official))
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=600"})


@router.get("/og/fire/{name}")
def share_fire_image(name: str, svc: Services = Depends(services)):
    """La imagen de la tarjeta de un incendio informado por CONAF sin incidente enlazado."""
    if not name.endswith(".png"):
        raise HTTPException(404, "Incendio no encontrado.")
    fire = svc.db.one("SELECT * FROM official_fires WHERE id = ?", (name[:-4],))
    if fire is None or not fire["name"]:
        raise HTTPException(404, "Incendio no encontrado.")
    # Todo lo dibujado va en la clave, igual que en el incidente (mismo defecto que FIX-44):
    # un incendio rebautizado o remido no puede seguir sirviendo la tarjeta vieja.
    key = (fire["id"], fire["name"], fire["status_raw"], fire["area_ha"], fire["comuna"], fire["region"], fire["started_at"])
    png = _card(key, lambda: _render_fire(fire))
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=600"})


@router.get("/og/comuna/{name}")
def share_comuna_image(name: str):
    """La tarjeta de la página de una comuna (`/comuna/<slug>`): nombre, provincia y
    región reales del índice territorial, sin métricas inventadas. Un código que no
    existe da 404, igual que un incidente o una ficha CONAF desconocidos."""
    if not name.endswith(".png"):
        raise HTTPException(404, "Comuna no encontrada.")
    code = name[:-4]
    comuna = geo.territory().by_code.get(int(code)) if code.isdecimal() and len(code) < 8 else None
    if comuna is None:
        raise HTTPException(404, "Comuna no encontrada.")
    key = ("comuna", comuna.code, comuna.name, comuna.provincia, comuna.region)
    png = _card(key, lambda: _render_comuna(comuna))
    # No cambia con los datos del día: solo con la versión del dibujo.
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
