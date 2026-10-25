"""Revisión en un navegador real (Playwright + Chromium) del servidor local. Uso: python dev.py e2e

Recorre las vistas principales en 320, 390 y 1280 px, con lectura sencilla y detallada y con letra normal
y grande, y las páginas estáticas, incluida una pasada en modo impresión a 794 px (A4), y reporta:
- errores de JavaScript y violaciones de la política de seguridad de contenidos (CSP);
- textos cortados (desbordados con overflow oculto) o que salen de la pantalla;
- en impresión, elementos fijos visibles, documentos más anchos que la hoja y secciones sin alto o desbordadas;
- violaciones de accesibilidad axe-core (WCAG 2.2 AA) con impacto serious/critical.
Además mide el tiempo de carga de cada página (marca de navegación y LCP) e imprime una
tabla informativa con el detalle en <out>/tiempos.json: no influye en el código de salida.
Guarda capturas de cada vista en --out. Termina con código 1 si encuentra algún problema.

Regresión visual: con --baseline DIR compara las capturas contra una referencia (≤ 0,5 % de píxeles
distintos por defecto, ajustable con --tolerancia) y falla si algo se movió; con --update-baseline DIR
fija la referencia copiando las capturas nuevas.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops
from playwright.async_api import async_playwright

from tiempos_pagina import LCP_LENTO_MS, resumen as resumen_tiempos, tabla as tabla_tiempos

CLIPPED_JS = """() => {
  const out = []; const W = innerWidth;
  const sel = document.querySelector('#app') ? '#app *, #modal *' : 'body *';
  const inScroll = (el) => {
    for (let p = el; p; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (['auto','scroll'].includes(s.overflowX) && p.scrollWidth > p.clientWidth + 1) return true;
    }
    return false;
  };
  for (const el of document.querySelectorAll(sel)) {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const txt = (el.innerText || '').trim(); if (!txt || el.children.length > 3) continue;
    const r = el.getBoundingClientRect(); if (r.width < 4) continue;
    const clipped = el.scrollWidth > el.clientWidth + 1 && ['hidden','clip'].includes(cs.overflowX);
    const outside = r.right > W + 1 && !inScroll(el) && !el.closest('.maplibregl-control-container,.card-actions-scroll');
    if (clipped || outside) out.push({ tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 40), text: txt.slice(0, 50),
      why: clipped ? 'cortado' : 'fuera de pantalla' });
  }
  return out;
}"""

# Modo impresión: el documento no debe superar el ancho de la hoja, no debe haber fijos
# visibles y cada sección debe tener alto y quedar dentro del ancho (las ocultas se omiten:
# respuesta.html esconde sus secciones hasta que llegan los datos).
PRINT_CHECK_JS = """(W) => {
  const out = [];
  const docW = Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth || 0);
  if (docW > W + 1) out.push({ why: 'ancho del documento', tag: 'html', cls: '', text: `${docW} px > ${W} px` });
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    if (cs.position === 'fixed') out.push({ why: 'fijo visible', tag: el.tagName.toLowerCase(),
      cls: (el.getAttribute('class') || '').slice(0, 40), text: (el.innerText || el.tagName).trim().slice(0, 50) });
  }
  for (const s of document.querySelectorAll('section')) {
    const cs = getComputedStyle(s);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = s.getBoundingClientRect();
    const text = (s.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 50);
    const cls = (s.getAttribute('class') || '').slice(0, 40);
    if (r.height <= 0) out.push({ why: 'sección sin alto', tag: 'section', cls, text });
    else if (r.left < -1 || r.right > W + 1) out.push({ why: 'sección fuera del ancho', tag: 'section', cls, text });
  }
  return out;
}"""

BASE_ROUTES = [
    "mi-zona",
    "mapa",
    "riesgo",
    "riesgo?comuna=5801",
    "casos",
    "casos/penco-lirquen-2026",
    "preparate",
    "alertas",
    "privacidad",
    "calidad",
    "temporada",
]

# Páginas estáticas fuera de la SPA (se sirven bajo /web/): modo liviano, pantalla pública
# (con comuna fija para pintar datos), la hoja imprimible, los tiempos de respuesta y los
# datos abiertos. No leen las preferencias de lectura simple/experto ni de letra, así que
# se revisan una vez por ancho.
STATIC_PAGES = [
    "/web/lite.html",
    "/web/pantalla.html?comuna=5801",
    "/web/lista.html",
    "/web/respuesta.html",
    "/web/plan.html",
    "/web/datos.html",
]
# Segunda pasada: las hojas A4 en modo impresión. Se emula el ancho de una A4 a 96 dpi
# (794 px) para detectar lo que en pantalla queda oculto: fijos, desbordes y secciones partidas.
PRINT_PAGES = ["/web/lista.html", "/web/respuesta.html"]
A4_WIDTH_PX = 794
COMUNAS_INDEX = "/web/data/comunas-index.json"

# REND-01: el LCP solo se lee con un observador instalado antes de cargar la página;
# queda en window.__lcp (último candidato) para consultarlo tras el pintado.
PERF_HOOK_JS = """
window.__lcp = 0;
try {
  new PerformanceObserver((list) => {
    const e = list.getEntries();
    if (e.length) window.__lcp = e[e.length - 1].startTime;
  }).observe({ type: 'largest-contentful-paint', buffered: true });
} catch (e) { /* navegador sin LCP: queda en 0 y se informa como sin dato */ }
"""

# Marcas del documento recién cargado: respuesta, DOMContentLoaded, load y el LCP del hook.
TIMING_JS = """() => {
  const n = performance.getEntriesByType('navigation')[0] || {};
  const v = (x) => (Number.isFinite(x) && x > 0 ? Math.round(x) : null);
  return { ttfb: v(n.responseStart), dcl: v(n.domContentLoadedEventEnd), carga: v(n.loadEventEnd), lcp: v(window.__lcp) };
}"""

AXE = Path(__file__).with_name("axe.min.js")
# axe.run sobre cada vista ya cargada: solo WCAG 2.x A/AA (incluye 2.2) y solo violaciones serious/critical.
# El lienzo WebGL y los controles internos de MapLibre/Cesium son de terceros y no los controla BRASA:
# se excluyen #map/#globe para que la auditoría mida lo que este repo puede arreglar.
AXE_RUN_JS = """async () => {
  const r = await axe.run({ exclude: [['#map'], ['#globe']] }, {
    resultTypes: ['violations'],
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] }
  });
  const out = [];
  for (const v of r.violations) {
    if (v.impact !== 'serious' && v.impact !== 'critical') continue;
    for (const n of v.nodes) out.push({ rule: v.id, impact: v.impact, help: v.help, sel: (n.target || []).join(' ') });
  }
  return out;
}"""
# Excepciones justificadas, una por entrada: (id de regla, selector) → motivo. No es un cajón de sastre.
AXE_ALLOW: dict[tuple[str, str], str] = {}

# UX-40: tras navegar a otra vista, el foco debe quedar en el encabezado de la vista (o en
# #panel si no hay) y el nombre de la vista debe repetirse en una hoja propia de una región
# aria-live (fuera de #view, que ya pinta el título por sí mismo).
# El destino es una vista fuera de BASE_ROUTES para que el hash siempre cambie de verdad.
FOCUS_NAV_VIEW = "quehago"
FOCUS_NAV_LABEL = "¿Qué hago si…?"
FOCUS_CHECK_JS = """(label) => {
  const active = document.activeElement;
  const heading = document.querySelector('#view h1, #view .view-title');
  const panel = document.getElementById('panel');
  const where = !active || active === document.body ? 'body' : active.id ? '#' + active.id
    : active.tagName.toLowerCase() + (active.className ? '.' + String(active.className).split(' ')[0] : '');
  const liveOk = [...document.querySelectorAll('[aria-live], [role="status"]')]
    .flatMap((r) => [r, ...r.querySelectorAll('*')])
    .some((el) => !el.closest('#view') && el.children.length === 0 && (el.textContent || '').includes(label));
  return { focusOk: active === heading || active === panel, where, liveOk };
}"""

# PORTADA-02: con la app funcionando la portada de emergencia #arranque-fallido debe
# seguir oculta. El vigilante inline la muestra a los 15/30 s si la app no pintó; como el
# recorrido de rutas dura más que eso, al final del contexto el chequeo ya corrió.
ARRANQUE_OCULTO_JS = """() => {
  const d = document.getElementById('arranque-fallido');
  if (!d) return 'ausente';
  return (d.hidden || getComputedStyle(d).display === 'none') ? 'oculto' : 'visible';
}"""

# Recorrido por teclado del mapa (a11y del lienzo): dónde quedó el foco tras cada Tab.
# 'ctrl' es un control de MapLibre (zoom, brújula, geolocalización, atribución) y 'capas'
# el <details> del control de capas (su <summary> o una de sus casillas).
MAP_KBD_TARGET_JS = """() => {
  const a = document.activeElement;
  if (!a) return '';
  if (a.closest('#map-layers')) return 'capas';
  if (a.closest('.maplibregl-ctrl')) return 'ctrl';
  if (a.closest('#map')) return 'mapa';
  return '';
}"""


async def check_mapa_teclado(page, url: str, where: str, problems: dict) -> None:
    """El lienzo se anuncia solo como «región»: al menos su texto y sus controles deben
    servir sin mirar. Comprueba que #map-summary describe el mapa tras cargar, que Tab
    alcanza los controles de MapLibre y el <details> de capas, y que cada casilla de capa
    se conmuta con Espacio."""
    await page.goto(f"{url}/#/mapa")
    await page.wait_for_timeout(2500)
    if not (await page.evaluate("() => (document.getElementById('map-summary')?.textContent || '').trim()")):
        problems.setdefault("«#map-summary» quedó sin texto tras cargar el mapa", set()).add(where)
    alcanzado = set()
    for _ in range(80):
        hit = await page.evaluate(MAP_KBD_TARGET_JS)
        if hit:
            alcanzado.add(hit)
        if {"ctrl", "capas"} <= alcanzado:
            break
        await page.keyboard.press("Tab")
    for falta in sorted({"ctrl", "capas"} - alcanzado):
        que = "los controles de MapLibre" if falta == "ctrl" else "el control «Capas»"
        problems.setdefault(f"Tab no alcanza {que} en el mapa", set()).add(where)
    # Con el foco en el <summary>, Espacio/Enter abre el <details> y Tab lleva a cada casilla.
    await page.evaluate("() => document.querySelector('#map-layers > summary')?.focus()")
    await page.keyboard.press("Space")
    if not await page.evaluate("() => Boolean(document.getElementById('map-layers')?.open)"):
        await page.keyboard.press("Enter")
    if not await page.evaluate("() => Boolean(document.getElementById('map-layers')?.open)"):
        problems.setdefault("el control «Capas» no se abre desde el teclado", set()).add(where)
        return
    boxes = await page.evaluate("() => document.querySelectorAll('#map-layers [data-capa]').length")
    vistas: set[str] = set()
    # Un campo de texto dentro del panel (buscador de comunas) recibe foco antes que las
    # casillas: es correcto, así que se acepta como parada intermedia y no como fallo.
    for _ in range(boxes + 10):
        if len(vistas) == boxes:
            break
        await page.keyboard.press("Tab")
        estado = await page.evaluate(
            """() => {
              const a = document.activeElement;
              if (!a || !a.closest('#map-layers')) return null;
              return a.dataset.capa || '';
            }"""
        )
        if estado is None:
            problems.setdefault("Tab sale del control «Capas» antes de recorrer las casillas", set()).add(where)
            break
        if not estado or estado in vistas:
            continue
        vistas.add(estado)
        antes = await page.evaluate("() => document.activeElement.checked")
        await page.keyboard.press("Space")
        despues = await page.evaluate("() => document.activeElement.checked")
        if antes == despues:
            problems.setdefault(f"Espacio no conmuta la casilla de la capa «{estado}»", set()).add(where)
        # «Aire» y «rayos» deshabilitan la casilla mientras cargan y el foco se pierde:
        # se espera a que vuelva y se recupera, para que el siguiente Tab no la salte.
        for _ in range(100):
            listo = await page.evaluate(
                """(capa) => {
                  const el = document.querySelector(`#map-layers [data-capa="${capa}"]`);
                  return Boolean(el && !el.disabled);
                }""",
                estado,
            )
            if listo:
                break
            await page.wait_for_timeout(50)
        await page.evaluate(
            """(capa) => document.querySelector(`#map-layers [data-capa="${capa}"]`)?.focus()""",
            estado,
        )
    if len(vistas) < boxes:
        problems.setdefault("Tab no llega a todas las casillas del control «Capas»", set()).add(where)


# QA-211: cada capa del control, al encenderse, debe dibujar en el lienzo, nombrarse en el
# resumen accesible y dejar leyenda propia. Antes solo se miraba que la casilla cambiara, así
# que una capa con el source vacío o el id mal escrito pasaba en verde con el mapa en blanco.
UMBRAL_CAPA = 0.00001  # 0,001 % del lienzo (unos 7 px a 1280 px): con capas de puntos basta

# Palabras con que el resumen (#map-summary) y la leyenda (#map-legend) deben nombrar cada
# capa: el sustantivo de su etiqueta en el control, sin artículos. Una capa nueva tiene que
# registrarse aquí; si no, el run falla y obliga a decidirlo.
CAPA_NOMBRE = {
    "focos": ("focos",),
    "incendios": ("incendio",),
    "risk": ("peligro",),
    "aire": ("humo",),
    "rain": ("lluvia",),
    "scars": ("cicatriz", "cicatrices"),  # el resumen dice «cicatrices» y la leyenda «cicatriz»
    "reports": ("aviso",),
    "places": ("lugar",),
    "hulls": ("huella",),
    "lightning": ("rayo",),
    "viento": ("viento",),
    "senapred": ("senapred",),
    "relieve": ("relieve",),
}

# Capas sin datos a la vista en la demo, con el motivo escrito al lado: no se les puede exigir
# que el lienzo cambie. La lista no crece sin justificar; una capa nueva sin datos lo dice aquí.
CAPAS_SIN_DATOS = {
    "aire": "el humo de la demo cae fuera del encuadre del mapa",
    "rain": "la demo no trae la anomalía de lluvia (/api/risk: rain vacío)",
    "reports": "la demo no tiene avisos de vecinos (/api/reports vacío)",
    "places": "la prueba no guarda lugares",
    "viento": "las partículas van en un canvas superpuesto (`viento.js`): el lienzo MapLibre no cambia",
    "senapred": "la demo no siembra alertas de SENAPRED (/api/senapred/alertas vacío)",
    "lightning": "la demo no siembra rayos: la capa lee GLM en vivo de S3 y puede no haber destellos sobre Chile en la ventana",
}

# Capas cuya leyenda todavía no las nombra: excepción con motivo, no un cajón de sastre.
CAPAS_SIN_LEYENDA = {
    "places": "web/js/map.js no tiene entrada de leyenda para «Mis lugares» (MAPA-130); el resumen sí la nombra",
}


async def _resumen_y_leyenda(page) -> tuple[str, str]:
    """Texto actual de #map-summary y #map-legend, en minúsculas (se lee textContent, no la
    visibilidad: en móvil la leyenda se esconde y el chequeo corre a 1280 px)."""
    resumen = (await page.evaluate("() => document.getElementById('map-summary')?.textContent || ''")).lower()
    leyenda = (await page.evaluate("() => document.getElementById('map-legend')?.textContent || ''")).lower()
    return resumen, leyenda


async def check_mapa_capas(page, url: str, where: str, problems: dict, out: Path) -> None:
    """Enciende cada capa del control y exige que el mapa cambie de píxeles, que #map-summary
    la nombre y que #map-legend no quede vacía y la nombre. Se llega con `capas=` vacío para
    partir de un mapa sin capas encendidas; cada vuelta apaga la suya antes de la siguiente."""
    await page.goto(f"{url}/#/mapa?capas=")
    await page.wait_for_timeout(2500)
    capas = await page.evaluate("() => [...document.querySelectorAll('#map-layers [data-capa]')].map((i) => i.dataset.capa)")
    if not capas:
        problems.setdefault("el control «Capas» no tiene casillas con data-capa", set()).add(where)
        return
    await page.evaluate("() => { const d = document.getElementById('map-layers'); if (d) d.open = true; }")
    # La leyenda y el control flotan sobre el lienzo y cambian con cada capa: se ocultan
    # (visibility, sin mover nada) para que la captura mida solo lo que pinta el mapa.
    await page.evaluate(
        "() => { for (const s of ['#map-legend', '#map-layers']) {"
        " const el = document.querySelector(s); if (el) el.style.visibility = 'hidden'; } }"
    )
    for capa in capas:
        etiqueta = await page.evaluate(
            "(k) => (document.querySelector(`#map-layers [data-capa=\"${k}\"]`)?.closest('.switch-row')"
            "?.querySelector('b')?.textContent || k).trim()",
            capa,
        )
        palabra = CAPA_NOMBRE.get(capa)
        if not palabra:
            problems.setdefault(f"la capa «{etiqueta}» no tiene palabra registrada en CAPA_NOMBRE", set()).add(where)
            continue
        ref = out / f"mapa-capa-{capa}-antes.png"
        nueva = out / f"mapa-capa-{capa}-despues.png"
        mirar_lienzo = capa not in CAPAS_SIN_DATOS
        if mirar_lienzo:
            await page.locator("#map canvas.maplibregl-canvas").screenshot(path=str(ref))
        await page.evaluate('(k) => document.querySelector(`#map-layers [data-capa="${k}"]`).click()', capa)
        # El mapa se aquieta solo: se reintenta hasta 3 s y basta con que la captura cambie.
        cambio = False
        if mirar_lienzo:
            for _ in range(10):
                await page.wait_for_timeout(300)
                await page.locator("#map canvas.maplibregl-canvas").screenshot(path=str(nueva))
                pct, size_changed, _ = compare_shots(ref, nueva)
                if size_changed or pct > UMBRAL_CAPA:
                    cambio = True
                    break
        resumen, leyenda = await _resumen_y_leyenda(page)
        # Algunas capas cargan sus datos al encenderse (humo, lluvia, rayos): se espera a que
        # el resumen y la leyenda las nombren. Tope de 9 s: con el runner cargado (WebGL y
        # capturas) 3 s no alcanzaba y el chequeo fallaba sin que la capa estuviera rota.
        for _ in range(30):
            if any(w in resumen for w in palabra) and (capa in CAPAS_SIN_LEYENDA or any(w in leyenda for w in palabra)):
                break
            await page.wait_for_timeout(300)
            resumen, leyenda = await _resumen_y_leyenda(page)
        if mirar_lienzo and not cambio:
            problems.setdefault(f"la capa «{etiqueta}» se enciende pero el mapa no cambia", set()).add(where)
        if not any(w in resumen for w in palabra):
            problems.setdefault(f"el resumen no nombra la capa «{etiqueta}»", set()).add(where)
        if capa not in CAPAS_SIN_LEYENDA:
            if not leyenda.strip():
                problems.setdefault(f"la leyenda quedó vacía con la capa «{etiqueta}» encendida", set()).add(where)
            elif not any(w in leyenda for w in palabra):
                problems.setdefault(f"la leyenda no nombra la capa «{etiqueta}»", set()).add(where)
        # Deja el mapa como estaba antes de la vuelta siguiente.
        if await page.evaluate('(k) => document.querySelector(`#map-layers [data-capa="${k}"]`).checked', capa):
            await page.evaluate('(k) => document.querySelector(`#map-layers [data-capa="${k}"]`).click()', capa)
            await page.wait_for_timeout(400)


async def check_pin_preciso(browser, url: str, where: str, problems: dict) -> None:
    """MAPA-161: marcar un lugar con el pin fijo debe dejarlo donde el vecino lo puso.

    Crea un suscriptor sin lugares (como emergency_sheet_check.py), abre «Agregar mi
    casa» → «Marcarlo en el mapa», exige «Confirmar» apagado a zoom 5, salta a zoom 13
    sobre el punto de prueba y guarda: la API debe devolver el lugar a menos de 100 m.
    El lugar se borra al final, falle o no la prueba.
    """

    def req(path: str, token: str | None = None, body: dict | None = None, method: str | None = None) -> dict:
        r = urllib.request.Request(
            f"{url}{path}", method=method or ("POST" if body is not None else "GET"),
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **({"X-Brasa-Token": token} if token else {})},
        )
        return json.load(urllib.request.urlopen(r, timeout=15))

    try:
        token = req("/api/subscribers", body={})["token"]
    except Exception as exc:
        problems.setdefault(f"no se pudo crear el suscriptor de prueba ({str(exc)[:80]})", set()).add(where)
        return
    place_id = None
    ctx = await browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
    try:
        await ctx.add_init_script(f"localStorage.setItem('brasa:token', JSON.stringify('{token}'))")
        page = await ctx.new_page()
        await page.goto(f"{url}/#/mi-zona")
        await page.get_by_role("button", name="Agregar mi casa").click(timeout=20000)
        await page.locator("#pf-map").click(timeout=10000)
        await page.locator("#pick-hint:not([hidden])").wait_for(timeout=10000)
        # A zoom de país marcar es impreciso: «Confirmar» debe seguir apagado y avisar.
        await page.evaluate("async () => { const { getMap } = await import('/web/js/map.js'); getMap().jumpTo({ zoom: 5 }); }")
        await page.wait_for_timeout(400)
        if not await page.evaluate("() => Boolean(document.getElementById('pick-ok')?.disabled)"):
            problems.setdefault("«Confirmar» está habilitado a zoom 5", set()).add(where)
        if await page.evaluate("() => Boolean(document.getElementById('pick-zoom')?.hidden)"):
            problems.setdefault("el aviso «Acércate más para marcar con precisión» no aparece a zoom 5", set()).add(where)
        # El objetivo bajo el pin: salto directo al punto de prueba junto a Quilpué.
        await page.evaluate(
            "async () => { const { getMap } = await import('/web/js/map.js'); getMap().jumpTo({ center: [-71.405, -33.075], zoom: 13 }); }"
        )
        await page.wait_for_timeout(400)
        if await page.evaluate("() => Boolean(document.getElementById('pick-ok')?.disabled)"):
            problems.setdefault("«Confirmar» sigue deshabilitado a zoom 13", set()).add(where)
            return
        await page.locator("#pick-ok").click()
        await page.locator("#place-form button[type=submit]").click(timeout=10000)
        saved = None
        for _ in range(40):
            rows = req("/api/places", token=token).get("places", [])
            if rows:
                saved = rows[0]
                break
            await page.wait_for_timeout(250)
        if not saved:
            problems.setdefault("el lugar no quedó guardado tras Confirmar y Guardar", set()).add(where)
            return
        place_id = saved["id"]
        lat1, lon1 = math.radians(-33.075), math.radians(-71.405)
        lat2, lon2 = math.radians(saved["lat"]), math.radians(saved["lon"])
        h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        dist_m = 2 * 6371000 * math.asin(math.sqrt(h))
        if dist_m >= 100:
            problems.setdefault(f"el lugar quedó a {dist_m:.0f} m del punto marcado (máx. 100 m)", set()).add(where)
        else:
            print(f"  ✓ pin preciso: lugar guardado a {dist_m:.1f} m del punto marcado")
    except Exception as exc:
        problems.setdefault(str(exc)[:160], set()).add(where)
    finally:
        if place_id is not None:
            try:
                req(f"/api/places/{place_id}", token=token, method="DELETE")
            except Exception:
                pass
        await ctx.close()
# Toque y ficha en el celular (MAPA-157..162): el foco más al sureste de la demo
# (lejos del incendio CONAF a pocos metros del primero) y el CONAF de la demo.
DEMO_FOCO = [-71.381, -33.112]  # lon, lat: -33.06 - 13*0.004, -71.42 + 13*0.003
DEMO_CONAF = [-71.41, -33.07]

# Acerca el mapa al punto y lo proyecta a coordenadas de pantalla; informa si el
# puntero del contexto es «coarse» (el margen de toque cambia: 12 vs 4 px).
PUNTO_MAPA_JS = """async (lonlat) => {
  const { getMap } = await import('/web/js/map.js');
  const map = getMap();
  if (!map) return null;
  map.jumpTo({ center: lonlat, zoom: 10 });
  await Promise.race([new Promise((r) => map.once('idle', r)), new Promise((r) => setTimeout(r, 4000))]);
  const p = map.project(lonlat);
  const r2 = map.getCanvas().getBoundingClientRect();
  return { x: r2.left + p.x, y: r2.top + p.y, coarse: matchMedia('(pointer: coarse)').matches };
}"""


async def check_toque_movil(page, url: str, where: str, problems: dict) -> None:
    """MAPA-157: un toque junto a un foco abre su ficha (margen de dedo de 12 px),
    y con «Peligro» encendido el mismo toque sigue abriendo el foco y no la
    comuna que hay debajo — un solo toque, un solo resultado."""
    await page.goto(f"{url}/#/mapa")
    await page.wait_for_timeout(2500)
    pos = await page.evaluate(PUNTO_MAPA_JS, DEMO_FOCO)
    if not pos:
        problems.setdefault("el mapa no estaba listo para proyectar el foco", set()).add(where)
        return
    margen = 8 if pos["coarse"] else 0
    await page.mouse.click(pos["x"] + margen, pos["y"])
    try:
        await page.wait_for_selector("#ficha.abierta", timeout=8000)
    except Exception:
        problems.setdefault("un toque junto a un foco no abrió su ficha", set()).add(where)
        return
    texto = await page.evaluate("() => document.querySelector('#ficha')?.innerText || ''")
    if "Punto de calor" not in texto:
        problems.setdefault("el toque junto a un foco abrió otra cosa, no su ficha", set()).add(where)
    # «Peligro» pinta la comuna bajo el dedo: el foco debe seguir ganando el toque.
    await page.evaluate(
        "() => { const d = document.getElementById('map-layers'); if (d) d.open = true;"
        " document.querySelector('#map-layers [data-capa=\"risk\"]')?.click(); }"
    )
    for _ in range(40):  # la comunal (1,9 MB) tarda en bajar; sin ella el toque no la alcanza
        lista = await page.evaluate(
            """async () => {
              const { getMap } = await import('/web/js/map.js');
              const m = getMap();
              return Boolean(m?.getLayer('risk-fill')
                && m.getLayoutProperty('risk-fill', 'visibility') === 'visible'
                && m.isSourceLoaded('comunas'));
            }"""
        )
        if lista:
            break
        await page.wait_for_timeout(300)
    pos = await page.evaluate(PUNTO_MAPA_JS, DEMO_FOCO)
    await page.mouse.click(pos["x"] + margen, pos["y"])
    await page.wait_for_timeout(800)
    texto = await page.evaluate("() => document.querySelector('#ficha')?.innerText || ''")
    if "Punto de calor" not in texto:
        problems.setdefault("con «Peligro» encendido el toque abrió la comuna, no el foco", set()).add(where)
    # MAPA-159: con puntero «coarse» el mapa no monta +/− y «Mi ubicación» mide 44 px.
    if pos["coarse"]:
        ctl = await page.evaluate("""async () => {
          const { getMap } = await import('/web/js/map.js');
          const m = getMap();
          return { zoom: Boolean(document.querySelector('.maplibregl-ctrl-zoom-in')),
                   geolocate: Math.round(document.querySelector('.maplibregl-ctrl-geolocate')?.getBoundingClientRect().width || 0),
                   rota: Boolean(m?.touchZoomRotate?.rotationEnabled?.()),
                   pitch: Boolean(m?.touchPitch?.isEnabled?.()) };
        }""")
        if ctl["zoom"]:
            problems.setdefault("con puntero «coarse» no debería montarse el control +/−", set()).add(where)
        if ctl["geolocate"] != 44:
            problems.setdefault("«Mi ubicación» no mide 44 px con puntero «coarse»", set()).add(where)
        if ctl["rota"] or ctl["pitch"]:
            problems.setdefault("con puntero «coarse» la rotación o la inclinación táctil sigue activa", set()).add(where)


# Como PUNTO_MAPA_JS pero deja el punto en una franja baja de la pantalla (`y_obj`
# en píxeles de lienzo): si la ficha acoplada lo cubre, el mapa tiene que subirlo.
PUNTO_BAJO_JS = """async ([lonlat, yObj]) => {
  const { getMap } = await import('/web/js/map.js');
  const map = getMap();
  if (!map) return null;
  map.jumpTo({ center: lonlat, zoom: 10 });
  await Promise.race([new Promise((r) => map.once('idle', r)), new Promise((r) => setTimeout(r, 4000))]);
  const r2 = map.getCanvas().getBoundingClientRect();
  const objetivo = Math.min(yObj, r2.height - 240);
  const p = map.project(lonlat);
  if (Math.abs(p.y - objetivo) > 24) {
    map.panBy([0, p.y - objetivo], { duration: 0 });
    await new Promise((r) => setTimeout(r, 300));
  }
  const q = map.project(lonlat);
  return { x: r2.left + q.x, y: r2.top + q.y };
}"""


async def check_ficha_movil(page, url: str, where: str, problems: dict) -> None:
    """MAPA-158: a 390 px la ficha se acopla abajo — entera en la ventana, sobre la
    barra y sin que la hoja la tape; un foco que quedó detrás sube al área visible.
    Esc la cierra y la hoja vuelve al estado que tenía («half» en la segunda vuelta)."""
    await page.goto(f"{url}/#/mapa")
    await page.wait_for_timeout(2500)
    # El chequeo de toque deja la ficha y el panel de capas abiertos en la misma
    # página: partir con todo cerrado y la hoja en «peek». Un punto a ~540 px
    # queda bajo la ficha.
    await page.evaluate("""async () => {
      const { cerrarPopup } = await import('/web/js/popup.js');
      cerrarPopup();
      const capas = document.getElementById('map-layers');
      if (capas) capas.open = false;
      document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'peek' }));
    }""")
    await page.wait_for_timeout(500)
    pos = await page.evaluate(PUNTO_BAJO_JS, [DEMO_FOCO, 540])
    if not pos:
        problems.setdefault("el mapa no estaba listo para proyectar el foco", set()).add(where)
        return
    await page.mouse.click(pos["x"], pos["y"])
    try:
        await page.wait_for_selector("#ficha.abierta", timeout=8000)
    except Exception:
        problems.setdefault("un toque a un foco no abrió #ficha", set()).add(where)
        return
    await page.wait_for_timeout(700)  # medición del alto + el easeTo que sube el punto
    geo = await page.evaluate("""async () => {
      const el = document.getElementById('ficha');
      const ficha = el.getBoundingClientRect();
      const tabbar = document.querySelector('.tabbar').getBoundingClientRect();
      const { getMap } = await import('/web/js/map.js');
      const p = getMap().project([-71.381, -33.112]);
      const enMedio = document.elementFromPoint(ficha.left + ficha.width / 2, ficha.top + Math.min(60, ficha.height / 2));
      return { top: ficha.top, bottom: ficha.bottom, left: ficha.left, right: ficha.right,
               tabTop: tabbar.top, puntoY: p.y, role: el.getAttribute('role'), titulo: el.querySelector('#ficha-titulo')?.textContent || '',
               tapada: !(enMedio && enMedio.closest('#ficha')), W: innerWidth, H: innerHeight };
    }""")
    if geo["bottom"] > geo["tabTop"] + 1 or geo["left"] < -1 or geo["right"] > geo["W"] + 1 or geo["top"] < -1:
        problems.setdefault("#ficha no quedó entera dentro de la ventana, sobre la barra", set()).add(where)
    if geo["tapada"]:
        problems.setdefault("la hoja (#panel) tapa a #ficha", set()).add(where)
    if geo["role"] != "dialog" or not geo["titulo"]:
        problems.setdefault("#ficha no se anuncia como diálogo con título", set()).add(where)
    if geo["puntoY"] >= geo["top"]:
        problems.setdefault("el foco quedó detrás de la ficha, bajo su borde superior", set()).add(where)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(400)
    if await page.evaluate("() => Boolean(document.querySelector('#ficha.abierta'))"):
        problems.setdefault("Esc no cierra la ficha", set()).add(where)
    # Segunda vuelta: con la hoja en «half», al cerrar la ficha la hoja vuelve a «half».
    await page.evaluate("() => document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'half' }))")
    await page.wait_for_timeout(500)
    # Con la hoja en «half» la atribución ocupa ~290-330 px: 360 es banda libre.
    pos = await page.evaluate(PUNTO_BAJO_JS, [DEMO_FOCO, 360])
    if pos:
        await page.mouse.click(pos["x"], pos["y"])
        try:
            await page.wait_for_selector("#ficha.abierta", timeout=8000)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)
            sheet_h = await page.evaluate("() => parseFloat(document.documentElement.style.getPropertyValue('--sheet-h'))")
            esperado = 0.5 * (geo["H"] - 64)
            if not sheet_h or abs(sheet_h - esperado) > 30:
                problems.setdefault("tras cerrar la ficha la hoja no volvió a «half»", set()).add(where)
        except Exception:
            problems.setdefault("la segunda apertura de #ficha falló", set()).add(where)


async def check_ficha_escritorio(page, url: str, where: str, problems: dict) -> None:
    """MAPA-158: a 1280 px el detalle sigue siendo el popup de MapLibre (sin #ficha)."""
    await page.goto(f"{url}/#/mapa")
    await page.wait_for_timeout(2500)
    pos = await page.evaluate(PUNTO_MAPA_JS, DEMO_FOCO)
    if not pos:
        problems.setdefault("el mapa no estaba listo para proyectar el foco", set()).add(where)
        return
    await page.mouse.click(pos["x"], pos["y"])
    try:
        await page.wait_for_selector(".maplibregl-popup", timeout=8000)
    except Exception:
        problems.setdefault("un clic a un foco no abrió el popup de MapLibre", set()).add(where)
        return
    if await page.evaluate("() => Boolean(document.querySelector('#ficha.abierta'))"):
        problems.setdefault("a 1280 px se abrió #ficha en vez del popup de MapLibre", set()).add(where)
    texto = await page.evaluate("() => document.querySelector('.maplibregl-popup')?.innerText || ''")
    if "Punto de calor" not in texto:
        problems.setdefault("el clic a un foco abrió otra cosa, no su ficha", set()).add(where)


async def check_incendios_etiqueta(page, url: str, where: str, problems: dict) -> None:
    """MAPA-163: con «Focos de calor» (sin prender «Huellas») el contorno del incidente
    demo se dibuja ya a zoom 9, y desde zoom 8 el incidente de Quilpué y el incendio
    CONAF de la demo llevan etiqueta en el lienzo."""
    await page.goto(f"{url}/#/mapa?lat=-33.07&lon=-71.41&z=9")
    await page.wait_for_timeout(2500)
    info = None
    for _ in range(40):  # los incidentes y el CONAF se piden al montar: esperar a que pinten
        info = await page.evaluate("""async () => {
          const { getMap } = await import('/web/js/map.js');
          const m = getMap();
          if (!m) return null;
          const r = (id) => (m.getLayer(id) ? m.queryRenderedFeatures({ layers: [id] }) : null);
          return { inc: r('incident-labels')?.map((f) => f.properties.label),
                   conaf: r('official-labels')?.map((f) => f.properties.label),
                   hullsVis: m.getLayer('incident-hulls-line') ? m.getLayoutProperty('incident-hulls-line', 'visibility') : null,
                   hulls: r('incident-hulls-line')?.length ?? null };
        }""")
        if info and info["inc"] and info["conaf"] and (info["hulls"] or 0) > 0:
            break
        await page.wait_for_timeout(300)
    if not info:
        problems.setdefault("el mapa no estaba listo para leer las etiquetas de incendios", set()).add(where)
        return
    if not info["inc"] or not any("Quilpué" in (t or "") for t in info["inc"]):
        problems.setdefault("sin etiqueta del incidente de Quilpué en el mapa a zoom 9", set()).add(where)
    if not info["conaf"] or not any("CONAF" in (t or "") for t in info["conaf"]):
        problems.setdefault("sin etiqueta «CONAF: «nombre»» en el mapa a zoom 9", set()).add(where)
    if info["hullsVis"] != "visible" or not info["hulls"]:
        problems.setdefault("el contorno del incidente no se dibuja a zoom 9 con «Focos de calor»", set()).add(where)


async def check_leyenda_mi_zona(page, url: str, where: str, problems: dict) -> None:
    """MAPA-160: en «Mi zona» del celular aparece el chip «Leyenda» y al tocarlo
    se ve la nota esencial («calor no siempre es incendio»)."""
    await page.goto(f"{url}/#/mi-zona")
    await page.wait_for_timeout(2500)
    try:
        await page.wait_for_selector("#legend-chip", state="visible", timeout=10000)
    except Exception:
        problems.setdefault("el chip «Leyenda» no apareció en «Mi zona» del celular", set()).add(where)
        return
    await page.click("#legend-chip")
    nota = await page.evaluate("""() => {
      const el = document.querySelector('#map-legend .legend-note.esencial');
      if (!el) return { ok: false, txt: '' };
      const r = el.getBoundingClientRect();
      const visible = r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none';
      return { ok: visible, txt: el.textContent };
    }""")
    if not nota["ok"]:
        problems.setdefault("la nota esencial de la leyenda no se ve en «Mi zona» del celular", set()).add(where)
    elif "incendio" not in nota["txt"]:
        problems.setdefault("la nota esencial no dice que el calor no siempre es incendio", set()).add(where)


async def check_lista_mapa(page, url: str, where: str, problems: dict) -> None:
    """MAPA-162 (vista Mapa): con la hoja desplegada, elegir el incendio CONAF de la
    lista baja la hoja a «peek», vuela al punto y abre su ficha — el punto proyectado
    queda sobre el borde superior de la hoja."""
    await page.goto(f"{url}/#/mapa")
    await page.wait_for_timeout(2500)
    try:
        await page.wait_for_selector("[data-official]", timeout=10000)
    except Exception:
        problems.setdefault("la lista «Incendios que informa CONAF» no apareció", set()).add(where)
        return
    await page.evaluate("() => document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'full' }))")
    await page.wait_for_timeout(500)
    await page.click("[data-official]")
    await page.wait_for_timeout(3000)  # el flyTo hasta el incendio + la apertura de la ficha
    geo = await page.evaluate("""async () => {
      const { getMap } = await import('/web/js/map.js');
      const m = getMap();
      const p = m.project([-71.41, -33.07]);
      const panel = document.getElementById('panel').getBoundingClientRect();
      return { puntoY: p.y, panelTop: panel.top,
               ficha: Boolean(document.querySelector('#ficha.abierta')),
               fichaTxt: document.querySelector('#ficha .ficha-body')?.innerText || '',
               sheetH: parseFloat(document.documentElement.style.getPropertyValue('--sheet-h')) };
    }""")
    esperado = 0.24 * (844 - 64)  # «peek»
    if abs((geo["sheetH"] or 0) - esperado) > 30:
        problems.setdefault("elegir un incendio de la lista no bajó la hoja a «peek»", set()).add(where)
    if not geo["ficha"] or "CONAF" not in geo["fichaTxt"]:
        problems.setdefault("elegir un incendio de la lista no abrió su ficha", set()).add(where)
    if geo["puntoY"] >= geo["panelTop"]:
        problems.setdefault("el punto del incendio quedó detrás de la hoja al volar", set()).add(where)


async def check_barra_movil(page, url: str, where: str, problems: dict) -> None:
    """UX-80: a 390 px la barra inferior tiene 5 pestañas y la última es «Más»;
    al entrar a una sección agrupada «Más» queda marcada, y la vista lista las
    secciones que salieron de la barra."""
    await page.goto(f"{url}/#/mi-zona")
    await page.wait_for_timeout(1500)
    tabs = await page.evaluate(
        "() => [...document.querySelectorAll('#tabbar .nav-link')]"
        ".map((a) => ({ href: a.getAttribute('href') || '', txt: (a.innerText || '').trim() }))"
    )
    if len(tabs) != 5:
        problems.setdefault(f"la barra inferior tiene {len(tabs)} pestañas, no 5", set()).add(where)
        return
    if tabs[4]["href"] != "#/mas" or "Más" not in tabs[4]["txt"]:
        problems.setdefault("la quinta pestaña de la barra no es «Más» (#/mas)", set()).add(where)
    # Una sección agrupada debe marcar «Más» como la pestaña activa.
    await page.evaluate("() => { location.hash = '#/casos'; }")
    await page.wait_for_timeout(1200)
    marcada = await page.evaluate(
        "() => document.querySelector('#tabbar .nav-link[data-view=\"mas\"]')?.getAttribute('aria-current') === 'page'"
    )
    if not marcada:
        problems.setdefault("en «Historia» la pestaña «Más» no quedó marcada como activa", set()).add(where)
    await page.evaluate("() => { location.hash = '#/mas'; }")
    await page.wait_for_timeout(1200)
    texto = await page.evaluate("() => document.getElementById('view')?.innerText || ''")
    for nombre in ("Prepárate", "Historia", "Temporada", "¿Qué hago si", "Calidad de los datos", "Ajustes", "Privacidad"):
        if nombre not in texto:
            problems.setdefault(f"la vista «Más» no lista «{nombre}»", set()).add(where)


async def check_riel_escritorio(page, url: str, where: str, problems: dict) -> None:
    """UX-80: a 1280 px el riel lateral conserva las 7 secciones de siempre."""
    await page.goto(f"{url}/#/mi-zona")
    await page.wait_for_timeout(1200)
    tabs = await page.evaluate("() => document.querySelectorAll('#nav .nav-link').length")
    if tabs != 7:
        problems.setdefault(f"el riel de escritorio tiene {tabs} enlaces, no 7", set()).add(where)


async def check_volver_incendio(page, url: str, incident: str | None, where: str, problems: dict) -> None:
    """UX-81: desde «Mi zona» la ficha ofrece «← Volver» a donde estabas; entrando
    por enlace directo (recarga en la ficha, sin vista anterior) dice «← Mapa»."""
    if not incident:
        return

    async def enlace_volver() -> dict:
        return await page.evaluate(
            "() => { const a = document.getElementById('in-back');"
            " return { txt: (a?.innerText || '').trim(), href: a?.getAttribute('href') || '' }; }"
        )

    await page.goto(f"{url}/#/mi-zona")
    await page.wait_for_timeout(1500)
    await page.evaluate(f"() => {{ location.hash = '#/incendio/{incident}'; }}")
    try:
        await page.wait_for_selector("#in-back", timeout=15000)
    except Exception:
        problems.setdefault("la ficha del incidente no cargó para probar «← Volver»", set()).add(where)
        return
    back = await enlace_volver()
    if back["txt"] != "← Volver" or back["href"] != "#/mi-zona":
        problems.setdefault(
            f"desde «Mi zona» el enlace dice «{back['txt']}» a {back['href']}, no «← Volver» a #/mi-zona", set()
        ).add(where)
    # Enlace directo: recargar en la ficha la deja sin vista anterior.
    await page.reload()
    try:
        await page.wait_for_selector("#in-back", timeout=15000)
    except Exception:
        problems.setdefault("la ficha del incidente no recargó para probar «← Mapa»", set()).add(where)
        return
    back = await enlace_volver()
    if back["txt"] != "← Mapa" or back["href"] != "#/mapa":
        problems.setdefault(
            f"por enlace directo el enlace dice «{back['txt']}» a {back['href']}, no «← Mapa» a #/mapa", set()
        ).add(where)
def demo_foco_id(url: str) -> str | None:
    """El punto de calor de la demo más cercano al origen del incidente de Quilpué
    (-33.06, -71.42): el que usa el enlace compartido de la prueba MAPA-165."""
    try:
        with urllib.request.urlopen(f"{url}/api/observations?hours=336", timeout=10) as r:
            pts = json.load(r)["points"]
        pts.sort(key=lambda p: (p["lat"] + 33.06) ** 2 + (p["lon"] + 71.42) ** 2)
        return pts[0]["id"] if pts else None
    except Exception:
        return None


async def check_compartir_enlace(page, url: str, where: str, problems: dict, foco_id: str | None) -> None:
    """MAPA-165: abrir «#/mapa?…&foco=<id>» muestra la ficha del punto con su botón
    «Compartir»; sin menú nativo, el modal ofrece WhatsApp y «Copiar enlace»."""
    if not foco_id:
        print("  (sin foco en la demo: se omite la prueba del enlace compartido)")
        return
    # Los chequeos anteriores corren sobre esta misma página: partir sin ficha ni panel.
    await page.evaluate("""async () => {
      const { cerrarPopup } = await import('/web/js/popup.js');
      cerrarPopup();
      const capas = document.getElementById('map-layers');
      if (capas) capas.open = false;
      document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'peek' }));
    }""")
    await page.goto(f"{url}/#/mapa?lat=-33.06&lon=-71.42&z=12&foco={foco_id}")
    await page.wait_for_timeout(2500)
    try:
        await page.wait_for_selector("#ficha.abierta", timeout=8000)
    except Exception:
        problems.setdefault("el enlace foco=<id> no abrió la ficha del punto", set()).add(where)
        return
    texto = await page.evaluate("() => document.querySelector('#ficha')?.innerText || ''")
    if "Punto de calor" not in texto:
        problems.setdefault("el enlace foco=<id> abrió otra ficha, no la del punto", set()).add(where)
    share = await page.evaluate(
        "() => ({ btn: Boolean(document.querySelector('#ficha #pp-share')), nativo: Boolean(navigator.share) })"
    )
    if not share["btn"]:
        problems.setdefault("la ficha del punto no tiene «Compartir»", set()).add(where)
        return
    if share["nativo"]:
        return  # con menú nativo no hay modal que comprobar
    await page.click("#ficha #pp-share")
    await page.wait_for_timeout(500)
    if not await page.evaluate("() => Boolean(document.querySelector('#modal')?.open)"):
        problems.setdefault("«Compartir» sin menú nativo no abrió el modal del enlace", set()).add(where)
        return
    modal = await page.evaluate(
        """() => ({ wa: Boolean(document.querySelector('#modal a[href^="https://wa.me/"]')),
                   copiar: (document.querySelector('#modal #share-copy')?.textContent || '').includes('Copiar enlace'),
                   url: document.querySelector('#modal #share-url')?.value || '' })"""
    )
    if not modal["wa"] or not modal["copiar"]:
        problems.setdefault("el modal de compartir no ofrece WhatsApp y «Copiar enlace»", set()).add(where)
    if f"foco={foco_id}" not in modal["url"]:
        problems.setdefault("el enlace del modal no conserva foco=<id>", set()).add(where)


def first_incident(url: str) -> str | None:
    try:
        with urllib.request.urlopen(f"{url}/api/incidents?hours=336", timeout=10) as r:
            items = json.load(r)["incidents"]
        return items[0]["id"] if items else None
    except Exception:
        return None


def shared_link(url: str) -> str | None:
    """Un lugar compartido en el servidor local, para que el recorrido cubra la vista familiar (UX-47).

    Lo crea por la API (un suscriptor, un lugar junto al incidente demo y su enlace); queda en la
    base de demostración, que es desechable. Si el servidor no responde, la vista se omite.
    """
    try:

        def post(path: str, body: dict | None = None, headers: dict | None = None) -> dict:
            req = urllib.request.Request(
                f"{url}{path}", method="POST", headers=headers or {}, data=json.dumps(body).encode() if body is not None else b""
            )
            if body is not None:
                req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.load(r)

        token = post("/api/subscribers")["token"]
        headers = {"X-Brasa-Token": token}
        pid = post("/api/places", {"name": "Casa (DEMO)", "lat": -33.075, "lon": -71.405, "radius_km": 10}, headers)["id"]
        return post(f"/api/places/{pid}/share", headers=headers)["token"]
    except Exception:
        return None


def missing_comunas_index(url: str) -> str | None:
    """Motivo si /web/data/comunas-index.json no se sirve; respuesta.html lo usa para el filtro."""
    try:
        with urllib.request.urlopen(f"{url}{COMUNAS_INDEX}", timeout=10) as r:
            return None if r.status < 400 else f"HTTP {r.status}"
    except Exception as exc:
        return str(exc)[:80]


async def page_text(page) -> str:
    return await page.evaluate("() => (document.body?.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 80)")


async def open_static(
    page,
    url: str,
    path: str,
    where: str,
    data_problem: str | None,
    load_problems: dict[str, set[str]],
    mediciones: list[dict] | None = None,
) -> bool:
    """Abre una página estática. Si no responde o falta comunas-index.json, lo anota y sigue.
    Con `mediciones` guarda además las marcas de tiempo de la carga (REND-01)."""
    try:
        response = await page.goto(f"{url}{path}")
        await page.wait_for_timeout(1800)
    except Exception as exc:
        load_problems.setdefault(f"no cargó {path}: {str(exc)[:80]}", set()).add(where)
        return False
    if mediciones is not None:
        timing = await page.evaluate(TIMING_JS)
        timing.update({"pagina": path, "contexto": where})
        mediciones.append(timing)
    text = await page_text(page)
    if response is None or response.status >= 400:
        status = response.status if response else "sin respuesta"
        load_problems.setdefault(f"{path} respondió {status}: «{text}»", set()).add(where)
    if path == "/web/respuesta.html" and data_problem:
        load_problems.setdefault(f"{path}: falló {COMUNAS_INDEX} ({data_problem}): «{text}»", set()).add(where)
    return True


def compare_shots(ref: Path, new: Path) -> tuple[float, bool, Image.Image]:
    """Compara dos capturas. Devuelve (% de píxeles distintos, cambió el tamaño, imagen diff).

    Un píxel cuenta como distinto si algún canal difiere en más de 16. El diff deja la captura
    nueva con los píxeles distintos marcados en magenta; si el tamaño cambió, ambas se montan en
    un lienzo del tamaño mayor para que la zona sin solape también quede marcada.
    """
    a = Image.open(ref).convert("RGB")
    b = Image.open(new).convert("RGB")
    size_changed = a.size != b.size
    if size_changed:
        w, h = max(a.width, b.width), max(a.height, b.height)
        ca, cb = Image.new("RGB", (w, h)), Image.new("RGB", (w, h))
        ca.paste(a)
        cb.paste(b)
        a, b = ca, cb
    diff = ImageChops.difference(a, b)
    r, g, bl = diff.split()
    mask = ImageChops.lighter(ImageChops.lighter(r, g), bl).point(lambda v: 255 if v > 16 else 0)
    pct = mask.histogram()[255] / (a.width * a.height)
    marked = Image.composite(Image.new("RGB", b.size, (255, 0, 255)), b, mask)
    return (1.0 if size_changed else pct), size_changed, marked


async def main(url: str, out: Path, baseline: Path | None, update_baseline: Path | None, tolerancia: float) -> int:
    out.mkdir(parents=True, exist_ok=True)
    routes = list(BASE_ROUTES)
    incident = first_incident(url)
    routes.append(f"incendio/{incident}") if incident else print(
        "  (sin incidentes: corre `python dev.py run --demo` para revisar la ficha)"
    )
    link = shared_link(url)
    routes.append(f"v/{link}") if link else print("  (sin enlace familiar: no se pudo crear el lugar compartido en el servidor)")
    problems: dict[tuple, set] = {}
    axe_problems: dict[tuple, set] = {}
    focus_problems: dict[str, set] = {}
    map_problems: dict[str, set] = {}
    capa_problems: dict[str, set] = {}
    pin_problems: dict[str, set] = {}
    toque_problems: dict[str, set] = {}
    nav_problems: dict[str, set] = {}
    load_problems: dict[str, set[str]] = {}
    data_problem = missing_comunas_index(url)
    errors: list[str] = []
    shots: list[str] = []
    mediciones: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.getenv("BRASA_CHROMIUM") or None)
        for width in (320, 390, 1280):
            for detail, text in (("simple", "normal"), ("experto", "grande")):
                # reduced_motion: las animaciones de entrada (.enter → rise, opacity 0→1) dejarían a axe
                # midiendo contraste a mitad de una transición: resultado no determinista.
                ctx = await browser.new_context(
                    viewport={"width": width, "height": 800 if width < 1000 else 900}, service_workers="block", reduced_motion="reduce"
                )
                await ctx.add_init_script(
                    f"localStorage.setItem('brasa:text', JSON.stringify('{text}'));"
                    f"localStorage.setItem('brasa:detail', JSON.stringify('{detail}'))"
                )
                await ctx.add_init_script(PERF_HOOK_JS)
                # axe en cada página del contexto. add_init_script corre por CDP, exento de CSP: un
                # add_script_tag inline sería rechazado por script-src 'self' y contaría como error CSP.
                await ctx.add_init_script(path=AXE)
                page = await ctx.new_page()
                page.on("pageerror", lambda e: errors.append(f"JS: {str(e)[:200]}"))
                page.on(
                    "console",
                    lambda m: (
                        errors.append(f"CSP: {m.text[:200]}")
                        if any(k in m.text for k in ("Content Security Policy", "Refused to"))
                        else None
                    ),
                )
                for route in routes:
                    await page.goto(f"{url}/#/{route}")
                    await page.wait_for_timeout(1800)
                    timing = await page.evaluate(TIMING_JS)
                    timing.update({"pagina": route, "contexto": f"{route} @{width} {detail}/{text}"})
                    mediciones.append(timing)
                    for item in await page.evaluate(CLIPPED_JS):
                        problems.setdefault((item["why"], item["tag"], item["cls"], item["text"]), set()).add(
                            f"{route} @{width} {detail}/{text}"
                        )
                    for v in await page.evaluate(AXE_RUN_JS):
                        if (v["rule"], v["sel"]) in AXE_ALLOW:
                            continue
                        axe_problems.setdefault((v["rule"], v["impact"], v["sel"], v["help"]), set()).add(
                            f"{route} @{width} {detail}/{text}"
                        )
                    if detail == "simple":
                        name = route.replace("/", "_").replace("?", "_").replace("=", "-")
                        shots.append(f"{name}-{width}.png")
                        await page.screenshot(path=str(out / f"{name}-{width}.png"))
                # PORTADA-02: tras el recorrido (los chequeos de 15/30 s ya corrieron) la
                # portada de emergencia debe seguir oculta si la app arrancó de verdad.
                estado_arranque = await page.evaluate(ARRANQUE_OCULTO_JS)
                if estado_arranque != "oculto":
                    load_problems.setdefault(f"#arranque-fallido quedó {estado_arranque} con la app funcionando", set()).add(
                        f"app @{width} {detail}/{text}"
                    )
                # UX-40: una navegación real dentro de la SPA — el foco debe quedar en el
                # contenido nuevo y el nombre de la vista en una región aria-live.
                await page.evaluate("(v) => { location.hash = '#/' + v; }", FOCUS_NAV_VIEW)
                await page.wait_for_timeout(1500)
                chk = await page.evaluate(FOCUS_CHECK_JS, FOCUS_NAV_LABEL)
                where_nav = f"{FOCUS_NAV_VIEW} @{width} {detail}/{text}"
                if not chk["focusOk"]:
                    focus_problems.setdefault(
                        f"tras navegar a «{FOCUS_NAV_LABEL}» el foco quedó en {chk['where']}: se esperaba el encabezado de la vista o #panel",
                        set(),
                    ).add(where_nav)
                if not chk["liveOk"]:
                    focus_problems.setdefault(
                        f"tras navegar a «{FOCUS_NAV_LABEL}» el nombre de la vista no quedó en ninguna región aria-live",
                        set(),
                    ).add(where_nav)
                if detail == "simple":
                    for path in STATIC_PAGES:
                        where = f"{path} @{width}"
                        if not await open_static(page, url, path, where, data_problem, load_problems, mediciones):
                            continue
                        for item in await page.evaluate(CLIPPED_JS):
                            problems.setdefault((item["why"], item["tag"], item["cls"], item["text"]), set()).add(where)
                        for v in await page.evaluate(AXE_RUN_JS):
                            if (v["rule"], v["sel"]) in AXE_ALLOW:
                                continue
                            axe_problems.setdefault((v["rule"], v["impact"], v["sel"], v["help"]), set()).add(where)
                        name = path.lstrip("/").replace("/", "_").replace("?", "_").replace("=", "-")
                        shots.append(f"{name}-{width}.png")
                        await page.screenshot(path=str(out / f"{name}-{width}.png"))
                    # a11y del lienzo: una pasada por teclado sobre el mapa por cada ancho.
                    # Va al final del contexto: conmutar capas cambia el estado del mapa.
                    await check_mapa_teclado(page, url, f"mapa @{width}", map_problems)
                    # MAPA-161: el pin fijo contra la API, una pasada en contexto propio a 390 px.
                    if width == 390:
                        await check_pin_preciso(browser, url, f"pin preciso @{width}", pin_problems)
                    # QA-211: las capas se comprueban una sola vez, a 1280 px (en móvil la
                    # leyenda se esconde y el lienzo es demasiado chico para ver el cambio).
                    if width == 1280:
                        await check_mapa_capas(page, url, f"mapa @{width}", capa_problems, out)
                await ctx.close()
        # Pasada de impresión: hojas A4 a 794 px (96 dpi). Se emula print desde la carga
        # para medir el layout que sale en papel, no el de pantalla.
        ctx = await browser.new_context(viewport={"width": A4_WIDTH_PX, "height": 1123}, service_workers="block", reduced_motion="reduce")
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"JS: {str(e)[:200]}"))
        page.on(
            "console",
            lambda m: (
                errors.append(f"CSP: {m.text[:200]}") if any(k in m.text for k in ("Content Security Policy", "Refused to")) else None
            ),
        )
        await page.emulate_media(media="print")
        for path in PRINT_PAGES:
            where = f"{path} @{A4_WIDTH_PX} impresión"
            if not await open_static(page, url, path, where, data_problem, load_problems):
                continue
            for item in await page.evaluate(PRINT_CHECK_JS, A4_WIDTH_PX):
                problems.setdefault((item["why"], item["tag"], item["cls"], item["text"]), set()).add(where)
        await ctx.close()
        # Toque, ficha móvil, leyenda de Mi zona y lista→mapa (MAPA-157/158/160/162):
        # un contexto táctil de 390 px emula el dedo; la ficha de escritorio va a 1280 px.
        ctx_tactil = await browser.new_context(
            viewport={"width": 390, "height": 844}, has_touch=True, service_workers="block", reduced_motion="reduce"
        )
        page = await ctx_tactil.new_page()
        page.on("pageerror", lambda e: errors.append(f"JS: {str(e)[:200]}"))
        await check_toque_movil(page, url, "toque @390 táctil", toque_problems)
        await check_ficha_movil(page, url, "ficha @390 táctil", toque_problems)
        await check_leyenda_mi_zona(page, url, "leyenda @390 táctil", toque_problems)
        await check_lista_mapa(page, url, "lista @390 táctil", toque_problems)
        await check_barra_movil(page, url, "barra @390 táctil", nav_problems)
        await check_volver_incendio(page, url, incident, "volver @390 táctil", nav_problems)
        await check_compartir_enlace(page, url, "compartir @390 táctil", toque_problems, demo_foco_id(url))
        await ctx_tactil.close()
        ctx_escritorio = await browser.new_context(
            viewport={"width": 1280, "height": 900}, service_workers="block", reduced_motion="reduce"
        )
        page = await ctx_escritorio.new_page()
        page.on("pageerror", lambda e: errors.append(f"JS: {str(e)[:200]}"))
        await check_ficha_escritorio(page, url, "ficha @1280", toque_problems)
        await check_riel_escritorio(page, url, "riel @1280", nav_problems)
        await check_incendios_etiqueta(page, url, "etiquetas @1280", toque_problems)
        await ctx_escritorio.close()
        await browser.close()
    for e in sorted(set(errors)):
        print("  ✗", e)
    for (why, tag, cls, txt), where in sorted(problems.items(), key=lambda kv: -len(kv[1])):
        print(f"  ✗ texto {why}: {tag}.{cls} «{txt}» ({len(where)}×, ej.: {sorted(where)[0]})")
    for (rule, impact, sel, help_), where in sorted(axe_problems.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        print(f"  ✗ a11y {impact} [{rule}]: {sel} — {help_} ({len(where)}×, ej.: {sorted(where)[0]})")
    for msg, where in sorted(focus_problems.items()):
        print(f"  ✗ navegación: {msg} ({len(where)}×, ej.: {sorted(where)[0]})")
    for msg, where in sorted(map_problems.items()):
        print(f"  ✗ teclado mapa: {msg} ({len(where)}×, ej.: {sorted(where)[0]})")
    for msg, where in sorted(capa_problems.items()):
        print(f"  ✗ capas del mapa: {msg} ({len(where)}×, ej.: {sorted(where)[0]})")
    for msg, where in sorted(pin_problems.items()):
        print(f"  ✗ pin preciso: {msg} ({len(where)}×, ej.: {sorted(where)[0]})")
    for msg, where in sorted(toque_problems.items()):
        print(f"  ✗ toque y ficha: {msg} ({len(where)}×, ej.: {sorted(where)[0]})")
    for msg, where in sorted(nav_problems.items()):
        print(f"  ✗ barra y «Más»: {msg} ({len(where)}×, ej.: {sorted(where)[0]})")
    for capa, motivo in CAPAS_SIN_DATOS.items():
        print(f"  · capa sin datos en la demo: {capa} ({motivo})")
    for capa, motivo in CAPAS_SIN_LEYENDA.items():
        print(f"  · capa sin leyenda propia: {capa} ({motivo})")
    for msg, where in sorted(load_problems.items()):
        print(f"  ✗ carga: {msg} ({len(where)}×, ej.: {sorted(where)[0]})")
    visual_fails = 0
    if update_baseline:
        update_baseline.mkdir(parents=True, exist_ok=True)
        for f in shots:
            shutil.copy2(out / f, update_baseline / f)
        print(f"  referencia visual actualizada: {len(shots)} capturas en {update_baseline}")
    elif baseline:
        compared = 0
        for f in shots:
            ref = baseline / f
            if not ref.exists():
                continue
            compared += 1
            pct, size_changed, marked = compare_shots(ref, out / f)
            fails = size_changed or pct > tolerancia
            diff_path = out / f"{f[:-4]}.diff.png"
            if fails:
                visual_fails += 1
                marked.save(diff_path)
            else:
                diff_path.unlink(missing_ok=True)
            note = " · tamaño distinto" if size_changed else ""
            print(f"  {'✗' if fails else '✓'} {f}: {pct:.2%} píxeles distintos{note}")
        if not compared:
            print(f"  ! referencia vacía o inexistente: {baseline}")
        print(
            f"  {compared} captura(s) comparadas · tolerancia {tolerancia:.2%}" + (f" · diffs en {out}/*.diff.png" if visual_fails else "")
        )
    else:
        print("  sin referencia visual (usa --baseline o --update-baseline)")
    # REND-01: tabla informativa de tiempos de carga — nunca suma al total de problemas.
    if mediciones:
        filas_tiempo = resumen_tiempos(mediciones)
        (out / "tiempos.json").write_text(
            json.dumps({"lcp_lento_ms": LCP_LENTO_MS, "resumen": filas_tiempo, "mediciones": mediciones}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Tiempos de carga por página · mediana en ms (informativo; «lenta» = LCP > {LCP_LENTO_MS / 1000:g} s):")
        print(tabla_tiempos(filas_tiempo))
        print(f"  detalle por pasada en {out / 'tiempos.json'}")
    total = (
        len(set(errors))
        + len(problems)
        + len(axe_problems)
        + len(focus_problems)
        + len(map_problems)
        + len(capa_problems)
        + len(pin_problems)
        + len(toque_problems)
        + len(nav_problems)
        + len(load_problems)
    )
    estaticas = ", ".join(STATIC_PAGES)
    impresion = ", ".join(PRINT_PAGES)
    print(
        f"{'Sin problemas' if not total else f'{total} problema(s)'} · {len(routes)} vistas SPA × 3 anchos × 2 modos"
        f" + {len(STATIC_PAGES)} estáticas × 3 anchos ({estaticas})"
        f" + {len(PRINT_PAGES)} impresión @{A4_WIDTH_PX} px ({impresion}) · capturas en {out}"
    )
    return 1 if total or visual_fails else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default="data/shots")
    parser.add_argument("--baseline", type=Path, help="directorio con la referencia visual a comparar")
    parser.add_argument("--update-baseline", type=Path, metavar="DIR", help="copia las capturas a DIR como nueva referencia y no compara")
    parser.add_argument("--tolerancia", type=float, default=0.005, help="fracción máxima de píxeles distintos permitida (defecto 0,5 %%)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url.rstrip("/"), Path(args.out), args.baseline, args.update_baseline, args.tolerancia)))
