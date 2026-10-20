"""Prueba de humo semanal de las fuentes de datos (OPS-02).

Verifica que cada fuente responda con el formato que BRASA espera, antes de la temporada:
- CONAF incendios: encabezado del CSV público de GEPRIF con las columnas que lee el parser.
- CONAF Botón Rojo: la capa ArcGIS responde con los campos que usa summarize() y filas de comunas.
- GEPRIF: el repositorio público `deigeprif/public` sigue sirviendo `reporte/incendios.csv`.
- GOES: claves recientes (< 60 min) del producto ABI-L2-FDCF en el bucket público de NOAA.
- GOES GLM: el prefijo horario del bucket lista archivos GLM-L2-LCFA (rayos).
- GOES ADPF: el barrido más reciente trae el producto ABI-L2-ADPF (humo).
- FIRMS: consulta mínima de área; con FIRMS_MAP_KEY en el entorno, si no hay se omite.
- Open-Meteo: pronóstico horario con las variables que pide weather.py (temperatura, humedad,
  viento, ráfagas y dirección).
- DMC: RSS de avisos que responde con ítems y un CAP enlazado que sigue siendo CAP 1.2 válido.
- GWIS: el GetCapabilities del WMS declara las capas ecmwf.fwi y nrt.ba (INV-27).
- NOAA ONI: la tabla ASCII del CPC sigue trayendo filas «SEAS YR TOTAL ANOM» que parse_oni() lee.

Cada chequeo imprime OK / OJO / FALLA (u OMITIDO) con el detalle, y anota ::error o ::warning
para que el run lo muestre. Sale 0 solo si no hay OJO ni FALLA. La clave de FIRMS va en la URL:
nunca se imprime ni aparece en errores.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "BRASA-Chile fuentes-salud (+https://github.com/falopass/brasas)"}

CONAF_CSV = "https://raw.githubusercontent.com/deigeprif/public/refs/heads/main/reporte/incendios.csv"
# Columnas que lee parse_fires() de backend/providers/conaf.py.
CONAF_COLUMNS = {
    "id",
    "temporada",
    "nombre",
    "estado",
    "lat",
    "lon",
    "f_inicio",
    "f_control",
    "f_extincion",
    "f_deteccion",
    "f_aviso",
    "f_despacho",
    "sup_total",
    "comuna",
    "region",
    "ambito",
    "comb_inicial",
}

# Capa pública que resume summarize() de backend/providers/conaf.py.
BOTON_ROJO = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/Boton_Rojo/FeatureServer/0/query"
BOTON_ROJO_FIELDS = {"date", "com_id", "horas", "SUM_br_ha", "proportion"}

GOES_BUCKET = "https://noaa-goes19.s3.amazonaws.com/"
GOES_PRODUCT = "ABI-L2-FDCF"
GLM_PRODUCT = "GLM-L2-LCFA"  # rayos, backend/providers/glm.py
ADPF_PRODUCT = "ABI-L2-ADPF"  # humo, backend/providers/smoke.py
GOES_MAX_AGE = timedelta(minutes=60)
_KEY_RE = re.compile(r"<Key>([^<]+)</Key>")
_START_RE = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})")

# Consulta mínima de la API de áreas: un día, una comuna (west, south, east, north).
FIRMS_AREA = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_NOAA21_NRT/-71.6,-34.2,-70.4,-33.2/1"
# Columnas que lee csv_hotspots() de backend/providers/firms.py.
FIRMS_COLUMNS = {"latitude", "longitude", "acq_date", "acq_time", "confidence", "daynight"}

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
# Las mismas variables de HOURLY_VARS/CURRENT_VARS de backend/providers/weather.py.
OPEN_METEO_HOURLY = {"temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m"}

DMC_RSS = "https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php"
CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"

GWIS_WMS = "https://maps.effis.emergency.copernicus.eu/gwis"
# Capas de contexto del mapa verificadas en INV-27: FWI ECMWF y área quemada NRT.
GWIS_CAPAS = {"ecmwf.fwi", "nrt.ba"}

# Tabla ASCII del ONI que lee parse_oni() de backend/providers/noaa.py (dominio público, sin clave).
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"


def get(url: str, n: int = 600_000) -> tuple[int, str]:
    """(status, cuerpo o detalle del error). Nunca se usa con la clave de FIRMS."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            return r.status, r.read(n).decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", 0) or 0, str(e)[:200]


def encabezado_csv(texto: str) -> list[str]:
    """Primera línea del CSV como lista de columnas."""
    first = texto.splitlines()[0] if texto.strip() else ""
    return next(csv.reader(io.StringIO(first)), [])


def faltan(columnas: list[str], requeridas: set[str]) -> list[str]:
    """Columnas requeridas ausentes del encabezado."""
    return sorted(set(requeridas) - set(columnas))


def goes_momento(key: str) -> datetime | None:
    """Instante «_s<año><día juliano><hhmmss>» de una clave FDCF, o None."""
    m = _START_RE.search(key)
    if not m:
        return None
    year, doy, hh, mm, ss = (int(g) for g in m.groups())
    return datetime(year, 1, 1, hh, mm, ss, tzinfo=timezone.utc) + timedelta(days=doy - 1)


def openmeteo_faltantes(data: object) -> list[str]:
    """Variables horarias ausentes o vacías en la respuesta de Open-Meteo."""
    hourly = data.get("hourly") if isinstance(data, dict) else None
    if not isinstance(hourly, dict):
        return sorted(OPEN_METEO_HOURLY | {"time"})
    faltantes = [v for v in sorted(OPEN_METEO_HOURLY | {"time"}) if not isinstance(hourly.get(v), list) or not hourly[v]]
    return faltantes


def rss_items(body: str) -> list[ET.Element]:
    """Ítems del RSS; ET.ParseError si no es XML válido."""
    return list(ET.fromstring(body).iter("item"))


def cap_valido(body: str) -> bool:
    """Un CAP que parse_alert() de backend/providers/dmc.py aceptaría: raíz «alert» con «info»."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return False
    return root.tag.endswith("alert") and root.find(f"{{{CAP_NS}}}info") is not None


def veredicto_conaf(body: str) -> tuple[str, str]:
    """Veredicto del CSV de CONAF a partir de su cuerpo."""
    faltantes = faltan(encabezado_csv(body), CONAF_COLUMNS)
    if faltantes:
        return "FALLA", f"el encabezado cambió: faltan {faltantes}"
    return "OK", f"encabezado con las {len(CONAF_COLUMNS)} columnas que usa el parser"


def check_conaf() -> tuple[str, str]:
    st, body = get(CONAF_CSV)
    if st != 200:
        return "FALLA", f"HTTP {st}: {body[:160]}"
    return veredicto_conaf(body)


def veredicto_goes(listados: list[str], now: datetime, producto: str = GOES_PRODUCT) -> tuple[str, str]:
    """Veredicto de GOES a partir de los XML de listado de las últimas 2 horas."""
    keys = [k for body in listados for k in _KEY_RE.findall(body)]
    if not keys:
        return "OJO", f"sin claves {producto} en las últimas 2 horas (¿producto renombrado o satélite detenido?)"
    momento = goes_momento(sorted(keys)[-1])
    if momento is None:
        return "OJO", "la clave más reciente no trae una fecha reconocible"
    edad_min = int((now - momento).total_seconds() // 60)
    if edad_min > GOES_MAX_AGE.total_seconds() // 60:
        return "OJO", f"último barrido {momento:%Y-%m-%dT%H:%MZ}, hace {edad_min} min"
    return "OK", f"último barrido {momento:%Y-%m-%dT%H:%MZ} (hace {edad_min} min)"


def _listar_bucket(producto: str, now: datetime) -> tuple[list[str], str]:
    """XML de listado de `producto` en las últimas 2 horas; (listas, detalle de error)."""
    listados: list[str] = []
    for hour in (now, now - timedelta(hours=1)):
        prefix = f"{producto}/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/"
        st, body = get(f"{GOES_BUCKET}?list-type=2&prefix={prefix}")
        if st != 200:
            return [], f"HTTP {st} al listar el bucket ({body[:120]})"
        listados.append(body)
    return listados, ""


def check_goes(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(timezone.utc)
    listados, error = _listar_bucket(GOES_PRODUCT, now)
    if error:
        return "FALLA", error
    return veredicto_goes(listados, now)


def check_glm(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(timezone.utc)
    listados, error = _listar_bucket(GLM_PRODUCT, now)
    if error:
        return "FALLA", error
    return veredicto_goes(listados, now, GLM_PRODUCT)


def check_adpf(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(timezone.utc)
    listados, error = _listar_bucket(ADPF_PRODUCT, now)
    if error:
        return "FALLA", error
    return veredicto_goes(listados, now, ADPF_PRODUCT)


def veredicto_boton_rojo(body: str) -> tuple[str, str]:
    """Veredicto del Botón Rojo a partir del JSON de la consulta ArcGIS."""
    try:
        data = json.loads(body)
    except ValueError:
        return "FALLA", "respuesta no JSON"
    if isinstance(data, dict) and data.get("error"):
        code = data["error"].get("code") if isinstance(data["error"], dict) else data["error"]
        return "FALLA", f"la capa devolvió un error ({code})"
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return "FALLA", "la respuesta ya no trae «features»"
    if not features:
        return "OJO", "la capa responde pero no trae comunas (¿fuera de temporada o capa renombrada?)"
    faltantes = faltan(list((features[0].get("attributes") or {}).keys()), BOTON_ROJO_FIELDS)
    if faltantes:
        return "FALLA", f"los campos cambiaron: faltan {faltantes}"
    return "OK", "la capa trae comunas con los campos que usa el resumen"


def check_boton_rojo() -> tuple[str, str]:
    url = (
        BOTON_ROJO
        + "?"
        + urllib.parse.urlencode(
            {
                "where": "1=1",
                "outFields": ",".join(sorted(BOTON_ROJO_FIELDS)),
                "returnGeometry": "false",
                "resultRecordCount": 1,
                "f": "json",
            }
        )
    )
    st, body = get(url)
    if st != 200:
        return "FALLA", f"HTTP {st}: {body[:160]}"
    return veredicto_boton_rojo(body)


def check_geprif() -> tuple[str, str]:
    """El repo público de GEPRIF sigue sirviendo el CSV (fuente de check_conaf también)."""
    st, body = get(CONAF_CSV)
    if st != 200:
        return "FALLA", f"HTTP {st}: {body[:160]}"
    return veredicto_conaf(body)


def check_firms() -> tuple[str, str]:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        return "OMITIDO", "sin FIRMS_MAP_KEY en el entorno"
    try:
        req = urllib.request.Request(FIRMS_AREA.format(key=key), headers=UA)
        with urllib.request.urlopen(req, timeout=40) as r:
            st, body = r.status, r.read(600_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return "FALLA", f"HTTP {e.code} (¿clave vencida o límite de la cuenta?)"
    except Exception as e:
        return "FALLA", f"sin respuesta ({type(e).__name__})"
    return veredicto_firms(st, body)


def veredicto_firms(st: int, body: str) -> tuple[str, str]:
    """Veredicto de FIRMS a partir de (status, cuerpo). La clave nunca entra aquí."""
    if st != 200 or body.lstrip().startswith(("<", "Error", "Invalid", "Wrong")):
        return "FALLA", f"HTTP {st}, respuesta no CSV (¿clave inválida?)"
    faltantes = faltan(encabezado_csv(body), FIRMS_COLUMNS)
    if faltantes:
        return "FALLA", f"el CSV cambió: faltan {faltantes}"
    return "OK", "CSV con las columnas que usa el parser"


def veredicto_openmeteo(body: str) -> tuple[str, str]:
    """Veredicto de Open-Meteo a partir de su cuerpo JSON."""
    try:
        data = json.loads(body)
    except ValueError:
        return "FALLA", "respuesta no JSON"
    faltantes = openmeteo_faltantes(data)
    if faltantes:
        return "FALLA", f"«hourly» cambió: faltan o vienen vacías {faltantes}"
    return "OK", "«hourly» con las variables esperadas"


def check_openmeteo() -> tuple[str, str]:
    url = (
        OPEN_METEO
        + "?"
        + urllib.parse.urlencode(
            {
                "latitude": "-33.45",
                "longitude": "-70.66",
                "forecast_days": 1,
                "hourly": ",".join(sorted(OPEN_METEO_HOURLY)),
                "timezone": "GMT",
            }
        )
    )
    st, body = get(url)
    if st != 200:
        return "FALLA", f"HTTP {st}: {body[:160]}"
    return veredicto_openmeteo(body)


def veredicto_dmc(body: str, descargar_cap) -> tuple[str, str]:
    """Veredicto de DMC: `descargar_cap(url)` devuelve (status, cuerpo) del CAP enlazado."""
    try:
        items = rss_items(body)
    except ET.ParseError as e:
        return "FALLA", f"el RSS no es XML válido ({e})"
    if not items:
        return "OJO", "el RSS respondió pero no trae avisos (¿feed vacío o sin avisos vigentes?)"
    links = [l for l in ((it.findtext("link") or "").strip() for it in items) if l.startswith("http")]
    if not links:
        return "FALLA", f"{len(items)} avisos, ninguno con enlace al CAP"
    # La producción descarga cada CAP: se valida hasta 3 para no confundir un aviso caído
    # con un cambio de formato del feed.
    for link in links[:3]:
        st, cap = descargar_cap(link)
        if st == 200 and cap_valido(cap):
            return "OK", f"{len(items)} avisos en el RSS y el CAP enlazado es válido"
    return "FALLA", f"los CAP enlazados no responden o no son CAP 1.2 ({min(3, len(links))} probados)"


def check_dmc() -> tuple[str, str]:
    st, body = get(DMC_RSS)
    if st != 200:
        return "FALLA", f"HTTP {st}: {body[:160]}"
    return veredicto_dmc(body, get)


def veredicto_gwis(body: str) -> tuple[str, str]:
    """Veredicto del WMS de GWIS a partir del XML del GetCapabilities."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        return "FALLA", f"el GetCapabilities no es XML válido ({e})"
    capas = {
        n.text.strip()
        for capa in root.iter()
        if capa.tag.rsplit("}", 1)[-1] == "Layer"
        for n in capa
        if n.tag.rsplit("}", 1)[-1] == "Name" and n.text
    }
    faltantes = sorted(GWIS_CAPAS - capas)
    if faltantes:
        return "OJO", f"el WMS responde pero ya no declara {faltantes} (¿el JRC las renombró?)"
    return "OK", "GetCapabilities declara ecmwf.fwi y nrt.ba"


def check_gwis() -> tuple[str, str]:
    st, body = get(GWIS_WMS + "?SERVICE=WMS&REQUEST=GetCapabilities")
    if st != 200:
        return "FALLA", f"HTTP {st}: {body[:160]}"
    return veredicto_gwis(body)


def _fila_oni(linea: str) -> bool:
    """La fila es del tipo «JAS 2026 26.9 -0.4» que parse_oni() de noaa.py aceptaría.

    (No se importa parse_oni: este script corre en un job sin las dependencias del backend.)
    """
    partes = linea.split()
    if len(partes) != 4 or not partes[0].isalpha():
        return False
    try:
        int(partes[1])
        float(partes[2])
        float(partes[3])
    except ValueError:
        return False
    return True


def veredicto_oni(body: str) -> tuple[str, str]:
    """Veredicto de la tabla ONI del CPC a partir de su cuerpo ASCII."""
    filas = [l.strip() for l in body.splitlines() if _fila_oni(l)]
    if not filas:
        return "OJO", "la tabla respondió pero ninguna fila calza con «SEAS YR TOTAL ANOM»"
    return "OK", f"{len(filas)} trimestres legibles; último: {filas[-1]}"


def check_noaa_oni() -> tuple[str, str]:
    st, body = get(ONI_URL)
    if st != 200:
        return "FALLA", f"HTTP {st}: {body[:160]}"
    return veredicto_oni(body)


def main() -> int:
    checks = [
        ("CONAF incendios", check_conaf),
        ("CONAF Botón Rojo", check_boton_rojo),
        ("GEPRIF repo", check_geprif),
        ("GOES FDCF", check_goes),
        ("GOES GLM", check_glm),
        ("GOES ADPF", check_adpf),
        ("FIRMS", check_firms),
        ("Open-Meteo", check_openmeteo),
        ("DMC avisos", check_dmc),
        ("GWIS WMS", check_gwis),
        ("NOAA ONI", check_noaa_oni),
    ]
    malos = 0
    for nombre, fn in checks:
        try:
            estado, detalle = fn()
        except Exception as e:
            estado, detalle = "FALLA", f"excepción {type(e).__name__}: {str(e)[:150]}"
        print(f"{estado:8} {nombre}: {detalle}")
        if estado == "FALLA":
            print(f"::error::{nombre}: {detalle}")
        elif estado == "OJO":
            print(f"::warning::{nombre}: {detalle}")
        malos += estado in ("OJO", "FALLA")
    print(f"\n{len(checks) - malos}/{len(checks)} fuentes OK" + ("" if malos else " — todo en orden"))
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main())
