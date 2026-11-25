"""Comparación de rendimiento entre dos despliegues de BRASA en la misma instancia de Chromium (PR1).

`medir_rendimiento.py` mide un despliegue; este runner enfrenta dos URLs (base y
candidata) sin cerrar el navegador entre muestras, para que ambas partes compartan la
misma máquina, versión de Chromium y estado térmico. Cada par de muestras se mide en
orden alterno (base/candidata, luego candidata/base) y cada muestra vive en un contexto
nuevo e independiente.

Una comparación por escenario y ruta solo es válida si ambas partes tienen el mínimo de
muestras completas y ninguna incompleta: las mediana/peor se calculan con las completas
y el conteo de incompletas invalida la comparación (no la oculta). Los errores del
producto se distinguen de los externos y de los esperados-sin-señal.

Códigos de salida: 0 = sin errores del producto y comparaciones válidas; 1 = errores del
producto en alguna parte; 2 = comparaciones invalidadas (incompletas o faltas de
muestras completas) sin errores del producto.

Uso (los filtros recortan la matriz para jobs de CI manejables):

    python scripts/local/comparar_rendimiento.py \
        --base URL --candidata URL --out DIR \
        [--device movil|escritorio] [--network normal|lenta] [--cpu 1|4] \
        [--cache fria|caliente|offline] [--ruta ID] [--muestras N] \
        [--revision-base HASH] [--revision-candidata HASH] [--hash-datos TEXTO] \
        [--integracion-real] [--retraso-config-ms MS] [--timeout-s S]

(--candidate y --samples son alias aceptados.)

Salida incremental: <OUT>/comparacion.json se reescribe tras cada muestra (y
<OUT>/muestras-base.jsonl / <OUT>/muestras-candidata.jsonl acumulan una línea por
muestra), capturas comparables con nombres idénticos en <OUT>/capturas/base/ y
<OUT>/capturas/candidata/, y el informe <OUT>/comparacion.md al final.
"""
from __future__ import annotations

import sys
from pathlib import Path

import medir_rendimiento as mr


def parsear_args(argv=None):
    return mr.parsear_args(argv, comparacion=True)


def lado_de(args, lado: str, escenario: dict, numero: int, opciones: dict, browser, out: Path) -> dict:
    """Una muestra de un lado: URL y carpeta de capturas del lado, escenario idéntico al otro."""
    url = args.base if lado == 'base' else args.candidata
    dir_capturas = out / 'capturas' / lado
    return mr.medir_contexto(browser, url, escenario, escenario['ruta'], numero, opciones, dir_capturas)


def comparar(muestras_base: list, muestras_candidata: list, minimo: int = mr.MIN_MUESTRAS) -> dict:
    """Resumen de cada lado por escenario y ruta, y validez de la comparación con sus motivos."""
    grupos_base = mr.agrupar(muestras_base)
    grupos_candidata = mr.agrupar(muestras_candidata)
    claves = list(dict.fromkeys([*grupos_base, *grupos_candidata]))
    salida = {}
    for clave in claves:
        resumen_base = mr.resumir_muestras(grupos_base.get(clave, []))
        resumen_candidata = mr.resumir_muestras(grupos_candidata.get(clave, []))
        valida, motivos = mr.comparacion_valida(resumen_base, resumen_candidata, minimo)
        salida[clave] = {'base': resumen_base, 'candidata': resumen_candidata, 'valida': valida, 'motivos': motivos}
    return salida


def codigo_salida(datos: dict) -> int:
    comparaciones = datos.get('comparacion', {}).values()
    if any(v['base']['errores'].get('producto', 0) or v['candidata']['errores'].get('producto', 0) for v in comparaciones):
        return 1
    if any(not v['valida'] for v in comparaciones):
        return 2
    return 0


def _fmt(valor):
    return '—' if valor is None else f"{valor} ms"


def _delta(base, candidata):
    cambio = mr.delta_porcentaje(base, candidata)
    if cambio is None:
        return '—'
    signo = '+' if cambio > 0 else ''
    return f"{signo}{cambio} %"


def informe_markdown(datos: dict) -> str:
    meta = datos.get('metadatos', {})
    comparaciones = datos.get('comparacion', {})
    lineas = [
        '# Comparación integral de rendimiento: base vs candidata', '',
        f"Generada: {meta.get('generadoIso')} · Chromium {meta.get('navegador')} · Playwright {meta.get('playwright') or '—'}",
        f"- Base: {meta.get('base', '')}" + (f" · revisión {meta.get('revisionBase')}" if meta.get('revisionBase') else ''),
        f"- Candidata: {meta.get('candidata', '')}" + (f" · revisión {meta.get('revisionCandidata')}" if meta.get('revisionCandidata') else ''),
        f"- Hashes de datos provistos: {'; '.join(meta.get('hashesDatos') or []) or '—'}",
        f"- Perfiles: dispositivos {', '.join(meta.get('dispositivos', []))} · redes {', '.join(meta.get('redes', []))} · "
        f"CPU ×{', ×'.join(str(c) for c in meta.get('cpus', []))} · caché {', '.join(meta.get('caches', []))} · "
        f"{meta.get('muestras')} muestras por escenario y lado.",
        f"- Fuentes externas: {'permitidas (--integracion-real)' if meta.get('integracionReal') else 'bloqueadas idénticamente (tiles.openfreemap.org, gibs.earthdata.nasa.gov)'}.",
        f"- Retraso de /api/config: {meta.get('retrasoConfigMs') or 0} ms · timeout por paso: hasta {meta.get('timeoutS')} s.",
        '- Orden de medición: pares alternos base/candidata y candidata/base sobre el mismo navegador; cada muestra en un contexto nuevo.', '',
    ]
    if meta.get('advertenciaOrigen'):
        lineas += [f"**Advertencia:** {meta['advertenciaOrigen']}.", '']
    lineas += [
        'Mediana (peor) en ms, calculada solo con muestras completas; Δ es el cambio porcentual de la candidata respecto de la base.', '',
        '| Escenario | Ruta | Paso | Base | Candidata | Δ | Base peor | Candidata peor | Válida |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for clave, comp in comparaciones.items():
        escenario_txt, ruta = clave.rsplit('/', 1)
        for paso in mr.PASOS:
            rb = comp['base']['pasos'].get(paso, {})
            rc = comp['candidata']['pasos'].get(paso, {})
            if rb.get('nUtil', 0) == 0 and rc.get('nUtil', 0) == 0:
                continue  # paso que no aplica a esta ruta (p. ej. desdePortada en la portada)
            lineas.append(
                f"| {escenario_txt} | {ruta} | {paso} | {_fmt(rb.get('medianaMs'))} | {_fmt(rc.get('medianaMs'))} | "
                f"{_delta(rb.get('medianaMs'), rc.get('medianaMs'))} | {_fmt(rb.get('peorMs'))} | {_fmt(rc.get('peorMs'))} | "
                f"{'sí' if comp['valida'] else 'NO'} |")
    lineas += [
        '', '## Documento, bytes y errores', '',
        '| Escenario | Ruta | FCP base→cand. | LCP base→cand. | Bytes red base→cand. | Errores prod. base/cand. | Completas base/cand. | Válida | Motivos |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for clave, comp in comparaciones.items():
        escenario_txt, ruta = clave.rsplit('/', 1)
        rb, rc = comp['base'], comp['candidata']
        lineas.append(
            f"| {escenario_txt} | {ruta} | "
            f"{rb['documento'].get('fcpMedianaMs')}→{rc['documento'].get('fcpMedianaMs')} | "
            f"{rb['documento'].get('lcpMedianaMs')}→{rc['documento'].get('lcpMedianaMs')} | "
            f"{rb['bytes'].get('bytesRedMediana')}→{rc['bytes'].get('bytesRedMediana')} B | "
            f"{rb['errores'].get('producto')}/{rc['errores'].get('producto')} | "
            f"{rb['nCompletas']}/{rc['nCompletas']} | {'sí' if comp['valida'] else 'NO'} | {'; '.join(comp['motivos']) or '—'} |")
    lineas += [
        '', '## Bytes por grupo de recurso', '',
        'Mediana de bytes por muestra con muestras completas; Δ es el cambio porcentual de la candidata. '
        '`teselasMapa` (fuentes externas del mapa) se bloquean por defecto: solo cuentan pedidos, sin '
        'bytes. Los grupos sin pedidos en ambos lados se omiten (el JSON los conserva).', '',
        '| Escenario | Ruta | Grupo | Red base | Red cand. | Δ | Caché base→cand. | Pedidos base→cand. | Duplicados base→cand. |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for clave, comp in comparaciones.items():
        escenario_txt, ruta = clave.rsplit('/', 1)
        for grupo in mr.GRUPOS_RECURSOS:
            gb = (comp['base']['bytes'].get('porGrupo') or {}).get(grupo) or {}
            gc = (comp['candidata']['bytes'].get('porGrupo') or {}).get(grupo) or {}
            if not (mr.grupo_informa(gb) or mr.grupo_informa(gc)):
                continue  # grupo sin pedidos en ningún lado: la fila no dice nada
            lineas.append(
                f"| {escenario_txt} | {ruta} | {grupo} | "
                f"{gb.get('bytesRedMediana')} B | {gc.get('bytesRedMediana')} B | "
                f"{_delta(gb.get('bytesRedMediana'), gc.get('bytesRedMediana'))} | "
                f"{gb.get('bytesCacheMediana')}→{gc.get('bytesCacheMediana')} | "
                f"{gb.get('nMediana')}→{gc.get('nMediana')} | "
                f"{gb.get('duplicadosMediana')}→{gc.get('duplicadosMediana')} |")
    invalidas = [clave for clave, comp in comparaciones.items() if not comp['valida']]
    lineas += [
        '', '## Validez', '',
        f"- Comparaciones válidas: {len(comparaciones) - len(invalidas)} de {len(comparaciones)}.",
    ]
    for clave in invalidas:
        lineas.append(f"- **{clave}**: {'; '.join(comparaciones[clave]['motivos'])}.")
    lineas += [
        '', 'Códigos de salida: 0 = sin errores del producto y comparaciones válidas · 1 = errores del producto · '
        '2 = comparaciones invalidadas sin errores del producto.',
        'Cobertura y límites de la medición: docs/RENDIMIENTO_INTEGRAL.md.', '',
    ]
    return '\n'.join(lineas)


def main(argv=None) -> int:
    args = parsear_args(sys.argv[1:] if argv is None else argv)
    opciones = mr.opciones_de(args)
    out = Path(args.out)
    (out / 'capturas' / 'base').mkdir(parents=True, exist_ok=True)
    (out / 'capturas' / 'candidata').mkdir(parents=True, exist_ok=True)
    pw, browser = mr.lanzar_navegador()
    datos = {'metadatos': mr.construir_metadatos(args, browser, comparacion=True),
             'muestrasBase': [], 'muestrasCandidata': [], 'comparacion': {}}
    try:
        for escenario in mr.combinaciones(args.dispositivos, args.redes, args.cpus, args.caches, args.rutas):
            for numero in range(1, args.muestras + 1):
                # Orden alterno por par: base/candidata y luego candidata/base.
                for lado in ('base', 'candidata') if numero % 2 == 1 else ('candidata', 'base'):
                    muestra = lado_de(args, lado, escenario, numero, opciones, browser, out)
                    datos['muestrasBase' if lado == 'base' else 'muestrasCandidata'].append(muestra)
                    mr.escribir_incremental(out / 'comparacion.json', datos)
                    mr.agregar_jsonl(out / f'muestras-{lado}.jsonl', muestra)
                    print(f"[{lado}] {mr.linea_progreso(muestra)}", flush=True)
        datos['comparacion'] = comparar(datos['muestrasBase'], datos['muestrasCandidata'], args.muestras)
        mr.escribir_incremental(out / 'comparacion.json', datos)
        (out / 'comparacion.md').write_text(informe_markdown(datos), encoding='utf-8')
    finally:
        try:
            browser.close()
            pw.stop()
        except Exception:
            pass
    return codigo_salida(datos)


if __name__ == '__main__':
    sys.exit(main())
