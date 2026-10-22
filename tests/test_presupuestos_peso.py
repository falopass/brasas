"""QA-46 — presupuesto de peso del arranque y de las respuestas públicas.

Nadie vigilaba cuánto pesa el shell que precachea el service worker ni el JSON de
las rutas calientes: una capa nueva de 300 KB o un SELECT de más llegaban a
producción sin aviso. Estas pruebas fijan un techo con holgura sobre lo medido hoy
(QA-46, 2026-10-19) para que el CI avise cuando el peso crece. El presupuesto de
`web/data` ya lo cubre `tests/test_data_files.py` (QA-43); aquí no se repite.
QA-88 suma los topes de `/api/incidents` y de la ficha de un incidente.
"""

import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import incidents
from backend.geo import haversine_km
from tests.test_incidents_props import insert_obs

ROOT = Path(__file__).resolve().parent.parent
SW = ROOT / "web" / "sw.js"

# Medido el 2026-10-22 sobre main ya rebasado (FUEGO-26 suma escenario.js al
# precache): 1 759 803 B de .js/.css en SHELL. MAPA-21 suma buscador.js (1,8 KB)
# al precache y entra en el +10 % sin mover la medida ni el techo.
# Ya excede lo razonable para bajar en la calle con un celular, así que el techo
# queda en +10 % (no +20 %) hasta que OPS-06 aliviane el arranque.
SHELL_HOY_B = 1_759_803
SHELL_TECHO_B = int(SHELL_HOY_B * 1.10)  # TODO(OPS-06): el arranque pesa 1,5 MB; bajarlo y volver a +20 %

# Medido el 2026-10-19 con la carga realista de abajo (~2 000 detecciones,
# ~200 incidentes abiertos); techo = medido + 25 %.
RESPUESTAS_HOY_B = {
    "/api/incidents": 96_377,
    "/api/observations?bbox=-76,-56,-66,-17&hours=48": 961_210,
    # AUTO-17: +`errors.desfase` (edad del ciclo, edad de cada fuente, texto y qué hacer).
    # DET-51: +`fixed_source_24h` (auditoría de las fuentes fijas).
    # Medido el 2026-10-21 con la misma carga: 1 280 B.
    "/api/status": 1_280,
}

# Medido el 2026-10-20 (QA-88) sobre `main` con `make_client` y la carga que
# describe cada prueba; techo = medido + 25 %, la holgura del resto del archivo.
INCIDENTS_VACIO_HOY_B = 161
INCIDENTS_UNO_HOY_B = 565
INCIDENTS_HULLS_HOY_B = 680
INCIDENTE_DETALLE_HOY_B = 5_204

_DESFASES = ((0.0, 0.0), (0.001, 0.001), (-0.001, 0.001), (0.001, -0.001), (-0.001, -0.001))


def _rutas_precache():
    bloque = SW.read_text(encoding="utf-8").split("SHELL = [", 1)[1].split("]", 1)[0]
    return re.findall(r"'([^']+)'", bloque)


def test_shell_del_service_worker_dentro_del_presupuesto():
    """El service worker baja SHELL entero en la instalación, en la calle:
    cada KB nuevo de JS/CSS se paga ahí, antes de ver un solo dato."""
    total = 0
    for ruta in _rutas_precache():
        # Solo JS y CSS: web/data tiene su propio presupuesto (QA-43) y las
        # fuentes e íconos no cambian con el código de la app.
        if not ruta.endswith((".js", ".css")):
            continue
        archivo = ROOT / ruta.lstrip("/")
        if archivo.is_file():
            # Las rutas declaradas pero aún pendientes (hoy /web/js/enso.js,
            # RISK-18) las cubre tests/test_estaticas_guardas.py.
            total += archivo.stat().st_size
    assert total <= SHELL_TECHO_B, (
        f"el shell pesa {total} B (hoy {SHELL_HOY_B} B, techo {SHELL_TECHO_B} B = +10 %): "
        "el service worker lo baja en la instalación, en la calle"
    )


def _sembrar_carga_realista(db) -> None:
    """~2 000 detecciones en ~200 focos a ≥ 15 km entre sí, en 10 tandas de
    10 min (mismo patrón que tests/test_incidents_perf.py)."""
    rng = random.Random(20261019)
    centers: list[tuple[float, float]] = []
    while len(centers) < 200:
        cand = (rng.uniform(-38.0, -33.0), rng.uniform(-73.5, -70.0))
        if all(haversine_km(cand[0], cand[1], c[0], c[1]) >= 15 for c in centers):
            centers.append(cand)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    batch = []
    for i in range(2000):
        lat = centers[i % 200][0] + rng.gauss(0, 0.002)
        lon = centers[i % 200][1] + rng.gauss(0, 0.002)
        at = (now - timedelta(minutes=(i // 200) * 10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = {
            "id": f"p{i}",
            "source": "gen",
            "sensor": "ABI",
            "satellite": "GOES",
            "resolution_m": 2000,
            "lat": lat,
            "lon": lon,
            "observed_at": at,
            "frp_mw": 8.0,
            "confidence": "alta",
            "comuna_code": 13101,
        }
        insert_obs(db, row)
        batch.append(row)
    incidents.update(db, batch, now)


def test_respuestas_publicas_dentro_del_presupuesto(make_client):
    with make_client() as client:
        _sembrar_carga_realista(client.app.state.services.db)
        for ruta, hoy in RESPUESTAS_HOY_B.items():
            response = client.get(ruta)
            assert response.status_code == 200, ruta
            techo = int(hoy * 1.25)
            assert len(response.content) <= techo, (
                f"{ruta} pesa {len(response.content)} B (hoy {hoy} B, techo {techo} B = +25 %): "
                "es de las rutas que más se piden desde la calle con señal mala"
            )


def _comprobar_peso(ruta: str, response, hoy_b: int) -> None:
    techo = int(hoy_b * 1.25)
    assert len(response.content) <= techo, (
        f"{ruta} pesa {len(response.content)} B (hoy {hoy_b} B, techo {techo} B = +25 %): "
        "recorta campos antes de subir el tope; si el aumento se justifica, explícalo en el CHANGELOG"
    )


def _sembrar_incidente(db, ahora: datetime, n: int) -> dict:
    """`n` detecciones VIIRS en un mismo foco, repartidas en 3 h (la última, ahora)."""
    filas = []
    for i, (dlat, dlon) in enumerate(_DESFASES[:n]):
        row = {
            "id": f"qa88-{i}",
            "source": "firms",
            "sensor": "VIIRS",
            "satellite": "N20",
            "resolution_m": 375,
            "lat": -33.5 + dlat,
            "lon": -70.8 + dlon,
            "observed_at": (ahora - timedelta(minutes=45 * (n - 1 - i))).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "frp_mw": 12.0,
            "confidence": "nominal",
            "comuna_code": 13101,
        }
        insert_obs(db, row)
        filas.append(row)
    [inc] = incidents.update(db, filas, ahora)
    return inc


def test_incidents_sin_hulls_dentro_del_presupuesto(make_client):
    """`/api/incidents` es la lista que la pantalla de comuna descarga cada 5 min:
    161 B con la base vacía y 565 B con un incidente de una detección. Techo = +25 %."""
    with make_client() as client:
        vacio = client.get("/api/incidents")
        assert vacio.status_code == 200
        _comprobar_peso("/api/incidents (vacío)", vacio, INCIDENTS_VACIO_HOY_B)

        ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        _sembrar_incidente(client.app.state.services.db, ahora, 1)
        uno = client.get("/api/incidents")
        assert uno.status_code == 200
        _comprobar_peso("/api/incidents (un incidente)", uno, INCIDENTS_UNO_HOY_B)


def test_incidents_con_hulls_dentro_del_presupuesto(make_client):
    """`?hulls=1` es la capa de huellas del mapa: 680 B con tres detecciones. Techo = +25 %."""
    with make_client() as client:
        ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        _sembrar_incidente(client.app.state.services.db, ahora, 3)
        response = client.get("/api/incidents?hulls=1")
        assert response.status_code == 200
        assert response.json()["incidents"][0]["hull"], "la medición necesita una respuesta con huella"
        _comprobar_peso("/api/incidents?hulls=1 (3 detecciones)", response, INCIDENTS_HULLS_HOY_B)


def test_incidente_detalle_dentro_del_presupuesto(make_client):
    """La ficha descarga evidencia, latencia y la reproducción hora a hora: 5 204 B
    con cinco detecciones en tres horas. Techo = +25 %."""
    with make_client() as client:
        ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        inc = _sembrar_incidente(client.app.state.services.db, ahora, 5)
        response = client.get(f"/api/incidents/{inc['id']}")
        assert response.status_code == 200
        body = response.json()
        assert body["evidence_total"] == 5, "la medición necesita cinco detecciones de evidencia"
        assert len(body["timeline"]["hours"]) >= 4, "la medición necesita el timeline de tres horas"
        _comprobar_peso(f"/api/incidents/{inc['id']} (5 detecciones, 3 h)", response, INCIDENTE_DETALLE_HOY_B)
