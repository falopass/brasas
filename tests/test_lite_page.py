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


def test_lite_tiene_las_dos_secciones_y_tres_pasos():
    html = LITE.read_text(encoding="utf-8")
    assert "Si ves fuego o humo" in html
    assert "Si te evacúan" in html
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


def test_lite_porque_del_dia():
    """UX-70 / RISK-08: bajo «Clima de hoy», /lite dice por qué el día es peligroso
    (los números de la fila y hasta dos razones de risk_days[0].reasons, que llega
    como texto JSON y debe tener respaldo cuando no parsea) y de qué hora es el
    pronóstico («Calculado …» junto a computed_at). Sin dato no se muestra nada."""
    js = LITE_JS.read_text(encoding="utf-8")
    assert re.search(r"JSON\.parse\(today\.reasons", js), "lite.js no lee risk_days[0].reasons"
    assert re.search(r"catch\s*\{\s*reasons\s*=\s*\[\]", js), (
        "falta la rama de respaldo: si el JSON de reasons no parsea no se muestra nada"
    )
    assert re.search(r"slice\(0,\s*2\)", js), "las razones del día deben acotarse a dos"
    for campo in ("today.tmax", "today.rhmin", "today.windmax"):
        assert campo in js, f"falta {campo} en la frase de condiciones del día"
    assert "Calculado" in js and "computed_at" in js, (
        "falta «Calculado …» junto a computed_at (edad del pronóstico)"
    )
    # La página sigue autocontenida: sin <script src> externos ni cambios en los teléfonos.
    html = LITE.read_text(encoding="utf-8")
    assert "<script src=" not in html.lower(), "lite.html no puede cargar scripts externos"
    for numero in ('href="tel:130"', 'href="tel:132"'):
        assert numero in html, f"falta {numero} en los teléfonos de lite.html"


def test_lite_se_encuentra_desde_la_app_y_las_preguntas():
    """Una página que nadie enlaza solo la usa quien leyó el repositorio:
    Ajustes y las preguntas frecuentes deben llevar a ella con un toque."""
    for archivo in ("web/js/ui.js", "web/preguntas.html"):
        assert "/web/lite.html" in (ROOT / archivo).read_text(encoding="utf-8"), f"{archivo} no enlaza el modo liviano"
