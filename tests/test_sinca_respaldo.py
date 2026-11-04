"""OFI-10 (Tanda 3A): respaldo de borde (`SINCA_PROXY_URL`) y snapshot (`SINCA_SNAPSHOT_PATH`) para estaciones SINCA.

Verifica:
- Uso de `SINCA_PROXY_URL` cuando está configurado (y fallback a la URL directa si el proxy falla).
- Fallback al snapshot cuando la petición HTTP falla y el snapshot es reciente (< 12 h), incluyendo `source_mode == "snapshot"` y preservación de `fetched_at`.
- Rechazo del snapshot cuando su `fetched_at` es antiguo (> 12 h), devolviendo degradación honesta (`status: "unavailable"`, `air: None`).
- El script `scripts/actualizar_sinca_snapshot.py` con respuesta simulada.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from backend.providers import sinca
from scripts import actualizar_sinca_snapshot
from tests.conftest import json_response

CHILE = ZoneInfo("America/Santiago")
NOW = datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc)  # 01:00 en Chile (UTC-3)


@pytest.fixture(autouse=True)
def entorno_sinca_limpio(monkeypatch):
    """La ventana de 12 h y la URL directa no heredan variables del entorno local."""
    for key in ("SINCA_PROXY_URL", "SINCA_SNAPSHOT_PATH", "SINCA_MAX_SNAPSHOT_AGE_HOURS"):
        monkeypatch.delenv(key, raising=False)


def fresco_ahora() -> str:
    """Hora local de Chile hace 30 min para lecturas vigentes respecto del reloj real."""
    return (datetime.now(CHILE) - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")


def estacion_raw(lat=-33.44, lon=-70.68, nombre="Cerro Navia", key="101", comuna="Cerro Navia",
                 region="Metropolitana", valor=18.4, icap=34, status="bueno", momento=None):
    momento = momento or "2026-10-23 22:00"
    pm25 = {
        "code": "PM25",
        "name": "MP-2,5",
        "tableRow": {
            "datetime": momento,
            "parameter": "MP 2,5",
            "movil": "media móvil 24 h",
            "value": valor,
            "icap": icap,
            "status": status,
            "statuscode": 1,
        },
    }
    return {
        "nombre": nombre,
        "key": key,
        "latitud": lat,
        "longitud": lon,
        "comuna": comuna,
        "region": region,
        "realtime": [pm25],
    }


# --- 1. SINCA_PROXY_URL ---

def test_fetch_network_usa_sinca_proxy_url_cuando_esta_configurado(monkeypatch):
    proxy = "https://sinca-relay.ejemplo.workers.dev/listadomapa2k19"
    monkeypatch.setenv("SINCA_PROXY_URL", proxy)
    urls_llamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls_llamadas.append(str(request.url))
        if str(request.url) == proxy:
            return json_response([estacion_raw()])
        return httpx.Response(503)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await sinca.fetch_network_with_meta(http, now=NOW)

    meta = asyncio.run(run())
    assert urls_llamadas == [proxy], "debe usar primero SINCA_PROXY_URL y no tocar sinca.mma.gob.cl si el proxy responde"
    assert meta["source_mode"] == "live"
    assert meta["status"] == "ok"
    assert len(meta["stations"]) == 1
    assert meta["stations"][0]["name"] == "Cerro Navia"
    assert meta["stations"][0]["pm25"] == 18.4


def test_fetch_network_cae_a_url_directa_si_proxy_falla(monkeypatch):
    proxy = "https://sinca-relay.ejemplo.workers.dev/listadomapa2k19"
    monkeypatch.setenv("SINCA_PROXY_URL", proxy)
    urls_llamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls_llamadas.append(str(request.url))
        if str(request.url) == proxy:
            return httpx.Response(502)
        return json_response([estacion_raw(nombre="Talca", lat=-35.43, lon=-71.67)])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await sinca.fetch_network_with_meta(http, now=NOW)

    meta = asyncio.run(run())
    assert urls_llamadas[0] == proxy and urls_llamadas[-1] == sinca.RED_URL
    assert meta["source_mode"] == "live"
    assert meta["stations"][0]["name"] == "Talca"


# --- 2. Fallback a snapshot reciente (< 12 h) ---

def test_fallback_a_snapshot_reciente_cuando_http_falla(monkeypatch, tmp_path):
    snap_file = tmp_path / "sinca_snapshot.json"
    fetched_dt = NOW - timedelta(hours=3)
    actualizar_sinca_snapshot.actualizar_snapshot(
        snap_file,
        payload=[estacion_raw(momento="2026-10-23 22:00")],
        fetched_at=fetched_dt,
    )
    monkeypatch.setenv("SINCA_SNAPSHOT_PATH", str(snap_file))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as http:
            return await sinca.fetch_network_with_meta(http, now=NOW)

    meta = asyncio.run(run())
    assert meta["source_mode"] == "snapshot"
    assert meta["status"] == "ok"
    assert meta["fetched_at"] == "2026-10-24T01:00:00Z"
    assert len(meta["stations"]) == 1
    assert meta["stations"][0]["name"] == "Cerro Navia"
    assert meta["stations"][0]["pm25"] == 18.4


def test_endpoint_sirve_snapshot_reciente_con_source_mode_snapshot(make_client, web, tmp_path):
    snap_file = tmp_path / "sinca_snapshot.json"
    ahora_utc = datetime.now(timezone.utc).replace(microsecond=0)
    fetched_dt = ahora_utc - timedelta(hours=2)
    actualizar_sinca_snapshot.actualizar_snapshot(
        snap_file,
        payload=[estacion_raw(momento=fresco_ahora(), valor=22.5, icap=45, status="regular")],
        fetched_at=fetched_dt,
    )
    web.add(lambda r: "sinca.mma.gob.cl" in r.url.host, lambda r: httpx.Response(403))

    with make_client(SINCA_SNAPSHOT_PATH=str(snap_file)) as client:
        body = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()

    assert body["source_mode"] == "snapshot"
    assert body["status"] == "ok"
    assert body["fetched_at"] == fetched_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert body["air"] is not None
    assert body["air"]["name"] == "Cerro Navia"
    assert body["air"]["pm25"] == 22.5
    assert body["air"]["source_mode"] == "snapshot"
    assert body["air"]["fetched_at"] == fetched_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- 3. Rechazo de snapshot antiguo (> 12 h) y degradación honesta ---

def test_rechaza_snapshot_antiguo_mayor_a_12h(monkeypatch, tmp_path):
    snap_file = tmp_path / "sinca_viejo.json"
    fetched_viejo = NOW - timedelta(hours=13)
    actualizar_sinca_snapshot.actualizar_snapshot(
        snap_file,
        payload=[estacion_raw(momento="2026-10-23 22:00")],
        fetched_at=fetched_viejo,
    )
    monkeypatch.setenv("SINCA_SNAPSHOT_PATH", str(snap_file))

    assert sinca.load_snapshot(now=NOW) is None

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as http:
            await sinca.fetch_network(http, now=NOW)

    with pytest.raises(sinca.SincaError):
        asyncio.run(run())


def test_endpoint_degrada_honestamente_si_snapshot_es_antiguo(make_client, web, tmp_path):
    snap_file = tmp_path / "sinca_viejo.json"
    ahora_utc = datetime.now(timezone.utc)
    fetched_viejo = ahora_utc - timedelta(hours=14)
    actualizar_sinca_snapshot.actualizar_snapshot(
        snap_file,
        payload=[estacion_raw(momento=fresco_ahora())],
        fetched_at=fetched_viejo,
    )
    web.add(lambda r: "sinca.mma.gob.cl" in r.url.host, lambda r: httpx.Response(503))

    with make_client(SINCA_SNAPSHOT_PATH=str(snap_file)) as client:
        body = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()

    assert body["air"] is None
    assert body["status"] == "unavailable"
    assert body["source_mode"] == "unavailable"


# --- 4. Script scripts/actualizar_sinca_snapshot.py con respuesta simulada ---

def test_script_actualizar_sinca_snapshot_con_respuesta_simulada(monkeypatch, tmp_path):
    destino = tmp_path / "sinca_snapshot.json"
    muestra = [
        estacion_raw(lat=-33.44, lon=-70.68, nombre="Cerro Navia", key="101",
                     comuna="Cerro Navia", region="Metropolitana", valor=15.2, icap=28, status="bueno"),
        estacion_raw(lat=-36.82, lon=-73.05, nombre="Concepción", key="202",
                     comuna="Concepción", region="Biobío", valor=42.8, icap=85, status="regular"),
        {"nombre": "Incompleta", "latitud": None, "longitud": None, "realtime": []},
    ]

    def fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(200, json=muestra, request=req)

    monkeypatch.setattr(actualizar_sinca_snapshot.httpx, "get", fake_get)
    rc = actualizar_sinca_snapshot.main(["--output", str(destino)])
    assert rc == 0
    assert destino.is_file()

    contenido = json.loads(destino.read_text(encoding="utf-8"))
    assert contenido["fetched_at"].endswith("Z")
    assert contenido["source_url"] == sinca.RED_URL
    assert len(contenido["stations"]) == 2
    primera = contenido["stations"][0]
    for campo in ("code", "name", "comuna", "region", "lat", "lon", "mp25", "pm25", "icap", "status", "observed_at"):
        assert campo in primera
    assert primera["code"] == "101"
    assert primera["name"] == "Cerro Navia"
    assert primera["mp25"] == 15.2
    assert primera["status"] == "bueno"


def test_estacion_snapshot_sin_observed_at_se_descarta(tmp_path):
    """Una estación del respaldo sin `observed_at` propio no hereda `fetched_at`."""
    snap_file = tmp_path / "sinca_sin_hora.json"
    snap_file.write_text(
        json.dumps({
            "fetched_at": "2026-10-24T03:30:00Z",
            "source_url": sinca.RED_URL,
            "stations": [
                {"code": "101", "name": "Sin Hora", "comuna": "Santiago", "lat": -33.44, "lon": -70.68, "pm25": 20.0},
                {"code": "102", "name": "Con Hora", "comuna": "Santiago", "lat": -33.45, "lon": -70.66, "pm25": 18.0, "observed_at": "2026-10-24T01:00:00Z"},
            ],
        }),
        encoding="utf-8",
    )
    loaded = sinca.load_snapshot(snap_file, now=NOW)
    assert loaded is not None
    assert [s["code"] for s in loaded["stations"]] == ["102"]


def test_consulta_en_vivo_persiste_snapshot_y_expira_al_vencer_12h(make_client, web, tmp_path):
    """Una descarga en vivo guarda el respaldo en disco y el TTL en caché no supera el vencimiento de 12 h."""
    snap_file = tmp_path / "sinca_auto.json"
    en_vivo = True

    def responder(req: httpx.Request) -> httpx.Response:
        if en_vivo:
            return json_response([estacion_raw(momento=fresco_ahora(), valor=19.3)])
        return httpx.Response(503)

    web.add(lambda r: "sinca.mma.gob.cl" in r.url.host, responder)
    with make_client(SINCA_SNAPSHOT_PATH=str(snap_file)) as client:
        primero = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()
        assert primero["source_mode"] == "live"
        assert snap_file.is_file()
        # Si expira la caché corta y SINCA cae, sirve el snapshot recién guardado en vivo.
        en_vivo = False
        client.app.state.services.db.conn.execute("DELETE FROM http_cache WHERE key = 'sinca:red'")
        segundo = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()
        assert segundo["source_mode"] == "snapshot"
        assert segundo["air"]["pm25"] == 19.3

