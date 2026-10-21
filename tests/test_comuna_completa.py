"""OFI-29: la ficha de comuna completa — lluvia de la temporada y avisos de la DMC."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.geo import territory
from backend.routes import comuna

CHILE_TZ = ZoneInfo("America/Santiago")
VALPO = 5101  # Valparaíso


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _risk(db, code: int, day: str, level: str = "alto") -> None:
    db.execute(
        "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
        "level_combined, fwi, fwi_level, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (code, day, level, 80, 2, 4, level, 25.5, "alto", _stamp(datetime.now(timezone.utc))),
    )


def _br(db, code: int, day: str, hours: int = 6) -> None:
    db.execute(
        "INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
        (code, day, hours, 500.0, 0.4, _stamp(datetime.now(timezone.utc))),
    )


def _fire(db, fid: str, code: int, started: datetime, area_ha: float = 500.0) -> None:
    c = territory().by_code[code]
    lon, lat = c.center
    _fire_at(db, fid, code, started, lat, lon, area_ha)


def _fire_at(db, fid: str, code: int, started: datetime, lat: float, lon: float, area_ha: float = 500.0) -> None:
    c = territory().by_code[code]
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, area_ha, lat, lon, "
        "comuna, region, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            fid,
            f"INCENDIO {fid}",
            "confirmado",
            "En combate",
            _stamp(started),
            area_ha,
            lat,
            lon,
            c.name,
            c.region,
            _stamp(datetime.now(timezone.utc)),
            _stamp(datetime.now(timezone.utc)),
        ),
    )


def _rain(db, code: int, year: int = 2026, current_mm: float = 110.0, normal_mm: float = 100.0) -> None:
    db.execute(
        "INSERT INTO rain_season(comuna_code, year, current_mm, normal_mm, ratio, level, computed_at) VALUES (?,?,?,?,?,?,?)",
        (code, year, current_mm, normal_mm, round(current_mm / normal_mm, 3), "normal", _stamp(datetime.now(timezone.utc))),
    )


def _dmc(db, code: int, kind: str = "viento", onset: str | None = None, expires: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO dmc_alerts(id, kind, event, headline, severity, urgency, onset, expires, web, "
        "areas, comunas, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            f"aviso-{kind}-{code}-{onset or 'vigente'}",
            kind,
            "Viento fuerte",
            "Viento fuerte en la zona",
            "Moderate",
            "Expected",
            onset or (now - timedelta(hours=1)).isoformat(),
            expires or (now + timedelta(hours=1)).isoformat(),
            "https://example.test/aviso",
            "[]",
            json.dumps([code]),
            now.isoformat(),
        ),
    )


def test_ficha_trae_lluvia_y_avisos_dmc_con_su_fuente(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _rain(db, VALPO)
        _dmc(db, VALPO)
        data = client.get(f"/api/comuna/{VALPO}").json()
    assert data["rain"]["level"] == "normal"
    assert data["rain"]["current_mm"] == 110.0 and data["rain"]["normal_mm"] == 100.0
    assert data["rain_source"]["name"]
    assert [a["kind"] for a in data["dmc"]["alerts"]] == ["viento"]
    assert data["dmc"]["alerts"][0]["label"] == "Viento"
    assert data["dmc"]["source"]["name"]


def test_sin_temporada_de_lluvia_rain_es_null_y_dmc_vacio(make_client):
    with make_client(GOES_ENABLED="0") as client:
        data = client.get(f"/api/comuna/{VALPO}").json()
    assert data["rain"] is None
    assert data["rain_source"]["name"]
    assert data["dmc"]["alerts"] == []
    assert data["dmc"]["source"]["name"]
    assert set(data) == {
        "type",
        "comuna",
        "risk",
        "boton_rojo",
        "exposicion",
        "incendios_oficiales",
        "historia",
        "temporada",
        "rain",
        "rain_source",
        "dmc",
        "freshness",
        "data_as_of",
    }
    assert data["comuna"]["code"] == VALPO
    assert data["risk"]["days"] == [] and data["boton_rojo"]["days"] == []


def test_la_ficha_se_cachea_bajo_comuna_v3(make_client):
    today = datetime.now(CHILE_TZ).date().isoformat()
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _risk(db, VALPO, today)
        first = client.get(f"/api/comuna/{VALPO}").json()
        _br(db, VALPO, today)
        second = client.get(f"/api/comuna/{VALPO}").json()
        cached = db.cache_get(f"comuna:v3:{VALPO}")
    assert second == first
    assert cached is not None and cached["boton_rojo"]["days"] == []
    assert cached["rain"] is None and cached["dmc"]["alerts"] == []


def test_una_entrada_con_la_clave_vieja_no_se_sirve(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        db.cache_set(f"comuna:{VALPO}", {"type": "viejo", "comuna": {"code": VALPO}}, 300)
        data = client.get(f"/api/comuna/{VALPO}").json()
    assert data["type"] == "comuna"
    assert data["rain_source"]["name"]  # el payload viejo no traía este bloque


def test_codigo_inexistente_sigue_en_404(make_client):
    with make_client(GOES_ENABLED="0") as client:
        response = client.get("/api/comuna/9999")
    assert response.status_code == 404 and response.json()["detail"]


def test_unidades_en_hectareas_y_milimetros(make_client):
    now = datetime.now(timezone.utc)
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _fire(db, "medio_ha", VALPO, now - timedelta(hours=1), area_ha=0.5)
        _rain(db, VALPO, current_mm=12.5, normal_mm=100.0)
        data = client.get(f"/api/comuna/{VALPO}").json()
    assert data["incendios_oficiales"]["fires"][0]["area_ha"] == 0.5  # 0,5 ha, no 5.000 m²
    assert data["rain"]["current_mm"] == 12.5  # milímetros, no metros


def test_los_incendios_se_filtran_con_lat_lon_en_el_orden_correcto(make_client):
    now = datetime.now(timezone.utc)
    c = territory().by_code[VALPO]
    lon, lat = c.center
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _fire(db, "correcto", VALPO, now - timedelta(hours=1))
        _fire_at(db, "invertido", VALPO, now - timedelta(hours=1), lat=lon, lon=lat)
        data = client.get(f"/api/comuna/{VALPO}").json()
    assert [f["id"] for f in data["incendios_oficiales"]["fires"]] == ["correcto"]


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        instant = datetime(2026, 6, 2, 2, 30, tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)


def test_la_ventana_de_riesgo_usa_la_fecha_de_chile(make_client, monkeypatch):
    # 02:30 UTC del 2 de junio es 22:30 del 1 de junio en Chile (UTC-4).
    monkeypatch.setattr(comuna, "datetime", _FrozenDatetime)
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _risk(db, VALPO, "2026-06-01")
        _risk(db, VALPO, "2026-06-06")  # último día de la ventana si hoy es 1 de junio en Chile
        _risk(db, VALPO, "2026-06-07")  # solo entraría usando la fecha UTC
        data = client.get(f"/api/comuna/{VALPO}").json()
    dates = [d["date"] for d in data["risk"]["days"]]
    assert dates == ["2026-06-01", "2026-06-06"]


def test_las_fuentes_declaran_su_frescura(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        db.kv_set("rain_computed_at", "2026-10-19T12:00:00Z")
        db.kv_set("rain_normal_at", "2026-06-01T00:00:00Z")
        db.kv_set("dmc_at", "2026-10-20T09:00:00Z")
        db.kv_set("last_ingest_at", "2026-10-20T09:05:00Z")
        _rain(db, VALPO)
        _dmc(db, VALPO)
        data = client.get(f"/api/comuna/{VALPO}").json()
    assert data["rain_source"]["fetched_at"] == "2026-10-19T12:00:00Z"
    assert data["rain_source"]["normal_at"] == "2026-06-01T00:00:00Z"
    assert data["dmc"]["source"]["fetched_at"] == "2026-10-20T09:00:00Z"
    assert data["data_as_of"] == "2026-10-20T09:05:00Z"


# COMUNA-EDAD: cada bloque declara su propia edad en `freshness` — `data_as_of` es solo la
# ingesta satelital y no puede pararse sobre un riesgo calculado hace horas.


def test_freshness_riesgo_fresco_no_queda_atrasado(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        db.kv_set("risk_computed_at", _stamp(datetime.now(timezone.utc) - timedelta(minutes=30)))
        data = client.get(f"/api/comuna/{VALPO}").json()
    risk = data["freshness"]["risk"]
    assert risk["stale"] is False and risk["stale_after_s"] == 180 * 60  # la cadencia del recálculo
    assert risk["age_seconds"] is not None and risk["age_seconds"] < 3600


def test_freshness_riesgo_de_4_horas_queda_atrasado_y_la_lluvia_no(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        db.kv_set("risk_computed_at", _stamp(datetime.now(timezone.utc) - timedelta(hours=4)))
        _rain(db, VALPO)
        data = client.get(f"/api/comuna/{VALPO}").json()
    risk = data["freshness"]["risk"]
    assert risk["stale"] is True and risk["age_seconds"] > 14000
    rain = data["freshness"]["rain"]
    assert rain["stale"] is False and rain["dato_de"]
    assert rain["age_seconds"] is not None and rain["age_seconds"] >= 0


def test_freshness_sin_riesgo_calculado_queda_atrasado(make_client):
    with make_client(GOES_ENABLED="0") as client:
        data = client.get(f"/api/comuna/{VALPO}").json()
    risk = data["freshness"]["risk"]
    assert risk["dato_de"] is None and risk["age_seconds"] is None
    assert risk["stale"] is True


def test_freshness_marca_corrupta_queda_atrasada_sin_numeros_negativos(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        db.kv_set("risk_computed_at", "no-es-una-fecha")
        data = client.get(f"/api/comuna/{VALPO}").json()
    risk = data["freshness"]["risk"]
    assert risk["dato_de"] == "no-es-una-fecha" and risk["age_seconds"] is None
    assert risk["stale"] is True


def test_freshness_dmc_sin_avisos_no_es_una_falla(make_client):
    with make_client(GOES_ENABLED="0") as client:
        data = client.get(f"/api/comuna/{VALPO}").json()
    dmc = data["freshness"]["dmc"]
    assert dmc == {"dato_de": None, "age_seconds": None, "stale_after_s": 21600, "stale": False}


def test_freshness_dmc_usa_el_aviso_mas_reciente(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _dmc(db, VALPO, onset=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
        data = client.get(f"/api/comuna/{VALPO}").json()
    dmc = data["freshness"]["dmc"]
    assert dmc["dato_de"] and dmc["stale"] is False
    assert 7000 < dmc["age_seconds"] < 8000


def test_freshness_cada_bloque_lleva_su_marca(make_client):
    today = datetime.now(CHILE_TZ).date().isoformat()
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        db.kv_set("risk_computed_at", _stamp(datetime.now(timezone.utc) - timedelta(hours=4)))
        _risk(db, VALPO, today)
        _br(db, VALPO, today)
        data = client.get(f"/api/comuna/{VALPO}").json()
    fresh = data["freshness"]
    assert set(fresh) == {"risk", "boton_rojo", "dmc", "rain", "incendios_oficiales"}
    assert fresh["boton_rojo"]["stale"] is False and fresh["boton_rojo"]["age_seconds"] is not None
    # Sin corrida CONAF_INCENDIOS registrada, la regla de freshness lo declara atrasado.
    assert fresh["incendios_oficiales"]["stale"] is True and fresh["incendios_oficiales"]["dato_de"] is None
