#!/usr/bin/env python3
"""Mide cuántas de las 345 comunas cubre cada JSON de `web/data` (COB-01).

El patrón es `web/data/comunas-index.json`. Se miden los archivos que
identifican la comuna por código (`comunas` como lista de objetos con `code`,
`comunas` como objeto con claves de código, o `cells` con claves de código).
Los que la identifican por nombre, o que no tienen desglose por comuna,
quedan fuera.

    python scripts/local/cobertura_datos.py            reescribe docs/COBERTURA.md
    python scripts/local/cobertura_datos.py --check    sale 1 si una comuna cubierta se perdió

`--check` usa la lista de faltantes versionada en el documento como línea base:
no falla por las faltantes históricas, pero sí cuando aparece una comuna que
antes estaba cubierta. Sin red y solo con la biblioteca estándar.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "web" / "data"
DOC = ROOT / "docs" / "COBERTURA.md"
INDEX = "comunas-index.json"

SECCION = re.compile(r"^### `([^`]+)`")
FALTANTE = re.compile(r"^- \*\*(.+?) \((\d+)\):\*\* (.+)$")
TOTAL_TABLA = re.compile(r"^\| `[^`]+` \| \d+/(\d+) \|")


def codigos(payload: object) -> set[int] | None:
    """Códigos de comuna del archivo, o None si no tiene desglose por comuna."""
    if not isinstance(payload, dict):
        return None
    for clave in ("comunas", "cells"):
        valor = payload.get(clave)
        if isinstance(valor, list):
            encontrados = {int(item["code"]) for item in valor if isinstance(item, dict) and "code" in item}
        elif isinstance(valor, dict):
            encontrados = {int(k) for k in valor if str(k).isdigit()}
        else:
            continue
        if encontrados:
            return encontrados
    return None


def fecha(payload: dict) -> str:
    """`fetched_at` o `generated_at`, en UTC y legible; `—` si no hay."""
    valor = payload.get("fetched_at") or payload.get("generated_at")
    if not isinstance(valor, str) or not valor:
        return "—"
    try:
        momento = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return valor
    if momento.tzinfo:
        momento = momento.astimezone(timezone.utc)
    return momento.strftime("%Y-%m-%d %H:%M UTC")


def medir(data_dir: Path = DATA) -> tuple[list[dict], list[dict]]:
    """Filas por archivo medido y el índice de comunas usado como patrón."""
    indice = json.loads((data_dir / INDEX).read_text(encoding="utf-8"))
    por_codigo = {int(comuna["code"]): comuna for comuna in indice}
    patron = set(por_codigo)
    filas = []
    for ruta in sorted(data_dir.glob("*.json")):
        if ruta.name == INDEX:
            continue
        payload = json.loads(ruta.read_text(encoding="utf-8"))
        cubiertos = codigos(payload)
        if cubiertos is None:
            continue
        faltantes = [por_codigo[code] for code in sorted(patron - cubiertos)]
        filas.append(
            {
                "archivo": ruta.name,
                "cubiertas": len(cubiertos & patron),
                "faltantes": faltantes,
                "fecha": fecha(payload),
            }
        )
    return filas, indice


def agrupar(faltantes: list[dict]) -> list[tuple[str, list[str]]]:
    """Regiones en orden alfabético, con sus comunas faltantes ordenadas."""
    grupos: dict[str, list[str]] = defaultdict(list)
    for comuna in faltantes:
        grupos[comuna["region"]].append(comuna["name"])
    return [(region, sorted(nombres)) for region, nombres in sorted(grupos.items())]


def render(filas: list[dict], indice: list[dict]) -> str:
    total = len(indice)
    lineas = [
        "# Cobertura de datos por comuna",
        "",
        f"Cuántas de las {total} comunas de `web/data/comunas-index.json` cubre cada archivo de "
        "`web/data`. Una comuna faltante es una sección de la ficha que no se puede pintar: "
        "`#/riesgo` para la exposición y `#/temporada` para la temporada, por ejemplo.",
        "",
        "Se miden los archivos que identifican la comuna por código; los que la agrupan por "
        "nombre o no tienen desglose por comuna quedan fuera.",
        "",
        "Generado por `scripts/local/cobertura_datos.py`; no editar a mano. "
        "Las faltantes de esta tabla quedan documentadas: `--check` no falla por ellas, "
        "solo si una comuna que estaba cubierta deja de estarlo.",
        "",
        "| Archivo | Cubiertas | Faltantes | Generado |",
        "|---|---:|---:|---|",
    ]
    for fila in filas:
        lineas.append(f"| `{fila['archivo']}` | {fila['cubiertas']}/{total} | {len(fila['faltantes'])} | {fila['fecha']} |")
    lineas += ["", "## Faltantes por archivo", ""]
    for fila in filas:
        lineas.append(f"### `{fila['archivo']}` — {fila['cubiertas']}/{total}")
        lineas.append("")
        if not fila["faltantes"]:
            lineas.append("Sin faltantes.")
        else:
            for region, nombres in agrupar(fila["faltantes"]):
                lineas.append(f"- **{region} ({len(nombres)}):** {', '.join(nombres)}")
        lineas.append("")
    return "\n".join(lineas).rstrip() + "\n"


def escribir_doc(data_dir: Path = DATA, doc: Path = DOC) -> list[dict]:
    filas, indice = medir(data_dir)
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(render(filas, indice), encoding="utf-8")
    return filas


def leer_documentado(doc: Path, indice: list[dict]) -> tuple[dict[str, set[int]], int | None]:
    """Faltantes por archivo y total de comunas según `docs/COBERTURA.md`."""
    por_nombre = {comuna["name"]: int(comuna["code"]) for comuna in indice}
    documentado: dict[str, set[int]] = {}
    total = None
    actual: str | None = None
    for linea in doc.read_text(encoding="utf-8").splitlines():
        if total is None:
            tabla = TOTAL_TABLA.match(linea)
            if tabla:
                total = int(tabla.group(1))
        seccion = SECCION.match(linea)
        if seccion:
            actual = seccion.group(1)
            documentado[actual] = set()
            continue
        if linea.startswith("## "):
            actual = None
            continue
        faltante = FALTANTE.match(linea)
        if not faltante or actual is None:
            continue
        region, cuantas, nombres = faltante.group(1), int(faltante.group(2)), faltante.group(3)
        items = [nombre.strip() for nombre in nombres.split(",")]
        if len(items) != cuantas:
            raise ValueError(f"{doc}: {actual}, {region}: dice {cuantas} y lista {len(items)}")
        for nombre in items:
            if nombre not in por_nombre:
                raise ValueError(f"{doc}: {actual}: comuna desconocida: {nombre!r}")
            documentado[actual].add(por_nombre[nombre])
    return documentado, total


def comprobar(data_dir: Path = DATA, doc: Path = DOC) -> list[str]:
    """Problemas de cobertura contra el documento; vacío si no se perdió ninguna comuna."""
    if not doc.exists():
        return [f"no existe {doc}; corre el script sin --check para generarlo"]
    filas, indice = medir(data_dir)
    try:
        documentado, total = leer_documentado(doc, indice)
    except ValueError as error:
        return [str(error)]
    if total is not None and len(indice) != total:
        return [f"comunas-index.json pasó de {total} a {len(indice)} comunas; corre el script sin --check para actualizar el patrón"]
    problemas = []
    actuales = {fila["archivo"]: {int(c["code"]) for c in fila["faltantes"]} for fila in filas}
    for fila in filas:
        archivo = fila["archivo"]
        if archivo not in documentado:
            problemas.append(f"{archivo}: no está en {doc.name}; corre el script sin --check")
            continue
        perdidas = actuales[archivo] - documentado[archivo]
        if perdidas:
            nombres = sorted(f"{comuna['name']} ({comuna['region']})" for comuna in indice if int(comuna["code"]) in perdidas)
            problemas.append(f"{archivo}: perdió {len(perdidas)} comuna(s): {', '.join(nombres)}")
    for archivo in documentado:
        if archivo not in actuales:
            problemas.append(f"{archivo}: desapareció de web/data o ya no tiene desglose por comuna")
    return problemas


def main(argv: list[str] | None = None, *, data_dir: Path = DATA, doc: Path = DOC) -> int:
    parser = argparse.ArgumentParser(description="Mide la cobertura por comuna de web/data.")
    parser.add_argument("--check", action="store_true", help="sale 1 si una comuna que estaba cubierta dejó de estarlo")
    args = parser.parse_args(argv)
    if args.check:
        problemas = comprobar(data_dir, doc)
        if problemas:
            print("Cobertura de datos: hay problemas.", file=sys.stderr)
            for problema in problemas:
                print(f"  ✗ {problema}", file=sys.stderr)
            return 1
        print("Cobertura de datos: OK, ninguna comuna perdida.")
        return 0
    filas = escribir_doc(data_dir, doc)
    for fila in filas:
        print(f"  {fila['archivo']}: {fila['cubiertas']} cubiertas, {len(fila['faltantes'])} faltantes")
    print(f"Escrito {doc}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
