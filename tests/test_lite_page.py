"""Guía mínima del modo liviano (UX-42): `/web/lite.html` debe responder qué
hacer ahora y qué llevar si te evacúan, en HTML estático — sin JavaScript
nuevo, sin hosts externos que cargar y dentro del presupuesto de UX-03
(menos de 50 KB). El criterio de hosts externos es el de
`test_estaticas_guardas.py`: los <a href> no descargan nada.

El umbral de frescura lo manda el servidor (`/api/status.freshness.stale_after_s`,
`backend/freshness.py`): lite.js no repite un 30 escrito a mano."""

import re

from backend.settings import ROOT

LITE = ROOT / "web" / "lite.html"
LITE_JS = ROOT / "web" / "js" / "lite.js"
PRESUPUESTO_BYTES = 50 * 1024


def _seccion(html, heading_id):
    """HTML de la <section aria-labelledby="heading_id"> completa."""
    bloque = html.split(f'aria-labelledby="{heading_id}"', 1)
    assert len(bloque) == 2, f"no existe la sección {heading_id} en lite.html"
    return bloque[1].split("</section>", 1)[0]


def test_lite_responde_200(make_client):
    with make_client() as client:
        r = client.get("/web/lite.html")
        assert r.status_code == 200


def test_lite_tiene_las_dos_secciones():
    html = LITE.read_text(encoding="utf-8")
    assert "Si ves fuego o humo" in html
    assert "Si te evacúan" in html


def test_lite_que_hacer_tiene_tres_pasos():
    html = LITE.read_text(encoding="utf-8")
    pasos = re.findall(r"<li", _seccion(html, "lite-quehacer-h"))
    assert len(pasos) == 3, f"la sección «Si ves fuego o humo» tiene {len(pasos)} pasos, deben ser 3"


def test_lite_cita_datos_clave():
    html = LITE.read_text(encoding="utf-8")
    for texto in ("130", "132", "2 litros", "SENAPRED"):
        assert texto in html, f"falta {texto!r} en lite.html"


def test_lite_sin_scripts_nuevos():
    """El único <script> permitido es el módulo existente /web/js/lite.js."""
    html = LITE.read_text(encoding="utf-8").lower()
    scripts = re.findall(r"<script[^>]*>", html)
    assert len(scripts) == 1, f"lite.html tiene {len(scripts)} <script>, solo puede tener el de lite.js"
    assert "/web/js/lite.js" in scripts[0]


def test_lite_dentro_del_presupuesto():
    assert len(LITE.read_bytes()) < PRESUPUESTO_BYTES, f"lite.html pesa {LITE.stat().st_size} bytes; el presupuesto de UX-03 es <50 KB"


def test_lite_usa_el_umbral_que_publica_el_servidor():
    """El umbral de frescura lo decide el servidor: si lite.js vuelve a comparar
    contra un 30 literal, /lite puede decir «datos atrasados» cuando el mapa y
    Mi zona dicen lo contrario."""
    js = LITE_JS.read_text(encoding="utf-8")
    assert "stale_after_s" in js, "lite.js no lee freshness.stale_after_s de /api/status"
    assert re.search(r"STALE_MIN\s*=[^;\n]*stale_after_s", js), "lite.js no guarda el umbral del servidor en STALE_MIN"
    assert not re.search(r"[<>]=?\s*30\b|\b30\s*[<>]", js), "lite.js compara contra un 30 literal: el umbral debe venir de /api/status"


def test_lite_sin_hosts_externos():
    """Ninguna referencia a otro host que el navegador descargue (src, action,
    link). Los <a href> a SENAPRED/CONAF son enlaces, no recursos."""
    html = LITE.read_text(encoding="utf-8")
    for tag, ref in re.findall(r'<(\w+)[^>]*?\b(?:src|href|action)\s*=\s*["\']([^"\']+)', html):
        if tag.lower() == "a":
            continue
        assert not re.match(r"(?:https?:)?//", ref), f"lite.html: host externo {ref}"
