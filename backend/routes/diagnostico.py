"""`GET /api/diagnostico`: el producto reporta sus propias fallas en palabras simples.

Lee la misma ventana en memoria que alimenta `/api/observability/routes` (misma deque, mismo
middleware en `backend/main.py`; aquí se mira solo los últimos 15 minutos) y la cruza con el
veredicto por fuente de `backend/diagnostics.py` (GOES, FIRMS con su cupo, CONAF, Open-Meteo y
el respaldo). No guarda ni publica IP, query string ni tokens: las rutas van plantilladas
(`/api/incidents/{incident_id}`), nunca la URL real. Si la telemetría falla, la consulta
responde igual con lo que haya.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from backend import diagnostics
from backend.routes import observability
from backend.routes.common import services
from backend.services import Services, stamp

log = logging.getLogger("brasa.diagnostico")
router = APIRouter(prefix="/api")

WINDOW_MIN = 15
VEREDICTO_TTL_S = 60  # el veredicto recorre toda ingest_runs: una vez por minuto basta
VEREDICTO_CACHE = "diagnostico:fuentes"
LENTA_MS = 2_000  # AUTO-01: una respuesta de más de 2 s cuenta como lenta
P95_LENTO_MS = 800  # AUTO-10: el p95 más alto sobre 800 ms marca «tarda demasiado»

_AVISO = (
    "Medición por proceso, igual que /api/observability/routes: la ventana se reinicia con el "
    "contenedor y cada instancia mide solo su propio tráfico. Guarda solo ruta plantillada, "
    "código y milisegundos; nunca IP, query string, cabeceras ni cuerpos."
)


def rutas(window_min: int = WINDOW_MIN) -> list[dict[str, Any]]:
    """Agrega la ventana por ruta plantillada: n, 5xx, p50/p95, lentas y el último 5xx.

    El instante del último error se convierte de monotónico a UTC aproximando contra el reloj
    actual (la diferencia es menor a un segundo y no cambia el diagnóstico).
    """
    now_mono = time.monotonic()
    ahora = datetime.now(timezone.utc)
    by_path: dict[str, list[tuple[float, int, float]]] = {}
    for t, path, code, ms in observability.SAMPLES:
        if t >= now_mono - window_min * 60:
            by_path.setdefault(path, []).append((t, code, ms))
    rows: list[dict[str, Any]] = []
    for path, items in by_path.items():
        ordered = sorted(ms for _, _, ms in items)
        errores = [(t, code) for t, code, _ in items if 500 <= code < 600]
        rows.append(
            {
                "path": path,
                "n": len(items),
                "p50_ms": observability._percentile(ordered, 50),
                "p95_ms": observability._percentile(ordered, 95),
                "errors_5xx": len(errores),
                "lentas": sum(1 for _, _, ms in items if ms > LENTA_MS),
                "ultimo_error_at": stamp(ahora - timedelta(seconds=now_mono - errores[-1][0])) if errores else None,
                "ultimo_codigo": errores[-1][1] if errores else None,
            }
        )
    rows.sort(key=lambda row: (-row["p95_ms"], row["path"]))
    return rows


def _problemas(rows: list[dict[str, Any]], fuentes: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Los problemas en palabras simples (AUTO-01): rutas con 5xx o lentas, y fuentes que no están bien."""
    out: list[dict[str, str]] = []
    for row in rows:
        if row["errors_5xx"]:
            out.append(
                {
                    "clave": "errores_5xx",
                    "gravedad": "alta",
                    "texto": f"{row['path']} devolvió {row['errors_5xx']} error(es) 5xx en los últimos {WINDOW_MIN} min.",
                    "arreglo": "revisar los registros del contenedor y el detalle en /api/status → errors.",
                }
            )
        if row["lentas"] or row["p95_ms"] > P95_LENTO_MS:
            out.append(
                {
                    "clave": "ruta_lenta",
                    "gravedad": "media",
                    "texto": f"{row['path']} está respondiendo lento (p95 de {row['p95_ms']} ms, {row['lentas']} sobre 2 s).",
                    "arreglo": "revisar su consulta o su caché.",
                }
            )
    for fuente in fuentes:
        if fuente["estado"] == "bien":
            continue
        out.append(
            {
                "clave": fuente["id"],
                "gravedad": "alta" if fuente["estado"] == "fallando" else "media" if fuente["estado"] == "tarde" else "baja",
                "texto": fuente["detalle"],
                "arreglo": fuente["que_hacer"],
            }
        )
    return out


def _advice(rows: list[dict[str, Any]], fuentes: list[dict[str, Any]], errors_5xx: int) -> str:
    """Una frase de reglas (AUTO-10): 5xx primero, después fuentes, después lentitud."""
    if errors_5xx:
        return "El servidor está devolviendo errores: revisa las rutas marcadas."
    caidas = [f for f in fuentes if f["estado"] == "fallando"]
    if caidas:
        return f"{caidas[0]['nombre']} está fallando: {caidas[0]['que_hacer']}"
    peor = rows[0] if rows else None
    if peor and peor["p95_ms"] > P95_LENTO_MS:
        return f"Esta ruta tarda demasiado: revisa su consulta ({peor['path']})."
    tardes = [f for f in fuentes if f["estado"] in ("tarde", "sin_dato")]
    if tardes:
        return f"{tardes[0]['nombre']} está atrasada: {tardes[0]['que_hacer']}"
    return "Sin problemas de rendimiento ni de fuentes en la ventana."


@router.get("/diagnostico")
async def diagnostico(svc: Services = Depends(services)) -> dict[str, Any]:
    """Rendimiento y errores del propio servicio en 15 minutos, más el veredicto por fuente.

    `async` a propósito, como `/api/observability/routes`: la ventana se recorre en el hilo del
    event loop, el mismo donde el middleware anota, así `SAMPLES` no se mueve a media lectura.
    """
    rows = rutas()
    # El veredicto hace consultas de tabla completa sobre ingest_runs: se cachea un minuto
    # en la base. La telemetría de rutas no se cachea: vive en memoria y es barata.
    fuentes: Any = None
    try:
        fuentes = svc.db.cache_get(VEREDICTO_CACHE)
        if fuentes is None:
            kv = svc.db.kv_many(["backup_at", "backup_reason"])
            backup = {"enabled": svc.persistence.enabled, "at": kv["backup_at"], "reason": kv["backup_reason"]}
            fuentes = diagnostics.veredicto_fuentes(svc.db, backup=backup)
            svc.db.cache_set(VEREDICTO_CACHE, fuentes, VEREDICTO_TTL_S)
    except Exception:  # la telemetría nunca tumba la consulta: se responde con las rutas igual
        log.warning("El veredicto de fuentes no se pudo calcular.", exc_info=True)
        if fuentes is None:
            fuentes = []
    errors_5xx = sum(row["errors_5xx"] for row in rows)
    return {
        "type": "diagnostico",
        "window_min": WINDOW_MIN,
        "desde": stamp(datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MIN)),
        "routes": rows,
        "errors_5xx": errors_5xx,
        "lentas": sum(row["lentas"] for row in rows),
        "slowest": rows[0]["path"] if rows else None,
        "problemas": _problemas(rows, fuentes),
        "fuentes": fuentes,
        "advice": _advice(rows, fuentes, errors_5xx),
        "aviso": _AVISO,
    }
