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
from backend.freshness import STALE_AFTER_S, STALE_POR_FUENTE, age_seconds, productos_por_fuente
from backend.services import stamp, utcnow

WINDOW_H = 24

# Una clave real (MAP_KEY de FIRMS y similares) tiene 20 caracteres o más; los valores cortos
# se dejan tal cual para no enmascarar texto corriente como «key=id».
_SECRETS = (
    (re.compile(r"\b(MAP_KEY|key)=[A-Za-z0-9]{20,}", re.IGNORECASE), r"\1=***"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"\bX-Internal-Token:\s*[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "X-Internal-Token: ***"),
    # Rutas locales de Windows y de Unix: el mensaje se publica sin autenticación y una ruta
    # absoluta revela la disposición del contenedor sin ayudar a nadie.
    (re.compile(r"\b[A-Za-z]:\\[^\s\"'<>]+"), "(ruta local)"),
    (re.compile(r"(?<![\w:])/(?:home|Users|root|tmp|var|opt|app|usr|data|srv|etc)/[^\s\"'<>]+"), "(ruta local)"),
)


def scrub(text: str) -> str:
    """Enmascara claves, tokens y rutas locales de un mensaje antes de publicarlo."""
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
        vieja = max(viejas, key=lambda f: f["age_h"] or 0)
        nombre = vieja["source"].upper()
        if "GOES" in nombre:
            que_hacer = "Revisar la última corrida de GOES en runs[]."
        elif any(parte in nombre for parte in ("VIIRS", "MODIS", "FIRMS")):
            que_hacer = "Revisar el cupo de la clave FIRMS en /api/status → firms_quota."
        else:
            que_hacer = f"Revisar la última corrida de {vieja['source']} en runs[]."
    else:
        nueva = min((f for f in fuentes if f["age_h"] is not None), key=lambda f: f["age_h"], default=None)
        if nueva:
            texto = f"El ciclo corrió hace {ingest_age_min:.0f} min y la detección más nueva es de hace {_horas(nueva['age_h'])} h ({nueva['source']})."
        else:
            texto = f"El ciclo corrió hace {ingest_age_min:.0f} min; todavía no hay detecciones registradas."
        que_hacer = "No hay nada que hacer: el ciclo y las fuentes están al día."
    return {"ingest_age_min": ingest_age_min, "fuentes": fuentes, "estado": estado, "texto": texto, "que_hacer": que_hacer}


def error_summary(db: Database, by_product: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Errores por producto en las últimas `WINDOW_H` horas y claves `*_error` del último ciclo.

    Los conteos salen de `_by_product`, la misma consulta que usa `failures_24h`. `cycle_errors`
    conserva los nombres de las claves y `cycle_detail` agrega el motivo saneado de cada una.
    `desfase` cruza la marca del ciclo con la edad de cada fuente para que `/api/status`
    distinga «no hay dato nuevo» de «la ingesta está parada». `by_product` permite reutilizar
    el agregado cuando `/api/status` pide los dos bloques juntos (`status_blocks`).
    """
    if by_product is None:
        by_product = _by_product(db, stamp(utcnow() - timedelta(hours=WINDOW_H)))
    last_cycle = json.loads(db.kv_get("last_cycle") or "{}")
    errores = sorted(scrub(k) for k in last_cycle if k.endswith("_error"))
    return {
        "window_h": WINDOW_H,
        "by_product": by_product,
        "cycle_errors": errores,
        "cycle_detail": _cycle_detail(last_cycle),
        "desfase": desfase(db),
    }


def _cycle_detail(last_cycle: dict) -> dict[str, str]:
    """Motivo saneado de cada clave `*_error` del último ciclo, para no publicar solo el nombre.

    `cycle_errors` se mantiene por compatibilidad; aquí va el texto que dejó la tarea, con
    claves, tokens y rutas locales enmascarados y recortado a `MAX_ERROR_LEN`. Sin mensaje
    (por ejemplo un ciclo viejo que guardó `true`) queda «error sin detalle».
    """
    detalle: dict[str, str] = {}
    for key in sorted(k for k in last_cycle if k.endswith("_error")):
        valor = last_cycle[key]
        texto = "" if isinstance(valor, bool) else str(valor or "")
        texto = scrub(texto).strip()[:MAX_ERROR_LEN]
        detalle[key] = texto or "error sin detalle"
    return detalle


MAX_ERROR_LEN = 160


def failures_24h(db: Database, by_product: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Corridas y fallos por producto en las últimas `WINDOW_H` horas, con el último error.

    Incluye todo producto con corridas en la ventana, aunque no haya fallado: `failed: 0` y
    `last_error: null`. El mensaje es el `message` que dejó la ingesta, enmascarado con `scrub`
    y recortado a `MAX_ERROR_LEN` caracteres (en ese orden, para no partir una clave).
    Los conteos salen de `_by_product`; el mensaje sale de una segunda consulta (`MAX(id)` por
    producto), que `error_summary` no necesita. `by_product` permite reutilizar el agregado
    cuando `/api/status` pide los dos bloques juntos (`status_blocks`).
    """
    since = stamp(utcnow() - timedelta(hours=WINDOW_H))
    if by_product is None:
        by_product = _by_product(db, since)
    out = {product: {**info, "last_error": None} for product, info in by_product.items()}
    for row in db.query(
        "SELECT r.product, r.message FROM ingest_runs r JOIN (SELECT product, MAX(id) AS id "
        "FROM ingest_runs WHERE ok = 0 AND started_at >= ? GROUP BY product) last ON last.id = r.id",
        (since,),
    ):
        if row["product"] in out and row["message"]:
            out[row["product"]]["last_error"] = scrub(row["message"])[:MAX_ERROR_LEN]
    return out


def status_blocks(db: Database) -> tuple[dict[str, Any], dict[str, Any]]:
    """Los dos bloques de fallas de `/api/status` con una sola lectura agregada de `ingest_runs`."""
    by_product = _by_product(db, stamp(utcnow() - timedelta(hours=WINDOW_H)))
    return error_summary(db, by_product), failures_24h(db, by_product)


# ------------------------------------------------------------------ veredicto por fuente
# (AUTO-14, unificado en AUTO-10): lo que /api/status ya calcula, dicho en palabras con arreglo.

CORRIDAS_VENTANA = 3  # corridas recientes por producto alcanzan para ver una racha de fallos
FALLOS_PARA_CAIDA = 3  # corridas seguidas en error para declarar una fuente «fallando»
RESPALDO_TARDE_S = 2 * 3600  # el respaldo corre al final de cada ciclo (~10 min): 2 h de holgura

# Familias que se publican siempre, en este orden (el id coincide con freshness.familia).
FUENTES = (
    ("GOES", "GOES (satélite geoestacionario)"),
    ("FIRMS", "FIRMS (satélites polares)"),
    ("CONAF", "CONAF (reporte público)"),
    ("Open-Meteo", "Open-Meteo (clima)"),
)

_QUE_HACER = {
    "GOES": {
        "fallando": "Revisar las corridas en /api/status → runs y goes_sweeps: la descarga de barridos desde S3 de NOAA está fallando.",
        "tarde": "Revisar goes_sweeps y la última corrida buena en /api/status → runs.",
        "sin_dato": "Revisar que la ingesta esté programada: /api/status → ingest_mode y scheduler_enabled.",
    },
    "FIRMS": {
        "fallando": "Revisar el cupo de la clave en /api/status → firms_quota; si está agotado, esperar la ventana de 10 minutos o revisar el secreto FIRMS_MAP_KEY.",
        "tarde": "Revisar /api/status → firms_quota y la última corrida del producto en runs[].",
        "sin_dato": "Revisar que el secreto FIRMS_MAP_KEY esté configurado: /api/status → firms_configured.",
    },
    "CONAF": {
        "fallando": "Revisar las corridas CONAF en /api/status → runs: puede ser el reporte público de GEPRIF o el servicio ArcGIS.",
        "tarde": "Revisar la última corrida buena de CONAF en /api/status → runs.",
        "sin_dato": "Revisar que la ingesta esté programada: /api/status → ingest_mode.",
    },
    "Open-Meteo": {
        "fallando": "Revisar el cupo diario en /api/status → open_meteo; si está agotado, las tandas se retoman al día siguiente.",
        "tarde": "Revisar /api/status → open_meteo y risk_computed_at.",
        "sin_dato": "Revisar que el ciclo de riesgo esté corriendo: /api/status → risk_computed_at.",
    },
}


def corridas_recientes(db: Database, n: int = CORRIDAS_VENTANA) -> list[dict[str, Any]]:
    """Las últimas `n` corridas por producto de `ingest_runs`, más nuevas primero por producto."""
    return db.query(
        "SELECT provider, product, ok, finished_at FROM (SELECT provider, product, ok, finished_at, "
        "ROW_NUMBER() OVER (PARTITION BY product ORDER BY id DESC) AS rn FROM ingest_runs) "
        "WHERE rn <= ? ORDER BY product, rn",
        (n,),
    )


def ultima_corrida_buena(db: Database) -> dict[str, str | None]:
    """`finished_at` de la última corrida buena por producto, sobre toda la tabla."""
    return {
        r["product"]: r["finished_at"]
        for r in db.query("SELECT product, MAX(finished_at) AS finished_at FROM ingest_runs WHERE ok = 1 GROUP BY product")
    }


def veredicto_fuentes(db: Database, *, backup: dict[str, Any] | None = None, ahora: datetime | None = None) -> list[dict[str, Any]]:
    """Veredicto por fuente de la ingesta para /api/diagnostico, en palabras simples.

    Reutiliza lo mismo que ve /api/status: las últimas corridas de `ingest_runs`
    (`corridas_recientes` y `ultima_corrida_buena`, la misma lectura que alimenta
    `freshness.products`), el cupo guardado de la clave FIRMS en `kv` y el bloque `backup`
    que le pasa la ruta. Estados: `bien`, `tarde` (sin corrida buena dentro de la ventana de
    la fuente), `fallando` (3 corridas seguidas en error) y `sin_dato` (nunca corrió). Los
    `que_hacer` nombran el panel o el secreto a revisar, nunca su valor.
    """
    productos = productos_por_fuente(corridas_recientes(db), ultima_corrida_buena(db))
    try:
        quota = json.loads(db.kv_get("firms_quota") or "{}")
    except ValueError:
        quota = {}
    out: list[dict[str, Any]] = []
    for nombre, etiqueta in FUENTES:
        entrada = productos.get(nombre)
        ultima_ok = entrada["last_ok_at"] if entrada else None
        edad_s = age_seconds(ultima_ok, ahora)
        minutos = round(edad_s / 60) if edad_s is not None else None
        fallos = entrada["fallos_seguidos"] if entrada else 0
        limite_min = STALE_POR_FUENTE.get(nombre.casefold(), STALE_AFTER_S) // 60
        if entrada is None:
            estado = "sin_dato"
            detalle = f"{etiqueta}: no hay corridas registradas de la ingesta."
        elif fallos >= FALLOS_PARA_CAIDA:
            estado = "fallando"
            detalle = f"{etiqueta}: {fallos} corridas seguidas en error."
        elif edad_s is None:
            estado = "sin_dato"
            detalle = f"{etiqueta}: todavía no hay una corrida buena registrada."
        elif edad_s > limite_min * 60:
            estado = "tarde"
            detalle = f"{etiqueta}: la última corrida buena fue hace {minutos} min; su ventana es de {limite_min} min."
        else:
            estado = "bien"
            detalle = f"{etiqueta}: al día (última corrida buena hace {minutos} min)."
        # El cupo de la clave FIRMS se agota por ventana de 10 minutos: cerca del tope la
        # fuente está en riesgo aunque la última corrida haya salido bien.
        if nombre == "FIRMS" and estado == "bien":
            limite_q, usado = quota.get("limit"), quota.get("used")
            if isinstance(limite_q, (int, float)) and limite_q and isinstance(usado, (int, float)) and usado >= 0.9 * limite_q:
                estado = "tarde"
                detalle = f"{etiqueta}: la clave ya gastó {usado} de {limite_q} consultas de su ventana."
        out.append(
            {
                "id": nombre.casefold(),
                "nombre": nombre,
                "estado": estado,
                "ultima_ok": ultima_ok,
                "minutos_desde_ultima_ok": minutos,
                "fallos_seguidos": fallos,
                "detalle": detalle,
                "que_hacer": _QUE_HACER[nombre][estado] if estado != "bien" else "Nada que hacer: la fuente está al día.",
                "enlace": "/api/status",
            }
        )
    respaldo = backup or {}
    if not respaldo.get("enabled"):
        estado_r, detalle_r = "sin_dato", "Respaldo: sin almacenamiento remoto configurado; la base no se está respaldando."
        hacer_r = "Configurar el almacenamiento remoto (secretos del despliegue) si esta instalación lo necesita."
        ultima_r, minutos_r = None, None
    elif respaldo.get("reason"):
        estado_r, detalle_r = "fallando", "Respaldo: el último intento falló."
        hacer_r = "Revisar los secretos del almacenamiento y /api/status → backup."
        ultima_r = respaldo.get("at")
        edad_r = age_seconds(ultima_r, ahora)
        minutos_r = round(edad_r / 60) if edad_r is not None else None
    else:
        ultima_r = respaldo.get("at")
        edad_r = age_seconds(ultima_r, ahora)
        minutos_r = round(edad_r / 60) if edad_r is not None else None
        if edad_r is None or edad_r > RESPALDO_TARDE_S:
            estado_r = "tarde"
            detalle_r = "Respaldo: no sube uno bueno hace más de 2 h." if edad_r is not None else "Respaldo: no hay marca de un respaldo bueno."
            hacer_r = "Revisar /api/status → backup y los secretos del almacenamiento."
        else:
            estado_r = "bien"
            detalle_r = f"Respaldo: al día (último hace {minutos_r} min)."
            hacer_r = "Nada que hacer: el respaldo está al día."
    out.append(
        {
            "id": "respaldo",
            "nombre": "Respaldo",
            "estado": estado_r,
            "ultima_ok": ultima_r,
            "minutos_desde_ultima_ok": minutos_r,
            "fallos_seguidos": 0,
            "detalle": detalle_r,
            "que_hacer": hacer_r,
            "enlace": "/api/status",
        }
    )
    return out
