"""Política de seguridad de contenido (CSP) de las páginas de BRASA.

La misma política la envía el Worker de Cloudflare (deploy/cloudflare/src/index.ts); tests/test_security.py
exige que ambas coincidan y que los hashes de los scripts en línea correspondan al HTML actual.
- Scripts: solo los propios, los scripts en línea por hash, Cesium (vista 3D) desde jsDelivr
  y el antibot Turnstile de Cloudflare (su widget abre un iframe del mismo origen → frame-src).
- Datos e imágenes: cualquier origen https (teselas de mapa base, satélite, relieve y Cesium ion).
- 'unsafe-eval' solo porque Cesium (Knockout, en sus controles) evalúa texto como código; sin él la vista 3D
  no abre. La vista 3D corre dentro de la portada (index.html la carga bajo demanda desde la vista Historia),
  así que solo las rutas que sirven esa página la llevan; el resto va sin evaluación de código.
  Lo que más importa contra XSS sigue cerrado: no se ejecuta ningún script en línea ni de otro origen.
"""

from __future__ import annotations

import base64
import hashlib
import re

from backend.settings import ROOT

INLINE_SCRIPT_PAGES = ("web/index.html", "web/admin.html", "web/lista.html")

_JS_TYPES = {"text/javascript", "application/javascript", "module"}
# Rutas que sirven index.html, la única página que puede montar la vista 3D con Cesium.
EVAL_PATHS = frozenset({"/", "/index.html"})


def inline_script_hashes() -> list[str]:
    """Hashes sha256 de los <script> en línea ejecutables (sin src ni type no-JS como ld+json)."""
    hashes = []
    for page in INLINE_SCRIPT_PAGES:
        html = re.sub(r"<!--.*?-->", "", (ROOT / page).read_text(encoding="utf-8"), flags=re.S)
        for tag, body in re.findall(r"(<script\b[^>]*>)(.*?)</script>", html, re.S | re.I):
            if re.search(r"(?<![-\w])src\s*=", tag, re.I):
                continue
            type_attr = re.search(r"(?<![-\w])type\s*=\s*[\"']?([^\"'>\s]+)", tag, re.I)
            if type_attr and type_attr.group(1).lower() not in _JS_TYPES:
                continue
            hashes.append("'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'")
    return hashes


def _build_policy(with_eval: bool) -> str:
    script_src = "script-src 'self' " + " ".join(inline_script_hashes()) + " https://cdn.jsdelivr.net https://challenges.cloudflare.com"
    if with_eval:
        script_src += " 'unsafe-eval' 'wasm-unsafe-eval'"
    return "; ".join(
        [
            "default-src 'self'",
            script_src,
            "worker-src 'self' blob:",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "img-src 'self' data: blob: https:",
            "font-src 'self' data: https://cdn.jsdelivr.net",
            "connect-src 'self' https:",
            "manifest-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-src https://challenges.cloudflare.com",
            "frame-ancestors 'self'",
        ]
    )


CSP = _build_policy(False)
CSP_EVAL = _build_policy(True)


def content_security_policy(path: str) -> str:
    """La CSP para `path`: 'unsafe-eval' solo donde la portada puede abrir la vista 3D."""
    return CSP_EVAL if path in EVAL_PATHS else CSP
