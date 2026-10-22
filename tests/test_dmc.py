"""Pruebas de los avisos CAP de la DMC: lectura, filtro y cruce con las comunas reales."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from shapely.geometry import Polygon

from backend.geo import territory
from backend.providers import _retry, dmc

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Sistema de Alerta Temprana</title>
  <item><title>Aviso A564/2026: Viento Normal a Moderado</title>
    <link>https://archivos.meteochile.gob.cl/portaldmc/rss/a564.xml</link>
    <category>Aviso</category><pubDate>Sun, 18 Oct 2026 00:11:17 -0300</pubDate></item>
  <item><title>Alerta AA180/2026: Precipitaciones Moderadas</title>
    <link>https://archivos.meteochile.gob.cl/portaldmc/rss/aa180.xml</link>
    <category>Alerta</category></item>
</channel></rss>"""

CAP = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>urn:oid:2.49.0.0.152.0.2026.10.18.1</identifier>
  <sender>meteochile@meteochile.cl</sender>
  <sent>2026-10-18T00:16:05-03:00</sent>
  <status>Actual</status><msgType>Alert</msgType><scope>Public</scope>
  <info>
    <language>es-CL</language><category>Met</category>
    <event>Viento Normal a Moderado</event>
    <urgency>Expected</urgency><severity>Moderate</severity>
    <onset>2026-10-18T12:00:00-03:00</onset>
    <expires>2026-10-18T18:00:00-03:00</expires>
    <headline>Viento Normal a Moderado en litoral de la región de Valparaíso</headline>
    <web>https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html</web>
    <area><areaDesc>Valparaíso: Litoral</areaDesc>
      <polygon>-33.10,-71.70 -33.00,-71.50 -33.10,-71.40 -33.10,-71.70</polygon></area>
    <area><areaDesc>Sin polígono válido</areaDesc><polygon>basura</polygon></area>
  </info>
</alert>"""


FEED_TWO = FEED.replace(
    "<item><title>Alerta AA180/2026: Precipitaciones Moderadas</title>", "<item><title>Aviso A565/2026: Viento Fuerte</title>"
)

# CAP 1.2 permite varios <info> en un aviso (por idioma o por grupo de zonas): el primero es
# de lluvia y no le importa a BRASA; hay que leer las zonas del segundo, de viento.
CAP_TWO_INFO = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>urn:oid:2.49.0.0.152.0.2026.10.19.1</identifier>
  <sender>meteochile@meteochile.cl</sender>
  <sent>2026-10-19T00:16:05-03:00</sent>
  <status>Actual</status><msgType>Alert</msgType><scope>Public</scope>
  <info>
    <language>es-CL</language><category>Met</category>
    <event>Precipitaciones Moderadas</event>
    <urgency>Expected</urgency><severity>Moderate</severity>
    <headline>Precipitaciones Moderadas en la región de Valparaíso</headline>
    <area><areaDesc>Valparaíso: Litoral (lluvia)</areaDesc>
      <polygon>-33.10,-71.70 -33.00,-71.50 -33.10,-71.40</polygon></area>
  </info>
  <info>
    <language>es-CL</language><category>Met</category>
    <event>Viento Fuerte</event>
    <urgency>Expected</urgency><severity>Severe</severity>
    <onset>2026-10-19T12:00:00-03:00</onset>
    <expires>2026-10-19T18:00:00-03:00</expires>
    <headline>Viento Fuerte en la costa del Maule</headline>
    <area><areaDesc>Maule: Costa</areaDesc>
      <polygon>-35.50,-72.70 -35.40,-72.50 -35.50,-72.40</polygon></area>
  </info>
</alert>"""

# Una misma zona descrita con dos <polygon> (área discontinua, como litoral y precordillera):
# son dos anillos separados del mismo aviso, no uno.
CAP_TWO_POLYGONS = CAP.replace(
    "<polygon>-33.10,-71.70 -33.00,-71.50 -33.10,-71.40 -33.10,-71.70</polygon>",
    "<polygon>-33.10,-71.70 -33.00,-71.50 -33.10,-71.40</polygon><polygon>-33.30,-71.90 -33.20,-71.80 -33.30,-71.70</polygon>",
)


@pytest.fixture
def no_sleeps(monkeypatch):
    """Reintentos sin espera real, como en `test_retry`."""
    async def fake_sleep(seconds: float) -> None:
        pass
    monkeypatch.setattr(_retry.asyncio, "sleep", fake_sleep)


def _fetch(handler) -> list[dmc.Alert]:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await dmc.fetch_alerts(client)
    return asyncio.run(go())


def test_fetch_alerts_survives_a_transient_feed_failure(no_sleeps):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(503, text="caído")
        return httpx.Response(200, text=FEED_TWO if "rss.php" in request.url.path else CAP)

    alerts = _fetch(handler)
    assert [a.id for a in alerts] == ["urn:oid:2.49.0.0.152.0.2026.10.18.1"] * 2
    assert calls[0] == dmc.FEED_URL and len(calls) == 4  # RSS ×2 + un CAP por aviso


def test_fetch_alerts_skips_a_cap_that_stays_down(no_sleeps):
    def handler(request: httpx.Request) -> httpx.Response:
        if "rss.php" in request.url.path:
            return httpx.Response(200, text=FEED_TWO)
        if "aa180" in request.url.path:
            return httpx.Response(503, text="caído")
        return httpx.Response(200, text=CAP)

    alerts = _fetch(handler)
    assert len(alerts) == 1 and alerts[0].event == "Viento Normal a Moderado"


def test_fetch_alerts_raises_dmcerror_when_feed_stays_down(no_sleeps):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="caído")

    with pytest.raises(dmc.DmcError, match="La DMC no respondió"):
        _fetch(handler)


def test_feed_lists_cap_links():
    items = dmc.parse_feed(FEED)
    assert [i["category"] for i in items] == ["Aviso", "Alerta"]
    assert items[0]["link"].endswith("a564.xml")


@pytest.mark.parametrize("title, kind", [
    ("Aviso A564/2026: Viento Normal a Moderado", "viento"),
    ("Alerta: Temperaturas Extremas en la zona central", "calor"),
    ("Aviso: Olas de Calor en el norte", "calor"),
    ("AVISO POR ALTAS TEMPERATURAS", "calor"),
    ("Alerta: Temperaturas altas en la zona central", "calor"),
    ("Aviso: Calor Extremo", "calor"),
    ("Aviso: Vientos intensos", "viento"),
    ("Aviso: Precipitaciones Moderadas a Fuertes", None),
    ("Aviso: Nevadas en cordillera", None),
    ("Aviso: Ola de frío", None),
    ("Alerta: Nevadas", None),
])
def test_only_wind_and_heat_matter(title, kind):
    assert dmc.kind_of(title) == kind


def test_heat_cap_in_plural_is_kept():
    """Un CAP con evento «Olas de Calor» se clasifica calor y llega a la tabla de alertas."""
    cap = CAP.replace("Viento Normal a Moderado", "Olas de Calor")
    alert = dmc.parse_alert(cap.encode())
    assert alert.kind == "calor" and alert.event == "Olas de Calor"


def test_cap_is_read_with_its_zones():
    alert = dmc.parse_alert(CAP.encode())
    assert alert.kind == "viento" and alert.severity == "Moderate"
    assert alert.expires == "2026-10-18T18:00:00-03:00"
    assert [a.desc for a in alert.areas] == ["Valparaíso: Litoral", "Sin polígono válido"]
    assert alert.areas[0].polygon == [(-71.70, -33.10), (-71.50, -33.00), (-71.40, -33.10), (-71.70, -33.10)]
    assert alert.areas[1].polygon == []  # «basura» no se convierte en un polígono inventado


def test_a_cap_with_several_info_blocks_reads_the_relevant_one():
    alert = dmc.parse_alert(CAP_TWO_INFO.encode())
    assert alert.kind == "viento" and alert.event == "Viento Fuerte"
    assert alert.severity == "Severe"  # todo sale del bloque elegido, no del primero
    assert [a.desc for a in alert.areas] == ["Maule: Costa"]


def test_several_polygons_in_one_area_are_all_read():
    alert = dmc.parse_alert(CAP_TWO_POLYGONS.encode())
    assert alert.areas[0].polygon == [
        (-71.70, -33.10),
        (-71.50, -33.00),
        (-71.40, -33.10),
        (-71.70, -33.10),  # primer anillo
        (-71.90, -33.30),
        (-71.80, -33.20),
        (-71.70, -33.30),
        (-71.90, -33.30),  # segundo anillo
    ]


def test_a_cap_without_info_still_raises_dmcerror():
    cap = "<alert xmlns='urn:oasis:names:tc:emergency:cap:1.2'><identifier>x</identifier></alert>"
    with pytest.raises(dmc.DmcError):
        dmc.parse_alert(cap.encode())


def test_alert_polygon_reaches_real_comunas():
    alert = dmc.parse_alert(CAP.encode())
    t = territory()
    codes = [c.code for c in t.comunas_in(Polygon(alert.areas[0].polygon).buffer(0))]
    assert 5109 in codes, "el litoral de Valparaíso debe incluir Viña del Mar"
    assert all(isinstance(c, int) for c in codes)


def test_comunas_outside_chile_have_no_alert():
    t = territory()
    assert t.comunas_in(Polygon([(-64.0, -40.0), (-63.0, -40.0), (-63.0, -39.0), (-64.0, -39.0)])) == []


def test_zone_name_is_used_when_the_cap_has_no_polygon():
    """El aviso de Juan Fernández llega sin polígono: hay que resolverlo por el nombre de la zona."""
    t = territory()
    juan_fernandez = t.comunas_named("Juan Fernández")
    assert len(juan_fernandez) == 1 and juan_fernandez[0].name == "Juan Fernández"
    magallanes = t.comunas_named("Magallanes: Insular Norte")
    assert magallanes and all(c.region_code == 12 for c in magallanes)
    assert t.comunas_named("Zona inexistente") == []
    assert t.comunas_named("") == []


def test_risk_api_exposes_dmc_without_data(make_client):
    with make_client() as client:
        body = client.get("/api/risk").json()
    assert body["dmc"] == {}
    assert body["dmc_source"]["name"] == dmc.SOURCE
    assert "solo los de viento y calor" in body["dmc_source"]["note"]


def _seed_dmc_alert(db, onset: str | None, expires: str | None) -> None:
    """Un aviso sembrado directo en la tabla, como la ingesta lo dejaría."""
    db.execute(
        "INSERT INTO dmc_alerts(id, kind, event, headline, severity, urgency, onset, expires, web, "
        "areas, comunas, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (f"a-{id(db)}-{onset}-{expires}", "viento", "Viento", "Titular", "Moderate", "Expected",
         onset, expires, "https://example.test", "[]", json.dumps([5109]),
         datetime.now(timezone.utc).isoformat()))


def _risk_dmc(client) -> dict:
    return client.get("/api/risk").json()["dmc"]


@pytest.mark.parametrize("onset_h, expires_h, shown", [
    (-5, -1, False),   # vencido
    (2, 6, False),     # todavía no empieza
    (-1, 2, True),     # vigente
    (-1, None, True),  # sin `expires` se muestra
])
def test_alert_visibility_follows_its_window(make_client, onset_h, expires_h, shown):
    with make_client() as client:
        now = datetime.now(timezone.utc)
        _seed_dmc_alert(client.app.state.services.db,
                        (now + timedelta(hours=onset_h)).isoformat(),
                        None if expires_h is None else (now + timedelta(hours=expires_h)).isoformat())
        body = _risk_dmc(client)
    if shown:
        assert [a["kind"] for a in body["5109"]] == ["viento"]
    else:
        assert body == {}
