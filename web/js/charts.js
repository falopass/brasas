/* Gráficos de series de tiempo en SVG: paneles pequeños apilados con eje X compartido.
 * Un eje Y por panel (nunca doble eje), cursor sincronizado, tooltip y navegación con teclado. */
import { fmtNum, TZ } from './util.js';

const NS = 'http://www.w3.org/2000/svg';
const PAD = { left: 40, right: 12, top: 18, bottom: 6 };
const AXIS_H = 22;

function el(name, attrs = {}, parent) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  parent?.append(node);
  return node;
}

function niceMax(value) {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const exp = 10 ** Math.floor(Math.log10(value));
  const f = value / exp;
  const step = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((s) => f <= s);
  return step * exp;
}

const hourLabel = (d) => d.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
const dayLabel = (d) => d.toLocaleDateString('es-CL', { day: 'numeric', month: 'short', timeZone: TZ });

/**
 * @param {HTMLElement} container
 * @param {{times: string[], panels: Array<{id, title, unit, kind, series: Array<{key,label,color,values}>, threshold?, digits?, yMax?}>,
 *          onSeek?: (i:number)=>void, cursor?: number, emptyText?: string}} spec
 */
export function timeChart(container, spec) {
  container.classList.add('tchart');
  container.tabIndex = 0;
  container.setAttribute('role', 'group');
  container.setAttribute('aria-label', `Gráficos: ${spec.panels.map((p) => p.title).join(', ')}. Usa las flechas para recorrer el tiempo.`);
  const times = spec.times.map((t) => new Date(t));
  const tooltip = document.createElement('div');
  tooltip.className = 'tchart-tip';
  tooltip.hidden = true;
  let cursor = spec.cursor ?? null;
  let width = 0;
  let svgs = [];

  const x = (i) => PAD.left + (times.length <= 1 ? 0 : (i / (times.length - 1)) * (width - PAD.left - PAD.right));
  const indexAt = (px) => {
    const ratio = (px - PAD.left) / Math.max(1, width - PAD.left - PAD.right);
    return Math.max(0, Math.min(times.length - 1, Math.round(ratio * (times.length - 1))));
  };

  function render() {
    width = container.clientWidth;
    if (!width) return;
    container.replaceChildren();
    svgs = [];
    spec.panels.forEach((panel, pi) => {
      const last = pi === spec.panels.length - 1;
      const height = (panel.height || 78) + (last ? AXIS_H : 0);
      const plotH = (panel.height || 78) - PAD.top - PAD.bottom;
      const wrap = document.createElement('div');
      wrap.className = 'tchart-panel';
      const svg = el('svg', { width, height, viewBox: `0 0 ${width} ${height}`, 'aria-hidden': 'true' }, wrap);
      container.append(wrap);
      const values = panel.series.flatMap((s) => s.values.filter(Number.isFinite));
      const stackedMax = panel.kind === 'bars' ? Math.max(0, ...times.map((_, i) => panel.series.reduce((a, s) => a + (s.values[i] || 0), 0))) : 0;
      const rawMax = Math.max(panel.yMax || 0, panel.threshold?.value || 0, panel.kind === 'bars' ? stackedMax : Math.max(0, ...values));
      const yMax = niceMax(rawMax * 1.05);
      const y = (v) => PAD.top + plotH - (v / yMax) * plotH;
      // título (texto, nunca en color de serie)
      const title = el('text', { x: PAD.left, y: 12, class: 'tchart-title' }, svg);
      title.textContent = panel.title + (panel.unit ? ` (${panel.unit})` : '');
      // grilla y eje Y: 0 y máximo
      for (const v of [0, yMax / 2, yMax]) {
        el('line', { x1: PAD.left, x2: width - PAD.right, y1: y(v), y2: y(v), class: v === 0 ? 'tchart-base' : 'tchart-grid' }, svg);
        const t = el('text', { x: PAD.left - 6, y: y(v) + 3.5, class: 'tchart-tick', 'text-anchor': 'end' }, svg);
        t.textContent = fmtNum(v, yMax < 10 ? 1 : 0);
      }
      if (panel.threshold) {
        const ty = y(panel.threshold.value);
        const below = panel.threshold.direction === 'below';
        el('rect', { x: PAD.left, width: width - PAD.left - PAD.right, class: 'tchart-zone',
          y: below ? ty : PAD.top, height: below ? PAD.top + plotH - ty : ty - PAD.top }, svg);
        el('line', { x1: PAD.left, x2: width - PAD.right, y1: ty, y2: ty, class: 'tchart-threshold' }, svg);
        const tl = el('text', { x: width - PAD.right, y: ty - 4, class: 'tchart-tick', 'text-anchor': 'end' }, svg);
        tl.textContent = panel.threshold.label;
      }
      const step = times.length > 1 ? (width - PAD.left - PAD.right) / (times.length - 1) : 10;
      if (panel.kind === 'bars') {
        const barW = Math.max(1, Math.min(24, step - (step > 4 ? 2 : 0)));
        const base = new Array(times.length).fill(0);
        panel.series.forEach((s) => {
          const path = [];
          s.values.forEach((v, i) => {
            if (!v) return;
            const x0 = x(i) - barW / 2;
            const y0 = y(base[i] + v); const y1 = y(base[i]);
            path.push(`M${x0},${y1}V${y0}H${x0 + barW}V${y1}Z`);
            base[i] += v;
          });
          el('path', { d: path.join(''), class: 'tchart-bars' }, svg).style.fill = s.color;
        });
      } else {
        panel.series.forEach((s) => {
          let d = ''; let area = ''; let started = false; let firstX = 0; let lastX = 0;
          s.values.forEach((v, i) => {
            if (!Number.isFinite(v)) { started = false; return; }
            const px = x(i); const py = y(v);
            if (!started) { d += `M${px},${py}`; if (!area) { firstX = px; area = `M${px},${y(0)}L${px},${py}`; } else area += `L${px},${py}`; started = true; } else { d += `L${px},${py}`; area += `L${px},${py}`; }
            lastX = px;
          });
          if (panel.area && area) el('path', { d: `${area}L${lastX},${y(0)}L${firstX},${y(0)}Z`, class: 'tchart-area' }, svg).style.fill = s.color;
          el('path', { d, class: 'tchart-line' }, svg).style.stroke = s.color;
        });
      }
      if (last) {
        // eje X: días y horas (hora de Chile)
        const span = times.length ? (times[times.length - 1] - times[0]) / 3600000 : 0;
        const every = span <= 30 ? 6 : span <= 80 ? 12 : span <= 200 ? 24 : 48;
        times.forEach((d, i) => {
          const h = Number(d.toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: TZ }));
          if (h % every !== 0 && !(every >= 24 && h === 0)) return;
          if (every >= 24 && h !== 0) return;
          const tx = x(i);
          if (tx < PAD.left + 14 || tx > width - PAD.right - 14) return;
          el('line', { x1: tx, x2: tx, y1: PAD.top + plotH, y2: PAD.top + plotH + 4, class: 'tchart-base' }, svg);
          const t = el('text', { x: tx, y: PAD.top + plotH + 16, class: 'tchart-tick', 'text-anchor': 'middle' }, svg);
          t.textContent = h === 0 ? dayLabel(d) : hourLabel(d);
        });
      }
      el('line', { class: 'tchart-cursor', y1: PAD.top - 4, y2: PAD.top + plotH, x1: 0, x2: 0, visibility: 'hidden' }, svg);
      el('line', { class: 'tchart-hover', y1: PAD.top - 4, y2: PAD.top + plotH, x1: 0, x2: 0, visibility: 'hidden' }, svg);
      svgs.push(svg);
      wrap.addEventListener('pointermove', (e) => { const r = svg.getBoundingClientRect(); setHover(indexAt(e.clientX - r.left), e); });
      wrap.addEventListener('pointerleave', () => setHover(null));
      wrap.addEventListener('click', (e) => { const r = svg.getBoundingClientRect(); spec.onSeek?.(indexAt(e.clientX - r.left)); });
    });
    if (!spec.times.length) {
      const empty = document.createElement('p');
      empty.className = 'tchart-empty';
      empty.textContent = spec.emptyText || 'Sin datos para graficar.';
      container.append(empty);
    }
    container.append(tooltip);
    drawCursor();
  }

  function drawLine(cls, index) {
    for (const svg of svgs) {
      const line = svg.querySelector(`.${cls}`);
      line.setAttribute('visibility', index === null || index === undefined ? 'hidden' : 'visible');
      const px = index === null || index === undefined ? 0 : x(index);
      line.setAttribute('x1', px); line.setAttribute('x2', px);
    }
  }
  const drawCursor = () => drawLine('tchart-cursor', cursor);

  function setHover(index, event) {
    drawLine('tchart-hover', index);
    if (index === null) { tooltip.hidden = true; return; }
    tooltip.replaceChildren();
    const head = document.createElement('div');
    head.className = 'tchart-tip-time';
    head.textContent = times[index].toLocaleString('es-CL', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
    tooltip.append(head);
    for (const panel of spec.panels) {
      for (const s of panel.series) {
        const row = document.createElement('div');
        row.className = 'tchart-tip-row';
        const key = document.createElement('span'); key.className = 'tchart-key'; key.style.background = s.color;
        const value = document.createElement('strong');
        const v = s.values[index];
        value.textContent = Number.isFinite(v) ? `${fmtNum(v, panel.digits ?? 0)}${panel.unit ? ` ${panel.unit}` : ''}` : '—';
        const label = document.createElement('span'); label.textContent = s.label || panel.title;
        row.append(key, value, label);
        tooltip.append(row);
      }
    }
    tooltip.hidden = false;
    if (event) {
      const box = container.getBoundingClientRect();
      const left = Math.min(box.width - tooltip.offsetWidth - 4, Math.max(4, event.clientX - box.left + 14));
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${Math.max(0, event.clientY - box.top - tooltip.offsetHeight - 10)}px`;
    }
  }

  container.addEventListener('keydown', (e) => {
    if (!times.length) return;
    const current = cursor ?? 0;
    const delta = { ArrowRight: 1, ArrowLeft: -1, PageUp: 12, PageDown: -12 }[e.key];
    if (delta) { e.preventDefault(); spec.onSeek?.(Math.max(0, Math.min(times.length - 1, current + delta))); }
  });
  const observer = new ResizeObserver(() => { if (container.clientWidth !== width) render(); });
  observer.observe(container);
  render();
  return {
    setCursor(index) { cursor = index; drawCursor(); },
    destroy() { observer.disconnect(); container.replaceChildren(); },
  };
}
