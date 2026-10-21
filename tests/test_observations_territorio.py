"""La capa «Focos de calor» solo muestra detecciones en territorio chileno.

`/api/incidents` ya publica solo incidentes con comuna chilena y los datos abiertos
hacen lo mismo, pero `/api/observations` —lo que pinta el mapa— devolvía todo el
rectángulo de lectura del satélite: cientos de puntos de Argentina, Bolivia y Perú
medidos en producción. Se conserva lo que `locate` ubica en una comuna (tolerancia
0.02°, islas incluidas) o lo que pertenece a un incidente con comuna chilena; el
resto se descarta y se cuenta en `outside_chile`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

STAMP = "%Y-%m-%dT%H:%M:%SZ"

TALCA = (-35.43, -71.65)  # (a) dentro del polígono de la comuna 7101
SAN_JUAN = (-31.99, -68.27)  # (b) Argentina: fuera de toda comuna
MAR_ABIERTO = (-35.43, -72.60)  # (c) Pacífico, ~10 km de toda comuna: locate → None
RAPA_NUI = (-27.12, -109.35)  # (d) Isla de Pascua (5201): insular también es Chile


def _momento() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime(STAMP)


def _insertar(db, oid: str, lat: float, lon: float, comuna_code: int | None = None) -> None:
    """Detección tal como queda guardada; `comuna_code` nulo reproduce las filas ya
    almacenadas que la ingesta no recortó o que cayeron en huecos del trazado."""
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (oid, "VIIRS_NOAA20_NRT", "I4", "NOAA-20", 375, lat, lon, _momento(), 12.0, "nominal", comuna_code, _momento()),
    )


def _incidente(db, iid: str, comuna_code: int | None) -> None:
    stamp = _momento()
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, comuna_code, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (iid, "posible", stamp, stamp, stamp, *TALCA, TALCA[0], TALCA[0], TALCA[1], TALCA[1], 1, comuna_code, stamp),
    )


def test_solo_territorio_chileno_sale_por_la_api(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _insertar(db, "talca", *TALCA, comuna_code=7101)  # (a) con comuna
        _insertar(db, "san-juan", *SAN_JUAN)  # (b) Argentina, sin comuna ni incidente
        # (c) sin comuna propia, pero su incidente ya rescató la comuna chilena:
        # descartarlo recortaría el borde de un incendio real.
        _insertar(db, "orilla", *MAR_ABIERTO)
        _incidente(db, "abc123def456", comuna_code=7101)
        db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES ('orilla', 'abc123def456')")
        _insertar(db, "rapa-nui", *RAPA_NUI)  # (d) insular: locate la ubica en Isla de Pascua
        body = client.get("/api/observations").json()

    ids = {p["id"] for p in body["points"]}
    assert ids == {"talca", "orilla", "rapa-nui"}
    assert body["count"] == len(body["points"]) == 3
    assert body["outside_chile"] == 1
    assert "territorio" in body["explanation"]


def test_contrato_del_filtro(make_client):
    """Lo que el filtro garantiza a la interfaz: nada devuelto cae fuera de Chile,
    lat/lon sin invertir, marcas en UTC («Z», no un offset fijo de Chile) y la
    frescura de la base viaja en `data_as_of`."""
    corte = _momento()
    with make_client() as client:
        db = client.app.state.services.db
        db.kv_set("last_ingest_at", corte)
        _insertar(db, "dentro", *TALCA, comuna_code=7101)
        _insertar(db, "fuera", *SAN_JUAN)
        body = client.get("/api/observations").json()

    [punto] = body["points"]
    assert (punto["lat"], punto["lon"]) == TALCA  # lat primero, lon después
    assert punto["observed_at"].endswith("Z") and punto["comuna"] == "Talca"
    assert body["outside_chile"] == 1 and body["truncated"] is False
    assert body["data_as_of"] == corte
