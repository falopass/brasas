"""La CSP del Worker de Cloudflare debe ser la misma que la del servidor (y con los hashes vigentes)."""

import re

from backend.security import INLINE_SCRIPT_PAGES, content_security_policy, inline_script_hashes
from backend.settings import ROOT


def test_worker_csp_matches_backend_and_current_inline_scripts():
    """El Worker declara las dos políticas del backend: CSP (estricta, por defecto) y
    CSP_EVAL (la portada, única página que puede montar la vista 3D con Cesium)."""
    worker = (ROOT / "deploy/cloudflare/src/index.ts").read_text(encoding="utf-8")
    for name, path in (("CSP", "/admin"), ("CSP_EVAL", "/")):
        match = re.search(rf'const {name} = "([^"]+)";', worker)
        assert match, f"El Worker no declara su {name}"
        assert match.group(1) == content_security_policy(path), (
            f"Actualiza {name} de deploy/cloudflare/src/index.ts (cambió un script en línea o la política)"
        )


def test_worker_uses_the_eval_policy_only_for_the_portada():
    """SEC-51: en el borde, la política con 'unsafe-eval' no puede filtrarse a otras páginas.
    `assetPath` normaliza '/index.html' a '/', así que la portada es la única ruta con CSP_EVAL."""
    worker = (ROOT / "deploy/cloudflare/src/index.ts").read_text(encoding="utf-8")
    assert "securityHeaders(path, path === '/' ? CSP_EVAL : CSP)" in worker, "serveAsset debe elegir CSP_EVAL solo para la portada"


_JS_TYPES = {"text/javascript", "application/javascript", "module"}


def _inline_script_bodies(html: str) -> list[str]:
    """Cuerpos de <script> en línea ejecutables (sin src y sin type no-JS como ld+json)."""
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    bodies = []
    for tag, body in re.findall(r"(<script\b[^>]*>)(.*?)</script>", html, re.S | re.I):
        if re.search(r"(?<![-\w])src\s*=", tag, re.I):
            continue
        type_attr = re.search(r"(?<![-\w])type\s*=\s*[\"']?([^\"'>\s]+)", tag, re.I)
        if type_attr and type_attr.group(1).lower() not in _JS_TYPES:
            continue
        bodies.append(body)
    return bodies


def test_every_inline_script_page_is_declared_in_csp():
    """DEBT-03: ninguna página con <script> en línea sin declararlo en la CSP.

    Caso real que motiva la guarda: una página nueva (o una existente que agregue
    un `<script>` sin `src`) vería su script bloqueado por la CSP en producción y
    el fallo se descubriría recién en el navegador. Quien agregue un script en
    línea debe decidir: declarar la página en `INLINE_SCRIPT_PAGES` (y el hash en
    la CSP de `backend/security.py` y la del Worker) o mover el script a un `.js`.

    Verificado: falla al agregar `<script>console.log(1)</script>` a
    `web/lista.html` y vuelve a verde al revertirlo.
    """
    declared = {str(page) for page in INLINE_SCRIPT_PAGES}
    total_declared_scripts = 0
    for page in sorted((ROOT / "web").glob("*.html")):
        bodies = _inline_script_bodies(page.read_text(encoding="utf-8"))
        if not bodies:
            continue
        rel = page.relative_to(ROOT).as_posix()
        assert rel in declared, (
            f"{rel} tiene {len(bodies)} <script> en línea sin declarar en la CSP: "
            "agrégala a INLINE_SCRIPT_PAGES en backend/security.py (y su hash a la CSP "
            "del backend y del Worker en deploy/cloudflare/src/index.ts) o mueve el script a un .js"
        )
        total_declared_scripts += len(bodies)
    assert len(inline_script_hashes()) == total_declared_scripts, (
        "inline_script_hashes() debe cubrir todos los scripts en línea declarados (su regex solo acepta `<script>` sin atributos)"
    )


def test_pages_send_csp_and_frame_protection(make_client):
    with make_client() as client:
        portada = client.get("/")
        csp_portada = portada.headers["content-security-policy"]
        assert csp_portada == content_security_policy("/")
        assert "'unsafe-eval'" in csp_portada  # la vista 3D (Cesium/Knockout) lo necesita
        for path in ("/admin", "/datos.html", "/robots.txt"):
            r = client.get(path)
            csp = r.headers["content-security-policy"]
            assert csp == content_security_policy(path)
            assert "unsafe-eval" not in csp  # solo la portada evalúa código
            assert r.headers["x-frame-options"] == "SAMEORIGIN"
        assert "Disallow: /api/" in client.get("/robots.txt").text


def test_dockerfile_forwarded_allow_ips_comes_from_env():
    """FIX-20: el contenedor no debe fijar `--forwarded-allow-ips "*"` literal.

    El valor por defecto sigue siendo `*` (en Cloudflare solo el Worker llega al
    contenedor), pero tiene que salir de FORWARDED_ALLOW_IPS: en un VPS sin proxy,
    un `*` fijo dejaría falsificar X-Forwarded-For y saltarse el limitador por IP.
    """
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "FORWARDED_ALLOW_IPS" in dockerfile, "El CMD debe leer FORWARDED_ALLOW_IPS"
    assert re.search(r"FORWARDED_ALLOW_IPS:?-\*", dockerfile), "El valor por defecto debe seguir siendo *"
    assert '"*"' not in dockerfile, 'No fijes --forwarded-allow-ips "*"; usa ${FORWARDED_ALLOW_IPS-*}'
