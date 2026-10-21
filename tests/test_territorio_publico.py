"""TERR-01: barrido territorial de todas las respuestas públicas con coordenadas.

La promesa del producto —focos e incendios que corresponden a Chile real— hoy se vigila
endpoint por endpoint. Esta prueba siembra a mano focos, un incidente, un incendio
oficial, rayos GLM y humo ADPF en coordenadas reales de Argentina, Bolivia y Perú (más
un punto chileno de control en Talca) y recorre cada respuesta pública que devuelve
coordenadas: ninguna feature puede caer fuera de `territory()` con el margen más
amplio que el sistema usa (`firms.COASTAL_TOLERANCE_DEG`).

El barrido ya muerde: al escribirlo, cinco respuestas publicaban el punto de Mendoza.
`/api/official-fires` ya filtra (OPS-45); los cuatro casos restantes quedan `xfail`
nombrando el arreglo para que el marcador se quite cuando aterrice. `risk.geojson` y
`boton-rojo.json` no se barren: emiten centroides de comunas válidas y no pueden salir
del territorio.
"""

from __future__ import annotations

import io
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
from tests.test_smoke import key_for as adp_key_for, synthetic_adp

ARGENTINA = ("Mendoza, Argentina", -31.35, -69.42)
BOLIVIA = ("Oruro, Bolivia", -17.05, -66.06)
PERU = ("Matarani, Perú", -17.25, -71.19)
FUERA = [ARGENTINA, BOLIVIA, PERU]
TALCA = ("Talca, Chile", -35.43, -71.66)

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Respuestas donde el barrido encontró una fuga real al escribirse. Cada entrada dice
# por qué sigue abierta; el `xfail` correspondiente se borra cuando el arreglo aterrice.
PENDIENTES = {
    "/api/observations": "fuga real: el filtro llega con el PR #504 (abierto)",
    "/api/opendata/observations.geojson": "fuga real: el filtro llega con el PR #485 (abierto)",
    "/api/opendata/lightning.geojson": "fuga real: el recorte GLM llega con el PR #479 (abierto)",
    "/api/opendata/smoke.geojson": "fuga real: parse_adp solo recorta por caja (el PR #473 no lo toca)",
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


def _seed(db, comuna_talca: int) -> None:
    """Siembra filas con marcas recientes: lo extranjero no debe salir por ninguna puerta."""
    for nombre, lat, lon in FUERA:
        db.execute(
            "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
            "frp_mw, confidence, comuna_code, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"obs-fuera-{lat}", "VIIRS_NOAA21_NRT", "VIIRS", "NOAA-21", 375, lat, lon, NOW, 20.0, "alta", None, NOW),
        )
        db.execute(
            "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
            "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, "
            "fixed_source, official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"inc-fuera-{lat}",
                "anomalia",
                NOW,
                NOW,
                NOW,
                lat,
                lon,
                lat - 0.05,
                lat + 0.05,
                lon - 0.05,
                lon + 0.05,
                1,
                1,
                "VIIRS",
                20.0,
                None,
                0,
                None,
                NOW,
            ),
        )
        db.execute(
            "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, "
            "area_ha, fetched_at, first_fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"fire-fuera-{lat}", f"FUEGO {nombre.upper()}", "confirmado", "En combate", NOW, lat, lon, nombre, nombre, 10.0, NOW, NOW),
        )
    # Control chileno: tres detecciones confiables en Talca alimentan observaciones,
    # un incidente con comuna y la cicatriz de su comuna.
    for i in range(3):
        db.execute(
            "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
            "frp_mw, confidence, comuna_code, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"obs-talca-{i}",
                "VIIRS_NOAA21_NRT",
                "VIIRS",
                "NOAA-21",
                375,
                TALCA[1] + i * 0.01,
                TALCA[2] + i * 0.01,
                NOW,
                20.0,
                "alta",
                comuna_talca,
                NOW,
            ),
        )
        db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES (?,?)", (f"obs-talca-{i}", "inc-talca"))
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, "
        "fixed_source, official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "inc-talca",
            "anomalia",
            NOW,
            NOW,
            NOW,
            TALCA[1],
            TALCA[2],
            TALCA[1] - 0.05,
            TALCA[1] + 0.05,
            TALCA[2] - 0.05,
            TALCA[2] + 0.05,
            3,
            3,
            "VIIRS",
            20.0,
            comuna_talca,
            0,
            None,
            NOW,
        ),
    )
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, "
        "area_ha, fetched_at, first_fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("fire-talca", "EL BARRIDO", "confirmado", "En combate", NOW, TALCA[1], TALCA[2], "Talca", "Maule", 10.0, NOW, NOW),
    )


def test_el_barrido_cubre_al_menos_siete_respuestas():
    """La lista vive en el propio test: un endpoint nuevo con coordenadas se agrega aquí."""
    assert len(ENDPOINTS) >= 7


@pytest.mark.parametrize("url, extraer", ENDPOINTS)
def test_ninguna_respuesta_publica_saca_puntos_fuera_de_chile(client_con_fuentes, url, extraer):
    """Ninguna feature de la respuesta cae fuera del territorio ni con el margen costero."""
    comuna_talca = territory().locate(*TALCA[1:]).code
    _seed(client_con_fuentes.app.state.services.db, comuna_talca)
    if url.split("?")[0] in PENDIENTES:
        pytest.xfail(PENDIENTES[url.split("?")[0]])
    response = client_con_fuentes.get(url)
    assert response.status_code == 200
    t = territory()
    for lat, lon in extraer(response.json()):
        assert t.locate(lat, lon, tolerance_deg=firms.COASTAL_TOLERANCE_DEG) is not None, (
            f"{url} devolvió ({lat}, {lon}), fuera del territorio chileno"
        )


def test_incendios_oficiales_fuera_de_chile_se_ocultan_sin_borrarse(client_con_fuentes):
    """OPS-45: el filtro es de lectura; las filas extranjeras siguen en la base."""
    db = client_con_fuentes.app.state.services.db
    _seed(db, territory().locate(*TALCA[1:]).code)
    body = client_con_fuentes.get("/api/official-fires").json()
    assert {f["id"] for f in body["fires"]} == {"fire-talca"}
    assert db.one("SELECT COUNT(*) AS n FROM official_fires WHERE id LIKE 'fire-fuera-%'")["n"] == len(FUERA)


@pytest.mark.parametrize("url, extraer", ENDPOINTS)
def test_el_control_chileno_si_aparece(client_con_fuentes, url, extraer):
    """El punto de Talca sí sale en cada respuesta: el barrido no pasa por vacío."""
    comuna_talca = territory().locate(*TALCA[1:]).code
    _seed(client_con_fuentes.app.state.services.db, comuna_talca)
    response = client_con_fuentes.get(url)
    assert response.status_code == 200
    puntos = extraer(response.json())
    assert any(abs(lat - TALCA[1]) < 0.3 and abs(lon - TALCA[2]) < 0.3 for lat, lon in puntos), (
        f"{url} no devolvió el punto chileno de control cerca de {TALCA[0]}"
    )
