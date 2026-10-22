"""Presupuesto del arranque (QA-62/UX-15): ninguna página secundaria arrastra
la aplicación completa. `scripts/local/peso_arranque.py` solo sigue los módulos
de `index.html`, así que un `app.js` colado en `datos.html`, `plan.html` o
`respuesta.html` suma peso sin mover ningún número. Esta guarda es la mitad que
faltaba: `tests/test_lite_page.py` ya fija la misma regla para `lite.html`."""

import re

from backend.settings import ROOT

# Página → su único módulo permitido (None: HTML estático, sin scripts).
# lista.html carga lista.js, que enlaza las casillas con el cálculo de
# lista-score.js; ambos están en el SHELL del service worker.
PAGINAS = {
    "datos.html": "datos.js",
    "plan.html": "plan.js",
    "respuesta.html": "respuesta.js",
    "lista.html": "lista.js",
    "admin.html": "admin.js",
}

# Cualquier ruta a un módulo bajo /web/js/ que la página mencione.
_RUTA_MODULO = re.compile(r"/web/js/[\w./-]+\.js")


def _modulos_de_pagina(html):
    """`src` locales bajo /web/js/ de cada <script type="module">."""
    refs = []
    for tag in re.findall(r"<script\b[^>]*>", html):
        if 'type="module"' not in tag:
            continue
        src = re.search(r'src=["\']([^"\']+)["\']', tag)
        if src and src.group(1).startswith("/web/js/"):
            refs.append(src.group(1))
    return refs


def _faltantes_pagina(html, modulo_propio):
    """Rutas bajo /web/js/ que la página no debería cargar: todas menos su
    módulo propio. Cubre el `src` de los <script type="module"> y los
    `import()` escritos dentro de la página, así que también veta `app.js`,
    `map.js`, `ui.js` y cualquier archivo de `web/js/views/`."""
    permitido = f"/web/js/{modulo_propio}" if modulo_propio else None
    return sorted({ruta for ruta in _RUTA_MODULO.findall(html) if ruta != permitido})


def test_paginas_solo_cargan_su_modulo():
    """Cada secundaria carga exactamente su módulo (que existe en disco) y ninguna
    otra ruta bajo /web/js/, ni en un `src` ni en un `import()`."""
    for pagina, propio in PAGINAS.items():
        html = (ROOT / "web" / pagina).read_text(encoding="utf-8")
        permitido = f"/web/js/{propio}" if propio else None
        cargados = set(_modulos_de_pagina(html))
        assert cargados <= ({permitido} if permitido else set()), (
            f"{pagina}: carga {sorted(cargados) or 'ningún módulo'}; solo puede cargar {permitido or 'ningún módulo'}"
        )
        if permitido:
            assert permitido in _RUTA_MODULO.findall(html), f"{pagina}: no referencia su módulo {permitido}"
            assert (ROOT / "web" / "js" / propio).is_file(), f"{pagina}: /web/js/{propio} no existe en disco"
        faltantes = _faltantes_pagina(html, propio)
        assert not faltantes, f"{pagina}: arrastra {', '.join(faltantes)}; solo puede cargar {permitido or 'ningún módulo'}"


def test_guarda_detecta_la_aplicacion_completa():
    """Un HTML de mentira que carga `app.js`, `map.js`, `ui.js` o una vista
    devuelve el módulo ofensor, venga del `src` del <script> o de un `import()`."""
    for ajeno in ("/web/js/app.js", "/web/js/map.js", "/web/js/ui.js", "/web/js/views/zona.js"):
        assert _faltantes_pagina(f'<script type="module" src="{ajeno}"></script>', "datos.js") == [ajeno]
    assert _faltantes_pagina('<script type="module">import("/web/js/app.js")</script>', "datos.js") == ["/web/js/app.js"]
