"""OFI-29: /api/comuna/{code} — la ficha de una comuna en un solo JSON."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend import censo
from backend.geo import territory
from tests.test_scars import seed_incident

CHILE_TZ = ZoneInfo("America/Santiago")
VALPO = 5101  # Valparaíso
IQUIQUE = 1101  # Iquique


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


def _fire(db, fid: str, code: int, started: datetime) -> None:
    c = territory().by_code[code]
    lon, lat = c.center
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, "
        "comuna, region, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            fid,
            f"INCENDIO {fid}",
            "confirmado",
            "En combate",
            _stamp(started),
            lat,
            lon,
            c.name,
            c.region,
            _stamp(datetime.now(timezone.utc)),
            _stamp(datetime.now(timezone.utc)),
        ),
    )


def test_comuna_con_riesgo_y_censo_devuelve_todos_los_bloques_con_fuente(make_client):
    today = datetime.now(CHILE_TZ).date()
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _risk(db, VALPO, today.isoformat())
        _risk(db, VALPO, (today + timedelta(days=5)).isoformat(), "moderado")
        _risk(db, VALPO, (today + timedelta(days=6)).isoformat())  # fuera de la ventana de 5 días
        _br(db, VALPO, today.isoformat())
        _fire(db, "f1", VALPO, datetime.now(timezone.utc) - timedelta(days=1))
        data = client.get(f"/api/comuna/{VALPO}").json()
    assert data["comuna"]["code"] == VALPO and data["comuna"]["name"] == "Valparaíso"
    assert [d["date"] for d in data["risk"]["days"]] == [today.isoformat(), (today + timedelta(days=5)).isoformat()]
    assert data["risk"]["days"][0]["level_combined"] == "alto" and data["risk"]["days"][0]["fwi"] == 25.5
    assert data["risk"]["source"]["name"] == "BRASA (30-30-30 + FWI)"
    assert data["boton_rojo"]["days"] == [{"date": today.isoformat(), "hours": 6, "area_ha": 500.0, "proportion": 0.4}]
    assert "CONAF" in data["boton_rojo"]["source"]["name"]
    assert data["exposicion"]["poblacion"] > 0 and "INE" in data["exposicion"]["license"]
    assert [f["id"] for f in data["incendios_oficiales"]["fires"]] == ["f1"]
    assert "CONAF" in data["incendios_oficiales"]["source"]["name"]


def test_censo_ausente_deja_exposicion_en_null(make_client, monkeypatch, tmp_path):
    monkeypatch.setattr(censo, "CENSO_FILE", tmp_path / "no_existe.json")
    censo._cache = None
    try:
        with make_client(GOES_ENABLED="0") as client:
            data = client.get(f"/api/comuna/{VALPO}").json()
        assert data["exposicion"] is None and data["comuna"]["code"] == VALPO
    finally:
        censo._cache = None


def test_incendios_oficiales_filtran_por_comuna_y_ventana_de_30_dias(make_client):
    now = datetime.now(timezone.utc)
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _fire(db, "reciente", VALPO, now - timedelta(days=10))
        _fire(db, "otra_comuna", IQUIQUE, now - timedelta(days=5))
        _fire(db, "viejo", VALPO, now - timedelta(days=40))
        data = client.get(f"/api/comuna/{VALPO}").json()
    assert [f["id"] for f in data["incendios_oficiales"]["fires"]] == ["reciente"]
    assert {f["name"] for f in data["incendios_oficiales"]["fires"]} == {"INCENDIO reciente"}


# --- RISK-23: el bloque `cicatrices` trae la huella satelital de la comuna ---


def test_comuna_sin_huellas_lleva_cicatrices_con_nota(make_client):
    """Sin incidentes, `temporada.cicatrices` sale con fuente, ceros y la nota que
    los explica; la fila de temporada de CONAF-GEPRIF se mantiene intacta."""
    with make_client(GOES_ENABLED="0") as client:
        data = client.get(f"/api/comuna/{VALPO}").json()
    assert "CONAF" in data["temporada"]["source"]["name"]
    cic = data["temporada"]["cicatrices"]
    assert cic["source"]["name"]
    assert cic["ha"] == 0 and cic["n_incidentes"] == 0
    assert cic["desde"] is None and cic["hasta"] is None
    assert "huella" in cic["note"]


def test_comuna_con_cicatriz_devuelve_ha_y_conteo(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        lon, lat = territory().by_code[VALPO].center
        seed_incident(db, "inc-v", comuna_code=VALPO, lat=lat, lon=lon)
        data = client.get(f"/api/comuna/{VALPO}").json()
    cic = data["temporada"]["cicatrices"]
    assert cic["n_incidentes"] == 1 and cic["ha"] > 0
    assert cic["desde"] <= cic["hasta"]
