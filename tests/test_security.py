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
