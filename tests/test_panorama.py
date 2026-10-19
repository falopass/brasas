"""Panorama de la temporada (TEMP-01): agregados de `official_fires` y `boton_rojo`."""


def _fire(db, fid, status, raw, region, area, season="2026-2027"):
    db.execute("INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, area_ha, season, "
               "first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (fid, fid, status, raw, "2027-01-20T18:30:00Z", -33.0, -71.6, "Quilpué", region, area, season,
                "2027-01-21T00:00:00Z", "2027-01-21T00:00:00Z"))


def _br(db, code, date, hours=3):
    db.execute("INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
               (code, date, hours, 100.0, 0.5, "2027-01-10T00:00:00Z"))


def _seed(db):
    """Temporada 2026-2027: 2 en combate y 1 controlado en Valparaíso, 1 extinguido en Maule,
    1 extinguido sin región y 1 sin superficie. Un incendio de otra temporada no debe contarse."""
    _fire(db, "f1", "confirmado", "En combate", "Valparaíso", 10.5)
    _fire(db, "f2", "confirmado", "Bajo observación", "Valparaíso", 100.0)
    _fire(db, "f3", "controlado", "Controlado", "Valparaíso", 50.0)
    _fire(db, "f4", "extinguido", "Extinguido", "Maule", 200.0)
    _fire(db, "f5", "extinguido", "Extinguido", None, 5.0)
    _fire(db, "f6", "confirmado", "En combate", "Valparaíso", None)
    _fire(db, "viejo", "extinguido", "Extinguido", "Maule", 999.0, season="2025-2026")


def test_panorama_aggregates_by_region_and_status(make_client):
    with make_client(GOES_ENABLED="0") as client:
        _seed(client.app.state.services.db)
        body = client.get("/api/panorama?season=2026-2027").json()
        assert body["season"] == "2026-2027" and body["source"]["name"]
        assert body["totals"] == {"n": 6, "ha": 365.5, "en_combate": 3, "controlados": 1, "extinguidos": 2}
        assert body["by_region"] == [
            {"region": "Maule", "n": 1, "ha": 200.0, "en_combate": 0},
            {"region": "Valparaíso", "n": 4, "ha": 160.5, "en_combate": 3},
            {"region": None, "n": 1, "ha": 5.0, "en_combate": 0},
        ]


def test_panorama_defaults_to_the_latest_season(make_client):
    with make_client(GOES_ENABLED="0") as client:
        _seed(client.app.state.services.db)
        body = client.get("/api/panorama").json()
        assert body["season"] == "2026-2027" and body["totals"]["n"] == 6


def test_panorama_counts_boton_rojo_days_inside_the_season(make_client):
    """La temporada 2026-2027 corre de jul-2026 a jun-2027: solo cuentan los días dentro."""
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _seed(db)
        _br(db, 5109, "2027-01-20")
        _br(db, 5109, "2027-01-21")
        _br(db, 13101, "2027-01-21")   # mismo día, otra comuna: sigue siendo un día
        _br(db, 5109, "2026-05-10")    # antes de la temporada: no cuenta
        body = client.get("/api/panorama?season=2026-2027").json()
        assert body["boton_rojo_days"] == 2


def test_panorama_empty_season_returns_zeros_and_source(make_client):
    with make_client(GOES_ENABLED="0") as client:
        _seed(client.app.state.services.db)
        response = client.get("/api/panorama?season=2030-2031")
        assert response.status_code == 200
        body = response.json()
        assert body["season"] == "2030-2031" and body["by_region"] == []
        assert body["totals"] == {"n": 0, "ha": 0.0, "en_combate": 0, "controlados": 0, "extinguidos": 0}
        assert body["boton_rojo_days"] == 0 and body["source"]["name"] and body["not_official"]


def test_panorama_without_fires_returns_zeros(make_client):
    """Sin ninguna fila (base demo, primera temporada) responde ceros, no un error."""
    with make_client(GOES_ENABLED="0") as client:
        body = client.get("/api/panorama").json()
        assert body["season"] is None and body["totals"]["n"] == 0 and body["source"]["name"]


def test_panorama_invalid_season_returns_422(make_client):
    with make_client(GOES_ENABLED="0") as client:
        assert client.get("/api/panorama?season=2027").status_code == 422
        assert client.get("/api/panorama?season=hola-mundo").status_code == 422
