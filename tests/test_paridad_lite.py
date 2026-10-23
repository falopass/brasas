"""Paridad del modo liviano (QA-41): `web/lite.html` es autocontenido por diseño,
así que su lista de teléfonos de emergencia está copiada a mano de `PHONES` en
`web/js/ui.js`. Un número mal copiado en una emergencia es el peor error posible:
estas guardas hacen que cualquier desincronización rompa el CI.

Si falla la comparación por un número editado a mano en lite.html (cambio de
prueba revertido antes de entregar), el mensaje dice qué archivo corregir."""

import re

from backend.settings import ROOT

LITE = ROOT / "web" / "lite.html"
LITE_JS = ROOT / "web" / "js" / "lite.js"
UI = ROOT / "web" / "js" / "ui.js"
QUEHAGO = ROOT / "web" / "js" / "views" / "quehago.js"
ZONA = ROOT / "web" / "js" / "views" / "zona.js"


def _telefonos_lite():
    """(número, etiqueta) de cada <a href="tel:…"> del bloque de teléfonos de
    lite.html, en el orden en que aparecen."""
    html = LITE.read_text(encoding="utf-8")
    bloque = html.split('class="phones"', 1)[1].split("</div>", 1)[0]
    return [
        (num.strip(), etiqueta.strip())
        for num, etiqueta in re.findall(
            r'href="tel:[^"]*">\s*<strong>([^<]+)</strong>\s*<span>([^<]+)</span>',
            bloque,
        )
    ]


def _telefonos_canonicos():
    """(número, etiqueta) de la constante PHONES de web/js/ui.js, en orden."""
    src = UI.read_text(encoding="utf-8")
    bloque = src.split("PHONES = [", 1)[1].split("]", 1)[0]
    return re.findall(r"n:\s*'([^']+)'.*?label:\s*'([^']+)'", bloque)


def test_lite_replica_la_lista_canonica():
    """La lista de lite.html debe ser la misma de PHONES, en el mismo orden.
    Si el modo liviano necesita una lista distinta (p. ej. sin SAMU), no se
    tolera en silencio: hay que cambiar esta prueba para comparar contra una
    lista explícita declarada aquí, con un comentario que explique por qué
    difiere, y actualizar lite.html a mano para que calce."""
    lite = _telefonos_lite()
    canon = _telefonos_canonicos()
    assert lite, "no se encontraron teléfonos en web/lite.html"
    assert canon, "no se encontró PHONES en web/js/ui.js"
    assert lite == canon, (
        "los teléfonos de web/lite.html no calzan con PHONES de web/js/ui.js: "
        f"lite={lite} · app={canon}. Copia la lista canónica en lite.html "
        "(es autocontenido por diseño) o corrige PHONES si el error está ahí."
    )


def _numeros_citados(src):
    """Números de emergencia citados en texto visible: enlaces tel: y frases
    como «llama al 130» o «(CONAF)». Solo formas de teléfono chileno
    (13X, *XXXX) para no confundir años ni cantidades con un teléfono."""
    citados = set(re.findall(r"tel:([^\"'<\\]+)", src))
    citados.update(re.findall(r"\bal\s+(\*?\d{3,4})\b", src))
    return {c for c in citados if re.fullmatch(r"\*?\d+", c)}


def test_numeros_citados_en_textos_estan_en_la_lista():
    """Todo número citado en las frases de emergencia de quehago.js y ui.js
    pertenece a la lista canónica. Si aparece un número nuevo, hay que
    agregarlo a PHONES en web/js/ui.js y a la lista de web/lite.html."""
    canon = {n for n, _ in _telefonos_canonicos()}
    quehago = QUEHAGO.read_text(encoding="utf-8")
    ui_sin_lista = UI.read_text(encoding="utf-8").split("phonesHtml", 1)[1]
    citados = _numeros_citados(quehago) | _numeros_citados(ui_sin_lista)
    fuera = sorted(citados - canon)
    assert not fuera, (
        f"números citados en los textos que no están en la lista: {fuera}. "
        "Agrégalos a PHONES en web/js/ui.js y a web/lite.html, o corrige "
        "el texto si el número está mal escrito."
    )


def _estados(src):
    """{clave: (label, title)} de un objeto `STATUS = {…}` de módulo JS."""
    bloque = src.split("STATUS = {", 1)[1].split("};", 1)[0]
    return {k: (label, title) for k, label, title in re.findall(r"(\w+):\s*\{\s*label:\s*'([^']+)',\s*title:\s*'([^']+)'", bloque)}


def test_textos_de_estado_salen_de_status_y_guidance():
    """lite.js copia a mano los textos de estado de la app (está autocontenido
    por diseño): cada label/title de su STATUS debe ser el de zona.js y cada
    línea de su GUIDANCE_FIRST la primera de GUIDANCE. Si la app cambia la
    redacción, /lite debe copiarla de nuevo; esta guarda lo pide."""
    lite = LITE_JS.read_text(encoding="utf-8")
    zona = ZONA.read_text(encoding="utf-8")
    estados_lite = _estados(lite)
    estados_app = _estados(zona)
    assert estados_lite, "no se encontró STATUS en lite.js"
    assert estados_app, "no se encontró STATUS en zona.js"
    assert estados_lite == estados_app, (
        f"los estados de lite.js no calzan con STATUS de zona.js: "
        f"lite={estados_lite} · app={estados_app}. Copia label/title a mano en lite.js."
    )
    guias_lite = dict(re.findall(
        r"(\w+):\s*'([^']+)'", lite.split("GUIDANCE_FIRST = {", 1)[1].split("};", 1)[0]))
    guias_app = dict(re.findall(
        r"(\w+):\s*\[\s*'([^']+)'", zona.split("GUIDANCE = {", 1)[1].split("};", 1)[0]))
    assert guias_lite, "no se encontró GUIDANCE_FIRST en lite.js"
    assert guias_lite == guias_app, (
        f"las primeras guías de lite.js no calzan con GUIDANCE de zona.js: "
        f"lite={guias_lite} · app={guias_app}. Copia la primera línea a mano en lite.js."
    )


def test_lite_abre_enlace_compartido():
    """MAPA-02: /lite entiende el enlace familiar (`/web/lite.html#/v/<token>` o
    `?v=<token>`), pide la API pública /api/shared/<token> sin tocar el token del
    dispositivo, y ante un enlace malo muestra «Este enlace ya no funciona» con
    Reintentar en vez de dejar la página en blanco."""
    js = LITE_JS.read_text(encoding="utf-8")
    plano = js.replace("\\/", "/")  # las expresiones JS escapan «/»; el texto queda legible
    html = LITE.read_text(encoding="utf-8")
    assert 'id="lite-shared"' in html, "lite.html no tiene el aviso de vista compartida"
    for marca in ("#/v/", ".get('v')", "/api/shared/", "auth: false",
                  "Este enlace ya no funciona", "Abrir en BRASA"):
        assert marca in plano, f"falta {marca!r} en lite.js (vista compartida MAPA-02)"
    assert "Este enlace ya no funciona" in plano and "Reintentar" in plano, (
        "el estado «enlace inválido» debe ofrecer Reintentar, no una página en blanco"
    )
    assert re.search(r"tel\('13[02]'\)", js), (
        "la tarjeta compartida debe citar los teléfonos de emergencia con tel()"
    )
