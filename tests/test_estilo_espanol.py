"""Guarda de español neutro (QA-90): ninguna vista, documento ni texto del producto usa voseo.

El diccionario de formas vive en este mismo archivo, así que la guarda se excluye a sí misma
del recorrido. Los hallazgos se informan juntos, con archivo, línea y la forma neutra.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.settings import ROOT

# Forma voseante o rioplatense → forma neutra. Se comparan sin distinguir mayúsculas y con
# límites de palabra, para no marcar secuencias dentro de otra palabra (por ejemplo «andamio»).
# «podé» no está: es homógrafo de la primera persona del pretérito de «podar» («Podé ramas»).
# shortcut: «elegí» y «escribí» también son primera persona del pretérito; si aparecen así,
# quitar la forma del diccionario o afinarla con contexto.
FORMAS = {
    "tenés": "tienes",
    "tené": "ten",
    "mirá": "mira",
    "mirás": "miras",
    "guardá": "guarda",
    "guardás": "guardas",
    "hacé": "haz",
    "hacés": "haces",
    "andá": "anda",
    "andás": "andas",
    "podés": "puedes",
    "querés": "quieres",
    "queré": "quiere",
    "sabés": "sabes",
    "sabé": "sabe",
    "vení": "ven",
    "venís": "vienes",
    "usá": "usa",
    "usás": "usas",
    "fijate": "fíjate",
    "fijá": "fija",
    "fijás": "fijas",
    "decime": "dime",
    "contame": "cuéntame",
    "avisame": "avísame",
    "acordate": "acuérdate",
    "poné": "pon",
    "ponés": "pones",
    "dejá": "deja",
    "dejás": "dejas",
    "elegí": "elige",
    "elegís": "eliges",
    "escribí": "escribe",
    "escribís": "escribes",
    "buscá": "busca",
    "buscás": "buscas",
    "probá": "prueba",
    "probás": "pruebas",
    "revisá": "revisa",
    "revisás": "revisas",
    "llamá": "llama",
    "llamás": "llamas",
    "anotá": "anota",
    "anotás": "anotas",
}

PATRONES = (
    "web/**/*.html",
    "web/**/*.js",
    "backend/**/*.py",
    "docs/**/*.md",
    "CHANGELOG.md",
    "README.md",
    "tests/**/*.py",
)
EXCLUIDOS = {".venv", "__pycache__", "node_modules"}
_VOSEO = re.compile(r"\b(?:" + "|".join(re.escape(forma) for forma in sorted(FORMAS, key=len, reverse=True)) + r")\b", re.IGNORECASE)


def _archivos(base: Path = ROOT) -> list[Path]:
    encontrados: list[Path] = []
    for patron in PATRONES:
        for ruta in sorted(base.glob(patron)):
            rel = ruta.relative_to(base)
            if not ruta.is_file() or EXCLUIDOS.intersection(rel.parts) or rel.parts[:2] == ("web", "vendor"):
                continue
            encontrados.append(ruta)
    return encontrados


def _hallazgos(base: Path = ROOT) -> list[str]:
    propio = Path(__file__).resolve()
    hallazgos: list[str] = []
    for ruta in _archivos(base):
        if ruta.resolve() == propio:
            continue
        for numero, linea in enumerate(ruta.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for coincidencia in _VOSEO.finditer(linea):
                forma = coincidencia.group(0).lower()
                hallazgos.append(f"{ruta.relative_to(base).as_posix()}:{numero}: usa «{FORMAS[forma]}», no «{forma}»")
    return hallazgos


def test_sin_voseo_en_el_repositorio():
    hallazgos = _hallazgos()
    assert not hallazgos, "Hay voseo o formas rioplatenses; escribe en español neutro:\n" + "\n".join(hallazgos)


def test_detector_marca_texto_sembrado(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "prueba.html").write_text("<p>Guardá esto en el plan</p>", encoding="utf-8")
    assert _hallazgos(tmp_path) == ["web/prueba.html:1: usa «guarda», no «guardá»"]


def test_detector_no_marca_palabras_que_contienen_la_secuencia(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "prueba.html").write_text("<p>El andamio y el desfijate quedaron ahí.</p>", encoding="utf-8")
    assert _hallazgos(tmp_path) == []


def test_los_globs_encuentran_archivos():
    for patron in PATRONES:
        assert list(ROOT.glob(patron)), f"El patrón {patron!r} no encontró archivos; la guarda no estaría revisando nada"
