"""Área tocable real de los controles de BRASA (hit-testing), no la caja dibujada.

Para cada control visible con caja menor a 44 px en algún lado, toca (elementFromPoint) una
grilla de puntos dentro de un cuadrado de 44×44 centrado en él. Cuenta como «propio» el
punto que cae en el control, en un descendiente, en su <label> o en un ancestro que sea el
mismo control interactivo. Reporta el % de la caja de 44 que responde al control.

Uso: python area_tactil.py <BASE> <OUT.json> [ancho]
"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip('/')
OUT = sys.argv[2]
ANCHO = int(sys.argv[3]) if len(sys.argv) > 3 else 360
VISTAS = ['mi-zona', 'mapa', 'riesgo', 'alertas', 'casos', 'temporada', 'preparate', 'calidad', 'mas', 'quehago', 'privacidad']
ESTATICAS = ['/focos.html', '/web/lite.html', '/web/lista.html']

JS = r"""() => {
  const SEL = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [tabindex]:not([tabindex="-1"])';
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0
      && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && !el.closest('.sr-only, [aria-hidden="true"]'); };
  const propio = (el, hit) => {
    if (!hit) return false;
    if (el === hit || el.contains(hit)) return true;
    const lab = hit.closest('label');
    if (lab && (lab.control === el || lab.contains(el))) return true;
    if (el.labels && [...el.labels].some((l) => l.contains(hit))) return true;
    const ctl = hit.closest(SEL);
    return ctl === el;
  };
  const desc = (el) => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/)[0] : ''} «${(el.getAttribute('aria-label') || el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 40)}»`;
  const out = [];
  for (const el of document.querySelectorAll(SEL)) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width >= 44 && r.height >= 44) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    let ok = 0, n = 0;
    for (let dy = -20; dy <= 20; dy += 5) for (let dx = -20; dx <= 20; dx += 5) {
      const x = cx + dx, y = cy + dy;
      if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
      n += 1;
      if (propio(el, document.elementFromPoint(x, y))) ok += 1;
    }
    // Alto y ancho tocables reales: barrido en cruz desde el centro, de a 1 px.
    const alcance = (vx, vy) => { let d = 0; while (d < 40 && propio(el, document.elementFromPoint(cx + vx * (d + 1), cy + vy * (d + 1)))) d++; return d; };
    const alto = alcance(0, -1) + alcance(0, 1) + 1, ancho = alcance(-1, 0) + alcance(1, 0) + 1;
    out.push({ el: desc(el), caja: [Math.round(r.width), Math.round(r.height)], tocable: [ancho, alto], pct44: n ? Math.round(100 * ok / n) : null });
  }
  return out;
}"""


def main():
    res = {'base': BASE, 'ancho': ANCHO, 'vistas': {}}
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--no-sandbox'])
        ctx = b.new_context(viewport={'width': ANCHO, 'height': 780}, device_scale_factor=2, is_mobile=True, has_touch=True,
                            locale='es-CL', timezone_id='America/Santiago')
        page = ctx.new_page()
        page.goto(BASE + '/', wait_until='load', timeout=60000)
        page.wait_for_function("document.getElementById('view')?.children.length > 0", timeout=40000)
        for v in VISTAS:
            page.evaluate(f"location.hash = '#/{v}'")
            try:
                page.wait_for_load_state('networkidle', timeout=12000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(1500)
            res['vistas'][v] = page.evaluate(JS)
        for s in ESTATICAS:
            page.goto(BASE + s, wait_until='load', timeout=60000)
            page.wait_for_timeout(800)
            res['vistas'][s] = page.evaluate(JS)
        b.close()
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for v, lista in res['vistas'].items():
        malos = [x for x in lista if min(x['tocable']) < 44]
        print(f"{v:18} chicos {len(lista):3}  tocable<44 {len(malos):3}  " + '; '.join(f"{x['el'][:38]} {x['tocable'][0]}x{x['tocable'][1]}" for x in malos[:6]))


main()
