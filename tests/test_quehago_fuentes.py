"""UX-11 / CONT-05: contrato de «¿Qué hago si…?».

Cada rama de web/js/views/quehago.js es una situación de emergencia y debe
traer su pregunta, dos pasos o más y al menos una fuente oficial con enlace
https. El párrafo final debe nombrar a SENAPRED y CONAF y decir que BRASA no
es una alerta oficial.

La prueba lee el archivo como texto y lo analiza con expresiones regulares
(sin ejecutar JavaScript). Los textos de emergencia no se tocan sin
aprobación: esta guarda fija lo que hay, no lo reescribe. La copia mutada de
la prueba existe solo en memoria y demuestra que quitar una fuente, dejar una
rama con un solo paso o romper el descargo enciende el CI.
"""

import re
from pathlib import Path
from urllib.parse import urlsplit

QUEHAGO = Path(__file__).resolve().parents[1] / "web" / "js" / "views" / "quehago.js"

# Instituciones oficiales cuyos dominios (o subdominios) puede citar una rama.
DOMINIOS_OFICIALES = (
    "senapred.cl",
    "senapred.gob.cl",
    "conaf.cl",
    "senadis.gob.cl",
    "minsal.cl",
    "degreyd.minsal.cl",
    "bomberos.cl",
)

_DESCARGOS = ("SENAPRED", "CONAF")
# El texto actual dice «no una alerta oficial»; el contrato pide el descargo
# «no es una alerta oficial». Se aceptan ambas formas: la copia no se toca.
_NO_ALERTA = re.compile(r"no (?:es )?una alerta oficial", re.I)

_STR = re.compile(r"'((?:[^'\\]|\\.)*)'")
_PAIR = re.compile(r"\[\s*'((?:[^'\\]|\\.)*)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\]")
_BRANCH = re.compile(r"\{\s*q:\s*'((?:[^'\\]|\\.)*)'")
_PARRAFO = re.compile(r'<p class="tiny muted">(.*?)</p>', re.S)


def parse_branches(src):
    """Ramas de BRANCHES en el orden del archivo: [{q, steps, sources, link}]."""
    m = re.search(r"const BRANCHES\s*=\s*\[(.*?)\n\];", src, re.S)
    assert m, "no se encontró el arreglo BRANCHES en web/js/views/quehago.js"
    bloque = m.group(1)
    cortes = [x.start() for x in _BRANCH.finditer(bloque)] + [len(bloque)]
    ramas = []
    for inicio, fin in zip(cortes, cortes[1:]):
        trozo = bloque[inicio:fin]
        assert "steps:" in trozo and "sources:" in trozo, f"rama sin steps o sources: {trozo[:60]}"
        resto = trozo.split("sources:", 1)[1]
        fuentes_trozo, _, link_trozo = resto.partition("link:")
        link = _PAIR.search(link_trozo)
        ramas.append(
            {
                "q": _BRANCH.match(trozo).group(1),
                "steps": _STR.findall(trozo.split("steps:", 1)[1].split("sources:", 1)[0]),
                "sources": _PAIR.findall(fuentes_trozo),
                "link": link.groups() if link else None,
            }
        )
    return ramas


def descargo(src):
    """Párrafo final que declara que BRASA no es una alerta oficial."""
    for texto in _PARRAFO.findall(src):
        if _NO_ALERTA.search(texto):
            return texto
    return ""


def ramas_sin_fuente(ramas):
    return [r["q"] for r in ramas if not r["sources"]]


def ramas_cortas(ramas):
    return [r["q"] for r in ramas if len(r["steps"]) < 2]


def fuentes_malas(ramas):
    """(rama, url) cuya URL no es https o no es de un dominio oficial."""
    malas = []
    for rama in ramas:
        for _, url in rama["sources"]:
            host = urlsplit(url).hostname or ""
            if not url.startswith("https://") or not any(host == d or host.endswith("." + d) for d in DOMINIOS_OFICIALES):
                malas.append((rama["q"], url))
    return malas


def _sin_fuentes(src):
    """Copia con las fuentes de la primera rama borradas."""
    m = re.search(r"sources:\s*\[(.*?)\]\s*\}", src, re.S)
    assert m, "no se encontró el primer arreglo sources"
    return src[: m.start(1)] + src[m.end(1) :]


def _con_un_solo_paso(src):
    """Copia con la primera rama reducida a su primer paso."""
    m = re.search(r"steps:\s*\[([^\]]*)\]", src, re.S)
    assert m, "no se encontró el primer arreglo steps"
    pasos = list(_STR.finditer(m.group(1)))
    assert len(pasos) >= 2, "la primera rama ya tiene menos de dos pasos"
    return src[: m.start(1) + pasos[0].end()] + src[m.start(1) + pasos[-1].end() :]


def _sin_descargo(src):
    texto = descargo(src)
    assert texto, "no se encontró el párrafo final"
    return src.replace(texto, "", 1)


_SRC = QUEHAGO.read_text(encoding="utf-8")


def test_las_ramas_cumplen_el_contrato():
    ramas = parse_branches(_SRC)
    assert len(ramas) >= 5, f"«¿Qué hago si…?» tiene {len(ramas)} ramas y el mínimo es 5"
    assert all(r["q"].strip() for r in ramas), "hay una rama con la pregunta vacía"
    assert not ramas_cortas(ramas), f"ramas con menos de dos pasos: {ramas_cortas(ramas)}"
    assert not ramas_sin_fuente(ramas), f"ramas sin fuente oficial: {ramas_sin_fuente(ramas)}"
    assert not fuentes_malas(ramas), f"fuentes que no son https u oficiales: {fuentes_malas(ramas)}"


def test_parrafo_final_nombra_autoridades_y_descargo():
    texto = descargo(_SRC)
    assert texto, "falta el párrafo final que aclara que BRASA no es una alerta oficial"
    for frase in _DESCARGOS:
        assert frase in texto, f"el párrafo final no menciona «{frase}»: {texto}"


def test_las_guardas_muerden():
    """Una copia mutada en memoria (sin fuente, con un paso, http:// o sin descargo) se detecta."""
    primera = parse_branches(_SRC)[0]["q"]
    assert ramas_sin_fuente(parse_branches(_sin_fuentes(_SRC))) == [primera]
    assert ramas_cortas(parse_branches(_con_un_solo_paso(_SRC))) == [primera]
    assert fuentes_malas(parse_branches(_SRC.replace("'https://", "'http://", 1)))
    assert descargo(_sin_descargo(_SRC)) == ""


# QUEHAGO-01: la rama para quien vive en el campo o en una parcela.
RURAL = r"campo|parcela"


def test_rama_rural_cumple_lo_suyo():
    rural = next((r for r in parse_branches(_SRC) if re.search(RURAL, r["q"], re.I)), None)
    assert rural, "falta la rama para quien vive en el campo o en una parcela"
    assert len(rural["steps"]) >= 3, f"la rama rural tiene {len(rural['steps'])} pasos y el mínimo es 3"
    texto = " ".join(rural["steps"])
    assert "130" in texto, "la rama rural debe nombrar el 130 (CONAF)"
    assert "132" in texto, "la rama rural debe nombrar el 132 (Bomberos)"
    assert len(rural["sources"]) >= len(rural["steps"]), "cada paso debe tener su fuente oficial"
    for _, url in rural["sources"]:
        host = urlsplit(url).hostname or ""
        assert url.startswith("https://"), f"fuente no https en la rama rural: {url}"
        assert any(host == d or host.endswith("." + d) for d in ("senapred.cl", "conaf.cl")), (
            f"fuente fuera de SENAPRED/CONAF en la rama rural: {url}"
        )
    assert rural["link"] and rural["link"][1] == "#/riesgo", f"la rama rural debe enlazar a #/riesgo, no a {rural['link']}"
