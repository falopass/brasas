"""OPS-01/QA-08: la sonda de producción (scripts/local/smoke_produccion.py) sin red.

El opener falso imita a urllib.request.urlopen, devuelve respuestas por URL y registra cada
Request: así se comprueban los veredictos y que la sonda solo haga peticiones GET.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "local" / "smoke_produccion.py"
_spec = importlib.util.spec_from_file_location("smoke_produccion", _SCRIPT)
smoke = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = smoke  # dataclasses busca el módulo para resolver sus tipos
_spec.loader.exec_module(smoke)

BASE = "https://ejemplo.test"
STATUS_URL = BASE + "/api/status"
OBSERVACIONES_URL = BASE + "/api/observations?bbox=-75,-56,-66,-17"


class Respuesta:
    """Lo mínimo que usa la sonda de una respuesta de urllib."""

    def __init__(self, body: bytes = b"", status: int = 200, content_type: str = "application/json"):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = body

    def read(self, n: int = -1) -> bytes:
        return self._body if n < 0 else self._body[:n]

    def __enter__(self) -> Respuesta:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class OpenerFalso:
    def __init__(self, respuestas: dict[str, Respuesta | Exception]):
        self.respuestas = respuestas
        self.peticiones: list[urllib.request.Request] = []

    def __call__(self, req: urllib.request.Request, timeout: int) -> Respuesta:
        self.peticiones.append(req)
        respuesta = self.respuestas[req.full_url]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class Reloj:
    """Reloj de mentira: cada llamada devuelve el siguiente valor de la lista."""

    def __init__(self, valores: list[float]):
        self.valores = valores
        self.i = 0

    def __call__(self) -> float:
        valor = self.valores[min(self.i, len(self.valores) - 1)]
        self.i += 1
        return valor


def respuestas_ok() -> dict[str, Respuesta | Exception]:
    status = {
        "time_utc": "2026-10-20T17:40:51Z",
        "last_ingest_at": "2026-10-20T17:40:51Z",
        "freshness": {"last_ingest_at": "2026-10-20T17:40:51Z", "age_seconds": 78, "stale_after_s": 1800, "stale": False},
        "failures_24h": {},
    }
    return {
        BASE + "/": Respuesta(b"<!doctype html><title>BRASA</title>", content_type="text/html; charset=utf-8"),
        BASE + "/web/js/app.js": Respuesta(b"console.log('brasa');", content_type="text/javascript"),
        BASE + "/manifest.webmanifest": Respuesta(b'{"name":"BRASA"}', content_type="application/manifest+json"),
        STATUS_URL: Respuesta(json.dumps(status).encode(), content_type="application/json"),
        OBSERVACIONES_URL: Respuesta(json.dumps({"points": [{"id": "x"}]}).encode(), content_type="application/json"),
        BASE + "/api/incidents": Respuesta(json.dumps({"incidents": []}).encode(), content_type="application/json"),
        BASE + "/api/panorama": Respuesta(json.dumps({"type": "panorama"}).encode(), content_type="application/json"),
        BASE + "/web/sitemap.xml": Respuesta(b'<?xml version="1.0"?><urlset/>', content_type="application/xml"),
    }


def correr(
    respuestas: dict[str, Respuesta | Exception] | None = None,
    reloj: Reloj | None = None,
    extra: tuple[str, ...] = (),
) -> tuple[int, OpenerFalso]:
    opener = OpenerFalso(respuestas if respuestas is not None else respuestas_ok())
    codigo = smoke.main(["--url", BASE, *extra], opener=opener, reloj=reloj or (lambda: 0.0))
    return codigo, opener


def cambiar_status(respuestas: dict[str, Respuesta | Exception], cambio: dict) -> None:
    status = json.loads(respuestas[STATUS_URL]._body)  # type: ignore[union-attr]
    status.update(cambio)
    respuestas[STATUS_URL] = Respuesta(json.dumps(status).encode(), content_type="application/json")


def test_todo_en_verde(capsys):
    codigo, _ = correr()
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "RESULTADO: todo en verde" in salida
    assert "ERROR" not in salida and "LENTA" not in salida


def test_502_en_incidents(capsys):
    respuestas = respuestas_ok()
    respuestas[BASE + "/api/incidents"] = Respuesta(status=502, body=b"")
    codigo, _ = correr(respuestas)
    salida = capsys.readouterr().out
    assert codigo == 1
    assert "/api/incidents responde HTTP 502" in salida
    assert "Arreglo:" in salida
    assert "RESULTADO:" in salida and "1 problema" in salida


def test_datos_estancados(capsys):
    respuestas = respuestas_ok()
    cambiar_status(respuestas, {"freshness": {"age_seconds": 2700, "stale_after_s": 1800, "stale": True}})
    codigo, _ = correr(respuestas)
    salida = capsys.readouterr().out
    assert codigo == 1
    assert "datos de hace 45 min" in salida
    assert "workflow monitoreo" in salida


def test_respuesta_lenta(capsys):
    # El primer sondeo es "/": el reloj marca 0 al empezar y 3 s al terminar; el resto, 0 ms.
    reloj = Reloj([0.0, 3.0] + [10.0, 10.0] * 10)
    codigo, _ = correr(reloj=reloj)
    salida = capsys.readouterr().out
    assert codigo == 1
    assert "LENTA" in salida
    assert "3000 ms" in salida


def test_solo_hace_get(capsys):
    codigo, opener = correr()
    assert codigo == 0
    assert len(opener.peticiones) == 8
    assert all(p.get_method() == "GET" for p in opener.peticiones)
    assert all(p.data is None for p in opener.peticiones)


def test_fallo_de_producto_sin_impacto_no_alerta(capsys):
    respuestas = respuestas_ok()
    cambiar_status(respuestas, {"failures_24h": {"CONAF_CONDICIONES": {"runs": 3, "failed": 3, "last_error": "timeout"}}})
    codigo, _ = correr(respuestas)
    assert codigo == 0
    assert "RESULTADO: todo en verde" in capsys.readouterr().out


def test_fallo_de_producto_con_impacto_alerta(capsys):
    respuestas = respuestas_ok()
    cambiar_status(respuestas, {"failures_24h": {"GOES19_FDCF": {"runs": 4, "failed": 2, "last_error": "HTTP 500"}}})
    codigo, _ = correr(respuestas)
    salida = capsys.readouterr().out
    assert codigo == 1
    assert "GOES19_FDCF" in salida
    assert "2 de 4" in salida


def test_red_caida(capsys):
    respuestas = respuestas_ok()
    respuestas[BASE + "/"] = urllib.error.URLError("sin ruta al host")
    codigo, _ = correr(respuestas)
    salida = capsys.readouterr().out
    assert codigo == 1
    assert "/ no responde (sin respuesta (URLError))" in salida


def test_salida_json(capsys):
    codigo, _ = correr(extra=("--json",))
    data = json.loads(capsys.readouterr().out)
    assert codigo == 0
    assert data["ok"] is True
    assert data["resultado"] == "todo en verde"
    assert len(data["sondas"]) == 8
    assert data["problemas"] == []
