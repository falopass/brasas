#!/usr/bin/env python3
"""Mide cuántas de las 345 comunas cubre cada JSON de `web/data` (COB-01).

El patrón es `web/data/comunas-index.json`. Se miden los archivos que
identifican la comuna por código (`comunas` como lista de objetos con `code`,
`comunas` como objeto con claves de código, o `cells` con claves de código).
Los que la identifican por nombre, o que no tienen desglose por comuna,
quedan fuera.

    python scripts/local/cobertura_datos.py            reescribe docs/COBERTURA.md
    python scripts/local/cobertura_datos.py --check    sale 1 si una comuna cubierta se perdió
                                                       o un archivo con cadencia está vencido

`--check` usa la lista de faltantes versionada en el documento como línea base:
no falla por las faltantes históricas, pero sí cuando aparece una comuna que
antes estaba cubierta. Además compara la fecha de cada archivo declarado en
`CADENCIA` con hoy: un archivo vencido hace fallar `--check` (y el mensaje
nombra el script que lo regenera), uno «por vencer» o «sin fecha» solo avisa.
Sin red y solo con la biblioteca estándar.
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

# Días tolerados desde la fecha del archivo y el script que lo regenera.
# Un archivo sin entrada no tiene chequeo de frescura: queda «sin cadencia».
CADENCIA: dict[str, tuple[int, str]] = {
    "censo_2024.json": (3650, "scripts/local/build_censo.py"),
    "historia-comunas.json": (3650, "scripts/local/build_historia_comunas.py"),
    "incendios-nominados.json": (3650, "scripts/local/build_incendios_nominados.py"),
    "snaspe.json": (365, "scripts/local/build_snaspe.py"),
    "interfaz.json": (365, "scripts/local/build_interfaz.py"),
    "rain_normals.json": (365, "scripts/local/build_rain_normals.py"),
    "temporada-2526.json": (365, "scripts/local/build_temporada_2526.py"),
    "calibracion.json": (180, "scripts/local/medir_adelanto.py"),
}

# Fracción de la cadencia restante bajo la cual un archivo se avisa «por vencer».
POR_VENCER = 0.15

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


def momento(payload: dict) -> datetime | None:
    """Fecha legible del archivo: `fetched_at`, `generated_at` o `source.fetched_at`."""
    valor = payload.get("fetched_at") or payload.get("generated_at")
    if not isinstance(valor, str) or not valor:
        fuente = payload.get("source")
        valor = fuente.get("fetched_at") if isinstance(fuente, dict) else None
    if not isinstance(valor, str) or not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def fecha(payload: dict) -> str:
    """La fecha de `momento`, en UTC y legible; el valor crudo o `—` si no hay."""
    instante = momento(payload)
    if instante is None:
        valor = payload.get("fetched_at") or payload.get("generated_at")
        return valor if isinstance(valor, str) and valor else "—"
    if instante.tzinfo:
        instante = instante.astimezone(timezone.utc)
    return instante.strftime("%Y-%m-%d %H:%M UTC")


def frescura(archivo: str, payload: dict, hoy: datetime) -> dict:
    """Edad y estado del archivo contra su cadencia declarada en `CADENCIA`."""
    instante = momento(payload)
    if instante is not None:
        if instante.tzinfo is None:
            instante = instante.replace(tzinfo=timezone.utc)
        edad = (hoy - instante.astimezone(timezone.utc)).days
    else:
        edad = None
    entrada = CADENCIA.get(archivo)
    if entrada is None:
        estado = "sin fecha" if edad is None else "sin cadencia"
        return {"vencimiento_dias": None, "dias_de_edad": edad, "estado": estado, "regenera": None}
    vencimiento, script = entrada
    if edad is None:
        estado = "sin fecha"
    elif edad > vencimiento:
        estado = "vencido"
    elif vencimiento - edad < vencimiento * POR_VENCER:
        estado = "por vencer"
    else:
        estado = "al día"
    return {"vencimiento_dias": vencimiento, "dias_de_edad": edad, "estado": estado, "regenera": script}


def medir(data_dir: Path = DATA) -> tuple[list[dict], list[dict]]:
    """Filas por archivo medido y el índice de comunas usado como patrón."""
    indice = json.loads((data_dir / INDEX).read_text(encoding="utf-8"))
    por_codigo = {int(comuna["code"]): comuna for comuna in indice}
    patron = set(por_codigo)
    hoy = datetime.now(timezone.utc)
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
                **frescura(ruta.name, payload, hoy),
            }
        )
    return filas, indice


def agrupar(faltantes: list[dict]) -> list[tuple[str, list[str]]]:
    """Regiones en orden alfabético, con sus comunas faltantes ordenadas."""
    grupos: dict[str, list[str]] = defaultdict(list)
    for comuna in faltantes:
        grupos[comuna["region"]].append(comuna["name"])
    return [(region, sorted(nombres)) for region, nombres in sorted(grupos.items())]


def celda_estado(fila: dict) -> str:
    """Texto de la columna Estado: cuántos días lleva vencido y qué lo regenera."""
    if fila["estado"] == "vencido":
        atraso = fila["dias_de_edad"] - fila["vencimiento_dias"]
        return f"vencido (hace {atraso} días; regenera `{fila['regenera']}`)"
    if fila["estado"] == "por vencer":
        return f"por vencer (quedan {fila['vencimiento_dias'] - fila['dias_de_edad']} días)"
    return fila["estado"]


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
        "La columna «Estado» compara la fecha del archivo con la cadencia declarada en "
        "`CADENCIA` (en `scripts/local/cobertura_datos.py`): «al día», «por vencer» "
        "(queda menos del 15 % de la cadencia), «vencido» (ya pasó; `--check` falla y "
        "nombra el script que lo regenera), «sin fecha» (el archivo no trae marca "
        "legible) y «sin cadencia» (no hay cadencia declarada para ese archivo).",
        "",
        "| Archivo | Cubiertas | Faltantes | Generado | Estado |",
        "|---|---:|---:|---|---|",
    ]
    for fila in filas:
        lineas.append(
            f"| `{fila['archivo']}` | {fila['cubiertas']}/{total} | {len(fila['faltantes'])} | {fila['fecha']} | {celda_estado(fila)} |"
        )
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


def vencimientos(data_dir: Path = DATA) -> tuple[list[str], list[str]]:
    """Fallas por archivos vencidos y avisos por los por vencer o sin fecha."""
    hoy = datetime.now(timezone.utc)
    problemas, avisos = [], []
    for archivo in sorted(CADENCIA):
        ruta = data_dir / archivo
        if not ruta.exists():
            continue
        payload = json.loads(ruta.read_text(encoding="utf-8"))
        fila = frescura(archivo, payload, hoy)
        estado, edad, vencimiento = fila["estado"], fila["dias_de_edad"], fila["vencimiento_dias"]
        if estado == "vencido":
            problemas.append(f"{archivo}: vencido hace {edad - vencimiento} día(s); regenéralo con `{fila['regenera']}`")
        elif estado == "por vencer":
            avisos.append(f"{archivo}: por vencer (quedan {vencimiento - edad} de {vencimiento} días); regenéralo con `{fila['regenera']}`")
        elif estado == "sin fecha":
            avisos.append(f"{archivo}: sin fecha legible; no se puede saber si está vencido")
    return problemas, avisos


def main(argv: list[str] | None = None, *, data_dir: Path = DATA, doc: Path = DOC) -> int:
    parser = argparse.ArgumentParser(description="Mide la cobertura por comuna de web/data.")
    parser.add_argument(
        "--check", action="store_true", help="sale 1 si una comuna que estaba cubierta dejó de estarlo o un archivo está vencido"
    )
    args = parser.parse_args(argv)
    if args.check:
        problemas, avisos = vencimientos(data_dir)
        problemas += comprobar(data_dir, doc)
        for aviso in avisos:
            print(f"  ! {aviso}")
        if problemas:
            print("Cobertura de datos: hay problemas.", file=sys.stderr)
            for problema in problemas:
                print(f"  ✗ {problema}", file=sys.stderr)
            return 1
        print("Cobertura de datos: OK, ninguna comuna perdida ni archivo vencido.")
        return 0
    filas = escribir_doc(data_dir, doc)
    for fila in filas:
        print(f"  {fila['archivo']}: {fila['cubiertas']} cubiertas, {len(fila['faltantes'])} faltantes")
    print(f"Escrito {doc}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
