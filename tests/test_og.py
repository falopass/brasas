"""UX-05: al compartir la ficha de un incidente se ve su propia tarjeta (título con estado y
comuna, e imagen «BRASA · no es una alerta oficial») en vez de la genérica del sitio.

`/i/<id>` sirve la app con las etiquetas Open Graph del incidente inyectadas — los
rastreadores no ven el fragmento #/ — y `/og/incident/<id>.png` es la imagen 1200×630.
"""
import io
import re
from datetime import datetime, timedelta, timezone

from PIL import Image

from backend import incidents
from tests.test_incidents import obs


def _seed(client):
    """Un incidente «posible» con dos detecciones (VIIRS + GOES) en Santiago."""
    db = client.app.state.services.db
    now = datetime.now(timezone.utc).replace(microsecond=0)
    pts = [obs(db, "a", -33.45, -70.66, when=now - timedelta(hours=2)),
           obs(db, "b", -33.44, -70.66, when=now - timedelta(hours=1), sensor="ABI", confidence="alta", resolution_m=2000)]
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
