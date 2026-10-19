"""Paridad del modo liviano (QA-41): `web/lite.html` es autocontenido por diseño,
así que su lista de teléfonos de emergencia está copiada a mano de `PHONES` en
`web/js/ui.js`. Un número mal copiado en una emergencia es el peor error posible:
estas guardas hacen que cualquier desincronización rompa el CI.

Si falla la comparación por un número editado a mano en lite.html (cambio de
prueba revertido antes de entregar), el mensaje dice qué archivo corregir."""
import re

from backend.settings import ROOT

LITE = ROOT / "web" / "lite.html"
UI = ROOT / "web" / "js" / "ui.js"
QUEHAGO = ROOT / "web" / "js" / "views" / "quehago.js"


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


def test_lite_no_carga_recursos_externos():
    """El modo liviano sigue autocontenido: mismo criterio de
    `test_autocontenidas_sin_terceros` en test_estaticas_guardas.py — ninguna
    referencia a otro host salvo los <a href>, que no descarga el navegador."""
    html = LITE.read_text(encoding="utf-8")
    for tag, attr, ref in re.findall(
        r"<(\w+)[^>]*?\b(src|href|action)\s*=\s*[\"']([^\"']+)", html
    ):
        if tag.lower() == "a":
            continue
        assert not re.match(
            r"(?:https?:)?//", ref
        ), f"lite.html: host externo {ref}"
