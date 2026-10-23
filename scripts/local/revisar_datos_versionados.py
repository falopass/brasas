"""Sonda de frescura de los datos versionados del frontend (AUTO-45).

Recorre ``web/data`` (``*.json`` y ``*.geojson``), lee la fecha que cada archivo declara —``fetched_at`` o
``generated_at`` en la raíz o dentro de ``source``, las dos convenciones del repo— y la
compara con su caducidad en ``CADUCIDAD_DIAS``. Cada archivo queda en un estado:

- ``vigente``       edad dentro de la caducidad
- ``vencido``       edad mayor que la caducidad: la foto está vieja y hay que regenerarla
- ``sin-reloj``     tiene política pero el archivo no declara una fecha legible
- ``sin-politica``  ni caduca ni está exento: un dato nuevo no entra sin política
- ``exento``        lista explícita (catálogos históricos y máscaras curadas): se informan
- ``ilegible``      el JSON no se pudo parsear

Uso:  python scripts/local/revisar_datos_versionados.py [--hoy AAAA-MM-DD] [--json]
                                                      [--data-dir DIR] [--alerta-md RUTA]

Sale 1 solo si hay algún ``vencido`` (0 si todos están al día; 2 si la sonda misma falló:
directorio inexistente o sin JSONs — sin datos no hay veredicto). Con ``--alerta-md`` escribe
ahí el cuerpo del issue cuando hay vencidos, y en CI deja ``alerta``/``titulo`` en
GITHUB_OUTPUT: el workflow datos-versionados.yml abre —o reutiliza— un issue «datos».
La sonda mide; regenerar los datos es otro trabajo (ver docs/DATOS_VERSIONADOS.md).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "web" / "data"

# Días que puede tener una foto antes de vencer. La temporada en curso cambia a diario y la
# calibración se re-mide cada temporada; el resto son fotos que bastan una vez al año.
# Un archivo nuevo que no calce con ningún patrón sale «sin-politica», y el inventario de
# tests/test_revisar_datos_versionados.py obliga a declararlo aquí o en EXENTOS.
CADUCIDAD_DIAS = {
    "temporada-*.json": 45,
    "calibracion.json": 120,
    "censo_2024.json": 365,
    "rain_normals.json": 365,
    "interfaz.json": 365,
    "snaspe.json": 365,
    "historia-comunas.json": 365,
    "incendios-nominados.json": 365,
    "prioritarias.json": 365,
    "comunas.geojson": 365,
    "regiones.geojson": 365,
    "comunas-index.json": 365,
}

# Archivos que no caducan por calendario, con el porqué: se informan como exentos, no se esconden.
EXENTOS = {
    "cases.json": "catálogo histórico curado: cada caso lleva sus propias fechas",
    "cases/*.json": "casos históricos: se actualizan con evidencia nueva, no por calendario",
    "persistent_hotspots.json": "cada punto declara su propio valid_from/valid_to",
    "privacidad.json": "texto legal versionado con la app, no una foto de datos: cambia cuando cambia la política",
    "licencias.json": "atribución de las capas, espejo de docs/FUENTES.md: texto curado, no una foto de datos",
    "mascara-norte.json": "cada celda declara su propio revisar_el (INV-25/DET-45)",
}

# Qué regenera cada foto (va en la tabla y en el cuerpo del issue).
REGENERA = {
    "temporada-*.json": "python scripts/local/build_temporada_2526.py --refresh",
    "calibracion.json": "python scripts/local/medir_adelanto.py",
    "censo_2024.json": "python scripts/local/build_censo.py",
    "rain_normals.json": "python scripts/local/build_rain_normals.py",
    "interfaz.json": "python scripts/local/build_interfaz.py",
    "snaspe.json": "python scripts/local/build_snaspe.py",
    "historia-comunas.json": "python scripts/local/build_historia_comunas.py",
    "incendios-nominados.json": "python scripts/local/build_incendios_nominados.py",
    "prioritarias.json": "a mano, cuando CONAF publique el listado oficial (ver `note` del JSON)",
    "comunas.geojson": "python scripts/build_territory.py",
    "regiones.geojson": "python scripts/build_territory.py",
    "comunas-index.json": "python scripts/build_territory.py",
}

# Orden de la tabla: primero lo que pide acción.
ORDEN = {"vencido": 0, "ilegible": 1, "sin-politica": 2, "sin-reloj": 3, "vigente": 4, "exento": 5}


def _patron(tabla: dict, nombre: str) -> str | None:
    """Primer patrón fnmatch de la tabla que calza con el nombre (ruta relativa con '/')."""
    return next((p for p in tabla if fnmatch.fnmatch(nombre, p)), None)


def _marca(data: object) -> datetime | None:
    """Primera fecha legible del payload: fetched_at/generated_at en la raíz o en `source`."""
    if not isinstance(data, dict):
        return None
    fuente = data.get("source")
    for d in (data, fuente if isinstance(fuente, dict) else {}):
        for clave in ("fetched_at", "generated_at"):
            valor = d.get(clave)
            if not isinstance(valor, str) or not valor:
                continue
            try:
                m = datetime.fromisoformat(valor.replace("Z", "+00:00"))
            except ValueError:
                continue
            return m if m.tzinfo else m.replace(tzinfo=timezone.utc)
    return None


def revisar(data_dir: Path, hoy: datetime) -> list[dict]:
    """Clasifica cada dato de data_dir (*.json y *.geojson, recursivo) según edad y política."""
    filas = []
    for p in sorted(q for q in data_dir.rglob("*.*") if q.suffix in (".json", ".geojson")):
        rel = p.relative_to(data_dir).as_posix()
        fila: dict = {"archivo": rel}
        exento = _patron(EXENTOS, rel)
        if exento:
            fila.update(estado="exento", motivo=EXENTOS[exento])
            filas.append(fila)
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fila["estado"] = "ilegible"
            filas.append(fila)
            continue
        politica = _patron(CADUCIDAD_DIAS, rel)
        if politica is None:
            fila["estado"] = "sin-politica"
            filas.append(fila)
            continue
        fila["caducidad_dias"] = CADUCIDAD_DIAS[politica]
        regenera = _patron(REGENERA, rel)
        if regenera:
            fila["regenerar"] = REGENERA[regenera]
        marca = _marca(data)
        if marca is None:
            fila["estado"] = "sin-reloj"
            filas.append(fila)
            continue
        edad = (hoy - marca).days
        fila.update(fecha=marca.isoformat(), edad_dias=edad)
        fila["estado"] = "vencido" if edad > fila["caducidad_dias"] else "vigente"
        filas.append(fila)
    return filas


def _resumen(filas: list[dict]) -> dict[str, int]:
    resumen: dict[str, int] = {}
    for f in filas:
        resumen[f["estado"]] = resumen.get(f["estado"], 0) + 1
    return resumen


def imprimir(filas: list[dict], hoy: datetime) -> None:
    print(f"Frescura de los datos versionados (web/data) — referencia {hoy.date().isoformat()} UTC\n")
    ancho = max(len(f["archivo"]) for f in filas)
    for f in sorted(filas, key=lambda f: (ORDEN.get(f["estado"], 9), f["archivo"])):
        edad = f"{f['edad_dias']} d" if "edad_dias" in f else "—"
        caduca = f"{f['caducidad_dias']} d" if "caducidad_dias" in f else "—"
        detalle = f.get("regenerar") or f.get("motivo") or "declara su caducidad o exento en la tabla"
        print(f"{f['archivo']:<{ancho}}  {f['estado']:<12} {edad:>7} /{caduca:>6}  {f.get('fecha', '—'):<26} {detalle}")
    r = _resumen(filas)
    print(
        f"\nResumen: {r.get('vigente', 0)} vigentes · {r.get('vencido', 0)} vencidos · "
        f"{r.get('sin-reloj', 0)} sin reloj · {r.get('exento', 0)} exentos · "
        f"{r.get('sin-politica', 0)} sin política · {r.get('ilegible', 0)} ilegibles"
    )
    if r.get("vencido"):
        nombres = ", ".join(f["archivo"] for f in filas if f["estado"] == "vencido")
        print(f"VENCIDOS: {nombres}")
    else:
        print("OK: ningún dato versionado venció")


def cuerpo_issue(filas: list[dict], hoy: datetime) -> str:
    """Cuerpo de alerta.md para el issue que abre el workflow."""
    vencidos = [f for f in filas if f["estado"] == "vencido"]
    lineas = [
        "## Datos versionados vencidos",
        "",
        f"La sonda semanal de `web/data/` (AUTO-45) encontró {len(vencidos)} archivo(s) más "
        f"viejo(s) que su caducidad, al {hoy.date().isoformat()} UTC:",
        "",
        "| archivo | fecha declarada | edad | caducidad | cómo regenerarlo |",
        "|---|---|---|---|---|",
    ]
    for f in vencidos:
        lineas.append(f"| `{f['archivo']}` | {f['fecha']} | {f['edad_dias']} d | {f['caducidad_dias']} d | `{f.get('regenerar', '—')}` |")
    otros = [f for f in filas if f["estado"] in ("sin-reloj", "sin-politica", "ilegible")]
    if otros:
        lineas.append("\nTambién conviene mirar:")
        lineas += [f"- `{f['archivo']}` — {f['estado']}" for f in otros]
    lineas += [
        "",
        "Qué hacer paso a paso: `docs/DATOS_VERSIONADOS.md`.",
        "",
        "Mientras este issue siga abierto la sonda no crea otros; ciérralo cuando los datos se regeneren.",
    ]
    if os.environ.get("GITHUB_RUN_ID"):
        run = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        lineas.append(f"\nCorrida: {run}")
    return "\n".join(lineas)


def _github_output(vencidos: list[dict]) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    titulo = ""
    if vencidos:
        nombres = ", ".join(f["archivo"] for f in vencidos)
        titulo = f"Datos versionados vencidos ({len(vencidos)}): {nombres}"[:200]
    with open(out, "a", encoding="utf-8") as f:
        f.write(f"alerta={'true' if vencidos else 'false'}\n")
        f.write(f"titulo={titulo}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hoy", metavar="AAAA-MM-DD", help="fecha de referencia (omisión: hoy UTC)")
    ap.add_argument("--data-dir", type=Path, default=DATA, help="carpeta a revisar (omisión: web/data)")
    ap.add_argument("--json", action="store_true", dest="como_json", help="salida en JSON")
    ap.add_argument(
        "--alerta-md",
        metavar="RUTA",
        type=Path,
        help="si hay vencidos, escribe ahí el cuerpo del issue (lo usa el workflow)",
    )
    args = ap.parse_args(argv)

    hoy = datetime.now(timezone.utc)
    if args.hoy:
        try:
            m = datetime.fromisoformat(args.hoy)
        except ValueError:
            ap.error(f"--hoy no es una fecha ISO: {args.hoy!r}")
        hoy = m if m.tzinfo else m.replace(tzinfo=timezone.utc)

    if not args.data_dir.is_dir():
        print(f"::error::no existe el directorio {args.data_dir}")
        return 2
    filas = revisar(args.data_dir, hoy)
    if not filas:
        print(f"::error::{args.data_dir} no tiene JSONs que revisar")
        return 2

    if args.como_json:
        print(
            json.dumps(
                {"hoy": hoy.date().isoformat(), "archivos": filas, "resumen": _resumen(filas)},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        imprimir(filas, hoy)

    vencidos = [f for f in filas if f["estado"] == "vencido"]
    if vencidos and args.alerta_md:
        args.alerta_md.write_text(cuerpo_issue(filas, hoy), encoding="utf-8")
    _github_output(vencidos)
    return 1 if vencidos else 0


if __name__ == "__main__":
    sys.exit(main())
