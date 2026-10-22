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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "local" / "smoke_produccion.py"
_spec = importlib.util.spec_from_file_location("smoke_produccion", _SCRIPT)
smoke = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = smoke  # dataclasses busca el módulo para resolver sus tipos
_spec.loader.exec_module(smoke)

BASE = "https://ejemplo.test"
HEALTH_URL = BASE + "/api/health"
STATUS_URL = BASE + "/api/status"
OBSERVACIONES_URL = BASE + "/api/observations?bbox=-75,-56,-66,-17"
INCIDENTES_URL = BASE + "/api/incidents"
INC_ID = "d8e9c96cac20"
COMPARTIR_URL = BASE + f"/i/{INC_ID}"
TARJETA_URL = BASE + f"/og/incident/{INC_ID}.png"


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
        # Recién calculado: la sonda marca un risk_computed_at ausente o estancado (OPS-42).
        "risk_computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # La versión publicada sale del propio repo para que la prueba siga en verde al subir de versión.
    health = {"status": "ok", "name": "BRASA Chile", "version": smoke.version_repo(), "time_utc": "2026-10-20T17:40:51Z"}
    return {
        BASE + "/": Respuesta(b"<!doctype html><title>BRASA</title>", content_type="text/html; charset=utf-8"),
        BASE + "/web/js/app.js": Respuesta(b"console.log('brasa');", content_type="text/javascript"),
        BASE + "/manifest.webmanifest": Respuesta(b'{"name":"BRASA"}', content_type="application/manifest+json"),
        BASE + "/web/lite.html": Respuesta(b"<!doctype html><title>BRASA liviana</title>", content_type="text/html; charset=utf-8"),
        HEALTH_URL: Respuesta(json.dumps(health).encode(), content_type="application/json"),
        STATUS_URL: Respuesta(json.dumps(status).encode(), content_type="application/json"),
        OBSERVACIONES_URL: Respuesta(json.dumps({"points": [{"id": "x"}]}).encode(), content_type="application/json"),
        INCIDENTES_URL: Respuesta(
            json.dumps({"incidents": [{"id": INC_ID, "lat": -33.5, "lon": -70.8, "comuna": "Santiago"}]}).encode(),
            content_type="application/json",
        ),
        BASE + "/api/panorama": Respuesta(json.dumps({"type": "panorama"}).encode(), content_type="application/json"),
        BASE + "/web/sitemap.xml": Respuesta(b'<?xml version="1.0"?><urlset/>', content_type="application/xml"),
        COMPARTIR_URL: Respuesta(
            b"<!doctype html><html><head>"
            b'<meta property="og:title" content="BRASA">'
            b'<meta property="og:image" content="x.png"></head><body></body></html>',
            content_type="text/html; charset=utf-8",
        ),
        TARJETA_URL: Respuesta(b"\x89PNG\r\n\x1a\nfake", content_type="image/png"),
    }


def cambiar_incidentes(respuestas: dict[str, Respuesta | Exception], incidentes: list[dict]) -> None:
    respuestas[INCIDENTES_URL] = Respuesta(json.dumps({"incidents": incidentes}).encode(), content_type="application/json")


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


def cambiar_version(respuestas: dict[str, Respuesta | Exception], version: str) -> None:
    health = json.loads(respuestas[HEALTH_URL]._body)  # type: ignore[union-attr]
    health["version"] = version
    respuestas[HEALTH_URL] = Respuesta(json.dumps(health).encode(), content_type="application/json")


def test_todo_en_verde(capsys):
    codigo, _ = correr()
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "RESULTADO: todo en verde" in salida
    assert f"versión: publicada {smoke.version_repo()} · repo {smoke.version_repo()}" in salida
    assert "más lenta:" in salida
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


@pytest.mark.parametrize(
    "extra, codigo_esperado",
    [((), 1), (("--sin-version",), 0)],
    ids=["desfasada", "ignorada-con-flag"],
)
def test_version_publicada(capsys, extra, codigo_esperado):
    respuestas = respuestas_ok()
    cambiar_version(respuestas, "0.8.0")
    codigo, _ = correr(respuestas, extra=extra)
    salida = capsys.readouterr().out
    assert codigo == codigo_esperado
    if codigo_esperado:
        assert f"producción publica 0.8.0 y el repositorio dice {smoke.version_repo()}" in salida
        assert "vuelve a desplegar y confirma el commit del Worker" in salida
    else:
        assert "versión:" not in salida


def test_solo_hace_get(capsys):
    codigo, opener = correr()
    assert codigo == 0
    assert len(opener.peticiones) == 12
    assert all(p.get_method() == "GET" for p in opener.peticiones)
    assert all(p.data is None for p in opener.peticiones)


@pytest.mark.parametrize(
    "cambio, esperados",
    [
        pytest.param(
            {"last_cycle": {"backup": False, "backup_error": "HTTP 500 /_internal/storage/db/work.db.gz"}},
            ("last_cycle.backup=false", "work.db.gz"),
            id="respaldo",
        ),
        pytest.param(
            {"last_cycle": {"backup": True, "work_backup": False, "backup_error": "HTTP 500"}},
            ("work_backup=false",),
            id="respaldo-de-trabajo",
        ),
        pytest.param(
            {"last_cycle": {"backup": True, "work_backup": True, "risk_error": "HTTP 429 de Open-Meteo"}},
            ("risk_error", "HTTP 429"),
            id="error-del-ciclo",
        ),
        pytest.param(
            {"risk_computed_at": (datetime.now(timezone.utc) - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            ("peligro", "7 h"),
            id="riesgo-estancado",
        ),
        pytest.param({"risk_computed_at": None}, ("risk_computed_at",), id="riesgo-sin-marca"),
    ],
)
def test_fallos_de_estado_alertan(capsys, cambio, esperados):
    """OPS-42: backup/work_backup/risk_error y un riesgo estancado o sin marca son problemas reales."""
    respuestas = respuestas_ok()
    cambiar_status(respuestas, cambio)
    codigo, _ = correr(respuestas)
    salida = capsys.readouterr().out
    assert codigo == 1
    for esperado in esperados:
        assert esperado in salida


@pytest.mark.parametrize(
    "cambio",
    [
        pytest.param({"failures_24h": {"CONAF_CONDICIONES": {"runs": 3, "failed": 3, "last_error": "timeout"}}}, id="producto"),
        pytest.param({"last_cycle": {"conaf_cond_error": "timeout"}}, id="ciclo"),
    ],
)
def test_fallo_sin_impacto_no_alerta(capsys, cambio):
    """Las condiciones de CONAF son contexto: su caída no cambia lo que ve el vecino."""
    respuestas = respuestas_ok()
    cambiar_status(respuestas, cambio)
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


@pytest.mark.parametrize(
    "respuesta, esperado",
    [
        pytest.param(Respuesta(status=404, body=b"", content_type="text/plain"), f"/i/{INC_ID} responde HTTP 404", id="404"),
        pytest.param(Respuesta(b"<!doctype html><html><head></head></html>", content_type="text/html"), "og:title", id="sin-og"),
    ],
)
def test_enlace_compartir_roto(capsys, respuesta, esperado):
    """OPS-35: si /i/<id> deja de responder 200 o pierde sus etiquetas og, el enlace de WhatsApp queda muerto."""
    respuestas = respuestas_ok()
    respuestas[COMPARTIR_URL] = respuesta
    codigo, _ = correr(respuestas)
    salida = capsys.readouterr().out
    assert codigo == 1
    assert esperado in salida


def test_sin_incidentes_omite_compartir(capsys):
    """Sin incidentes abiertos no hay id que sondear: /i/ y /og/ se saltan sin reclamar."""
    respuestas = respuestas_ok()
    cambiar_incidentes(respuestas, [])
    codigo, opener = correr(respuestas)
    salida = capsys.readouterr().out
    assert codigo == 0
    assert len(opener.peticiones) == 10
    assert "/i/" not in salida


def test_incidente_fuera_de_chile(capsys):
    """SONDA-01: un incidente publicado fuera del territorio se marca con id y coordenadas."""
    respuestas = respuestas_ok()
    cambiar_incidentes(
        respuestas,
        [
            {"id": INC_ID, "lat": -33.5, "lon": -70.8},
            {"id": "aaaa1111bbbb", "lat": -36.8, "lon": -73.05},
            {"id": "cccc2222dddd", "lat": -25.02, "lon": -66.19},
        ],
    )
    codigo, _ = correr(respuestas)
    salida = capsys.readouterr().out
    assert codigo == 1
    assert "1 incidente fuera de Chile" in salida
    assert "cccc2222dddd" in salida


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
    repo = smoke.version_repo()
    assert codigo == 0
    assert data["ok"] is True
    assert data["resultado"] == "todo en verde"
    assert len(data["sondas"]) == 12
    assert data["mas_lenta"]["ms"] >= 0 and data["mas_lenta"]["ruta"]
    assert data["version"] == {"publicada": repo, "repo": repo, "coincide": True}
    assert data["problemas"] == []
