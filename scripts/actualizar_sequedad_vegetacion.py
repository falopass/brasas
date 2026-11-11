"""Genera ``web/data/vegetacion-sequedad.json`` (RISK-11).

Pide el verdor de la vegetación (NDVI del producto MOD13Q1 de NASA, píxel de
250 m y compuesto de 16 días) al servicio público de subconjuntos de ORNL.
Cada región conserva su punto de muestra y cada comuna de Chile continental
usa el suyo: el centro del índice territorial. La anomalía es el verdor de la
última imagen frente al promedio de la misma fecha en los años anteriores. Si
falta el píxel o el promedio, la comuna no se publica: no se guarda un cero
inventado. Isla de Pascua y Juan Fernández quedan fuera de la grilla del
producto y se omiten sin detener la corrida.

La ficha cita «NASA MODIS / VIIRS · Índice de verdor satelital (NDVI)» y
https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod13q1-061. El número sale de MODIS
(MOD13Q1); VIIRS es la familia de satélites polares que la cita nombra.

Uso: python scripts/actualizar_sequedad_vegetacion.py [--cache RUTA]
  --cache guarda fuera del repo cada píxel ya pedido: si la corrida se corta,
  volver a correr retoma donde quedó sin repetir peticiones a ORNL.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDICE = ROOT / "web" / "data" / "comunas-index.json"
SALIDA = ROOT / "web" / "data" / "vegetacion-sequedad.json"
ORNL = "https://modis.ornl.gov/rst/api/v1/MOD13Q1"
FUENTE = "NASA MODIS / VIIRS · Índice de verdor satelital (NDVI)"
FUENTE_URL = "https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod13q1-061"
# `comunas` viaja como mapa código → anomalía %, así que las ~340 con dato
# caben con holgura en este tope (y el archivo sigue entrando en el presupuesto
# de 4 MB de web/data que mide tests/test_data_files.py).
TOPE_BYTES = 48 * 1024
# Puntos en paralelo y una fecha a la vez por punto: nunca más de esta
# cantidad de peticiones simultáneas contra ORNL.
TRABAJADORES = 8
ANOS_ATRAS = 10
MIN_ANOS = 5
# Por debajo de esto el archivo quedaría degradado: no reemplazar el vigente.
MIN_COMUNAS = 100
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

MACROZONAS = (
    ("norte", "Norte", ("Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo")),
    ("centro", "Centro", ("Valparaíso", "Metropolitana", "O'Higgins")),
    ("centro_sur", "Centro-sur", ("Maule", "Ñuble", "Biobío")),
    ("sur", "Sur", ("La Araucanía", "Los Ríos", "Los Lagos")),
    ("austral", "Austral", ("Aysén", "Magallanes")),
)

_AGENTE = "brasas-sequedad/1.0 (falopass/brasas; riesgo ciudadano)"

# Toque amable con ORNL: a lo más una petición en vuelo por trabajador.
_HTTP = threading.BoundedSemaphore(TRABAJADORES)


class Cache:
    """Píxeles ya pedidos, en disco fuera del repo. None se guarda igual: un
    hueco no se vuelve a pedir en la reanudación."""

    def __init__(self, ruta: Path | None):
        self.ruta = ruta
        self._lock = threading.Lock()
        self._pixeles: dict[str, float | None] = {}
        if ruta and ruta.exists():
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                if isinstance(datos, dict):
                    self._pixeles = {str(k): v for k, v in datos.items()}
            except (OSError, json.JSONDecodeError):
                print(f"cache ilegible en {ruta}; se parte de cero", flush=True)

    @staticmethod
    def _clave(lat: float, lon: float, fecha_modis: str) -> str:
        return f"{lat:.4f},{lon:.4f}|{fecha_modis}"

    def verdor(self, lat: float, lon: float, fecha_modis: str) -> tuple[bool, float | None]:
        clave = self._clave(lat, lon, fecha_modis)
        with self._lock:
            if clave in self._pixeles:
                return True, self._pixeles[clave]
        return False, None

    def guardar(self, lat: float, lon: float, fecha_modis: str, verdor: float | None) -> None:
        if not self.ruta:
            return
        with self._lock:
            self._pixeles[self._clave(lat, lon, fecha_modis)] = verdor

    def volcar(self) -> None:
        if not self.ruta:
            return
        with self._lock:
            texto = json.dumps(self._pixeles)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=self.ruta.parent, prefix=self.ruta.name, suffix=".tmp", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(texto)
            temp = Path(tmp.name)
        temp.replace(self.ruta)


def ndvi_util(valor, fiabilidad) -> float | None:
    """NDVI usable, o None. No convierte un hueco en 0.

    El entero de MOD13Q1 viene escalado por 0,0001 (7204 = 0,7204). La
    fiabilidad 0 es píxel bueno y 1 es marginal; el resto (nube, nieve, relleno)
    no entra al promedio.
    """
    try:
        calidad = int(fiabilidad)
    except (TypeError, ValueError):
        return None
    if calidad not in (0, 1):
        return None
    try:
        # ORNL entrega el entero escalado por 0,0001; un flotante ya viene en NDVI.
        verdor = valor if isinstance(valor, float) else int(valor) * 0.0001
    except (TypeError, ValueError):
        return None
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
    # Una media negativa es agua o nieve: el porcentaje sobre ella no dice nada.
    if media < VERDOR_MINIMO:
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


def mediana(valores: list[int]) -> int | None:
    if not valores:
        return None
    orden = sorted(valores)
    medio = len(orden) // 2
    if len(orden) % 2:
        return orden[medio]
    return int(round((orden[medio - 1] + orden[medio]) / 2))


def ficha(nombre: str, anomalia: int | None, **extra) -> dict | None:
    """Fila compacta: la frase la arma la vista desde estado y anomalia_pct."""
    estado = estado_de(anomalia)
    if estado is None or anomalia is None:
        return None
    fila = {"nombre": nombre, "estado": estado, "anomalia_pct": anomalia}
    fila.update(extra)
    return fila


def _pedir(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _AGENTE, "Accept": "application/json"})
    ultimo: Exception | None = None
    for intento in range(3):
        try:
            with _HTTP, urllib.request.urlopen(req, timeout=50) as resp:
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


def verdor_en(lat: float, lon: float, fecha_modis: str, cache: Cache) -> float | None:
    en_cache, valor = cache.verdor(lat, lon, fecha_modis)
    if en_cache:
        return valor
    url = f"{ORNL}/subset?latitude={lat:.4f}&longitude={lon:.4f}&startDate={fecha_modis}&endDate={fecha_modis}&kmAboveBelow=0&kmLeftRight=0"
    try:
        data = _pedir(url)
    except (RuntimeError, urllib.error.HTTPError):
        # Fallo de transporte: no se guarda; una reanudación lo vuelve a pedir.
        return None
    valor = verdor_de_subset(data.get("subset") or [], fecha_modis)
    # Solo se cachea una respuesta válida: su «sin píxel fiable» es un hecho del
    # compuesto, no un apagón de la red.
    cache.guardar(lat, lon, fecha_modis, valor)
    return valor


def _anos(fecha_modis: str) -> list[str]:
    """La misma fecha (DDD) en el año de la imagen y en los ANOS_ATRAS anteriores."""
    anio = int(fecha_modis[1:5])
    dia = fecha_modis[5:]
    return [f"A{anio - i}{dia}" for i in range(0, ANOS_ATRAS + 1)]


def serie_punto(lat: float, lon: float, fecha_modis: str, cache: Cache) -> tuple[float | None, list[float]]:
    """Verdor de la fecha actual y de la misma fecha en los años anteriores.

    Las fechas se piden de a una: la concurrencia total la pone el pool de
    comunas (TRABAJADORES) y el semáforo de _pedir.
    """
    fechas = _anos(fecha_modis)
    por_fecha = {fecha: verdor_en(lat, lon, fecha, cache) for fecha in fechas}
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


def construir(indice: dict[int, dict] | None = None, cache: Cache | None = None) -> dict:
    """Arma el paquete. Hace red: una fecha de control y la serie de cada punto."""
    indice = indice or _indice()
    cache = cache or Cache(None)
    control = indice[MUESTRA_REGION["Maule"]]
    lat0, lon0 = _punto(control)
    fecha_modis, imagen_en = fecha_reciente(lat0, lon0)
    print(f"imagen {imagen_en} ({fecha_modis})", flush=True)

    # Todas las comunas del índice; los puntos de muestra regional ya son
    # comunas de la lista (Putre, Empedrado…) y se miden una sola vez.
    codigos = sorted(indice)
    series: dict[int, int | None] = {}
    omitidas: list[str] = []

    def una(codigo: int) -> tuple[int, int | None, bool]:
        comuna = indice[codigo]
        try:
            lat, lon = _punto(comuna)
        except RuntimeError:
            return codigo, None, True
        actual, historicos = serie_punto(lat, lon, fecha_modis, cache)
        return codigo, anomalia_porcentual(actual, historicos), False

    with ThreadPoolExecutor(max_workers=TRABAJADORES) as pool:
        futuros = [pool.submit(una, codigo) for codigo in codigos]
        for n, futuro in enumerate(as_completed(futuros), start=1):
            codigo, anomalia, fuera = futuro.result()
            if fuera:
                omitidas.append(indice[codigo]["name"])
            else:
                series[codigo] = anomalia
            cache.volcar()
            nombre = indice[codigo]["name"]
            print(
                f"  {n}/{len(codigos)} {nombre}: {'omitida' if fuera else (anomalia if anomalia is not None else 'sin dato')}",
                flush=True,
            )

    sin_dato: dict[str, list[str]] = defaultdict(list)
    for codigo, anomalia in series.items():
        if anomalia is None:
            sin_dato[indice[codigo]["region"]].append(indice[codigo]["name"])
    total_dato = sum(1 for a in series.values() if a is not None)
    print(f"comunas con dato: {total_dato}; sin dato: {sum(len(v) for v in sin_dato.values())}", flush=True)
    for region, nombres in sorted(sin_dato.items()):
        print(f"  sin dato · {region} ({len(nombres)}): {', '.join(sorted(nombres))}", flush=True)
    if omitidas:
        print(f"omitidas fuera del continente: {', '.join(sorted(omitidas))}", flush=True)

    regiones = []
    for nombre, codigo in MUESTRA_REGION.items():
        fila = ficha(nombre, series.get(codigo), muestra=codigo)
        if fila:
            regiones.append(fila)

    # Mapa código de comuna → ficha mínima. La vista conoce nombre y región por
    # su propio índice y el estado es función del porcentaje, así que el único
    # dato que viaja por comuna es anomalia_pct. Una comuna ausente es sin dato.
    comunas = {str(codigo): {"anomalia_pct": anomalia} for codigo, anomalia in sorted(series.items()) if anomalia is not None}

    por_region = {fila["nombre"]: fila["anomalia_pct"] for fila in regiones}
    macrozonas = []
    for ident, nombre, miembros in MACROZONAS:
        # Solo las regiones que aportaron al número: una sin dato no se cuelga de la zona.
        aportan = [m for m in miembros if m in por_region]
        anomalia = mediana([por_region[m] for m in aportan])
        fila = ficha(nombre, anomalia, id=ident, regiones=aportan)
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
            "Sin píxel o sin promedio la comuna no se publica: no se guarda un cero. "
            "`comunas` es un mapa código → {anomalia_pct} (la vista deriva el estado y la frase). "
            "Las comunas insulares (Isla de Pascua y Juan Fernández) quedan fuera de la grilla "
            "del producto y se omiten."
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
    if len(paquete["regiones"]) < 8 or len(paquete["comunas"]) < MIN_COMUNAS:
        raise RuntimeError("quedaron pocos lugares con verdor fiable; no reemplazo el archivo")
    destino.write_bytes(crudo)
    return len(crudo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=None, help="JSON fuera del repo para reanudar la corrida")
    args = parser.parse_args(argv)
    paquete = construir(cache=Cache(args.cache))
    peso = escribir(paquete)
    print(f"escribí {SALIDA.relative_to(ROOT).as_posix()} ({peso} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
