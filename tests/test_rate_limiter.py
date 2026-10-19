"""FIX-34: el limitador en memoria poda las IPs que no vuelven, sin cambiar el cupo."""
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routes.common import RateLimiter


def _request(ip: str):
    return SimpleNamespace(client=SimpleNamespace(host=ip))


def test_check_counts_and_blocks_with_retry_after():
    rl = RateLimiter()
    req = _request("203.0.113.7")
    for _ in range(3):
        rl.check(req, "reports", 3, 60)
    with pytest.raises(HTTPException) as exc:
        rl.check(req, "reports", 3, 60)
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 0
    assert exc.value.detail["code"] == "RATE_LIMITED"


def test_stale_ips_are_swept_and_limited_ip_stays_limited():
    rl = RateLimiter()
    bad = _request("198.51.100.9")
    rl.check(bad, "reports", 2, 3600)
    rl.check(bad, "reports", 2, 3600)  # cupo lleno: la próxima debe dar 429

    # 6.000 IPs distintas con marcas ya vencidas (no vuelven dentro de la ventana).
    stale = time.monotonic() - 3700
    for i in range(6_000):
        rl.hits[("reports", f"192.0.{i // 256}.{i % 256}")].append(stale)
    before = len(rl.hits)

    # La primera comprobación con len(hits) > _SWEEP_OVER dispara la poda.
    for i in range(200):
        rl.check(_request(f"203.0.113.{i}"), "reports", 5, 3600)

    after = len(rl.hits)
    assert after < 1_000, f"la poda no acotó el diccionario ({before} -> {after})"

    # La IP limitada antes de la poda sigue limitada dentro de su ventana.
    with pytest.raises(HTTPException) as exc:
        rl.check(bad, "reports", 2, 3600)
    assert exc.value.status_code == 429
