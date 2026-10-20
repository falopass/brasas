"""Chequeo de los enlaces externos que BRASA muestra al vecino (AUTO-08).

Recorre web/**/*.html, web/js/**/*.js y docs/**/*.md, extrae las URL https?://
y comprueba cuáles responden. Escribe docs/ENLACES.md con el estado de cada
enlace, dónde aparece (archivo:línea) y, si está roto, la URL vigente del mismo
organismo en docs/FUENTES.md.

    python scripts/local/chequeo_enlaces.py
    python scripts/local/chequeo_enlaces.py --solo-rotos
    python scripts/local/chequeo_enlaces.py --json
    python scripts/local/chequeo_enlaces.py --offline --desde tests/data/enlaces_simulados.json

Sólo `roto` (404/410) hace fallar el chequeo (código 1); `bloqueado`
(401/403/429) y `error` (timeout, DNS, 5xx) se informan y no lo rompen.
Sin dependencias nuevas: urllib de la biblioteca estándar.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
PATRONES = ("web/**/*.html", "web/js/**/*.js", "docs/**/*.md")
# Citas históricas de docs/investigacion/ y el propio informe (si no, cada corrida
# sumaría sus propias filas como apariciones).
EXCLUIDOS = ("docs/investigacion/", "docs/ENLACES.md")

URL_RE = re.compile(r"https?://[^\s\"'<>`]+")
# Dominios de ejemplo o internos, y marcas de plantilla (${...}, {z}/{x}, [MAP_KEY]):
# no son enlaces que alguien pueda abrir tal cual.
NO_ENLACE = (
    "example.com",
    "example.org",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "storage.brasa",  # servicio interno de Docker Compose
    "brasa.tu-dominio.cl",
    "brasa.tudominio.cl",  # dominios de ejemplo de la documentación
)
# Identificadores técnicos de XML/JSON-LD, nunca enlaces de la interfaz.
HOSTS_TECNICOS = ("w3.org", "opengis.net", "schema.org")
# Plataformas donde otra URL del mismo dominio es otro proyecto, no la misma
# institución: no sirven como reemplazo automático.
SIN_REEMPLAZO = ("github.com", "arcgis.com")
# CONAF y DMC publican en varios dominios; el reemplazo puede cruzar de uno a otro.
ALIAS_ORGANISMO = {"deigeprif": "conaf", "conafprevencionincendios": "conaf", "meteochile": "dmc"}

ESTADOS = ("ok", "roto", "bloqueado", "error")
ORDEN = {"roto": 0, "error": 1, "bloqueado": 2, "ok": 3}
TIMEOUT_S = 8
TRABAJADORES = 8
UA = "BRASA-Chile-chequeo-enlaces/1.0 (+https://github.com/falopass/brasas)"
CABECERAS = {"User-Agent": UA, "Range": "bytes=0-1024"}
SIN_REEMPLAZO_TXT = "sin reemplazo conocido: revisar a mano"


def _limpiar(url: str) -> str:
    """Quita la puntuación que la URL hereda de la prosa («ver <https://x.cl/>.»)."""
    url = url.rstrip(".,;:!?")
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1]
    return url


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _descartar(url: str) -> bool:
    host = _host(url)
    if "." not in host:
        return True
    if host in NO_ENLACE or host.endswith((".workers.dev", ".local")):
        return True
    if any(host == tecnico or host.endswith("." + tecnico) for tecnico in HOSTS_TECNICOS):
        return True
    return any(marca in url for marca in "{}[]$…")


def extraer_enlaces(raiz: Path) -> dict[str, list[str]]:
    """URL → apariciones (`archivo:línea`), en orden de archivo y deduplicadas."""
    enlaces: dict[str, list[str]] = {}
    for patron in PATRONES:
        for ruta in sorted(raiz.glob(patron)):
            relativa = ruta.relative_to(raiz).as_posix()
            if relativa.startswith(EXCLUIDOS):
                continue
            texto = ruta.read_text(encoding="utf-8", errors="replace")
            for numero, linea in enumerate(texto.splitlines(), 1):
                for encontrada in URL_RE.findall(linea):
                    url = _limpiar(encontrada)
                    if _descartar(url):
                        continue
                    ubicacion = f"{relativa}:{numero}"
                    apariciones = enlaces.setdefault(url, [])
                    if ubicacion not in apariciones:
                        apariciones.append(ubicacion)
    return enlaces


def clasificar(codigo: int) -> str:
    if 200 <= codigo < 400:
        return "ok"
    if codigo in (404, 410):
        return "roto"
    if codigo in (401, 403, 429):
        return "bloqueado"
    return "error"


def consultar(url: str, timeout: float = TIMEOUT_S) -> tuple[str, int | None, str]:
    """(estado, código, detalle). Nunca lanza: un fallo de red es `error`."""
    try:
        with urlopen(Request(url, headers=CABECERAS), timeout=timeout) as respuesta:
            return clasificar(respuesta.status), respuesta.status, ""
    except HTTPError as error:
        return clasificar(error.code), error.code, ""
    except (URLError, OSError, ValueError) as error:
        motivo = getattr(error, "reason", error)
        return "error", None, f"{type(error).__name__}: {motivo}"[:160]


def simulado(url: str, respuestas: dict) -> tuple[str, int | None, str]:
    """Respuesta del JSON de `--desde`; una URL sin entrada cuenta como error visible."""
    respuesta = respuestas.get(url)
    if respuesta is None:
        return "error", None, "sin respuesta simulada"
    if "status" in respuesta:
        codigo = int(respuesta["status"])
        return clasificar(codigo), codigo, ""
    return "error", None, str(respuesta.get("error") or "error simulado")


def _sitio(host: str) -> str:
    """Dominio registrable aproximado: www.conaf.cl → conaf.cl, x.senapred.gob.cl → senapred.gob.cl."""
    partes = host.removeprefix("www.").split(".")
    if len(partes) >= 3 and partes[-2] in ("gob", "gov"):
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def _organismo(url: str) -> str:
    clave = _sitio(_host(url)).split(".")[0]
    return ALIAS_ORGANISMO.get(clave, clave)


def urls_de_fuentes(raiz: Path) -> list[str]:
    ruta = raiz / "docs" / "FUENTES.md"
    if not ruta.exists():
        return []
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    return [url for url in (_limpiar(x) for x in URL_RE.findall(texto)) if not _descartar(url)]


def reemplazo(url: str, fuentes: list[str]) -> str | None:
    """URL vigente del mismo organismo en docs/FUENTES.md, o None si no hay."""
    host = _host(url)
    if any(host == plataforma or host.endswith("." + plataforma) for plataforma in SIN_REEMPLAZO):
        return None
    sitio = _sitio(host)
    candidatos = [u for u in fuentes if u != url and _host(u)]
    mismo_sitio = [u for u in candidatos if _sitio(_host(u)) == sitio]
    if mismo_sitio:
        return mismo_sitio[0]
    # Cruzar de dominio solo dentro de un organismo público chileno: en un sitio
    # genérico otra URL del mismo dominio no reemplaza a la que se cayó.
    if not (host.endswith(".cl") or _organismo(url) in ALIAS_ORGANISMO.values()):
        return None
    mismo_organismo = [u for u in candidatos if _organismo(u) == _organismo(url)]
    return mismo_organismo[0] if mismo_organismo else None


def consultar_todos(enlaces: dict[str, list[str]], raiz: Path, respuestas: dict | None = None) -> list[dict]:
    urls = list(enlaces)
    if respuestas is not None:
        respuestas_url = [(url, *simulado(url, respuestas)) for url in urls]
    else:
        with ThreadPoolExecutor(max_workers=TRABAJADORES) as pool:
            respuestas_url = list(pool.map(lambda url: (url, *consultar(url)), urls))
    fuentes = urls_de_fuentes(raiz)
    return [
        {
            "url": url,
            "estado": estado,
            "codigo": codigo,
            "detalle": detalle,
            "apariciones": enlaces[url],
            "reemplazo": reemplazo(url, fuentes) if estado == "roto" else None,
        }
        for url, estado, codigo, detalle in respuestas_url
    ]


def _celda(texto: str) -> str:
    return texto.replace("|", "\\|")


def escribir_informe(resultados: list[dict], salida: Path, solo_rotos: bool = False) -> None:
    resumen = Counter(r["estado"] for r in resultados)
    filas = sorted(
        (r for r in resultados if not solo_rotos or r["estado"] == "roto"),
        key=lambda r: (ORDEN[r["estado"]], r["url"]),
    )
    lineas = [
        "# Estado de los enlaces externos",
        "",
        f"Generado el {date.today().isoformat()} por `scripts/local/chequeo_enlaces.py`.",
        "Regenerar con: `python scripts/local/chequeo_enlaces.py`.",
        "",
        "Sólo un enlace `roto` (404/410) hace fallar el chequeo. `bloqueado` (401/403/429) y "
        "`error` (timeout, DNS, 5xx) se informan y no lo rompen.",
    ]
    if solo_rotos:
        lineas += ["", "Tabla filtrada a los enlaces rotos (`--solo-rotos`)."]
    conteo = " · ".join(f"{resumen[estado]} {estado}" for estado in ESTADOS)
    lineas += [
        "",
        f"**Resumen:** {len(resultados)} enlaces · {conteo}",
        "",
        "| URL | Estado | Código | Apariciones | Reemplazo propuesto |",
        "|---|---|---|---|---|",
    ]
    for fila in filas:
        apariciones = "<br>".join(f"`{a}`" for a in fila["apariciones"])
        propuesta = fila["reemplazo"] or (SIN_REEMPLAZO_TXT if fila["estado"] == "roto" else "—")
        lineas.append(f"| {_celda(fila['url'])} | {fila['estado']} | {fila['codigo'] or '—'} | {apariciones} | {_celda(propuesta)} |")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chequea los enlaces externos de BRASA y escribe docs/ENLACES.md")
    parser.add_argument("--offline", action="store_true", help="no sale a la red; exige --desde")
    parser.add_argument("--desde", type=Path, help="JSON con respuestas simuladas (implica --offline)")
    parser.add_argument("--solo-rotos", action="store_true", help="tabla sólo con los enlaces rotos")
    parser.add_argument("--json", action="store_true", help="resultado en JSON por stdout")
    parser.add_argument("--raiz", type=Path, default=ROOT, help="raíz del proyecto (para pruebas)")
    parser.add_argument("--salida", type=Path, help="informe de salida (por defecto <raíz>/docs/ENLACES.md)")
    args = parser.parse_args(argv)
    if args.offline and not args.desde:
        parser.error("--offline necesita --desde <archivo.json> con respuestas simuladas")

    respuestas = json.loads(args.desde.read_text(encoding="utf-8")) if args.desde else None
    salida = args.salida or args.raiz / "docs" / "ENLACES.md"
    enlaces = extraer_enlaces(args.raiz)
    resultados = consultar_todos(enlaces, args.raiz, respuestas)
    escribir_informe(resultados, salida, args.solo_rotos)

    rotos = [r for r in resultados if r["estado"] == "roto"]
    resumen = Counter(r["estado"] for r in resultados)
    if args.json:
        print(
            json.dumps(
                {
                    "fecha": date.today().isoformat(),
                    "resumen": {estado: resumen[estado] for estado in ESTADOS},
                    "enlaces": [r for r in resultados if not args.solo_rotos or r["estado"] == "roto"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"{len(resultados)} enlaces: " + ", ".join(f"{resumen[e]} {e}" for e in ESTADOS))
        for fila in rotos:
            print(f"  roto {fila['codigo']}: {fila['url']} ({', '.join(fila['apariciones'])})")
        print(f"Informe: {salida}")
    return 1 if rotos else 0


if __name__ == "__main__":
    raise SystemExit(main())
