"""SEO-05: páginas /comuna/<slug> — canonical, riesgo, noindex, redirección, escape, sitemap.
PROD-06: la página responde «¿hay incendios hoy?» con CONAF y las señales satelitales.
PROD-07: el piloto Biobío muestra el estado mensual del Calendario de Quemas CONAF."""
from datetime import datetime, timezone

import pytest

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


def seed_fuentes(db) -> None:
    """Marca de ingesta CONAF y satélite: sin ella la página no puede afirmar ni ausencia ni presencia."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new) "
        "VALUES (?,?,?,?,?,?,?)",
        ("CONAF", "CONAF_INCENDIOS", now, now, 1, 0, 0),
    )
    db.kv_set("last_ingest_at", now)


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


def test_las_hectareas_chicas_conservan_su_decimal():
    assert paginas_comuna._fmt_ha(0.4) == "0,4"
    assert paginas_comuna._fmt_ha(9.96) == "10,0"
    assert paginas_comuna._fmt_ha(1234.6) == "1.235"
    assert paginas_comuna._fmt_ha(1500) == "1.500"


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
        seed_fuentes(db)
        _fire(db, "F-1", c.code, datetime.now(timezone.utc))
        lon, lat = c.center
        seed_incident(db, "inc-comuna", comuna_code=c.code, lat=lat, lon=lon, days_ago=0, status="posible")
        # Lo que no debe contar como señal de hoy: ayer, fuente fija y estado terminal.
        seed_incident(db, "inc-ayer", comuna_code=c.code, lat=lat, lon=lon, days_ago=1, status="posible")
        seed_incident(db, "inc-fija", comuna_code=c.code, lat=lat, lon=lon, days_ago=0, status="posible", fixed_source=1)
        seed_incident(db, "inc-ext", comuna_code=c.code, lat=lat, lon=lon, days_ago=0, status="extinguido")
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "Incendios en" in body and "INCENDIO F-1" in body and "CONAF" in body
        assert "1 incidente con señal de calor" in body and "última señal" in body
        assert "{_esc" not in body and "reporte público de incendios" in body


def test_pagina_comuna_sin_incendios_lo_dice_honesto(make_client):
    """Sin datos, el cero se explica: no es «no hay fuego»."""
    with make_client() as client:
        db = client.app.state.services.db
        c = paginas_comuna.territory().comunas[0]
        seed_riesgo(db, c.code)
        seed_fuentes(db)
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "CONAF no informa incendios activos" in body
        assert "ningún incidente con señal de calor" in body


def test_pagina_comuna_sin_ingesta_no_afirma_ausencia(make_client):
    """Sin ingesta de las fuentes, la página dice que no sabe, no que no hay fuego."""
    with make_client() as client:
        db = client.app.state.services.db
        c = paginas_comuna.territory().comunas[0]
        seed_riesgo(db, c.code)
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "aún no recibe el reporte de incendios de CONAF" in body
        assert "aún no tiene datos satelitales" in body
        assert "CONAF no informa incendios activos" not in body
        assert "ningún incidente con señal de calor" not in body


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


def _comuna(nombre: str):
    return next(c for c in paginas_comuna.territory().comunas if c.name == nombre)


@pytest.mark.parametrize(
    "nombre,fecha,esperado",
    [
        ("Curanilahue", "2026-11-15", "En noviembre, el calendario de CONAF 2026-2027 marca restricciones para quemas"),
        ("Concepción", "2027-01-10", "En enero, el calendario de CONAF 2026-2027 prohíbe el uso del fuego"),
        ("Concepción", "2027-04-10", "D.S. 6/2018 desde el 01 abril al 30 de septiembre"),
        ("Curanilahue", "2027-05-10", "En mayo, el calendario de CONAF 2026-2027 no marca una restricción adicional"),
    ],
)
def test_quemas_piloto_muestra_el_estado_del_mes(monkeypatch, make_client, nombre, fecha, esperado):
    monkeypatch.setattr(paginas_comuna, "_hoy", lambda: fecha)
    with make_client() as client:
        c = _comuna(nombre)
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "Uso del fuego y quemas" in body
        assert esperado in body
        assert "CONAF puede suspender el uso del fuego" in body
        assert "La autorización la da CONAF o el municipio" in body
        for url in (
            "https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/region-del-bio-bio/",
            "https://www.conafprevencionincendios.cl/wp-content/uploads/Biobio.pdf",
            "https://www.conaf.cl/incendios/prevencion-y-mitigacion/uso-del-fuego/",
        ):
            assert url in body
        lower = body.lower()
        for prohibido in ("puedes quemar", "puedes usar el fuego", "está permitido", "está autorizado", "autorizado a quemar"):
            assert prohibido not in lower


def test_quemas_no_piloto_no_muestra_la_seccion(monkeypatch, make_client):
    monkeypatch.setattr(paginas_comuna, "_hoy", lambda: "2026-11-15")
    with make_client() as client:
        c = next(c for c in paginas_comuna.territory().comunas if c.code not in paginas_comuna._QUEMAS_PILOTO)
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "Uso del fuego y quemas" not in body
        assert "calendario de CONAF 2026-2027" not in body


def test_quemas_piloto_cubre_todas_las_comunas_biobio():
    biobio = {c.code for c in paginas_comuna.territory().comunas if c.region_code == 8}
    assert set(paginas_comuna._QUEMAS_PILOTO) == biobio


def test_quemas_matriz_conaf_2026_2027_exacta():
    """PROD-07: bloquea la matriz 5 grupos × 12 meses (oct-2026…sep-2027) del PDF oficial."""
    esperado = {
        "arauco": ("A", "A", "A", "R", "R", "A", "A", "V", "V", "V", "V", "A"),
        "concepcion_metropolitano": ("A", "A", "A", "R", "R", "A", "R", "R", "R", "R", "R", "R"),
        "florida_santa_juana": ("A", "A", "A", "R", "R", "A", "A", "V", "V", "V", "V", "A"),
        "provincia_biobio": ("A", "A", "A", "R", "R", "A", "A", "V", "V", "V", "V", "A"),
        # Los Ángeles tiene abril partido (1-14 A, 15-30 R); la matriz guarda la base y el corte
        # se prueba en test_quemas_los_angeles_en_abril_muestra_el_corte_del_15.
        "los_angeles": ("A", "A", "A", "R", "R", "A", "A", "R", "R", "R", "R", "R"),
    }
    comunas = {"arauco": 7, "concepcion_metropolitano": 10, "florida_santa_juana": 2, "provincia_biobio": 13, "los_angeles": 1}
    assert set(paginas_comuna._QUEMAS_GRUPOS) == set(esperado)
    for clave, estados in esperado.items():
        grupo = paginas_comuna._QUEMAS_GRUPOS[clave]
        assert tuple(grupo["estados"]) == estados
        assert len(grupo["estados"]) == 12
        assert len(grupo["comunas"]) == comunas[clave]


def test_quemas_los_angeles_en_abril_muestra_el_corte_del_15(monkeypatch, make_client):
    la = _comuna("Los Angeles")
    assert paginas_comuna._quema_estado(la, "2027-04-10")["estado"] == "A"
    assert paginas_comuna._quema_estado(la, "2027-04-20")["estado"] == "R"
    monkeypatch.setattr(paginas_comuna, "_hoy", lambda: "2027-04-10")
    with make_client() as client:
        body = client.get(f"/comuna/{paginas_comuna.slug(la.name)}").text
        assert "del 1 al 14 marca restricciones" in body
        assert "del 15 al 30 prohíbe el uso del fuego" in body
        assert "D.S. 4/2019 desde el 15 de abril al 30 de septiembre" in body


def test_quemas_calendario_vencido_manda_a_conaf_sin_inventar(monkeypatch, make_client):
    monkeypatch.setattr(paginas_comuna, "_hoy", lambda: "2027-10-01")
    with make_client() as client:
        c = _comuna("Concepción")
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
        assert "El calendario de CONAF 2026-2027 ya venció" in body
        assert "confirma el estado vigente en CONAF" in body
        assert "En octubre, el calendario de CONAF 2026-2027" not in body
        assert "https://www.conafprevencionincendios.cl/wp-content/uploads/Biobio.pdf" in body

