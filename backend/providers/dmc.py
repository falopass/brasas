"""Avisos, alertas y alarmas de la DMC (MeteoChile) en CAP 1.2.

Fuente oficial de dominio público: el RSS del Sistema de Alerta Temprana de la Dirección
Meteorológica de Chile, que enlaza un archivo CAP 1.2 por aviso.

BRASA muestra solo los avisos que cambian el comportamiento del fuego: **viento** (aviva y arrastra
pavesas) y **calor extremo** (seca el combustible y agota a quien trabaja afuera). La **lluvia
intensa** y la **tormenta eléctrica** también se guardan desde AGUA-07 —sobre suelo quemado son
amenaza de aluvión y de ignición por rayos—, pero solo generan aviso en comunas con cicatriz de
incendio reciente (`alerts.evaluate_dmc`): en el resto son un pronóstico más. Los avisos de
nieve, heladas o marejadas se descartan a propósito: en un día de incendio no cambian qué hacer,
y mostrar todo taparía lo que sí importa.

Cada aviso trae zonas con nombre («Magallanes: Insular Norte») y su polígono; el polígono se cruza
con las comunas reales para poder decirlo en el lugar de cada persona.
"""
from __future__ import annotations

import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.providers import _retry

FEED_URL = "https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php"
SOURCE = "Dirección Meteorológica de Chile (DMC)"
SOURCE_URL = "https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php"
CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"

# Qué se muestra y con qué nombre sencillo. El resto de los eventos se descarta a propósito.
KINDS = {
    "viento": ("viento",),
    "calor": ("calor", "ola de calor", "altas temperaturas", "temperaturas altas",
              "temperaturas maximas"),
    # AGUA-07: los nombres con que la DMC titula sus avisos de tormenta y lluvia en el CAP.
    # «tormenta» va antes: un aviso de tormenta que menciona la lluvia asociada sigue siendo
    # de tormenta (los rayos son la amenaza propia); ambos tipos están restringidos por cicatriz.
    "tormenta": ("tormenta",),
    "lluvia": ("lluvia", "precipitacion", "chubasco", "aguacero"),
}
# Palabras de frío que vetan cualquier clasificación: la DMC titula sus heladas
# «Temperaturas extremas», y sin este freno BRASA las anunciaría como «Calor extremo».
# Comparadas sobre texto ya normalizado (sin tildes): «helad» cubre helada/heladas,
# «minima» cubre mínima/mínimas, «baja» cubre baja/bajas y «nevad» cubre nevada/nevadas.
COLD_WORDS = ("helad", "minima", "baja", "frio", "nieve", "nevad")
KIND_LABELS = {"viento": "Viento", "calor": "Calor extremo", "lluvia": "Lluvia intensa",
               "tormenta": "Tormenta eléctrica"}
# AGUA-07: estos tipos llegan a `dmc_alerts`, pero el aviso solo se crea en comunas con
# cicatriz de incendio reciente (`alerts.evaluate_dmc`). Los demás tipos avisan a toda
# comuna que toca el polígono del aviso.
SCAR_GATED_KINDS = frozenset(("lluvia", "tormenta"))


class DmcError(Exception):
    pass


@dataclass
class Area:
    desc: str
    polygon: list[tuple[float, float]] = field(default_factory=list)  # (lon, lat)


@dataclass
class Alert:
    id: str
    kind: str
    event: str
    headline: str
    severity: str = ""
    urgency: str = ""
    onset: str = ""
    expires: str = ""
    web: str = ""
    areas: list[Area] = field(default_factory=list)

    def as_row(self, areas: list[dict[str, Any]], comunas: list[int], now: str) -> tuple:
        return (self.id, self.kind, self.event, self.headline, self.severity, self.urgency,
                self.onset, self.expires, self.web, areas, comunas, now)


def _fold(text: str) -> str:
    """Minúsculas y sin tildes, para que «Temperaturas» y «temperaturas» pesen lo mismo."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower())
                   if not unicodedata.combining(c))


def kind_of(*texts: str) -> str | None:
    """Tipo de aviso que le importa a BRASA, o None si no cambia el comportamiento del fuego.

    Regla con señal positiva y negativa: se muestra «viento», calor real («calor»,
    «ola de calor», «altas temperaturas», «temperaturas máximas») y, desde AGUA-07, lluvia
    («lluvia», «precipitaciones», «chubascos», «aguaceros») y tormenta; se descarta siempre
    lo que huela a frío («helada», «mínimas», «bajas», «frío», «nieve», «nevada»). La DMC
    titula sus heladas «Temperaturas extremas»: sin el veto, una helada saldría como «Calor
    extremo» con consejos de hidratación. El mismo veto descarta el viento que la DMC emite
    como parte de un aviso de heladas y las precipitaciones que caen como nieve.
    """
    haystack = _fold(" ".join(texts))
    if any(word in haystack for word in COLD_WORDS):
        return None
    for kind, needles in KINDS.items():
        if any(needle in haystack for needle in needles):
            return kind
    return None


def parse_feed(body: str) -> list[dict[str, str]]:
    """Elementos del RSS: título, enlace al CAP, categoría y fecha."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise DmcError(f"El RSS de la DMC no es XML válido ({exc}).") from exc
    items = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        if not link:
            continue
        items.append({"title": (item.findtext("title") or "").strip(), "link": link,
                      "category": (item.findtext("category") or "").strip(),
                      "pub_date": (item.findtext("pubDate") or "").strip()})
    return items


def parse_alert(body: bytes) -> Alert:
    """Un archivo CAP 1.2 → aviso con sus zonas."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise DmcError(f"El CAP de la DMC no es XML válido ({exc}).") from exc
    if not root.tag.endswith("alert"):
        raise DmcError("El archivo de la DMC no es un CAP («alert»).")
    infos = root.findall(f"{{{CAP_NS}}}info")
    if not infos:
        raise DmcError("El CAP de la DMC no trae «info».")
    # CAP 1.2 permite varios «info» en un aviso (por idioma o por grupo de zonas): los datos
    # salen del primero que le importe a BRASA, sin mezclar zonas entre bloques. Si el aviso
    # mezcla tipos, gana el que no está restringido por cicatriz (AGUA-07): un «info» de
    # viento o calor avisa a todas sus comunas, mientras el de lluvia/tormenta solo se queda
    # cuando el CAP no trae otro evento más amplio.
    chosen = None
    gated = None
    for info in infos:
        event = (info.findtext(f"{{{CAP_NS}}}event") or "").strip()
        headline = (info.findtext(f"{{{CAP_NS}}}headline") or "").strip() or event
        kind = kind_of(event, headline)
        if kind is None:
            continue
        if kind in SCAR_GATED_KINDS:
            gated = gated or (info, event, headline, kind)
            continue
        chosen = (info, event, headline, kind)
        break
    chosen = chosen or gated
    if chosen is None:
        raise DmcError("aviso no relevante")
    info, event, headline, kind = chosen

    def text(tag: str) -> str:
        return (info.findtext(f"{{{CAP_NS}}}{tag}") or "").strip()

    areas = []
    for node in info.findall(f"{{{CAP_NS}}}area"):
        desc = (node.findtext(f"{{{CAP_NS}}}areaDesc") or "").strip()
        # Una zona puede traer varios <polygon> (área discontinua): cada uno es un anillo
        # separado del mismo aviso; se suman los puntos ya cerrados por polygons().
        points = []
        for poly in node.findall(f"{{{CAP_NS}}}polygon"):
            points += polygons(poly.text or "")
        areas.append(Area(desc, points))
    return Alert(id=(root.findtext(f"{{{CAP_NS}}}identifier") or "").strip(), kind=kind, event=event,
                 headline=headline, severity=text("severity"), urgency=text("urgency"),
                 onset=text("onset"), expires=text("expires"), web=text("web"), areas=areas)


def polygons(raw: str) -> list[tuple[float, float]]:
    """«lat,lon lat,lon …» de CAP 1.2 → lista (lon, lat) para shapely, cerrando el anillo."""
    points: list[tuple[float, float]] = []
    for pair in raw.split():
        parts = pair.split(",")
        if len(parts) != 2:
            continue
        try:
            lat, lon = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        points.append((lon, lat))
    if len(points) >= 3 and points[0] != points[-1]:
        points.append(points[0])
    return points


async def fetch_alerts(client: httpx.AsyncClient) -> list[Alert]:
    """Lee el RSS y cada CAP, y devuelve solo los avisos que le importan a BRASA (viento,
    calor, lluvia o tormenta; `kind_of` decide)."""
    try:
        feed = await _retry.get(client, FEED_URL)
    except _retry.Failure as exc:
        raise DmcError(f"La DMC no respondió ({exc.detail}).") from exc.cause
    alerts = []
    for item in parse_feed(feed.text):
        if kind_of(item["title"]) is None:
            continue
        try:
            response = await _retry.get(client, item["link"])
        except _retry.Failure:
            continue  # un aviso caído no debe tumbar el resto
        try:
            alerts.append(parse_alert(response.content))
        except DmcError:
            continue
    return alerts
