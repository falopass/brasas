"""Boletín de 60 segundos para radios comunitarias (IDEA-05 / ALI-09).

Lee /api/risk, /api/official-fires y /api/incidents de un servidor BRASA y arma,
solo con reglas y plantillas (sin modelos de lenguaje), un bloque por región
listo para leer al aire:

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


def fold(text: str) -> str:
    """Texto comparable: minúsculas, sin tildes y con espacios simples (igual que geo._fold)."""
    normalized = unicodedata.normalize("NFKD", (text or "").casefold())
    return " ".join("".join(ch for ch in normalized if not unicodedata.combining(ch)).split())


def load_territory() -> tuple[list[dict], dict[str, int]]:
    """Regiones de norte a sur (con sus comunas) y nombre de comuna → código de región.

    Se leen los GeoJSON de web/data directamente: así el script no importa backend
    (ni shapely) y corre con el Python del sistema, no solo con el .venv.
    """
    regiones_geo = json.loads((ROOT / "web" / "data" / "regiones.geojson").read_text(encoding="utf-8"))["features"]
    comunas_geo = json.loads((ROOT / "web" / "data" / "comunas.geojson").read_text(encoding="utf-8"))["features"]
    regiones = []
    for f in regiones_geo:
        p = f["properties"]
        regiones.append({"code": p["code"], "name": p["name"], "fold": fold(p["name"]), "norte": -p["bbox"][3],
                         "comunas": {c["properties"]["code"] for c in comunas_geo
                                     if c["properties"]["region_code"] == p["code"]}})
    regiones.sort(key=lambda r: r["norte"])
    comuna_region = {fold(c["properties"]["name"]): c["properties"]["region_code"] for c in comunas_geo}
    return regiones, comuna_region


def fetch_json(url: str) -> dict | None:
    """JSON de `url`, o None si el servidor no responde o no devuelve JSON: nunca rompe el boletín."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
            return json.load(r)
    except Exception:
        return None


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    return singular if n == 1 else (plural or f"{singular}s")


def _lista_y(items: list[str]) -> str:
    if len(items) <= 2:
        return " y ".join(items)
    return ", ".join(items[:-1]) + f" y {items[-1]}"


def _region_de(comuna: str | None, region_txt: str | None, comuna_region: dict[str, int],
               regiones: list[dict]) -> int | None:
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


def build_block(region: dict, risk: dict | None, fires: list | None, incidents: list | None,
                hora: str, comuna_region: dict[str, int], regiones: list[dict]) -> dict:
    """Bloque de una región. `risk` es el payload de /api/risk; `fires` e `incidents`,
    las listas de las otras dos rutas. None en cualquiera = esa fuente no respondió."""
    fuentes: list[str] = []
    cuerpo: list[str] = []

    # Riesgo (Open-Meteo vía BRASA) y Botón Rojo (CONAF) llegan en la misma respuesta.
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
            top = max(cuentas, key=LEVELS.index)
            n = cuentas[top]
            cuerpo.append(f"El nivel de condiciones más alto es {top} en {n} "
                          f"{_plural(n, 'comuna')}.")
        else:
            cuerpo.append("Sin pronóstico de riesgo para hoy.")
        br = sum(1 for c in (risk.get("boton_rojo") or {})
                 if c.isdigit() and int(c) in region["comunas"])
        if br:
            cuerpo.append(f"CONAF mantiene Botón Rojo en {br} {_plural(br, 'comuna')}.")

    if fires is None:
        cuerpo.append("Sin datos de CONAF en este momento.")
    else:
        fuentes.append("CONAF (incendios)")
        activos = [f for f in fires if f.get("status") == "confirmado"
                   and _region_de(f.get("comuna"), f.get("region"), comuna_region, regiones) == region["code"]]
        if not activos:
            cuerpo.append("CONAF no informa incendios activos en la región.")
        else:
            detalles = [_detalle_incendio(f) for f in sorted(activos, key=lambda f: -(f.get("area_ha") or 0))]
            n = len(activos)
            if n <= 3:
                cuerpo.append(f"CONAF informa {n} {_plural(n, 'incendio activo', 'incendios activos')}: "
                              f"{_lista_y(detalles)}.")
            else:
                cuerpo.append(f"CONAF informa {n} incendios activos, entre ellos {_lista_y(detalles[:3])}.")

    if incidents is None:
        cuerpo.append("Sin datos del monitoreo satelital en este momento.")
    else:
        focos = [i for i in incidents if i.get("status") in FOCOS_ABIERTOS
                 and _region_de(i.get("comuna"), i.get("region"), comuna_region, regiones) == region["code"]]
        if focos:
            fuentes.append("BRASA (detecciones satelitales)")
            n = len(focos)
            cuerpo.append(f"El satélite sigue {n} {_plural(n, 'foco')} de calor sin confirmar.")

    cierre = "Si ves fuego o humo, llama al 132 (Bomberos)."
    fuente = f"Fuente: CONAF (Botón Rojo e incendios) y Open-Meteo vía BRASA al {hora}."

    def texto_con(partes: list[str]) -> str:
        return " ".join([f"{region['name']}:", *partes, cierre, fuente])

    # Si el bloque se pasa de 90 palabras se quitan las frases más prescindibles:
    # están ordenadas de menos a más esencial (satélite, incendios, Botón Rojo, riesgo).
    while len(cuerpo) > 1 and len(texto_con(cuerpo).split()) > MAX_PALABRAS:
        cuerpo = cuerpo[:-1]
    texto = texto_con(cuerpo)
    return {"region": region["name"], "texto": texto, "palabras": len(texto.split()), "fuentes": fuentes}


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

    regiones, comuna_region = load_territory()
    if args.region:
        wanted = fold(args.region)
        regiones = [r for r in regiones if r["fold"] == wanted]
        if not regiones:
            sys.exit(f"Región no encontrada: {args.region}. Usa uno de estos nombres: "
                     + ", ".join(r["name"] for r in load_territory()[0]))

    risk = fetch_json(f"{base}/api/risk" + (f"?day={args.fecha}" if args.fecha else ""))
    fires_payload = fetch_json(f"{base}/api/official-fires")
    incidents_payload = fetch_json(f"{base}/api/incidents")
    fires = fires_payload.get("fires") if fires_payload else None
    incidents = incidents_payload.get("incidents") if incidents_payload else None
    for ruta, payload in (("/api/risk", risk), ("/api/official-fires", fires_payload),
                          ("/api/incidents", incidents_payload)):
        if payload is None:
            print(f"Aviso: {ruta} no respondió; el bloque lo dirá al aire.", file=sys.stderr)

    hora = datetime.now(CHILE_TZ).strftime("%H:%M")
    bloques = [build_block(r, risk, fires, incidents, hora, comuna_region, regiones) for r in regiones]
    if args.json:
        print(json.dumps(bloques, ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(b["texto"] for b in bloques))
    return 0


if __name__ == "__main__":
    sys.exit(main())
