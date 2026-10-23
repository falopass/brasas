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
para que el run lo muestre. El informe completo queda en el resumen del run
($GITHUB_STEP_SUMMARY): fuente, estado, qué significa y qué hacer. Sale 1 solo con FALLA: un
OJO (por ejemplo una demora normal de la NOAA) queda en amarillo, y con --estricto recupera
el criterio anterior y también detiene el run. Con --json imprime las filas del informe para
reusarlas desde otro job. La clave de FIRMS va en la URL: nunca se imprime ni aparece en errores.
"""

from __future__ import annotations

import argparse
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
    return con_umbral("CONAF incendios", *veredicto_conaf(body), edad_conaf(body, datetime.now(timezone.utc)))


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
    return con_umbral("CONAF Botón Rojo", *veredicto_boton_rojo(body), edad_boton_rojo(body, datetime.now(timezone.utc)))


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
    return con_umbral("FIRMS", *veredicto_firms(st, body), edad_firms(body, datetime.now(timezone.utc)))


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
    return con_umbral("DMC avisos", *veredicto_dmc(body, get), edad_dmc(body, datetime.now(timezone.utc)))


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
    return con_umbral("NOAA ONI", *veredicto_oni(body), edad_oni(body, datetime.now(timezone.utc)))


# Qué revisar cuando una fuente falla; el detalle de cada una está en docs/FUENTES.md.
QUE_HACER = {
    "CONAF incendios": "comparar el encabezado del CSV con CONAF_COLUMNS y ajustar parse_fires() en backend/providers/conaf.py",
    "CONAF Botón Rojo": "revisar los campos de la capa Boton_Rojo en el catálogo ArcGIS de GEPRIF y ajustar BOTON_ROJO_FIELDS",
    "GEPRIF repo": "verificar que deigeprif/public siga sirviendo reporte/incendios.csv; si se movió, actualizar la URL en backend/providers/conaf.py",
    "GOES FDCF": "una demora puntual de la NOAA se resuelve sola; si se repite, revisar el bucket noaa-goes19 y READ_WINDOW en backend/providers/goes.py",
    "GOES GLM": "revisar el prefijo horario del bucket noaa-goes19 y backend/providers/glm.py",
    "GOES ADPF": "revisar el barrido reciente del bucket noaa-goes19 y backend/providers/smoke.py (de noche no hay detección)",
    "FIRMS": "renovar o revisar FIRMS_MAP_KEY y el producto VIIRS en backend/providers/firms.py",
    "Open-Meteo": "revisar las variables horarias que pide backend/providers/weather.py",
    "DMC avisos": "revisar el RSS de MeteoChile y el parseo CAP en backend/providers/dmc.py",
    "GWIS WMS": "revisar que el GetCapabilities siga declarando ecmwf.fwi y nrt.ba (INV-27)",
    "NOAA ONI": "revisar el formato de la tabla ASCII del CPC y parse_oni() en backend/providers/noaa.py",
}

# AUTO-06: edad máxima admitida del dato más nuevo de cada fuente, en horas. Si el dato
# supera su umbral el veredicto sube a OJO aunque el formato siga bien: un CSV de hace
# cuatro días no es una fuente sana. ONI tolera el atraso editorial propio de la NOAA.
UMBRAL_HORAS = {
    "CONAF incendios": 24,
    "CONAF Botón Rojo": 24,
    "DMC avisos": 6,
    "FIRMS": 6,
    "NOAA ONI": 120 * 24,
}


def edad_conaf(body: str, now: datetime) -> float | None:
    """Horas desde el último `f_deteccion`/`f_inicio` del CSV de CONAF; None si no se fechar."""
    lector = csv.DictReader(io.StringIO(body))
    campos = [c for c in ("f_deteccion", "f_inicio", "f_aviso") if lector.fieldnames and c in lector.fieldnames]
    fechas = []
    for fila in lector:
        for c in campos:
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    d = datetime.strptime((fila.get(c) or "").strip(), fmt)
                    fechas.append(d if d.tzinfo else d.replace(tzinfo=timezone.utc))
                    break
                except ValueError:
                    continue
    return (now - max(fechas)).total_seconds() / 3600 if fechas else None


def edad_boton_rojo(body: str, now: datetime) -> float | None:
    """Horas desde el campo `date` más reciente del JSON ArcGIS del Botón Rojo."""
    try:
        feats = json.loads(body).get("features") or []
        fechas = [datetime.fromtimestamp(int(f["attributes"]["date"]) / 1000, timezone.utc)
                  for f in feats if isinstance(f.get("attributes"), dict) and f["attributes"].get("date")]
    except (ValueError, TypeError, KeyError):
        return None
    return (now - max(fechas)).total_seconds() / 3600 if fechas else None


def edad_dmc(body: str, now: datetime) -> float | None:
    """Horas desde el pubDate más reciente del RSS de avisos de la DMC."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    fechas = []
    for item in root.iter("item"):
        txt = (item.findtext("pubDate") or "").strip()
        if txt:
            try:
                fechas.append(datetime.strptime(txt, "%a, %d %b %Y %H:%M:%S %z"))
            except ValueError:
                continue
    return (now - max(fechas)).total_seconds() / 3600 if fechas else None



def edad_firms(body: str, now: datetime) -> float | None:
    """Horas desde el acq_date/acq_time más reciente del CSV de FIRMS."""
    fechas = []
    for fila in csv.DictReader(io.StringIO(body)):
        try:
            d = fila.get("acq_date") or ""
            h = int(fila.get("acq_time") or 0)
            fechas.append(datetime.strptime(d, "%Y-%m-%d").replace(
                hour=h // 100, minute=h % 100, tzinfo=timezone.utc))
        except (ValueError, TypeError):
            continue
    return (now - max(fechas)).total_seconds() / 3600 if fechas else None


def edad_oni(body: str, now: datetime) -> float | None:
    """Horas desde el fin del trimestre de la última fila ONI (atrás editorial ya tolerado)."""
    meses = {"JFM": 1, "FMA": 2, "MAM": 3, "AMJ": 4, "MJJ": 5, "JJA": 6,
             "JAS": 7, "ASO": 8, "SON": 9, "OND": 10, "NDJ": 11, "DJF": 12}
    filas = [l.split() for l in body.splitlines() if _fila_oni(l)]
    if not filas:
        return None
    try:
        seas, yr = filas[-1][0], int(filas[-1][1])
        fin = datetime(yr, meses[seas], 1, tzinfo=timezone.utc) + timedelta(days=32)
        fin = datetime(fin.year, fin.month, 1, tzinfo=timezone.utc)  # primer día del mes siguiente
        return (now - fin).total_seconds() / 3600
    except (ValueError, KeyError, IndexError):
        return None


def con_umbral(nombre: str, estado: str, detalle: str, edad_h: float | None, now_fmt: str = "") -> tuple[str, str]:
    """Aplica el umbral de AUTO-06: sana → OJO si el dato está viejo o no se fecha."""
    umbral = UMBRAL_HORAS.get(nombre)
    if umbral is None or estado == "FALLA":
        return estado, detalle
    if edad_h is None:
        return "OJO", f"{detalle}; no se pudo fechar el dato"
    if edad_h > umbral:
        return "OJO", f"{detalle}; el dato más nuevo tiene {edad_h:.0f} h (tope {umbral} h)"
    return estado, f"{detalle} (edad {edad_h:.1f} h)"


CHECKS = [
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


def fila(nombre: str, estado: str, detalle: str) -> dict[str, str]:
    """Una fila del informe con su acción sugerida; nunca queda sin «qué hacer»."""
    return {
        "fuente": nombre,
        "estado": estado,
        "detalle": detalle,
        "que_hacer": QUE_HACER.get(nombre, f"revisar `docs/FUENTES.md` · {nombre}"),
    }


def informe_markdown(filas: list[dict[str, str]]) -> str:
    """Tabla del resumen del run: fuente, estado, detalle y qué hacer, más el total de OK."""
    iconos = {"OK": "✅", "OJO": "⚠️", "FALLA": "❌", "OMITIDO": "➖"}

    def celda(texto: str) -> str:
        return str(texto).replace("|", "\\|")

    lineas = [
        "## Salud de las fuentes",
        "",
        "| Fuente | Estado | Detalle | Qué hacer |",
        "|---|---|---|---|",
    ]
    lineas += [
        f"| {celda(f['fuente'])} | {iconos.get(f['estado'], '➖')} {f['estado']} | {celda(f['detalle'])} | {celda(f['que_hacer'])} |"
        for f in filas
    ]
    ok = sum(1 for f in filas if f["estado"] == "OK")
    lineas += ["", f"**{ok}/{len(filas)} fuentes OK**"]
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prueba de humo de las fuentes de datos de BRASA.")
    parser.add_argument("--estricto", action="store_true", help="un OJO también detiene el run (criterio anterior)")
    parser.add_argument("--json", action="store_true", help="imprime las filas del informe como JSON, sin el texto")
    args = parser.parse_args(argv)

    filas = []
    for nombre, fn in CHECKS:
        try:
            estado, detalle = fn()
        except Exception as e:
            estado, detalle = "FALLA", f"excepción {type(e).__name__}: {str(e)[:150]}"
        filas.append(fila(nombre, estado, detalle))

    if args.json:
        print(json.dumps(filas, ensure_ascii=False, indent=2))
    else:
        for f in filas:
            print(f"{f['estado']:8} {f['fuente']}: {f['detalle']}")
            if f["estado"] == "FALLA":
                print(f"::error::{f['fuente']}: {f['detalle']}")
            elif f["estado"] == "OJO":
                print(f"::warning::{f['fuente']}: {f['detalle']}")

    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        try:
            with open(resumen, "a", encoding="utf-8") as fh:
                fh.write(informe_markdown(filas))
        except OSError:
            pass  # el informe es un extra del run: nunca tumba el chequeo

    ok = sum(1 for f in filas if f["estado"] == "OK")
    omitidas = sum(1 for f in filas if f["estado"] == "OMITIDO")
    malos = len(filas) - ok - omitidas
    if not args.json:
        extra = f" ({omitidas} omitida{'s' if omitidas != 1 else ''})" if omitidas else ""
        print(f"\n{ok}/{len(filas)} fuentes OK{extra}" + ("" if malos else " — todo en orden"))
    graves = sum(1 for f in filas if f["estado"] == "FALLA" or (args.estricto and f["estado"] == "OJO"))
    return 1 if graves else 0


if __name__ == "__main__":
    sys.exit(main())
