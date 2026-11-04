"""Lluvia horaria e isoterma 0 °C: el insumo del aviso de aluvión (AGUA-03A).

Tras un incendio el suelo quemado absorbe menos agua, así que lo que importa no es el
acumulado del día sino cuánta lluvia cae en pocas horas y a qué altura está la isoterma
0 °C: si está muy alta, en la cordillera cae lluvia en vez de nieve y el agua escurre de
inmediato hacia las quebradas.

La serie horaria viene del pronóstico de Open-Meteo (`forecast_hourly` con
`extra_vars=["precipitation", "freezing_level_height"]`), con `time` en UTC.

Los umbrales son iniciales y están pendientes de calibración con datos chilenos
(intensidades de DMC/DGA y la isoterma de los aluviones documentados). La señal marca la
peor ventana de lluvia y `explicacion` la traduce a un texto prudente para el vecino;
ninguna de las dos gatilla avisos todavía (AGUA-206).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

VENTANA_HORAS = 3
MM_3H_INTENSA = 10.0  # mm en 3 horas: umbral inicial de «lluvia intensa», por calibrar
ISOTERMA_ALTA_M = 2500.0  # sobre esta altura la isoterma se informa como alta; no decide la señal

# La etiqueta y la frase que manda a SENAPRED van en todos los textos de `explicacion`.
ETIQUETA = "Estimación de BRASA con umbrales provisionales: no es un aviso oficial."
SENAPRED = "Sigue las indicaciones de SENAPRED y de la autoridad local (senapred.cl)."


def _hora(valor: Any) -> float | None:
    """Una lectura horaria válida (número real, no booleano) o None."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def ventana(hourly: dict[str, Any]) -> dict[str, Any] | None:
    """La peor ventana de VENTANA_HORAS horas: {mm_3h, inicio, isoterma_m}.

    `mm_3h` es la mayor suma de `precipitation` en 3 horas seguidas e `inicio` la marca
    `time` de su primera hora. `isoterma_m` es la `freezing_level_height` de la hora
    central de esa ventana; None si esa hora no trae dato.

    Devuelve None cuando no hay ventana evaluable: sin `precipitation`, con menos de
    VENTANA_HORAS horas o con algún `None` en la serie, porque un hueco puede esconder
    la verdadera peor ventana y BRASA nunca inventa una lectura.
    """
    times = hourly.get("time") or []
    mm = hourly.get("precipitation") or []
    isoterma = hourly.get("freezing_level_height") or []
    horas = min(len(times), len(mm))
    if any(_hora(mm[i]) is None for i in range(horas)):
        return None
    mejor = None
    for i in range(horas - VENTANA_HORAS + 1):
        total = round(sum(float(mm[j]) for j in range(i, i + VENTANA_HORAS)), 1)
        central = i + VENTANA_HORAS // 2
        iso = _hora(isoterma[central]) if central < len(isoterma) else None
        if mejor is None or total > mejor["mm_3h"]:
            mejor = {"mm_3h": total, "inicio": times[i], "isoterma_m": iso}
    return mejor


def _instante(valor: Any) -> datetime | None:
    """Un `datetime` consciente a partir de un `datetime` o una marca ISO.

    Los valores sin zona se leen como UTC, la zona de la serie de Open-Meteo; None si
    `valor` no se puede leer como fecha-hora.
    """
    if isinstance(valor, datetime):
        marca = valor
    elif isinstance(valor, str):
        try:
            marca = datetime.fromisoformat(valor)
        except ValueError:
            return None
    else:
        return None
    return marca if marca.tzinfo else marca.replace(tzinfo=timezone.utc)


def senal(hourly: dict[str, Any], now: datetime | str | None = None) -> dict[str, Any]:
    """Resumen para el futuro aviso de aluvión.

    {"mm_3h": float|None, "isoterma_m": float|None, "isoterma_alta": bool|None,
     "intensa": bool, "ventana": str|None, "horas_hasta": int|None}.

    `intensa` es mm_3h >= MM_3H_INTENSA: el único umbral que decide la señal, aún
    pendiente de calibración con datos chilenos. `isoterma_alta` es isoterma_m >=
    ISOTERMA_ALTA_M: se informa (None si la hora central no trae dato) pero no gatilla
    nada. `horas_hasta` son las horas enteras desde `now` (un `datetime` con zona o una
    marca ISO) hasta el inicio de la ventana —0 si ya empezó, nunca negativo—; None
    sin `now` o cuando la marca de `now` o de `ventana` no se puede leer. Sin datos
    los campos quedan en None e `intensa` en False; si las series no permiten evaluar
    ninguna ventana, `ventana` es None.
    """
    peor = ventana(hourly)
    if peor is None:
        return {"mm_3h": None, "isoterma_m": None, "isoterma_alta": None, "intensa": False, "ventana": None, "horas_hasta": None}
    iso = peor["isoterma_m"]
    ahora = _instante(now)
    inicio = _instante(peor["inicio"])
    horas = None if ahora is None or inicio is None else max(0, int((inicio - ahora).total_seconds() // 3600))
    return {
        "mm_3h": peor["mm_3h"],
        "isoterma_m": iso,
        "isoterma_alta": None if iso is None else iso >= ISOTERMA_ALTA_M,
        "intensa": peor["mm_3h"] >= MM_3H_INTENSA,
        "ventana": peor["inicio"],
        "horas_hasta": horas,
    }


def _contexto(dias: float | None) -> str:
    """Una frase con la fecha del incendio, sin convertirla en umbral."""
    if dias is None or dias < 0:
        return "No consta la fecha del incendio."
    if dias <= 365:
        return f"El incendio fue hace {int(dias)} días, dentro del primer año tras el fuego."
    return f"El incendio fue hace {int(dias)} días, más de un año después del fuego."


def explicacion(lluvia: float | None, isoterma: float | None, dias_desde_el_incendio: int | None) -> str:
    """Texto prudente para el vecino sobre lluvia en suelo quemado; no es un aviso.

    `lluvia` son los mm de la peor ventana de 3 h (`senal()["mm_3h"]`), `isoterma` la
    altura de la isoterma 0 °C en metros y `dias_desde_el_incendio` los días desde el
    incendio que dejó el suelo quemado. El texto siempre lleva la etiqueta de estimación
    de BRASA y la frase que manda a SENAPRED.

    La lluvia decide el mensaje con MM_3H_INTENSA y la isoterma solo lo modula con
    ISOTERMA_ALTA_M. La fecha del incendio agrega contexto y no cambia la señal: no hay
    calibración de cómo decae el riesgo con los años. Sin dato de lluvia no se afirma
    nada; sin dato de isoterma se avisa igual, porque la lluvia intensa ya es el factor
    principal.
    """
    mm = _hora(lluvia)
    iso = _hora(isoterma)
    if mm is None:
        cuerpo = "No hay pronóstico de lluvia para esta zona, así que no se puede estimar el riesgo de hoy."
    elif mm < MM_3H_INTENSA:
        cuerpo = (
            f"Se prevén {mm:.1f} mm en 3 horas, bajo el umbral provisional de lluvia intensa "
            f"({MM_3H_INTENSA:.0f} mm). No se espera lluvia intensa sobre el suelo quemado."
        )
    elif iso is None:
        cuerpo = (
            f"Se prevén {mm:.1f} mm en 3 horas sobre suelo quemado: es lluvia intensa según el umbral "
            "provisional de BRASA. No hay dato de la isoterma 0 °C, así que no se puede saber si en la "
            "cordillera cae lluvia o nieve. Atento a las quebradas y no te ubiques en su cauce."
        )
    elif iso >= ISOTERMA_ALTA_M:
        cuerpo = (
            f"Lluvia intensa sobre suelo quemado: {mm:.1f} mm en 3 horas y la isoterma 0 °C está alta "
            f"({iso:.0f} m, por encima de {ISOTERMA_ALTA_M:.0f} m). En la cordillera cae lluvia en vez de "
            "nieve y el agua escurre de inmediato hacia las quebradas. Atento a las quebradas: no te "
            "ubiques en su cauce y aléjate de él si escuchas un ruido fuerte que baja."
        )
    else:
        cuerpo = (
            f"Lluvia intensa sobre suelo quemado: {mm:.1f} mm en 3 horas. La isoterma 0 °C está baja "
            f"({iso:.0f} m, por debajo de {ISOTERMA_ALTA_M:.0f} m), así que en la cordillera la "
            "precipitación cae sobre todo como nieve y el agua llega más lenta. Aun así, no te ubiques "
            "en el cauce de las quebradas."
        )
    return " ".join((cuerpo, _contexto(_hora(dias_desde_el_incendio)), ETIQUETA, SENAPRED))


# Umbrales provisionales del cruce lluvia × pendiente × suelo quemado (AGUA-02, AGUA-04).
PENDIENTE_FUERTE_DEG = 15.0
PENDIENTE_MODERADA_DEG = 8.0
MM_3H_TERRENO = 5.0  # con huella de calor y pendiente moderada sube de «bajo» a «moderado»


def _numero(valor: Any) -> float | None:
    """Un número real (no booleano) o None: un dato ilegible no entra al cruce."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def evaluar_terreno(
    senal_lluvia: dict | None,
    slope_deg: float | None,
    scar_ha: float | None,
    dias_desde_incendio: int | None = None,
) -> dict:
    """Susceptibilidad de escurrimiento en ladera o quebrada quemada.

    Cruza la señal de lluvia (`intensa`, mm en 3 h, isoterma 0 °C), la pendiente del
    punto y las hectáreas de huella de calor a ≤ 5 km. Sin cicatriz el nivel queda en
    «bajo»: la pendiente y la lluvia solas no describen una ladera quemada. No es un
    aviso: `explicacion` siempre termina con `ETIQUETA` y `SENAPRED`.
    `dias_desde_incendio` solo agrega contexto y no cambia `nivel`.
    """
    intensa = bool(senal_lluvia and senal_lluvia.get("intensa"))
    mm_3h = senal_lluvia.get("mm_3h") if senal_lluvia else None
    isoterma_m = senal_lluvia.get("isoterma_m") if senal_lluvia else None
    isoterma_alta = bool(senal_lluvia and senal_lluvia.get("isoterma_alta"))
    pendiente = _numero(slope_deg)
    cicatriz = _numero(scar_ha)
    mm = _numero(mm_3h)
    pendiente_fuerte = pendiente is not None and pendiente >= PENDIENTE_FUERTE_DEG
    pendiente_moderada = pendiente is not None and pendiente >= PENDIENTE_MODERADA_DEG
    suelo_quemado = cicatriz is not None and cicatriz > 0
    if mm is None:
        nivel = "sin_dato"
    elif suelo_quemado and intensa and (pendiente_fuerte or isoterma_alta):
        nivel = "alto"
    elif suelo_quemado and (intensa or (mm >= MM_3H_TERRENO and pendiente_moderada)):
        nivel = "moderado"
    else:
        nivel = "bajo"
    return {
        "nivel": nivel,
        "slope_deg": slope_deg,
        "scar_ha": scar_ha,
        "explicacion": _texto_terreno(nivel, pendiente, cicatriz, mm, _numero(isoterma_m), dias_desde_incendio),
    }


def _texto_terreno(
    nivel: str,
    slope_deg: float | None,
    scar_ha: float | None,
    mm_3h: float | None,
    isoterma_m: float | None,
    dias_desde_incendio: int | None,
) -> str:
    """Hechos del cruce, en el mismo tono prudente que `explicacion`."""
    sin_cicatriz = scar_ha is None or scar_ha <= 0
    if nivel == "sin_dato":
        cuerpo = "No hay pronóstico de lluvia en 3 horas, así que no se estima el escurrimiento en laderas o quebradas."
    elif sin_cicatriz:
        # Pendiente y lluvia no alcanzan para hablar de suelo quemado.
        cuerpo = (
            "No se registran huellas de calor recientes cerca de este punto."
            if slope_deg is not None and mm_3h is not None
            else "La lluvia prevista y la pendiente quedan bajo los umbrales provisionales de susceptibilidad."
        )
    elif nivel == "alto":
        cuerpo = (
            "Lluvia intensa sobre suelo con huella de calor, con pendiente fuerte o isoterma 0 °C alta. "
            "En laderas o quebradas quemadas el agua escurre más rápido."
        )
    elif nivel == "moderado":
        cuerpo = (
            "La lluvia y el terreno de este punto merecen atención. "
            "En laderas o quebradas quemadas el agua puede escurrir más rápido."
        )
    else:
        cuerpo = (
            "La lluvia prevista, la pendiente y la huella de calor quedan bajo los umbrales "
            "provisionales de susceptibilidad."
        )
    datos: list[str] = []
    if slope_deg is not None:
        datos.append(f"Pendiente del terreno: {slope_deg:.1f}°.")
    if scar_ha is not None and scar_ha > 0:
        datos.append(f"Hay {scar_ha:.1f} ha con huella de calor a menos de 5 km.")
    if mm_3h is not None:
        datos.append(f"Lluvia en 3 h: {mm_3h:.1f} mm.")
    if isoterma_m is not None:
        datos.append(f"Isoterma 0 °C: {isoterma_m:.0f} m.")
    if isinstance(dias_desde_incendio, int) and not isinstance(dias_desde_incendio, bool) and dias_desde_incendio >= 0:
        datos.append(f"Días desde el incendio: {dias_desde_incendio}.")
    return " ".join([cuerpo, *datos, ETIQUETA, SENAPRED])
