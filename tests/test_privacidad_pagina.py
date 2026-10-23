"""PRIV-02 (Ley 21.719): la política de privacidad promete plazos por escrito y esta
guarda amarra cada plazo publicado a la constante que lo ejecuta, en ambos sentidos.

Lee web/data/privacidad.json —el texto que la vista pide y pinta (PESO-05)—, lo aplana
a texto con marcadores de sección, traduce cada plazo a días con una tabla explícita y
lo compara con las constantes del código. Si cambia un plazo en el código, cambia
también el texto; si cambia el texto, cambia la constante. Cada fallo nombra la frase
y la constante que discrepan.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from backend import services

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "web" / "data" / "privacidad.json"
RETENCION_TS = RAIZ / "deploy" / "cloudflare" / "src" / "retention.ts"


def _segmentos(items) -> str:
    """Texto plano de una lista de segmentos del JSON: texto, {b}, {a}, {m}, {s:[…]} y {d:[…]}"""
    out = []
    for s in items:
        if isinstance(s, str):
            out.append(s)
        elif "b" in s or "m" in s:
            out.append(s.get("b") or s.get("m") or "")
        elif "a" in s:
            out.append(s["a"])
        elif "s" in s:
            out.append(_segmentos(s["s"]))
        elif "d" in s:
            out.extend(s["d"])
    return "".join(out)


def _texto_pagina() -> str:
    """El contenido de la página aplanado: actualización, lede y una línea
    `<h2 class="section">…` por sección del JSON, para leer los plazos igual que antes."""
    data = json.loads(DATOS.read_text(encoding="utf-8"))
    partes = [data["actualizacion"], _segmentos(data["lede"])]
    for s in data["secciones"]:
        if s.get("slot"):
            continue
        partes.append(f'<h2 class="section">{s["titulo"]}</h2>')
        for b in s.get("bloques", []):
            if "lista" in b:
                partes.extend(_segmentos(item) for item in b["lista"])
            elif "p" in b:
                partes.append(_segmentos(b["p"]))
    return "\n".join(partes)


TEXTO = _texto_pagina()

# Traducción explícita de los plazos que la página puede prometer, en días.
PLAZOS_EN_DIAS = {
    "24 horas": 1,
    "45 días": 45,
    "90 días": 90,
    "12 meses": 365,
    "2 años": 730,
}

# Qué constante cumple cada plazo publicado. Cuatro viven en backend/services.py;
# la de las copias diarias del respaldo vive en el Worker (RETENCION_MS, en ms).
CONSTANTE_DEL_PLAZO = {
    "12 meses": "ALERTS_RETENTION_DAYS",
    "90 días": "REPORTS_STALE_DAYS",
    "2 años": "REPORTS_VERIFIED_DAYS",
    "45 días": "RETENTION_DAYS",
    "24 horas": "RETENCION_MS",
}

_PLAZO = re.compile(r"(\d+)\s*(horas|días|meses|años)")
_RETENCION_MS = re.compile(r"RETENCION_MS\s*=\s*([\d\s*]+)")
_MS_POR_DIA = 24 * 60 * 60 * 1000


def plazos_publicados(texto: str) -> set[str]:
    """Plazos de conservación prometidos, normalizados como «12 meses».

    Se excluye la ficha de fuentes: ahí «5 días» (Botón Rojo) y «7 días» (Open-Meteo)
    son horizontes de pronóstico, no cuánto se guarda un dato de personas.
    """
    sin_fuentes = re.sub(
        r'<h2 class="section">De dónde vienen los datos</h2>.*?(?=<h2 class="section">)',
        "",
        texto,
        count=1,
        flags=re.S,
    )
    assert sin_fuentes != texto, "no se encontró la sección «De dónde vienen los datos» en web/data/privacidad.json"
    return {f"{numero} {unidad}" for numero, unidad in _PLAZO.findall(sin_fuentes)}


def dias_de_constante(nombre: str) -> float:
    """Valor de la constante en días. RETENCION_MS está en milisegundos en retention.ts."""
    if nombre == "RETENCION_MS":
        m = _RETENCION_MS.search(RETENCION_TS.read_text(encoding="utf-8"))
        assert m, f"no se encontró {nombre} en {RETENCION_TS.relative_to(RAIZ)}"
        return math.prod(int(factor) for factor in m.group(1).split("*")) / _MS_POR_DIA
    valor = getattr(services, nombre, None)
    assert valor is not None, f"backend/services.py ya no define {nombre}"
    return valor


def test_pagina_declara_desde_cuando_rige():
    """Sin fecha de revisión, quien lee la página no puede saber si el texto está vigente."""
    assert re.search(r"Última actualización:\s*\d{1,2} de \w+ de \d{4}", TEXTO), (
        "web/data/privacidad.json debe declarar «Última actualización: <fecha>» bajo el título"
    )


def test_cada_plazo_publicado_tiene_su_constante_con_el_mismo_valor():
    for plazo in sorted(plazos_publicados(TEXTO)):
        constante = CONSTANTE_DEL_PLAZO.get(plazo)
        assert constante, (
            f"la página promete «{plazo}» y ninguna constante lo ejecuta: "
            "agrega la correspondencia en CONSTANTE_DEL_PLAZO de tests/test_privacidad_pagina.py "
            "o corrige el texto de web/data/privacidad.json"
        )
        esperado = PLAZOS_EN_DIAS[plazo]
        real = dias_de_constante(constante)
        assert real == esperado, (
            f"la página promete «{plazo}» ({esperado} días) pero {constante} vale {real:g} días: "
            "ajusta la constante o el texto de web/data/privacidad.json"
        )


def test_ninguna_constante_de_retencion_queda_sin_su_frase():
    publicados = plazos_publicados(TEXTO)
    for plazo, constante in sorted(CONSTANTE_DEL_PLAZO.items()):
        assert plazo in publicados, (
            f"{constante} sigue borrando datos pero la página ya no promete «{plazo}»: devuelve la frase a web/data/privacidad.json"
        )
    huerfanas = {n for n in vars(services) if n.endswith("RETENTION_DAYS")} - set(CONSTANTE_DEL_PLAZO.values())
    assert not huerfanas, (
        f"backend/services.py tiene constantes de retención sin promesa en la página: {sorted(huerfanas)}. "
        "Declara su plazo en web/data/privacidad.json y agrégalo a CONSTANTE_DEL_PLAZO de "
        "tests/test_privacidad_pagina.py"
    )
