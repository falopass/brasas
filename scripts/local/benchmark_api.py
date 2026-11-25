"""Benchmark reproducible de la API de BRASA Chile (REND-02, primera tanda: instrumentación).

Mide rutas públicas de la API en un proceso nuevo por ruta y escenario, sin red externa:

- ``fria``: la primera llamada de la ruta en un proceso recién arrancado (sin calentamiento).
- ``caliente``: una llamada de calentamiento explícita y luego N muestras (N >= 20 para el p95).
- ``contienda``: como ``caliente`` con un hilo que hace escrituras reales de base de datos
  (el lado de datos de la ingesta: inserciones + reagrupación con el mismo ``incidents.update``),
  sin avisos, sin envíos y sin red.
- ``fixture``/``restauracion``: mide las fases de arranque y restauración del respaldo con un
  fixture íntegro y reproducible, y cuenta las subidas de respaldo provocadas por escrituras
  de usuario. Si el fixture no se puede crear o restaurar, se declara «no medido» y nada cambia
  en el backend.

Uso (este script siempre es el del checkout candidato; ``--repo`` elige el código medido, así
se pueden comparar dos checkouts con el mismo harness):

    python scripts/local/benchmark_api.py --repo . --out out/bench --samples 20
    python scripts/local/benchmark_api.py --base-repo ../brasas-base --candidate-repo . --out out/comp
    python scripts/local/benchmark_api.py --base http://127.0.0.1:8001 --candidate http://127.0.0.1:8002 --out out/urls

El modo ``--base URL --candidate URL`` compara dos servidores vivos con llamadas alternadas
(HTTP real; sin contadores de SQL ni de llamadas externas, que exigen acceso al proceso).

Contrato del hijo (proceso nuevo por ruta y escenario): ``--hijo --repo RUTA --rol ROL ...``
imprime una sola línea JSON en stdout; todo lo demás va a stderr. Código de salida 0 si la
medición salió, 3 si el hijo falló (el JSON trae el ``error``).

Reproducibilidad: el hijo congela el reloj en EPOCA (2026-11-01T12:00:00Z) y fija los uuid,
así base y candidata ven exactamente los mismos datos y los cuerpos son comparables (la
«huella estable» además ignora los campos de tiempo de ejecución, claves ``*_ms`` y tamaños).
La siembra es determinista y jamás consulta Open-Meteo: el riesgo 30-30-30 es sintético.

Límites declarados (van en el informe y en el JSON):

- ``bytes_decodificados``: tamaño del cuerpo ya descomprimido por el cliente de pruebas; el
  tamaño gzip real y la transferencia en bruto NO se miden en el modo con TestClient (ASGI).
- El SQL se cuenta con la traza de sqlite3: sentencias, nunca parámetros (incluye PRAGMA).
- Las llamadas externas se bloquean con 503 y solo se cuenta el host, nunca la URL completa
  (la URL puede llevar tokens en su consulta).
- ``contienda`` escribe en la base mientras se mide: sus cuerpos no son comparables entre corridas.
- ``medir_latencia.py`` (la sonda de producción) no se modifica ni aumenta sus repeticiones.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib
import itertools
import json
import math
import os
import random
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

RUTA_SCRIPT = Path(__file__).resolve()

# Reloj congelado: verano de Chile 2026 (UTC-3). Todas las fechas de la siembra salen de aquí.
EPOCA = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
CHILE_TZ = ZoneInfo("America/Santiago")

GATE_P95_MS = 2500.0  # REND-02: API caliente p95 <= 2 500 ms (gate heredado, no se aumenta)
MIN_MUESTRAS = 20
ESCALAS = ("demo", "volumen")  # demo: 2 incidentes; volumen: 2 000 detecciones / 200 incidentes
ROLES = ("fria", "caliente", "contienda")

# Rutas públicas, GET, sin token de sesión ni datos personales, y sin limitador por IP
# (los limitadores de 30-60 llamadas/hora harían fallar una tanda de 20+ muestras).
RUTAS = [
    {"id": "salud", "plantilla": "/api/health"},
    {"id": "estado", "plantilla": "/api/status"},
    {"id": "observaciones", "plantilla": "/api/observations?hours=48"},
    {"id": "incidentes", "plantilla": "/api/incidents?hours=48"},
    {"id": "ficha", "plantilla": "/api/incidents/{incident_id}"},
    {"id": "oficiales", "plantilla": "/api/official-fires"},
    {"id": "riesgo", "plantilla": "/api/risk"},
    {"id": "prioritarias", "plantilla": "/api/priority-comunas"},
]

# Secretos y llaves de entorno que el hijo nunca hereda (mismo criterio que tests/conftest.py).
CLAVES_ENV_LIMPIAS = (
    "FIRMS_MAP_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME", "ADMIN_TOKEN",
    "CESIUM_ION_PUBLIC_TOKEN", "FIRMS_SOURCES", "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET",
    "CONAF_PERIMETRO_ENABLED", "DMC_USUARIO", "DMC_TOKEN", "SINCA_PROXY_URL",
    "SINCA_SNAPSHOT_PATH", "SINCA_MAX_SNAPSHOT_AGE_HOURS", "PUBLIC_BASE_URL",
    "INTERNAL_TOKEN", "TELEGRAM_WEBHOOK_SECRET",
)

# Claves cuyo valor es medición y no dato: se normalizan en la «huella estable».
CLAVES_VOLATILES = {"bytes", "work_bytes", "work_db_bytes", "backup_bytes", "ms", "uptime_s", "edad_s"}

_ESCRITURA_SQL = re.compile(r"^\s*(insert|update|delete|replace)\b", re.I)
_SQL_OBSERVACION = (
    "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
    "frp_mw, confidence, comuna_code, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
)

LIMITES = [
    "Los bytes son del cuerpo ya descomprimido (TestClient/ASGI): el tamaño gzip real de la respuesta "
    "y la transferencia en bruto no se miden en este modo.",
    "El SQL se cuenta por sentencia (traza de sqlite3), sin parámetros; incluye los PRAGMA de la base.",
    "Las llamadas externas se bloquean con 503 y solo se cuenta su host, nunca la URL completa.",
    "«fria» es la primera llamada de la ruta en un proceso nuevo; el arranque de la app ya terminó y se informa aparte.",
    "«contienda» agrega escrituras reales de base de datos en segundo plano; sus cuerpos no son comparables entre corridas.",
    "La restauración se mide solo si el fixture del respaldo es íntegro y reproducible; si no, se declara «no medido». "
    "El fixture reproduce el formato comprimido que recibe el backend después del descifrado del Worker; "
    "no mide cifrado ni recuperación de R2 de extremo a extremo.",
    "El modo --base/--candidate (URLs) mide HTTP real sin acceso al proceso: sin contadores de SQL ni de externos.",
    "El reloj va congelado (2026-11-01T12:00:00Z) y los uuid son fijos: dos corridas ven los mismos datos; los campos "
    "de tiempo de ejecución (claves *_ms y tamaños) se normalizan en la «huella estable».",
    "medir_latencia.py (la sonda de producción) no se modifica ni aumenta sus repeticiones.",
]


# ---------------------------------------------------------------- estadística --

def percentil(muestras: list[float], p: float) -> float | None:
    """Percentil por rango más cercano: la k-ésima muestra ordenada, con k = ceil(p/100 · n).

    Con 20 muestras, el p95 es la 19.ª (índice 18); con 3, el p95 es la peor. None si no hay muestras.
    """
    if not muestras:
        return None
    ordenadas = sorted(muestras)
    k = max(1, math.ceil(p / 100 * len(ordenadas)))
    return ordenadas[min(k, len(ordenadas)) - 1]


def resumen_muestras(muestras: list[dict]) -> dict:
    """n, errores, p50, p95, máximo y promedios de costo por llamada.

    Las llamadas con error (excepción o estado fuera de 2xx) se cuentan como errores y no
    entran a los percentiles: se conservan a la vista, no se promedian como si valieran.
    """
    ok = [m for m in muestras if not m.get("error") and (m.get("estado") or 0) // 100 == 2]
    latencias = [m["ms"] for m in ok]
    sql = [m["sql"] for m in ok if m.get("sql") is not None]
    resumen: dict = {
        "n": len(muestras),
        "errores": len(muestras) - len(ok),
        "p50": percentil(latencias, 50),
        "p95": percentil(latencias, 95),
        "max": max(latencias) if latencias else None,
        "media": round(statistics.fmean(latencias), 3) if latencias else None,
        "estados": sorted({str(m.get("estado")) for m in muestras}),
    }
    if sql:
        resumen["sql_por_llamada"] = round(statistics.fmean(sql), 1)
    return resumen


def evaluar_gate(resultados: dict, umbral_ms: float = GATE_P95_MS, min_muestras: int = MIN_MUESTRAS) -> tuple[bool, list[str]]:
    """Gate de REND-02 sobre el escenario caliente: p95 <= umbral, sin errores y con el mínimo de muestras."""
    motivos: list[str] = []
    if not resultados:
        motivos.append("sin rutas medidas")
    for ruta, escenarios in sorted(resultados.items()):
        resumen = ((escenarios or {}).get("caliente") or {}).get("resumen") or {}
        if not resumen:
            motivos.append(f"{ruta}: sin escenario caliente medido")
            continue
        if resumen["n"] < min_muestras:
            motivos.append(f"{ruta}: {resumen['n']} muestras (< {min_muestras})")
        if resumen["errores"]:
            motivos.append(f"{ruta}: {resumen['errores']} llamadas con error")
        if resumen["p95"] is not None and resumen["p95"] > umbral_ms:
            motivos.append(f"{ruta}: p95 {resumen['p95']:.0f} ms > {umbral_ms:.0f} ms")
    return (not motivos), motivos


# ------------------------------------------------------------ cuerpos y huella --

def hash_bytes(cuerpo: bytes) -> str:
    """SHA-256 del cuerpo. El contenido nunca se guarda: solo este hash (nada personal viaja al informe)."""
    return hashlib.sha256(cuerpo).hexdigest()


def huella_estable(valor):
    """Copia del JSON con las claves volátiles (``*_ms`` y tamaños) reemplazadas por una marca.

    Así dos corridas con los mismos datos comparan igual aunque su medición interna haya variado.
    """
    if isinstance(valor, dict):
        return {
            str(clave): "<variable>" if (str(clave).endswith("_ms") or str(clave) in CLAVES_VOLATILES) else huella_estable(contenido)
            for clave, contenido in valor.items()
        }
    if isinstance(valor, list):
        return [huella_estable(item) for item in valor]
    return valor


def huella_json(cuerpo: bytes) -> str:
    """Hash de la huella estable del cuerpo; si no es JSON, el hash directo."""
    try:
        datos = json.loads(cuerpo)
    except ValueError:
        return hash_bytes(cuerpo)
    canonico = json.dumps(huella_estable(datos), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hash_bytes(canonico.encode())


def veredicto_cuerpos(hijo_a: dict | None, hijo_b: dict | None, rol: str = "caliente") -> str:
    """Compara la primera muestra de dos corridas de la misma ruta.

    La comparación de cuerpos es la que valida la de latencias: si los datos difieren, los
    milisegundos de una y otra no son comparables y hay que decirlo, no asumirlos válidos.
    """
    if rol == "contienda":
        return "no comparables (escrituras en curso)"
    if not hijo_a or not hijo_b or hijo_a.get("error") or hijo_b.get("error"):
        return "no comparables"
    ma = (hijo_a.get("muestras") or [{}])[0]
    mb = (hijo_b.get("muestras") or [{}])[0]
    if ma.get("estado") != mb.get("estado"):
        return "estados distintos"
    if ma.get("hash") is not None and ma.get("hash") == mb.get("hash"):
        return "equivalentes"
    if ma.get("hash_huella") is not None and ma.get("hash_huella") == mb.get("hash_huella"):
        return "equivalentes salvo tiempos"
    return "distintos"


# ------------------------------------------------------------------ contadores --

class ContadorSQL:
    """Cuenta las sentencias SQL que ejecuta la app, por la traza de sqlite3.

    Cuenta solo números: nunca guarda el texto de la sentencia ni sus parámetros. Las
    sentencias de hilos excluidos (la ingesta simulada de «contienda») se cuentan aparte,
    para que cada muestra refleje solo el trabajo de la propia llamada medida.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._excluidos: set[int] = set()
        self.reiniciar()

    def reiniciar(self) -> None:
        with self._lock:
            self.principal = 0
            self.principal_escrituras = 0
            self.fondo = 0
            self.fondo_escrituras = 0

    def excluir(self, hilo: threading.Thread) -> None:
        """Marca un hilo como «de fondo»: sus sentencias van al contador aparte."""
        with self._lock:
            self._excluidos.add(id(hilo))

    def registrar(self, sql: str, hilo: threading.Thread | None = None) -> None:
        actual = threading.current_thread() if hilo is None else hilo
        escribe = 1 if _ESCRITURA_SQL.match(sql or "") else 0
        with self._lock:
            if id(actual) in self._excluidos:
                self.fondo += 1
                self.fondo_escrituras += escribe
            else:
                self.principal += 1
                self.principal_escrituras += escribe

    def instantanea(self) -> dict:
        with self._lock:
            return {
                "sql": self.principal,
                "sql_escrituras": self.principal_escrituras,
                "sql_fondo": self.fondo,
                "sql_fondo_escrituras": self.fondo_escrituras,
            }


class ContadorExterno:
    """Bloquea toda llamada externa con 503 y las cuenta por host.

    Solo se guarda el host (nunca la URL completa: podría llevar tokens en la consulta).
    En el rol «restauracion» también sirve el fixture del respaldo: los GET a las rutas
    ``db/brasa.db`` y ``db/work.db.gz`` devuelven el fixture y los PUT se aceptan y se cuentan.
    """

    def __init__(self, respuestas: dict[str, bytes] | None = None):
        self._lock = threading.Lock()
        self._respuestas = dict(respuestas or {})
        self.reiniciar()

    def reiniciar(self) -> None:
        """Reinicia la ventana por muestra; los acumulados del proceso nunca se reinician."""
        with self._lock:
            self.total = 0
            self.put = 0
            self.por_host: dict[str, int] = {}
            self.total_acum = getattr(self, "total_acum", 0)
            self.put_acum = getattr(self, "put_acum", 0)
            self.por_host_acum: dict[str, int] = dict(getattr(self, "por_host_acum", {}))

    def atender(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host or "?"
        with self._lock:
            self.total += 1
            self.total_acum += 1
            self.por_host[host] = self.por_host.get(host, 0) + 1
            self.por_host_acum[host] = self.por_host_acum.get(host, 0) + 1
            es_put = request.method == "PUT"
            if es_put:
                self.put += 1
                self.put_acum += 1
            cuerpo = None
            if request.method == "GET":
                for sufijo, contenido in self._respuestas.items():
                    if request.url.path.endswith(sufijo):
                        cuerpo = contenido
                        break
        if cuerpo is not None:
            return httpx.Response(200, content=cuerpo)
        if request.method == "PUT":
            return httpx.Response(200, content=b"respaldado por el benchmark")
        # 503 explícito: queda registrado como fuente caída, con Retry-After 0 para no
        # sumar esperas artificiales (además las esperas de reintento van en 0 en el hijo).
        return httpx.Response(503, text="bloqueado por el benchmark", headers={"Retry-After": "0"})

    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.atender)

    def instantanea(self) -> dict:
        with self._lock:
            return {
                "externos": self.total,
                "externos_put": self.put,
                "externos_por_host": dict(self.por_host),
            }

    def totales(self) -> dict:
        with self._lock:
            return {"total": self.total_acum, "put": self.put_acum, "por_host": dict(self.por_host_acum)}


def instalar_traza_sqlite(contador: ContadorSQL):
    """Parcha sqlite3.connect para que toda conexión nueva cuente sus sentencias en el contador.

    Devuelve una función que restaura sqlite3.connect (las conexiones ya creadas conservan la traza).
    """
    if getattr(sqlite3.connect, "_bench_traza", False):
        return lambda: None
    conectores = sqlite3.connect

    def conectar(*args, **kwargs):
        conexion = conectores(*args, **kwargs)
        conexion.set_trace_callback(contador.registrar)
        return conexion

    conectar._bench_traza = True  # type: ignore[attr-defined]
    sqlite3.connect = conectar

    def restaurar() -> None:
        sqlite3.connect = conectores

    return restaurar


class _HttpxBloqueado:
    """Vista de httpx donde cada cliente nuevo nace ya con el transporte bloqueado."""

    def __init__(self, transporte: httpx.BaseTransport) -> None:
        clase_real = httpx.AsyncClient

        class _ClienteBloqueado(clase_real):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault("transport", transporte)
                super().__init__(*args, **kwargs)

        self._cliente = _ClienteBloqueado

    @property
    def AsyncClient(self):  # noqa: N802 (nombre igual al de httpx, a propósito)
        return self._cliente

    def __getattr__(self, nombre: str):
        return getattr(httpx, nombre)


def aislar_proveedores(transporte: httpx.BaseTransport):
    """Firms y Overpass tienen refugios que crean su propio ``httpx.AsyncClient`` cuando no
    reciben cliente (``backend/providers/firms.py``, ``backend/providers/overpass.py``).

    Se les sustituye su vista de ``httpx`` para que esos refugios también nazcan bloqueados.
    El ``httpx`` global queda intacto (TestClient y el resto no se tocan).
    """
    aislada = _HttpxBloqueado(transporte)
    cambios: list[tuple] = []
    for nombre in ("backend.providers.firms", "backend.providers.overpass"):
        modulo = importlib.import_module(nombre)
        cambios.append((modulo, modulo.httpx))
        modulo.httpx = aislada

    def restaurar() -> None:
        for modulo, original in cambios:
            modulo.httpx = original

    return restaurar


def acortar_reintentos():
    """Deja las esperas de reintento en 0 dentro del harness: los 503 del bloqueo externo no
    deben sumar esperas artificiales a las mediciones (mismo patrón que tests/conftest.py).
    Solo vale dentro del proceso del hijo; el backend medido no cambia.
    """
    from backend import storage
    from backend.providers import _retry, overpass

    originales = (_retry.RETRY_DELAYS, storage.STORAGE_DELAYS, overpass.WAITS_S)
    _retry.RETRY_DELAYS = tuple(0.0 for _ in originales[0])
    storage.STORAGE_DELAYS = tuple(0.0 for _ in originales[1])
    overpass.WAITS_S = tuple(0.0 for _ in originales[2])

    def restaurar() -> None:
        _retry.RETRY_DELAYS, storage.STORAGE_DELAYS, overpass.WAITS_S = originales

    return restaurar


# ------------------------------------------------------------- reloj y uuid --

def congelar_reloj(momento: datetime):
    """Congela ``datetime.now``/``today``/``utcnow`` y ``date.today`` en el módulo ``datetime``.

    Debe llamarse ANTES de importar el backend medido: los módulos que hacen
    ``from datetime import datetime`` quedan con la clase congelada. Devuelve una función
    que restaura el módulo (el hijo no la usa: su proceso vive y muere congelado).
    """
    import datetime as modulo

    real_datetime = modulo.datetime
    real_date = modulo.date
    base = momento.astimezone(timezone.utc)

    class _RelojFijo(real_datetime):
        @classmethod
        def now(cls, tz=None):
            valor = base.replace(tzinfo=None) if tz is None else base.astimezone(tz)
            return cls.fromisoformat(valor.isoformat())

        @classmethod
        def utcnow(cls):
            return cls.fromisoformat(base.replace(tzinfo=None).isoformat())

        @classmethod
        def today(cls):
            return cls.now()

    class _FechaFija(real_date):
        @classmethod
        def today(cls):
            return cls(base.year, base.month, base.day)

    modulo.datetime = _RelojFijo
    modulo.date = _FechaFija

    def restaurar() -> None:
        modulo.datetime = real_datetime
        modulo.date = real_date

    return restaurar


def congelar_uuid():
    """Fija ``uuid.uuid4`` con una secuencia determinista (1, 2, 3…): los ids de incidentes
    que genera ``incidents.update`` dejan de ser aleatorios y dos siembras son idénticas."""
    import uuid as modulo_uuid

    real_uuid4 = modulo_uuid.uuid4
    secuencia = itertools.count(1)

    def _uuid4():
        # incidents.update usa hex[:12]: el contador debe vivir en ese prefijo.
        return modulo_uuid.UUID(int=next(secuencia) << 80)

    modulo_uuid.uuid4 = _uuid4

    def restaurar() -> None:
        modulo_uuid.uuid4 = real_uuid4

    return restaurar


# -------------------------------------------------------------------- siembra --

def _sello(momento: datetime) -> str:
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


def _deteccion(oid: str, sensor: str, lat: float, lon: float, momento: datetime, frp: float, confianza: str, terr) -> dict:
    comuna = terr.locate(lat, lon)
    return {
        "id": oid,
        "source": "GOES19_FDCF" if sensor == "ABI" else "VIIRS_NOAA20_NRT",
        "sensor": sensor,
        "satellite": "GOES-19" if sensor == "ABI" else "NOAA-20",
        "resolution_m": 2000 if sensor == "ABI" else 375,
        "lat": lat,
        "lon": lon,
        "observed_at": _sello(momento),
        "frp_mw": round(frp, 1),
        "confidence": confianza,
        "comuna_code": comuna.code if comuna else None,
    }


def _fila_observacion(obs: dict) -> tuple:
    demora = timedelta(minutes=12 if obs["sensor"] == "ABI" else 95)
    return (
        obs["id"], obs["source"], obs["sensor"], obs["satellite"], obs["resolution_m"],
        obs["lat"], obs["lon"], obs["observed_at"], obs["frp_mw"], obs["confidence"],
        obs["comuna_code"], _sello(datetime.fromisoformat(obs["observed_at"]).replace(tzinfo=timezone.utc) + demora),
    )


def _detecciones(escala: str, ahora: datetime, terr) -> list[dict]:
    """El dataset determinista: mismas detecciones para base y candidata, misma hora congelada."""
    if escala == "demo":
        filas = []
        # Frente que avanza hacia el sureste en Quilpué: GOES cada ~14 min y dos pasadas VIIRS.
        for i in range(14):
            sensor = "VIIRS" if i in (3, 9) else "ABI"
            filas.append(_deteccion(
                f"bench:demo:{sensor}:{i}", sensor, -33.06 - i * 0.004, -71.42 + i * 0.003,
                ahora - timedelta(minutes=200 - i * 14), 20 + i * 9.5,
                "alta" if sensor == "ABI" else "nominal", terr))
        # Foco joven al sur de Talca: «posible», todavía sin reporte oficial de CONAF.
        for i in range(7):
            sensor = "VIIRS" if i in (2, 5) else "ABI"
            filas.append(_deteccion(
                f"bench:demo:maule:{sensor}:{i}", sensor, -35.44 - i * 0.003, -71.62 + i * 0.002,
                ahora - timedelta(minutes=105 - i * 15), 12 + i * 6.5,
                "alta" if sensor == "ABI" else "nominal", terr))
        return filas
    if escala != "volumen":
        raise ValueError(f"escala desconocida: {escala}")
    # Volumen del contrato REND-02: ~2 000 detecciones en ~200 focos, un solo ciclo.
    # La semilla es la misma de tests/test_incidents_perf.py: ya se sabe que el generador
    # encuentra 200 focos a 15 km o más dentro del territorio chileno sin dar vueltas.
    from backend.geo import haversine_km, inside_chile

    rng = random.Random(202302)
    centros: list[tuple[float, float]] = []
    while len(centros) < 200:
        cand = (rng.uniform(-38.0, -33.0), rng.uniform(-73.5, -70.0))
        if not inside_chile(cand[0], cand[1], tolerance_deg=0.1):
            continue  # FUEGO-04: solo focos chilenos entran al agrupador
        if all(haversine_km(cand[0], cand[1], c[0], c[1]) >= 15 for c in centros):
            centros.append(cand)  # a 15 km o más: sin cadenas de fusión entre focos
    filas = []
    for i in range(2000):
        lat = centros[i % 200][0] + rng.gauss(0, 0.002)
        lon = centros[i % 200][1] + rng.gauss(0, 0.002)
        sensor = "VIIRS" if i % 37 == 0 else "ABI"
        filas.append(_deteccion(
            f"bench:v:{i}", sensor, lat, lon, ahora - timedelta(minutes=90 - (i // 200) * 10),
            8.0 + i % 10, "alta" if sensor == "ABI" else "nominal", terr))
    return filas


def _sembrar_contexto(db, terr, ahora: datetime) -> None:
    """Incendio oficial ficticio «(BENCH)», Botón Rojo, condiciones de CONAF y riesgo sintético."""
    from backend import incidents

    sello = _sello(ahora)
    fuego = {
        "id": "bench-1", "name": "(BENCH) EL BELLOTO", "status": "confirmado", "status_raw": "En combate",
        "started_at": _sello(ahora - timedelta(hours=3, minutes=10)), "controlled_at": None, "extinguished_at": None,
        "area_ha": 35.5, "lat": -33.07, "lon": -71.41, "comuna": "Quilpué", "region": "Valparaíso",
        "ambito": "CONAF", "fuel": "Pastizal",
    }
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, controlled_at, extinguished_at, area_ha, "
        "lat, lon, comuna, region, ambito, fuel, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fuego["id"], fuego["name"], fuego["status"], fuego["status_raw"], fuego["started_at"],
         fuego["controlled_at"], fuego["extinguished_at"], fuego["area_ha"], fuego["lat"], fuego["lon"],
         fuego["comuna"], fuego["region"], fuego["ambito"], fuego["fuel"], sello, sello),
    )
    incidents.link_official(db, [fuego], ahora)

    hoy = ahora.astimezone(CHILE_TZ).date()
    niveles = ["bajo", "moderado", "alto", "extremo"]
    with db.connect() as conn:
        for k, codigo in enumerate([5801, 5109, 5804, 13101, 7301]):
            for d in range(3):
                fecha = (hoy + timedelta(days=d)).isoformat()
                conn.execute(
                    "INSERT OR REPLACE INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
                    (codigo, fecha, 4 - k % 3, 1500.0 * (k + 1), 0.05 * (k + 1), sello))
                for variable, etiqueta in (("PI", 70), ("HC", 3), ("VV", 6), ("HR", 2), ("TP", 8)):
                    conn.execute(
                        "INSERT OR REPLACE INTO conaf_condiciones(comuna_code, date, var, label, cells, cells_total, fetched_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (codigo, fecha, variable, etiqueta, 40, 120, sello))
        # Riesgo 30-30-30 sintético y determinista para todas las comunas, 7 días: nunca consulta Open-Meteo.
        for comuna in terr.comunas:
            for d in range(7):
                indice = (comuna.code + d) % 4
                nivel = niveles[indice]
                conn.execute(
                    "INSERT OR REPLACE INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, tmax, "
                    "rhmin, windmax, gustmax, level_combined, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (comuna.code, (hoy + timedelta(days=d)).isoformat(), nivel, indice * 3, 0, indice * 2,
                     24 + 3 * indice, 50 - 8 * indice, 15 + 6 * indice, 30, nivel, sello))
    db.kv_set("boton_rojo_at", sello)
    db.kv_set("conaf_cond_at", sello)
    db.kv_set("risk_computed_at", sello)
    db.kv_set("windgrid", json.dumps({
        "computed_at": sello, "step": 1.0,
        "points": [[-35.5, -71.5], [-33.5, -70.5], [-38.5, -72.5]],
        "speed": [25.0, 18.0, 30.0], "dir": [240, 200, 270]}, ensure_ascii=False))
    db.kv_set("windgrid_at", sello)


def sembrar(data_dir: Path, ahora: datetime, escala: str = "volumen") -> dict:
    """Crea la base determinista del benchmark en ``data_dir`` (brasa.db + work.db).

    Reproduce el lado de base de datos de la ingesta: detecciones insertadas y reagrupadas
    con el ``incidents.update`` del repositorio medido, más un incendio oficial ficticio
    («(BENCH)»), Botón Rojo, condiciones de CONAF y riesgo 30-30-30 sintético. ``ahora`` fija
    todas las fechas: con el reloj congelado, dos siembras son idénticas en sus datos.
    Nunca consulta la red ni evalúa avisos. Devuelve la base y el id de la ficha más activa.
    """
    from backend import incidents
    from backend.db import Database
    from backend.geo import territory

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(data_dir / "brasa.db")
    terr = territory()
    filas = _detecciones(escala, ahora, terr)
    with db.connect() as conn:
        for obs in filas:
            conn.execute(_SQL_OBSERVACION, _fila_observacion(obs))
    if escala == "demo":
        # Dos frentes separados: se agrupan como en la siembra de demo de desarrollo.
        corte = 14
        incidents.update(db, filas[:corte], ahora)
        incidents.update(db, filas[corte:], ahora)
    else:
        incidents.update(db, filas, ahora)
    _sembrar_contexto(db, terr, ahora)
    sello = _sello(ahora)
    db.kv_set("last_ingest_at", sello)
    db.kv_set("bench_seed_at", sello)  # marca: esta base la sembró el benchmark
    ficha = db.one("SELECT id FROM incidents ORDER BY n_obs DESC, last_seen_at DESC, id LIMIT 1")
    return {
        "db": db,
        "terr": terr,
        "observaciones": len(filas),
        "incidentes": db.one("SELECT COUNT(*) AS n FROM incidents")["n"],
        "ficha_id": ficha["id"] if ficha else None,
    }


def resolver_ruta(plantilla: str, db) -> str:
    """Rellena el marcador ``{incident_id}`` con el incidente más activo de la base sembrada."""
    if "{incident_id}" not in plantilla:
        return plantilla
    fila = db.one("SELECT id FROM incidents ORDER BY n_obs DESC, last_seen_at DESC, id LIMIT 1")
    if not fila:
        raise RuntimeError("la siembra no dejó incidentes para resolver la ruta ficha")
    return plantilla.replace("{incident_id}", fila["id"])


def plantilla_de(ruta_id: str) -> str:
    for ruta in RUTAS:
        if ruta["id"] == ruta_id:
            return ruta["plantilla"]
    raise ValueError(f"ruta desconocida: {ruta_id}")


# ------------------------------------------------------------------ medición --

def medir_llamada(client, ruta: str, contador_sql: ContadorSQL | None = None,
                  contador_ext: ContadorExterno | None = None) -> dict:
    """Una llamada medida: latencia, estado, bytes decodificados, hashes y contadores de costo.

    El hash completo permite comparar cuerpos base/candidata; la «huella estable» ignora los
    campos de tiempo de ejecución para no marcar diferencia donde solo varió la medición.
    El contenido del cuerpo nunca se guarda. Los bytes son los ya descomprimidos por el
    cliente (gzip y transferencia en bruto: ver LIMITES).
    """
    if contador_sql is not None:
        contador_sql.reiniciar()
    if contador_ext is not None:
        contador_ext.reiniciar()
    t0 = time.perf_counter()
    try:
        respuesta = client.get(ruta)
    except Exception as exc:  # la app falló o la conexión se cayó: se conserva el error
        ms = (time.perf_counter() - t0) * 1000
        return {
            "ms": round(ms, 3), "estado": None, "error": type(exc).__name__,
            "bytes_decodificados": None, "hash": None, "hash_huella": None,
            **(contador_sql.instantanea() if contador_sql is not None else
               {"sql": None, "sql_escrituras": None, "sql_fondo": None, "sql_fondo_escrituras": None}),
            **(contador_ext.instantanea() if contador_ext is not None else
               {"externos": None, "externos_put": None, "externos_por_host": None}),
        }
    ms = (time.perf_counter() - t0) * 1000
    cuerpo = respuesta.content
    return {
        "ms": round(ms, 3),
        "estado": respuesta.status_code,
        "bytes_decodificados": len(cuerpo),
        "hash": hash_bytes(cuerpo),
        "hash_huella": huella_json(cuerpo),
        **(contador_sql.instantanea() if contador_sql is not None else
           {"sql": None, "sql_escrituras": None, "sql_fondo": None, "sql_fondo_escrituras": None}),
        **(contador_ext.instantanea() if contador_ext is not None else
           {"externos": None, "externos_put": None, "externos_por_host": None}),
    }


class HiloIngesta(threading.Thread):
    """El lado de base de datos de la ingesta, en un hilo aparte (escenario «contienda»).

    Inserta lotes de detecciones sintéticas y reagrupa con el mismo ``incidents.update`` de un
    ciclo real, con la misma secuencia determinista en base y candidata. Nunca evalúa avisos,
    nunca envía nada y nunca toca la red: las escrituras son reales y controladas.
    """

    def __init__(self, db, contador_sql: ContadorSQL, terr, ahora: datetime, paso_s: float = 0.2):
        super().__init__(name="bench-ingesta", daemon=True)
        self.db = db
        self.contador = contador_sql
        self.terr = terr
        self.ahora = ahora
        self.paso_s = paso_s
        self.lotes = 0
        self._parar = threading.Event()
        contador_sql.excluir(self)  # sus sentencias van al contador de fondo

    def _lote(self, k: int) -> list[dict]:
        base_lat = -33.40 - 0.05 * (k % 5)
        base_lon = -70.60 + 0.05 * (k % 7)
        lote = []
        for i in range(6):
            lote.append(_deteccion(
                f"bench:contienda:{k}:{i}", "ABI" if i % 3 else "VIIRS",
                base_lat + i * 0.0015, base_lon + i * 0.0012,
                self.ahora - timedelta(minutes=180 - ((k * 6 + i) % 180)),
                15.0 + (k + i) % 20, "alta" if i % 3 else "nominal", self.terr))
        return lote

    def run(self) -> None:
        from backend import incidents

        while not self._parar.is_set():
            lote = self._lote(self.lotes)
            with self.db.connect() as conn:
                for obs in lote:
                    conn.execute(_SQL_OBSERVACION, _fila_observacion(obs))
            incidents.update(self.db, lote, self.ahora)
            self.lotes += 1
            self._parar.wait(self.paso_s)

    def detener(self) -> None:
        self._parar.set()


class HiloSonda(threading.Thread):
    """Escrituras de usuario reales (kv) en segundo plano para provocar respaldos del rol «restauracion»."""

    def __init__(self, db, contador_sql: ContadorSQL, paso_s: float = 0.5):
        super().__init__(name="bench-sonda", daemon=True)
        self.db = db
        self.paso_s = paso_s
        self.escrituras = 0
        self._parar = threading.Event()
        contador_sql.excluir(self)  # sus sentencias van al contador de fondo

    def run(self) -> None:
        while not self._parar.is_set():
            self.db.kv_set(f"bench:sonda:{self.escrituras}", "1")
            self.escrituras += 1
            self._parar.wait(self.paso_s)

    def detener(self) -> None:
        self._parar.set()


# ----------------------------------------------------------------------- hijo --

def _leer_fixture(directorio: Path) -> dict[str, bytes]:
    """Lee el fixture del respaldo: brasa.db tal cual y work.db comprimido con gzip
    (el formato exacto de las claves ``db/brasa.db`` y ``db/work.db.gz`` del almacenamiento)."""
    brasa = directorio / "brasa.db"
    work = directorio / "work.db.gz"
    if not brasa.exists() or not work.exists():
        raise FileNotFoundError(f"el fixture del respaldo no está completo en {directorio}")
    return {"db/brasa.db": brasa.read_bytes(), "db/work.db.gz": work.read_bytes()}


def _escribir_fixture(directorio: Path, db) -> dict:
    """Escribe el fixture desde la base sembrada, con las mismas herramientas de respaldo de la app."""
    directorio.mkdir(parents=True, exist_ok=True)
    brasa = db.snapshot()
    work_gz = gzip.compress(db.snapshot_work(), 6, mtime=0)  # mismos datos, mismos bytes
    (directorio / "brasa.db").write_bytes(brasa)
    (directorio / "work.db.gz").write_bytes(work_gz)
    return {"brasa_db_bytes": len(brasa), "work_gz_bytes": len(work_gz)}


def _arranque(modulo_principal, t0: float) -> dict:
    """Fases de arranque que la propia app publica en su estado (OPS-813/OPS-818)."""
    svc = modulo_principal.app.state.services
    return {
        "total_ms": round((time.perf_counter() - t0) * 1000),
        "startup_ms": svc.startup_ms,
        "fases": svc.startup,
        "work_db_bytes": svc.persistence.work_db_bytes,
    }


def _medir_caliente(client, ruta: str, muestras: int, contador_sql: ContadorSQL,
                    contador_ext: ContadorExterno) -> dict:
    """Una llamada de calentamiento explícita (no cuenta como muestra) y luego N muestras."""
    medir_llamada(client, ruta, contador_sql, contador_ext)
    medidas = [medir_llamada(client, ruta, contador_sql, contador_ext) for _ in range(muestras)]
    return {"muestras": medidas, "resumen": resumen_muestras(medidas)}


def _correr_hijo(args) -> dict:
    repo = Path(args.repo).resolve()
    if not (repo / "backend" / "main.py").exists():
        raise FileNotFoundError(f"{repo} no es un checkout con backend/main.py")
    sys.path.insert(0, str(repo))
    data_dir = Path(tempfile.mkdtemp(prefix="bench-api-"))
    restauradores: list = []
    try:
        for clave in CLAVES_ENV_LIMPIAS:
            os.environ[clave] = ""  # load_dotenv no puede reponer secretos del checkout.
        os.environ["BRASA_STORAGE_URL"] = ""
        os.environ["BRASA_SCHEDULER"] = "0"
        os.environ["BRASA_DATA_DIR"] = str(data_dir)

        fixture: dict[str, bytes] = {}
        if args.rol == "restauracion":
            os.environ["BRASA_STORAGE_URL"] = "http://almacen.bench/storage"
            fixture = _leer_fixture(Path(args.fixture_dir))

        # El reloj y los uuid se congelan ANTES de importar el backend medido.
        restauradores.append(congelar_reloj(EPOCA))
        restauradores.append(congelar_uuid())
        contador_sql = ContadorSQL()
        restauradores.append(instalar_traza_sqlite(contador_sql))
        contador_ext = ContadorExterno(fixture)

        from backend import main as modulo_principal
        restauradores.append(aislar_proveedores(contador_ext.transporte()))
        restauradores.append(acortar_reintentos())
        modulo_principal.HTTP_TRANSPORT = contador_ext.transporte()

        resultado: dict = {
            "repo": str(repo), "rol": args.rol, "ruta": args.ruta, "escala": args.escala,
            "reloj": EPOCA.isoformat(), "muestras_pedidas": args.samples,
        }

        if args.rol == "fixture":
            siembra = sembrar(data_dir, EPOCA, args.escala)
            resultado["fixture"] = _escribir_fixture(Path(args.fixture_dir), siembra["db"])
            resultado["fixture"]["incidentes"] = siembra["incidentes"]
            resultado["fixture"]["observaciones"] = siembra["observaciones"]
            siembra["db"].close_all()
            return resultado
        if args.rol != "restauracion":
            if not args.fixture_dir:
                raise ValueError("La medición necesita un fixture creado en otro proceso; no se precalienta con la siembra")
            respaldos = _leer_fixture(Path(args.fixture_dir))
            (data_dir / "brasa.db").write_bytes(respaldos["db/brasa.db"])
            (data_dir / "work.db").write_bytes(gzip.decompress(respaldos["db/work.db.gz"]))

        from fastapi.testclient import TestClient

        cliente = TestClient(modulo_principal.app)  # lifespan real: Services.start corre completo
        t0 = time.perf_counter()
        with cliente as activo:
            resultado["arranque"] = _arranque(modulo_principal, t0)
            svc = modulo_principal.app.state.services

            if args.rol == "restauracion":
                # La restauración ya corrió dentro del arranque: se mide lo que la app reporta.
                ruta = resolver_ruta(plantilla_de(args.ruta), svc.db)
                resultado["path"] = ruta
                sonda = HiloSonda(svc.db, contador_sql)
                sonda.start()
                try:
                    resultado.update(_medir_caliente(activo, ruta, args.samples, contador_sql, contador_ext))
                finally:
                    sonda.detener()
                    sonda.join(5)
                # El respaldo va con «debounce» de 3 s: se espera a que la subida ocurra para contarla.
                time.sleep(4.5)
            else:
                ruta = resolver_ruta(plantilla_de(args.ruta), svc.db)
                resultado["path"] = ruta
                if args.rol == "fria":
                    # Primera llamada de la ruta en el proceso: sin calentamiento alguno.
                    medida = medir_llamada(activo, ruta, contador_sql, contador_ext)
                    resultado["muestras"] = [medida]
                    resultado["resumen"] = resumen_muestras([medida])
                elif args.rol == "caliente":
                    resultado.update(_medir_caliente(activo, ruta, args.samples, contador_sql, contador_ext))
                elif args.rol == "contienda":
                    from backend.geo import territory
                    hilo = HiloIngesta(svc.db, contador_sql, territory(), EPOCA)
                    hilo.start()
                    try:
                        resultado.update(_medir_caliente(activo, ruta, args.samples, contador_sql, contador_ext))
                    finally:
                        hilo.detener()
                        hilo.join(10)
                    resultado["lotes_ingesta"] = hilo.lotes
                else:
                    raise ValueError(f"rol desconocido: {args.rol}")
        if args.rol == "restauracion":
            # Se arma después de cerrar la app: el respaldo final del cierre también se cuenta.
            restauracion = {
                "medido": svc.persistence.restore_db_ms is not None,
                "startup_ms": svc.startup_ms,
                "territory_ms": (svc.startup or {}).get("territory_ms"),
                "restore_db_ms": svc.persistence.restore_db_ms,
                "restore_work_ms": svc.persistence.restore_work_ms,
                "restore_work_parts": svc.persistence.restore_work_parts or None,
                "work_db_bytes": svc.persistence.work_db_bytes,
                "escrituras_sonda": sonda.escrituras,
                "respaldos_put": contador_ext.totales()["put"],
            }
            if not restauracion["medido"]:
                restauracion["motivo"] = "la restauración del respaldo no se completó (se declara no medido)"
            resultado["restauracion"] = restauracion
        resultado["externos_total"] = contador_ext.totales()
        return resultado
    finally:
        for restaurar in reversed(restauradores):
            try:
                restaurar()
            except Exception:
                pass
        shutil.rmtree(data_dir, ignore_errors=True)


def hijo(args) -> int:
    """Punto de entrada del proceso hijo: imprime una línea JSON con el resultado."""
    try:
        resultado = _correr_hijo(args)
    except Exception as exc:  # el padre lo registra como error de esa ruta/escenario
        resultado = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
    return 3 if resultado.get("error") else 0


# ---------------------------------------------------------------------- padre --

def _subproceso(repo: Path, extra: list[str], timeout_s: int) -> dict:
    """Un hijo nuevo por llamada: `python <este script> --hijo --repo <repo> ...`."""
    comando = [sys.executable, str(RUTA_SCRIPT), "--hijo", "--repo", str(repo), *extra]
    inicio = time.perf_counter()
    try:
        proceso = subprocess.run(comando, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"error": f"el hijo no terminó en {timeout_s} s",
                "proceso_total_ms": round((time.perf_counter() - inicio) * 1000, 1)}
    lineas = [linea for linea in (proceso.stdout or "").splitlines() if linea.strip()]
    if not lineas:
        cola = (proceso.stderr or "").strip().splitlines()[-3:]
        return {"error": f"el hijo no respondió (código {proceso.returncode})", "stderr_tail": cola}
    try:
        resultado = json.loads(lineas[-1])
        resultado["proceso_total_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
        return resultado
    except ValueError:
        return {"error": "la salida del hijo no es JSON"}


def correr_repo(repo: Path, out_dir: Path, muestras: int, escala: str, rutas_ids: list[str],
                gate_ms: float, min_muestras: int, con_restauracion: bool, timeout_s: int,
                fixture_compartido: Path | None = None) -> dict:
    """Corre la tanda completa sobre un checkout: hijos nuevos por ruta y escenario.

    Escribe ``benchmark.json`` e ``informe.md`` en ``out_dir`` y devuelve el resultado completo.
    """
    repo = Path(repo).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    resultados: dict[str, dict] = {rid: {} for rid in rutas_ids}

    fixture_dir = fixture_compartido or out_dir / "fixture"
    if fixture_compartido is None:
        print(f"[benchmark] {repo.name}: creando fixture del respaldo...", flush=True)
        fix = _subproceso(repo, ["--rol", "fixture", "--escala", escala, "--fixture-dir", str(fixture_dir)], timeout_s)
        if fix.get("error") or not fix.get("fixture"):
            datos = {"repo": str(repo), "rutas": {}, "gate": {"ok": False, "motivos": ["fixture no disponible"]}, "error": fix}
            (out_dir / "benchmark.json").write_text(json.dumps(datos, indent=1))
            return datos
    restauracion: dict = {"medido": False, "motivo": "no pedido (--sin-restauracion)"}
    if con_restauracion:
        print(f"[benchmark] {repo.name}: restauración...", flush=True)
        restauro = _subproceso(
            repo, ["--rol", "restauracion", "--ruta", "estado", "--samples", str(muestras),
                   "--escala", escala, "--fixture-dir", str(fixture_dir)], timeout_s)
        datos_rest = restauro.get("restauracion") or {}
        if restauro.get("error") or not datos_rest.get("medido"):
            motivo = restauro.get("error") or datos_rest.get("motivo") or "la restauración no se pudo medir"
            restauracion = {"medido": False, "motivo": f"no medido: {motivo}"}
        else:
            restauracion = datos_rest
            restauracion["latencias_calientes"] = restauro.get("resumen")

    for rid in rutas_ids:
        for rol in ROLES:
            print(f"[benchmark] {repo.name}: {rid}/{rol} ({muestras} muestras)...", flush=True)
            resultado_hijo = _subproceso(
                repo, ["--rol", rol, "--ruta", rid, "--samples", str(muestras), "--escala", escala,
                       "--fixture-dir", str(fixture_dir)], timeout_s)
            resultados[rid][rol] = resultado_hijo
            (out_dir / "benchmark.json").write_text(json.dumps({
                "repo": str(repo), "rutas": resultados, "incompleto": True,
                "restauracion": restauracion,
            }, ensure_ascii=False, indent=1))

    gate_ok, motivos = evaluar_gate(resultados, gate_ms, min_muestras)
    for rid, escenarios in resultados.items():
        for rol, medido in escenarios.items():
            if medido.get("error") or (medido.get("resumen") or {}).get("errores"):
                gate_ok = False
                motivos.append(f"{rid}/{rol}: medición fallida o respuesta con error")
    datos = {
        "herramienta": "benchmark_api",
        "repo": str(repo),
        "escala": escala,
        "muestras": muestras,
        "reloj": EPOCA.isoformat(),
        "python": sys.version.split()[0],
        "gate_ms": gate_ms,
        "min_muestras": min_muestras,
        "rutas": resultados,
        "restauracion": restauracion,
        "gate": {"ok": gate_ok, "motivos": motivos},
        "limites": LIMITES,
    }
    (out_dir / "benchmark.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (out_dir / "informe.md").write_text(informe_markdown(datos), encoding="utf-8")
    return datos


def comparar_resultados(base: dict, candidata: dict) -> dict:
    """Compara dos tandas completas: cuerpos por ruta y delta de p95 caliente.

    Si los cuerpos no son equivalentes, el delta de latencia se marca como no comparable:
    no se asume que unos milisegundos distintos con datos distintos sean una comparación válida.
    """
    por_ruta: dict[str, dict] = {}
    for rid in dict.fromkeys([*base["rutas"], *candidata["rutas"]]):
        rb = base["rutas"].get(rid) or {}
        rc = candidata["rutas"].get(rid) or {}
        fila: dict = {}
        for rol in ("fria", "caliente", "contienda"):
            veredicto = veredicto_cuerpos(rb.get(rol), rc.get(rol), rol)
            p95_base = ((rb.get(rol) or {}).get("resumen") or {}).get("p95")
            p95_cand = ((rc.get(rol) or {}).get("resumen") or {}).get("p95")
            fila[rol] = {
                "cuerpos": veredicto,
                "p95_base_ms": p95_base,
                "p95_candidata_ms": p95_cand,
                "delta_p95_ms": round(p95_cand - p95_base, 1) if p95_base is not None and p95_cand is not None else None,
                "comparable": veredicto.startswith("equivalentes"),
            }
        por_ruta[rid] = fila
    return {
        "modo": "repositorios",
        "base": base["repo"],
        "candidata": candidata["repo"],
        "por_ruta": por_ruta,
        "gate_candidata": candidata["gate"],
        "gate_base": base["gate"],
        "limites": LIMITES,
    }


def unir_url(base: str, ruta: str) -> str:
    return base.rstrip("/") + ruta


def _primer_incidente_url(cliente: httpx.Client, base: str) -> str | None:
    """Resuelve el id de un incidente vivo para la ruta ficha (una sola consulta GET)."""
    respuesta = cliente.get(unir_url(base, "/api/incidents?hours=48"))
    if respuesta.status_code != 200:
        return None
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return None
    incidentes = cuerpo.get("incidents") or cuerpo.get("data") or []
    for item in incidentes:
        if isinstance(item, dict) and item.get("id"):
            return str(item["id"])
    return None


def comparar_urls(base: str, candidata: str, muestras: int, rutas_ids: list[str], gate_ms: float,
                  min_muestras: int, timeout_s: float) -> dict:
    """Compara dos servidores vivos con llamadas alternadas (primera llamada aparte).

    Sin acceso al proceso no hay contadores de SQL ni de externos: se mide HTTP real.
    Los cuerpos cambian solos contra datos vivos: la comparación de cuerpos solo es útil
    entre dos servidores con el mismo dataset.
    """
    cliente = httpx.Client(timeout=timeout_s)
    por_ruta: dict[str, dict] = {}
    gate_resultados: dict[str, dict] = {}
    try:
        for rid in rutas_ids:
            plantilla = plantilla_de(rid)
            if "{incident_id}" in plantilla:
                id_incidente = _primer_incidente_url(cliente, candidata)
                if not id_incidente:
                    por_ruta[rid] = {"error": "no se pudo resolver el id del incidente para la ficha"}
                    gate_resultados[rid] = {"caliente": {"resumen": {}}}
                    continue
                ruta = plantilla.replace("{incident_id}", id_incidente)
            else:
                ruta = plantilla
            # Primera llamada de cada lado (proceso nuevo/servidor en frío), aparte del caliente.
            primera_base = medir_llamada(cliente, unir_url(base, ruta))
            primera_cand = medir_llamada(cliente, unir_url(candidata, ruta))
            muestras_base, muestras_cand = [], []
            for _ in range(muestras):  # alternadas: pares contemporáneos, sin deriva de reloj
                muestras_base.append(medir_llamada(cliente, unir_url(base, ruta)))
                muestras_cand.append(medir_llamada(cliente, unir_url(candidata, ruta)))
            por_ruta[rid] = {
                "path": ruta,
                "primera": {"base": primera_base, "candidata": primera_cand},
                "base": {"muestras": muestras_base, "resumen": resumen_muestras(muestras_base)},
                "candidata": {"muestras": muestras_cand, "resumen": resumen_muestras(muestras_cand)},
                "cuerpos": veredicto_cuerpos(
                    {"muestras": [primera_base] + muestras_base}, {"muestras": [primera_cand] + muestras_cand}),
            }
            gate_resultados[rid] = {"caliente": {"resumen": por_ruta[rid]["candidata"]["resumen"]}}
    finally:
        cliente.close()
    gate_ok, motivos = evaluar_gate(gate_resultados, gate_ms, min_muestras)
    return {
        "modo": "urls",
        "base": base,
        "candidata": candidata,
        "muestras": muestras,
        "por_ruta": por_ruta,
        "gate": {"ok": gate_ok, "motivos": motivos},
        "limites": LIMITES,
    }


# -------------------------------------------------------------------- informe --

def _ms_texto(valor) -> str:
    return f"{valor:.0f}" if isinstance(valor, (int, float)) else "—"


def informe_markdown(datos: dict) -> str:
    """Informe legible de una tanda: latencias, arranque, restauración, gate y límites."""
    lineas = [
        "# Benchmark API — BRASA Chile",
        "",
        f"- Repositorio medido: `{datos['repo']}` (Python {datos['python']})",
        f"- Escala de datos: {datos['escala']} · muestras calientes: {datos['muestras']} · reloj congelado: {datos['reloj']}",
        f"- Gate: p95 caliente <= {datos['gate_ms']:.0f} ms, sin errores y >= {datos['min_muestras']} muestras",
        "",
        "## Latencias por ruta y escenario",
        "",
        "| ruta | escenario | n | errores | p50 ms | p95 ms | máx ms | SQL/llamada | externos | arranque ms |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rid, escenarios in datos["rutas"].items():
        for rol, hijo_resultado in escenarios.items():
            resumen = hijo_resultado.get("resumen") or {}
            arranque = (hijo_resultado.get("arranque") or {}).get("total_ms")
            externos = (hijo_resultado.get("externos_total") or {}).get("total", "—")
            lineas.append(
                f"| `{rid}` | {rol} | {resumen.get('n', '—')} | {resumen.get('errores', '—')} | "
                f"{_ms_texto(resumen.get('p50'))} | {_ms_texto(resumen.get('p95'))} | {_ms_texto(resumen.get('max'))} | "
                f"{resumen.get('sql_por_llamada', '—')} | {externos} | {_ms_texto(arranque)} |")
    restauracion = datos.get("restauracion") or {}
    lineas += ["", "## Arranque y restauración", ""]
    if restauracion.get("medido"):
        lineas += [
            f"- startup: {restauracion.get('startup_ms')} ms (territorio: {restauracion.get('territory_ms')} ms)",
            f"- restauración de brasa.db: {restauracion.get('restore_db_ms')} ms",
            f"- restauración de work.db: {restauracion.get('restore_work_ms')} ms "
            f"(desglose: {json.dumps(restauracion.get('restore_work_parts') or {})})",
            f"- subidas de respaldo contadas: {restauracion.get('respaldos_put')} PUT",
        ]
    else:
        lineas.append(f"- No medido: {restauracion.get('motivo', 'no pedido')}")
    lineas += ["", "## Gate", ""]
    lineas.append("APROBADO" if datos["gate"]["ok"] else "REPROBADO")
    for motivo in datos["gate"]["motivos"]:
        lineas.append(f"- {motivo}")
    lineas += ["", "## Límites de la medición", ""]
    lineas += [f"- {texto}" for texto in datos.get("limites", LIMITES)]
    lineas.append("")
    return "\n".join(lineas)


def informe_comparacion_markdown(comparacion: dict) -> str:
    """Informe de la comparación base/candidata: cuerpos primero, delta de p95 después."""
    lineas = [
        "# Comparación benchmark API — BRASA Chile",
        "",
        f"- Base: `{comparacion.get('base')}` · Candidata: `{comparacion.get('candidata')}`",
        "",
        "| ruta | escenario | cuerpos | p95 base ms | p95 candidata ms | delta p95 ms | comparable |",
        "|---|---|---|---|---|---|---|",
    ]
    for rid, fila in comparacion["por_ruta"].items():
        if "cuerpos" in fila:  # modo urls: una fila por ruta con base/candidata ya resumidas
            res_base = (fila.get("base") or {}).get("resumen") or {}
            res_cand = (fila.get("candidata") or {}).get("resumen") or {}
            p95_base, p95_cand = res_base.get("p95"), res_cand.get("p95")
            comparable = str(fila["cuerpos"]).startswith("equivalentes")
            lineas.append(
                f"| `{rid}` | caliente | {fila['cuerpos']} | {_ms_texto(p95_base)} | {_ms_texto(p95_cand)} | "
                f"{_ms_texto(round(p95_cand - p95_base, 1)) if p95_base is not None and p95_cand is not None else '—'} | "
                f"{'sí' if comparable else 'no'} |")
            continue
        for rol, datos_rol in fila.items():
            lineas.append(
                f"| `{rid}` | {rol} | {datos_rol['cuerpos']} | {_ms_texto(datos_rol['p95_base_ms'])} | "
                f"{_ms_texto(datos_rol['p95_candidata_ms'])} | {_ms_texto(datos_rol['delta_p95_ms'])} | "
                f"{'sí' if datos_rol['comparable'] else 'no'} |")
    gate = comparacion.get("gate_candidata") or comparacion.get("gate") or {}
    lineas += ["", "## Gate de la candidata", "", "APROBADO" if gate.get("ok") else "REPROBADO"]
    for motivo in gate.get("motivos", []):
        lineas.append(f"- {motivo}")
    lineas += ["", "## Límites de la medición", ""]
    lineas += [f"- {texto}" for texto in comparacion.get("limites", LIMITES)]
    lineas.append("")
    return "\n".join(lineas)


# ------------------------------------------------------------------------ CLI --

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark_api.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".", help="checkout a medir (con backend/); por defecto, el actual")
    parser.add_argument("--base-repo", help="checkout base para comparar dos carpetas de trabajo")
    parser.add_argument("--candidate-repo", help="checkout candidata (este script es siempre el de la candidata)")
    parser.add_argument("--base", help="URL base viva para comparar alternada (por ejemplo http://127.0.0.1:8001)")
    parser.add_argument("--candidate", help="URL candidata viva para comparar alternada")
    parser.add_argument("--out", default="benchmark_api_out", help="carpeta de salida del informe")
    parser.add_argument("--samples", "--muestras", dest="samples", type=int, default=MIN_MUESTRAS,
                        help=f"muestras calientes por ruta (mínimo {MIN_MUESTRAS} para el gate)")
    parser.add_argument("--escala", choices=ESCALAS, default="volumen",
                        help="dataset determinista: demo (2 incidentes) o volumen (2 000/200)")
    parser.add_argument("--rutas", default=",".join(ruta["id"] for ruta in RUTAS),
                        help="ids de rutas a medir, separados por coma")
    parser.add_argument("--gate-ms", type=float, default=GATE_P95_MS, help="tope del p95 caliente en ms")
    parser.add_argument("--timeout", type=int, default=300, help="tope de espera por hijo en segundos")
    parser.add_argument("--sin-restauracion", action="store_true", help="no mide las fases de respaldo/restauración")
    # Argumentos del hijo (contrato interno): un proceso nuevo por ruta y escenario.
    parser.add_argument("--hijo", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--rol", choices=(*ROLES, "fixture", "restauracion"), help=argparse.SUPPRESS)
    parser.add_argument("--ruta", help=argparse.SUPPRESS)
    parser.add_argument("--fixture-dir", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.hijo:
        if not args.rol:
            print("el hijo necesita --rol", file=sys.stderr)
            return 2
        return hijo(args)
    if args.samples < 1:
        print("--samples debe ser >= 1", file=sys.stderr)
        return 2
    rutas_ids = [rid.strip() for rid in args.rutas.split(",") if rid.strip()]
    for rid in rutas_ids:
        plantilla_de(rid)  # valida el id antes de arrancar
    out = Path(args.out)

    if bool(args.base) != bool(args.candidate):
        print("--base y --candidate van juntos (comparación de URLs vivas)", file=sys.stderr)
        return 2
    if bool(args.base_repo) != bool(args.candidate_repo):
        print("--base-repo y --candidate-repo van juntos (comparación de dos checkouts)", file=sys.stderr)
        return 2
    if args.base and args.candidate:
        comparacion = comparar_urls(args.base, args.candidate, args.samples, rutas_ids, args.gate_ms, MIN_MUESTRAS, args.timeout)
        out.mkdir(parents=True, exist_ok=True)
        (out / "comparacion.json").write_text(
            json.dumps(comparacion, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        (out / "informe_comparacion.md").write_text(informe_comparacion_markdown(comparacion), encoding="utf-8")
        return 0 if comparacion["gate"]["ok"] else 1

    if args.base_repo and args.candidate_repo:
        out.mkdir(parents=True, exist_ok=True)
        fixture_dir = out / "fixture"
        fix = _subproceso(Path(args.base_repo), [
            "--rol", "fixture", "--escala", args.escala, "--fixture-dir", str(fixture_dir)
        ], args.timeout)
        if fix.get("error") or not fix.get("fixture"):
            (out / "comparacion.json").write_text(json.dumps({"errorFixture": fix, "valida": False}, indent=1))
            return 1
        agregados = {}
        orden = []
        for i, rid in enumerate(rutas_ids):
            lados = ("base", "candidata") if i % 2 == 0 else ("candidata", "base")
            for lado in lados:
                repo = Path(args.base_repo if lado == "base" else args.candidate_repo)
                orden.append({"ruta": rid, "lado": lado})
                medido = correr_repo(repo, out / lado / rid, args.samples, args.escala, [rid],
                                     args.gate_ms, MIN_MUESTRAS,
                                     not args.sin_restauracion and i == 0, args.timeout,
                                     fixture_compartido=fixture_dir)
                if lado not in agregados:
                    agregados[lado] = {**medido, "rutas": {}, "gate": {"ok": True, "motivos": []}}
                agregados[lado]["rutas"].update(medido["rutas"])
                agregados[lado]["gate"]["ok"] &= medido["gate"]["ok"]
                agregados[lado]["gate"]["motivos"].extend(medido["gate"]["motivos"])
        base, candidata = agregados["base"], agregados["candidata"]
        comparacion = comparar_resultados(base, candidata)
        comparacion["orden"] = orden
        comparacion["fixture"] = fix["fixture"]
        comparacion["revision_base"] = subprocess.check_output(
            ["git", "-C", str(Path(args.base_repo)), "rev-parse", "HEAD"], text=True).strip()
        comparacion["revision_candidata"] = subprocess.check_output(
            ["git", "-C", str(Path(args.candidate_repo)), "rev-parse", "HEAD"], text=True).strip()
        (out / "comparacion.json").write_text(
            json.dumps(comparacion, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        (out / "informe_comparacion.md").write_text(informe_comparacion_markdown(comparacion), encoding="utf-8")
        return 0 if candidata["gate"]["ok"] and base["gate"]["ok"] else 1

    datos = correr_repo(Path(args.repo), out, args.samples, args.escala, rutas_ids,
                        args.gate_ms, MIN_MUESTRAS, not args.sin_restauracion, args.timeout)
    return 0 if datos["gate"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
