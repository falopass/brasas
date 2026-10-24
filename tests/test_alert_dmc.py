"""ALR-14: un aviso DMC nuevo (viento, calor extremo y —AGUA-07— lluvia o tormenta) que
toca la comuna de un lugar guardado genera una alerta nivel «aviso», una sola vez por
aviso y lugar.

El cruce es por comuna (el polígono del aviso ya se resolvió a comunas en `ingest_dmc`),
no por distancia ni radio del lugar, y nunca llega a «urgente»: es un pronóstico de zona,
no un foco medido contra el viento del lugar. Lluvia y tormenta son la excepción: solo
avisan cuando la comuna tiene cicatriz de incendio reciente.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend import alerts as alerts_mod
from backend import services as services_mod
from backend.db import Database
from tests.test_scars import seed_incident
from tests.conftest import json_response

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
ONSET = (NOW - timedelta(hours=1)).isoformat()      # 2026-10-18T11:00:00+00:00
EXPIRES = (NOW + timedelta(hours=6)).isoformat()    # 15:00 hora de Chile


def _db(tmp_path, comuna: int | None = 5109, older_adult: int = 0) -> Database:
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, older_adult, created_at) "
               "VALUES ('p1','s1','Casa','casa',-33.02,-71.55,10,?,?,'2026-10-01T00:00:00Z')", (comuna, older_adult))
    return db


def _dmc_row(**kw) -> dict:
    """Una fila de `dmc_alerts` como la deja `ingest_dmc` (areas y comunas en JSON)."""
    return {"id": "urn:oid:2.49.0.0.152.0.2026.10.18.1", "kind": "viento",
            "event": "Viento Normal a Moderado",
            "headline": "Viento Normal a Moderado en litoral de la región de Valparaíso",
            "severity": "Moderate", "urgency": "Expected", "onset": ONSET, "expires": EXPIRES,
            "web": "https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html",
            "areas": "[]", "comunas": json.dumps([5109]), "fetched_at": NOW.isoformat(), **kw}


def test_wind_alert_touching_the_place_comuna_creates_one_aviso(tmp_path):
    """(a) Aviso de viento que toca la comuna del lugar → una alerta «aviso»; dos corridas no duplican."""
    db = _db(tmp_path, older_adult=1)   # ni viviendo una persona mayor sube a «urgente»
    created = asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row()], now=NOW))
    assert len(created) == 1 and created[0]["level"] == "aviso"
    row = db.one("SELECT * FROM alerts")
    assert row["observation_id"] == "dmc:urn:oid:2.49.0.0.152.0.2026.10.18.1"
    assert row["level"] == "aviso"
    # `observed_at` es el inicio (onset) del aviso, normalizado a UTC.
    assert row["observed_at"] == "2026-10-18T11:00:00Z"
    # La misma pasada repetida (la tabla se reescribe en cada ingesta) no avisa dos veces.
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row()], now=NOW)) == []
    assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1


@pytest.mark.parametrize(
    "db_kwargs,row_kwargs",
    [
        ({"comuna": 13101}, {}),                                   # (b) el aviso es de otra comuna
        ({"comuna": None}, {}),                                    # (b bis) el lugar no tiene comuna
        ({}, {"expires": (NOW - timedelta(hours=1)).isoformat()}),  # aviso ya vencido
    ],
)
def test_a_warning_that_does_not_apply_creates_nothing(tmp_path, db_kwargs, row_kwargs):
    db = _db(tmp_path, **db_kwargs)
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row(**row_kwargs)], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_the_payload_carries_the_official_link_the_expiry_and_the_footer(tmp_path):
    """(c) El payload trae el enlace oficial `web`, el vencimiento y el descargo, una sola vez."""
    db = _db(tmp_path)
    [created] = asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row()], now=NOW))
    payload = created["payload"]
    assert payload["level"] == "aviso" and payload["kind"] == "dmc"
    assert payload["url"] == "/#/mi-zona"   # donde la interfaz muestra el aviso
    assert payload["dmc"]["web"] == _dmc_row()["web"]
    assert payload["dmc"]["expires"] == EXPIRES
    assert payload["expires"] == EXPIRES          # nivel superior: `vencida` lo lee al entregar
    assert _dmc_row()["web"] in payload["body"]          # el enlace va en el texto
    assert "15:00" in payload["body"]                    # vence a las 15:00 hora de Chile continental
    assert "hora de Chile continental" in payload["body"]
    # El cuerpo no repite el pie oficial y el aviso sigue sin prometer ser oficial.
    assert "alerta oficial" not in payload["body"]
    assert alerts_mod.OFFICIAL_FOOTER not in payload["body"]
    assert payload["footer"] == alerts_mod.OFFICIAL_FOOTER


def test_only_the_heat_alert_carries_the_health_action_with_its_sources(tmp_path):
    """(a) ALR-22: el aviso de calor trae una acción de salud concreta y sus fuentes oficiales;
    el de viento no la repite."""
    db = _db(tmp_path)
    [viento] = asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row()], now=NOW))
    calor = _dmc_row(id="urn:oid:2.49.0.0.152.0.2026.10.18.2", kind="calor", event="Calor extremo",
                     headline="Calor extremo en la región de Valparaíso")
    [caliente] = asyncio.run(alerts_mod.evaluate_dmc(db, [calor], now=NOW))
    body = caliente["payload"]["body"]
    assert "toma agua a cada rato aunque no sientas sed" in body
    assert "entre las 11 y las 17 h" in body
    assert "MINSAL" in body and "SENAPRED" in body
    assert "toma agua a cada rato" not in viento["payload"]["body"]
    assert "MINSAL" not in viento["payload"]["body"]


def test_ingest_dmc_creates_the_alert_once_through_the_real_path(make_client, web):
    """La ingesta completa (RSS → CAP → comunas → aviso) avisa una sola vez por aviso y lugar."""
    onset = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    cap = f"""<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>urn:oid:2.49.0.0.152.0.2026.10.19.1</identifier>
  <sender>meteochile@meteochile.cl</sender><sent>2026-10-19T00:16:05-03:00</sent>
  <status>Actual</status><msgType>Alert</msgType><scope>Public</scope>
  <info><language>es-CL</language><category>Met</category>
    <event>Viento Normal a Moderado</event><urgency>Expected</urgency><severity>Moderate</severity>
    <onset>{onset}</onset><expires>{expires}</expires>
    <headline>Viento Normal a Moderado en litoral de la región de Valparaíso</headline>
    <web>https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html</web>
    <area><areaDesc>Valparaíso: Litoral</areaDesc>
      <polygon>-33.10,-71.70 -33.00,-71.50 -33.10,-71.40 -33.10,-71.70</polygon></area>
  </info></alert>""".encode()
    feed = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Sistema de Alerta Temprana</title>
  <item><title>Aviso A564/2026: Viento Normal a Moderado</title>
    <link>https://archivos.meteochile.gob.cl/portaldmc/rss/a564.xml</link>
    <category>Aviso</category></item>
</channel></rss>"""
    web.add(lambda r: r.url.path.endswith("rss.php"), lambda r: httpx.Response(200, text=feed))
    web.add(lambda r: "meteochile" in r.url.host, lambda r: httpx.Response(200, content=cap))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        db = svc.db
        db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
        db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) "
                   "VALUES ('p1','s1','Casa','casa',-33.02,-71.55,10,5109,'2026-10-01T00:00:00Z')")
        assert asyncio.run(svc.ingest_dmc()) == 1
        [row] = db.query("SELECT * FROM alerts")
        assert row["observation_id"] == "dmc:urn:oid:2.49.0.0.152.0.2026.10.19.1"
        assert row["level"] == "aviso" and row["delivered_at"]   # deliver la marcó intentada
        # La segunda ingesta reemplaza dmc_alerts con el mismo aviso: no se repite el aviso.
        assert asyncio.run(svc.ingest_dmc()) == 1
        assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1


# ---------------------------------------------------------------- AGUA-07: cicatriz

LLUVIA = {"id": "urn:oid:2.49.0.0.152.0.2026.10.18.9", "kind": "lluvia",
          "event": "Precipitaciones Moderadas a Fuertes",
          "headline": "Precipitaciones Moderadas a Fuertes en la región de Valparaíso"}
TORMENTA = {"id": "urn:oid:2.49.0.0.152.0.2026.10.18.10", "kind": "tormenta",
            "event": "Tormenta Eléctrica", "headline": "Tormenta eléctrica en Valparaíso"}


def _cicatriz(db, comuna: int = 5109, **kw) -> None:
    """Un incidente con detecciones confiables que `scars.season_scars` cuenta como
    cicatriz de la temporada en la comuna del lugar (≥ SCAR_MIN_HA en SCAR_DAYS días)."""
    seed_incident(db, "inc-1", comuna_code=comuna, lat=-33.02, lon=-71.52, **kw)


def test_a_rain_alert_only_wakes_a_comuna_with_a_recent_scar(tmp_path):
    """AGUA-07: el aviso de lluvia de la DMC no despierta a nadie sin suelo quemado en la
    comuna; con cicatriz reciente genera el «aviso» y explica la amenaza de aluvión."""
    db = _db(tmp_path)
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row(**LLUVIA)], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None
    _cicatriz(db)
    [created] = asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row(**LLUVIA)], now=NOW))
    assert created["payload"]["dmc"]["kind"] == "lluvia"
    body = created["payload"]["body"]
    assert "lluvia intensa" in body and "quebradas" in body
    # No le cae el consejo genérico de viento/calor: el aviso es de aluvión.
    assert "arrastra pavesas" not in body and "seca la vegetación" not in body


def test_a_storm_alert_follows_the_same_scar_rule(tmp_path):
    db = _db(tmp_path)
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row(**TORMENTA)], now=NOW)) == []
    _cicatriz(db)
    [created] = asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row(**TORMENTA)], now=NOW))
    assert "aviso de tormenta" in created["payload"]["body"]


@pytest.mark.parametrize("incident_kw", [
    {"comuna": 13101},                        # la cicatriz es de otra comuna
    {"days_ago": alerts_mod.SCAR_DAYS + 1},   # fuera de la ventana de la temporada
    {"status": "descartado"},                 # fuera del filtro de la cicatriz
    {"fixed_source": 1},                      # volcán/industria: calor sin suelo quemado
])
def test_a_scar_that_does_not_count_leaves_the_rain_alert_silent(tmp_path, incident_kw):
    db = _db(tmp_path)
    _cicatriz(db, **incident_kw)
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row(**LLUVIA)], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_wind_and_heat_still_alert_without_any_scar(tmp_path):
    """La regla de la cicatriz no encadena los avisos de siempre: viento y calor siguen
    llegando a toda comuna que toca el polígono del aviso."""
    db = _db(tmp_path)
    calor = _dmc_row(id="urn:oid:2.49.0.0.152.0.2026.10.18.11", kind="calor", event="Calor extremo",
                     headline="Calor extremo en la región de Valparaíso")
    assert len(asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row(), calor], now=NOW))) == 2


def test_a_pending_dmc_alert_past_its_expires_is_not_delivered(make_client, web, monkeypatch):
    """El vencimiento del CAP viaja en el nivel superior del payload: una pendiente vencida
    —aplazada por silencio nocturno o reintentada tras una entrega cortada— se marca y no
    se manda; la que sigue vigente sí sale."""
    monkeypatch.setattr(services_mod, "utcnow", lambda: NOW)
    sent = []
    web.add(lambda r: "telegram" in r.url.host,
            lambda r: sent.append(r) or json_response({"ok": True}))
    with make_client(TELEGRAM_BOT_TOKEN="123:tok") as client:
        svc = client.app.state.services
        db = svc.db
        db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
        db.execute("UPDATE subscribers SET telegram_chat_id = '777' WHERE id = 's1'")
        db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) "
                   "VALUES ('p1','s1','Casa','casa',-33.02,-71.55,10,5109,'2026-10-01T00:00:00Z')")
        stamp = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        pasado = (NOW - timedelta(hours=1)).isoformat()
        futuro = (NOW + timedelta(hours=6)).isoformat()

        def fila(obs_id: str, expires: str, delivered: str = "[]") -> None:
            payload = {"title": "Aviso de la DMC", "body": "Detectado hace 2 horas.",
                       "level": "aviso", "kind": "dmc", "expires": expires,
                       "place": {"id": "p1", "name": "Casa", "lat": -33.02, "lon": -71.55},
                       "observation": {"id": obs_id, "observed_at": stamp},
                       "dmc": {"id": "cap-x", "expires": expires}, "url": "/#/mi-zona",
                       "footer": alerts_mod.OFFICIAL_FOOTER}
            db.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, "
                       "lat, lon, observed_at, created_at, payload, delivered) VALUES ('p1',?,'aviso',1,0,0,"
                       "-33.05,-71.55,?,?,?,?)",
                       (obs_id, stamp, stamp, json.dumps(payload), delivered))

        fila("dmc:vencida-silencio", pasado, '["silencio"]')  # aplazada de madrugada, ya venció
        fila("dmc:vencida-reintento", pasado)                 # pendiente tras una caída, ya venció
        fila("dmc:vigente", futuro, '["silencio"]')           # aplazada y todavía vigente
        asyncio.run(svc.deliver([]))
        rows = {r["observation_id"]: r for r in db.query("SELECT observation_id, delivered, delivered_at FROM alerts")}
        assert len(sent) == 1, "solo la vigente se entrega"
        assert rows["dmc:vencida-silencio"]["delivered_at"] is not None
        assert "telegram" not in rows["dmc:vencida-silencio"]["delivered"]
        assert rows["dmc:vencida-reintento"]["delivered_at"] is not None
        assert rows["dmc:vencida-reintento"]["delivered"] == "[]"  # marcada, sin canal entregado
        assert '"telegram"' in rows["dmc:vigente"]["delivered"]
