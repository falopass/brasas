"""Boletín de 60 segundos para radios comunitarias (IDEA-05 / ALI-09).

Lee /api/risk, /api/official-fires, /api/incidents y /api/risk/{comuna}/trend de
un servidor BRASA y arma, solo con reglas y plantillas (sin modelos de
lenguaje), un bloque por región listo para leer al aire:

    python scripts/local/boletin.py --url http://127.0.0.1:8000
    python scripts/local/boletin.py --url http://127.0.0.1:8000 --region Maule
    python scripts/local/boletin.py --url http://127.0.0.1:8000 --fecha 2026-10-19 --json

Cada bloque lleva su fuente al final y no supera las 90 palabras. Si una fuente
no responde, el bloque lo dice («sin datos de CONAF en este momento») y sigue
con las demás: ninguna cifra se inventa. Guía de lectura en docs/BOLETIN.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
CHILE_TZ = ZoneInfo("America/Santiago")
MAX_PALABRAS = 90
TIMEOUT_S = 15
LEVELS = ["bajo", "moderado", "alto", "extremo"]
# Estados de incidente satelital aún sin respaldo oficial («confirmado» ya lo cubre CONAF).
FOCOS_ABIERTOS = ("anomalia", "posible", "reportado")
# Acciones de preparación por nivel regional máximo. Se leen solo cuando el nivel
# lo justifica (alto o extremo): son consejos fijos, no un dato que se pueda inventar.
PREPARATE = {
    "alto": ("Prepárate hoy: despeja diez metros de pasto y ramas alrededor de la casa y no hagas quemas ni prendas fuego afuera."),
    "extremo": (
        "Prepárate hoy: despeja diez metros de pasto y ramas alrededor de la casa, "
        "no hagas quemas ni prendas fuego afuera y deja agua y documentos a mano por si hay que salir."
    ),
}


def fold(text: str) -> str:
    """Texto comparable: minúsculas, sin tildes y con espacios simples (igual que geo._fold)."""
    normalized = unicodedata.normalize("NFKD", (text or "").casefold())
    return " ".join("".join(ch for ch in normalized if not unicodedata.combining(ch)).split())


def load_territory() -> tuple[list[dict], dict[str, int], dict[int, str]]:
    """Regiones de norte a sur (con sus comunas), nombre de comuna → código de región
    y código de comuna → nombre (para nombrar las comunas de los avisos DMC).

    Se leen los GeoJSON de web/data directamente: así el script no importa backend
    (ni shapely) y corre con el Python del sistema, no solo con el .venv.
    """
    regiones_geo = json.loads((ROOT / "web" / "data" / "regiones.geojson").read_text(encoding="utf-8"))["features"]
    comunas_geo = json.loads((ROOT / "web" / "data" / "comunas.geojson").read_text(encoding="utf-8"))["features"]
    regiones = []
    for f in regiones_geo:
        p = f["properties"]
        regiones.append(
            {
                "code": p["code"],
                "name": p["name"],
                "fold": fold(p["name"]),
                "norte": -p["bbox"][3],
                "comunas": {c["properties"]["code"] for c in comunas_geo if c["properties"]["region_code"] == p["code"]},
            }
        )
    regiones.sort(key=lambda r: r["norte"])
    comuna_region = {fold(c["properties"]["name"]): c["properties"]["region_code"] for c in comunas_geo}
    comuna_nombres = {c["properties"]["code"]: c["properties"]["name"] for c in comunas_geo}
    return regiones, comuna_region, comuna_nombres


def fetch_json(url: str) -> dict | None:
    """JSON de `url`, o None si el servidor no responde o no devuelve JSON: nunca rompe el boletín."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
            return json.load(r)
    except Exception:
        return None


def fetch_trends(base: str, comunas: set[int]) -> dict[int, dict | None]:
    """Comparador semanal (/api/risk/{comuna}/trend?weeks=1) de cada comuna de la región.

    None en la comuna que no respondió. Se pide en paralelo acotado porque una
    región tiene decenas de comunas y cada llamada es un HTTP aparte.
    """
    codes = sorted(comunas)
    with ThreadPoolExecutor(max_workers=8) as ex:
        values = list(ex.map(lambda c: fetch_json(f"{base}/api/risk/{c}/trend?weeks=1"), codes))
    return dict(zip(codes, values))


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    return singular if n == 1 else (plural or f"{singular}s")


def _lista_y(items: list[str]) -> str:
    if len(items) <= 2:
        return " y ".join(items)
    return ", ".join(items[:-1]) + f" y {items[-1]}"


def _region_de(comuna: str | None, region_txt: str | None, comuna_region: dict[str, int], regiones: list[dict]) -> int | None:
    """Región de un incendio/foco: primero su comuna (nombre estándar), si no su texto de región.

    El texto de región de CONAF puede venir con artículo («Del Maule»): se acepta
    que un nombre contenga al otro, siempre sin tildes.
    """
    if comuna and fold(comuna) in comuna_region:
        return comuna_region[fold(comuna)]
    fr = fold(region_txt or "")
    if fr:
        for r in regiones:
            if r["fold"] in fr or fr in r["fold"]:
                return r["code"]
    return None


def _detalle_incendio(fire: dict) -> str:
    where = fire.get("comuna") or (fire.get("name") or "").title() or "lugar sin nombre"
    ha = fire.get("area_ha")
    return f"{where} ({ha:g} ha)" if ha else where


def _instante(value: object) -> datetime | None:
    """Un instante ISO-8601 del CAP; None si falta, no se puede leer o viene sin zona
    (ante la duda se muestra el aviso, igual que en backend: mejor un aviso oficial
    de más que uno oculto)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _frases_dmc(dmc_map: dict, region: dict, ahora: datetime, comuna_nombres: dict[int, str]) -> list[str]:
    """Una frase por aviso oficial vigente (tipo + vencimiento) que toca comunas de la región.

    `dmc_map` es risk["dmc"]: código de comuna → lista de avisos. Se agrupa por tipo
    y vencimiento porque un mismo aviso puede cubrir varias comunas.
    """
    grupos: dict[tuple[str, str], set[int]] = {}
    for code, items in (dmc_map or {}).items():
        try:
            code = int(code)
        except (TypeError, ValueError):
            continue
        if code not in region["comunas"]:
            continue
        for item in items or []:
            onset, expires = _instante(item.get("onset")), _instante(item.get("expires"))
            if (onset and onset > ahora) or (expires and expires <= ahora):
                continue
            label = (item.get("label") or item.get("kind") or "tiempo").lower()
            grupos.setdefault((label, str(item.get("expires") or "")), set()).add(code)
    frases = []
    for (label, expires), codes in sorted(grupos.items(), key=lambda g: (not g[0][1], g[0][1])):
        nombres = sorted({n for c in codes if (n := comuna_nombres.get(c))})
        if not nombres:
            donde = "comunas de la región"
        elif len(nombres) <= 3:
            donde = _lista_y(nombres)
        else:
            donde = f"{len(nombres)} comunas"
        vence = _instante(expires)
        hasta = f" hasta las {vence.astimezone(CHILE_TZ).strftime('%H:%M')}" if vence else ""
        frases.append(f"La DMC mantiene un aviso oficial de {label} en {donde}{hasta}.")
    return frases


def build_block(
    region: dict,
    risk: dict | None,
    fires: list | None,
    incidents: list | None,
    hora: str,
    comuna_region: dict[str, int],
    regiones: list[dict],
    comuna_nombres: dict[int, str] | None = None,
    ahora: datetime | None = None,
    trends: dict[int, dict | None] | None = None,
) -> dict:
    """Bloque de una región. `risk` es el payload de /api/risk; `fires` e `incidents`,
    las listas de las otras dos rutas, y `trends` un mapa comuna → payload de
    /api/risk/{comuna}/trend. None en cualquiera = esa fuente no respondió."""
    ahora = ahora or datetime.now(CHILE_TZ)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=CHILE_TZ)
    fuentes: list[str] = []
    cuerpo: list[str] = []

    # Riesgo (Open-Meteo vía BRASA) y Botón Rojo (CONAF) llegan en la misma respuesta.
    nivel_top: str | None = None
    if risk is None:
        cuerpo.append("Sin datos de riesgo ni de Botón Rojo en este momento.")
    else:
        fuentes += ["Open-Meteo vía BRASA", "CONAF (Botón Rojo)"]
        cuentas: dict[str, int] = {}
        for code, row in (risk.get("comunas") or {}).items():
            try:
                code = int(code)
            except (TypeError, ValueError):
                continue
            if code not in region["comunas"]:
                continue
            level = row.get("level_combined") or row.get("level")
            if level in LEVELS:
                cuentas[level] = cuentas.get(level, 0) + 1
        if cuentas:
            nivel_top = max(cuentas, key=LEVELS.index)
            n = cuentas[nivel_top]
            cuerpo.append(f"El nivel de condiciones más alto es {nivel_top} en {n} {_plural(n, 'comuna')}.")
        else:
            cuerpo.append("Sin pronóstico de riesgo para hoy.")
        br = sum(1 for c in (risk.get("boton_rojo") or {}) if c.isdigit() and int(c) in region["comunas"])
        if br:
            cuerpo.append(f"CONAF mantiene Botón Rojo en {br} {_plural(br, 'comuna')}.")

    if fires is None:
        cuerpo.append("Sin datos de CONAF en este momento.")
    else:
        fuentes.append("CONAF (incendios)")
        activos = [
            f
            for f in fires
            if f.get("status") == "confirmado" and _region_de(f.get("comuna"), f.get("region"), comuna_region, regiones) == region["code"]
        ]
        if not activos:
            cuerpo.append("CONAF no informa incendios activos en la región.")
        else:
            detalles = [_detalle_incendio(f) for f in sorted(activos, key=lambda f: -(f.get("area_ha") or 0))]
            n = len(activos)
            if n <= 3:
                cuerpo.append(f"CONAF informa {n} {_plural(n, 'incendio activo', 'incendios activos')}: {_lista_y(detalles)}.")
            else:
                cuerpo.append(f"CONAF informa {n} incendios activos, entre ellos {_lista_y(detalles[:3])}.")

    # Avisos oficiales de la DMC (viento y calor extremo) llegan dentro de /api/risk.
    # Van antes del detalle satelital: en el recorte de 90 palabras tienen prioridad.
    if risk is not None:
        frases_dmc = _frases_dmc(risk.get("dmc"), region, ahora, comuna_nombres or {})
        if frases_dmc:
            fuentes.append("DMC (avisos oficiales)")
            cuerpo += frases_dmc

    if incidents is None:
        cuerpo.append("Sin datos del monitoreo satelital en este momento.")
    else:
        focos = [
            i
            for i in incidents
            if i.get("status") in FOCOS_ABIERTOS and _region_de(i.get("comuna"), i.get("region"), comuna_region, regiones) == region["code"]
        ]
        if focos:
            fuentes.append("BRASA (detecciones satelitales)")
            n = len(focos)
            cuerpo.append(f"El satélite sigue {n} {_plural(n, 'foco')} de calor sin confirmar.")

    # Comparación con el pronóstico que se emitió la semana pasada para hoy
    # (/api/risk/{comuna}/trend?weeks=1): se toma el nivel `previous` de la fila
    # del día del boletín en cada comuna y se agrega igual que el nivel de hoy.
    # Sin foto previa la fila trae previous=None y no se cuenta: nunca se inventa
    # un cero ni un «igual que antes». Va casi al final del cuerpo a propósito:
    # en el recorte sale antes que el Botón Rojo, el dato más urgente.
    target = (risk or {}).get("date") or ahora.date().isoformat()
    prev_cuentas: dict[str, int] = {}
    for code in region["comunas"]:
        payload = (trends or {}).get(code)
        prev = next(
            (r.get("previous") for r in (payload or {}).get("rows") or [] if r.get("target_date") == target),
            None,
        )
        if prev in LEVELS:
            prev_cuentas[prev] = prev_cuentas.get(prev, 0) + 1
    if prev_cuentas:
        prev_top = max(prev_cuentas, key=LEVELS.index)
        n = prev_cuentas[prev_top]
        comparacion = f"El pronóstico de la semana pasada para hoy llegaba a {prev_top} en {n} {_plural(n, 'comuna')}."
        fuentes.append("Open-Meteo vía BRASA (semana pasada)")
    else:
        comparacion = "Sin comparación esta semana."
    cuerpo.append(comparacion)

    # «Prepárate hoy»: acciones fijas según el nivel máximo de la región, solo
    # cuando el nivel lo justifica (alto o extremo). Es la frase más prescindible:
    # es consejo, no un dato del momento.
    preparate = PREPARATE.get(nivel_top) if nivel_top else None
    if preparate:
        cuerpo.append(preparate)

    cierre = "Si ves fuego o humo, llama al 132 (Bomberos)."
    fuente = f"Fuente: CONAF (Botón Rojo e incendios) y Open-Meteo vía BRASA al {hora}."

    def texto_con(partes: list[str]) -> str:
        return " ".join([f"{region['name']}:", *partes, cierre, fuente])

    # Si el bloque se pasa de 90 palabras se quitan frases desde el final de
    # `cuerpo`, así que el orden de la lista es la prioridad. Sale primero lo
    # prescindible («Prepárate hoy», comparación semanal, satélite), después los
    # avisos DMC y los incendios, y aguantan hasta el final el Botón Rojo y el
    # nivel de hoy: son los datos más urgentes. La comparación queda detrás del
    # Botón Rojo precisamente para no poder expulsarlo.
    while len(cuerpo) > 1 and len(texto_con(cuerpo).split()) > MAX_PALABRAS:
        cuerpo = cuerpo[:-1]
    texto = texto_con(cuerpo)
    return {
        "region": region["name"],
        "texto": texto,
        "palabras": len(texto.split()),
        "fuentes": fuentes,
        # La comparación y el «prepárate» viajan también como campos propios, con
        # su fuente, para que la radio los lea por separado aunque el recorte los
        # haya sacado del texto al aire.
        "comparacion": {"texto": comparacion, "fuente": "Open-Meteo vía BRASA" if prev_cuentas else None},
        "preparate": {"texto": preparate, "fuente": "Open-Meteo vía BRASA (nivel de condiciones)"} if preparate else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Boletín radial de riesgo de incendios por región.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base del servidor BRASA")
    parser.add_argument("--region", help="Solo esta región (nombre, con o sin tildes)")
    parser.add_argument("--fecha", help="Día del pronóstico AAAA-MM-DD (hoy si se omite)")
    parser.add_argument("--json", action="store_true", help="Salida en JSON en vez de texto")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    if args.fecha:
        try:
            date.fromisoformat(args.fecha)
        except ValueError:
            sys.exit("--fecha debe ser AAAA-MM-DD")

    regiones, comuna_region, comuna_nombres = load_territory()
    if args.region:
        wanted = fold(args.region)
        regiones = [r for r in regiones if r["fold"] == wanted]
        if not regiones:
            sys.exit(f"Región no encontrada: {args.region}. Usa uno de estos nombres: " + ", ".join(r["name"] for r in load_territory()[0]))

    risk = fetch_json(f"{base}/api/risk" + (f"?day={args.fecha}" if args.fecha else ""))
    fires_payload = fetch_json(f"{base}/api/official-fires")
    incidents_payload = fetch_json(f"{base}/api/incidents")
    fires = fires_payload.get("fires") if fires_payload else None
    incidents = incidents_payload.get("incidents") if incidents_payload else None
    for ruta, payload in (("/api/risk", risk), ("/api/official-fires", fires_payload), ("/api/incidents", incidents_payload)):
        if payload is None:
            print(f"Aviso: {ruta} no respondió; el bloque lo dirá al aire.", file=sys.stderr)

    hora = datetime.now(CHILE_TZ).strftime("%H:%M")
    bloques = [
        build_block(
            r, risk, fires, incidents, hora, comuna_region, regiones, comuna_nombres=comuna_nombres, trends=fetch_trends(base, r["comunas"])
        )
        for r in regiones
    ]
    if args.json:
        print(json.dumps(bloques, ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(b["texto"] for b in bloques))
    return 0


if __name__ == "__main__":
    sys.exit(main())
