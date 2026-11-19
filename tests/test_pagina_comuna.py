"""SEO-05: páginas /comuna/<slug> — canonical, riesgo, noindex, redirección, escape, sitemap.
PROD-06: la página responde «¿hay incendios hoy?» con CONAF y las señales satelitales."""
from datetime import datetime, timezone

from backend.routes import paginas_comuna
from tests.test_comuna_api import _fire
from tests.test_scars import seed_incident


def seed_riesgo(db, code: int, level: str = "alto") -> None:
    db.execute(
        "INSERT OR REPLACE INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
        "tmax, rhmin, windmax, gustmax, level_combined, fwi, fwi_level, reasons, computed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (code, paginas_comuna._hoy(), level, 70, 0, 0, 34.0, 18.0, 30.0, 45.0, "alto", 30.0, "alto", "[]",
         "2026-10-23T14:00:00Z"))


def test_pagina_comuna_indexable_con_canonical_y_riesgo(make_client):
    """Tres comunas con datos: 200, canonical propio, nivel y fuente con hora."""
    with make_client() as client:
        db = client.app.state.services.db
        comunas = list(paginas_comuna.territory().comunas)[:3]
        for c in comunas:
            seed_riesgo(db, c.code)
            r = client.get(f"/comuna/{paginas_comuna.slug(c.name)}")
            assert r.status_code == 200, c.name
            body = r.text
            assert 'canonical" href="' in body and f"/comuna/{paginas_comuna.slug(c.name)}" in body
            assert "index,follow" in body and "Nivel" in body and "computed_at" not in body.lower() or "calculado" in body
            assert "application/ld+json" in body and "130" in body and "132" in body
            assert "no es una alerta oficial" in body


def test_comuna_sin_datos_va_noindex(make_client):
    with make_client() as client:
        c = paginas_comuna.territory().comunas[0]
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "noindex" in body and "Todavía no hay pronóstico" in body


def test_codigo_numerico_redirige_al_slug(make_client):
    with make_client() as client:
        c = paginas_comuna.territory().comunas[0]
        r = client.get(f"/comuna/{c.code}", follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == f"/comuna/{paginas_comuna.slug(c.name)}"


def test_slug_desconocido_da_404_honesto(make_client):
    with make_client() as client:
        assert client.get("/comuna/esta-comuna-no-existe").status_code == 404
        assert client.get("/comuna/99999999").status_code == 404


def test_el_slug_escapa_tildes_y_el_html_escapa_nombres():
    assert paginas_comuna.slug("Peñaflor") == "penaflor"
    assert paginas_comuna.slug("Alto Bío Bío") == "alto-bio-bio"
    assert "&lt;" in paginas_comuna._esc("<script>")


def test_sitemap_solo_lista_comunas_con_datos(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        t = paginas_comuna.territory()
        seed_riesgo(db, t.comunas[0].code)
        body = client.get("/sitemap-comunas.xml").text
        assert f"/comuna/{paginas_comuna.slug(t.comunas[0].name)}" in body
        assert f"/comuna/{paginas_comuna.slug(t.comunas[1].name)}" not in body

def test_pagina_comuna_responde_si_hay_incendios_hoy(make_client):
    """PROD-06: la página suma los incendios que informa CONAF y las señales satelitales del día."""
    with make_client() as client:
        db = client.app.state.services.db
        c = next(c for c in paginas_comuna.territory().comunas if c.name == "Concepción")
        seed_riesgo(db, c.code)
        _fire(db, "F-1", c.code, datetime.now(timezone.utc))
        seed_incident(db, "inc-comuna", comuna_code=c.code, lat=c.center[1], lon=c.center[0], days_ago=0, status="posible")
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "Incendios en" in body and "INCENDIO F-1" in body and "CONAF" in body
        assert "señal de calor" in body and "última señal" in body


def test_pagina_comuna_sin_incendios_lo_dice_honesto(make_client):
    """Sin datos, el cero se explica: no es «no hay fuego»."""
    with make_client() as client:
        db = client.app.state.services.db
        c = paginas_comuna.territory().comunas[0]
        seed_riesgo(db, c.code)
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "CONAF no informa incendios activos" in body
        assert "ninguna señal de calor" in body


def test_los_incendios_de_la_pagina_escapan_el_nombre(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        c = paginas_comuna.territory().comunas[0]
        seed_riesgo(db, c.code)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lon, lat = c.center
        db.execute(
            "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, "
            "first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("F-X", "INCENDIO <script>alert(1)</script>", "confirmado", "En combate", now, lat, lon,
             c.name, c.region, now, now),
        )
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "INCENDIO <script>" not in body and "&lt;script&gt;" in body

