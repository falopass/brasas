"""PERF-CLS: la hoja del teléfono no puede animar ``height``.

La ``transition: height`` de ``.panel`` en ``@media (max-width: 899px)`` era el
origen de los saltos de composición medidos al cargar una vista (CLS 0,24–0,30
a 360 px): cada cuadro de la animación contaba como salto. Desde PERF-CLS la
caja queda fija en 94dvh y el estado la desliza con ``transform``, que el
observador de ``layout-shift`` no cuenta. Si ``.panel`` vuelve a declarar una
transición sobre ``height`` (o ``all``) dentro del bloque de teléfono, esta
prueba lo rompe antes del merge.
"""
from __future__ import annotations

import re

from backend.settings import ROOT
from tests.test_movil_tactiles import _reglas, _trozos_media_899


def test_panel_no_transiciona_height_en_telefono():
    css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
    dentro, _ = _trozos_media_899(css)
    for selector, cuerpo in _reglas(dentro):
        if ".panel" not in selector:
            continue
        for transicion in re.findall(r"transition(?:-[a-z-]+)?\s*:[^;]*", cuerpo):
            assert not re.search(r"(^|[,\s])height\b|:\s*all\b", transicion), (
                f"app.css: `{selector.strip()}` anima una propiedad de composición "
                f"en el teléfono ({transicion.strip()}): la hoja se mueve con transform (PERF-CLS)"
            )
