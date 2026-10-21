"""Diagnóstico operativo: resumen de errores de la ingesta para /api/status.

Conteos, instantes y el último mensaje de la propia ingesta (recortado): sirve para
diagnosticar fallos sin acceso a los registros del contenedor (OPS-14). Sin datos personales.
Los mensajes se publican en un endpoint público y sin autenticación: `scrub` enmascara las
claves y tokens que puedan venir en una URL o en una cabecera antes de recortarlos.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.db import Database
from backend.services import stamp, utcnow

WINDOW_H = 24

# Una clave real (MAP_KEY de FIRMS y similares) tiene 20 caracteres o más; los valores cortos
# se dejan tal cual para no enmascarar texto corriente como «key=id».
_SECRETS = (
    (re.compile(r"\b(MAP_KEY|key)=[A-Za-z0-9]{20,}", re.IGNORECASE), r"\1=***"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"\bX-Internal-Token:\s*[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "X-Internal-Token: ***"),
)


def scrub(text: str) -> str:
    """Enmascara claves y tokens de un mensaje antes de publicarlo."""
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


def _by_product(db: Database, since: str) -> dict[str, dict[str, Any]]:
    """Corridas, fallos e instante del último fallo por producto desde `since`."""
    return {
        row["product"]: {
            "runs": row["runs"],
            "failed": row["failed"] or 0,
            "last_failed_at": row["last_failed_at"],
        }
        for row in db.query(
            "SELECT product, COUNT(*) AS runs, SUM(ok = 0) AS failed, "
            "MAX(CASE WHEN ok = 0 THEN started_at END) AS last_failed_at "
            "FROM ingest_runs WHERE started_at >= ? GROUP BY product ORDER BY product",
            (since,),
        )
    }


def _momento(valor: object) -> datetime | None:
    """Lee una marca ISO-8601; None si falta o no se puede leer."""
    if not isinstance(valor, str) or not valor:
        return None
    try:
        marca = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return marca if marca.tzinfo else marca.replace(tzinfo=timezone.utc)


DESFASE_H = 6  # una fuente sin detecciones nuevas por más de 6 h ya no está al día
PARADO_MIN = 90  # el ciclo corre cada 10 min: 90 min sin cerrar es una ingesta detenida
RELOJ_MIN = 10  # una marca más de 10 min en el futuro no es un reloj confiable


def _horas(valor: float) -> str:
    """Horas con un decimal y coma decimal, como el resto de los textos en español."""
    return f"{valor:.1f}".replace(".", ",")


def desfase(db: Database, now: datetime | None = None) -> dict[str, Any]:
    """Cruza la marca del último ciclo con la detección más nueva de cada fuente.

    `freshness` solo dice si el cron corrió; esto distingue «la fuente no trae nada nuevo» de
    «la ingesta está parada». Dos consultas agregadas: `kv` y `MAX(observed_at) GROUP BY source`.
    `estado` es el peor de `sin_datos`, `reloj`, `parado`, `atrasada` y `al_dia`. No afirma que
    una fuente haya fallado: en invierno puede no ver focos y el texto deja esa puerta abierta.
    """
    ahora = now or utcnow()
    marca = _momento(db.kv_get("last_ingest_at"))
    ingest_age_min = round((ahora - marca).total_seconds() / 60, 1) if marca else None
    fuentes: list[dict[str, Any]] = []
    for row in db.query("SELECT source, MAX(observed_at) AS t FROM observations GROUP BY source ORDER BY source"):
        marca_fuente = _momento(row["t"])
        age_h = round(max(0.0, (ahora - marca_fuente).total_seconds() / 3600), 1) if marca_fuente else None
        fuentes.append({"source": row["source"], "age_h": age_h, "stale": age_h is None or age_h > DESFASE_H})
    viejas = [f for f in fuentes if f["stale"]]
    if ingest_age_min is None:
        estado = "sin_datos"
    elif ingest_age_min < -RELOJ_MIN:
        estado = "reloj"
    elif ingest_age_min > PARADO_MIN:
        estado = "parado"
    elif viejas:
        estado = "atrasada"
    else:
        estado = "al_dia"

    if estado == "sin_datos":
        texto = "Todavía no hay una marca del último ciclo de ingesta: no se puede saber si el dato satelital está al día."
        que_hacer = "Revisar que la ingesta esté programada y que el contenedor haya arrancado."
    elif estado == "reloj":
        texto = f"El último ciclo dice haber corrido hace {-ingest_age_min:.0f} min en el futuro: la marca del reloj no es confiable."
        que_hacer = "Revisar el reloj del contenedor: la marca del ciclo no puede estar en el futuro."
    elif estado == "parado":
        texto = f"El ciclo de ingesta lleva {ingest_age_min:.0f} min sin cerrar (más de {PARADO_MIN} min): puede estar detenido."
        que_hacer = "Revisar la última corrida en runs[] y el estado del programador; el ciclo no cierra desde hace más de 90 min."
    elif estado == "atrasada":
        detalle = ", ".join(f"{f['source']} ({_horas(f['age_h'])} h)" if f["age_h"] is not None else f["source"] for f in viejas)
        texto = (
            f"El ciclo corrió hace {ingest_age_min:.0f} min, pero no entró dato nuevo de {detalle}. "
            "Puede ser que esa fuente no esté viendo focos o que su ingesta esté atrasada; el mapa puede mostrar focos ya apagados."
        )
        que_hacer = "Revisar el cupo de la clave FIRMS en /api/status → firms_quota y la última corrida de GOES en runs[]."
    else:
        if fuentes and fuentes[0]["age_h"] is not None:
            nueva = max(fuentes, key=lambda f: f["age_h"] or 0)
            texto = f"El ciclo corrió hace {ingest_age_min:.0f} min y la detección más nueva es de hace {_horas(nueva['age_h'])} h ({nueva['source']})."
        else:
            texto = f"El ciclo corrió hace {ingest_age_min:.0f} min; todavía no hay detecciones registradas."
        que_hacer = "No hay nada que hacer: el ciclo y las fuentes están al día."
    return {"ingest_age_min": ingest_age_min, "fuentes": fuentes, "estado": estado, "texto": texto, "que_hacer": que_hacer}


def error_summary(db: Database) -> dict[str, Any]:
    """Errores por producto en las últimas `WINDOW_H` horas y claves `*_error` del último ciclo.

    Los conteos salen de `_by_product`, la misma consulta que usa `failures_24h`; aquí no se
    publica el mensaje del último error. `desfase` cruza la marca del ciclo con la edad de cada
    fuente para que `/api/status` distinga «no hay dato nuevo» de «la ingesta está parada».
    """
    since = stamp(utcnow() - timedelta(hours=WINDOW_H))
    last_cycle = json.loads(db.kv_get("last_cycle") or "{}")
    return {
        "window_h": WINDOW_H,
        "by_product": _by_product(db, since),
        "cycle_errors": sorted(scrub(k) for k in last_cycle if k.endswith("_error")),
        "desfase": desfase(db),
    }


MAX_ERROR_LEN = 160


def failures_24h(db: Database) -> dict[str, Any]:
    """Corridas y fallos por producto en las últimas `WINDOW_H` horas, con el último error.

    Incluye todo producto con corridas en la ventana, aunque no haya fallado: `failed: 0` y
    `last_error: null`. El mensaje es el `message` que dejó la ingesta, enmascarado con `scrub`
    y recortado a `MAX_ERROR_LEN` caracteres (en ese orden, para no partir una clave).
    Los conteos salen de `_by_product`; el mensaje sale de una segunda consulta (`MAX(id)` por
    producto), que `error_summary` no necesita.
    """
    since = stamp(utcnow() - timedelta(hours=WINDOW_H))
    out = {product: {**info, "last_error": None} for product, info in _by_product(db, since).items()}
    for row in db.query(
        "SELECT r.product, r.message FROM ingest_runs r JOIN (SELECT product, MAX(id) AS id "
        "FROM ingest_runs WHERE ok = 0 AND started_at >= ? GROUP BY product) last ON last.id = r.id",
        (since,),
    ):
        if row["product"] in out and row["message"]:
            out[row["product"]]["last_error"] = scrub(row["message"])[:MAX_ERROR_LEN]
    return out
