#!/usr/bin/env node
/* Valida que los niveles del mapa de riesgo se distingan con daltonismo (UX-13).
 *
 * Lee RISK_COLORS y los fondos de PALETTE desde web/js/map.js, y las variables
 * --risk-* de web/css/app.css (deben ser idénticas). Falla (exit 1) si:
 *   - los colores de map.js y app.css difieren;
 *   - algún par de niveles adyacentes queda con ΔE76 < 12 en CIELAB bajo visión
 *     normal, deuteranopía o protanopía;
 *   - algún nivel queda bajo 3:1 de contraste WCAG contra el fondo del mapa
 *     (PALETTE.*.chile, la superficie bajo las comunas) en tema claro u oscuro.
 *
 * Además guarda el contraste de texto (WCAG AA, ≥ 4,5:1) en cada bloque de tema
 * de app.css: --br-ink contra --bg…--surface-3; --ink y --muted contra las
 * mismas cuatro superficies; --danger contra --surface y --bg; y --accent-ink
 * contra --accent (texto de botón). Si falta un token, falla. Los pares que hoy
 * no cumplen y se toleran a propósito viven en PENDIENTES, con su razón.
 */
import { readFileSync } from 'node:fs';

const MAP_JS = new URL('../../web/js/map.js', import.meta.url);
const APP_CSS = new URL('../../web/css/app.css', import.meta.url);
const DE_MIN = 12;
const CONTRASTE_MIN = 3;
const NIVELES = ['bajo', 'moderado', 'alto', 'extremo'];

// ------------------------------------------------------------------ color
const hex2rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
const srgb2lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const lin2srgb = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

/* Simulación de dicromacia: matrices de Viénot, Brettel & Mollon (1999),
 * «Digital video colourmaps for checking the legibility of displays by dichromats»,
 * Color Research & Application 24(4):243-252 — versión simplificada de una sola
 * matriz, aplicada en RGB lineal. */
const DEUTERANOPIA = [[0.625, 0.375, 0], [0.7, 0.3, 0], [0, 0.3, 0.7]];
const PROTANOPIA = [[0.567, 0.433, 0], [0.558, 0.442, 0], [0, 0.242, 0.758]];
const aplicarMatriz = (m, [r, g, b]) => m.map((f) => f[0] * r + f[1] * g + f[2] * b);
const simular = (rgb, m) => aplicarMatriz(m, rgb.map(srgb2lin)).map((v) => Math.min(1, Math.max(0, v))).map(lin2srgb);

const luminancia = ([r, g, b]) => 0.2126 * srgb2lin(r) + 0.7152 * srgb2lin(g) + 0.0722 * srgb2lin(b);
const contraste = (rgb1, rgb2) => {
  const [mayor, menor] = [luminancia(rgb1), luminancia(rgb2)].sort((a, b) => b - a);
  return (mayor + 0.05) / (menor + 0.05);
};

function lab(rgb) {
  const [r, g, b] = rgb.map(srgb2lin);
  const x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047;
  const y = 0.2126729 * r + 0.7151522 * g + 0.072175 * b;
  const z = (0.0193339 * r + 0.119192 * g + 0.9503041 * b) / 1.08883;
  const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const [fx, fy, fz] = [f(x), f(y), f(z)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}
const deltaE = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

// ------------------------------------------------------------------ lectura
const mapSrc = readFileSync(MAP_JS, 'utf8');
const cssSrc = readFileSync(APP_CSS, 'utf8');

const objeto = (fuente, nombre) => {
  const m = fuente.match(new RegExp(`${nombre}\\s*=\\s*\\{([^}]+)\\}`));
  if (!m) return null;
  return Object.fromEntries([...m[1].matchAll(/(\w+):\s*'([^']+)'/g)].map((x) => [x[1], x[2]]));
};

const riesgoJs = objeto(mapSrc, 'RISK_COLORS');
if (!riesgoJs || NIVELES.some((n) => !/^#[0-9a-fA-F]{6}$/.test(riesgoJs[n] ?? ''))) {
  console.error('No se pudo leer RISK_COLORS completo en web/js/map.js');
  process.exit(1);
}
const riesgoCss = Object.fromEntries(
  [...cssSrc.matchAll(/--risk-(\w+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2].toLowerCase()]),
);

const inicioPalette = mapSrc.indexOf('PALETTE');
const bloquePalette = mapSrc.slice(inicioPalette, mapSrc.indexOf('\n};', inicioPalette));
const temas = {};
for (const t of ['dark', 'light']) {
  const m = bloquePalette.match(new RegExp(`${t}:\\s*\\{([^}]+)\\}`));
  temas[t] = m ? Object.fromEntries([...m[1].matchAll(/(\w+):\s*'([^']+)'/g)].map((x) => [x[1], x[2]])) : null;
}
const FONDOS = { oscuro: temas.dark?.chile, claro: temas.light?.chile };
if (!Object.values(FONDOS).every((v) => /^#[0-9a-fA-F]{6}$/.test(v ?? ''))) {
  console.error('No se pudieron leer los fondos (chile) de PALETTE en web/js/map.js');
  process.exit(1);
}

// ------------------------------------------------------------------ chequeos
const fallas = [];

const distintos = NIVELES.filter((n) => riesgoCss[n]?.toLowerCase() !== riesgoJs[n].toLowerCase());
if (distintos.length) {
  fallas.push(`map.js y app.css difieren en: ${distintos.map((n) => `${n} (${riesgoJs[n]} vs ${riesgoCss[n] ?? 'ausente'})`).join(', ')}`);
}

const rgb = Object.fromEntries(NIVELES.map((n) => [n, hex2rgb(riesgoJs[n])]));
console.log('ΔE76 entre niveles adyacentes (mínimo 12):');
console.log('par                visión normal   deuteranopía   protanopía');
for (let i = 0; i < NIVELES.length - 1; i++) {
  const [a, b] = [NIVELES[i], NIVELES[i + 1]];
  const dist = [
    deltaE(lab(rgb[a]), lab(rgb[b])),
    deltaE(lab(simular(rgb[a], DEUTERANOPIA)), lab(simular(rgb[b], DEUTERANOPIA))),
    deltaE(lab(simular(rgb[a], PROTANOPIA)), lab(simular(rgb[b], PROTANOPIA))),
  ];
  console.log(`${`${a}-${b}`.padEnd(19)}${dist.map((d) => `${d.toFixed(1).padStart(8)} ${d < DE_MIN ? '✗' : ' '}`).join('       ')}`);
  for (const [j, vision] of ['normal', 'deuteranopía', 'protanopía'].entries()) {
    if (dist[j] < DE_MIN) fallas.push(`${a}-${b} con ΔE ${dist[j].toFixed(1)} < ${DE_MIN} bajo ${vision}`);
  }
}

console.log('\nContraste WCAG contra el fondo del mapa (mínimo 3:1):');
console.log(`nivel      color      fondo claro (${FONDOS.claro})   fondo oscuro (${FONDOS.oscuro})`);
for (const n of NIVELES) {
  const porTema = [contraste(rgb[n], hex2rgb(FONDOS.claro)), contraste(rgb[n], hex2rgb(FONDOS.oscuro))];
  console.log(`${n.padEnd(11)}${riesgoJs[n].padEnd(11)}${porTema.map((c) => `${c.toFixed(2).padStart(8)} ${c < CONTRASTE_MIN ? '✗' : ' '}`).join('               ')}`);
  if (porTema[0] < CONTRASTE_MIN) fallas.push(`${n} con contraste ${porTema[0].toFixed(2)}:1 < 3:1 sobre el fondo claro`);
  if (porTema[1] < CONTRASTE_MIN) fallas.push(`${n} con contraste ${porTema[1].toFixed(2)}:1 < 3:1 sobre el fondo oscuro`);
}

// ------------------------------------------------- tinta de la marca «BR»
const CONTRASTE_TEXTO_MIN = 4.5;
const FONDOS_TEXTO = ['--bg', '--surface', '--surface-2', '--surface-3'];
const cssTema = {};
for (const t of ['dark', 'light']) {
  const m = cssSrc.match(new RegExp(`data-theme="${t}"\\]\\s*\\{([^}]+)\\}`));
  cssTema[t] = m
    ? Object.fromEntries([...m[1].matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})/g)].map((x) => [x[1], x[2].toLowerCase()]))
    : null;
}

console.log('\nContraste WCAG del texto «BR» (--br-ink) contra las superficies (mínimo 4.5:1):');
for (const [t, nombre] of [['dark', 'oscuro'], ['light', 'claro']]) {
  const vars = cssTema[t];
  if (!vars) {
    fallas.push(`no se encontró el bloque :root[data-theme="${t}"] en web/css/app.css`);
    continue;
  }
  const tinta = vars['--br-ink'];
  if (!tinta) {
    fallas.push(`no se encontró --br-ink en :root[data-theme="${t}"] de web/css/app.css`);
    continue;
  }
  console.log(`tema ${nombre} — --br-ink ${tinta}`);
  for (const f of FONDOS_TEXTO) {
    const fondo = vars[f];
    if (!fondo) {
      fallas.push(`no se encontró ${f} en :root[data-theme="${t}"] de web/css/app.css`);
      continue;
    }
    const c = contraste(hex2rgb(tinta), hex2rgb(fondo));
    console.log(`  ${f.padEnd(12)}${fondo}   ${c.toFixed(2).padStart(6)} ${c < CONTRASTE_TEXTO_MIN ? '✗' : ' '}`);
    if (c < CONTRASTE_TEXTO_MIN) fallas.push(`--br-ink ${tinta} con contraste ${c.toFixed(2)}:1 < 4.5:1 sobre ${f} (${fondo}) en tema ${nombre}`);
  }
}

// ------------------------------------------------- texto corriente por tema
/* Pares que hoy quedan bajo 4,5:1 y se toleran a propósito. Clave:
 * `${tema}|${token}|${fondo}`. Cada entrada debe justificar por qué se acepta
 * (texto decorativo, tamaño grande, etc.). Quitar un token de la paleta es
 * decisión de diseño: si un par falla y no está aquí, el script falla y hay
 * que anotarlo para que Diego decida, nunca ajustar el color desde la guarda. */
const PENDIENTES = new Map([
  // ['claro|--muted|--surface-3', '4,4:1 — ejemplo: texto auxiliar grande'],
]);

/* Los pares que la app usa de verdad: --ink y --muted van sobre cualquier
 * superficie; --danger se usa como texto sobre --bg y --surface; --accent-ink
 * es la tinta de los botones con fondo --accent. */
const PARES_TEXTO = [
  { token: '--ink', fondos: FONDOS_TEXTO },
  { token: '--muted', fondos: FONDOS_TEXTO },
  { token: '--danger', fondos: ['--surface', '--bg'] },
  { token: '--accent-ink', fondos: ['--accent'] },
];

console.log('\nContraste WCAG del texto corriente por tema (mínimo 4.5:1):');
for (const [t, nombre] of [['dark', 'oscuro'], ['light', 'claro']]) {
  const vars = cssTema[t];
  if (!vars) continue; // ya quedó registrado como falla arriba
  for (const { token, fondos } of PARES_TEXTO) {
    const tinta = vars[token];
    if (!tinta) {
      fallas.push(`no se encontró ${token} en :root[data-theme="${t}"] de web/css/app.css`);
      continue;
    }
    console.log(`tema ${nombre} — ${token} ${tinta}`);
    for (const f of fondos) {
      const fondo = vars[f];
      if (!fondo) {
        fallas.push(`no se encontró ${f} en :root[data-theme="${t}"] de web/css/app.css`);
        continue;
      }
      const c = contraste(hex2rgb(tinta), hex2rgb(fondo));
      const clave = `${nombre}|${token}|${f}`;
      const pendiente = PENDIENTES.get(clave);
      const marca = c < CONTRASTE_TEXTO_MIN ? (pendiente ? '◌' : '✗') : ' ';
      console.log(`  ${f.padEnd(12)}${fondo}   ${c.toFixed(2).padStart(6)} ${marca}${pendiente ? ` (pendiente: ${pendiente})` : ''}`);
      if (c < CONTRASTE_TEXTO_MIN && !pendiente) {
        fallas.push(`${token} ${tinta} con contraste ${c.toFixed(2)}:1 < 4.5:1 sobre ${f} (${fondo}) en tema ${nombre}`);
      }
      if (c >= CONTRASTE_TEXTO_MIN && pendiente) {
        fallas.push(`${token} sobre ${f} en tema ${nombre} ya da ${c.toFixed(2)}:1: quita la entrada de PENDIENTES`);
      }
    }
  }
}

if (fallas.length) {
  console.error(`\n${fallas.length} problema(s):`);
  for (const f of fallas) console.error(`  ✗ ${f}`);
  process.exit(1);
}
console.log('\nPaleta apta para daltonismo: todos los pares se distinguen y hay contraste suficiente.');
