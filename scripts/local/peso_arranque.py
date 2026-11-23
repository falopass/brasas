"""Peso del arranque de BRASA: lo que el navegador descarga antes de poder
mostrar y usar la aplicación (QA-62).

Es el presupuesto de peso del arranque: `presupuesto_peso.py` mide aparte las
páginas que se descargan solo cuando se piden (DEBT-07).
Este script parte de web/index.html, toma la portada y las referencias que
bloquean el arranque —<link rel="stylesheet">, <link rel="preload" as="font">
y <script type="module" src>— y sigue los imports relativos de esos módulos
de forma transitiva (se ignoran web/vendor y lo externo, igual que en
tests/test_estaticas_guardas.py).

Separa dos conjuntos y no esconde ninguno:
- «bloqueante»: lo alcanzable por imports estáticos (`import … from`,
  `export … from` e `import '…'`). Es lo que el navegador descarga y parsea
  antes del primer pintado; se mide contra PRESUPUESTO_ARRANQUE_KB.
- «diferido»: lo alcanzable solo por `import('…')` desde el arranque. No
  bloquea el primer pintado, pero se informa siempre y suma al total, que
  tiene su propio tope (PRESUPUESTO_TOTAL_KB) para que no crezca sin control.

    python scripts/local/peso_arranque.py            verifica ambos umbrales
    python scripts/local/peso_arranque.py --informe  tabla completa, siempre termina en 0
    python scripts/local/peso_arranque.py --json     medición en JSON
    python scripts/local/peso_arranque.py --build    mide el build servido (web/ minificado, OPS-06)

Medido el 2026-10-22: 133,9 KB gzip de bloqueante y 238,6 KB de total.
Presupuestos: 183 KB bloqueante y 325 KB
total. Si el crecimiento es intencional, súbelo aquí y explica por qué en el
CHANGELOG; si no, recorta el arranque o mueve la vista a carga diferida.

Con --build el script construye web/ en un directorio temporal con
`node deploy/cloudflare/build-web.mjs --salida <tmp>/web` (el mismo paso del
despliegue, OPS-06) y mide esa copia contra PRESUPUESTO_ARRANQUE_BUILD_KB y
PRESUPUESTO_TOTAL_BUILD_KB: son los topes que mandan en producción, porque lo
que se sirve viaja minificado. El modo por defecto mide el fuente y conserva
sus topes históricos, para `dev.py check` local.

Este es el tope del arranque. El de las páginas que no se abren desde
index.html (lite, lista, pantalla, respuesta…) está en
scripts/local/presupuesto_peso.py, para que una página nueva no compita con
lo que bloquea el primer pintado (DEBT-07).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Medido el 2026-10-25 tras las olas de funciones (mapa, popup, ui, incendio,
# zona, css y los controles de MAPA-164): 170,2 KB gzip bloqueantes — el tope con
# holgura quedaba en 170 KB y ya no cabía ni una regla de CSS. Sube a 181 KB para
# devolver la holgura de ~10 KB a la próxima vista; OPS-06 sigue pendiente y es
# el que debe bajar este número, no seguir subiéndolo.
# 2026-11-05: 172,5 KB medidos — la ficha de sotavento (bloqueante vía zona.js) y
# la geometría de manchas en util.js agotaron la holgura; sube a 183 para
# reponer ~10 KB. OPS-06 sigue siendo quien debe bajarlo.
# 2026-11-08: 173,7 KB medidos — el fix MAPA-168 (aplazar setPadding/easeTo al
# moveend para no cortar el flyTo) sumó ~0,3 KB en map.js/popup.js y cruzó el tope
# con holgura; sube a 184 para reponer ~10 KB. OPS-06 sigue siendo el dueño de bajarlo.
# 2026-11-10: 174,0 KB medidos — a main le quedaban 91 bytes de holgura y CARGA-UI
# (el arranque monta con la configuración guardada) suma ~0,1 KB en app.js; sube a
# 185 para reponer ~10 KB. OPS-06 sigue siendo el dueño de bajarlo.
# 2026-11-11: 175,1 KB medidos — AGUA-04 (aviso de aluvión en la interfaz) suma
# ~0,9 KB entre ui.js, zona.js y alertas.js; sube a 186 para reponer ~10 KB.
# OPS-06 sigue siendo el dueño de bajarlo.
# 2026-11-16: 175,6 KB medidos con los cimientos y el carril del mapa del rediseño
# «Isoterma 2» (focos por potencia, barra de controles, leyenda en rampa); sube a 192
# para que quepan los tres carriles que faltan con ~10 KB de holgura. OPS-06 sigue
# siendo el dueño de bajarlo.
# 2026-11-19: 182,3 KB medidos con las capas satelitales NASA GIBS (MAPA-180: gibs.js
# entra al grafo estático y map.js suma el bloque de fuentes y layers); a main le
# quedaban 3,0 KB de holgura y la capa nueva lo cruza por ~0,3 KB; sube a 193 para
# reponer ~10 KB. OPS-06 sigue siendo el dueño de bajarlo.
# 2026-11-19: 183,2 KB medidos con el plan municipal de Quintero (PROD-05:
# municipios.js entra al grafo estático de zona.js y la tarjeta suma ~0,7 KB gzip);
# a main le quedaban ~0,5 KB de holgura y el enlace lo cruza por ~0,2 KB; sube a 194
# para reponer ~10 KB. OPS-06 sigue siendo el dueño de bajarlo.
# 2026-11-19: 161,6 KB medidos tras sacar del arranque la vista de incendio
# (PERF-11: INCIDENT/incidentInfo/enlazarSeguimiento pasan a web/js/incidente.js,
# módulo liviano; views/incendio.js queda en carga diferida como el resto de las
# vistas). Baja de 194 a 175 para devolver ~3,5 KB de holgura a las próximas
# vistas sin acercarse al tope con holgura (165 KB). OPS-06 sigue siendo el dueño
# de bajarlo.
PRESUPUESTO_ARRANQUE_KB = 175  # bloqueante: lo que se descarga antes del primer pintado
# 2026-11-04: el tope total sube a 315 KB gzip para alojar las vistas diferidas
# y capas nuevas (Riesgo 3 capas + MINVU, Pyrocast, SNASPE, terreno/lluvia,
# Calidad, la etiqueta de Landsat en util.js, la ficha de verdor satelital
# (RISK-11), el comparador de casos, las cicatrices 2014-2024 en zona.js y el
# popup del mapa, y la ficha de sotavento).
# 2026-11-05: sube a 325 con la medición ya en ~315 KB tras esa misma ola.
# 2026-11-16: 327,1 KB medidos con los cimientos del rediseño «Isoterma 2» (barra de
# pestañas, cruce de la hoja, entradas por tipo de pieza y arrastre de la hoja desde su
# contenido). Sube a 345 para alojar los cuatro carriles del rediseño (mapa y fuego,
# portada, riesgo e historia, páginas de apoyo); lo bloqueante sigue en su tope de 186.
# 2026-11-19: 345,4 KB medidos con PERF-12 (en teléfonos el motor del mapa espera la
# primera interacción o ~8 s en vez de calentarse en cada vista; ~0,2 KB gzip en app.js).
# Entra en el tope 346 vigente; el bloqueante queda en 162,4 de 175.
# 2026-11-19: 354,7 KB medidos tras PERF-14 (#927) con la cola de mejoras web en
# paralelo: #932 (módulos JS en red primero y recarga única tras un deploy, +0,6 KB
# gzip), #930 (PERF-15: Riesgo e Historia pintan antes del motor del mapa, +0,2 KB) y
# #933 (ALR-44: la lectura de seguimientos no pisa el estado tras un clic, +0,05 KB)
# suman ~1,3 KB y no caben en el tope 347 por ~0,3 KB (proyección 355,6 KB). Sube a 348
# para alojarlos con ~0,7 KB de holgura; OPS-06 sigue siendo el dueño de bajarlo y hay
# un ahorro real de peso (no comentarios) en camino para volver a subir la holgura.
PRESUPUESTO_TOTAL_KB = 348  # bloqueante + diferido; evita que lo diferido crezca sin control

# 2026-11-19 (OPS-06): producción ya no sirve el fuente: el despliegue minifica
# web/js y web/css con esbuild (deploy/cloudflare/build-web.mjs) y el presupuesto
# que manda es el del build. Medido sobre main 8de31ed con
# `node deploy/cloudflare/build-web.mjs --salida <tmp>/web` y `peso_arranque.py
# --raiz <tmp>`: 112,6 KB gzip bloqueantes, 130,9 KB diferidos y 243,4 KB de
# total. Topes con ~10 % de holgura: 125 KB bloqueante (11 % sobre lo medido) y
# 265 KB total (~9 %). El modo por defecto (fuente) conserva sus topes
# históricos 175/348 para `dev.py check`; en CI el que bloquea es este, medido
# en el job `web` de tests.yml con `--build`.
# 2026-11-23 (MAPA-187): tras la ola de capas diferidas del mapa (GWIS,
# WorldCover, relieve 3D, WUI CONAF, respaldo sin conexión y viento 0,25° con
# interpolación bilineal y pasos horarios), el build servido midió 267,2 KB
# gzip en total (el bloqueante sigue bajo 125 KB). Sube el tope total del build
# de 265 a 275 KB (~3 % de holgura) manteniendo intacto el tope bloqueante.
PRESUPUESTO_ARRANQUE_BUILD_KB = 125  # bloqueante del build servido (minificado)
PRESUPUESTO_TOTAL_BUILD_KB = 275  # bloqueante + diferido del build servido

# Referencias que bloquean el arranque dentro de index.html, en el orden en
# que el navegador las encuentra: cada entrada es (grupo, regex del tag).
_REF_TAGS = [
    ("css", re.compile(r'<link\b[^>]*rel=["\']stylesheet["\'][^>]*>', re.I)),
    ("fuente", re.compile(r'<link\b[^>]*rel=["\']preload["\'][^>]*as=["\']font["\'][^>]*>', re.I)),
    ("js", re.compile(r'<script\b[^>]*type=["\']module["\'][^>]*>', re.I)),
]
_ATTR = re.compile(r'\b(?:src|href)\s*=\s*["\']([^"\']+)["\']')

# Imports que bloquean el arranque: `import … from '…'`, `export … from '…'`
# e `import '…'`. Los `import('…')` dinámicos se miden aparte. Solo se
# siguen las rutas relativas.
# OPS-06: el web/ desplegado viaja minificado, donde `import{…}from"…"` no
# lleva espacios; las dos formas (con y sin espacio) tienen que leerse igual.
_IMPORT_DESDE = re.compile(r"\b(?:import|export)\b[^'\";]*?\bfrom\s*[\"']([^\"']+)[\"']")
_IMPORT_LADO = re.compile(r"\bimport\s*[\"']([^\"']+)[\"']")
_IMPORT_ESTATICO = (_IMPORT_DESDE, _IMPORT_LADO)
# Imports diferidos: `import('…')`, que el navegador pide solo al ejecutarse.
_IMPORT_DINAMICO = re.compile(r"\bimport\s*\(\s*[\"']([^\"']+)[\"']")

PISTA = (
    "Si el crecimiento es intencional, sube el umbral en "
    "scripts/local/peso_arranque.py y explica por qué en el CHANGELOG; "
    "si no, recorta el arranque o mueve la vista a carga diferida. Las páginas "
    "que no se abren desde index.html se miden aparte, en "
    "scripts/local/presupuesto_peso.py."
)


def _resolver(raiz: Path, ref: str, base: Path) -> Path | None:
    """Convierte una referencia del HTML en un archivo local, o None si es
    externa (https://…, //cdn…) o apunta fuera del repo."""
    if re.match(r"(?:https?:)?//", ref):
        return None
    ruta = (raiz / ref.lstrip("/")).resolve() if ref.startswith("/") else (base / ref).resolve()
    return ruta if ruta.is_relative_to(raiz.resolve()) else None


def referencias_html(index: Path, raiz: Path) -> list[tuple[str, Path]]:
    """(grupo, archivo) de la portada y de cada referencia que bloquea el
    arranque en index.html."""
    html = index.read_text(encoding="utf-8")
    refs: list[tuple[str, Path]] = [("html", index)]
    for grupo, patron in _REF_TAGS:
        for tag in patron.findall(html):
            attr = _ATTR.search(tag)
            if not attr:
                continue
            ruta = _resolver(raiz, attr.group(1), index.parent)
            if ruta is not None:
                refs.append((grupo, ruta))
    return refs


def _import_relativos(archivo: Path, patrones: re.Pattern[str] | tuple[re.Pattern[str], ...]) -> list[Path]:
    src = archivo.read_text(encoding="utf-8")
    if isinstance(patrones, tuple):
        refs = [ref for patron in patrones for ref in patron.findall(src)]
    else:
        refs = patrones.findall(src)
    return [(archivo.parent / ref).resolve() for ref in refs if ref.startswith(("./", "../"))]


def _alcanzables(semillas: list[Path], raiz: Path, patrones: tuple[re.Pattern[str], ...]) -> set[Path]:
    """Módulos alcanzables desde las semillas siguiendo los patrones dados.
    web/vendor y lo que cae fuera del repo quedan fuera."""
    raiz = raiz.resolve()
    modulos: set[Path] = set()
    pendientes = [s.resolve() for s in semillas]
    while pendientes:
        modulo = pendientes.pop()
        if not modulo.is_file() or not modulo.is_relative_to(raiz) or "vendor" in modulo.parts or modulo in modulos:
            continue
        modulos.add(modulo)
        for patron in patrones:
            pendientes.extend(_import_relativos(modulo, patron))
    return modulos


def modulos_arranque(semillas: list[Path], raiz: Path) -> set[Path]:
    """Módulos que bloquean el primer pintado: solo imports estáticos."""
    return _alcanzables(semillas, raiz, _IMPORT_ESTATICO)


def modulos_diferidos(semillas: list[Path], raiz: Path) -> set[Path]:
    """Módulos que solo llegan por import() desde el arranque. Si un módulo
    también es alcanzable de forma estática, cuenta como bloqueante."""
    bloqueantes = modulos_arranque(semillas, raiz)
    destinos = [destino for modulo in bloqueantes for destino in _import_relativos(modulo, _IMPORT_DINAMICO)]
    return _alcanzables(destinos, raiz, (*_IMPORT_ESTATICO, _IMPORT_DINAMICO)) - bloqueantes


def archivos_arranque(raiz: Path) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    """(bloqueantes, diferidos): la portada, sus referencias bloqueantes y los
    módulos transitivos de cada conjunto, sin duplicados."""
    web = raiz / "web"
    refs = referencias_html(web / "index.html", raiz)
    semillas = [ruta for grupo, ruta in refs if grupo == "js"]
    bloqueantes = modulos_arranque(semillas, raiz)
    diferidos = modulos_diferidos(semillas, raiz)
    vistos = {ruta for _, ruta in refs}
    bloqueantes_refs = list(refs)
    for modulo in sorted(bloqueantes - vistos):
        bloqueantes_refs.append(("js", modulo))
    return bloqueantes_refs, [("js", modulo) for modulo in sorted(diferidos)]


def medir(raiz: Path) -> list[dict]:
    """Peso en disco y gzip -9 de cada archivo, con su sección y grupo."""
    filas = []
    bloqueantes, diferidos = archivos_arranque(raiz)
    for seccion, refs in (("bloqueante", bloqueantes), ("diferido", diferidos)):
        for tipo, ruta in refs:
            if not ruta.is_file():
                continue
            datos = ruta.read_bytes()
            filas.append(
                {
                    "archivo": ruta.relative_to(raiz).as_posix(),
                    "tipo": tipo,
                    "seccion": seccion,
                    "disco": len(datos),
                    "gzip": len(gzip.compress(datos, compresslevel=9, mtime=0)),
                }
            )
    return filas


def imprimir_tabla(filas: list[dict]) -> None:
    print(f"{'archivo':44s} {'disco':>9s} {'gzip':>9s}")
    total_disco = total_gzip = 0
    for seccion in ("bloqueante", "diferido"):
        print(seccion.upper())
        sec_disco = sec_gzip = 0
        tipo = None
        sub_disco = sub_gzip = 0
        for f in filas:
            if f["seccion"] != seccion:
                continue
            if f["tipo"] != tipo:
                if tipo is not None:
                    print(f"  {'subtotal':42s} {sub_disco / 1024:8.1f} K {sub_gzip / 1024:8.1f} K")
                tipo = f["tipo"]
                sub_disco = sub_gzip = 0
                print(f"  {tipo.upper()}")
            print(f"  {f['archivo']:42s} {f['disco'] / 1024:8.1f} K {f['gzip'] / 1024:8.1f} K")
            sub_disco += f["disco"]
            sub_gzip += f["gzip"]
            sec_disco += f["disco"]
            sec_gzip += f["gzip"]
            total_disco += f["disco"]
            total_gzip += f["gzip"]
        if tipo is not None:
            print(f"  {'subtotal':42s} {sub_disco / 1024:8.1f} K {sub_gzip / 1024:8.1f} K")
        print(f"  {'subtotal ' + seccion:42s} {sec_disco / 1024:8.1f} K {sec_gzip / 1024:8.1f} K")
    print(f"{'TOTAL':44s} {total_disco / 1024:8.1f} K {total_gzip / 1024:8.1f} K")


def presupuestos_para(modo: str) -> tuple[int, int]:
    """(tope bloqueante, tope total) en KB según se mida el fuente o el build."""
    if modo == "build":
        return PRESUPUESTO_ARRANQUE_BUILD_KB, PRESUPUESTO_TOTAL_BUILD_KB
    return PRESUPUESTO_ARRANQUE_KB, PRESUPUESTO_TOTAL_KB


def _construir_build(raiz: Path) -> bool:
    """Minifica web/ del repo en <raiz>/web con el mismo paso del despliegue
    (OPS-06). Devuelve False y explica qué falta si no hay Node o esbuild."""
    script = ROOT / "deploy" / "cloudflare" / "build-web.mjs"
    try:
        proc = subprocess.run(
            ["node", str(script), "--salida", str(raiz / "web")],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print(
            "No se pudo construir el build servido: no se encontró `node` en el PATH.\n"
            "Se necesita Node.js y las dependencias de deploy/cloudflare: corre "
            "`npm ci` en deploy/cloudflare (y revisa que `node` esté instalado) y repite.",
            file=sys.stderr,
        )
        return False
    if proc.returncode != 0:
        detalle = (proc.stderr or proc.stdout or "").strip().splitlines()
        print(
            "No se pudo construir el build servido (OPS-06):\n"
            + "\n".join(detalle[-5:])
            + "\nSi falta esbuild, corre `npm ci` en deploy/cloudflare y repite.",
            file=sys.stderr,
        )
        return False
    return True


def _verificar(raiz: Path, args: argparse.Namespace, modo: str) -> int:
    if not (raiz / "web" / "index.html").is_file():
        print(f"No existe {raiz / 'web' / 'index.html'}", file=sys.stderr)
        return 2
    filas = medir(raiz)
    bloqueante = sum(f["gzip"] for f in filas if f["seccion"] == "bloqueante")
    diferido = sum(f["gzip"] for f in filas if f["seccion"] == "diferido")
    total = bloqueante + diferido
    tope_bloqueante_kb, tope_total_kb = presupuestos_para(modo)
    etiqueta = "build servido minificado" if modo == "build" else "fuente"

    if args.json:
        print(
            json.dumps(
                {
                    "modo": modo,
                    "bloqueante": [f for f in filas if f["seccion"] == "bloqueante"],
                    "diferido": [f for f in filas if f["seccion"] == "diferido"],
                    "bloqueante_gzip": bloqueante,
                    "diferido_gzip": diferido,
                    "total_gzip": total,
                    "presupuestos": {"bloqueante_kb": tope_bloqueante_kb, "total_kb": tope_total_kb},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.informe:
        imprimir_tabla(filas)
        return 0

    errores = []
    tope_bloqueante = tope_bloqueante_kb * 1024
    if bloqueante > tope_bloqueante:
        pesado = max((f for f in filas if f["seccion"] == "bloqueante"), key=lambda f: f["gzip"])
        errores.append(
            f"Peso del arranque excedido (bloqueante): {bloqueante / 1024:.1f} KB gzip supera el "
            f"presupuesto de {tope_bloqueante_kb} KB por "
            f"{(bloqueante - tope_bloqueante) / 1024:.1f} KB; "
            f"el archivo más pesado es {pesado['archivo']} ({pesado['gzip'] / 1024:.1f} KB)"
        )
    if total > tope_total_kb * 1024:
        pesado_total = max(filas, key=lambda f: f["gzip"])
        errores.append(
            f"Peso total excedido: {total / 1024:.1f} KB gzip supera el "
            f"presupuesto de {tope_total_kb} KB por "
            f"{(total - tope_total_kb * 1024) / 1024:.1f} KB; "
            f"el archivo más pesado es {pesado_total['archivo']} ({pesado_total['gzip'] / 1024:.1f} KB)"
        )
    if errores:
        print("\n".join(errores))
        print(PISTA)
        return 1
    print(
        f"Peso del arranque dentro del presupuesto ({etiqueta}): bloqueante "
        f"{bloqueante / 1024:.1f} KB gzip de {tope_bloqueante_kb} KB; diferido "
        f"{diferido / 1024:.1f} KB; total {total / 1024:.1f} KB gzip de {tope_total_kb} KB"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--informe", action="store_true", help="imprime la tabla completa y termina en 0")
    p.add_argument("--json", action="store_true", help="imprime la medición en JSON")
    p.add_argument(
        "--build",
        action="store_true",
        help="mide el build servido (web/ minificado con esbuild, OPS-06) en vez del fuente; --raiz no aplica",
    )
    p.add_argument("--raiz", type=Path, default=ROOT, help="raíz del proyecto (por defecto, este repo)")
    args = p.parse_args(argv)

    if args.build:
        with tempfile.TemporaryDirectory(prefix="brasa-peso-build-") as tmp:
            raiz = Path(tmp)
            if not _construir_build(raiz):
                return 2
            return _verificar(raiz, args, modo="build")
    return _verificar(args.raiz, args, modo="fuente")


if __name__ == "__main__":
    sys.exit(main())
