"""Verificador semanal de los enlaces vivos que BRASA le muestra a la gente.

A diferencia de `fuentes_salud.py` (que sondea endpoints de datos), este script comprueba las
páginas oficiales que el usuario puede apretar: el bloque `SRC` de Prepárate, `THIRD_PARTY` y
`OWN_WORK` de la vista Calidad y todos los enlaces de `docs/FUENTES.md`. Si CONAF o SENAPRED
mueven una ruta, el vecino cae en un 404 y este run lo detecta.

Cada enlace se pide con GET (varias de esas páginas responden 405 a HEAD), User-Agent propio y
15 s de espera; solo se reintenta ante un error de red. Veredictos:
  OK    2xx (una redirección al mismo dominio, con o sin www, sigue siendo OK)
  OJO   3xx a otro dominio, 401/403/429 (la página existe pero bloquea la sonda)
  FALLA 404/410, 5xx, timeout o DNS
Sale 0 solo sin FALLA. Con FALLA escribe `alerta.md` y deja `alerta=true` y `titulo` en
GITHUB_OUTPUT para que el workflow abra el issue.

Uso: python .github/scripts/enlaces_vivos.py [--from veredictos.json]
`--from` lee una lista de {url, fuentes, estado, detalle} ya calculada: así las pruebas y los
ensayos corren sin red.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
UA = {"User-Agent": "BRASA-Chile enlaces-vivos (+https://github.com/falopass/brasas)"}
TIMEOUT = 15

# Bloques de los que se extraen enlaces, por archivo. En Calidad hoy son descripciones sin URL:
# cuando una capa sume su enlace, la extracción lo toma sin tocar este script.
BLOQUES = {
    "web/js/views/preparate.js": (r"const SRC = \{(.*?)\};",),
    "web/js/views/calidad.js": (r"const THIRD_PARTY = \[(.*?)\n\];", r"const OWN_WORK = \[(.*?)\n\];"),
}
FUENTES = "docs/FUENTES.md"
_URL_RE = re.compile(r"https://[^\s<>\"'`]+")


def _urls(texto: str) -> list[str]:
    """URLs https del texto, sin puntuación final ni plantillas con [PLACEHOLDER]."""
    urls = []
    for cruda in _URL_RE.findall(texto):
        url = cruda.rstrip(".,;:)")
        if "[" not in url and "{" not in url:
            urls.append(url)
    return urls


def extraer_todos(raiz: Path = ROOT) -> list[dict]:
    """Enlaces de los tres orígenes, sin duplicados y con la lista de archivos que los citan."""
    vistos: dict[str, list[str]] = {}

    def sumar(urls: list[str], archivo: str) -> None:
        for url in urls:
            fuentes = vistos.setdefault(url, [])
            if archivo not in fuentes:
                fuentes.append(archivo)

    for archivo, patrones in BLOQUES.items():
        texto = (raiz / archivo).read_text(encoding="utf-8")
        for patron in patrones:
            for bloque in re.findall(patron, texto, re.S):
                sumar(_urls(bloque), archivo)
    sumar(_urls((raiz / FUENTES).read_text(encoding="utf-8")), FUENTES)
    return [{"url": url, "fuentes": fuentes} for url, fuentes in vistos.items()]


def _host(url: str) -> str:
    """Host en minúsculas, sin el prefijo www. (mismo sitio para este chequeo)."""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def veredicto(url: str, status: int, final: str) -> tuple[str, str]:
    """Veredicto de un enlace a partir del status y de la URL final tras redirecciones."""
    if 200 <= status < 300:
        otro = _host(final)
        if otro and otro != _host(url):
            return "OJO", f"HTTP {status}, redirige a otro dominio ({otro})"
        return "OK", f"HTTP {status}"
    if status in (401, 403, 429):
        return "OJO", f"HTTP {status} (bloquea la sonda)"
    if 300 <= status < 400:
        return "OJO", f"HTTP {status} sin destino final"
    return "FALLA", f"HTTP {status}" if status else "sin respuesta"


def sondear(url: str) -> tuple[int, str]:
    """(status, URL final) de un GET; reintenta una vez solo ante error de red."""
    for intento in (1, 2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT) as r:
                r.read(2048)
                return r.status, r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Location") or url
        except Exception:
            if intento == 2:
                raise
    return 0, url


def revisar(enlaces: list[dict], sonda=sondear) -> list[dict]:
    """Un resultado por enlace: los datos de entrada más estado y detalle."""
    resultados = []
    for enlace in enlaces:
        try:
            status, final = sonda(enlace["url"])
            estado, detalle = veredicto(enlace["url"], status, final)
        except Exception as e:
            estado, detalle = "FALLA", f"sin respuesta ({type(e).__name__})"
        resultados.append({**enlace, "estado": estado, "detalle": detalle})
    return resultados


def _cuerpo(fallas: list[dict], resultados: list[dict]) -> str:
    """Cuerpo del issue: todos los FALLA y OJO con su origen."""
    lista = "\n".join(
        f"- **{r['estado']}** `{r['url']}` — {r['detalle']} ({', '.join(r['fuentes']) or 'origen desconocido'})"
        for r in resultados
        if r["estado"] != "OK"
    )
    run = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run = (
            f"\nCorrida: {os.environ.get('GITHUB_SERVER_URL')}/{os.environ.get('GITHUB_REPOSITORY')}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        )
    return f"""## Enlaces caídos

La revisión semanal encontró {len(fallas)} enlace(s) que no responden. Quien apriete uno de estos
botones cae en un error, así que hay que corregir el enlace o la cita:

{lista}

Los OJO son avisos (redirección a otro dominio, 401/403/429): revísalos si persisten.
Mientras este issue siga abierto la revisión no crea otros; ciérralo cuando los enlaces vuelvan.{run}
"""


def _titulo(fallas: list[dict]) -> str:
    hosts = ", ".join(sorted({_host(r["url"]) for r in fallas}))
    return f"[enlaces] {len(fallas)} enlace(s) caído(s): {hosts}"[:200].replace("\n", " ")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Comprueba que los enlaces citados por BRASA respondan.")
    ap.add_argument("--from", dest="origen", metavar="ARCHIVO.json", help="lee veredictos ya calculados, sin red")
    args = ap.parse_args(argv)

    if args.origen:
        try:
            datos = json.loads(Path(args.origen).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"::error::No se pudo leer {args.origen}: {e}")
            return 2
        crudos = datos.get("enlaces") if isinstance(datos, dict) else datos
        if not isinstance(crudos, list) or not all(
            isinstance(r, dict) and r.get("url") and r.get("estado") in ("OK", "OJO", "FALLA") for r in crudos
        ):
            print("::error::El JSON debe traer una lista de {url, estado} con estado OK, OJO o FALLA")
            return 2
        resultados = [
            {
                "url": r["url"],
                "fuentes": r.get("fuentes") or [],
                "estado": r["estado"],
                "detalle": r.get("detalle", ""),
            }
            for r in crudos
        ]
    else:
        resultados = revisar(extraer_todos())

    for r in resultados:
        print(f"{r['estado']:8} {r['url']} — {r['detalle']} ({', '.join(r['fuentes']) or '—'})")
        if r["estado"] == "FALLA":
            print(f"::error::{r['url']}: {r['detalle']}")
        elif r["estado"] == "OJO":
            print(f"::warning::{r['url']}: {r['detalle']}")

    fallas = [r for r in resultados if r["estado"] == "FALLA"]
    oks = sum(r["estado"] == "OK" for r in resultados)
    print(f"\n{oks}/{len(resultados)} enlaces OK, {len(fallas)} con FALLA")

    out = os.environ.get("GITHUB_OUTPUT")
    if not fallas:
        if out:
            Path(out).open("a", encoding="utf-8").write("alerta=false\n")
        return 0

    Path("alerta.md").write_text(_cuerpo(fallas, resultados), encoding="utf-8")
    titulo = _titulo(fallas)
    if out:
        with Path(out).open("a", encoding="utf-8") as f:
            f.write(f"alerta=true\ntitulo={titulo}\n")
    else:
        print(f"titulo: {titulo}\n---\n{Path('alerta.md').read_text(encoding='utf-8')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
