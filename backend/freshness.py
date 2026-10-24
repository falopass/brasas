"""Frescura del dato satelital: una sola regla para toda la aplicación.

Un punto de calor sin edad se lee como si fuera de ahora. La regla de los 30 minutos se usa en el
pill de la cabecera, en Mi zona, en la ficha de incidente, en el modo vecino y en Riesgo; tenerla
en un solo lugar evita que cada vista invente su propio umbral y que dos pantallas digan cosas
distintas del mismo dato. FUEGO-08 suma la frescura por familia de la ingesta (`status` con
`products`): una fuente caída por horas no puede seguir saliendo como «al día».
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

STALE_AFTER_S = 30 * 60

# Umbral propio por fuente o familia de la ingesta (FUEGO-08): un solo umbral de 30 minutos
# declararía «viejo» al satélite polar casi siempre. GOES barre el disco cada ~10 minutos, así
# que media hora sin corrida buena ya es un problema; VIIRS/MODIS pasan 2-3 veces al día y FIRMS
# NRT suma 1-3 h de latencia de diseño; el reporte de CONAF y las pasadas de Open-Meteo se
# actualizan en horas, no en minutos. El porqué de cada número está en docs/FUENTES.md.
STALE_POR_FUENTE: dict[str, int] = {
    "goes": 30 * 60,
    "firms": 3 * 3600,
    "conaf": 6 * 3600,
    "open-meteo": 6 * 3600,
}


def familia(provider: str | None, product: str | None) -> str | None:
    """Familia pública de una corrida de `ingest_runs`; None si no mide frescura del mapa.

    Primero se mira el proveedor y el producto queda de respaldo: GOES corre con varios
    productos por barrido (`GOES19_FDCF`, `ABI-L2-FDCF`) y FIRMS guarda las fuentes pedidas
    separadas por coma. La DMC (avisos de clima) no alimenta focos y queda fuera, igual que
    los proveedores desconocidos — y que el GLM: los LCFA llenan la tabla `lightning` (la
    marca de rayos del incidente), no el mapa de focos. Un GLM sano no puede declarar
    «GOES al día» con el ABI caído, ni un archivo GLM roto declararlo «fallando».
    """
    prod = (product or "").upper()
    if "GLM" in prod:
        return None
    proveedor = provider or ""
    if proveedor.startswith("NOAA GOES"):
        return "GOES"
    if proveedor.startswith("NASA FIRMS"):
        return "FIRMS"
    if proveedor.startswith("CONAF"):
        return "CONAF"
    if proveedor == "Open-Meteo":
        return "Open-Meteo"
    if prod.startswith(("GOES", "ABI-L2")):
        return "GOES"
    if prod.startswith(("VIIRS", "MODIS")):
        return "FIRMS"
    if prod.startswith(("CONAF", "BOTON_ROJO")):
        return "CONAF"
    if prod in ("FWI", "LLUVIA"):
        return "Open-Meteo"
    return None


def productos_por_fuente(corridas: Iterable[Mapping[str, Any]], last_ok: Mapping[str, str | None]) -> dict[str, dict[str, Any]]:
    """Agrupa las corridas recientes por familia: última corrida buena y racha de fallos.

    `corridas` son filas `{provider, product, ok}` de `ingest_runs`, las más nuevas primero
    dentro de cada producto (la consulta ordena por `rn`). `last_ok` trae el `finished_at` de
    la última corrida buena por producto, agregado sobre toda la tabla: así una racha de fallos
    reciente no borra la marca de un acierto anterior a la ventana. De cada familia se conserva
    la marca más fresca entre sus productos y la racha de fallos más larga: basta que un
    producto de la familia esté cayéndose para que la fuente no esté sana.
    """
    por_producto: dict[tuple[str, str], list[bool]] = {}
    for fila in corridas:
        por_producto.setdefault((fila.get("provider") or "", fila.get("product") or ""), []).append(bool(fila.get("ok")))
    familias: dict[str, dict[str, Any]] = {}
    for (provider, product), oks in por_producto.items():
        nombre = familia(provider, product)
        if nombre is None:
            continue
        entrada = familias.setdefault(nombre, {"last_ok_at": None, "fallos_seguidos": 0})
        marca = last_ok.get(product)
        if marca and (entrada["last_ok_at"] is None or marca > entrada["last_ok_at"]):
            entrada["last_ok_at"] = marca
        fallos = 0
        for ok in oks:
            if ok:
                break
            fallos += 1
        entrada["fallos_seguidos"] = max(entrada["fallos_seguidos"], fallos)
    return familias


def age_seconds(stamp: str | None, now: datetime | None = None) -> int | None:
    """Segundos desde una marca ISO de la ingesta. None si no hay marca o no se puede leer."""
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    return max(0, int((reference - moment).total_seconds()))


def status(
    last_ingest_at: str | None,
    now: datetime | None = None,
    products: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Contrato que consume la interfaz, para que el cliente no repita la aritmética.

    `stale` es True también cuando no hay marca: una aplicación recién instalada no debe decir
    «al día» de un dato que todavía no existe.

    `products` es la salida de `productos_por_fuente` (FUEGO-08): la frescura por familia de la
    ingesta, cada una con su umbral de `STALE_POR_FUENTE`. Una familia está vieja cuando su
    última corrida buena superó el umbral —o nunca existió— y también cuando lleva 2 o más
    corridas seguidas en error con el dato ya pasado de la regla base de 30 minutos: una fuente
    que falla cada ciclo está caída aunque su umbral de diseño (horas en el polar) todavía no
    se cumpla. El `stale` global es el peor de las dos señales: la aplicación no afirma «datos
    al día» cuando una fuente lleva horas caída.
    """
    age = age_seconds(last_ingest_at, now)
    stale = age is None or age > STALE_AFTER_S
    out: dict[str, Any] = {
        "last_ingest_at": last_ingest_at,
        "age_seconds": age,
        "stale_after_s": STALE_AFTER_S,
        "stale": stale,
    }
    if not products:
        return out
    detalle: dict[str, dict[str, Any]] = {}
    for nombre, info in products.items():
        limite = STALE_POR_FUENTE.get(nombre.casefold(), STALE_AFTER_S)
        marca = info.get("last_ok_at")
        fallos = int(info.get("fallos_seguidos") or 0)
        edad = age_seconds(marca, now)
        vieja = edad is None or edad > limite or (fallos >= 2 and edad > STALE_AFTER_S)
        detalle[nombre] = {
            "last_ok_at": marca,
            "age_seconds": edad,
            "stale_after_s": limite,
            "fallos_seguidos": fallos,
            "stale": vieja,
        }
        stale = stale or vieja
    out["products"] = detalle
    out["stale"] = stale
    return out


def status_por_fuente(marcas: Mapping[str, str | None], ahora: datetime | None = None) -> dict[str, Any]:
    """Frescura por fuente: a diferencia de `status` (una sola marca global), recibe la marca de
    ingesta de cada fuente y dice cuál está vieja.

    Si una fuente se cae y las demás siguen entrando, la marca global se refresca igual y la
    aplicación diría «al día» aunque falte la mitad de los sensores; aquí `stale` global es True
    si cualquier fuente lo está y `fuentes_viejas` nombra cuáles, para que el vecino no lea
    «no vemos datos» como «no hay fuego». Cada fuente puede tener su propio umbral
    (`STALE_POR_FUENTE`); sin marca o con marca ilegible cuenta como vieja, igual que `status`.
    """
    fuentes: dict[str, dict[str, Any]] = {}
    viejas: list[str] = []
    for nombre, marca in marcas.items():
        limite = STALE_POR_FUENTE.get(nombre.casefold(), STALE_AFTER_S)
        age = age_seconds(marca, ahora)
        vieja = age is None or age > limite
        fuentes[nombre] = {"last_ingest_at": marca, "age_seconds": age, "stale_after_s": limite, "stale": vieja}
        if vieja:
            viejas.append(nombre)
    return {"fuentes": fuentes, "fuentes_viejas": viejas, "stale": bool(viejas)}
