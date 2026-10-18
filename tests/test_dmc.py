"""Pruebas de los avisos CAP de la DMC: lectura, filtro y cruce con las comunas reales."""
from __future__ import annotations

from shapely.geometry import Polygon

from backend.geo import territory
from backend.providers import dmc

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


def test_feed_lists_cap_links():
    items = dmc.parse_feed(FEED)
    assert [i["category"] for i in items] == ["Aviso", "Alerta"]
    assert items[0]["link"].endswith("a564.xml")


def test_only_wind_and_heat_matter():
    assert dmc.kind_of("Aviso A564/2026: Viento Normal a Moderado") == "viento"
    assert dmc.kind_of("Alerta: Temperaturas Extremas en la zona central") == "calor"
    assert dmc.kind_of("Aviso: Precipitaciones Moderadas a Fuertes") is None
    assert dmc.kind_of("Aviso: Nevadas en cordillera") is None


def test_cap_is_read_with_its_zones():
    alert = dmc.parse_alert(CAP.encode())
    assert alert.kind == "viento" and alert.severity == "Moderate"
    assert alert.expires == "2026-10-18T18:00:00-03:00"
    assert [a.desc for a in alert.areas] == ["Valparaíso: Litoral", "Sin polígono válido"]
    assert alert.areas[0].polygon == [(-71.70, -33.10), (-71.50, -33.00), (-71.40, -33.10), (-71.70, -33.10)]
    assert alert.areas[1].polygon == []  # «basura» no se convierte en un polígono inventado


def test_polygon_is_reversed_to_lon_lat_and_closed():
    points = dmc.polygons("-33.5,-70.6 -33.6,-70.7 -33.7,-70.8")
    assert points[0] == (-70.6, -33.5)  # CAP escribe lat,lon; shapely espera lon,lat
    assert points[0] == points[-1]


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
