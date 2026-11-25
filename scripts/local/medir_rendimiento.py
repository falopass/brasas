"""Medición integral de rendimiento de BRASA en navegador real (PR1, medición sin cambios funcionales).

Reemplaza la medición de A11Y-02 (FCP/LCP/CLS en 4G y 3G) por una matriz completa:
dispositivo (móvil 390×844 táctil / escritorio 1280×900) × red (normal 40 ms 12 Mbps /
lenta 2000 ms ~400 kbps) × CPU (×1 / ×4) × caché (fría con service worker permitido /
caliente / sin señal), con N contextos independientes por escenario (mínimo 5) y hasta
tres pasos por ruta: primer acceso directo a la URL (incluidas URLs profundas), navegación
SPA desde la portada y reingreso (navegación repetida).

Por muestra se conservan también los errores (JS, consola, HTTP, red) y los timeouts:
nada se descarta. La mediana y el peor se calculan solo con las muestras completas y el
conteo de incompletas invalida la comparación entre dos despliegues, que hace
scripts/local/comparar_rendimiento.py sobre la misma instancia de Chromium.

«Contenido usable» no es el título ni el esqueleto: cada ruta declara un selector de
contenido real (consultado en web/js/views/) y, cuando existe, un selector de fallo
explícito (bloque «Reintentar»). Los estados intermedios quedan como timeout, también
conservados.

REND-02 tanda 5: cada muestra desglosa además sus bytes por grupo de recurso
(infraestructura, viento, teselas de mapa, datos estáticos, API y resto de la app), y la
ruta `mapa-capas` mide el costo de prender capas (infraestructura crítica y viento),
esperando tras el contenido usable a que la red de esos grupos quede quieta para que sus
bytes no se pierdan.

La ruta `mapa-capas-santiago` repite esa combinación acercada a una ubicación real
representativa (centro de Santiago, z=11) con los parámetros lat/lon/z que la vista
interpreta al montar: `directo` mide el encendido inicial ya encuadrado, `desdePortada`
la navegación SPA hasta el encuadre acercado y `reingreso` el encuadre repetido con los
módulos calientes. El contenido usable llega mientras el vuelo animado sigue en curso y
las teselas de infraestructura solo se piden tras `moveend`: antes de la ventana de red
quieta se espera el encuadre de forma verificable (zoom objetivo con tolerancia y mapa
sin movimiento, consultando getMap de /web/js/map.js desde la página) con el resto del
timeout del paso como límite. Si el encuadre o la red quieta no se confirman dentro del
timeout del paso, ese timeout queda registrado como error del medidor y la muestra
incompleta (sus bytes pueden estar truncados); el tiempo hasta el contenido usable no se
toca.

Uso (compatible con la medición anterior: BASE OUT y opcionalmente filtros):

    python scripts/local/medir_rendimiento.py <BASE> <OUT_DIR> [filtros]

    --device movil|escritorio     (alias mobile|desktop; por defecto ambos)
    --network normal|lenta         (alias 4g|3g|fast|slow; por defecto ambas)
    --cpu 1|4                      (por defecto ambos)
    --cache fria|caliente|offline  (alias fría|cold|warm; por defecto las tres)
    --ruta ID [--ruta ID]          (por defecto todas; ver RUTAS)
    --muestras N | --samples N     (mínimo 5)
    --timeout-s S                  (por paso: navegación + espera; por defecto 90)
    --revision TEXTO               (etiqueta del despliegue para el informe)
    --hash-datos TEXTO [...]       (hashes de datos provistos por quien llama)
    --integracion-real             (no bloquea tiles.openfreemap.org ni gibs.earthdata.nasa.gov)
    --retraso-config-ms MS         (retrasa /api/config; ver límites en docs/RENDIMIENTO_INTEGRAL.md)

Salida incremental: <OUT>/medicion.json se reescribe tras cada muestra (y
<OUT>/muestras.jsonl acumula una línea por muestra), capturas comparables en
<OUT>/capturas/ y el informe <OUT>/medicion.md al final. Código de salida: 1 si hubo
errores del producto (los externos y los esperados-sin-señal se distinguen y no fallan).

El módulo se puede importar sin Playwright instalado (las pruebas de
tests/test_medir_rendimiento.py ejercen lo puro): la importación es perezosa y main()
solo corre como script.
"""
from __future__ import annotations

import itertools
import json
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

MIN_MUESTRAS = 5
PASOS = ('directo', 'desdePortada', 'reingreso')
_CLIENTES_CI = itertools.count(1)

# Fuentes externas de la interfaz (teselas del mapa e imagery satelital): fuera del
# control del despliegue. Por defecto se bloquean igual en base y candidata para no
# comparar el azar de terceros; --integracion-real las permite y se registra aparte.
ORIGENES_EXTERNOS = ('tiles.openfreemap.org', 'gibs.earthdata.nasa.gov')

# Desglose de bytes por grupo de recurso (REND-02 tanda 5): el costo de red de una
# muestra separado por qué lo causó. `teselasMapa` son las fuentes externas de arriba
# (bloqueadas por defecto: cuentan los pedidos abortados, sin bytes); `app` es el cascarón
# propio (documento, JS, CSS, service worker y demás); `otros`, cualquier tercero que no
# sea teselas. Todos los grupos aparecen siempre en el desglose, aunque no medan nada.
GRUPOS_RECURSOS = ('infraestructura', 'viento', 'teselasMapa', 'datosEstaticos', 'api', 'app', 'otros')

DISPOSITIVOS = {
    'movil': {'ancho': 390, 'alto': 844, 'tactil': True, 'esMovil': True, 'escala': 2},
    'escritorio': {'ancho': 1280, 'alto': 900, 'tactil': False, 'esMovil': False, 'escala': 1},
}
ALIAS_DISPOSITIVO = {'mobile': 'movil', 'desktop': 'escritorio'}
# Latencia en ms y transferencia en bytes/s, como pide CDP. «lenta» es la 3G lenta que
# ya usaban los scripts del repo (~400 kbps), para seguir comparando peras con peras.
REDES = {
    'normal': {'latencia': 40, 'bajada': 12 * 1024 * 1024 // 8, 'subida': 4 * 1024 * 1024 // 8},
    'lenta': {'latencia': 2000, 'bajada': 400 * 1024 // 8, 'subida': 400 * 1024 // 8},
}
ALIAS_RED = {'4g': 'normal', 'fast': 'normal', '3g': 'lenta', 'slow': 'lenta'}
CPUS = (1, 4)
CACHES = ('fria', 'caliente', 'offline')
ALIAS_CACHE = {'fría': 'fria', 'cold': 'fria', 'warm': 'caliente'}

# Rutas reales de la app, con los selectores exactos de web/js/views/ y las páginas
# estáticas públicas. `listo` es contenido usable (no título ni esqueleto), `fallo` un
# estado de fallo explícito («Reintentar»); `listoPrimero` sirve cuando un bloque
# parcial puede fallar sin que la vista deje de estar pintada (Calidad, Prepárate).
RUTAS = {
    'mi-zona': {'url': '/', 'hash': '#/mi-zona', 'tipo': 'spa',
                'listo': '#zona-b #add-place, .ember-hero',
                'nota': 'acción principal o estado del lugar, nunca solo el título'},
    'mapa': {'url': '/#/mapa', 'hash': '#/mapa', 'tipo': 'spa',
             'listo': '#map-listas h2', 'fallo': '#map-carga-err .callout-warn, #map-err .callout-warn',
             'nota': 'las listas de la hoja llegan con los datos, no con el cascarón'},
    # REND-02 tanda 5: costo medido de prender capas (infraestructura crítica y viento).
    # Los nombres son los públicos de web/js/capas.js (`url:` de CAPAS) y van en el orden
    # del control, el mismo con el que la vista reescribe la URL (capasToUrl): el hash queda
    # estable y el recolector no pierde el criterio. En el encuadre inicial (país) la
    # infraestructura no debe pedir teselas (loadInfra solo baja el índice
    # /web/data/infraestructura/indice.json y corta bajo zoom 10, INFRA_MINZOOM): se mide
    # el costo de prender la capa (el índice y /api/wind/grid), no el de pintarla. Tras el
    # contenido usable, `redQuieta` espera a que no queden pedidos en vuelo de esos grupos
    # (~500 ms) antes de cerrar la medición del paso, para que sus bytes no se pierdan.
    'mapa-capas': {'url': '/#/mapa?capas=focos,viento,infraestructura',
                   'hash': '#/mapa?capas=focos,viento,infraestructura', 'tipo': 'spa',
                   'listo': '#map-listas h2', 'fallo': '#map-carga-err .callout-warn, #map-err .callout-warn',
                   'redQuieta': ('infraestructura', 'viento')},
    # REND-02: la misma combinación de capas, acercada a Santiago con los parámetros
    # lat/lon/z que la vista interpreta al montar (fly al encuadre; con lat/lon la vista
    # no reencuadra a los focos). El zoom 11 supera INFRA_MINZOOM (10): tras el vuelo,
    # loadInfra pide las teselas de 1° del encuadre —la clave es su esquina suroeste:
    # -34_-71, la tesela real más grande del catastro. `encuadre` declara el zoom
    # esperado: el contenido usable llega mientras el vuelo animado sigue en curso y las
    # teselas solo se piden tras moveend, así que antes de la ventana de red quieta se
    # espera el encuadre de forma verificable (zoom objetivo con tolerancia y mapa sin
    # movimiento, consultando getMap de /web/js/map.js desde la página) y recién ahí se
    # cierran los bytes; el tiempo util del paso no se toca. El hash lleva todos los
    # parámetros porque updateCapasUrl conserva los que no son `capas` al reescribirlo y
    # el recolector exige hash exacto; `capas` va en el orden del control para que esa
    # reescritura sea idéntica (hash estable durante toda la muestra). Sin depender de
    # terceros: MapLibre viaja con la app y las teselas de infraestructura son archivos
    # estáticos del propio despliegue.
    'mapa-capas-santiago': {'url': '/#/mapa?capas=focos,viento,infraestructura&lat=-33.45&lon=-70.66&z=11',
                            'hash': '#/mapa?capas=focos,viento,infraestructura&lat=-33.45&lon=-70.66&z=11',
                            'tipo': 'spa',
                            'listo': '#map-listas h2', 'fallo': '#map-carga-err .callout-warn, #map-err .callout-warn',
                            'encuadre': {'zoom': 11},
                            'redQuieta': ('infraestructura', 'viento')},
    'riesgo': {'url': '/#/riesgo', 'hash': '#/riesgo', 'tipo': 'spa',
               'listo': '#r-search', 'fallo': '#view .callout-warn [data-retry]',
               'nota': 'el buscador solo está en el render con pronóstico'},
    'casos': {'url': '/#/casos', 'hash': '#/casos', 'tipo': 'spa',
              'listo': '.chips-region', 'fallo': '#view .callout-warn [data-retry]'},
    'caso-penco-2026': {'url': '/#/casos/penco-lirquen-2026', 'hash': '#/casos/penco-lirquen-2026', 'tipo': 'spa',
                        'listo': '.player, .callout.c-nota', 'fallo': '#case-err .callout-warn',
                        'nota': 'URL profunda real: la reconstrucción del caso Penco/Lirquén 2026'},
    'temporada': {'url': '/#/temporada', 'hash': '#/temporada', 'tipo': 'spa',
                  'listo': '#view .t-nota', 'fallo': '#view .callout-warn [data-retry]'},
    'preparate': {'url': '/#/preparate', 'hash': '#/preparate', 'tipo': 'spa',
                  'listo': '#view .fold.caso', 'listoPrimero': True,
                  'nota': 'guía de emergencia utilizable; no mide la preparación del paquete'},
    'alertas': {'url': '/#/alertas', 'hash': '#/alertas', 'tipo': 'spa',
                'listo': '#inbox-body .kpis, #inbox-body .empty', 'fallo': '#inbox-body #retry'},
    'quehago': {'url': '/#/quehago', 'hash': '#/quehago', 'tipo': 'spa', 'listo': '.fold.caso'},
    'calidad': {'url': '/#/calidad', 'hash': '#/calidad', 'tipo': 'spa',
                'listo': '#view .status-badge, #copy-diag', 'fallo': '#view [data-retry]', 'listoPrimero': True,
                'nota': 'estado sano o diagnóstico; los errores parciales se registran aparte'},
    'privacidad': {'url': '/#/privacidad', 'hash': '#/privacidad', 'tipo': 'spa',
                   'listo': '#pr-cuerpo .lede, #pr-cuerpo h2.section', 'fallo': '#pr-cuerpo [data-retry]'},
    'mas': {'url': '/#/mas', 'hash': '#/mas', 'tipo': 'spa', 'listo': '#view ul.indice'},
    'focos': {'url': '/focos.html', 'tipo': 'estatica',
              'listo': '#focos-tabla-wrap:not([hidden]), #focos-vacio:not([hidden])',
              'fallo': '#focos-error:not([hidden])'},
    'lite': {'url': '/web/lite.html', 'tipo': 'estatica', 'listo': '#lite-places > *'},
    'preguntas': {'url': '/web/preguntas.html', 'tipo': 'estatica', 'listo': 'main.faq', 'minTexto': 300},
}

# Recolector en página: FCP/LCP/CLS del documento (se separan del tiempo de ruta usable),
# tareas largas del hilo principal (>50 ms) y un marco por transición que se reinicia con
# P.reset(). La detección de contenido usable corre en la página (sin la latencia de
# ida y vuelta de Python) y los timeouts también quedan como estado.
RECOLECTOR_JS = r"""
(() => {
  const P = window.__brasaPerf = {
    fcp: null, lcp: null, clsDoc: 0, tareas: [],
    ruta: { inicio: null, estado: 'inactivo', ms: null, cls: 0, criterio: null },
    interaccion: null, errorObs: null, doc: { loadMs: null, dclMs: null },
  };
  const inicioDoc = 0; // Incluye TTFB y descarga del documento, no solo la ejecución del hook.
  const lista = (sel) => { try { return sel ? document.querySelector(sel) : null; } catch (e) { return null; } };
  try {
    new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.name === 'first-contentful-paint') P.fcp = e.startTime; })
      .observe({ type: 'paint', buffered: true });
    new PerformanceObserver((l) => { let ultimo = null; for (const e of l.getEntries()) ultimo = e.startTime; if (ultimo !== null) P.lcp = ultimo; })
      .observe({ type: 'largest-contentful-paint', buffered: true });
    new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) { P.clsDoc += e.value; P.ruta.cls += e.value; } })
      .observe({ type: 'layout-shift', buffered: true });
    // Tareas largas del hilo principal (más de 50 ms): bloqueo de procesado, no «tiempo de parseo».
    new PerformanceObserver((l) => { for (const e of l.getEntries()) P.tareas.push({ inicio: e.startTime, ms: e.duration }); })
      .observe({ type: 'longtask', buffered: true });
  } catch (e) { P.errorObs = String(e); }
  const conTexto = (el, min) => el && el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden' &&
    (!min || (el.innerText || '').trim().length >= min);
  setInterval(() => {
    if (P.ruta.estado === 'inactivo') {
      const c = window.__brasaPerfCriterio;
      if (c) P.ruta = { inicio: inicioDoc, estado: 'pendiente', ms: null, cls: 0, criterio: c };
      return;
    }
    if (P.ruta.estado !== 'pendiente' || !P.ruta.criterio) return;
    const c = P.ruta.criterio;
    if (P.ruta.anterior && lista(c.listo) === P.ruta.anterior) return;
    if (P.ruta.hash && location.hash !== P.ruta.hash) return;
    const falloEl = lista(c.fallo);
    const listoEl = lista(c.listo);
    let estado = null;
    if (c.listoPrimero) {
      if (listoEl && conTexto(listoEl, c.minTexto)) estado = 'util';
      else if (falloEl) estado = 'fallo';
    } else if (falloEl) estado = 'fallo';
    else if (listoEl && conTexto(listoEl, c.minTexto)) estado = 'util';
    if (estado) { P.ruta.estado = estado; P.ruta.ms = Math.round((performance.now() - P.ruta.inicio) * 10) / 10; }
  }, 80);
  // Cada transición SPA parte de cero: marca, CLS y criterio nuevos (el FCP/LCP del documento no se tocan).
  P.reset = (criterio) => {
    P.ruta = { inicio: performance.now(), estado: 'pendiente', ms: null, cls: 0,
      criterio, anterior: lista(criterio.listo), hash: criterio.hash };
  };
  // Interacción sintética: toque → siguiente frame. Latencia sintética, no un INP real.
  document.addEventListener('pointerdown', () => {
    if (!P.interaccion) return;
    const marca = P.interaccion; P.interaccion = null; P.ultimaInteraccion = marca;
    marca.t0 = performance.now();
    requestAnimationFrame(() => { if (marca.t1 === null) marca.t1 = performance.now(); });
  }, true);
  P.armaInteraccion = () => { P.interaccion = { t0: null, t1: null }; };
  P.leer = () => {
    const nav = performance.getEntriesByType('navigation')[0];
    if (nav) { P.doc.loadMs = nav.loadEventEnd || null; P.doc.dclMs = nav.domContentLoadedEventEnd || null; }
    return {
      fcp: P.fcp, lcp: P.lcp, clsDoc: Math.round(P.clsDoc * 10000) / 10000,
      ruta: { estado: P.ruta.estado, ms: P.ruta.ms, cls: Math.round(P.ruta.cls * 10000) / 10000, inicio: P.ruta.inicio },
      tareas: P.tareas, doc: { loadMs: P.doc.loadMs, dclMs: P.doc.dclMs },
      interaccion: P.interaccion, errorObs: P.errorObs,
    };
  };
})();
"""


# ------------------------------------------------------------------ utilidades puras

def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def url_de_ruta(base: str, url_ruta: str) -> str:
    return base.rstrip('/') + url_ruta


def mismo_origen(url: str, base: str) -> bool:
    b = urlparse(base)
    u = urlparse(url)
    if not u.hostname or not b.hostname:
        return False
    return (u.scheme, u.hostname, u.port or (443 if u.scheme == 'https' else 80)) == \
        (b.scheme, b.hostname, b.port or (443 if b.scheme == 'https' else 80))


def es_externa(url: str) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return any(host == origen or host.endswith('.' + origen) for origen in ORIGENES_EXTERNOS)


def clasificar_url(url: str, base: str, bloqueadas: bool = True) -> str:
    """Clase de un URL a efectos de errores: externo controlado, externo permitido o producto."""
    if es_externa(url):
        return 'bloqueado' if bloqueadas else 'externo'
    return 'producto' if mismo_origen(url, base) else 'externo'


def grupo_de_url(url: str, base: str) -> str:
    """Grupo de recurso de un pedido para el desglose de bytes (ver GRUPOS_RECURSOS).

    Los prefijos más específicos se prueban antes que los generales: la infraestructura
    crítica (/web/data/infraestructura/…) es datos estáticos, pero se informa aparte, y la
    grilla de viento (/api/wind/…) es API, pero también. Las teselas de mapa base son las
    fuentes externas de ORIGENES_EXTERNOS.
    """
    if es_externa(url):
        return 'teselasMapa'
    if not mismo_origen(url, base):
        return 'otros'
    ruta = urlparse(url).path
    if ruta.startswith('/web/data/infraestructura/'):
        return 'infraestructura'
    if ruta.startswith('/api/wind/'):
        return 'viento'
    if ruta.startswith('/web/data/'):
        return 'datosEstaticos'
    if ruta.startswith('/api/'):
        return 'api'
    return 'app'


def clase_texto(texto: str) -> str:
    """Clase de un mensaje de consola o de JS por su contenido (menciona una fuente externa)."""
    bajo = (texto or '').lower()
    return 'externo' if any(origen in bajo for origen in ORIGENES_EXTERNOS) else 'producto'


def mediana_peor(valores):
    limpios = [v for v in valores if v is not None]
    if not limpios:
        return None, None
    return round(statistics.median(limpios), 1), round(max(limpios), 1)


def estado_global(pasos: dict) -> str:
    """Peor estado de una muestra: los pasos útiles no tapan un fallo ni un timeout."""
    if not pasos:
        return 'fallo'
    estados = {p.get('estado') for p in pasos.values()}
    if estados == {'util'}:
        return 'util'
    if 'timeout' in estados:
        return 'timeout'
    if estados == {'fallo'}:
        return 'fallo'
    return 'mixto'


def resumen_red(pedidos: dict, base: str) -> dict:
    """Bytes por la red (encodedDataLength de respuestas servidas por red) y desde caché/SW.

    encodedDataLength es el tamaño en el cable (comprimido): no se suma como si fuera
    bytes decodificados (eso CDP no lo entrega por pedido). Los duplicados se cuentan:
    una misma URL puede pedirse más de una vez. Además desglosa por grupo de recurso
    (grupo_de_url): de cada grupo, n pedidos, bytesRed, bytesCache y duplicados; todos
    los grupos aparecen siempre, midan o no (los grupos vacíos también dicen algo).
    """
    por_tipo = {}
    por_grupo = {g: {'n': 0, 'bytesRed': 0, 'bytesCache': 0, 'duplicados': 0, '_urls': set()}
                 for g in GRUPOS_RECURSOS}
    for p in pedidos.values():
        t = por_tipo.setdefault(p.get('tipo', 'Other'), {'n': 0, 'bytesRed': 0, 'bytesCache': 0})
        t['n'] += 1
        grupo = por_grupo[grupo_de_url(p.get('url', ''), base)]
        grupo['n'] += 1
        url = p.get('url', '')
        if url in grupo['_urls']:
            grupo['duplicados'] += 1
        else:
            grupo['_urls'].add(url)
        if p.get('desdeCache') or p.get('desdeSw'):
            t['bytesCache'] += p.get('bytes', 0)
            grupo['bytesCache'] += p.get('bytes', 0)
        else:
            t['bytesRed'] += p.get('bytes', 0)
            grupo['bytesRed'] += p.get('bytes', 0)
    for grupo in por_grupo.values():
        del grupo['_urls']
    urls = [p.get('url', '') for p in pedidos.values()]
    unicos = len(set(urls))
    return {
        'bytesRed': sum(t['bytesRed'] for t in por_tipo.values()),
        'bytesCache': sum(t['bytesCache'] for t in por_tipo.values()),
        'pedidos': len(pedidos), 'pedidosUnicos': unicos, 'duplicados': len(urls) - unicos,
        'porTipo': por_tipo, 'porGrupo': por_grupo,
    }


def valores_grupo(completas: list, grupo: str, campo: str) -> list:
    """Valores de un campo del desglose por grupo, solo de muestras completas que lo traen."""
    salida = []
    for m in completas:
        datos = ((m.get('bytes') or {}).get('porGrupo') or {}).get(grupo) or {}
        valor = datos.get(campo)
        if valor is not None:
            salida.append(valor)
    return salida


def resumir_muestras(muestras: list) -> dict:
    """Mediana y peor solo con muestras completas; los errores y las incompletas se cuentan, no se descartan."""
    completas = [m for m in muestras if m.get('completa')]
    res = {
        'n': len(muestras), 'nCompletas': len(completas), 'nIncompletas': len(muestras) - len(completas),
        'porEstado': dict(Counter(m.get('estado') for m in muestras)),
        'pasos': {}, 'documento': {}, 'errores': {}, 'bytes': {}, 'interaccion': {},
    }
    for paso in PASOS:
        propios = [m['pasos'][paso] for m in completas if (m.get('pasos') or {}).get(paso)]
        valores = [p['ms'] for p in propios if p['estado'] == 'util' and p['ms'] is not None]
        mediana, peor = mediana_peor(valores)
        tareas = [p.get('tareasLargasMs') for p in propios if p['estado'] == 'util' and p.get('tareasLargasMs') is not None]
        mediana_t, peor_t = mediana_peor(tareas)
        res['pasos'][paso] = {'medianaMs': mediana, 'peorMs': peor, 'nUtil': len(valores),
                              'tareasLargasMedianaMs': mediana_t, 'tareasLargasPeorMs': peor_t}
    fcp = [m['documento']['fcpMs'] for m in completas if (m.get('documento') or {}).get('fcpMs') is not None]
    lcp = [m['documento']['lcpMs'] for m in completas if (m.get('documento') or {}).get('lcpMs') is not None]
    med_fcp, peor_fcp = mediana_peor(fcp)
    med_lcp, peor_lcp = mediana_peor(lcp)
    res['documento'] = {'fcpMedianaMs': med_fcp, 'fcpPeorMs': peor_fcp, 'lcpMedianaMs': med_lcp, 'lcpPeorMs': peor_lcp}
    clases = Counter(e.get('clase') for m in muestras for e in (m.get('errores') or []))
    res['errores'] = {k: clases.get(k, 0) for k in ('producto', 'externo', 'bloqueado', 'esperado', 'medidor')}
    bytes_red = [m['bytes']['bytesRed'] for m in completas if (m.get('bytes') or {}).get('bytesRed') is not None]
    med_b, peor_b = mediana_peor(bytes_red)
    bytes_cache = [m['bytes']['bytesCache'] for m in completas if (m.get('bytes') or {}).get('bytesCache') is not None]
    med_c, _ = mediana_peor(bytes_cache)
    res['bytes'] = {'bytesRedMediana': med_b, 'bytesRedPeor': peor_b, 'bytesCacheMediana': med_c}
    # Desglose por grupo de recurso (REND-02 tanda 5): mediana/peor solo con muestras
    # completas, como el resto. Los grupos sin pedidos quedan en None (se omiten en el
    # informe, no en el JSON).
    res['bytes']['porGrupo'] = {}
    for grupo in GRUPOS_RECURSOS:
        med_rg, peor_rg = mediana_peor(valores_grupo(completas, grupo, 'bytesRed'))
        res['bytes']['porGrupo'][grupo] = {
            'nMediana': mediana_peor(valores_grupo(completas, grupo, 'n'))[0],
            'bytesRedMediana': med_rg, 'bytesRedPeor': peor_rg,
            'bytesCacheMediana': mediana_peor(valores_grupo(completas, grupo, 'bytesCache'))[0],
            'duplicadosMediana': mediana_peor(valores_grupo(completas, grupo, 'duplicados'))[0],
        }
    inter = [m.get('interaccionRafMs') for m in completas if m.get('interaccionRafMs') is not None]
    med_i, _ = mediana_peor(inter)
    res['interaccion'] = {'rafSinteticoMedianaMs': med_i, 'n': len(inter)}
    return res


def comparacion_valida(resumen_base: dict, resumen_candidata: dict, minimo: int = MIN_MUESTRAS) -> tuple[bool, list]:
    """Una comparación vale si ambas partes tienen el mínimo de completas y ninguna incompleta."""
    motivos = []
    if resumen_base['nCompletas'] < minimo:
        motivos.append(f"base tiene {resumen_base['nCompletas']} completas (mínimo {minimo})")
    if resumen_candidata['nCompletas'] < minimo:
        motivos.append(f"candidata tiene {resumen_candidata['nCompletas']} completas (mínimo {minimo})")
    if resumen_base['nIncompletas'] or resumen_candidata['nIncompletas']:
        motivos.append(f"incompletas: base {resumen_base['nIncompletas']}, candidata {resumen_candidata['nIncompletas']}")
    return (not motivos), motivos


def codigo_salida(resumen: dict) -> int:
    return 1 if resumen['errores'].get('producto', 0) > 0 else 0


def codigo_salida_global(resumenes: dict) -> int:
    return 1 if any(codigo_salida(r) for r in resumenes.values()) else 0


def delta_porcentaje(base, candidata):
    """Cambio porcentual de la candidata respecto de la base; None si falta alguna mediana."""
    if base is None or candidata is None or not base:
        return None
    return round((candidata - base) / base * 100, 1)


def escribir_incremental(ruta: Path, datos) -> None:
    """Escribe el JSON completo en cada muestra: una corrida interrumpida deja el informe hasta ahí."""
    temporal = ruta.with_name(ruta.name + '.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(temporal, ruta)


def agregar_jsonl(ruta: Path, muestra: dict) -> None:
    with open(ruta, 'a', encoding='utf-8') as f:
        f.write(json.dumps(muestra, ensure_ascii=False) + '\n')


# ------------------------------------------------------------------ CLI

def _lista(parser, crudos, orden, alias, bandera):
    if not crudos:
        return list(orden)
    salida = []
    for crudo in crudos:
        for parte in crudo.split(','):
            parte = parte.strip().lower()
            if not parte:
                continue
            canonica = alias.get(parte, parte)
            if canonica not in orden:
                parser.error(f'{bandera}: «{parte}» no es válido. Opciones: {", ".join(str(x) for x in orden)}')
            if canonica not in salida:
                salida.append(canonica)
    return salida


def _lista_cpu(parser, crudos):
    if not crudos:
        return list(CPUS)
    salida = []
    for crudo in crudos:
        for parte in crudo.split(','):
            parte = parte.strip()
            if not parte:
                continue
            try:
                valor = int(parte)
            except ValueError:
                parser.error(f'--cpu: «{parte}» no es un número')
            if valor not in CPUS:
                parser.error(f'--cpu: «{valor}» no es válido. Opciones: 1, 4')
            if valor not in salida:
                salida.append(valor)
    return salida


def parsear_args(argv: list, comparacion: bool = False):
    import argparse

    descripcion = 'Medición integral de rendimiento de BRASA en navegador real (ver docs/RENDIMIENTO_INTEGRAL.md).'
    parser = argparse.ArgumentParser(description=descripcion)
    if comparacion:
        parser.add_argument('--base', required=True, help='URL del despliegue de referencia')
        parser.add_argument('--candidata', '--candidate', dest='candidata', required=True, help='URL del despliegue candidato')
        parser.add_argument('--out', required=True, help='directorio de salida')
        parser.add_argument('--revision-base', dest='revision_base', default=None, help='revisión de la base (p. ej. hash)')
        parser.add_argument('--revision-candidata', dest='revision_candidata', default=None, help='revisión de la candidata')
    else:
        parser.add_argument('base', help='URL base del despliegue')
        parser.add_argument('out', help='directorio de salida')
        parser.add_argument('--revision', default=None, help='revisión del despliegue (p. ej. hash)')
    parser.add_argument('--device', '--dispositivo', dest='device', action='append', default=[],
                        help='movil|escritorio (alias mobile|desktop); por defecto ambos')
    parser.add_argument('--network', '--red', dest='network', action='append', default=[],
                        help='normal|lenta (alias 4g|3g|fast|slow); por defecto ambas')
    parser.add_argument('--cpu', dest='cpu', action='append', default=[], help='1|4; por defecto ambos')
    parser.add_argument('--cache', dest='cache', action='append', default=[],
                        help='fria|caliente|offline (alias fría|cold|warm); por defecto las tres')
    parser.add_argument('--ruta', '--route', dest='ruta', action='append', default=[],
                        help='id de ruta (ver RUTAS); por defecto todas')
    parser.add_argument('--muestras', '--samples', dest='muestras', type=int, default=MIN_MUESTRAS,
                        help=f'número de muestras por escenario (mínimo {MIN_MUESTRAS})')
    parser.add_argument('--timeout-s', dest='timeout_s', type=float, default=90.0,
                        help='segundos por paso (navegación + espera de contenido usable)')
    parser.add_argument('--hash-datos', dest='hash_datos', action='append', default=[],
                        help='hash de datos provisto por quien llama (repetible)')
    parser.add_argument('--integracion-real', dest='integracion_real', action='store_true',
                        help='permite las fuentes externas en vez de bloquearlas (se registra aparte)')
    parser.add_argument('--retraso-config-ms', dest='retraso_config_ms', type=int, default=0,
                        help='retrasa /api/config para medir el arranque con datos tardíos')
    args = parser.parse_args(argv)
    args.dispositivos = _lista(parser, args.device, DISPOSITIVOS, ALIAS_DISPOSITIVO, '--device')
    args.redes = _lista(parser, args.network, REDES, ALIAS_RED, '--network')
    args.cpus = _lista_cpu(parser, args.cpu)
    args.caches = _lista(parser, args.cache, CACHES, ALIAS_CACHE, '--cache')
    args.rutas = _lista(parser, args.ruta, RUTAS, {}, '--ruta')
    if args.muestras < MIN_MUESTRAS:
        parser.error(f'--muestras debe ser {MIN_MUESTRAS} o más (mínimo estadístico); recibido: {args.muestras}')
    if args.timeout_s <= 0 or args.retraso_config_ms < 0:
        parser.error('El timeout debe ser positivo y el retraso no puede ser negativo.')
    return args


def combinaciones(dispositivos: list, redes: list, cpus: list, caches: list, rutas: list) -> list:
    return [{'dispositivo': d, 'red': n, 'cpu': c, 'cache': k, 'ruta': r}
            for d in dispositivos for n in redes for c in cpus for k in caches for r in rutas]


def orden_pares(n: int) -> list:
    """Orden de medición por pares: A/B, luego B/A, alternando cada par (cancela el deriva de la máquina)."""
    return [lado for i in range(n) for lado in (('base', 'candidata') if i % 2 == 0 else ('candidata', 'base'))]


# ------------------------------------------------------------------ criterios por ruta

def criterio_de(ruta_id: str) -> dict:
    ruta = RUTAS[ruta_id]
    return {'listo': ruta['listo'], 'fallo': ruta.get('fallo'), 'hash': ruta.get('hash'),
            'minTexto': ruta.get('minTexto') or 0, 'listoPrimero': bool(ruta.get('listoPrimero'))}


def criterio_js(ruta_id: str) -> str:
    return 'window.__brasaPerfCriterio = ' + json.dumps(criterio_de(ruta_id), ensure_ascii=False) + ';'


def criterios_documento_js() -> str:
    """Un solo init script: Playwright no garantiza orden entre scripts sucesivos."""
    criterios = [
        {'url': r['url'], 'hash': r.get('hash'), 'criterio': criterio_de(rid)}
        for rid, r in RUTAS.items()
    ]
    return f"""
    (() => {{
      const criterios = {json.dumps(criterios)};
      const hash = location.hash || '#/mi-zona';
      const r = criterios.find(r => r.hash ? location.pathname === '/' && r.hash === hash :
        location.pathname === r.url);
      window.__brasaPerfCriterio = r ? r.criterio : null;
    }})();
    """


def clave_de_muestra(m: dict) -> str:
    return f"{m['dispositivo']}/{m['red']}/cpu{m['cpu']}/{m['cache']}/{m['ruta']}"


def agrupar(muestras: list) -> dict:
    grupos = {}
    for m in muestras:
        grupos.setdefault(clave_de_muestra(m), []).append(m)
    return grupos


def resumir_por_escenario(muestras: list) -> dict:
    return {clave: resumir_muestras(grupo) for clave, grupo in agrupar(muestras).items()}


# ------------------------------------------------------------------ recolección con navegador

class Seguimiento:
    """Pedidos y errores de un contexto: todo se acumula, nada se descarta.

    Clases de error: «producto» (falla del despliegue medido, hace fallar la corrida),
    «externo» (tercero permitido con --integracion-real), «bloqueado» (tercero bloqueado
    a propósito: esperado), «esperado» (sin señal: respuesta sintética del service worker
    o red caída en modo offline) y «medidor» (falla propia del instrumento).
    """

    def __init__(self, base: str, escenario: dict, opciones: dict):
        self.base = base
        self.escenario = escenario
        self.opciones = opciones
        self.pedidos = {}
        self.errores = []
        self.client = None
        self.page = None

    def reiniciar(self) -> None:
        """Borra lo acumulado por la preparación: la medición parte limpia."""
        self.pedidos.clear()
        self.errores.clear()

    def error(self, entrada: dict) -> None:
        self.errores.append(entrada)

    def enganchar(self, ctx, page) -> None:
        self.page = page
        self.client = ctx.new_cdp_session(page)
        self.client.send('Network.enable')
        self.client.send('Performance.enable')
        red = REDES[self.escenario['red']]
        self.client.send('Network.emulateNetworkConditions', {
            'offline': False, 'latency': red['latencia'],
            'downloadThroughput': red['bajada'], 'uploadThroughput': red['subida']})
        if self.escenario['cpu'] > 1:
            self.client.send('Emulation.setCPUThrottlingRate', {'rate': self.escenario['cpu']})
        if not self.opciones.get('integracionReal'):
            # Red de respaldo por si alguna petición nacida en el service worker escapa a la ruta de Playwright.
            try:
                self.client.send('Network.setBlockedURLs', {'urls': [f'*{host}*' for host in ORIGENES_EXTERNOS]})
            except Exception:
                pass
        self.client.on('Network.requestWillBeSent', self._al_pedido)
        self.client.on('Network.responseReceived', self._al_respuesta)
        self.client.on('Network.loadingFinished', self._al_termino)
        self.client.on('Network.loadingFailed', self._al_fallo_red)
        page.on('pageerror', self._al_error_js)
        page.on('console', self._al_consola)

    def _al_pedido(self, e: dict) -> None:
        pedido = e.get('request') or {}
        self.pedidos.setdefault(e.get('requestId'), {
            'url': pedido.get('url', ''), 'tipo': e.get('type', 'Other'),
            'bytes': 0, 'desdeCache': False, 'desdeSw': False, 'estado': None, 'fin': False})

    def _al_respuesta(self, e: dict) -> None:
        p = self.pedidos.get(e.get('requestId'))
        if not p:
            return
        resp = e.get('response') or {}
        p['estado'] = resp.get('status')
        p['desdeCache'] = bool(resp.get('fromDiskCache'))
        p['desdeSw'] = bool(resp.get('fromServiceWorker'))
        estado = resp.get('status') or 0
        if estado >= 400:
            clase = 'esperado' if (self.escenario['cache'] == 'offline' and estado == 503 and '/api/' in p['url']) else \
                clasificar_url(p['url'], self.base, bloqueadas=not self.opciones.get('integracionReal'))
            self.error({'tipo': 'http', 'url': p['url'], 'estado': estado, 'clase': clase})

    def _al_termino(self, e: dict) -> None:
        p = self.pedidos.get(e.get('requestId'))
        if p is not None:
            p['bytes'] = e.get('encodedDataLength') or 0
            p['fin'] = True  # sin pedidos en vuelo se mide la red quieta de las capas

    def _al_fallo_red(self, e: dict) -> None:
        p = self.pedidos.get(e.get('requestId'))
        url = p['url'] if p else ''
        if es_externa(url):
            clase = 'bloqueado' if not self.opciones.get('integracionReal') else 'externo'
        elif not mismo_origen(url, self.base):
            clase = 'externo'
        else:
            clase = 'esperado' if self.escenario['cache'] == 'offline' else 'producto'
        self.error({'tipo': 'red', 'url': url, 'texto': e.get('errorText', ''), 'clase': clase})
        if p is not None:
            p['fallo'] = e.get('errorText', '')

    def _al_error_js(self, excepcion) -> None:
        texto = str(excepcion)
        self.error({'tipo': 'js', 'texto': texto[:400], 'clase': clase_texto(texto)})

    def _al_consola(self, mensaje) -> None:
        try:
            if mensaje.type != 'error':
                return
            texto = mensaje.text or ''
        except Exception:
            return
        self.error({'tipo': 'consola', 'texto': texto[:400], 'clase': clase_texto(texto)})


def instalar_rutas(ctx, opciones: dict) -> None:
    """Intercepta el tráfico del contexto: bloquea las fuentes externas y retrasa /api/config si se pide."""
    retraso = 0 if os.environ.get('BRASA_BENCH_CONFIG_SERVER') == '1' else \
        (opciones.get('retrasoConfigMs') or 0)

    def manejador(ruta):
        url = ruta.request.url
        if not opciones.get('integracionReal') and es_externa(url):
            return ruta.abort()
        if retraso and urlparse(url).path == '/api/config':
            time.sleep(retraso / 1000)
        return ruta.continue_()

    # Enrutar todo desactiva la caché HTTP de Playwright y contamina el perfil caliente.
    if not opciones.get('integracionReal'):
        for host in ORIGENES_EXTERNOS:
            ctx.route(f'https://{host}/**', manejador)
    if retraso:
        ctx.route('**/api/config', manejador)


# Rutas con capas (mapa-capas): tras el contenido usable, la red de esos grupos debe quedar
# quieta (sin pedidos en vuelo) durante ~500 ms antes de cerrar la medición del paso, con
# tope dentro del timeout del paso. Los bytes de infraestructura y de la grilla de viento
# llegan después del primer render; sin esta espera se perderían del desglose.
RED_QUIETA_MS = 500
RED_QUIETA_ENCUESTA_MS = 100

# Encuadre esperado (mapa-capas-santiago): el contenido usable llega mientras el vuelo
# animado sigue en curso y las teselas de infraestructura solo se piden tras `moveend`.
# Sin esperar el encuadre, la ventana de red quieta podría cerrar los bytes antes del
# pedido real. La verificación consulta el mapa real de la página vía `getMap` de
# /web/js/map.js (la vista ya hace import() dinámico de módulos propios, así la CSP lo
# permite): zoom objetivo con tolerancia y mapa sin movimiento.
ENCUADRE_ENCUESTA_MS = 100
ENCUADRE_TOLERANCIA_ZOOM = 0.25


def pedidos_en_vuelo(pedidos: dict, base: str, grupos) -> list:
    """URLs de pedidos de `grupos` sin término (ni carga completa ni fallo de red)."""
    return [p.get('url', '') for p in pedidos.values()
            if grupo_de_url(p.get('url', ''), base) in grupos
            and not p.get('fin') and not p.get('fallo')]


def esperar_red_quieta(seguimiento, page, base: str, grupos, tope_ms: int,
                       ventana_ms: int = RED_QUIETA_MS) -> bool:
    """Espera a que ningún pedido de `grupos` esté en vuelo durante `ventana_ms` seguidos.

    Encuesta cada 100 ms con tope en `tope_ms` (el tiempo que queda del paso). El límite
    es estricto: la última encuesta se recorta a lo que quede del tope, así la espera
    nunca lo sobrepasa (antes dormía los 100 ms completos aunque el tope estuviera a
    pocos milisegundos de vencer). Si el tope vence sin confirmar la ventana, devuelve
    False: es un mejor esfuerzo, no un error propio ni del producto (los bytes que
    llegaron quedan en la muestra y la medición sigue).
    """
    if tope_ms <= 0:
        return False
    fin = time.monotonic() + tope_ms / 1000
    quieta_desde = None
    while True:
        ahora = time.monotonic()
        if pedidos_en_vuelo(seguimiento.pedidos, base, grupos):
            quieta_desde = None
        else:
            if quieta_desde is None:
                quieta_desde = ahora
            if ahora - quieta_desde >= ventana_ms / 1000:
                return True
        if ahora >= fin:
            return False
        try:
            page.wait_for_timeout(min(RED_QUIETA_ENCUESTA_MS, max(0, round((fin - ahora) * 1000))))
        except Exception:
            return False


def js_estado_encuadre() -> str:
    """JS evaluado en la página: importa el módulo real del mapa y reporta zoom y movimiento.

    /web/js/map.js ya está cargado por la propia vista del mapa: el import() dinámico
    devuelve esa misma instancia (la app usa import() dinámico de módulos propios, así que
    la CSP lo permite). getMap/getZoom/isMoving son la API pública de MapLibre expuesta
    por map.js; el veredicto (tolerancia de zoom) lo decide Python, una sola fuente.
    """
    return """async () => {
      try {
        const m = await import('/web/js/map.js');
        const map = typeof m.getMap === 'function' ? m.getMap() : null;
        if (!map) return { razon: 'sin-mapa' };
        return { zoom: map.getZoom(), moviendo: map.isMoving() };
      } catch (e) {
        return { razon: 'sin-modulo', error: String(e).slice(0, 120) };
      }
    }"""


def encuadre_listo(estado, encuadre: dict) -> bool:
    """True si el mapa llegó al encuadre declarado: zoom objetivo con tolerancia y sin movimiento."""
    zoom = (estado or {}).get('zoom')
    if zoom is None:
        return False
    return zoom >= encuadre['zoom'] - ENCUADRE_TOLERANCIA_ZOOM and not (estado or {}).get('moviendo')


def esperar_encuadre(page, encuadre: dict, tope_ms: int) -> bool:
    """Espera a que el mapa llegue al encuadre declarado (vuelo animado incluido), con tope estricto.

    El fly al encuadre es animado: el contenido usable llega antes de que termine y las
    teselas de infraestructura solo se piden tras `moveend`. La encuesta duerme lo que
    quede del tope (como esperar_red_quieta): la espera total nunca lo sobrepasa. Si el
    tope vence sin confirmar el encuadre, devuelve False: mejor esfuerzo que registra
    quien llama; los bytes que llegaron quedan en la muestra.
    """
    if tope_ms <= 0:
        return False
    fin = time.monotonic() + tope_ms / 1000
    while True:
        ahora = time.monotonic()
        try:
            estado = page.evaluate(js_estado_encuadre())
        except Exception:
            estado = None
        if encuadre_listo(estado, encuadre):
            return True
        if ahora >= fin:
            return False
        try:
            page.wait_for_timeout(min(ENCUADRE_ENCUESTA_MS, max(0, round((fin - ahora) * 1000))))
        except Exception:
            return False


def calmar_red_de_ruta(ruta: dict, seguimiento, page, base: str, estado_paso: str,
                       inicio_paso: float, opciones: dict, paso: str | None = None):
    """Aplica las esperas de la ruta tras un paso util: primero el encuadre, después la red quieta.

    El tope de cada espera es lo que queda del timeout del paso: ninguna lo excede. En
    fallos y timeouts no se espera (no hay contenido usable que seguir cargando). Devuelve
    None si la ruta no declara esperas o el paso no llegó a util, True si el encuadre y la
    red quedaron confirmados dentro del tope y False si alguno venció: ese False no se
    ignora. Con `paso` se registra como timeout explícito del medidor (tipo `encuadre` o
    `redQuieta`), la muestra queda incompleta (sus bytes pueden estar truncados) y el
    tiempo util del paso se conserva intacto: nada se descarta y nada se contamina.
    """
    grupos = ruta.get('redQuieta')
    encuadre = ruta.get('encuadre')
    if not (grupos or encuadre) or estado_paso != 'util':
        return None
    if encuadre is not None:
        tope = opciones['timeoutMs'] - int((time.monotonic() - inicio_paso) * 1000)
        if not esperar_encuadre(page, encuadre, tope):
            if paso is not None:
                seguimiento.error({'tipo': 'encuadre', 'paso': paso, 'clase': 'medidor',
                                   'texto': f"el mapa no llegó al encuadre esperado (zoom >= "
                                            f"{encuadre['zoom'] - ENCUADRE_TOLERANCIA_ZOOM} sin movimiento) "
                                            f"dentro del timeout del paso: los bytes del encuadre pueden estar truncados"})
            return False
    if grupos:
        tope = opciones['timeoutMs'] - int((time.monotonic() - inicio_paso) * 1000)
        if not esperar_red_quieta(seguimiento, page, base, grupos, tope):
            if paso is not None:
                seguimiento.error({'tipo': 'redQuieta', 'paso': paso, 'clase': 'medidor',
                                   'texto': f"la red de {', '.join(grupos)} no quedó quieta dentro del "
                                            f"timeout del paso: sus bytes pueden estar truncados"})
            return False
    return True


def metricas_cdp(client) -> dict:
    """Métricas CDP del hilo principal: TaskDuration, script/layout/recalcStyle y heap JS."""
    if client is None:
        return {}
    try:
        res = client.send('Performance.getMetrics')
    except Exception:
        return {}
    valores = {e.get('name'): e.get('value', 0) for e in res.get('metrics', [])}

    def ms(nombre):
        return round((valores.get(nombre) or 0) * 1000, 1)

    return {
        'taskDurationMs': ms('TaskDuration'), 'scriptMs': ms('ScriptDuration'),
        'layoutMs': ms('LayoutDuration'), 'recalcStyleMs': ms('RecalcStyleDuration'),
        'heapUsedBytes': int(valores.get('JSHeapUsedSize') or 0),
        'heapTotalBytes': int(valores.get('JSHeapTotalSize') or 0),
        'nodos': int(valores.get('Nodes') or 0),
    }


def delta_procesamiento(base: dict, fin: dict) -> dict:
    """Diferencia de métricas de CPU entre el inicio y el fin de la parte medida."""
    if not fin:
        return {}
    delta = {k: max(0.0, round(fin[k] - (base or {}).get(k, 0), 1))
             for k in ('taskDurationMs', 'scriptMs', 'layoutMs', 'recalcStyleMs') if k in fin}
    delta['heapUsedBytes'] = fin.get('heapUsedBytes')
    delta['heapTotalBytes'] = fin.get('heapTotalBytes')
    delta['nodos'] = fin.get('nodos')
    return delta


def lanzar_navegador():
    """Una sola instancia de Chromium para toda la corrida (y para comparar base vs candidata)."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(args=['--no-sandbox'])
    return pw, browser


def version_navegador(browser):
    try:
        return browser.version
    except Exception:
        return None


def version_playwright():
    try:
        from importlib.metadata import version

        return version('playwright')
    except Exception:
        return None


def esperar_ruta(page, timeout_ms: int) -> dict:
    """Espera a que la ruta llegue a un estado definitivo; el timeout también es un estado, no un descarte."""
    inicio = time.monotonic()
    fin = inicio + timeout_ms / 1000
    while True:
        try:
            leer = page.evaluate('() => window.__brasaPerf.leer()')
            if leer and (leer.get('ruta') or {}).get('estado') in ('util', 'fallo'):
                return leer
        except Exception:
            pass
        if time.monotonic() >= fin:
            return {'ruta': {'estado': 'timeout', 'ms': round((time.monotonic() - inicio) * 1000, 1),
                             'cls': None, 'inicio': None}, 'tareas': []}
        page.wait_for_timeout(100)


def ir_y_esperar(page, base: str, ruta: dict, opciones: dict) -> dict:
    """Navegación de documento (URL completa) y espera del contenido usable."""
    inicio = time.monotonic()
    try:
        page.goto(url_de_ruta(base, ruta['url']), wait_until='domcontentloaded', timeout=opciones['timeoutMs'])
    except Exception as exc:
        return {'ruta': {'estado': 'timeout', 'ms': round((time.monotonic() - inicio) * 1000, 1),
                         'cls': None, 'inicio': None}, 'tareas': [], 'errorNavegacion': type(exc).__name__}
    restante = max(1, opciones['timeoutMs'] - int((time.monotonic() - inicio) * 1000))
    return esperar_ruta(page, restante)


def reiniciar_ruta(page, criterio: dict) -> None:
    """Transición SPA: marca, CLS y criterio parten de cero; el FCP/LCP del documento queda aparte."""
    page.evaluate('c => window.__brasaPerf.reset(c)', criterio)


def ir_a_hash(page, hash_ruta: str) -> None:
    """Navegación SPA real: clic en el enlace si existe (barra o rail) y si no, cambio de hash directo."""
    enlace = page.locator(f'a[href="{hash_ruta}"]').first
    try:
        if enlace.count() > 0:
            enlace.click(timeout=2000)
            return
    except Exception:
        pass
    page.evaluate('h => { location.hash = h; }', hash_ruta)


def paso_de_leer(leer: dict) -> dict:
    """Paso medido: estado, tiempo hasta contenido usable, CLS de la transición y tareas largas propias."""
    r = leer.get('ruta') or {}
    tareas = leer.get('tareas') or []
    inicio = r.get('inicio')
    propias = []
    if r.get('estado') != 'timeout' and inicio is not None:
        propias = [t for t in tareas if (t.get('inicio') or -1) >= inicio - 1]
    return {
        'estado': r.get('estado') or 'timeout', 'ms': r.get('ms'), 'cls': r.get('cls'),
        'tareasLargasMs': round(sum(t['ms'] for t in propias), 1) if r.get('estado') != 'timeout' else None,
        'nTareasLargas': len(propias),
    }


def documento_de_leer(leer: dict) -> dict:
    return {
        'fcpMs': round(leer['fcp'], 1) if leer.get('fcp') is not None else None,
        'lcpMs': round(leer['lcp'], 1) if leer.get('lcp') is not None else None,
        'clsMs': leer.get('clsDoc'),
        'loadMs': (leer.get('doc') or {}).get('loadMs'), 'dclMs': (leer.get('doc') or {}).get('dclMs'),
    }


def registrar_estado_paso(seguimiento: Seguimiento, paso: str, estado: str, escenario: dict) -> None:
    """Un fallo explícito o un timeout también son parte de la muestra; sin señal, el fallo es esperado."""
    if estado == 'util':
        return
    clase = 'esperado' if (escenario['cache'] == 'offline' and estado == 'fallo') else 'producto'
    seguimiento.error({'tipo': 'estado' if estado == 'fallo' else 'timeout', 'paso': paso, 'clase': clase,
                       'texto': f"el paso {paso} terminó en estado {estado}"})


def preparar(ctx, page, base: str, ruta_id: str, opciones: dict, seguimiento=None) -> bool:
    """Calienta el service worker (y su caché) y la ruta: portada, SW listo y la propia ruta. No se mide.

    En rutas con `encuadre` espera primero el vuelo al encuadre (zoom objetivo con
    tolerancia, mapa sin movimiento) y en rutas con `redQuieta` espera después (con el
    seguimiento de la preparación) a que esa red quede quieta: sin eso, la caché caliente
    mediría sin los bytes de las capas que aún viajaban y, en offline, la capa de
    infraestructura fallaría al montar por no estar su índice ni sus teselas en la caché
    del SW (y al revertirse, la vista reescribe el hash del criterio). Una preparación que
    no confirma el encuadre o la red no se da por buena: se reporta.
    """
    ruta = RUTAS[ruta_id]
    try:
        page.goto(url_de_ruta(base, '/'), wait_until='domcontentloaded', timeout=opciones['timeoutMs'])
        page.wait_for_function(
            "() => !!(document.querySelector('#zona-b #add-place') || document.querySelector('.ember-hero'))",
            timeout=opciones['timeoutMs'])
        page.wait_for_function('() => navigator.serviceWorker.ready.then(() => true, () => false)',
                               timeout=opciones['timeoutMs'])
        page.wait_for_timeout(1500)
        page.goto(url_de_ruta(base, ruta['url']), wait_until='domcontentloaded', timeout=opciones['timeoutMs'])
        page.wait_for_function('([s, m]) => { const el = document.querySelector(s); return !!(el && (el.innerText || "").trim().length >= m); }',
                               arg=[ruta['listo'], ruta.get('minTexto') or 0], timeout=opciones['timeoutMs'])
        page.wait_for_timeout(800)
        # El encuadre primero, la red quieta después: las teselas de infraestructura solo
        # se piden tras moveend y sin esto la preparación cortaría antes de que existan.
        encuadre = ruta.get('encuadre')
        if encuadre and not esperar_encuadre(page, encuadre, opciones['timeoutMs']):
            return False
        grupos = ruta.get('redQuieta')
        if grupos and seguimiento is not None and \
                not esperar_red_quieta(seguimiento, page, base, grupos, opciones['timeoutMs']):
            return False
        return True
    except Exception:
        return False


def medir_interaccion(page, disp: dict):
    """Toque sintético sobre la pestaña activa → siguiente frame. Latencia sintética, no un INP real."""
    try:
        page.evaluate('() => window.__brasaPerf.armaInteraccion()')
        selector = '#tabbar .nav-link[aria-current="page"]' if disp['tactil'] else '#nav .nav-link[aria-current="page"]'
        enlace = page.locator(selector).first
        if enlace.count() == 0:
            return None
        if disp['tactil']:
            enlace.tap(timeout=3000)
        else:
            enlace.click(timeout=3000)
        page.wait_for_timeout(300)
        marca = page.evaluate('() => window.__brasaPerf.ultimaInteraccion')
        if marca and marca.get('t0') is not None and marca.get('t1') is not None:
            return round(marca['t1'] - marca['t0'], 1)
    except Exception:
        return None
    return None


def nueva_muestra(base: str, escenario: dict, ruta_id: str, numero: int) -> dict:
    return {
        'ruta': ruta_id, 'dispositivo': escenario['dispositivo'], 'red': escenario['red'],
        'cpu': escenario['cpu'], 'cache': escenario['cache'], 'numero': numero,
        'url': url_de_ruta(base, RUTAS[ruta_id]['url']),
        'generadoIso': ahora_iso(), 'pasos': {}, 'documento': {}, 'estado': 'fallo', 'completa': False,
        'errores': [], 'bytes': None, 'procesamiento': {}, 'interaccionRafMs': None, 'captura': None,
    }


def cabeceras_cliente_ci(base: str) -> dict:
    """Cada contexto representa una IP distinta solo en los servidores efímeros de CI."""
    url = urlparse(base)
    if os.environ.get('BRASA_BENCH_CLIENT_IPS') != '1' or url.scheme != 'http' or \
            url.hostname != '127.0.0.1' or url.port not in (8001, 8002):
        return {}
    numero = next(_CLIENTES_CI)
    if numero >= 65536:
        raise ValueError('demasiados clientes sintéticos en una corrida')
    return {'X-Forwarded-For': f'127.1.{numero // 256}.{numero % 256}'}


def medir_contexto(browser, base: str, escenario: dict, ruta_id: str, numero: int, opciones: dict, dir_capturas: Path) -> dict:
    """Una muestra: un contexto nuevo e independiente con todos los pasos de la ruta."""
    ruta = RUTAS[ruta_id]
    disp = DISPOSITIVOS[escenario['dispositivo']]
    seguimiento = Seguimiento(base, escenario, opciones)
    muestra = nueva_muestra(base, escenario, ruta_id, numero)
    cpu_base = {}
    ctx = browser.new_context(
        viewport={'width': disp['ancho'], 'height': disp['alto']}, has_touch=disp['tactil'],
        is_mobile=disp['esMovil'], device_scale_factor=disp['escala'], locale='es-CL',
        timezone_id='America/Santiago', service_workers='allow',
        extra_http_headers=cabeceras_cliente_ci(base))
    page = None
    try:
        instalar_rutas(ctx, opciones)
        page = ctx.new_page()
        page.add_init_script(RECOLECTOR_JS + criterios_documento_js())
        seguimiento.enganchar(ctx, page)
        if escenario['cache'] in ('caliente', 'offline'):
            # Preparación de caché (no medida): fría no prepara nada, caliente y offline sí.
            if not preparar(ctx, page, base, ruta_id, opciones, seguimiento):
                seguimiento.error({'tipo': 'preparacion', 'clase': 'producto',
                                   'texto': 'la preparación de caché no terminó dentro del timeout'})
                raise RuntimeError('preparación de caché fallida')
            if escenario['cache'] == 'offline':
                ctx.set_offline(True)
        seguimiento.reiniciar()
        cpu_base = metricas_cdp(seguimiento.client)

        # Paso directo: primer acceso a la URL (documento nuevo; en rutas profundas, de golpe).
        page.goto('about:blank')
        inicio_paso = time.monotonic()
        leer = ir_y_esperar(page, base, ruta, opciones)
        muestra['pasos']['directo'] = paso_de_leer(leer)
        registrar_estado_paso(seguimiento, 'directo', muestra['pasos']['directo']['estado'], escenario)
        muestra['documento'] = documento_de_leer(leer)
        calmar_red_de_ruta(ruta, seguimiento, page, base, muestra['pasos']['directo']['estado'],
                           inicio_paso, opciones, paso='directo')

        if ruta['tipo'] == 'spa':
            if ruta_id != 'mi-zona':
                # Paso desde portada: la portada es el documento nuevo, la ruta llega por SPA.
                page.goto('about:blank')
                leer_portada = ir_y_esperar(page, base, RUTAS['mi-zona'], opciones)
                if (leer_portada.get('ruta') or {}).get('estado') == 'util':
                    reiniciar_ruta(page, criterio_de(ruta_id))
                    inicio_paso = time.monotonic()
                    ir_a_hash(page, ruta['hash'])
                    leer = esperar_ruta(page, opciones['timeoutMs'])
                    muestra['pasos']['desdePortada'] = paso_de_leer(leer)
                    calmar_red_de_ruta(ruta, seguimiento, page, base,
                                       muestra['pasos']['desdePortada']['estado'], inicio_paso, opciones,
                                       paso='desdePortada')
                else:
                    muestra['pasos']['desdePortada'] = {'estado': 'timeout', 'ms': None, 'cls': None,
                                                        'tareasLargasMs': None, 'nTareasLargas': 0}
                    seguimiento.error({'tipo': 'portada', 'clase': 'producto',
                                       'texto': 'la portada no quedó usable: no se pudo medir la navegación SPA'})
                registrar_estado_paso(seguimiento, 'desdePortada', muestra['pasos']['desdePortada']['estado'], escenario)
            # Paso reingreso: navegación repetida (distractor y volver), con módulos y datos ya calientes.
            distractor = 'mas' if ruta_id == 'quehago' else 'quehago'
            reiniciar_ruta(page, criterio_de(distractor))
            ir_a_hash(page, RUTAS[distractor]['hash'])
            esperar_ruta(page, opciones['timeoutMs'])  # contexto: el distractor no se registra
            reiniciar_ruta(page, criterio_de(ruta_id))
            inicio_paso = time.monotonic()
            ir_a_hash(page, ruta['hash'])
            leer = esperar_ruta(page, opciones['timeoutMs'])
            muestra['pasos']['reingreso'] = paso_de_leer(leer)
            registrar_estado_paso(seguimiento, 'reingreso', muestra['pasos']['reingreso']['estado'], escenario)
            calmar_red_de_ruta(ruta, seguimiento, page, base, muestra['pasos']['reingreso']['estado'],
                               inicio_paso, opciones, paso='reingreso')
        else:
            # Páginas estáticas: el reingreso es una recarga del documento (caché HTTP/SW ya caliente).
            page.goto('about:blank')
            leer = ir_y_esperar(page, base, ruta, opciones)
            muestra['pasos']['reingreso'] = paso_de_leer(leer)
            registrar_estado_paso(seguimiento, 'reingreso', muestra['pasos']['reingreso']['estado'], escenario)

        # Captura comparable (mismo viewport y perfil) antes de la interacción sintética.
        nombre = f"{ruta_id}-{escenario['dispositivo']}-{escenario['red']}-cpu{escenario['cpu']}-{escenario['cache']}-{numero}.png"
        page.screenshot(path=str(dir_capturas / nombre))
        muestra['captura'] = nombre
        if ruta['tipo'] == 'spa':
            muestra['interaccionRafMs'] = medir_interaccion(page, disp)
    except Exception as err:
        # La preparación fallida ya quedó registrada como error del producto; el resto es falla del instrumento.
        if not any(e.get('tipo') == 'preparacion' for e in seguimiento.errores):
            seguimiento.error({'tipo': 'medidor', 'clase': 'medidor', 'texto': str(err)[:300]})
    finally:
        try:
            if page is not None and not page.is_closed() and not muestra.get('captura'):
                nombre = f"{ruta_id}-{escenario['dispositivo']}-{escenario['red']}-cpu{escenario['cpu']}-{escenario['cache']}-{numero}.png"
                page.screenshot(path=str(dir_capturas / nombre))
                muestra['captura'] = nombre
        except Exception:
            pass
        muestra['procesamiento'] = delta_procesamiento(cpu_base, metricas_cdp(seguimiento.client))
        muestra['bytes'] = resumen_red(seguimiento.pedidos, base)
        muestra['errores'] = list(seguimiento.errores)
        requeridos = {'directo', 'reingreso'}
        if ruta['tipo'] == 'spa' and ruta_id != 'mi-zona':
            requeridos.add('desdePortada')
        for faltante in requeridos - muestra['pasos'].keys():
            muestra['pasos'][faltante] = {'estado': 'timeout', 'ms': None, 'cls': None,
                                         'tareasLargasMs': None, 'nTareasLargas': 0}
        if muestra['pasos']:
            muestra['estado'] = estado_global(muestra['pasos'])
            muestra['completa'] = all(p['estado'] == 'util' for p in muestra['pasos'].values()) and \
                not any(e.get('clase') == 'medidor' for e in muestra['errores'])
        try:
            ctx.close()
        except Exception:
            pass
    return muestra


# ------------------------------------------------------------------ informes

def construir_metadatos(args, browser, comparacion: bool = False) -> dict:
    meta = {
        'generadoIso': ahora_iso(),
        'navegador': version_navegador(browser),
        'playwright': version_playwright(),
        'dispositivos': args.dispositivos, 'redes': args.redes, 'cpus': args.cpus, 'caches': args.caches,
        'rutas': args.rutas, 'muestras': args.muestras, 'timeoutS': args.timeout_s,
        'integracionReal': args.integracion_real, 'retrasoConfigMs': args.retraso_config_ms,
        'retrasoConfigServidor': os.environ.get('BRASA_BENCH_CONFIG_SERVER') == '1',
        'origenesExternos': list(ORIGENES_EXTERNOS), 'hashesDatos': args.hash_datos,
    }
    if comparacion:
        meta['base'] = args.base
        meta['candidata'] = args.candidata
        meta['revisionBase'] = args.revision_base
        meta['revisionCandidata'] = args.revision_candidata
        meta['advertenciaOrigen'] = aviso_mismo_origen(args.base, args.candidata)
    else:
        meta['base'] = args.base
        meta['revision'] = args.revision
    return meta


def aviso_mismo_origen(base: str, candidata: str):
    if mismo_origen(base, candidata):
        return 'Las URL comparten origen; verificar que identifican revisiones distintas. Cada muestra usa un contexto aislado.'
    return None


def linea_progreso(muestra: dict) -> str:
    pasos = []
    for nombre, p in muestra['pasos'].items():
        tiempo = '' if p['ms'] is None else f" {p['ms']} ms"
        pasos.append(f"{nombre} {p['estado']}{tiempo}")
    escena = f"{muestra['dispositivo']}/{muestra['red']}/cpu{muestra['cpu']}/{muestra['cache']}"
    return f"{muestra['ruta']} [{escena}] muestra {muestra['numero']}: {muestra['estado']} — " + ' · '.join(pasos)


def _par_ms(mediana, peor):
    return '—' if mediana is None else f"{mediana} ({peor}) ms"


def _par_b(mediana, peor):
    return '—' if mediana is None else f"{mediana} ({peor}) B"


def grupo_informa(g: dict) -> bool:
    """True si el grupo midió algo: una fila de puros ceros no aporta al informe (el JSON la conserva)."""
    return bool(g) and any(g.get(k) for k in ('nMediana', 'bytesRedMediana', 'bytesRedPeor',
                                              'bytesCacheMediana', 'duplicadosMediana'))


def informe_markdown(datos: dict) -> str:
    meta = datos.get('metadatos', {})
    lineas = [
        f"# Medición integral de rendimiento — {meta.get('base', '')}", '',
        f"Generada: {meta.get('generadoIso')} · Chromium {meta.get('navegador')} · Playwright {meta.get('playwright') or '—'}",
        f"Perfiles: dispositivos {', '.join(meta.get('dispositivos', []))} · redes {', '.join(meta.get('redes', []))} · "
        f"CPU ×{', ×'.join(str(c) for c in meta.get('cpus', []))} · caché {', '.join(meta.get('caches', []))} · "
        f"{meta.get('muestras')} muestras por escenario.",
        f"Revisión: {meta.get('revision') or '—'} · hashes de datos: {'; '.join(meta.get('hashesDatos') or []) or '—'}",
        f"Fuentes externas: {'permitidas (--integracion-real)' if meta.get('integracionReal') else 'bloqueadas (tiles.openfreemap.org, gibs.earthdata.nasa.gov)'}.",
        f"Retraso de /api/config: {meta.get('retrasoConfigMs') or 0} ms · timeout por paso: hasta {meta.get('timeoutS')} s (navegación + espera).", '',
        'La mediana y el peor se calculan solo con muestras completas; las incompletas se cuentan y no se descartan.',
        'Cobertura y límites: docs/RENDIMIENTO_INTEGRAL.md.', '',
        '| Escenario y ruta | Compl./incompl. | Directo | Desde portada | Reingreso | FCP | LCP | Bytes red | Errores prod./ext./bloq./esp. |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for clave, res in datos.get('resumen', {}).items():
        pasos = res['pasos']
        doc = res['documento']
        err = res['errores']
        lineas.append(
            f"| {clave} | {res['nCompletas']}/{res['nIncompletas']} | "
            f"{_par_ms(pasos['directo']['medianaMs'], pasos['directo']['peorMs'])} | "
            f"{_par_ms(pasos['desdePortada']['medianaMs'], pasos['desdePortada']['peorMs'])} | "
            f"{_par_ms(pasos['reingreso']['medianaMs'], pasos['reingreso']['peorMs'])} | "
            f"{_par_ms(doc['fcpMedianaMs'], doc['fcpPeorMs'])} | "
            f"{_par_ms(doc['lcpMedianaMs'], doc['lcpPeorMs'])} | "
            f"{res['bytes'].get('bytesRedMediana')} B | "
            f"{err.get('producto')}/{err.get('externo')}/{err.get('bloqueado')}/{err.get('esperado')} |")
    lineas += ['', '## Bytes por grupo de recurso', '',
               'Mediana (peor) de bytes por muestra, solo con muestras completas. `teselasMapa` son las '
               'fuentes externas del mapa: por defecto se bloquean, así que cuentan pedidos, sin bytes. '
               'Los grupos sin pedidos se omiten (el JSON los conserva en cero).', '',
               '| Escenario y ruta | Grupo | Pedidos | Red | Caché | Duplicados |',
               '|---|---|---|---|---|---|']
    for clave, res in datos.get('resumen', {}).items():
        for grupo in GRUPOS_RECURSOS:
            g = (res['bytes'].get('porGrupo') or {}).get(grupo)
            if not grupo_informa(g):
                continue
            lineas.append(
                f"| {clave} | {grupo} | {g.get('nMediana')} | "
                f"{_par_b(g.get('bytesRedMediana'), g.get('bytesRedPeor'))} | "
                f"{g.get('bytesCacheMediana')} B | {g.get('duplicadosMediana')} |")
    incompletas = [m for m in datos.get('muestras', []) if not m.get('completa')]
    lineas += ['', f"## Muestras incompletas ({len(incompletas)})", '']
    if not incompletas:
        lineas.append('Ninguna: todas las muestras llegaron a contenido usable.')
    for m in incompletas:
        errores = '; '.join(f"[{e.get('clase')}] {e.get('texto') or e.get('url')}" for e in m.get('errores', [])[:3])
        lineas.append(f"- {clave_de_muestra(m)} muestra {m['numero']}: estado {m['estado']} · {errores}")
    return '\n'.join(lineas) + '\n'


# ------------------------------------------------------------------ corredor de un despliegue

def opciones_de(args) -> dict:
    return {'timeoutMs': int(args.timeout_s * 1000), 'integracionReal': args.integracion_real,
            'retrasoConfigMs': args.retraso_config_ms}


def main(argv=None) -> int:
    args = parsear_args(sys.argv[1:] if argv is None else argv)
    opciones = opciones_de(args)
    out = Path(args.out)
    dir_capturas = out / 'capturas'
    dir_capturas.mkdir(parents=True, exist_ok=True)
    pw, browser = lanzar_navegador()
    datos = {'metadatos': construir_metadatos(args, browser), 'muestras': [], 'resumen': {}}
    try:
        for escenario in combinaciones(args.dispositivos, args.redes, args.cpus, args.caches, args.rutas):
            for numero in range(1, args.muestras + 1):
                muestra = medir_contexto(browser, args.base, escenario, escenario['ruta'], numero, opciones, dir_capturas)
                datos['muestras'].append(muestra)
                escribir_incremental(out / 'medicion.json', datos)
                agregar_jsonl(out / 'muestras.jsonl', muestra)
                print(linea_progreso(muestra), flush=True)
        datos['resumen'] = resumir_por_escenario(datos['muestras'])
        escribir_incremental(out / 'medicion.json', datos)
        (out / 'medicion.md').write_text(informe_markdown(datos), encoding='utf-8')
    finally:
        try:
            browser.close()
            pw.stop()
        except Exception:
            pass
    return codigo_salida_global(datos['resumen'])


if __name__ == '__main__':
    sys.exit(main())
