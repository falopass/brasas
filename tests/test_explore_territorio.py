"""QA-89: contrato territorial de /api/explore.

`/api/explore` es el único endpoint público que declara cuántas detecciones
quedaron dentro (`in_chile`) y fuera (`outside_chile`) de Chile. El recorte fino
es territorial —comunas BCN con tolerancia costera en `csv_hotspots`
(`backend/providers/firms.py`)—, no por caja: si alguien lo quita al tocar la
ingesta, focos de Argentina, Bolivia y Perú vuelven a colarse (FUEGO-12/FUEGO-04)
sin que el CI lo note.

`comuna_code` viaja en `points` por contrato: es campo público también en
`/api/observations` (`OBSERVATION_FIELDS`, DET-20) y en los GeoJSON de
`/api/opendata`. Lo que nunca debe salir son las columnas internas de la tabla
`observations` (`run_id`, `ingested_at`, `alerts_evaluated_at`): si el endpoint
se reescribe leyendo de la base, esta prueba las caza.
"""

from __future__ import annotations

import json

import httpx

from backend.geo import territory
from backend.providers import firms

# Focos sembrados fuera de Chile. (-17.7, -66.3) es Bolivia profundo —queda fuera
# hasta de la caja que se pide a FIRMS— y (-19.0, -68.0) es Bolivia DENTRO de la
# caja de la zona «chile»: solo el recorte territorial lo detiene, que es el
# filtro que esta prueba guarda.
SEMILLAS_BOLIVIA = [(-17.70, -66.30), (-19.00, -68.00)]

# Columnas de la tabla `observations` que son detalle interno y jamás salen al cliente.
CAMPOS_INTERNOS = {"run_id", "ingested_at", "alerts_evaluated_at"}


def _csv(puntos: list[tuple[float, float]]) -> str:
    filas = "\n".join(f"{lat},{lon},340.0,2027-01-15,1800,12.0,n" for lat, lon in puntos)
    return f"latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence\n{filas}\n"


def _explore(web, client, puntos: list[tuple[float, float]]) -> dict:
    web.add(lambda r: "firms" in r.url.host, lambda r: httpx.Response(200, text=_csv(puntos)))
    r = client.get("/api/explore?zone=chile")
    assert r.status_code == 200, r.text
    return r.json()


# 1. Todo punto entregado cae dentro del territorio ----------------------------


def test_todos_los_puntos_caen_dentro_del_territorio_chileno(make_client, web):
    with make_client(FIRMS_MAP_KEY="k-123") as client:
        data = _explore(web, client, [(-33.06, -71.45), (-36.82, -73.05), (-35.43, -71.66)])
    puntos = data["points"]
    assert puntos
    t = territory()
    for p in puntos:
        assert t.locate(p["lat"], p["lon"], tolerance_deg=firms.COASTAL_TOLERANCE_DEG) is not None, p["id"]
    assert data["in_chile"] + data["outside_chile"] == len(puntos)
    assert data["in_chile"] == len(puntos) and data["outside_chile"] == 0


# 2. Un foco boliviano no llega a la respuesta ---------------------------------


def test_un_foco_boliviano_no_cuenta_ni_aparece_en_los_puntos(make_client, web):
    with make_client(FIRMS_MAP_KEY="k-123") as client:
        data = _explore(web, client, [*SEMILLAS_BOLIVIA, (-33.06, -71.45)])
    puntos = data["points"]
    assert puntos  # el foco chileno sí llega
    assert data["in_chile"] == len(puntos) and data["outside_chile"] == 0
    colados = [p["id"] for p in puntos if (round(p["lat"], 2), round(p["lon"], 2)) in SEMILLAS_BOLIVIA]
    assert colados == [], f"foco extranjero en la respuesta: {colados}"


# 3. Presupuesto de respuesta y campos internos --------------------------------


def test_la_respuesta_cabe_en_el_presupuesto_y_no_filtra_campos_internos(make_client, web):
    # Una detección por comuna en su centro real: la peor carga territorial posible.
    semillas = [(c.center[1], c.center[0]) for c in territory().comunas]
    with make_client(FIRMS_MAP_KEY="k-123") as client:
        data = _explore(web, client, semillas)
    assert len(json.dumps(data)) < 400_000
    for p in data["points"]:
        assert CAMPOS_INTERNOS.isdisjoint(p), p["id"]
