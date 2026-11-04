"""Genera ``web/data/vegetacion-sequedad.json`` (RISK-11).

Pide el verdor de la vegetación (NDVI del producto MOD13Q1 de NASA, píxel de
250 m y compuesto de 16 días) al servicio público de subconjuntos de ORNL.
Por cada región y por cada comuna forestal clave usa un solo punto: el centro
del índice territorial. La anomalía es el verdor de la última imagen frente al
promedio de la misma fecha en los años anteriores. Si falta el píxel o el
promedio, el valor queda en null: no se publica un cero inventado.

La ficha cita «NASA MODIS / VIIRS · Índice de verdor satelital (NDVI)» y
https://modis.gsfc.nasa.gov/data/dataprod/mod13.php. El número sale de MODIS
(MOD13Q1); VIIRS es la familia de satélites polares que la cita nombra.

Uso: python scripts/actualizar_sequedad_vegetacion.py
"""

from __future__ import annotations

import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDICE = ROOT / "web" / "data" / "comunas-index.json"
SALIDA = ROOT / "web" / "data" / "vegetacion-sequedad.json"
ORNL = "https://modis.ornl.gov/rst/api/v1/MOD13Q1"
FUENTE = "NASA MODIS / VIIRS · Índice de verdor satelital (NDVI)"
FUENTE_URL = "https://modis.gsfc.nasa.gov/data/dataprod/mod13.php"
TOPE_BYTES = 8192
ANOS_ATRAS = 10
MIN_ANOS = 5
# Por debajo de esto el porcentaje explota (suelo desnudo o píxel vacío).
VERDOR_MINIMO = 0.05
# Bandas de BRASA, no una clase de la NASA: cuánto baja el verdor frente a su promedio.
UMBRAL_MUY_SECA = -20
UMBRAL_SECA = -8

# Un punto de muestra por región: comuna con vegetación, no la capital urbana
# cuando el centro comunal es ciudad o desierto puro.
MUESTRA_REGION = {
    "Arica y Parinacota": 15201,  # Putre
    "Tarapacá": 1405,  # Pica
    "Antofagasta": 2104,  # Taltal
    "Atacama": 3301,  # Vallenar
    "Coquimbo": 4301,  # Ovalle
    "Valparaíso": 5801,  # Quilpué
    "Metropolitana": 13501,  # Melipilla
    "O'Higgins": 6310,  # Santa Cruz
    "Maule": 7104,  # Empedrado
    "Ñuble": 16107,  # Quillón
    "Biobío": 8109,  # Santa Juana
    "La Araucanía": 9208,  # Purén
    "Los Ríos": 14108,  # Panguipulli
    "Los Lagos": 10101,  # Puerto Montt
    "Aysén": 11101,  # Coyhaique
    "Magallanes": 12101,  # Punta Arenas
}

# Comunas donde el fuego de interfaz ha importado. El centro es el del índice.
COMUNAS_CLAVE = (
    5101,  # Valparaíso
    5109,  # Viña del Mar
    5801,  # Quilpué
    5804,  # Villa Alemana
    8107,  # Penco
    8104,  # Florida
    8109,  # Santa Juana
    16107,  # Quillón
    7101,  # Talca
    7102,  # Constitución
    7104,  # Empedrado
    7201,  # Cauquenes
    9201,  # Angol
    9208,  # Purén
    9211,  # Victoria
    14101,  # Valdivia
    14108,  # Panguipulli
    10101,  # Puerto Montt
)

MACROZONAS = (
    ("norte", "Norte", ("Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo")),
    ("centro", "Centro", ("Valparaíso", "Metropolitana", "O'Higgins")),
    ("centro_sur", "Centro-sur", ("Maule", "Ñuble", "Biobío")),
    ("sur", "Sur", ("La Araucanía", "Los Ríos", "Los Lagos")),
    ("austral", "Austral", ("Aysén", "Magallanes")),
)

_AGENTE = "brasas-sequedad/1.0 (falopass/brasas; riesgo ciudadano)"


def ndvi_util(valor, fiabilidad) -> float | None:
    """NDVI usable, o None. No convierte un hueco en 0.

    El entero de MOD13Q1 viene escalado por 0,0001 (7204 = 0,7204). La
    fiabilidad 0 es píxel bueno y 1 es marginal; el resto (nube, nieve, relleno)
    no entra al promedio.
    """
    try:
        bruto = int(valor)
        calidad = int(fiabilidad)
    except (TypeError, ValueError):
        return None
    if calidad not in (0, 1):
        return None
    verdor = bruto * 0.0001 if abs(bruto) > 2 else float(bruto)
    if verdor < -0.2 or verdor > 1:
        return None
    return verdor


def verdor_de_subset(subset: list, fecha_modis: str) -> float | None:
    """Saca NDVI y fiabilidad de un subconjunto ORNL para una fecha AYYYYDDD."""
    ndvi = None
    calidad = None
    for fila in subset or []:
        if fila.get("modis_date") != fecha_modis:
            continue
        banda = str(fila.get("band") or "")
        datos = fila.get("data") or []
        if not datos:
            continue
        if banda.endswith("NDVI"):
            ndvi = datos[0]
        elif banda.endswith("pixel_reliability"):
            calidad = datos[0]
    if ndvi is None or calidad is None:
        return None
    return ndvi_util(ndvi, calidad)


def anomalia_porcentual(actual: float | None, historicos: list[float]) -> int | None:
    """Porcentaje frente al promedio de la misma fecha. None si no hay con qué comparar."""
    buenos = [v for v in historicos if v is not None]
    if actual is None or len(buenos) < MIN_ANOS:
        return None
    media = statistics.fmean(buenos)
    if abs(media) < VERDOR_MINIMO:
        return None
    return int(round((actual - media) / abs(media) * 100))


def estado_de(anomalia: int | None) -> str | None:
    """normal, seca o muy_seca. None si la anomalía no existe: no es «normal» por hueco."""
    if anomalia is None:
        return None
    if anomalia <= UMBRAL_MUY_SECA:
        return "muy_seca"
    if anomalia <= UMBRAL_SECA:
        return "seca"
    return "normal"


def lugar(nombre: str) -> str:
    if nombre == "Metropolitana":
        return "la Región Metropolitana"
    if nombre in {zona for _, zona, _ in MACROZONAS}:
        return f"la zona {nombre}"
    return nombre


def lectura(nombre: str, estado: str, anomalia: int | None) -> str:
    sitio = lugar(nombre)
    if estado == "muy_seca":
        return f"Los bosques, matorrales y pastizales de {sitio} están mucho más secos que lo habitual para esta época."
    if estado == "seca":
        return f"Los bosques, matorrales y pastizales de {sitio} están más secos que lo habitual para esta época."
    # El espejo de la banda «seca» (-8 %): desde +8 % se dice que está más verde.
    if anomalia is not None and anomalia >= -UMBRAL_SECA:
        return f"Los bosques, matorrales y pastizales de {sitio} están más verdes que lo habitual para esta época."
    return f"Los bosques, matorrales y pastizales de {sitio} están como lo habitual para esta época."


def mediana(valores: list[int]) -> int | None:
    if not valores:
        return None
    orden = sorted(valores)
    medio = len(orden) // 2
    if len(orden) % 2:
        return orden[medio]
    return int(round((orden[medio - 1] + orden[medio]) / 2))


def ficha(nombre: str, anomalia: int | None, **extra) -> dict | None:
    estado = estado_de(anomalia)
    if estado is None or anomalia is None:
        return None
    fila = {"nombre": nombre, "estado": estado, "anomalia_pct": anomalia, "lectura": lectura(nombre, estado, anomalia)}
    fila.update(extra)
    return fila


def _pedir(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _AGENTE, "Accept": "application/json"})
    ultimo: Exception | None = None
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=50) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            ultimo = exc
            time.sleep(1.2 * (intento + 1))
    raise RuntimeError(f"sin respuesta de ORNL: {ultimo}")


def fecha_reciente(lat: float, lon: float) -> tuple[str, str]:
    """Última fecha MODIS publicada para un punto (modis_date, calendar_date)."""
    data = _pedir(f"{ORNL}/dates?latitude={lat:.4f}&longitude={lon:.4f}")
    fechas = data.get("dates") or []
    if not fechas:
        raise RuntimeError("ORNL no publicó fechas MOD13Q1 para el punto de control")
    ultima = fechas[-1]
    return str(ultima["modis_date"]), str(ultima["calendar_date"])


def verdor_en(lat: float, lon: float, fecha_modis: str) -> float | None:
    url = (
        f"{ORNL}/subset?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&startDate={fecha_modis}&endDate={fecha_modis}&kmAboveBelow=0&kmLeftRight=0"
    )
    try:
        data = _pedir(url)
    except (RuntimeError, urllib.error.HTTPError):
        return None
    return verdor_de_subset(data.get("subset") or [], fecha_modis)


def _anos(fecha_modis: str) -> list[str]:
    """La misma fecha (DDD) en el año de la imagen y en los ANOS_ATRAS anteriores."""
    anio = int(fecha_modis[1:5])
    dia = fecha_modis[5:]
    return [f"A{anio - i}{dia}" for i in range(0, ANOS_ATRAS + 1)]


def serie_punto(lat: float, lon: float, fecha_modis: str) -> tuple[float | None, list[float]]:
    fechas = _anos(fecha_modis)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futuros = {pool.submit(verdor_en, lat, lon, fecha): fecha for fecha in fechas}
        por_fecha: dict[str, float | None] = {}
        for futuro in as_completed(futuros):
            por_fecha[futuros[futuro]] = futuro.result()
    actual = por_fecha.get(fechas[0])
    historicos = [por_fecha.get(fecha) for fecha in fechas[1:]]
    return actual, [v for v in historicos if v is not None]


def _indice() -> dict[int, dict]:
    filas = json.loads(INDICE.read_text(encoding="utf-8"))
    return {int(fila["code"]): fila for fila in filas}


def _punto(comuna: dict) -> tuple[float, float]:
    lon, lat = comuna["center"]
    lat, lon = float(lat), float(lon)
    if not (-56 <= lat <= -17 and -76 <= lon <= -66):
        raise RuntimeError(f"centro fuera de Chile continental: {comuna.get('name')} {lat},{lon}")
    return lat, lon


def construir(indice: dict[int, dict] | None = None) -> dict:
    """Arma el paquete. Hace red: una fecha de control y la serie de cada punto."""
    indice = indice or _indice()
    control = indice[MUESTRA_REGION["Maule"]]
    lat0, lon0 = _punto(control)
    fecha_modis, imagen_en = fecha_reciente(lat0, lon0)
    print(f"imagen {imagen_en} ({fecha_modis})", flush=True)

    codigos = list(dict.fromkeys([*MUESTRA_REGION.values(), *COMUNAS_CLAVE]))
    series: dict[int, int | None] = {}

    def una(codigo: int) -> tuple[int, int | None]:
        comuna = indice[codigo]
        lat, lon = _punto(comuna)
        actual, historicos = serie_punto(lat, lon, fecha_modis)
        return codigo, anomalia_porcentual(actual, historicos)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futuros = [pool.submit(una, codigo) for codigo in codigos]
        for n, futuro in enumerate(as_completed(futuros), start=1):
            codigo, anomalia = futuro.result()
            series[codigo] = anomalia
            nombre = indice[codigo]["name"]
            print(f"  {n}/{len(codigos)} {nombre}: {anomalia if anomalia is not None else 'sin dato'}", flush=True)

    regiones = []
    for nombre, codigo in MUESTRA_REGION.items():
        fila = ficha(nombre, series.get(codigo), muestra=codigo)
        if fila:
            regiones.append(fila)

    comunas = []
    for codigo in COMUNAS_CLAVE:
        comuna = indice[codigo]
        fila = ficha(comuna["name"], series.get(codigo), code=codigo, region=comuna["region"])
        if fila:
            # `nombre` ya viene de ficha(); el índice manda la grafía.
            fila["nombre"] = comuna["name"]
            comunas.append(fila)

    por_region = {fila["nombre"]: fila["anomalia_pct"] for fila in regiones}
    macrozonas = []
    for ident, nombre, miembros in MACROZONAS:
        anomalia = mediana([por_region[m] for m in miembros if m in por_region])
        fila = ficha(nombre, anomalia, id=ident, regiones=list(miembros))
        if fila:
            macrozonas.append(fila)

    ahora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "updated_at": ahora,
        "generated_at": ahora,
        "source": FUENTE,
        "source_url": FUENTE_URL,
        "producto": "MOD13Q1",
        "imagen_en": imagen_en,
        "metodo": (
            "Un punto por lugar (centro de la comuna en el índice territorial). "
            "NDVI MOD13Q1 de 250 m, compuesto de 16 días, vía el servicio de subconjuntos de ORNL. "
            "La anomalía es el verdor de la última imagen frente al promedio de la misma fecha "
            f"en los {ANOS_ATRAS} años anteriores, solo con píxel fiable. "
            f"Muy seca: {UMBRAL_MUY_SECA} % o menos. Seca: {UMBRAL_SECA} % o menos. Si no, normal. "
            "Sin píxel o sin promedio el valor no se publica: no se guarda un cero."
        ),
        "macrozonas": macrozonas,
        "regiones": regiones,
        "comunas": comunas,
    }


def escribir(paquete: dict, destino: Path = SALIDA) -> int:
    texto = json.dumps(paquete, ensure_ascii=False, separators=(",", ":")) + "\n"
    crudo = texto.encode("utf-8")
    if len(crudo) >= TOPE_BYTES:
        raise RuntimeError(f"{destino.name} pesa {len(crudo)} bytes, el tope es {TOPE_BYTES - 1}")
    if len(paquete["regiones"]) < 8 or len(paquete["comunas"]) < 6:
        raise RuntimeError("quedaron pocos lugares con verdor fiable; no reemplazo el archivo")
    destino.write_bytes(crudo)
    return len(crudo)


def main() -> int:
    paquete = construir()
    peso = escribir(paquete)
    print(f"escribí {SALIDA.relative_to(ROOT).as_posix()} ({peso} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
