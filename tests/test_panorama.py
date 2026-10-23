"""Panorama de la temporada (TEMP-01/02): agregados de `official_fires` y `boton_rojo`.

TEMP-31 suma el bloque `semana`: los últimos 7 días calendario de Chile contra los 7
previos, con la fecha de detección de CONAF (`started_at`) y días sin filas en cero.
"""

from datetime import datetime, time, timedelta, timezone

from backend.routes.panorama import CHILE_TZ
from tests.test_api_sin_datos_personales import _forbidden_keys


def _fire(db, fid, status, raw, region, area, season="2026-2027", comuna="Quilpué", started_at="2027-01-20T18:30:00Z"):
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, area_ha, season, "
        "first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            fid,
            fid,
            status,
            raw,
            started_at,
            -33.0,
            -71.6,
            comuna,
            region,
            area,
            season,
            "2027-01-21T00:00:00Z",
            "2027-01-21T00:00:00Z",
        ),
    )


def _chile_iso(day, hour=12):
    """Instante UTC que en Chile cae en `day` a la hora local pedida."""
    return datetime.combine(day, time(hour), tzinfo=CHILE_TZ).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _br(db, code, date, hours=3):
    db.execute(
        "INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
        (code, date, hours, 100.0, 0.5, "2027-01-10T00:00:00Z"),
    )


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


def test_panorama_by_comuna_ranks_by_area_and_links_known_comunas(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _seed(db)
        _fire(db, "otra", "confirmado", "En combate", "Maule", 400.0, comuna="Curicó")
        _fire(db, "sinco", "extinguido", "Extinguido", "Maule", 1.0, comuna=None)
        body = client.get("/api/panorama?season=2026-2027").json()
        assert body["by_comuna"] == [
            {"comuna": "Curicó", "region": "Maule", "comuna_code": 7301, "n": 1, "ha": 400.0, "en_combate": 1},
            {"comuna": "Quilpué", "region": "Maule", "comuna_code": 5801, "n": 1, "ha": 200.0, "en_combate": 0},
            {"comuna": "Quilpué", "region": "Valparaíso", "comuna_code": 5801, "n": 4, "ha": 160.5, "en_combate": 3},
            {"comuna": "Quilpué", "region": None, "comuna_code": 5801, "n": 1, "ha": 5.0, "en_combate": 0},
            {"comuna": None, "region": "Maule", "comuna_code": None, "n": 1, "ha": 1.0, "en_combate": 0},
        ]


def test_panorama_reports_status_raw_fuera_del_mapa(make_client):
    """DAT-02: un estado de CONAF que BRASA no interpreta se cuenta en `unknown_status`
    con el texto tal cual vino, sin cambiar los totales (sigue contando según su `status`)."""
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _fire(db, "f1", "confirmado", "En combate", "Valparaíso", 10.0)
        _fire(db, "f2", "extinguido", "Extinguido", "Maule", 20.0)
        _fire(db, "f3", "confirmado", "extinguido con resguardo", "Maule", 30.0)
        body = client.get("/api/panorama?season=2026-2027").json()
        assert body["unknown_status"] == {"n": 1, "values": [{"raw": "extinguido con resguardo", "n": 1}]}
        assert body["totals"] == {"n": 3, "ha": 60.0, "en_combate": 2, "controlados": 0, "extinguidos": 1}


def test_panorama_unknown_status_sin_estados_raros_devuelve_vacio(make_client):
    """DAT-02: el campo siempre existe; con solo estados conocidos queda en cero."""
    with make_client(GOES_ENABLED="0") as client:
        _seed(client.app.state.services.db)
        body = client.get("/api/panorama?season=2026-2027").json()
        assert body["unknown_status"] == {"n": 0, "values": []}


def test_panorama_seasons_lists_present_seasons_desc(make_client):
    with make_client(GOES_ENABLED="0") as client:
        _seed(client.app.state.services.db)
        body = client.get("/api/panorama?season=2025-2026").json()
        assert body["seasons"] == ["2026-2027", "2025-2026"]


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
        _br(db, 13101, "2027-01-21")  # mismo día, otra comuna: sigue siendo un día
        _br(db, 5109, "2026-05-10")  # antes de la temporada: no cuenta
        body = client.get("/api/panorama?season=2026-2027").json()
        assert body["boton_rojo_days"] == 2


def test_panorama_empty_season_returns_zeros_and_source(make_client):
    with make_client(GOES_ENABLED="0") as client:
        _seed(client.app.state.services.db)
        response = client.get("/api/panorama?season=2030-2031")
        assert response.status_code == 200
        body = response.json()
        assert body["season"] == "2030-2031" and body["by_region"] == [] and body["by_comuna"] == []
        assert body["seasons"] == ["2026-2027", "2025-2026"]
        assert body["totals"] == {"n": 0, "ha": 0.0, "en_combate": 0, "controlados": 0, "extinguidos": 0}
        assert body["boton_rojo_days"] == 0 and body["source"]["name"] and body["not_official"]
        assert body["by_comuna_total"] == 0 and body["by_comuna_truncated"] is False and body["updated_at"] is None


def test_panorama_without_fires_returns_zeros(make_client):
    """Sin ninguna fila (base demo, primera temporada) responde ceros, no un error."""
    with make_client(GOES_ENABLED="0") as client:
        body = client.get("/api/panorama").json()
        assert body["season"] is None and body["totals"]["n"] == 0 and body["source"]["name"]


def test_panorama_invalid_season_returns_422(make_client):
    with make_client(GOES_ENABLED="0") as client:
        assert client.get("/api/panorama?season=2027").status_code == 422
        assert client.get("/api/panorama?season=hola-mundo").status_code == 422


def test_panorama_by_comuna_reports_total_and_truncation(make_client):
    """DAT-07: el ranking se corta en 12, pero la respuesta dice cuántas comunas quedaron fuera."""
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        for i in range(15):
            _fire(db, f"t{i}", "extinguido", "Extinguido", "Valparaíso", float(i + 1), comuna=f"Comuna {i:02d}")
        body = client.get("/api/panorama?season=2026-2027").json()
        assert len(body["by_comuna"]) == 12
        assert body["by_comuna_total"] == 15
        assert body["by_comuna_truncated"] is True
        for campo in ("totals", "by_region", "boton_rojo_days", "source"):
            assert campo in body


def test_panorama_updated_at_es_de_la_temporada_pedida(make_client):
    """La fecha de actualización no debe ser la ingesta de hoy si se pide una temporada vieja."""
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _fire(db, "viejo", "extinguido", "Extinguido", "Maule", 10.0, season="2025-2026")
        _fire(db, "nuevo", "extinguido", "Extinguido", "Maule", 20.0, season="2026-2027")
        db.execute("UPDATE official_fires SET fetched_at = ? WHERE id = ?", ("2026-03-01T00:00:00Z", "viejo"))
        db.execute("UPDATE official_fires SET fetched_at = ? WHERE id = ?", ("2027-02-01T00:00:00Z", "nuevo"))
        body = client.get("/api/panorama?season=2025-2026").json()
        assert body["updated_at"] == "2026-03-01T00:00:00Z"


def test_panorama_semana_cuenta_los_ultimos_siete_dias_de_chile(make_client):
    """TEMP-31: la semana es hoy y los seis días anteriores; el día 7 y 13 caen en la anterior."""
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        hoy = datetime.now(CHILE_TZ).date()
        for i, days_ago in enumerate((0, 3, 6)):
            _fire(db, f"sem-{i}", "confirmado", "En combate", "Maule", 10.0, started_at=_chile_iso(hoy - timedelta(days=days_ago)))
        _fire(db, "prev-1", "extinguido", "Extinguido", "Maule", 1.0, started_at=_chile_iso(hoy - timedelta(days=7)))
        _fire(db, "prev-7", "extinguido", "Extinguido", "Maule", 1.0, started_at=_chile_iso(hoy - timedelta(days=13)))
        _fire(db, "fuera", "extinguido", "Extinguido", "Maule", 1.0, started_at=_chile_iso(hoy - timedelta(days=14)))
        semana = client.get("/api/panorama?season=2026-2027").json()["semana"]
        assert (semana["desde"], semana["hasta"]) == ((hoy - timedelta(days=6)).isoformat(), hoy.isoformat())
        assert (semana["incendios"], semana["ha"]) == (3, 30.0)
        assert (semana["anterior"]["incendios"], semana["anterior"]["ha"]) == (2, 2.0)
        assert semana["anterior"]["hasta"] == (hoy - timedelta(days=7)).isoformat()


def test_panorama_semana_usa_el_dia_calendario_de_chile(make_client):
    """TEMP-31: un incendio de las 23:30 de Chile cae al día siguiente en UTC y aun así cuenta hoy."""
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        hoy = datetime.now(CHILE_TZ).date()
        _fire(db, "tarde", "confirmado", "En combate", "Maule", 2.0, started_at=_chile_iso(hoy, hour=23))
        semana = client.get("/api/panorama?season=2026-2027").json()["semana"]
        assert semana["incendios"] == 1 and semana["ha"] == 2.0
        assert semana["dias_con_datos"] == 1


def test_panorama_semana_declara_los_dias_con_datos(make_client):
    """TEMP-31: los días sin incendios informados cuentan cero y `dias_con_datos` dice cuántos traen filas."""
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        hoy = datetime.now(CHILE_TZ).date()
        _fire(db, "a", "confirmado", "En combate", "Maule", 1.0, started_at=_chile_iso(hoy))
        _fire(db, "b", "confirmado", "En combate", "Maule", 1.0, started_at=_chile_iso(hoy))
        _fire(db, "c", "controlado", "Controlado", "Maule", 1.0, started_at=_chile_iso(hoy - timedelta(days=2)))
        _fire(db, "d", "extinguido", "Extinguido", "Maule", 1.0, started_at=_chile_iso(hoy - timedelta(days=9)))
        semana = client.get("/api/panorama?season=2026-2027").json()["semana"]
        assert (semana["incendios"], semana["dias_con_datos"]) == (3, 2)
        assert (semana["anterior"]["incendios"], semana["anterior"]["dias_con_datos"]) == (1, 1)


def test_panorama_semana_sin_datos_devuelve_ceros(make_client):
    """TEMP-31: una base sin incendios responde la semana en cero, con sus fechas y sin excepción."""
    with make_client(GOES_ENABLED="0") as client:
        hoy = datetime.now(CHILE_TZ).date()
        body = client.get("/api/panorama").json()
        semana = body["semana"]
        assert body["season"] is None
        assert (semana["incendios"], semana["ha"], semana["dias_con_datos"]) == (0, 0.0, 0)
        assert (semana["desde"], semana["hasta"]) == ((hoy - timedelta(days=6)).isoformat(), hoy.isoformat())
        assert semana["anterior"] == {
            "desde": (hoy - timedelta(days=13)).isoformat(),
            "hasta": (hoy - timedelta(days=7)).isoformat(),
            "incendios": 0,
            "ha": 0.0,
            "dias_con_datos": 0,
        }


def test_panorama_semana_no_incluye_datos_personales(make_client):
    """TEMP-31: el bloque nuevo son agregados; ninguna clave nombra a una persona o su dispositivo."""
    with make_client(GOES_ENABLED="0") as client:
        _seed(client.app.state.services.db)
        body = client.get("/api/panorama?season=2026-2027").json()
        assert _forbidden_keys(body["semana"]) == []
        assert set(body["semana"]) == {"desde", "hasta", "incendios", "ha", "dias_con_datos", "anterior"}


def test_panorama_comuna_detail_trae_la_comuna_pedida(make_client):
    """TEMP-03: ?comuna=<code> da el detalle aunque no entre al top 12."""
    from backend.geo import territory
    quilpue = territory().comunas_named("Quilpué")[0]
    with make_client() as client:
        db = client.app.state.services.db
        _fire(db, "f1", "controlado", "CONTROLADO", "Valparaíso", 120.0, comuna="Quilpué")
        _fire(db, "f2", "confirmado", "EN CURSO", "Valparaíso", 40.0, comuna="Quilpué")
        _br(db, quilpue.code, "2026-10-20", 4)
        body = client.get(f"/api/panorama?season=2026-2027&comuna={quilpue.code}").json()
    d = body["comuna_detail"]
    assert d["comuna"]["code"] == quilpue.code
    assert d["current"]["n"] == 2 and d["current"]["ha"] == 160.0 and d["current"]["en_combate"] == 1
    assert d["previous"]["n"] == 0 and d["previous"]["ha"] == 0.0


def test_panorama_comuna_boton_rojo_days_es_de_la_comuna(make_client):
    """Los días de Botón Rojo del detalle cuentan solo la comuna pedida."""
    from backend.geo import territory
    quilpue = territory().comunas_named("Quilpué")[0]
    with make_client() as client:
        db = client.app.state.services.db
        _fire(db, "f1", "controlado", "CONTROLADO", "Valparaíso", 10.0, season="2026-2027", comuna="Quilpué")
        _br(db, quilpue.code, "2026-10-20")
        _br(db, quilpue.code, "2026-10-21")
        _br(db, 999999, "2026-10-22")  # otra comuna no cuenta
        body = client.get(f"/api/panorama?season=2026-2027&comuna={quilpue.code}").json()
    assert body["comuna_detail"]["boton_rojo_days"] == 2


def test_panorama_comuna_previous_cuenta_la_temporada_anterior(make_client):
    from backend.geo import territory
    quilpue = territory().comunas_named("Quilpué")[0]
    with make_client() as client:
        db = client.app.state.services.db
        _fire(db, "f1", "controlado", "CONTROLADO", "Valparaíso", 10.0, season="2026-2027", comuna="Quilpué")
        _fire(db, "v1", "extinguido", "EXTINGUIDO", "Valparaíso", 55.0, season="2025-2026", comuna="Quilpué")
        _fire(db, "v2", "extinguido", "EXTINGUIDO", "Valparaíso", 45.0, season="2025-2026", comuna="Quilpué")
        body = client.get(f"/api/panorama?season=2026-2027&comuna={quilpue.code}").json()
    assert body["comuna_detail"]["previous"] == {"season": "2025-2026", "n": 2, "ha": 100.0}


def test_panorama_sin_comuna_responde_igual_que_antes(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _fire(db, "f1", "controlado", "CONTROLADO", "Valparaíso", 10.0, season="2026-2027", comuna="Quilpué")
        body = client.get("/api/panorama?season=2026-2027").json()
        assert body["comuna_detail"] is None
        assert {"totals", "by_comuna", "boton_rojo_days", "semana"} <= set(body)


def test_panorama_comuna_desconocida_da_422(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _fire(db, "f1", "controlado", "CONTROLADO", "Valparaíso", 10.0, season="2026-2027", comuna="Quilpué")
        assert client.get("/api/panorama?season=2026-2027&comuna=1").status_code == 422
