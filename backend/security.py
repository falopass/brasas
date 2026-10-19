"""Política de seguridad de contenido (CSP) de las páginas de BRASA.

La misma política la envía el Worker de Cloudflare (deploy/cloudflare/src/index.ts); tests/test_security.py
exige que ambas coincidan y que los hashes de los scripts en línea correspondan al HTML actual.
- Scripts: solo los propios, los dos scripts en línea por hash, Cesium (vista 3D) desde jsDelivr
  y el antibot Turnstile de Cloudflare (su widget abre un iframe del mismo origen → frame-src).
- Datos e imágenes: cualquier origen https (teselas de mapa base, satélite, relieve y Cesium ion).
- 'unsafe-eval' solo porque Cesium (Knockout, en sus controles) evalúa texto como código; sin él la vista 3D
  no abre. Lo que más importa contra XSS sigue cerrado: no se ejecuta ningún script en línea ni de otro origen.
"""

from __future__ import annotations

import base64
import hashlib
import re

from backend.settings import ROOT

INLINE_SCRIPT_PAGES = ("web/index.html", "web/admin.html")


def inline_script_hashes() -> list[str]:
    hashes = []
    for page in INLINE_SCRIPT_PAGES:
        html = (ROOT / page).read_text(encoding="utf-8")
        for body in re.findall(r"<script>(.*?)</script>", html, re.S):
            hashes.append("'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'")
    return hashes


def content_security_policy() -> str:
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self' "
            + " ".join(inline_script_hashes())
            + " https://cdn.jsdelivr.net https://challenges.cloudflare.com 'unsafe-eval' 'wasm-unsafe-eval'",
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


def embed_policy() -> str:
    """CSP de la página embebible (/embed?comuna=…), pensada para que un municipio
    la enmarque en su propia web con un iframe.

    Es deliberadamente mínima (la página no usa fuentes, imágenes externas ni
    formularios) y abierta a ser enmarcada: solo muestra datos públicos de una
    comuna, igual que la pantalla pública (web/pantalla.html). En esa ruta no se
    envía X-Frame-Options (no admite lista de dominios y ALLOW-FROM murió): quién
    puede enmarcarla lo decide frame-ancestors. Para limitarla a municipios
    pactados, cambiar `*` por la lista de orígenes (p. ej. https://municipalidad.cl)."""
    return "; ".join(
        [
            "default-src 'none'",
            "script-src 'self'",
            "style-src 'unsafe-inline'",
            "img-src 'self' data:",
            "connect-src 'self'",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors *",
        ]
    )


CSP = content_security_policy()
EMBED_CSP = embed_policy()
