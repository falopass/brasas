"""OFI-33: la estación automática de la DMC más cercana a un lugar, medida de verdad.

La red EMA se baja una vez (`getDatosRecientesRedEma`), se destila y se comparte en caché;
cada lugar solo consulta cuál le queda más cerca. Nada se inventa: sin credenciales, sin
estación a ≤25 km o con la lectura atrasada, la respuesta es null.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.providers import dmc_stations
from tests.conftest import json_response

NOW = datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc)
FRESCO = "2026-10-24 03:10:00"          # ~50 min atrás de NOW: fresco
VIEJO = "2026-10-23 12:00:00"           # >3 h: ya no es «medido ahora»


def fresco_ahora() -> str:
    """Los tests del endpoint usan el reloj real del servidor: el momento se ancla al ahora
    para que la lectura siga «fresca» sin importar cuándo corra la suite."""
    return (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")


def estacion(lat, lon, nombre="Estación", momento=FRESCO, **lectura):
    base = {"temperatura": "11.9 °C", "humedadRelativa": "69 %",
            "fuerzaDelVientoPromedio10Minutos": "6.4 kt",
            "direccionDelVientoPromedio10Minutos": "180"}
    base.update(lectura)
    return {"estacion": {"codigoNacional": "000000", "nombreEstacion": nombre,
                         "latitud": lat, "longitud": lon, "altura": 520},
            "datos": [{"momento": momento, **base}]}


def red(*items):
    return {"estacionesConDatos": len(items), "datosEstaciones": list(items)}


# --- parsing: texto con unidad → número, nulos → None ---

@pytest.mark.parametrize("texto, esperado", [
    ("11.9 °C", 11.9), ("69 %", 69.0), (" 0.000 Watt/m2", 0.0), ("6,4 kt", 6.4),
    (None, None), ("", None), ("—", None), (12.5, None),
])
def test_num_descompone_texto_con_unidad(texto, esperado):
    assert dmc_stations._num(texto) == esperado


def test_latest_network_destila_una_fila_por_estacion():
    """Kt → km/h, dirección en grados; sin lectura o sin coords la fila no nace."""
    filas = dmc_stations.latest_network(red(
        estacion(-33.44, -70.68, "Quinta Normal, Santiago"),
        {"estacion": {"nombreEstacion": "Sin datos", "latitud": -33, "longitud": -70}, "datos": []},
        {"estacion": {"nombreEstacion": "Sin coords", "latitud": None, "longitud": None},
         "datos": [{"momento": FRESCO, "temperatura": "10.0 °C"}]},
    ))
    assert len(filas) == 1
    st = filas[0]
    assert st["name"] == "Quinta Normal, Santiago" and st["code"] == "000000"
    assert st["temp_c"] == 11.9 and st["humidity"] == 69.0
    assert st["wind_kmh"] == pytest.approx(11.9, abs=0.1)   # 6.4 kt × 1.852
    assert st["wind_deg"] == 180.0 and st["observed_at"] == FRESCO


def test_latest_network_respalda_al_viento_instantaneo():
    """Sin promedio de 10 min se usa el instantáneo; sin ambos, el viento sale None."""
    filas = dmc_stations.latest_network(red(
        estacion(-33.4, -70.7, "Solo instantáneo", fuerzaDelVientoPromedio10Minutos=None,
                 direccionDelVientoPromedio10Minutos=None, fuerzaDelViento="10 kt",
                 direccionDelViento="270"),
        estacion(-33.4, -70.7, "Sin viento", fuerzaDelVientoPromedio10Minutos=None,
                 direccionDelVientoPromedio10Minutos=None, fuerzaDelViento=None,
                 direccionDelViento=None),
    ))
    assert filas[0]["wind_kmh"] == pytest.approx(18.5, abs=0.1) and filas[0]["wind_deg"] == 270.0
    assert filas[1]["wind_kmh"] is None and filas[1]["wind_deg"] is None


# --- nearest: distancia, frescura y un solo ganador ---

def test_nearest_elige_la_mas_cercana_con_lectura_fresca():
    stns = dmc_stations.latest_network(red(
        estacion(-33.44, -70.68, "Quinta Normal"),
        estacion(-35.43, -71.67, "Talca"),               # ~220 km: fuera
        estacion(-33.30, -70.55, "Atrasada", momento=VIEJO),  # cerca pero sin dato fresco
    ))
    cerca = dmc_stations.nearest(stns, -33.45, -70.66, now=NOW)
    assert cerca["name"] == "Quinta Normal" and cerca["distance_km"] == pytest.approx(2.4, abs=0.6)
    # La hora servida es la de la estación ganadora, no la de la última fila del bucle.
    assert cerca["observed_at"] == "2026-10-24T03:10:00Z" and cerca["temperature_c"] == 11.9


def test_nearest_sin_estacion_a_25_km_devuelve_none():
    stns = dmc_stations.latest_network(red(estacion(-35.43, -71.67, "Talca")))
    assert dmc_stations.nearest(stns, -33.45, -70.66, now=NOW) is None


def test_nearest_lectura_atrasada_devuelve_none():
    stns = dmc_stations.latest_network(red(estacion(-33.44, -70.68, "Quinta", momento=VIEJO)))
    assert dmc_stations.nearest(stns, -33.45, -70.66, now=NOW) is None


# --- fetch_network: credenciales en params y errores explícitos ---

def test_fetch_network_envia_credenciales_y_destila():
    pedidos = []

    def handler(request):
        pedidos.append(request.url.params)
        return json_response(red(estacion(-33.44, -70.68, "Quinta Normal")))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await dmc_stations.fetch_network(http, "u@x.cl", "k")

    filas = asyncio.run(run())
    assert pedidos[0]["usuario"] == "u@x.cl" and pedidos[0]["token"] == "k"
    assert len(filas) == 1 and filas[0]["name"] == "Quinta Normal"


def test_fetch_network_mensaje_de_bloqueo_es_error():
    def handler(request):
        return json_response({"mensaje": "Este servicio ha sido bloqueado para el usuario que consulta"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await dmc_stations.fetch_network(http, "u", "k")

    with pytest.raises(dmc_stations.DmcStationsError):
        asyncio.run(run())


def test_fetch_network_caida_del_portal_es_error():
    async def run():
        async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda r: httpx.Response(503))) as http:
            await dmc_stations.fetch_network(http, "u", "k")

    with pytest.raises(dmc_stations.DmcStationsError):
        asyncio.run(run())


# --- el endpoint ---

def test_endpoint_devuelve_la_estacion_mas_cercana(make_client, web):
    momento = fresco_ahora()
    web.add(lambda r: "meteochile" in r.url.host,
            lambda r: json_response(red(
                estacion(-33.44, -70.68, "Quinta Normal, Santiago", momento=momento),
                estacion(-35.43, -71.67, "Talca", momento=momento),
            )))
    with make_client(DMC_USUARIO="u@x.cl", DMC_TOKEN="k") as client:
        body = client.get("/api/climate/station?lat=-33.45&lon=-70.66").json()
    s = body["station"]
    assert s["name"] == "Quinta Normal, Santiago" and s["distance_km"] < 25
    assert s["observed_at"].startswith(momento[:10]) and s["observed_at"].endswith("Z")
    assert s["temperature_c"] == 11.9 and s["humidity"] == 69.0 and s["wind_kmh"] > 0
    assert "DMC" in body["source"] and "climatologia" in body["source_url"]


def test_endpoint_red_cacheada_sirve_a_otro_punto(make_client, web):
    llamadas = []
    momento = fresco_ahora()
    web.add(lambda r: "meteochile" in r.url.host,
            lambda r: (llamadas.append(r), json_response(red(
                estacion(-33.44, -70.68, "Quinta Normal", momento=momento),
                estacion(-33.65, -70.58, "Puente Alto", momento=momento),)))[1])
    with make_client(DMC_USUARIO="u@x.cl", DMC_TOKEN="k") as client:
        a = client.get("/api/climate/station?lat=-33.45&lon=-70.66").json()
        b = client.get("/api/climate/station?lat=-33.64&lon=-70.57").json()
    assert len(llamadas) == 1, "la segunda consulta no vuelve a llamar a la DMC"
    assert a["station"]["name"] == "Quinta Normal" and b["station"]["name"] == "Puente Alto"


def test_endpoint_sin_credenciales_no_llama_y_devuelve_null(make_client, web):
    llamadas = []
    web.add(lambda r: "meteochile" in r.url.host,
            lambda r: (llamadas.append(r), json_response(red()))[1])
    with make_client() as client:
        body = client.get("/api/climate/station?lat=-33.45&lon=-70.66").json()
    assert body["station"] is None and not llamadas and body["source"]


def test_endpoint_fuera_de_rango_devuelve_null(make_client, web):
    web.add(lambda r: "meteochile" in r.url.host,
            lambda r: json_response(red(estacion(-35.43, -71.67, "Talca", momento=fresco_ahora()))))
    with make_client(DMC_USUARIO="u", DMC_TOKEN="k") as client:
        body = client.get("/api/climate/station?lat=-33.45&lon=-70.66").json()
    assert body["station"] is None


def test_endpoint_fuente_caida_no_inventa(make_client, web):
    web.add(lambda r: "meteochile" in r.url.host, lambda r: httpx.Response(503))
    with make_client(DMC_USUARIO="u", DMC_TOKEN="k") as client:
        body = client.get("/api/climate/station?lat=-33.45&lon=-70.66").json()
    assert body["station"] is None and body["source"]
