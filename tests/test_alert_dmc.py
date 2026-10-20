"""ALR-14: un aviso DMC nuevo (viento o calor extremo) que toca la comuna de un lugar
guardado genera una alerta nivel «aviso», una sola vez por aviso y lugar.

El cruce es por comuna (el polígono del aviso ya se resolvió a comunas en `ingest_dmc`),
no por distancia ni radio del lugar, y nunca llega a «urgente»: es un pronóstico de zona,
no un foco medido contra el viento del lugar.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx

from backend import alerts as alerts_mod
from backend.db import Database

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


def test_an_alert_for_other_comunas_creates_nothing(tmp_path):
    """(b) El aviso no toca la comuna del lugar → sin alerta."""
    db = _db(tmp_path)
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row(comunas=json.dumps([13101]))], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_a_place_without_comuna_creates_nothing(tmp_path):
    """(b bis) Un lugar fuera de una comuna conocida no tiene avisos DMC que cruzar."""
    db = _db(tmp_path, comuna=None)
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row()], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_an_expired_alert_creates_nothing(tmp_path):
    """Un aviso cuyo `expires` ya pasó no despierta a nadie."""
    db = _db(tmp_path)
    row = _dmc_row(expires=(NOW - timedelta(hours=1)).isoformat())
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [row], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_the_payload_carries_the_official_link_and_the_expiry(tmp_path):
    """(c) El payload trae el enlace oficial `web` y el vencimiento del aviso."""
    db = _db(tmp_path)
    [created] = asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row()], now=NOW))
    payload = created["payload"]
    assert payload["level"] == "aviso" and payload["kind"] == "dmc"
    assert payload["url"] == "/#/mi-zona"   # donde la interfaz muestra el aviso
    assert payload["dmc"]["web"] == _dmc_row()["web"]
    assert payload["dmc"]["expires"] == EXPIRES
    assert _dmc_row()["web"] in payload["body"]          # el enlace va en el texto
    assert "15:00" in payload["body"]                    # vence a las 15:00 hora de Chile


def test_heat_alert_carries_the_health_action_with_its_sources(tmp_path):
    """(a) ALR-22: el aviso de calor trae una acción de salud concreta y sus fuentes oficiales."""
    db = _db(tmp_path)
    row = _dmc_row(kind="calor", event="Calor extremo",
                   headline="Calor extremo en la región de Valparaíso")
    [created] = asyncio.run(alerts_mod.evaluate_dmc(db, [row], now=NOW))
    body = created["payload"]["body"]
    assert "toma agua a cada rato aunque no sientas sed" in body
    assert "entre las 11 y las 17 h" in body
    assert "MINSAL" in body and "SENAPRED" in body


def test_wind_alert_does_not_carry_the_heat_health_action(tmp_path):
    """(b) El aviso de viento no trae la acción de salud de calor."""
    db = _db(tmp_path)
    [created] = asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row()], now=NOW))
    body = created["payload"]["body"]
    assert "toma agua a cada rato" not in body
    assert "MINSAL" not in body


def test_the_dmc_body_keeps_the_disclaimer_only_in_the_footer(tmp_path):
    """(c) El cuerpo no repite el pie oficial y el aviso sigue sin prometer ser oficial."""
    db = _db(tmp_path)
    [created] = asyncio.run(alerts_mod.evaluate_dmc(db, [_dmc_row(kind="calor")], now=NOW))
    payload = created["payload"]
    assert "alerta oficial" not in payload["body"]
    assert alerts_mod.OFFICIAL_FOOTER not in payload["body"]
    assert payload["footer"] == alerts_mod.OFFICIAL_FOOTER


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
