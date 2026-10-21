"""FUEGO-12: ni /api/incidents ni /api/opendata/incidents.geojson publican incidentes
fuera del territorio chileno.

Un incidente sin comuna chilena (`comuna_code` nulo) no es un incendio de Chile: queda en la
tabla — su purga es otra decisión — pero no sale por la API pública ni por los datos abiertos.
La excepción es el que tiene `official_ref`: un incendio informado por CONAF no desaparece
aunque su comuna no se haya podido emparejar.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend import incidents

STAMP = "%Y-%m-%dT%H:%M:%SZ"

TALCA = 7101


def ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(STAMP)


def seed_incident(
    db,
    ident: str,
    status: str = "posible",
    lat: float = -35.42,
    lon: float = -71.66,
    comuna_code: int | None = TALCA,
    official_ref: str | None = None,
    hours: int = 1,
) -> None:
    moment = ago(hours)
    db.execute(
        "INSERT OR REPLACE INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, fixed_source, "
        "official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ident,
            status,
            moment,
            moment,
            moment,
            lat,
            lon,
            lat - 0.01,
            lat + 0.01,
            lon - 0.01,
            lon + 0.01,
            3,
            2,
            "GOES19, VIIRS",
            42.5,
            comuna_code,
            0,
            official_ref,
            moment,
        ),
    )


def seed_cuatro_incidentes(db) -> None:
    """Talca (comuna válida), Tacna y Oruro (fuera de Chile) y uno de CONAF sin comuna emparejada."""
    seed_incident(db, "inc-talca", lat=-35.42, lon=-71.66, comuna_code=TALCA)
    seed_incident(db, "inc-tacna", status="anomalia", lat=-17.99, lon=-70.24, comuna_code=None)
    seed_incident(db, "inc-oruro", status="posible", lat=-17.97, lon=-67.11, comuna_code=None)
    seed_incident(db, "inc-conaf", status="confirmado", lat=-35.0, lon=-71.0, comuna_code=None, official_ref="conaf-2026-0001")


def test_api_incidents_solo_publica_territorio_chileno(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_cuatro_incidentes(db)
        body = client.get("/api/incidents").json()
        assert {i["id"] for i in body["incidents"]} == {"inc-talca", "inc-conaf"}
        assert body["count"] == len(body["incidents"]) == 2


def test_opendata_incidents_solo_publica_territorio_chileno(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_cuatro_incidentes(db)
        body = client.get("/api/opendata/incidents.geojson").json()
        assert {f["properties"]["id"] for f in body["features"]} == {"inc-talca", "inc-conaf"}
        assert body["count"] == len(body["features"]) == 2


def test_el_filtro_no_borra_filas(make_client):
    """Los puntos extranjeros siguen en la tabla: el filtro es de lectura, no una purga."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_cuatro_incidentes(db)
        client.get("/api/incidents")
        client.get("/api/opendata/incidents.geojson")
        assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 4


def test_extinguido_extranjero_tampoco_se_publica(make_client):
    """El síntoma medido en producción: un punto fuera de Chile cerrado como «extinguido»
    tampoco puede salir (San Juan, Argentina)."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_cuatro_incidentes(db)
        seed_incident(db, "inc-sanjuan", status="extinguido", lat=-31.99, lon=-68.29, comuna_code=None)
        body = client.get("/api/incidents").json()
        assert {i["id"] for i in body["incidents"]} == {"inc-talca", "inc-conaf"}
        assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 5


def test_geojson_mantiene_el_orden_lon_lat(make_client):
    """Las coordenadas salen como [lon, lat]: Talca queda al oeste de -71 y al sur de -35."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_cuatro_incidentes(db)
        features = {f["properties"]["id"]: f for f in client.get("/api/opendata/incidents.geojson").json()["features"]}
        assert features["inc-talca"]["geometry"]["coordinates"] == [-71.66, -35.42]


def test_expire_descarta_el_incendio_fuera_de_chile(make_client):
    """FUEGO-32: el incidente sin comuna chilena pasa a «descartado», no a «extinguido» —
    un fuego en Argentina no es un incendio chileno apagado. La fila queda para auditoría."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_cuatro_incidentes(db)
        n = incidents.expire(db)
        assert db.one("SELECT status FROM incidents WHERE id = 'inc-tacna'")["status"] == "descartado"
        assert db.one("SELECT status FROM incidents WHERE id = 'inc-oruro'")["status"] == "descartado"
        # El oficial de CONAF sin comuna emparejada no se toca, y el chileno reciente sigue abierto.
        assert db.one("SELECT status FROM incidents WHERE id = 'inc-conaf'")["status"] == "confirmado"
        assert db.one("SELECT status FROM incidents WHERE id = 'inc-talca'")["status"] == "posible"
        assert n == 2
        assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 4


def test_expire_reetiqueta_el_extinguido_extranjero_heredado(make_client):
    """Las filas que FUEGO-12 cerró como «extinguido» se corrigen solas en el próximo ciclo."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "inc-sanjuan", status="extinguido", lat=-31.99, lon=-68.29, comuna_code=None)
        incidents.expire(db)
        assert db.one("SELECT status FROM incidents WHERE id = 'inc-sanjuan'")["status"] == "descartado"


def test_expire_sigue_extinguiendo_al_incendio_chileno_sin_calor(make_client):
    """El cierre por 24 h sin detecciones no cambia: solo se separa lo fuera del territorio."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "inc-viejo", status="posible", comuna_code=TALCA, hours=30)
        incidents.expire(db)
        assert db.one("SELECT status FROM incidents WHERE id = 'inc-viejo'")["status"] == "extinguido"


def test_status_no_cuenta_descartados_como_abiertos(make_client):
    """El conteo de «incendios abiertos» excluye «extinguido» y «descartado»."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "inc-talca", status="posible", comuna_code=TALCA)
        seed_incident(db, "inc-oruro", status="descartado", lat=-17.97, lon=-67.11, comuna_code=None)
        body = client.get("/api/status").json()
        assert body["incidents_open"] == {"posible": 1}
