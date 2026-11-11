"""Medición de rendimiento de BRASA en navegador real (A11Y-02).

Playwright + CDP. Por caso y perfil, 3 corridas en contexto nuevo (caché vacía,
service worker bloqueado, viewport 390×844 táctil):

- FCP y LCP (paint y largest-contentful-paint del PerformanceObserver);
- CLS (layout-shift sin interacción reciente);
- suma de tareas largas (> 50 ms) hasta el load;
- bytes transferidos y número de pedidos por tipo de recurso, y el mayor
  recurso de cada tipo (CDP Network, encodedDataLength).

Perfiles: «4g» (4G rápida, sin límite de CPU) y «3g» (3G lenta — los valores de
slow-3g que ya usa scripts de este repo — con CPU ×4 vía
Emulation.setCPUThrottlingRate).

Salida: <OUT_DIR>/medicion.json con las muestras crudas, la mediana y el peor;
además imprime (y guarda en <OUT_DIR>/medicion.md) una tabla Markdown.
Complementa los presupuestos estáticos de peso_arranque.py y
presupuesto_peso.py: aquí se mide lo que el navegador vive, no tamaños de archivo.

Uso: python scripts/local/medir_rendimiento.py <BASE> <OUT_DIR>
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip('/')
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
CORRIDAS = 3

CASOS = {
    'mi-zona': '/',
    'mapa': '/#/mapa',
    'riesgo': '/#/riesgo',
    'focos': '/focos.html',
    'lite': '/web/lite.html',
}
# Latencia en ms; transferencia en bytes/s (como pide CDP). La 3G lenta reusa
# los números de slow-3g de auditar_movil.py para comparar peras con peras.
PERFILES = {
    '4g': dict(latency=40, downloadThroughput=int(12 * 1024 * 1024 / 8), uploadThroughput=int(4 * 1024 * 1024 / 8), cpu=1, espera=3000),
    '3g': dict(latency=2000, downloadThroughput=int(500 * 1024 / 8 * 0.8), uploadThroughput=int(500 * 1024 / 8 * 0.8), cpu=4, espera=6000),
}

INIT_JS = r"""
window.__perf = { fcp: null, lcp: null, cls: 0, tareas: [] };
try {
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.name === 'first-contentful-paint') window.__perf.fcp = e.startTime; })
    .observe({ type: 'paint', buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__perf.lcp = e.startTime; })
    .observe({ type: 'largest-contentful-paint', buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__perf.cls += e.value; })
    .observe({ type: 'layout-shift', buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__perf.tareas.push({ inicio: e.startTime, ms: e.duration }); })
    .observe({ type: 'longtask', buffered: true });
} catch (e) { window.__perfError = String(e); }
"""

LEER_JS = r"""() => {
  const nav = performance.getEntriesByType('navigation')[0] || {};
  return { ...window.__perf, load: nav.loadEventEnd || 0, domContentLoaded: nav.domContentLoadedEventEnd || 0 };
}"""


def medir_una(browser, url, perfil):
    ctx = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True,
                              locale='es-CL', timezone_id='America/Santiago', service_workers='block')
    page = ctx.new_page()
    page.add_init_script(INIT_JS)
    client = ctx.new_cdp_session(page)
    pedidos = {}
    client.send('Network.enable')
    client.send('Network.setCacheDisabled', {'cacheDisabled': True})
    client.send('Network.emulateNetworkConditions', {'offline': False, 'latency': perfil['latency'],
                                                     'downloadThroughput': perfil['downloadThroughput'],
                                                     'uploadThroughput': perfil['uploadThroughput']})
    if perfil['cpu'] > 1:
        client.send('Emulation.setCPUThrottlingRate', {'rate': perfil['cpu']})
    client.on('Network.requestWillBeSent', lambda e: pedidos.setdefault(e['requestId'], {'url': e['request']['url'], 'tipo': e.get('type', 'Other'), 'bytes': 0}))
    client.on('Network.loadingFinished', lambda e: pedidos[e['requestId']].update({'bytes': e['encodedDataLength']}) if e['requestId'] in pedidos else None)
    page.goto(BASE + url, wait_until='domcontentloaded', timeout=120000)
    try:
        page.wait_for_load_state('load', timeout=120000)
    except Exception:
        pass
    page.wait_for_timeout(perfil['espera'])
    m = page.evaluate(LEER_JS)
    ctx.close()
    por_tipo, mayor = {}, {}
    for p in pedidos.values():
        t = por_tipo.setdefault(p['tipo'], {'n': 0, 'bytes': 0})
        t['n'] += 1
        t['bytes'] += p['bytes']
        if p['bytes'] > mayor.get(p['tipo'], {}).get('bytes', -1):
            mayor[p['tipo']] = {'url': p['url'][-110:], 'bytes': p['bytes']}
    tareas_hasta_load = [t['ms'] for t in m['tareas'] if t['inicio'] <= m['load']] if m['load'] else [t['ms'] for t in m['tareas']]
    return {
        'fcpMs': round(m['fcp'], 1) if m['fcp'] is not None else None,
        'lcpMs': round(m['lcp'], 1) if m['lcp'] is not None else None,
        'cls': round(m['cls'], 4),
        'loadMs': round(m['load'], 1),
        'tareasLargasMs': round(sum(tareas_hasta_load), 1),
        'nTareasLargas': len(tareas_hasta_load),
        'bytes': sum(p['bytes'] for p in pedidos.values()),
        'pedidos': len(pedidos),
        'porTipo': por_tipo,
        'mayorPorTipo': mayor,
        'tareasCrudas': m['tareas'],
    }


NUMERICAS = ['fcpMs', 'lcpMs', 'cls', 'loadMs', 'tareasLargasMs', 'nTareasLargas', 'bytes', 'pedidos']


def resumir(muestras):
    mediana, peor = {}, {}
    for k in NUMERICAS:
        vals = [m[k] for m in muestras if m[k] is not None]
        mediana[k] = round(statistics.median(vals), 2) if vals else None
        peor[k] = round(max(vals), 2) if vals else None
    return mediana, peor


def main():
    res = {'base': BASE, 'casos': {}}
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--no-sandbox'])
        for caso, ruta in CASOS.items():
            res['casos'][caso] = {}
            for perfil_n, perfil in PERFILES.items():
                muestras = []
                for i in range(CORRIDAS):
                    m = medir_una(b, ruta, perfil)
                    muestras.append(m)
                    print(f"{caso} {perfil_n} {i + 1}/{CORRIDAS}: fcp {m['fcpMs']} lcp {m['lcpMs']} cls {m['cls']} "
                          f"tareas {m['tareasLargasMs']} ms bytes {m['bytes']}", flush=True)
                mediana, peor = resumir(muestras)
                res['casos'][caso][perfil_n] = {'muestras': muestras, 'mediana': mediana, 'peor': peor}
        b.close()
    with open(OUT / 'medicion.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    lineas = ['| Caso | Perfil | FCP mediana (peor) | LCP mediana (peor) | CLS mediana (peor) | Tareas largas mediana (peor) | Bytes mediana (peor) | Pedidos |',
              '|---|---|---|---|---|---|---|---|']
    for caso, perfiles in res['casos'].items():
        for perfil_n, r in perfiles.items():
            md, pr = r['mediana'], r['peor']
            lineas.append(f"| {caso} | {perfil_n} | {md['fcpMs']} ({pr['fcpMs']}) | {md['lcpMs']} ({pr['lcpMs']}) | "
                          f"{md['cls']} ({pr['cls']}) | {md['tareasLargasMs']} ms ({pr['tareasLargasMs']}) | "
                          f"{md['bytes']} ({pr['bytes']}) | {md['pedidos']} |")
    tabla = '\n'.join(lineas)
    (OUT / 'medicion.md').write_text(tabla + '\n', encoding='utf-8')
    print('\n' + tabla)


main()
