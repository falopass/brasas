"""RISK-03, OFI-25 y OFI-20: tres capas del riesgo, campamentos MINVU y Pyrocast.

Revisa el contrato de `web/js/exposure.js` y `web/js/views/riesgo.js`: el catastro
público entra en la exposición, el ranking puede ordenarse por peligro × exposición
y el meteograma abre con lat/lon a 4 decimales. Las cadenas visibles no usan raya larga.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPOSURE = ROOT / "web" / "js" / "exposure.js"
RIESGO = ROOT / "web" / "js" / "views" / "riesgo.js"

_NODE = r"""
globalThis.window ??= { addEventListener() {} };
const riesgo = await import('./web/js/views/riesgo.js');
const exposure = await import('./web/js/exposure.js');
const cerca = (a, b) => Math.abs(a - b) < 1e-9;

const url = riesgo.pyrocastUrl(-33.45678, -70.64891);
if (url !== 'https://meteograma.deigeprif.com/?lat=-33.4568&lon=-70.6489') throw new Error('pyrocast ' + url);
const urlCeros = riesgo.pyrocastUrl(-33.45, -70.6);
if (urlCeros !== 'https://meteograma.deigeprif.com/?lat=-33.4500&lon=-70.6000') throw new Error('pyrocast ceros ' + urlCeros);

const rows = [
  { code: 1, score: 10, tmax: 30 },
  { code: 2, score: 10, tmax: 35 },
  { code: 3, score: 8, tmax: 40 },
];
const antes = rows.map((r) => r.code).join();
const peligro = riesgo.ordenarRanking(rows, 'peligro').map((r) => r.code);
if (antes !== '1,2,3') throw new Error('ordenarRanking mutó el arreglo');
if (peligro.join() !== '2,1,3') throw new Error('peligro ' + peligro);
const expo = riesgo.ordenarRanking(rows, 'exposicion', { 3: { factor: 2 }, 1: { factor: 1 }, 2: { factor: 1 } }).map((r) => r.code);
if (expo.join() !== '3,2,1') throw new Error('exposicion ' + expo);
const defecto = riesgo.ordenarRanking(rows, 'otro').map((r) => r.code).join();
if (defecto !== peligro.join()) throw new Error('modo desconocido ' + defecto);

const n2 = exposure.exposureNumbers({ poblacion: 1, viviendas: 2 }, { ha_interfaz: 3, pct_comuna: 4 });
const forma = JSON.stringify({ poblacion: 1, viviendas: 2, ha_interfaz: 3, pct_comuna: 4 });
if (JSON.stringify(n2) !== forma) throw new Error('dos argumentos ' + JSON.stringify(n2));
const n3 = exposure.exposureNumbers(
  { poblacion: 1, viviendas: 2 },
  { ha_interfaz: 3, pct_comuna: 4 },
  { n_campamentos: 8, n_hogares: 626 },
);
if (n3.n_campamentos !== 8 || n3.n_hogares_campamentos !== 626) throw new Error('tres argumentos ' + JSON.stringify(n3));
const nNull = exposure.exposureNumbers({ poblacion: 1, viviendas: 2 }, null, null);
if (nNull.n_campamentos !== null || nNull.n_hogares_campamentos !== null) throw new Error('campamento nulo');

const censo = { comunas: [{ code: 1101, poblacion: 10, viviendas: 4 }] };
const sinInterfaz = { comunas: {} };
const base = exposure.comunaExposureOf(censo, sinInterfaz, 1101);
if (JSON.stringify(base) !== JSON.stringify({ poblacion: 10, viviendas: 4, interfaz: false })) {
  throw new Error('comunaExposureOf 3 args ' + JSON.stringify(base));
}
const conCamp = exposure.comunaExposureOf(censo, sinInterfaz, 1101, {
  comunas: [{ code: 1101, n_campamentos: 2, n_hogares: 9 }],
});
if (conCamp.poblacion !== 10 || conCamp.interfaz !== false || conCamp.n_campamentos !== 2 || conCamp.n_hogares_campamentos !== 9) {
  throw new Error('comunaExposureOf 4 args ' + JSON.stringify(conCamp));
}
const ceros = exposure.comunaExposureOf(censo, sinInterfaz, 1101, { comunas: [] });
if (ceros.n_campamentos !== 0 || ceros.n_hogares_campamentos !== 0) throw new Error('sin fila ' + JSON.stringify(ceros));

if (!cerca(exposure.exposureFactor({}), 1)) throw new Error('factor vacio');
if (!cerca(exposure.exposureFactor({ ha_interfaz: 1 }), 1.4)) throw new Error('factor interfaz');
if (!cerca(exposure.exposureFactor({ ha_interfaz: 5, viviendas: 80000, n_hogares: 2000 }), 2)) throw new Error('factor tope');
if (!cerca(exposure.exposureFactor({ ha_interfaz: 5, viviendas: 500000, n_hogares: 9000 }), 2)) throw new Error('factor sobre tope');

const ahora = new Date().toISOString();
const CENSO = { fetched_at: ahora, comunas: [{ code: 1101, name: 'Iquique', poblacion: 199587, viviendas: 75372 }] };
const INTERFAZ = { fetched_at: ahora, comunas: { '1101': { ha_interfaz: 2735.3, pct_comuna: 1.03 } } };
const responder = (camps) => async (path) => {
  const p = String(path);
  const data = p.includes('censo') ? CENSO : p.includes('campamentos') ? camps : p.includes('interfaz') ? INTERFAZ : {};
  return { ok: true, json: async () => data };
};
globalThis.fetch = responder({ comunas: [{ code: 1101, n_campamentos: 8, n_hogares: 626 }] });
const fresco = await import('./web/js/exposure.js?caso=camp');
const html = String(await fresco.exposureSection(1101));
if (!html.includes('8 campamentos') || !html.includes('626 hogares')) throw new Error('parrafo ' + html);
if (!html.includes('https://geoide.minvu.cl/server/rest/services/Catastros/Catastros_campamentos/FeatureServer')) {
  throw new Error('sin enlace MINVU');
}
if (!html.includes('MINVU · Catastro de Campamentos')) throw new Error('sin rotulo MINVU');
const partes = { ha_interfaz: 2735.3, viviendas: 75372, n_hogares: 626 };
const idx = await fresco.loadExposureIndex();
if (!idx['1101'] || !cerca(idx['1101'].factor, fresco.exposureFactor(partes))) throw new Error('indice ' + JSON.stringify(idx['1101']));
if (idx['1101'].factor < 1 || idx['1101'].factor > 2) throw new Error('fuera de rango');

globalThis.fetch = responder({ comunas: [{ code: 1101, n_campamentos: 1, n_hogares: 3 }] });
const uno = await import('./web/js/exposure.js?caso=uno');
const htmlUno = String(await uno.exposureSection(1101));
if (!htmlUno.includes('1 campamento') || htmlUno.includes('1 campamentos')) throw new Error('singular ' + htmlUno);

globalThis.fetch = async () => { throw new Error('sin red'); };
const caido = await import('./web/js/exposure.js?caso=caido');
const vacio = await caido.loadExposureIndex();
if (JSON.stringify(vacio) !== '{}') throw new Error('sin red debio dar indice vacio');
if (await caido.exposureSection(1101) !== '') throw new Error('sin red debio dar seccion vacia');

console.log(JSON.stringify({ ok: true, url, peligro, expo, factor: idx['1101'].factor }));
"""


def _sin_comentarios(texto: str) -> str:
    sin_bloque = re.sub(r"/\*[\s\S]*?\*/", "", texto)
    return "\n".join(re.split(r"(?<!:)//", linea, maxsplit=1)[0] for linea in sin_bloque.splitlines())


def _node() -> dict:
    corrida = subprocess.run(
        ["node", "--input-type=module", "-e", _NODE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert corrida.returncode == 0, corrida.stderr or corrida.stdout
    return json.loads(corrida.stdout)


def test_exposure_consume_el_catastro():
    texto = EXPOSURE.read_text(encoding="utf-8")
    assert "/web/data/campamentos.json" in texto
    assert "function campamentos(" in texto
    assert "export async function loadExposureIndex(" in texto
    assert "export function exposureFactor(" in texto
    assert "n_campamentos" in texto and "n_hogares_campamentos" in texto
    assert "MINVU · Catastro de Campamentos" in texto
    assert "geoide.minvu.cl/server/rest/services/Catastros/Catastros_campamentos/FeatureServer" in texto


def test_riesgo_tiene_tres_capas_orden_y_pyrocast():
    texto = RIESGO.read_text(encoding="utf-8")
    assert "export function pyrocastUrl(" in texto
    assert "export function ordenarRanking(" in texto
    assert "pyrocastUrl(centro[1], centro[0])" in texto
    assert "https://meteograma.deigeprif.com/" in texto
    assert "Meteograma Pyrocast en" in texto
    assert 'id="r-sort"' in texto
    assert "Peligro del día" in texto
    assert "Peligro × Exposición (estimación BRASA)" in texto
    assert "estimación orientativa de BRASA, no índice oficial" in texto
    assert "1. Condiciones del día" in texto
    assert "2. Combustible acumulado" in texto
    assert "3. Exposición territorial" in texto
    assert "Capa 1 · ¿Puede empezar y propagarse hoy?" in texto
    assert "Capa 2 · ¿Cuánto combustible seco hay acumulado?" in texto
    assert "Capa 3 · ¿A quién afecta si hay fuego?" in texto


def test_sin_raya_larga_en_cadenas_visibles():
    for ruta in (EXPOSURE, RIESGO):
        limpio = _sin_comentarios(ruta.read_text(encoding="utf-8"))
        assert "\u2014" not in limpio, ruta.name
        assert "\\u2014" not in limpio, ruta.name


def test_funciones_exportadas():
    dato = _node()
    assert dato["ok"] is True
    assert dato["url"].endswith("lat=-33.4568&lon=-70.6489")
    assert dato["peligro"] == [2, 1, 3]
    assert dato["expo"] == [3, 2, 1]
    assert 1 <= dato["factor"] <= 2
