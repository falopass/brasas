"""UX-05: al compartir la ficha de un incidente se ve su propia tarjeta (título con estado y
comuna, e imagen «BRASA · no es una alerta oficial») en vez de la genérica del sitio.

`/i/<id>` sirve la app con las etiquetas Open Graph del incidente inyectadas — los
rastreadores no ven el fragmento #/ — y `/og/incident/<id>.png` es la imagen 1200×630.
"""

import io
import re
from datetime import datetime, timedelta, timezone

from PIL import Image

from backend import incidents, og
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
