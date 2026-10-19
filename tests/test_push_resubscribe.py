"""Resincronización de la suscripción push: cuando el navegador rota la suscripción,
el service worker la guarda en la caché y la app la reenvía a /api/push/subscribe
(un UPDATE idempotente por dispositivo). Sin esto, la suscripción se pierde en
silencio cuando el servidor la borra tras un 404/410 del servicio de push.
"""
from backend.settings import ROOT

SW = (ROOT / "web" / "sw.js").read_text(encoding="utf-8")
PUSH = (ROOT / "web" / "js" / "push.js").read_text(encoding="utf-8")


def test_sw_escucha_pushsubscriptionchange_y_resuscribe():
    assert "addEventListener('pushsubscriptionchange'" in SW
    body = SW.split("addEventListener('pushsubscriptionchange'", 1)[1]
    assert "pushManager.subscribe" in body
    assert "/api/config" in body
    assert "waitUntil" in body


def test_sw_guarda_la_suscripcion_y_avisa_a_las_ventanas():
    assert "brasa-push-pending" in SW
    assert "postMessage" in SW
    assert "matchAll" in SW


def test_pushjs_reenvia_la_suscripcion_al_servidor():
    assert "brasa:push-resubscribed" in PUSH
    assert "brasa-push-pending" in PUSH
    assert "api.pushSubscribe" in PUSH


def test_sw_no_cachea_api_push():
    # Las llamadas push llevan el token del dispositivo: nunca deben quedar en la caché del SW.
    assert "/api/push" not in SW
