"""Guarda de coherencia (Ley 21.719): los plazos que publica #/privacidad son los que el
servidor ejecuta. Lee web/data/privacidad.json —el texto que la vista pinta (PESO-05)—
aplanado a texto con marcadores de sección, y las constantes de backend.services, sin
levantar el servidor ni escribir en disco.

Si cambia un plazo en el código, cambia también web/data/privacidad.json; si cambia el
texto, cambia la constante. Cada prueba nombra el número y el archivo que hay que ajustar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.services import (
    ALERTS_RETENTION_DAYS,
    REPORTS_STALE_DAYS,
    REPORTS_VERIFIED_DAYS,
    RETENTION_DAYS,
)

DATOS = Path(__file__).resolve().parents[1] / "web" / "data" / "privacidad.json"


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

# Plazos de conservación que la página puede publicar. Un plazo nuevo aquí obliga a mirar
# qué constante de backend/services.py lo cumple (y a agregarlo a este conjunto).
PLAZOS_PERMITIDOS = {"12 meses", "24 horas", "90 días", "45 días", "2 años"}

_PLAZO = re.compile(r"(\d+)\s*(meses|días|años)")


def bloque(texto: str, titulo: str) -> str:
    """Cuerpo del bloque «En simple» o «Cuánto tiempo» de la vista."""
    m = re.search(rf'<h2 class="section">{re.escape(titulo)}</h2>(.*?)(?=<h2 class="section">)', texto, re.S)
    assert m, f"no se encontró la sección «{titulo}» en web/data/privacidad.json"
    return m.group(1)


def plazos_publicados(texto: str) -> set[str]:
    """Plazos de conservación publicados, normalizados como «12 meses».

    Queda fuera la ficha de fuentes: ahí «5 días» (Botón Rojo) y «7 días» (Open-Meteo)
    son horizontes de pronóstico, no cuánto se guarda un dato de personas.
    """
    sin_fuentes = re.sub(r'<h2 class="section">De dónde vienen los datos</h2>.*?(?=<h2 class="section">)', "", texto, count=1, flags=re.S)
    assert sin_fuentes != texto, "no se encontró la sección «De dónde vienen los datos» en web/data/privacidad.json"
    return {f"{numero} {unidad}" for numero, unidad in _PLAZO.findall(sin_fuentes)}


def plazos_fuera_de_conjunto(texto: str) -> set[str]:
    return plazos_publicados(texto) - PLAZOS_PERMITIDOS


def test_retencion_avisos_doce_meses_coincide_con_el_codigo():
    assert 360 <= ALERTS_RETENTION_DAYS <= 366, (
        f"ALERTS_RETENTION_DAYS={ALERTS_RETENTION_DAYS} en backend/services.py ya no son 12 meses: "
        "ajusta la constante o el plazo «12 meses» de web/data/privacidad.json"
    )
    assert "12 meses" in plazos_publicados(TEXTO), (
        "web/data/privacidad.json debe publicar «12 meses» para los avisos: "
        f"ALERTS_RETENTION_DAYS={ALERTS_RETENTION_DAYS} en backend/services.py"
    )


def test_retencion_reportes_sin_verificar_90_dias_coincide_con_el_codigo():
    assert REPORTS_STALE_DAYS == 90, (
        f"REPORTS_STALE_DAYS={REPORTS_STALE_DAYS} en backend/services.py ya no son 90 días: "
        "ajusta la constante o el plazo «90 días» de web/data/privacidad.json"
    )
    assert "90 días" in plazos_publicados(TEXTO), (
        "web/data/privacidad.json debe publicar «90 días» para los reportes sin verificar: "
        f"REPORTS_STALE_DAYS={REPORTS_STALE_DAYS} en backend/services.py"
    )


def test_retencion_reportes_verificados_dos_anios_coincide_con_el_codigo():
    assert REPORTS_VERIFIED_DAYS == 730, (
        f"REPORTS_VERIFIED_DAYS={REPORTS_VERIFIED_DAYS} en backend/services.py ya no son 2 años: "
        "ajusta la constante o el plazo «2 años» de web/data/privacidad.json"
    )
    assert "2 años" in plazos_publicados(TEXTO), (
        "web/data/privacidad.json debe publicar «2 años» para los reportes verificados: "
        f"REPORTS_VERIFIED_DAYS={REPORTS_VERIFIED_DAYS} en backend/services.py"
    )


def test_retencion_observaciones_45_dias_coincide_con_el_codigo():
    assert RETENTION_DAYS == 45, (
        f"RETENTION_DAYS={RETENTION_DAYS} en backend/services.py ya no son 45 días: "
        "ajusta la constante o el plazo «45 días» de web/data/privacidad.json"
    )
    assert "45 días" in plazos_publicados(TEXTO), (
        "web/data/privacidad.json debe publicar «45 días» para las observaciones satelitales: "
        f"RETENTION_DAYS={RETENTION_DAYS} en backend/services.py"
    )


def test_retencion_ningun_plazo_publicado_queda_fuera_del_conjunto():
    fuera = plazos_fuera_de_conjunto(TEXTO)
    assert not fuera, (
        f"web/data/privacidad.json publica plazos sin constante verificada: {sorted(fuera)}. "
        "Agrégalos a PLAZOS_PERMITIDOS en tests/test_privacidad_retencion.py y comprueba que "
        "backend/services.py los cumple; si no, corrige el texto de la página"
    )


def test_retencion_en_simple_mantiene_el_descargo_de_emergencia():
    texto = bloque(TEXTO, "En simple")
    assert re.search(r"no es una alerta oficial", texto, re.I), (
        "el bloque «En simple» de web/data/privacidad.json debe decir que BRASA no es una alerta oficial"
    )
    assert re.search(r"130\s*\(CONAF\)", texto), "el bloque «En simple» de web/data/privacidad.json debe llamar al 130 (CONAF)"
    assert re.search(r"132\s*\(Bomberos\)", texto), "el bloque «En simple» de web/data/privacidad.json debe llamar al 132 (Bomberos)"


def test_retencion_falla_si_la_pagina_promete_180_dias():
    mutado = TEXTO.replace("90 días", "180 días", 1)
    assert "180 días" in plazos_fuera_de_conjunto(mutado), "la guarda debe rechazar un plazo publicado que backend/services.py no cumple"
