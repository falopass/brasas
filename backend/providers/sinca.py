"""Estaciones SINCA (Ministerio del Medio Ambiente): el MP2,5 medido más cercano a un punto.

El portal público <https://sinca.mma.gob.cl/> publica `listadomapa2k19`, un JSON sin clave con
las ~119 estaciones de la red (públicas y privadas), su posición y el resumen vigente de cada
parámetro (`tableRow`: valor, ICAP, estado y hora). Una sola descarga cacheada sirve a todos
los lugares, igual que la red EMA de la DMC.

La hora de `tableRow.datetime` es hora de Chile («2026-10-23 22:00»), no UTC: se interpreta
en `America/Santiago`, que resuelve solo el UTC-3/UTC-4 del día. Los valores son **preliminares** hasta la validación del Ministerio del Medio Ambiente de Chile,
como declara el propio portal: por eso `status`/el aviso viajan con el dato. Según la Carta
N° 02853/2026 del MMA (23-11-2026, folio AW002T0016097), los datos no usan licencia Creative
Commons y pueden republicarse citando la autoría con el Ministerio del Medio Ambiente de Chile
(sin API pública por el momento). Si la fuente falla o no hay estación cerca, sale null: jamás
un valor inventado (OFI-10).

Si `SINCA_PROXY_URL` está definida, se intenta antes que la URL directa. Si la
petición en vivo falla, se usa el snapshot de `SINCA_SNAPSHOT_PATH` solo cuando
su `fetched_at` tiene como máximo 12 h (`source_mode` «snapshot», con esa hora
real). Un respaldo más viejo o ausente no se presenta como dato reciente.

Lectura horaria y otros parámetros (OFI-35): cuando `realtime[].info.rows` trae la serie, el
MP2,5 que se informa es el de la última hora (`pm25_period` «horario») y la media móvil de
24 h de `tableRow` viaja aparte (`pm25_24h`). Sin serie se degrada a la media móvil. Se leen
también MP10 y CO (`code` «0004») de la misma estación, con unidad explícita (ppb se pasa a
ppm) y su propia hora; `signal` (humo/polvo/mixto) es solo una pista conservadora.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from backend.geo import haversine_km
from backend.providers import _retry

ROOT = Path(__file__).resolve().parents[2]
RED_URL = "https://sinca.mma.gob.cl/index.php/json/listadomapa2k19/"
SOURCE = "SINCA · Ministerio del Medio Ambiente de Chile (medición preliminar)"
SOURCE_URL = "https://sinca.mma.gob.cl/"
CHILE_TZ = ZoneInfo("America/Santiago")

# El contenedor corre sin privilegios: solo $BRASA_DATA_DIR (/data en la imagen) es escribible.
DEFAULT_SNAPSHOT_PATH = Path(os.getenv("BRASA_DATA_DIR", ROOT / "data")) / "sinca_snapshot.json"
MAX_SNAPSHOT_AGE_HOURS = 12.0

MAX_KM = 60.0          # el MP2,5 es regional: una estación a esa distancia ya describe el aire
MAX_AGE_S = 6 * 3600   # el resumen se actualiza cada hora con ~2 h de latencia

UG_M3 = "\u00b5g/m\u00b3"
MG_M3 = "mg/m\u00b3"
PERIODOS = ("horario", "24h")

# Umbrales conservadores de CO para la señal: 1 ppm ≈ 1,15 mg/m³ a 25 °C y 1 atm.
CO_ALTO_PPM = 1.0
CO_ALTO_MG_M3 = 1.15

_MU = str.maketrans({"\u00b5": "u", "\u03bc": "u"})
_UNIDADES_CANON = {
    "ug/m3": UG_M3, "ug/m\u00b3": UG_M3,
    "ppm": "ppm", "ppmv": "ppm",
    "ppb": "ppb", "ppbv": "ppb",
    "mg/m3": MG_M3, "mg/m\u00b3": MG_M3,
}
_LIMITE_FISICO = {UG_M3: 5000.0, "ppm": 200.0, MG_M3: 230.0}
_UNIDADES_ADMITIDAS = {"pm25": {UG_M3}, "pm10": {UG_M3}, "co": {"ppm", "ppb", MG_M3}}
_CODIGOS = {"pm25": {"PM25"}, "pm10": {"PM10"}, "co": {"0004", "CO"}}
_NUM_TOKEN = r"(?<![\d.,])(-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:[.,]\d+)?)"
_MILES_SIN_COMA_RE = re.compile(r"^-?[1-9]\d{0,2}(?:\.\d{3})+$")
_TOOLTIP_RE = re.compile(
    _NUM_TOKEN + r"\s*([u\u00b5\u03bc]g\s*/\s*m[3\u00b3]|mg\s*/\s*m[3\u00b3]|ppmv|ppm|ppbv|ppb)",
    re.IGNORECASE,
)
_TOOLTIP_NUM_RE = re.compile(_NUM_TOKEN)


class SincaError(Exception):
    pass


def _momento_local(text: Any) -> datetime | None:
    """«2026-10-23 22:00» en hora de Chile → datetime consciente; ilegible → None."""
    if not isinstance(text, str):
        return None
    for formato in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text.strip(), formato).replace(tzinfo=CHILE_TZ)
        except (TypeError, ValueError):
            continue
    return None


def _iso_utc(at: datetime) -> str:
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _momento_utc(text: Any) -> datetime | None:
    """Marca ISO UTC («2026-10-24T01:00:00Z») → datetime en UTC; ilegible → None."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _num(v: Any) -> float | None:
    """Número o texto numérico → float; el portal a veces serializa como string."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _num_cl(v: Any, *, miles_punto: bool = False) -> float | None:
    """Como `_num`, pero entiende la coma decimal chilena («1,5», «1.234,5») y descarta NaN/inf.

    Si `miles_punto=True` (p. ej. lecturas en ppb o tooltips con separador de miles chileno),
    «1.200» se lee como 1200 y no como 1,2, mientras «0.500» sigue siendo 0,5.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        v = v.strip()
        if "," in v:
            v = v.replace(".", "").replace(",", ".")
        elif miles_punto and _MILES_SIN_COMA_RE.match(v):
            v = v.replace(".", "")
    n = _num(v)
    return n if n is not None and math.isfinite(n) else None


def _unidad_canonica(text: Any) -> str | None:
    """«ug/m3», «µg/m³», «ppmv», «ppbv», «mg/m3»… → unidad canónica; desconocida → None."""
    if not isinstance(text, str):
        return None
    return _UNIDADES_CANON.get(text.strip().lower().translate(_MU).replace(" ", ""))


def _medida(valor: float, unidad: str | None, kind: str) -> tuple[float, str] | None:
    """Valor + unidad → (valor, unidad canónica) dentro de rango físico, o None.

    El CO exige unidad explícita: sin ella no se sabe si son ppm o ppb y un valor mal
    interpretado se mostraría 1000 veces más alto o más bajo. ppb se pasa a ppm.
    """
    if unidad is None:
        if kind == "co":
            return None
        unidad = UG_M3
    if unidad not in _UNIDADES_ADMITIDAS[kind]:
        return None
    if unidad == "ppb":
        valor, unidad = valor / 1000.0, "ppm"
    if not math.isfinite(valor) or valor < 0 or valor > _LIMITE_FISICO[unidad]:
        return None
    return valor, unidad


def _unidad_declarada(rt: dict[str, Any], fila: dict[str, Any]) -> str | None:
    info = rt.get("info") if isinstance(rt.get("info"), dict) else {}
    for origen in (fila, info, rt):
        for clave in ("unit", "unidad", "units"):
            unidad = _unidad_canonica(origen.get(clave))
            if unidad:
                return unidad
    return None


def _celdas(fila: Any) -> list[Any] | None:
    """Fila de DataTable de Google Charts (`{"c": [{"v": …}]}`) o lista plana → lista de valores."""
    celdas = fila.get("c") if isinstance(fila, dict) else fila
    if not isinstance(celdas, (list, tuple)):
        return None
    return [c.get("v") if isinstance(c, dict) else c for c in celdas]


def _lectura_horaria(rt: dict[str, Any], kind: str, unidad_decl: str | None) -> dict[str, Any] | None:
    """Última fila válida de `info.rows`: [fecha-hora local, valor, color, tooltip].

    En listadomapa2k19 el valor de la columna 1 puede venir desfasado respecto del que
    muestra el tooltip (columna 3, «8 µg/m³»): si el tooltip trae número con unidad, ese es
    el valor real; la columna 1 solo se usa cuando el tooltip está vacío o no trae número.
    """
    info = rt.get("info")
    filas = info.get("rows") if isinstance(info, dict) else None
    if not isinstance(filas, list):
        return None
    mejor = None
    for fila in filas:
        celdas = _celdas(fila)
        if not celdas or len(celdas) < 2:
            continue
        at = _momento_local(celdas[0])
        if at is None:
            continue
        valor, unidad = None, unidad_decl
        tooltip = celdas[3] if len(celdas) > 3 else None
        if isinstance(tooltip, str) and tooltip.strip():
            m = _TOOLTIP_RE.search(tooltip)
            if m:
                unidad = _unidad_canonica(m.group(2))
                valor = _num_cl(m.group(1), miles_punto=(unidad == "ppb"))
            else:
                m_num = _TOOLTIP_NUM_RE.search(tooltip)
                if m_num:
                    # El tooltip trajo número sin unidad: se usa este valor y nunca `celdas[1]`
                    # (que puede venir desfasado en listadomapa2k19 según INV-26).
                    valor = _num_cl(m_num.group(1), miles_punto=(unidad == "ppb"))
        if valor is None and (not isinstance(tooltip, str) or not _TOOLTIP_NUM_RE.search(tooltip)):
            valor = _num_cl(celdas[1], miles_punto=(unidad == "ppb"))
        if valor is None:
            continue
        medida = _medida(valor, unidad, kind)
        if medida is None:
            continue
        if mejor is None or at >= mejor["at"]:
            mejor = {"at": at, "value": medida[0], "unit": medida[1]}
    return mejor


def _lectura_tabla(fila: dict[str, Any], kind: str, unidad_decl: str | None) -> dict[str, Any] | None:
    valor = _num_cl(fila.get("value"))
    at = _momento_local(fila.get("datetime"))
    if valor is None or at is None:
        return None
    medida = _medida(valor, unidad_decl, kind)
    if medida is None:
        return None
    return {"at": at, "value": medida[0], "unit": medida[1]}


def _leer_parametro(st: dict[str, Any], kind: str) -> dict[str, Any] | None:
    """Lectura vigente de un parámetro de la estación: horaria si hay `info.rows`, si no `tableRow` (24 h).

    Devuelve {"at", "value", "unit", "period", "tabla"}; `tabla` es el valor de `tableRow`
    (media móvil 24 h) aunque la lectura sea horaria.
    """
    mejor = None
    for rt in st.get("realtime") or []:
        if not isinstance(rt, dict) or rt.get("code") not in _CODIGOS[kind]:
            continue
        fila = rt.get("tableRow") if isinstance(rt.get("tableRow"), dict) else {}
        decl = _unidad_declarada(rt, fila)
        tabla = _lectura_tabla(fila, kind, decl)
        lectura = _lectura_horaria(rt, kind, decl)
        if lectura is not None:
            lectura["period"] = "horario"
        elif tabla is not None:
            lectura = {**tabla, "period": "24h"}
        else:
            continue
        lectura["tabla"] = tabla["value"] if tabla else None
        lectura["tabla_at"] = _iso_utc(tabla["at"]) if tabla else None
        if mejor is None or lectura["at"] >= mejor["at"]:
            mejor = lectura
    return mejor


def parse_cgi_hourly(csv_text: str, *, unit: str = UG_M3) -> dict[str, Any] | None:
    """CSV de `apub.tsindico2.cgi` → última lectura horaria válida, o None.

    Columnas separadas por «;»: FECHA (YYMMDD); HORA (HHMM); validados; preliminares; no
    validados. En cada fila se toma el mejor dato disponible (validado > preliminar > no
    validado) y entre filas, la más reciente. La hora es local de Chile; «2400» es la
    medianoche del día siguiente. Devuelve {"value", "observed_at", "quality", "unit"}.
    """
    unidad = _unidad_canonica(unit)
    if unidad is None or not isinstance(csv_text, str):
        return None
    kind = "co" if unidad in ("ppm", "ppb", MG_M3) else "pm25"
    mejor = None
    for linea in csv_text.splitlines():
        campos = [c.strip() for c in linea.split(";")]
        if len(campos) < 3 or not (len(campos[0]) == 6 and campos[0].isdigit()):
            continue
        hora = campos[1]
        if not (len(hora) == 4 and hora.isdigit()):
            continue
        try:
            dia = datetime.strptime(campos[0], "%y%m%d")
            hh, mm = int(hora[:2]), int(hora[2:])
            if not (0 <= mm <= 59 and 0 <= hh <= 24 and (hh < 24 or mm == 0)):
                continue
            local = (dia + timedelta(hours=hh, minutes=mm)).replace(tzinfo=CHILE_TZ)
        except ValueError:
            continue
        for calidad, texto in zip(("validado", "preliminar", "no_validado"), campos[2:5]):
            valor = _num_cl(texto) if texto else None
            medida = _medida(valor, unidad, kind) if valor is not None else None
            if medida is None:
                continue
            if mejor is None or local >= mejor["at"]:
                mejor = {"at": local, "value": medida[0], "quality": calidad, "unit": medida[1]}
            break
    if mejor is None:
        return None
    return {"value": mejor["value"], "observed_at": _iso_utc(mejor["at"]),
            "quality": mejor["quality"], "unit": mejor["unit"]}


def clasificar_senal_aire(pm25: float | None, pm10: float | None, co: float | None,
                          co_unit: str | None) -> str | None:
    """Indicador conservador del origen del material particulado: «humo», «polvo», «mixto» o None.

    Es una pista, no un diagnóstico: usa el cociente MP2,5/MP10 y el CO (el CO alto delata
    combustión). Con datos insuficientes o unidad de CO desconocida no clasifica por CO.
    """
    co_alto = False
    if co is not None:
        if co_unit == "ppm":
            co_alto = co >= CO_ALTO_PPM
        elif co_unit == MG_M3:
            co_alto = co >= CO_ALTO_MG_M3
    razon = pm25 / pm10 if pm25 is not None and pm10 is not None and pm10 > 0 else None
    if pm25 is not None and pm25 >= 25.0 and (co_alto or (razon is not None and razon >= 0.65)):
        return "humo"
    if pm10 is not None and pm10 >= 80.0 and razon is not None and razon < 0.35 and not co_alto:
        return "polvo"
    if (pm25 is not None and pm25 >= 25.0 and pm10 is not None and pm10 >= 80.0
            and razon is not None and 0.35 <= razon < 0.65 and not co_alto):
        return "mixto"
    return None


def latest_network(payload: Any) -> list[dict[str, Any]]:
    """listadomapa2k19 → una fila por estación con su MP2,5 vigente y, si los mide, MP10 y CO.

    Solo cuentan las estaciones con `realtime` para `code == "PM25"` con lectura válida:
    una estación sin PM2,5 vigente no describe el humo del lugar. El MP2,5 es la última hora
    de `info.rows` (`pm25_period` «horario»); sin ella, la media móvil 24 h de `tableRow`
    (`pm25_period` «24h»). MP10 y CO (`code` «0004») son opcionales: la mayoría de las
    estaciones no los mide y esos campos quedan en null. `regionindex` y `calificacion` no se usan.
    """
    if not isinstance(payload, list):
        return []
    out = []
    for st in payload:
        if not isinstance(st, dict):
            continue
        lat, lon = _num(st.get("latitud")), _num(st.get("longitud"))
        if lat is None or lon is None:
            continue
        pm25 = _leer_parametro(st, "pm25")
        if pm25 is None:
            continue
        val = round(pm25["value"], 1)
        pm25_24h = round(pm25["tabla"], 1) if pm25["tabla"] is not None else None
        fila = next((rt.get("tableRow") for rt in st.get("realtime") or []
                     if isinstance(rt, dict) and rt.get("code") == "PM25"
                     and isinstance(rt.get("tableRow"), dict)), {})
        region = (st.get("region") or st.get("region_name") or "").strip()
        row: dict[str, Any] = {
            "code": str(st.get("key") or ""),
            "name": (st.get("nombre") or "").strip(),
            "comuna": (st.get("comuna") or "").strip(),
            "lat": lat, "lon": lon,
            "observed_at": _iso_utc(pm25["at"]),
            "pm25": val,
            "mp25": val,
            "pm25_period": pm25["period"],
            "pm25_24h": pm25_24h,
            "pm25_24h_observed_at": pm25.get("tabla_at"),
            "icap": fila.get("icap"),
            "status": (fila.get("status") or "").strip(),
        }
        pm10 = _leer_parametro(st, "pm10")
        co = _leer_parametro(st, "co")
        row.update({
            "pm10": round(pm10["value"], 1) if pm10 else None,
            "pm10_unit": pm10["unit"] if pm10 else None,
            "pm10_observed_at": _iso_utc(pm10["at"]) if pm10 else None,
            "pm10_period": pm10["period"] if pm10 else None,
            "co": round(co["value"], 3) if co else None,
            "co_unit": co["unit"] if co else None,
            "co_observed_at": _iso_utc(co["at"]) if co else None,
            "co_period": co["period"] if co else None,
        })
        if region:
            row["region"] = region
        out.append(row)
    return out


# El JSON lo carga el propio mapa público del portal; desde datacenters el WAF del MMA
# rechaza agentes que no son navegador — el encabezado emula al visitante del sitio.
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://sinca.mma.gob.cl/"}


def _candidate_urls(proxy_url: str | None = None) -> list[str]:
    """URLs a intentar en orden: primero SINCA_PROXY_URL (si está definida) y luego RED_URL."""
    raw = proxy_url if proxy_url is not None else os.getenv("SINCA_PROXY_URL", "")
    clean = raw.strip()
    if clean and clean != RED_URL:
        return [clean, RED_URL]
    return [RED_URL]


def _resolve_snapshot_path(snapshot_path: str | Path | None = None) -> Path:
    if snapshot_path is not None:
        return Path(snapshot_path)
    env_path = os.getenv("SINCA_SNAPSHOT_PATH", "").strip()
    if env_path:
        return Path(env_path)
    alt_web = ROOT / "web" / "data" / "sinca-snapshot.json"
    if alt_web.is_file() and not DEFAULT_SNAPSHOT_PATH.is_file():
        return alt_web
    return DEFAULT_SNAPSHOT_PATH


def _max_snapshot_hours(max_snapshot_age_hours: float | None = None) -> float:
    if max_snapshot_age_hours is not None:
        return max_snapshot_age_hours
    env_hours = _num(os.getenv("SINCA_MAX_SNAPSHOT_AGE_HOURS"))
    return env_hours if env_hours is not None and env_hours > 0 else MAX_SNAPSHOT_AGE_HOURS


def snapshot_remaining_ttl_s(
    meta: dict[str, Any],
    *,
    max_snapshot_age_hours: float | None = None,
    now: datetime | None = None,
) -> int:
    """Segundos restantes de vigencia para un resultado `snapshot` antes de cumplir el tope de horas."""
    fetched_dt = _momento_utc(meta.get("fetched_at"))
    if fetched_dt is None:
        return 0
    now_utc = now or datetime.now(timezone.utc)
    max_s = _max_snapshot_hours(max_snapshot_age_hours) * 3600
    age_s = (now_utc - fetched_dt).total_seconds()
    if age_s < -900 or age_s >= max_s:
        return 0
    return int(max_s - age_s)


def save_snapshot(
    stations: list[dict[str, Any]],
    *,
    fetched_at: str,
    snapshot_path: str | Path | None = None,
) -> Path | None:
    """Guarda el último listado válido en vivo para servir de respaldo si SINCA bloquea después."""
    if not stations:
        return None
    target = Path(snapshot_path) if snapshot_path is not None else (
        Path(os.getenv("SINCA_SNAPSHOT_PATH", "").strip()) if os.getenv("SINCA_SNAPSHOT_PATH", "").strip() else None
    )
    if target is None:
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"fetched_at": fetched_at, "source_url": RED_URL, "stations": stations}
        target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        return target
    except OSError:
        return None


def _extras_snapshot(st: dict[str, Any], rounded: float) -> dict[str, Any]:
    """Campos de MP2,5 horario, MP10 y CO de una estación del respaldo; los ilegibles salen en null.

    Un snapshot antiguo (solo `pm25`/`observed_at`) guardaba la media móvil 24 h: se lee como tal.
    """
    periodo = st.get("pm25_period") if st.get("pm25_period") in PERIODOS else "24h"
    p24 = _num_cl(st.get("pm25_24h"))
    if p24 is None and periodo == "24h":
        p24 = rounded
    p24_obs_dt = _momento_utc(st.get("pm25_24h_observed_at"))
    extras: dict[str, Any] = {
        "pm25_period": periodo,
        "pm25_24h": round(p24, 1) if p24 is not None and 0 <= p24 <= _LIMITE_FISICO[UG_M3] else None,
        "pm25_24h_observed_at": _iso_utc(p24_obs_dt) if p24_obs_dt is not None else None,
    }
    for campo in ("pm10", "co"):
        valor = _num_cl(st.get(campo))
        unidad = _unidad_canonica(st.get(f"{campo}_unit"))
        obs_dt = _momento_utc(st.get(f"{campo}_observed_at"))
        medida = _medida(valor, unidad, campo) if valor is not None and unidad is not None else None
        if medida is None or unidad == "ppb" or obs_dt is None:
            medida = None
        periodo_param = st.get(f"{campo}_period") if st.get(f"{campo}_period") in PERIODOS else None
        extras.update({
            campo: round(medida[0], 1 if campo == "pm10" else 3) if medida else None,
            f"{campo}_unit": medida[1] if medida else None,
            f"{campo}_observed_at": _iso_utc(obs_dt) if medida and obs_dt else None,
            f"{campo}_period": periodo_param if medida else None,
        })
    return extras


def _normalizar_estacion_snapshot(st: Any) -> dict[str, Any] | None:
    if not isinstance(st, dict):
        return None
    lat = _num(st.get("lat") if "lat" in st else st.get("latitud"))
    lon = _num(st.get("lon") if "lon" in st else st.get("longitud"))
    val = _num(st.get("pm25") if st.get("pm25") is not None else st.get("mp25"))
    if lat is None or lon is None or val is None:
        return None
    obs = str(st.get("observed_at") or "").strip()
    obs_dt = _momento_utc(obs)
    if not obs or obs_dt is None:
        return None
    rounded = round(val, 1)
    row: dict[str, Any] = {
        "code": str(st.get("code") or st.get("key") or ""),
        "name": (st.get("name") or st.get("nombre") or "").strip(),
        "comuna": (st.get("comuna") or "").strip(),
        "lat": lat,
        "lon": lon,
        "observed_at": _iso_utc(obs_dt),
        "pm25": rounded,
        "mp25": rounded,
        "icap": st.get("icap"),
        "status": (st.get("status") or "").strip(),
        **_extras_snapshot(st, rounded),
    }
    if st.get("region"):
        row["region"] = str(st["region"]).strip()
    return row

def load_snapshot(
    snapshot_path: str | Path | None = None,
    *,
    max_snapshot_age_hours: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Lee el snapshot precalculado si existe y su `fetched_at` no supera `max_snapshot_age_hours`."""
    path = _resolve_snapshot_path(snapshot_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    fetched_raw = data.get("fetched_at")
    fetched_dt = _momento_utc(fetched_raw)
    if fetched_dt is None:
        return None
    now_utc = now or datetime.now(timezone.utc)
    max_hours = _max_snapshot_hours(max_snapshot_age_hours)
    age_seconds = (now_utc - fetched_dt).total_seconds()
    if age_seconds < -900 or age_seconds > max_hours * 3600:
        return None
    raw_stations = data.get("stations")
    if not isinstance(raw_stations, list):
        return None
    fetched_iso = fetched_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if raw_stations and isinstance(raw_stations[0], dict) and "realtime" in raw_stations[0]:
        stations = latest_network(raw_stations)
    else:
        stations = [
            norm for item in raw_stations
            if (norm := _normalizar_estacion_snapshot(item)) is not None
        ]
    return {
        "stations": stations,
        "source_mode": "snapshot",
        "fetched_at": fetched_iso,
        "status": "ok" if stations else "unavailable",
    }


def _host_propio() -> str | None:
    """Host del Worker propio al que sí se le entrega `INTERNAL_TOKEN` (rutas `/_internal/`)."""
    for raw in (os.getenv("PUBLIC_BASE_URL"), os.getenv("BRASA_STORAGE_URL")):
        host = urlparse((raw or "").strip()).hostname
        if host:
            return host
    return None


async def _fetch_from_url(client: httpx.AsyncClient, url: str) -> list[dict[str, Any]]:
    headers = dict(_HEADERS)
    token = os.getenv("INTERNAL_TOKEN", "").strip()
    # El token interno solo viaja al propio Worker: un proxy externo con `/_internal/`
    # en la ruta no debe recibirlo.
    if token and "/_internal/" in url and urlparse(url).hostname == _host_propio():
        headers["X-Internal-Token"] = token
    try:
        r = await _retry.get(client, url, headers=headers, timeout=httpx.Timeout(30.0))
    except _retry.Failure as exc:
        raise SincaError(f"El portal SINCA no respondió ({exc.detail}).") from exc.cause
    try:
        payload = r.json()
    except json.JSONDecodeError as exc:
        raise SincaError("La respuesta de SINCA no es JSON.") from exc
    if not isinstance(payload, list):
        raise SincaError("La respuesta de SINCA no tiene el formato esperado.")
    return latest_network(payload)


async def fetch_network_with_meta(
    client: httpx.AsyncClient,
    *,
    proxy_url: str | None = None,
    snapshot_path: str | Path | None = None,
    max_snapshot_age_hours: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Obtiene la red SINCA: intenta primero `SINCA_PROXY_URL` (si está definida), luego `RED_URL`
    directa, y si ambas fallan cae en el snapshot vigente (≤12 h). Cuando una consulta en vivo
    responde con estaciones y hay ruta de snapshot configurada, actualiza el archivo de respaldo."""
    now_utc = now or datetime.now(timezone.utc)
    fetched_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    last_err: SincaError | None = None
    for url in _candidate_urls(proxy_url):
        try:
            stations = await _fetch_from_url(client, url)
            # El archivo no bloquea el event loop: la escritura corre en un hilo aparte.
            await asyncio.to_thread(save_snapshot, stations, fetched_at=fetched_iso, snapshot_path=snapshot_path)
            return {
                "stations": stations,
                "source_mode": "live",
                "fetched_at": fetched_iso,
                "status": "ok",
            }
        except SincaError as exc:
            last_err = exc
    snap = load_snapshot(
        snapshot_path,
        max_snapshot_age_hours=max_snapshot_age_hours,
        now=now_utc,
    )
    if snap is not None:
        return snap
    assert last_err is not None
    raise last_err


async def fetch_network(
    client: httpx.AsyncClient,
    *,
    proxy_url: str | None = None,
    snapshot_path: str | Path | None = None,
    max_snapshot_age_hours: float | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Baja el listado completo de estaciones SINCA con su MP2,5 vigente (sin clave)."""
    meta = await fetch_network_with_meta(
        client,
        proxy_url=proxy_url,
        snapshot_path=snapshot_path,
        max_snapshot_age_hours=max_snapshot_age_hours,
        now=now,
    )
    return meta["stations"]


def _lectura_vigente(st: dict[str, Any], campo: str, now: datetime) -> float | None:
    """MP10/CO de la estación solo si su propia hora está dentro de la ventana de frescura."""
    valor = _num(st.get(campo))
    at = _momento_utc(st.get(f"{campo}_observed_at"))
    if valor is None or at is None:
        return None
    edad = (now - at).total_seconds()
    return valor if -900 <= edad <= MAX_AGE_S else None


def nearest(stations: list[dict[str, Any]], lat: float, lon: float,
            now: datetime | None = None) -> dict[str, Any] | None:
    """La estación con MP2,5 más cercana con lectura fresca (≤ MAX_AGE_S) y a ≤ MAX_KM, o None.

    MP10 y CO se entregan solo si su propia lectura también está dentro de MAX_AGE_S: un dato
    vencido sale en null en vez de mostrarse junto a un MP2,5 reciente.
    """
    now = now or datetime.now(timezone.utc)
    best = None
    for st in stations:
        at = _momento_utc(st.get("observed_at"))
        if at is None:
            continue
        edad = (now - at).total_seconds()
        if edad < -900 or edad > MAX_AGE_S:      # hora futura (reloj malo) o muy vieja
            continue
        d = haversine_km(lat, lon, st["lat"], st["lon"])
        if d <= MAX_KM and (best is None or d < best[0]):
            best = (d, st, at)
    if best is None:
        return None
    d, st, at = best
    periodo = st.get("pm25_period") if st.get("pm25_period") in PERIODOS else "24h"
    pm25_24h = _num(st.get("pm25_24h"))
    icap = st["icap"]
    status = st["status"]
    if pm25_24h is None and periodo == "24h":
        pm25_24h = st["pm25"]
    if periodo == "horario":
        at_24h = _momento_utc(st.get("pm25_24h_observed_at"))
        if at_24h is not None:
            edad_24h = (now - at_24h).total_seconds()
            if edad_24h < -900 or edad_24h > MAX_AGE_S:
                pm25_24h = None
                icap = None
                status = ""
    pm10 = _lectura_vigente(st, "pm10", now)
    co = _lectura_vigente(st, "co", now)
    co_unit = st.get("co_unit") if st.get("co_unit") in ("ppm", MG_M3) else None
    if co is not None and co_unit is None:
        co = None
    # Solo se cruzan MP10 y CO con MP2,5 cuando comparten período explícito y la misma ventana horaria (≤ 1 h).
    pm10_at = _momento_utc(st.get("pm10_observed_at")) if pm10 is not None else None
    co_at = _momento_utc(st.get("co_observed_at")) if co is not None else None
    pm10_comparable = (
        pm10
        if pm10 is not None and st.get("pm10_period") == periodo
        and pm10_at is not None and abs((pm10_at - at).total_seconds()) <= 3600
        else None
    )
    co_comparable = (
        co
        if co is not None and st.get("co_period") == periodo
        and co_at is not None and abs((co_at - at).total_seconds()) <= 3600
        else None
    )
    return {"name": st["name"], "code": st["code"], "comuna": st["comuna"],
            "distance_km": round(d, 1), "lat": st["lat"], "lon": st["lon"],
            "observed_at": _iso_utc(at), "pm25": st["pm25"],
            "pm25_period": periodo, "pm25_24h": pm25_24h,
            "icap": icap, "status": status,
            "pm10": pm10, "pm10_unit": UG_M3 if pm10 is not None else None,
            "pm10_observed_at": st.get("pm10_observed_at") if pm10 is not None else None,
            "pm10_period": st.get("pm10_period") if pm10 is not None else None,
            "co": co, "co_unit": co_unit if co is not None else None,
            "co_observed_at": st.get("co_observed_at") if co is not None else None,
            "co_period": st.get("co_period") if co is not None else None,
            "signal": clasificar_senal_aire(st["pm25"], pm10_comparable, co_comparable, co_unit),
            "preliminar": True}
