"""Auditoría de accesibilidad de BRASA en navegador real (A11Y-02).

Playwright + Chromium. Por vista y por porte (390×844 táctil y 1280×800):

- nombre accesible de cada control, campos con etiqueta, imágenes con alt;
- encabezados: <h1> expuestos en el árbol (sin doble conteo) y saltos de nivel;
- landmarks (main/nav/banner), ids duplicados, lang, <title> y regiones vivas;
- contraste WCAG del texto visible contra su fondo efectivo (AA: 4,5:1, o 3:1
  en texto grande), en tema claro y oscuro y en nivel sencillo y técnico;
- teclado: 40 Tab sin trampa ni foco invisible; el modal (<dialog>) atrapa el
  foco, cierra con Escape y lo devuelve al control que lo abrió;
- prefers-reduced-motion: ninguna animación ni transición dura más de 0,2 s;
- zoom de texto al 200 % (solo 390 px): sin scroll lateral ni texto cortado.

El nombre accesible se calcula como el árbol de accesibilidad: cuenta el texto
recortado por clip (.sr-only, expuesto al árbol) y descarta display:none,
visibility:hidden y aria-hidden. Cada control marcado «sin nombre» se confirma
además contra el árbol real con aria_snapshot: si el árbol le da nombre pasa a
«falsosPositivos» en vez de corregirse a ciegas (los chips con dual() tienen un
span por nivel y uno siempre está oculto por CSS).

Uso: python scripts/local/auditar_a11y.py <BASE> <salida.json>
"""
from __future__ import annotations

import json
import re
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip('/')
OUT = sys.argv[2]

VISTAS = ['mi-zona', 'mapa', 'riesgo', 'riesgo?comuna=7101', 'alertas', 'casos', 'temporada', 'preparate', 'calidad', 'mas',
          'quehago', 'privacidad']
ESTATICAS = ['/focos.html', '/web/lite.html', '/web/lista.html', '/web/preguntas.html', '/web/datos.html',
             '/web/pantalla.html?comuna=5801']
UMBRAL_MOTION_S = 0.2
TABS = 40

# Nombre accesible estilo árbol de accesibilidad: el texto clip-oculto cuenta
# (.sr-only), display:none/visibility:hidden/aria-hidden no. Devuelve también
# encabezados expuestos, landmarks, ids duplicados, lang, title y regiones vivas.
JS = r"""() => {
  const expuesta = (el) => {
    for (let p = el; p && p !== document.documentElement; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse') return false;
      if (p.hidden || p.getAttribute('aria-hidden') === 'true') return false;
    }
    return true;
  };
  const visible = (el) => { const r = el.getBoundingClientRect(); return expuesta(el) && r.width > 0 && r.height > 0 && +getComputedStyle(el).opacity !== 0; };
  const desc = (el) => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/)[0] : ''}`;
  // Texto expuesto al árbol: incluye clip (.sr-only); descarta ramas ocultas.
  const textoAcc = (el) => {
    let t = '';
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) {
      const p = w.currentNode.parentElement;
      if (p && expuesta(p)) t += ' ' + w.currentNode.nodeValue;
    }
    return t.replace(/\s+/g, ' ').trim();
  };
  const nombre = (el) => {
    const a = el.getAttribute('aria-label'); if (a && a.trim()) return a.trim();
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map((i) => { const n = document.getElementById(i); return n ? textoAcc(n) : ''; }).join(' ').trim(); if (t) return t; }
    if (el.labels && el.labels.length) { const t = [...el.labels].map((l) => textoAcc(l)).join(' ').trim(); if (t) return t; }
    const t = textoAcc(el) || (el.value || '').trim(); if (t) return t;
    const img = el.querySelector('img'); if (img && img.alt && img.alt.trim()) return img.alt.trim();
    const svgt = el.querySelector('svg title'); if (svgt && svgt.textContent.trim()) return svgt.textContent.trim();
    return (el.getAttribute('title') || el.getAttribute('placeholder') || '').trim();
  };
  const r = { sinNombre: [], camposSinEtiqueta: [], imgSinAlt: [], svgSinTitulo: [], h1: 0, saltosTitulo: [],
              landmarks: {}, idsDuplicados: [], lang: document.documentElement.lang || '', titulo: document.title, vivos: [] };
  let i = 0;
  for (const el of document.querySelectorAll('button, a[href], [role=button], [role=link], select, input:not([type=hidden]), textarea, summary, [tabindex]:not([tabindex="-1"])')) {
    if (!visible(el)) continue;
    if (!nombre(el)) { el.dataset.a11yCand = i++; r.sinNombre.push(desc(el) + ' ' + el.outerHTML.slice(0, 100)); }
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName) && !['button', 'submit', 'reset', 'checkbox', 'radio'].includes(el.type)) {
      const ok = (el.labels && el.labels.length) || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('title');
      if (!ok) r.camposSinEtiqueta.push(desc(el) + ' ' + (el.getAttribute('placeholder') || ''));
    }
  }
  for (const img of document.querySelectorAll('img')) if (visible(img) && !img.hasAttribute('alt')) r.imgSinAlt.push(img.src.slice(-60));
  for (const svg of document.querySelectorAll('svg')) {
    if (!visible(svg) || svg.closest('[aria-hidden="true"]')) continue;
    const rol = svg.getAttribute('role');
    if (rol === 'img' && !svg.querySelector('title') && !svg.getAttribute('aria-label') && !svg.getAttribute('aria-labelledby')) r.svgSinTitulo.push(desc(svg));
  }
  const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(expuesta);
  r.h1 = hs.filter((h) => h.tagName === 'H1').length;
  let prev = 0; for (const h of hs) { const n = +h.tagName[1]; if (prev && n > prev + 1) r.saltosTitulo.push(`h${prev}→h${n} «${textoAcc(h).slice(0, 40)}»`); prev = n; }
  r.landmarks = { main: !!document.querySelector('main,[role=main]'), nav: !!document.querySelector('nav,[role=navigation]'),
                  banner: !!document.querySelector('header,[role=banner]') };
  const ids = {}; for (const e of document.querySelectorAll('[id]')) ids[e.id] = (ids[e.id] || 0) + 1;
  r.idsDuplicados = Object.entries(ids).filter(([, n]) => n > 1).map(([id, n]) => `${id}×${n}`);
  for (const el of document.querySelectorAll('[aria-live], [role=status], [role=alert]'))
    r.vivos.push(desc(el) + '=' + (el.getAttribute('aria-live') || el.getAttribute('role')));
  return r;
}"""

# Contraste WCAG: color del texto contra el fondo efectivo compuesto subiendo
# por los ancestros (cada fondo parcial se mezcla sobre el de abajo). Omite el
# texto sobre imagen/gradiente/mapa y lo cuenta aparte.
CONTRASTE_JS = r"""() => {
  const rgba = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(',').map((x) => parseFloat(x)); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const mezcla = (arriba, abajo) => { const a = arriba.a + abajo.a * (1 - arriba.a); if (!a) return abajo;
    return { r: (arriba.r * arriba.a + abajo.r * abajo.a * (1 - arriba.a)) / a,
             g: (arriba.g * arriba.a + abajo.g * abajo.a * (1 - arriba.a)) / a,
             b: (arriba.b * arriba.a + abajo.b * abajo.a * (1 - arriba.a)) / a, a };
  };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const razon = (l1, l2) => (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  const fondoEfectivo = (el) => {
    let eff = { r: 255, g: 255, b: 255, a: 1 };
    const cadena = [];
    for (let p = el; p; p = p.parentElement) cadena.unshift(p);
    for (const p of cadena) { const c = rgba(getComputedStyle(p).backgroundColor); if (c && c.a > 0) eff = mezcla(c, eff); }
    return eff;
  };
  const sobreImagen = (el) => {
    for (let p = el; p; p = p.parentElement) {
      if (p.id === 'map' || (typeof p.className === 'string' && /maplibregl/.test(p.className)) || p.tagName === 'CANVAS') return true;
      const bi = getComputedStyle(p).backgroundImage;
      if (bi && bi !== 'none') return true;
    }
    return false;
  };
  const expuesta = (el) => {
    for (let p = el; p && p !== document.documentElement; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse') return false;
      if (p.hidden || p.getAttribute('aria-hidden') === 'true') return false;
    }
    return true;
  };
  const visible = (el) => { const r = el.getBoundingClientRect(); return expuesta(el) && r.width > 0 && r.height > 0 && +getComputedStyle(el).opacity !== 0; };
  const desc = (el) => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/)[0] : ''}`;
  const out = { fallos: [], sobreImagen: 0, nodos: 0 };
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const hechos = new Set();
  while (w.nextNode()) {
    const n = w.currentNode, txt = n.nodeValue.replace(/\s+/g, ' ').trim();
    if (txt.length < 2) continue;
    const el = n.parentElement;
    if (!el || hechos.has(el) || el.closest('script,style,noscript,template,svg') || el.closest('.sr-only') && !visible(el)) continue;
    if (!visible(el)) continue;
    hechos.add(el);
    if (sobreImagen(el)) { out.sobreImagen++; continue; }
    out.nodos++;
    const s = getComputedStyle(el);
    const frente = rgba(s.color); if (!frente) continue;
    const fondo = fondoEfectivo(el);
    const r = razon(lum(frente), lum(fondo));
    const px = parseFloat(s.fontSize);
    const grande = px >= 24 || (px >= 18.66 && (parseInt(s.fontWeight, 10) >= 700 || s.fontWeight === 'bold'));
    const umbral = grande ? 3 : 4.5;
    if (r < umbral) out.fallos.push({ el: desc(el), txt: txt.slice(0, 40), razon: +r.toFixed(2), umbral,
      color: s.color, fondo: `rgb(${Math.round(fondo.r)},${Math.round(fondo.g)},${Math.round(fondo.b)})`, px: +px.toFixed(1) });
  }
  return out;
}"""

FOCO_JS = r"""() => { const el = document.activeElement; if (!el || el === document.body) return { el: 'body' };
  const s = getComputedStyle(el); const r = el.getBoundingClientRect();
  const anillo = (c) => c && ((c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0) || (c.boxShadow && c.boxShadow !== 'none'));
  let visible = r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0;
  let marca = anillo(s);
  // El control puede ser invisible con un proxy que dibuja el anillo (`.switch input` → `+ span`).
  if (!visible && el.tagName === 'INPUT') {
    const proxy = el.nextElementSibling || (el.labels && el.labels[0]) || el.parentElement;
    if (proxy) { const pr = proxy.getBoundingClientRect(); const ps = getComputedStyle(proxy);
      if (pr.width > 0 && pr.height > 0 && anillo(ps)) { visible = true; marca = true; } }
  }
  return { el: `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''} «${(el.getAttribute('aria-label') || el.innerText || '').trim().slice(0, 30)}»`,
           idx: [...document.querySelectorAll('*')].indexOf(el),
           visible, anillo: marca, enModal: !!el.closest('dialog[open]') }; }"""

MOTION_JS = r"""() => {
  const malas = [];
  for (const el of document.querySelectorAll('*')) {
    const s = getComputedStyle(el);
    const duras = [...s.animationDuration.split(','), ...s.transitionDuration.split(',')];
    for (const d of duras) { const v = parseFloat(d); if (v && v > 0.2) { malas.push(`${el.tagName.toLowerCase()}.${(typeof el.className === 'string' ? el.className.split(' ')[0] : '')} ${d}`); break; } }
    if (malas.length > 30) break;
  }
  return malas;
}"""

ZOOM_JS = r"""() => {
  const vw = document.documentElement.clientWidth;
  const r = { scrollLateral: document.documentElement.scrollWidth > vw + 1, cortados: [], anchos: [] };
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') continue;
    const box = el.getBoundingClientRect();
    // Clip intencional (.sr-only, #live-text oculto por :has): no es texto cortado.
    if (box.width <= 2 || box.height <= 2 || el.closest('.sr-only')) continue;
    const propio = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (propio && el.scrollWidth > el.clientWidth + 1 && /(hidden|clip)/.test(s.overflowX) && s.textOverflow !== 'ellipsis' && el.clientWidth > 0)
      r.cortados.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''} «${el.textContent.trim().slice(0, 30)}»`);
    if (r.scrollLateral && (box.right > vw + 1 || box.left < -1) && box.width < vw * 3) {
      let p = el.parentElement, enScroll = false;
      while (p && p !== document.body) { const sp = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(sp.overflowX)) { enScroll = true; break; } p = p.parentElement; }
      if (!enScroll) r.anchos.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''} ${Math.round(box.left)}→${Math.round(box.right)} «${(el.textContent || '').trim().slice(0, 30)}»`);
    }
    if (r.cortados.length > 25 || r.anchos.length > 15) break;
  }
  return r;
}"""


def probar_modal(page):
    """El modal atrapa el foco, cierra con Escape y lo devuelve a quien lo abrió."""
    r = {'abre': False, 'trampa': False, 'escape': False, 'devuelve': False, 'detalle': ''}
    btn = None
    for sel in ('#settings-btn-m', '#settings-btn'):
        b = page.locator(sel)
        if b.count() and b.is_visible():
            btn = b
            break
    if not btn:
        r['detalle'] = 'sin botón de ajustes visible'
        return r
    btn.click()
    try:
        page.wait_for_selector('dialog[open]', timeout=5000)
    except Exception:
        r['detalle'] = 'el dialog no abrió'
        return r
    r['abre'] = True
    # 12 Tab: todo foco dentro del dialog. «body» es un paso válido del ciclo del
    # navegador en modo headless (vuelve a entrar al dialog en la tecla siguiente);
    # trampa solo si un elemento fuera del dialog recibe el foco.
    r['trampa'] = True
    for _ in range(12):
        page.keyboard.press('Tab')
        f = page.evaluate(FOCO_JS)
        if f['el'] != 'body' and not f.get('enModal'):
            r['trampa'] = False
            r['detalle'] = f"el foco salió del modal a {f['el']}"
            break
    page.keyboard.press('Escape')
    page.wait_for_timeout(400)
    r['escape'] = not page.evaluate("document.querySelector('dialog')?.open")
    f = page.evaluate(FOCO_JS)
    r['devuelve'] = 'settings-btn' in f['el']
    if not r['devuelve']:
        r['detalle'] = (r['detalle'] + '; ' if r['detalle'] else '') + f"el foco quedó en {f['el']}"
    return r


def confirmar_nombres(page, r):
    """Cada control marcado «sin nombre» se confirma contra el árbol real."""
    confirmados, falsos = [], []
    for i, texto in enumerate(r['sinNombre']):
        loc = page.locator(f'[data-a11y-cand="{i}"]')
        try:
            snap = loc.aria_snapshot(timeout=1500)
            # Un nodo nombrado aparece como `- button "nombre"` en la instantánea.
            m = re.match(r'^-\s*\w+\s+"([^"]+)"', (snap or '').strip())
            if m and m.group(1).strip():
                falsos.append(texto + f' → árbol: «{m.group(1).strip()}»')
                continue
        except Exception:
            pass
        confirmados.append(texto)
    r['falsosPositivosNombre'] = falsos
    r['sinNombre'] = confirmados


def auditar(page, ruta, es_spa, vp):
    if es_spa:
        page.evaluate(f"location.hash = '#/{ruta}'")
        page.wait_for_timeout(3000)
    else:
        page.goto(BASE + ruta, wait_until='load', timeout=60000)
        page.wait_for_timeout(1000)
    r = page.evaluate(JS)
    confirmar_nombres(page, r)
    r['focoMalo'] = teclado(page)
    # Contraste: 4 combinaciones en 390 px; en escritorio claro y oscuro en sencillo.
    # Las transiciones de color/fondo de la hoja de estilo se congelan: sin esto la
    # medición captura valores a mitad de camino entre un tema y el otro.
    combos = [('dark', 'simple'), ('light', 'simple'), ('dark', 'experto'), ('light', 'experto')] if vp == '390' \
        else [('dark', 'simple'), ('light', 'simple')]
    r['contraste'] = {}
    page.evaluate("""() => { const st = document.createElement('style'); st.id = 'a11y-sin-trans';
      st.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; }';
      document.head.appendChild(st); }""")
    for tema, nivel in combos:
        page.evaluate(f"document.documentElement.dataset.theme = '{tema}'; document.documentElement.dataset.detail = '{nivel}'")
        page.evaluate("() => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)))")
        r['contraste'][f'{tema}-{nivel}'] = page.evaluate(CONTRASTE_JS)
    page.evaluate("""() => { document.getElementById('a11y-sin-trans')?.remove();
      document.documentElement.dataset.theme = 'dark'; document.documentElement.dataset.detail = 'simple'; }""")
    # Movimiento reducido.
    page.emulate_media(reduced_motion='reduce')
    page.wait_for_timeout(100)
    r['motion'] = page.evaluate(MOTION_JS)
    page.emulate_media(reduced_motion='no-preference')
    # Zoom de texto 200 % solo en 390 px.
    if vp == '390':
        page.evaluate("document.documentElement.style.fontSize = '200%'")
        page.wait_for_timeout(400)
        r['zoom200'] = page.evaluate(ZOOM_JS)
        page.evaluate("document.documentElement.style.fontSize = ''")
        page.wait_for_timeout(200)
    return r


def teclado(page):
    """40 Tab: foco visible con anillo y sin trampa (mismo elemento repetido que
    no sea el último enfocable de la página — ahí el navegador se detiene)."""
    page.evaluate("document.activeElement?.blur(); window.scrollTo(0, 0)")
    page.keyboard.press('Tab')
    malos, ultimos = [], []
    for _ in range(TABS):
        f = page.evaluate(FOCO_JS)
        if f['el'] != 'body' and (not f.get('visible') or not f.get('anillo')):
            malos.append(f)
        ultimos.append(f.get('idx', f['el']))
        page.keyboard.press('Tab')
    if len(set(ultimos[-4:])) == 1 and ultimos[-1] != 'body':
        ultimo = page.evaluate(r"""() => { const els = [...document.querySelectorAll(
            'a[href], button, input:not([type=hidden]), select, textarea, summary, [tabindex]:not([tabindex="-1"])')]
            .filter((el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
              return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; });
          const u = els[els.length - 1];
          return u ? [...document.querySelectorAll('*')].indexOf(u) : -1; }""")
        if ultimos[-1] == ultimo:
            malos.append({'finPagina': ultimos[-1]})
        else:
            malos.append({'trampa': ultimos[-1]})
    return malos


def main():
    res = {}
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--no-sandbox'])
        for nombre, vp, tactil in (('390', {'width': 390, 'height': 844}, True), ('1280', {'width': 1280, 'height': 800}, False)):
            ctx = b.new_context(viewport=vp, has_touch=tactil, is_mobile=tactil, locale='es-CL', timezone_id='America/Santiago',
                                service_workers='block')
            page = ctx.new_page()
            page.goto(BASE + '/', wait_until='load', timeout=60000)
            page.wait_for_function("document.getElementById('view')?.children.length > 0", timeout=40000)
            res[nombre] = {}
            for v in VISTAS:
                res[nombre][v] = auditar(page, v, True, nombre)
            for s in ESTATICAS:
                res[nombre][s] = auditar(page, s, False, nombre)
            # Modal una vez por porte, desde la última vista SPA.
            page.goto(BASE + '/', wait_until='load', timeout=60000)
            page.wait_for_function("document.getElementById('view')?.children.length > 0", timeout=40000)
            res[nombre]['__modal__'] = probar_modal(page)
            ctx.close()
        b.close()
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for nombre, vistas in res.items():
        print('==', nombre)
        for v, r in vistas.items():
            if v == '__modal__':
                print(f"  {'modal':20} abre {r['abre']} trampa {r['trampa']} esc {r['escape']} devuelve {r['devuelve']} {r['detalle']}")
                continue
            ctr = {k: len(v['fallos']) for k, v in r['contraste'].items()}
            print(f"  {v:24} sinNombre {len(r['sinNombre']):2} fp {len(r['falsosPositivosNombre'])} campos {len(r['camposSinEtiqueta']):2} "
                  f"img {len(r['imgSinAlt'])} h1 {r['h1']} saltos {len(r['saltosTitulo'])} lm {''.join(k[0] for k, ok in r['landmarks'].items() if ok)} "
                  f"ids {len(r['idsDuplicados'])} foco {len(r['focoMalo'])} ctr {ctr} mot {len(r['motion'])}"
                  + (f" zoom lat:{r['zoom200']['scrollLateral']} cort:{len(r['zoom200']['cortados'])}" if 'zoom200' in r else ''))


main()
