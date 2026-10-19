"""Informe mensual por región para radios comunitarias y municipios (IDEA-04).

Hermano mensual del boletín de 60 segundos (IDEA-05): con las mismas reglas y
plantillas (sin modelos de lenguaje) arma, por región, el bloque «Así fue el
mes en incendios», listo para leer al aire o pegar en un comunicado:

    python scripts/local/informe_mensual.py --url http://127.0.0.1:8000
    python scripts/local/informe_mensual.py --url http://127.0.0.1:8000 --region Maule
    python scripts/local/informe_mensual.py --url http://127.0.0.1:8000 --mes 2026-09 --json

Lee /api/status, /api/official-fires, /api/incidents, /api/opendata/boton-rojo.json
y /api/risk de un servidor BRASA. La API pública entrega a lo más 14 días de
incendios, incidentes y Botón Rojo, y la DMC solo publica los avisos vigentes:
cada bloque dice hasta dónde llegan sus cifras («al menos N incendios desde el
5 de octubre», «sin datos de CONAF para este mes») y nunca inventa ceros.
Guía de lectura en docs/INFORME_MENSUAL.md.
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date, datetime, timedelta, timezone

import boletin

CHILE_TZ = boletin.CHILE_TZ
VENTANA_API_DIAS = 14  # tope de `hours` de /api/official-fires e /api/incidents y de historia del Botón Rojo
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
# Estados de incidente satelital sin respaldo oficial todavía (los del boletín, más «descartado» aparte).
SIN_CONFIRMAR = ("anomalia", "posible", "reportado")
KIND_TXT = {"viento": "de viento", "calor": "de calor extremo"}


def _dia(value) -> date | None:
    """Fecha (AAAA-MM-DD) de un instante ISO con o sin hora; None si falta o es ilegible."""
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _dia_txt(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]}"


def _corte_txt(iso) -> str:
    """«19 de octubre a las 18:30» en hora de Chile; sin marca del servidor, la hora de generar."""
    dt = None
    if iso:
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            dt = None
    local = (dt or datetime.now(timezone.utc)).astimezone(CHILE_TZ)
    return f"{_dia_txt(local.date())} a las {local:%H:%M}"


def month_info(mes: str, hoy: date) -> dict:
    """Marco del mes pedido: inicio, fin (hoy si es el mes en curso) y hasta dónde alcanza la API."""
    inicio = date.fromisoformat(f"{mes}-01")
    fin_mes = inicio.replace(day=calendar.monthrange(inicio.year, inicio.month)[1])
    return {
        "inicio": inicio,
        "fin_mes": fin_mes,
        "fin": min(fin_mes, hoy),
        "hoy": hoy,
        "nombre": f"{MESES[inicio.month - 1]} de {inicio.year}",
        "actual": inicio <= hoy <= fin_mes,
        "cubierto_desde": max(inicio, hoy - timedelta(days=VENTANA_API_DIAS)),
    }


def _del_mes(d: date | None, mes: dict) -> bool:
    return d is not None and mes["inicio"] <= d <= mes["fin"]


def _en_region(item: dict, region: dict, comuna_region: dict, regiones: list) -> bool:
    """True si el punto cae en la región: por código de comuna si lo trae; si no, por los nombres."""
    try:
        code = int(item.get("comuna_code") or 0)
    except (TypeError, ValueError):
        code = 0
    if code:
        return code in region["comunas"]
    return boletin._region_de(item.get("comuna"), item.get("region"), comuna_region, regiones) == region["code"]


def _lista_dias(dias: list[date]) -> str:
    return "los días " + boletin._lista_y([str(d.day) for d in dias])


def _nota_parcial(mes: dict) -> str:
    if mes["cubierto_desde"] > mes["inicio"]:
        return f" (la API conserva {VENTANA_API_DIAS} días: cifras desde el {_dia_txt(mes['cubierto_desde'])})"
    return ""


def _sin_cobertura(fuente: str, mes: dict) -> str:
    return f"Sin datos de {fuente} para {mes['nombre']}: la API pública solo entrega los últimos {VENTANA_API_DIAS} días."


def _linea_conaf(region: dict, mes: dict, fires: list, comuna_region: dict, regiones: list) -> str:
    if mes["fin"] < mes["cubierto_desde"]:
        return _sin_cobertura("incendios CONAF", mes)
    del_mes = [f for f in fires if _del_mes(_dia(f.get("started_at")), mes) and _en_region(f, region, comuna_region, regiones)]
    ha = round(sum(f.get("area_ha") or 0 for f in del_mes), 1)
    parcial = mes["cubierto_desde"] > mes["inicio"]
    if not del_mes:
        return f"CONAF no informa incendios iniciados en {mes['nombre']} en la región{_nota_parcial(mes)}."
    n = len(del_mes)
    al_menos = "al menos " if parcial else ""
    return (
        f"CONAF informó {al_menos}{n} {boletin._plural(n, 'incendio')} y {ha:g} "
        f"{'hectárea' if ha == 1 else 'hectáreas'} en {mes['nombre']}{_nota_parcial(mes)}."
    )


def _linea_boton_rojo(region: dict, mes: dict, br: list, comuna_region: dict, regiones: list) -> tuple[str, list[date]]:
    """Frase de Botón Rojo y los días pronosticados a futuro (alimentan el cierre)."""
    if not br:
        return "Sin datos del Botón Rojo en la fuente pública.", []
    fechas = {
        d
        for p in br
        if (d := _dia(p.get("date"))) and mes["inicio"] <= d <= mes["fin_mes"] and _en_region(p, region, comuna_region, regiones)
    }
    todas = [_dia(p.get("date")) for p in br if _dia(p.get("date"))]
    min_d = min(todas) if todas else None
    dias_mes = sorted(d for d in fechas if d <= mes["fin"])
    dias_fut = sorted(d for d in fechas if d > mes["fin"])
    if not dias_mes:
        if min_d and min_d > mes["fin"]:
            return (f"Sin datos del Botón Rojo para {mes['nombre']}: el registro público conserva desde el {_dia_txt(min_d)}."), dias_fut
        nota = (
            f" en los días que conserva el registro (desde el {_dia_txt(min_d)})"
            if min_d and min_d > mes["inicio"]
            else f" en {mes['nombre']}"
        )
        return f"CONAF no declaró Botón Rojo en la región{nota}.", dias_fut
    n = len(dias_mes)
    lista = f" ({_lista_dias(dias_mes)})" if n <= 8 else ""
    nota = f" El registro público conserva desde el {_dia_txt(min_d)}." if min_d and min_d > mes["inicio"] else ""
    return f"CONAF declaró Botón Rojo en {n} {boletin._plural(n, 'día')} del mes{lista}.{nota}", dias_fut


def _linea_dmc(region: dict, mes: dict, dmc: dict) -> str:
    """Avisos DMC vigentes (la fuente solo publica los vigentes) cuyo inicio cae en el mes."""
    items: dict = {}
    for code, avisos in (dmc or {}).items():
        try:
            c = int(code)
        except (TypeError, ValueError):
            continue
        if c not in region["comunas"]:
            continue
        for a in avisos or []:
            items.setdefault(a.get("web") or (a.get("headline"), a.get("onset")), a)
    del_mes = [a for a in items.values() if _del_mes(_dia(a.get("onset")), mes)]
    # Un aviso vigente sin fecha legible se cuenta solo en el mes en curso (es actual por definición).
    sin_fecha = [a for a in items.values() if _dia(a.get("onset")) is None] if mes["actual"] else []
    avisos = del_mes + sin_fecha
    if avisos:
        por_kind: dict[str, int] = {}
        for a in avisos:
            kind = KIND_TXT.get(a.get("kind"), a.get("kind") or "de tipo no indicado")
            por_kind[kind] = por_kind.get(kind, 0) + 1
        detalle = boletin._lista_y([f"{n} {k}" for k, n in sorted(por_kind.items())])
        n = len(avisos)
        return (
            f"La DMC emitió {n} {boletin._plural(n, 'aviso')} que "
            f"{'sigue vigente' if n == 1 else 'siguen vigentes'} para la región ({detalle})."
        )
    if mes["actual"]:
        return "La DMC no tiene avisos de viento ni calor vigentes emitidos este mes en la región."
    return f"La fuente solo publica los avisos vigentes: sin datos de la DMC para {mes['nombre']}."


def _linea_incidentes(region: dict, mes: dict, incidents: list, comuna_region: dict, regiones: list) -> str:
    if mes["fin"] < mes["cubierto_desde"]:
        return _sin_cobertura("incidentes BRASA", mes)
    del_mes = [i for i in incidents if _del_mes(_dia(i.get("first_seen_at")), mes) and _en_region(i, region, comuna_region, regiones)]
    parcial = mes["cubierto_desde"] > mes["inicio"]
    if not del_mes:
        return f"BRASA no agrupó focos de calor nuevos en la región{_nota_parcial(mes)}."
    cuentas: dict[str, int] = {}
    for i in del_mes:
        cuentas[i.get("status") or "?"] = cuentas.get(i.get("status") or "?", 0) + 1
    conf = cuentas.get("confirmado", 0)
    ctrl = cuentas.get("controlado", 0) + cuentas.get("extinguido", 0)
    abiertos = sum(cuentas.get(s, 0) for s in SIN_CONFIRMAR)
    desc = cuentas.get("descartado", 0)
    resumen = []
    if conf:
        resumen.append(f"{conf} {boletin._plural(conf, 'confirmado por CONAF', 'confirmados por CONAF')}")
    if ctrl:
        resumen.append(f"{ctrl} {boletin._plural(ctrl, 'controlado o extinguido', 'controlados o extinguidos')}")
    if abiertos:
        resumen.append(f"{abiertos} sin confirmar")
    if desc:
        resumen.append(f"{desc} {boletin._plural(desc, 'descartado')}")
    sensores = sorted({s for i in del_mes for s in (i.get("sensors") or [])})
    n = len(del_mes)
    al_menos = "al menos " if parcial else ""
    texto = (
        f"BRASA agrupó {al_menos}{n} {boletin._plural(n, 'foco de calor', 'focos de calor')} en la región: "
        f"{boletin._lista_y(resumen)}{_nota_parcial(mes)}."
    )
    if sensores:
        texto += f" Señal de los sensores {', '.join(sensores)}."
    return texto


def _cierre(dias_fut: list[date]) -> str:
    if dias_fut:
        return (
            f"Esta semana CONAF pronostica Botón Rojo en la región ({_lista_dias(dias_fut)}): "
            "evita quemas, fogatas y maquinaria que eche chispas al aire libre."
        )
    return "Esta semana: limpia techos y canales, repasa el plan familiar de evacuación y, si ves fuego o humo, llama al 132 (Bomberos)."


def build_block(
    region: dict,
    mes: dict,
    fires: list | None,
    incidents: list | None,
    br: list | None,
    dmc: dict | None,
    corte: str,
    comuna_region: dict,
    regiones: list,
) -> dict:
    """Bloque de una región. None en una fuente = no respondió: el bloque lo dice y sigue."""
    lineas: list[str] = []
    fuentes: list[str] = []

    if fires is None:
        lineas.append("Sin datos de incendios CONAF en este momento.")
    else:
        fuentes.append("CONAF (incendios)")
        lineas.append(_linea_conaf(region, mes, fires, comuna_region, regiones))

    dias_fut: list[date] = []
    if br is None:
        lineas.append("Sin datos del Botón Rojo de CONAF en este momento.")
    else:
        fuentes.append("CONAF (Botón Rojo)")
        linea, dias_fut = _linea_boton_rojo(region, mes, br, comuna_region, regiones)
        lineas.append(linea)

    if dmc is None:
        lineas.append("Sin datos de la DMC en este momento.")
    else:
        fuentes.append("DMC (avisos CAP)")
        lineas.append(_linea_dmc(region, mes, dmc))

    if incidents is None:
        lineas.append("Sin datos del monitoreo satelital en este momento.")
    else:
        fuentes.append("BRASA (NASA FIRMS y NOAA GOES)")
        lineas.append(_linea_incidentes(region, mes, incidents, comuna_region, regiones))

    lineas.append(_cierre(dias_fut))
    if fuentes:
        lineas.append(f"Fuentes: {boletin._lista_y(fuentes)}, al corte del {corte}.")
    else:
        lineas.append("Ninguna fuente respondió en este momento.")

    texto = " ".join([f"{region['name']}, {mes['nombre']}:", *lineas])
    return {"region": region["name"], "mes": mes["nombre"], "texto": texto, "fuentes": fuentes}


def main() -> int:
    parser = argparse.ArgumentParser(description="Informe mensual de incendios por región para radios y municipios.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base del servidor BRASA")
    parser.add_argument("--mes", help="Mes del informe AAAA-MM (el mes en curso si se omite)")
    parser.add_argument("--region", help="Solo esta región (nombre, con o sin tildes)")
    parser.add_argument("--json", action="store_true", help="Salida en JSON en vez de texto")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    hoy = datetime.now(CHILE_TZ).date()
    try:
        mes = month_info(args.mes or hoy.strftime("%Y-%m"), hoy)
    except ValueError:
        sys.exit("--mes debe ser AAAA-MM")

    regiones, comuna_region = boletin.load_territory()
    if args.region:
        wanted = boletin.fold(args.region)
        regiones = [r for r in regiones if r["fold"] == wanted]
        if not regiones:
            sys.exit(
                f"Región no encontrada: {args.region}. Usa uno de estos nombres: "
                + ", ".join(r["name"] for r in boletin.load_territory()[0])
            )

    status = boletin.fetch_json(f"{base}/api/status")
    horas = VENTANA_API_DIAS * 24
    fires_payload = boletin.fetch_json(f"{base}/api/official-fires?hours={horas}")
    incidents_payload = boletin.fetch_json(f"{base}/api/incidents?hours={horas}")
    br_payload = boletin.fetch_json(f"{base}/api/opendata/boton-rojo.json?days={VENTANA_API_DIAS}")
    risk = boletin.fetch_json(f"{base}/api/risk")
    fires = fires_payload.get("fires") if fires_payload else None
    incidents = incidents_payload.get("incidents") if incidents_payload else None
    br = [f.get("properties") or {} for f in br_payload.get("features", [])] if br_payload else None
    dmc = risk.get("dmc") if risk else None
    for ruta, payload in (
        ("/api/official-fires", fires_payload),
        ("/api/incidents", incidents_payload),
        ("/api/opendata/boton-rojo.json", br_payload),
        ("/api/risk", risk),
    ):
        if payload is None:
            print(f"Aviso: {ruta} no respondió; el bloque lo dirá en el informe.", file=sys.stderr)

    corte = _corte_txt(status.get("last_ingest_at") if status else None)
    bloques = [build_block(r, mes, fires, incidents, br, dmc, corte, comuna_region, regiones) for r in regiones]
    if args.json:
        print(json.dumps(bloques, ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(b["texto"] for b in bloques))
    return 0


if __name__ == "__main__":
    sys.exit(main())
