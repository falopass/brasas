"""La CSP del Worker de Cloudflare debe ser la misma que la del servidor (y con los hashes vigentes)."""
import re

from backend.security import CSP
from backend.settings import ROOT


def test_worker_csp_matches_backend_and_current_inline_scripts():
    worker = (ROOT / "deploy/cloudflare/src/index.ts").read_text(encoding="utf-8")
    match = re.search(r'const CSP = "([^"]+)";', worker)
    assert match, "El Worker no declara su CSP"
    assert match.group(1) == CSP, "Actualiza la CSP de deploy/cloudflare/src/index.ts (cambió un script en línea o la política)"


def test_pages_send_csp_and_frame_protection(make_client):
    with make_client() as client:
        for path in ("/", "/admin"):
            r = client.get(path)
            assert r.headers["content-security-policy"] == CSP
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
