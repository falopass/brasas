"""UX-05: al compartir la ficha de un incidente se ve su propia tarjeta (título con estado y
comuna, e imagen «BRASA · no es una alerta oficial») en vez de la genérica del sitio.

`/i/<id>` sirve la app con las etiquetas Open Graph del incidente inyectadas — los
rastreadores no ven el fragmento #/ — y `/og/incident/<id>.png` es la imagen 1200×630.
"""

import io
import re
import uuid
from datetime import datetime, timedelta, timezone

from PIL import Image

from backend import incidents, og
from backend.geo import territory
from tests.test_incidents import obs


def _seed(client):
    """Un incidente «posible» con dos detecciones (VIIRS + GOES) en Santiago."""
    db = client.app.state.services.db
    now = datetime.now(timezone.utc).replace(microsecond=0)
    pts = [
        obs(db, "a", -33.45, -70.66, when=now - timedelta(hours=2)),
        obs(db, "b", -33.44, -70.66, when=now - timedelta(hours=1), sensor="ABI", confidence="alta", resolution_m=2000),
    ]
    [inc] = incidents.update(db, pts, now)
    return inc


def _seed_point(client, lat, lon, *, cuando=None):
    """Un incidente «posible» de dos detecciones en el punto, con la comuna que lo contiene.

    Fuera de Chile la ingesta no crea incidentes (FUEGO-12): se siembra con una comuna
    chilena para poder crearlo y se limpia después, como las filas extranjeras ya guardadas.
    """
    db = client.app.state.services.db
    cuando = cuando or datetime.now(timezone.utc).replace(microsecond=0)
    comuna = territory().locate(lat, lon)
    if comuna is None:
        # FUEGO-04: el agrupador ya no crea incidentes fuera de Chile. Se siembra la fila
        # como las que quedaron guardadas antes del recorte, para probar el enlace viejo.
        return _insert_foreign_incident(db, lat, lon, cuando)
    code = comuna.code
    pts = [
        obs(db, f"a{lat}-{lon}", lat, lon, when=cuando - timedelta(hours=2), comuna_code=code),
        obs(
            db,
            f"b{lat}-{lon}",
            lat,
            lon,
            when=cuando - timedelta(hours=1),
            sensor="ABI",
            confidence="alta",
            resolution_m=2000,
            comuna_code=code,
        ),
    ]
    [inc] = incidents.update(db, pts, cuando)
    return inc


def _insert_foreign_incident(db, lat, lon, cuando):
    """Incidente guardado antes de FUEGO-04: sin comuna, para que la ficha diga «fuera de Chile»."""
    iid = uuid.uuid4().hex[:12]
    stamp = cuando.strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, "
        "fixed_source, official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (iid, "posible", stamp, stamp, stamp, lat, lon, lat, lat, lon, lon, 2, 2, "ABI,VIIRS", 12.0, None, 0, None, stamp),
    )
    return db.one("SELECT * FROM incidents WHERE id = ?", (iid,))


def test_share_page_injects_incident_og_tags(make_client):
    with make_client() as client:
        inc = _seed(client)
        r = client.get(f"/i/{inc['id']}")
        assert r.status_code == 200
        assert 'property="og:title" content="BRASA · Posible incendio en Santiago,' in r.text
        # Las genéricas del sitio se reemplazan: una sola og:image, absoluta y del incidente.
        assert r.text.count('property="og:image"') == 1
        og_image = re.search(r'property="og:image" content="([^"]+)"', r.text).group(1)
        assert og_image.startswith("http") and og_image.endswith(f"/og/incident/{inc['id']}.png")
        assert re.search(r'property="og:url" content="([^"]+)"', r.text).group(1).endswith(f"/i/{inc['id']}")
        assert "No es una alerta oficial" in r.text
        # La persona que abre el enlace cae en la ficha real de la app.
        assert f'http-equiv="refresh" content="0; url=/#/incendio/{inc["id"]}"' in r.text
        # Y sigue siendo la app completa, no una página aparte.
        assert 'id="app"' in r.text and 'src="/web/js/app.js"' in r.text


def test_share_page_with_unknown_id_serves_the_default_page(make_client):
    with make_client() as client:
        for r in (client.get("/i/ffffffffffff"), client.get("/i/no-es-id")):
            assert r.status_code == 200
            assert 'id="app"' in r.text
            assert 'property="og:image" content="https://brasa-chile.ddiegosebastianbb.workers.dev/web/icons/og.png"' in r.text
            assert 'http-equiv="refresh"' not in r.text


def test_share_image_is_a_1200x630_png(make_client):
    with make_client() as client:
        inc = _seed(client)
        r = client.get(f"/og/incident/{inc['id']}.png")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        assert r.headers["cache-control"] == "public, max-age=600"
        assert Image.open(io.BytesIO(r.content)).size == (1200, 630)


def test_share_image_unknown_id_is_a_sober_404(make_client):
    with make_client() as client:
        assert client.get("/og/incident/ffffffffffff.png").status_code == 404
        assert client.get("/og/incident/no-es-id.png").status_code == 404
        assert client.get("/og/incident/aaaaaaaaaaaa.jpg").status_code == 404


def test_share_image_is_refreshed_when_the_comuna_changes(make_client):
    """FIX-44: CONAF rebautiza o reubica el foco y la tarjeta debe reflejarlo al instante,
    no cuando la entrada vieja caiga de la caché."""
    with make_client() as client:
        inc = _seed(client)
        db = client.app.state.services.db
        first = client.get(f"/og/incident/{inc['id']}.png").content
        # La misma fila repetida reutiliza la caché.
        assert client.get(f"/og/incident/{inc['id']}.png").content == first
        db.execute("UPDATE incidents SET comuna_code = 1101 WHERE id = ?", (inc["id"],))
        moved = client.get(f"/og/incident/{inc['id']}.png").content
        assert moved != first
        assert client.get(f"/og/incident/{inc['id']}.png").content == moved


def _link_conaf(db, inc_id: str, name: str = "Las Máquinas", status_raw: str = "En combate", area_ha: float | None = 1200.5) -> None:
    """La ficha que publica CONAF y el enlace que deja `link_official` (official_ref)."""
    stamp = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, "
        "area_ha, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("conaf-1", name, "confirmado", status_raw, stamp, -33.45, -70.66, "Santiago", "Metropolitana", area_ha, stamp, stamp),
    )
    db.execute("UPDATE incidents SET official_ref = 'conaf-1', status = 'confirmado' WHERE id = ?", (inc_id,))


def test_share_card_names_the_conaf_fire_and_its_area(make_client):
    """UX-54: el incendio bautizado por CONAF se comparte con nombre, estado y superficie."""
    with make_client() as client:
        inc = _seed(client)
        db = client.app.state.services.db
        assert 'content="BRASA · Posible incendio en Santiago,' in client.get(f"/i/{inc['id']}").text
        generic_png = client.get(f"/og/incident/{inc['id']}.png").content

        _link_conaf(db, inc["id"])
        r = client.get(f"/i/{inc['id']}")
        assert r.status_code == 200
        assert 'property="og:title" content="BRASA · Incendio «Las Máquinas» en Santiago,' in r.text
        assert 'property="og:image:alt" content="BRASA · Incendio «Las Máquinas» en Santiago,' in r.text
        # La línea que se dibuja bajo el estado, con coma decimal como el resto del sitio.
        assert og._official_line({"status_raw": "En combate", "area_ha": 1200.5}) == "CONAF: En combate · 1200,5 ha"
        assert og._official_line({"status_raw": "En combate", "area_ha": None}) == "CONAF: En combate"
        assert client.get(f"/og/incident/{inc['id']}.png").content != generic_png


def test_share_page_without_an_official_name_looks_like_today(make_client):
    """Sin ficha CONAF (o con nombre vacío) la tarjeta es exactamente la de siempre:
    el producto nunca inventa un nombre."""
    with make_client() as client:
        inc = _seed(client)
        db = client.app.state.services.db
        # official_ref apunta a una ficha que no existe.
        db.execute("UPDATE incidents SET official_ref = 'conaf-fantasma' WHERE id = ?", (inc["id"],))
        r = client.get(f"/i/{inc['id']}")
        assert 'property="og:title" content="BRASA · Posible incendio en Santiago,' in r.text
        # Y una ficha real pero sin nombre tampoco cambia la tarjeta.
        _link_conaf(db, inc["id"], name="")
        r = client.get(f"/i/{inc['id']}")
        assert 'property="og:title" content="BRASA · Incendio informado por CONAF en Santiago,' in r.text


def test_a_conaf_name_with_ampersand_and_quotes_is_escaped(make_client):
    """Un nombre con `&` o comillas no puede romper las etiquetas ni el og:image:alt."""
    with make_client() as client:
        inc = _seed(client)
        db = client.app.state.services.db
        _link_conaf(db, inc["id"], name='Bosque & "Lago"')
        r = client.get(f"/i/{inc['id']}")
        assert "Incendio «Bosque &amp; &quot;Lago&quot;»" in r.text
        assert 'Bosque & "Lago"' not in r.text


def test_share_image_is_refreshed_when_conaf_updates_the_area(make_client):
    """Si CONAF remide el incendio, la tarjeta cambia: la clave del caché lleva la superficie."""
    with make_client() as client:
        inc = _seed(client)
        db = client.app.state.services.db
        _link_conaf(db, inc["id"])
        first = client.get(f"/og/incident/{inc['id']}.png").content
        assert client.get(f"/og/incident/{inc['id']}.png").content == first
        db.execute("UPDATE official_fires SET area_ha = 2500.0 WHERE id = 'conaf-1'")
        updated = client.get(f"/og/incident/{inc['id']}.png").content
        assert updated != first
        assert client.get(f"/og/incident/{inc['id']}.png").content == updated


def test_share_page_of_a_point_outside_chile_says_so(make_client):
    """Un enlace viejo a un foco extranjero no puede leerse como un incendio chileno."""
    with make_client() as client:
        inc = _seed_point(client, -31.997, -68.288)  # San Juan, Argentina
        r = client.get(f"/i/{inc['id']}")
        assert r.status_code == 200
        assert 'property="og:title" content="BRASA · Fuera de Chile · Posible incendio"' in r.text
        assert 'property="og:image:alt" content="BRASA · Fuera de Chile · Posible incendio.' in r.text
        assert "Este punto no está en territorio chileno: no es una alerta de BRASA." in r.text
        assert " en Chile" not in r.text


def test_share_page_of_a_point_in_chile_keeps_the_usual_card(make_client):
    with make_client() as client:
        inc = _seed_point(client, -35.42, -71.60)  # Talca
        r = client.get(f"/i/{inc['id']}")
        assert r.status_code == 200
        assert 'property="og:title" content="BRASA · Posible incendio en Talca, Maule"' in r.text
        assert "no está en territorio chileno" not in r.text
        assert "Fuera de Chile" not in r.text


def _inc(n_obs=2, status="posible", first=None, last=None):
    """Un incidente mínimo para probar `_detail` sin base de datos."""
    return {"n_obs": n_obs, "status": status, "first_seen_at": first, "last_seen_at": last}


def test_detail_names_the_last_signal_when_it_is_well_after_the_first():
    """COMPARTIR-02: si la última señal llegó más de 30 min después de la primera,
    la tarjeta dice cuándo fue, no solo cuándo empezó."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    inc = _inc(first=stamp(now - timedelta(hours=2)), last=stamp(now - timedelta(minutes=10)))
    detail = og._detail(inc)
    assert detail.startswith("2 detecciones satelitales · primera señal ")
    assert "(hora de Chile continental)" in detail
    assert detail.endswith(" · última señal hace 10 minutos")


def test_detail_says_no_new_heat_when_extinguido_or_the_signal_is_stale():
    """Un incendio sin calor nuevo no puede leerse como si estuviera pasando ahora."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    ext = _inc(status="extinguido", first=stamp(now - timedelta(hours=32)), last=stamp(now - timedelta(hours=30)))
    assert og._detail(ext).endswith(" · sin calor nuevo hace 1 día")
    # Lo mismo aunque el estado siga «posible»: más de 6 h sin señal ya es fuego frío.
    frio = _inc(first=stamp(now - timedelta(hours=9)), last=stamp(now - timedelta(hours=8)))
    assert og._detail(frio).endswith(" · sin calor nuevo hace 8 horas")


def test_detail_keeps_quiet_when_first_and_last_signal_match():
    """Una sola detección (o marcas a menos de 30 min entre sí) no repite la hora."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    t = stamp(now - timedelta(minutes=20))
    assert "última señal" not in og._detail(_inc(n_obs=1, status="anomalia", first=t, last=t))
    inc = _inc(first=stamp(now - timedelta(hours=1)), last=stamp(now - timedelta(minutes=40)))
    detail = og._detail(inc)
    assert "última señal" not in detail and "sin calor nuevo" not in detail


def test_the_detail_lines_stay_left_of_the_minimap():
    """El detalle se parte a lo ancho del bloque (como el título): nada bajo el minimapa."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    inc = _inc(n_obs=12, status="extinguido", first=stamp(now - timedelta(days=3)), last=stamp(now - timedelta(hours=30)))
    for line in og._wrap(og._detail(inc), og._font(30), 740):
        assert og._font(30).getlength(line) <= 740


def test_share_page_and_card_tell_how_old_the_last_signal_is(make_client):
    """La frase llega al og:description, y la imagen cambia cuando el incidente se enfría:
    `last_seen_at` ya estaba en la clave de la caché."""
    with make_client() as client:
        db = client.app.state.services.db
        now = datetime.now(timezone.utc).replace(microsecond=0)
        pts = [
            obs(db, "a", -33.45, -70.66, when=now - timedelta(hours=2)),
            obs(db, "b", -33.44, -70.66, when=now - timedelta(minutes=10), sensor="ABI", confidence="alta", resolution_m=2000),
        ]
        [inc] = incidents.update(db, pts, now)
        assert "última señal hace 10 minutos" in client.get(f"/i/{inc['id']}").text
        caliente = client.get(f"/og/incident/{inc['id']}.png").content
        frio = (now - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.execute("UPDATE incidents SET status = 'extinguido', last_seen_at = ? WHERE id = ?", (frio, inc["id"]))
        assert client.get(f"/og/incident/{inc['id']}.png").content != caliente


def test_share_page_of_a_discarded_point_does_not_claim_a_heat_signal(make_client):
    """FUEGO-32: un incidente descartado (fuera de Chile) no puede compartirse como «Señal de calor»."""
    with make_client() as client:
        inc = _seed_point(client, -31.997, -68.288)  # San Juan, Argentina
        client.app.state.services.db.execute("UPDATE incidents SET status = 'descartado' WHERE id = ?", (inc["id"],))
        r = client.get(f"/i/{inc['id']}")
        assert r.status_code == 200
        assert 'property="og:title" content="BRASA · Fuera de Chile · Descartado"' in r.text
        assert "Señal de calor" not in r.text


def test_share_image_outside_chile_draws_no_point(make_client):
    """Dos focos extranjeros en coordenadas distintas dan la misma imagen: no hay brasa."""
    with make_client() as client:
        cuando = datetime.now(timezone.utc).replace(microsecond=0)
        a = _seed_point(client, -31.997, -68.288, cuando=cuando)  # San Juan, Argentina
        b = _seed_point(client, -19.700, -67.725, cuando=cuando)  # Potosí, Bolivia
        png_a = client.get(f"/og/incident/{a['id']}.png").content
        png_b = client.get(f"/og/incident/{b['id']}.png").content
        assert Image.open(io.BytesIO(png_a)).size == (1200, 630)
        assert png_a == png_b
        # En Chile el punto sí se dibuja: dos coordenadas de la misma comuna dan imágenes distintas.
        c = _seed_point(client, -35.40, -71.58, cuando=cuando)  # Talca
        d = _seed_point(client, -35.44, -71.62, cuando=cuando)  # Talca
        assert client.get(f"/og/incident/{c['id']}.png").content != client.get(f"/og/incident/{d['id']}.png").content
