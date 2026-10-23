"""SCARS-01 — cicatrices de la temporada (`backend/scars.py`).

La cicatriz es la unión por comuna de las huellas de detecciones confiables de
cada incidente de la ventana: alimenta `/api/opendata/scars.geojson`, la capa
«cicatrices» del mapa y la base del aviso de aluvión post-incendio
(docs/ALUVIONES.md). Los incidentes y detecciones se siembran directo en una
base temporal; no dependen de `web/data/*.json` (el módulo solo usa
`comunas.geojson` para nombrar la comuna, como en producción).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.db import Database
from backend.scars import season_scars

NOW = datetime.now(timezone.utc)
TALCA = 7101  # centro (-71.6035, -35.4211): Maule, Chile continental
VINA = 5109  # Viña del Mar (-71.5237, -33.025)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_incident(
    db: Database,
    iid: str,
    comuna_code: int = TALCA,
    lat: float = -35.42,
    lon: float = -71.60,
    days_ago: float = 1,
    status: str = "posible",
    fixed_source: int = 0,
    pixels: list[tuple[float, float, str]] | None = None,
) -> None:
    """Un incidente con sus detecciones enlazadas.

    `pixels` son `(lat, lon, confidence)` absolutas; None siembra tres píxeles
    confiables junto al centro (un incidente real de tamaño mínimo).
    """
    seen = NOW - timedelta(days=days_ago)
    at = _stamp(seen)
    if pixels is None:
        pixels = [(lat, lon, "alta"), (lat + 0.002, lon, "alta"), (lat, lon + 0.002, "alta")]
    lats = [p[0] for p in pixels]
    lons = [p[1] for p in pixels]
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, "
        "lat, lon, min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, "
        "fixed_source, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            iid,
            status,
            at,
            _stamp(seen - timedelta(hours=2)),
            at,
            lat,
            lon,
            min(lats),
            max(lats),
            min(lons),
            max(lons),
            len(pixels),
            len(pixels),
            "VIIRS",
            comuna_code,
            fixed_source,
            at,
        ),
    )
    for j, (plat, plon, conf) in enumerate(pixels):
        oid = f"{iid}-o{j}"
        db.execute(
            "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, "
            "observed_at, frp_mw, confidence, comuna_code, ingested_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (oid, "gen", "VIIRS", "GEN", 375, plat, plon, at, 10.0, conf, comuna_code, at),
        )
        db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES (?,?)", (oid, iid))


def _coords(geometry: dict) -> list[tuple[float, float]]:
    """Todas las parejas [x, y] de una geometría GeoJSON, anidadas o no."""
    found = []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            found.append(tuple(c))
        else:
            for x in c:
                walk(x)

    walk(geometry["coordinates"])
    return found


def test_incidente_confiable_deja_huella_no_vacia(tmp_path):
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-1")
    scars = season_scars(db, 90)
    assert len(scars["features"]) == 1
    feat = scars["features"][0]
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert _coords(feat["geometry"])
    props = feat["properties"]
    assert props["comuna_code"] == TALCA and props["comuna"] == "Talca"
    assert props["n_incidentes"] == 1
    # Tres píxeles VIIRS son decenas de hectáreas, no metros ni miles de km²:
    # si el área viniera en m² o en km² este rango lo delata.
    assert 0 < props["ha"] < 1000
    assert props["desde"] < props["hasta"]


def test_dos_incidentes_de_la_misma_comuna_se_unen_en_una_cicatriz(tmp_path):
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-1", days_ago=5)
    seed_incident(db, "inc-2", lat=-35.50, lon=-71.50, days_ago=1)
    seed_incident(db, "inc-3", comuna_code=VINA, lat=-33.02, lon=-71.52, days_ago=2)
    scars = season_scars(db, 90)
    assert len(scars["features"]) == 2
    maule = next(f for f in scars["features"] if f["properties"]["comuna_code"] == TALCA)
    assert maule["properties"]["n_incidentes"] == 2
    # La ventana del grupo cubre del más viejo al más nuevo.
    assert maule["properties"]["desde"] < maule["properties"]["hasta"]


def test_descartados_y_fuentes_fijas_no_aportan_cicatriz(tmp_path):
    """Un volcán o una quema industrial (fixed_source) y lo ya descartado no son
    suelo quemado: no pueden gatillar un aviso de aluvión."""
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-desc", status="descartado")
    seed_incident(db, "inc-fijo", fixed_source=1, lat=-35.60, lon=-71.50)
    assert season_scars(db, 90)["features"] == []


def test_con_menos_del_limite_no_hay_recorte(tmp_path):
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-1")
    scars = season_scars(db, 90)
    assert scars["incidents_truncated"] is False
    assert scars["incidents_examined"] == 1


def test_la_ventana_days_incluye_y_excluye_por_fecha(tmp_path):
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-reciente", days_ago=5)
    seed_incident(db, "inc-viejo", days_ago=100, lat=-35.60, lon=-71.50)
    scars = season_scars(db, 90)
    assert scars["incidents_examined"] == 1
    assert season_scars(db, 120)["incidents_examined"] == 2


def test_la_geometria_sale_en_epsg4326_con_orden_lon_lat(tmp_path):
    """GeoJSON es [lon, lat]: una cicatriz del Maule cae en lon -74..-70 y
    lat -40..-30; si el orden saliera invertido este test lo nota."""
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-1")
    feat = season_scars(db, 90)["features"][0]
    for x, y in _coords(feat["geometry"]):
        assert -74 <= x <= -70, f"longitud fuera de Chile: {x}"
        assert -40 <= y <= -30, f"latitud fuera de Chile: {y}"


def test_miembro_con_coordenadas_invalidas_no_deforma_al_resto(tmp_path):
    """Una detección con lat/lon imposible (dato corrupto) no puede llevar la
    cicatriz fuera del mundo ni tumbar la de otra comuna sana."""
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-sano", comuna_code=VINA, lat=-33.02, lon=-71.52)
    seed_incident(db, "inc-corrupto", pixels=[(-35.42, -71.60, "alta"), (114.58, 200.0, "alta")])
    scars = season_scars(db, 90)
    assert len(scars["features"]) == 2
    for feat in scars["features"]:
        for x, y in _coords(feat["geometry"]):
            assert -180 <= x <= 180 and -90 <= y <= 90
    maule = next(f for f in scars["features"] if f["properties"]["comuna_code"] == TALCA)
    for x, y in _coords(maule["geometry"]):
        assert -74 <= x <= -70 and -40 <= y <= -30


def test_el_endpoint_sirve_geojson_con_el_descargo_de_perimetro(make_client):
    """`/api/opendata/scars.geojson` responde GeoJSON, une los incidentes de la
    comuna en un feature y declara que no es el perímetro oficial de CONAF."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "inc-a")
        seed_incident(db, "inc-b", lat=-35.50, lon=-71.50)
        r = client.get("/api/opendata/scars.geojson")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/geo+json")
        body = r.json()
        assert body["type"] == "FeatureCollection" and body["count"] == 1
        feat = body["features"][0]
        assert feat["properties"]["comuna_code"] == TALCA
        assert feat["properties"]["n_incidentes"] == 2
        assert "no es perímetro oficial" in body["source"]


def test_el_endpoint_valida_la_ventana_days(make_client):
    """`days` fuera de 1..180 responde 422: la guarda de parámetros sigue puesta."""
    with make_client() as client:
        assert client.get("/api/opendata/scars.geojson?days=0").status_code == 422
        assert client.get("/api/opendata/scars.geojson?days=181").status_code == 422


def test_sin_incidentes_el_endpoint_responde_coleccion_vacia(make_client):
    with make_client() as client:
        body = client.get("/api/opendata/scars.geojson").json()
        assert body["type"] == "FeatureCollection"
        assert body["count"] == 0 and body["features"] == []


# --- RISK-23: filtro por comuna en la consulta, para la ficha de una sola comuna ---


def test_el_filtro_por_comuna_solo_devuelve_esa_comuna(tmp_path):
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-1")
    seed_incident(db, "inc-2", comuna_code=VINA, lat=-33.02, lon=-71.52)
    scars = season_scars(db, 90, comuna_code=TALCA)
    assert len(scars["features"]) == 1
    assert scars["features"][0]["properties"]["comuna_code"] == TALCA


def test_sin_filtro_sigue_devolviendo_todas_las_comunas(tmp_path):
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-1")
    seed_incident(db, "inc-2", comuna_code=VINA, lat=-33.02, lon=-71.52)
    assert len(season_scars(db, 90, comuna_code=None)["features"]) == 2
    assert len(season_scars(db, 90)["features"]) == 2
