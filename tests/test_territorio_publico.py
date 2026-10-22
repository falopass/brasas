"""TERR-01: barrido territorial de todas las respuestas públicas con coordenadas.

La promesa del producto —focos e incendios que corresponden a Chile real— hoy se vigila
endpoint por endpoint. Esta prueba siembra a mano focos, un incidente, un incendio
oficial, rayos GLM y humo ADPF en coordenadas reales de Argentina, Bolivia y Perú (más
un punto chileno de control en Talca) y recorre cada respuesta pública que devuelve
coordenadas: ninguna feature puede caer fuera de `territory()` con el margen más
amplio que el sistema usa (`firms.COASTAL_TOLERANCE_DEG`).

El barrido ya muerde: al escribirlo, cinco respuestas publicaban el punto de Mendoza.
Cuatro ya filtran (`/api/observations`, `/api/opendata/observations.geojson` y
`/api/opendata/lightning.geojson` con #504, #485 y #479; `/api/official-fires` con
OPS-45) y su entrada se borró de `PENDIENTES`; la que sigue abierta queda `xfail` con
la causa verificada en el código, no con un número de PR. `risk.geojson` y
`boton-rojo.json` no se barren: emiten centroides de comunas válidas y no pueden salir
del territorio.

Regla de mantenimiento (QA-122): el mismo PR que cierra una fuga borra su entrada de
`PENDIENTES` y el `xfail` que la cubría. No se deja para después: una nota que
sobrevive a su arreglo miente y el barrido sigue verde sin proteger nada.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone

import h5py
import httpx
import numpy as np
import pytest
from shapely.geometry import shape

from backend.geo import territory
from backend.providers import firms
from backend.routes import opendata
from tests.test_glm import key_for as glm_key_for
from tests.test_incidents_territorio_api import seed_incident
from tests.test_smoke import key_for as adp_key_for, synthetic_adp

ARGENTINA = ("Mendoza, Argentina", -31.35, -69.42)
BOLIVIA = ("Oruro, Bolivia", -17.05, -66.06)
PERU = ("Matarani, Perú", -17.25, -71.19)
FUERA = [ARGENTINA, BOLIVIA, PERU]
TALCA = ("Talca, Chile", -35.43, -71.66)

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Respuestas donde el barrido encontró una fuga real y que hoy siguen publicando el punto
# de Mendoza. Cada nota dice la causa verificada en el código (no un PR) y el ítem que la
# persigue; el mismo PR que cierre la fuga borra su entrada, sin dejarla para después.
PENDIENTES = {
    "/api/opendata/smoke.geojson": (
        "fuga real: `parse_adp` solo recorta por caja y `smoke.polygons` dibuja la mancha entera; DET-21 (en curso) "
        "recorta las celdas al territorio chileno. Falta que la ruta deje de publicar el humo de Mendoza."
    ),
}


def _geojson(body: dict) -> list[tuple[float, float]]:
    """(lat, lon) representativo de cada feature: el punto o el centroide del polígono."""
    out = []
    for feature in body["features"]:
        geom = feature["geometry"]
        if geom["type"] == "Point":
            lon, lat = geom["coordinates"][:2]
        else:
            centroide = shape(geom).centroid
            lon, lat = centroide.x, centroide.y
        out.append((lat, lon))
    return out


# Cada respuesta pública con coordenadas y cómo extraer sus (lat, lon).
ENDPOINTS = [
    pytest.param("/api/observations", lambda b: [(p["lat"], p["lon"]) for p in b["points"]], id="observations"),
    pytest.param("/api/incidents", lambda b: [(i["lat"], i["lon"]) for i in b["incidents"]], id="incidents"),
    pytest.param("/api/official-fires", lambda b: [(f["lat"], f["lon"]) for f in b["fires"]], id="official-fires"),
    pytest.param("/api/explore?zone=chile&days=3", lambda b: [(p["lat"], p["lon"]) for p in b["points"]], id="explore"),
    pytest.param("/api/opendata/incidents.geojson", _geojson, id="opendata-incidents"),
    pytest.param("/api/opendata/observations.geojson", _geojson, id="opendata-observations"),
    pytest.param("/api/opendata/lightning.geojson", _geojson, id="opendata-lightning"),
    pytest.param("/api/opendata/smoke.geojson", _geojson, id="opendata-smoke"),
    pytest.param("/api/opendata/scars.geojson", _geojson, id="opendata-scars"),
]


def _listing(*keys: str) -> httpx.Response:
    body = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    return httpx.Response(200, text=f"<ListBucketResult>{body}</ListBucketResult>")


def _lcfa(points: list[tuple[float, float]]) -> bytes:
    """LCFA mínimo como el de `tests/data/build_glm_sample.py`, con destellos nominales."""
    scale = 0.005
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        f.attrs["time_coverage_start"] = np.bytes_(b"2026-10-21T03:00:00.0Z")
        lat = f.create_dataset("flash_lat", data=np.array([p[0] / scale for p in points], "int16"))
        lat.attrs["scale_factor"] = np.array([scale], "float32")
        lon = f.create_dataset("flash_lon", data=np.array([p[1] / scale for p in points], "int16"))
        lon.attrs["scale_factor"] = np.array([scale], "float32")
        off = f.create_dataset("flash_time_offset_of_first_event", data=np.full(len(points), 120, "int16"))
        off.attrs["scale_factor"] = np.array([0.1], "float32")
        f.create_dataset("flash_quality_flag", data=np.zeros(len(points), "int16"))
        f.create_dataset("flash_energy", data=np.full(len(points), 100.0, "float32"))
        area = f.create_dataset("flash_area", data=np.full(len(points), 100, "int16"))
        area.attrs["scale_factor"] = np.array([0.1], "float32")
    return buf.getvalue()


@pytest.fixture
def client_con_fuentes(make_client, web, monkeypatch):
    """Cliente con la base sembrada y S3/FIRMS simulados sirviendo puntos de ambos lados."""
    monkeypatch.setattr(opendata, "_LIGHTNING_CACHE", {})
    monkeypatch.setattr(opendata, "_SMOKE_CACHE", {})
    now = datetime.now(timezone.utc)
    glm_key = glm_key_for(now)
    adp_key = adp_key_for(now)
    web.add(
        lambda r: "list-type" in r.url.params and r.url.params.get("prefix", "").startswith("GLM"),
        lambda r: _listing(glm_key),
    )
    web.add(
        lambda r: "list-type" in r.url.params and r.url.params.get("prefix", "").startswith("ABI"),
        lambda r: _listing(adp_key),
    )
    web.add(
        lambda r: r.url.path.endswith(".nc") and "GLM" in r.url.path,
        lambda r: httpx.Response(200, content=_lcfa([(lat, lon) for _, lat, lon in FUERA + [TALCA]])),
    )
    # La grilla sintética del ADPF cubre solo el centro de Chile: Mendoza y Talca entran;
    # Bolivia y Perú ya quedan fuera de la ventana de lectura del satélite, como en la real.
    web.add(
        lambda r: r.url.path.endswith(".nc") and "ADPF" in r.url.path,
        lambda r: httpx.Response(200, content=synthetic_adp([(ARGENTINA[1], ARGENTINA[2], 0, True), (TALCA[1], TALCA[2], 0, True)])),
    )
    today = now.date().isoformat()
    csv = "latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence,daynight\n" + "".join(
        f"{lat},{lon},330.0,{today},0140,10.0,n,N\n" for _, lat, lon in FUERA + [TALCA]
    )
    web.add(lambda r: "/api/area/" in r.url.path, lambda r: httpx.Response(200, text=csv))
    with make_client(FIRMS_MAP_KEY="clave-de-prueba") as client:
        yield client


def _observation(db, ident: str, lat: float, lon: float, comuna: int | None) -> None:
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (ident, "VIIRS_NOAA21_NRT", "VIIRS", "NOAA-21", 375, lat, lon, NOW, 20.0, "alta", comuna, NOW),
    )


def _official_fire(db, ident: str, name: str, lat: float, lon: float, comuna: str, region: str) -> None:
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, "
        "area_ha, fetched_at, first_fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (ident, name, "confirmado", "En combate", NOW, lat, lon, comuna, region, 10.0, NOW, NOW),
    )


def _seed(db, comuna_talca: int) -> None:
    """Siembra filas con marcas recientes: lo extranjero no debe salir por ninguna puerta."""
    for nombre, lat, lon in FUERA:
        _observation(db, f"obs-fuera-{lat}", lat, lon, None)
        seed_incident(db, f"inc-fuera-{lat}", status="anomalia", lat=lat, lon=lon, comuna_code=None)
        _official_fire(db, f"fire-fuera-{lat}", f"FUEGO {nombre.upper()}", lat, lon, nombre, nombre)
    # Control chileno: tres detecciones confiables en Talca alimentan observaciones,
    # un incidente con comuna y la cicatriz de su comuna.
    for i in range(3):
        _observation(db, f"obs-talca-{i}", TALCA[1] + i * 0.01, TALCA[2] + i * 0.01, comuna_talca)
        db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES (?,?)", (f"obs-talca-{i}", "inc-talca"))
    seed_incident(db, "inc-talca", status="anomalia", lat=TALCA[1], lon=TALCA[2], comuna_code=comuna_talca)
    _official_fire(db, "fire-talca", "EL BARRIDO", TALCA[1], TALCA[2], "Talca", "Maule")


def test_cada_pendiente_declara_su_causa():
    """QA-122: una entrada huérfana no protege nada y una nota sin causa ni ítem miente."""
    rutas = {param.values[0].split("?")[0] for param in ENDPOINTS}
    for url, nota in PENDIENTES.items():
        assert url in rutas, f"{url} está en PENDIENTES pero el barrido no lo recorre: una entrada huérfana no protege nada"
        assert len(nota.split()) >= 12, f"la nota de {url} no explica la causa ({len(nota.split())} palabras): {nota!r}"
        assert re.search(r"[A-Z]+-\d+|#\d+", nota), f"la nota de {url} no nombra el ítem que persigue la fuga: {nota!r}"


@pytest.mark.parametrize("url, extraer", ENDPOINTS)
def test_cada_respuesta_solo_publica_puntos_chilenos_y_el_control(client_con_fuentes, url, extraer):
    """Ninguna feature cae fuera del territorio ni con el margen costero, y Talca sí aparece."""
    comuna_talca = territory().locate(*TALCA[1:]).code
    _seed(client_con_fuentes.app.state.services.db, comuna_talca)
    if url.split("?")[0] in PENDIENTES:
        pytest.xfail(PENDIENTES[url.split("?")[0]])
    response = client_con_fuentes.get(url)
    assert response.status_code == 200
    t = territory()
    puntos = extraer(response.json())
    for lat, lon in puntos:
        assert t.locate(lat, lon, tolerance_deg=firms.COASTAL_TOLERANCE_DEG) is not None, (
            f"{url} devolvió ({lat}, {lon}), fuera del territorio chileno"
        )
    assert any(abs(lat - TALCA[1]) < 0.3 and abs(lon - TALCA[2]) < 0.3 for lat, lon in puntos), (
        f"{url} no devolvió el punto chileno de control cerca de {TALCA[0]}"
    )


def test_incendios_oficiales_fuera_de_chile_se_ocultan_sin_borrarse(client_con_fuentes):
    """OPS-45: el filtro es de lectura; las filas extranjeras siguen en la base."""
    db = client_con_fuentes.app.state.services.db
    _seed(db, territory().locate(*TALCA[1:]).code)
    body = client_con_fuentes.get("/api/official-fires").json()
    assert {f["id"] for f in body["fires"]} == {"fire-talca"}
    assert db.one("SELECT COUNT(*) AS n FROM official_fires WHERE id LIKE 'fire-fuera-%'")["n"] == len(FUERA)
