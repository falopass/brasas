"""RISK-11: sequedad de la vegetación viva (verdor satelital) en la ficha de riesgo.

El JSON cabe, no inventa un cero cuando falta la anomalía, el generador publica
la misma regla y la ficha explica el índice en palabras con el enlace de la NASA
visible fuera de la doble lectura.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON = ROOT / "web" / "data" / "vegetacion-sequedad.json"
SCRIPT = ROOT / "scripts" / "actualizar_sequedad_vegetacion.py"
RIESGO = ROOT / "web" / "js" / "views" / "riesgo.js"
INDICE = ROOT / "web" / "data" / "comunas-index.json"
FUENTE = "NASA MODIS / VIIRS · Índice de verdor satelital (NDVI)"
URL = "https://modis.gsfc.nasa.gov/data/dataprod/mod13.php"
ESTADOS = {"normal", "seca", "muy_seca"}

_NODE = r"""
globalThis.window ??= { addEventListener() {} };
const riesgo = await import('./web/js/views/riesgo.js');

if (riesgo.anomaliaVisible(null) !== null) throw new Error('paquete nulo');
if (riesgo.anomaliaVisible({}) !== null) throw new Error('sin campo');
if (riesgo.anomaliaVisible({ anomalia_pct: null }) !== null) throw new Error('null no es null');
if (riesgo.textoAnomalia(null) !== '') throw new Error('texto de null');
if (/\b0\s*%/.test(riesgo.textoAnomalia(null) + riesgo.textoAnomalia(undefined))) throw new Error('null dijo 0 %');
if (riesgo.anomaliaVisible({ anomalia_pct: 0 }) !== 0) throw new Error('el cero real se perdio');
if (!riesgo.textoAnomalia(-14).includes('14') || !riesgo.textoAnomalia(-14).includes('más seco')) {
  throw new Error('negativo ' + riesgo.textoAnomalia(-14));
}

const paquete = {
  source: 'NASA MODIS / VIIRS · Índice de verdor satelital (NDVI)',
  source_url: 'https://modis.gsfc.nasa.gov/data/dataprod/mod13.php',
  imagen_en: '2026-09-14',
  regiones: [{ nombre: 'Maule', estado: 'seca', anomalia_pct: -12, lectura: 'Los bosques, matorrales y pastizales de Maule están más secos que lo habitual para esta época.' }],
  comunas: [{ code: 7101, nombre: 'Talca', region: 'Maule', estado: 'seca', anomalia_pct: null, lectura: 'Los bosques, matorrales y pastizales de Talca están más secos que lo habitual para esta época.' }],
  macrozonas: [{ id: 'centro_sur', nombre: 'Centro-sur', regiones: ['Maule'], estado: 'seca', anomalia_pct: -12, lectura: 'zona' }],
};
const talca = String(riesgo.htmlSequedad(paquete, { code: 7101, name: 'Talca', region: 'Maule' }));
if (/\b0\s*%/.test(talca)) throw new Error('null de Talca se volvio 0: ' + talca);
if (!talca.includes('más secos que lo habitual')) throw new Error('sin lectura');
if (!talca.includes('para esta época. Imagen del 14 de septiembre de 2026.')) {
  throw new Error('la lectura simple no dice de cuándo es la imagen: ' + talca);
}
const normal = String(riesgo.htmlSequedad(
  { imagen_en: '2026-09-14', comunas: [{ code: 7101, region: 'Maule', estado: 'normal', anomalia_pct: 122, lectura: 'más verdes' }] },
  { code: 7101, region: 'Maule' },
));
if (normal.includes('satélite · como lo habitual')) throw new Error('normal contradice un +122 %: ' + normal);
if (!normal.includes('qué tan verde se ve el follaje')) throw new Error('sin explicacion');
const i = talca.indexOf('https://modis.gsfc.nasa.gov/data/dataprod/mod13.php');
if (i < 0) throw new Error('sin enlace');
const alrededor = talca.slice(Math.max(0, i - 120), i + 80);
if (alrededor.includes('x-plain') || alrededor.includes('x-tech')) throw new Error('enlace dentro de dual: ' + alrededor);
if (!talca.includes('target="_blank"') || !talca.includes('rel="noopener"')) throw new Error('ancla incompleta');
if (riesgo.htmlSequedad(null, { code: 7101, region: 'Maule' }) !== '') throw new Error('fallo no degrada en silencio');

const region = riesgo.filaSequedad(
  { regiones: paquete.regiones, comunas: [], macrozonas: [] },
  { code: 9999, region: 'Maule' },
);
if (!region || region.nombre !== 'Maule') throw new Error('no cayo a la region');

let pedidos = 0;
const fetchRoto = async () => { pedidos += 1; return { ok: false, status: 500, json: async () => ({}) }; };
await riesgo.pedirSequedad(fetchRoto).catch(() => {});
await riesgo.pedirSequedad(fetchRoto).catch(() => {});
if (pedidos !== 2) throw new Error('cacheo el fallo ' + pedidos);

console.log(JSON.stringify({ ok: true, pedidos }));
"""


def _modulo():
    spec = importlib.util.spec_from_file_location("sequedad_vegetacion", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _paquete() -> dict:
    return json.loads(JSON.read_text(encoding="utf-8"))


def test_json_cabe_y_cita_la_fuente():
    crudo = JSON.read_bytes()
    assert len(crudo) < 8192, f"vegetacion-sequedad.json pesa {len(crudo)} bytes"
    data = _paquete()
    assert data["source"] == FUENTE
    assert data["source_url"] == URL
    assert data["updated_at"]
    assert data["generated_at"]
    assert data["producto"] == "MOD13Q1"
    assert data["imagen_en"]
    assert "cero" in data["metodo"]
    assert len(data["regiones"]) >= 8
    assert len(data["comunas"]) >= 6
    assert len(data["macrozonas"]) >= 4
    assert "\u2014" not in crudo.decode("utf-8")
    # Una macrozona no cuelga de sí una región sin dato: el promedio no la incluyó.
    con_dato = {fila["nombre"] for fila in data["regiones"]}
    for zona in data["macrozonas"]:
        assert set(zona["regiones"]) <= con_dato, zona["nombre"]


def test_cada_lugar_tiene_estado_y_no_inventa_cero():
    data = _paquete()
    codigos = {fila["code"] for fila in json.loads(INDICE.read_text(encoding="utf-8"))}
    vistos = []
    for grupo in ("regiones", "comunas", "macrozonas"):
        for fila in data[grupo]:
            assert fila["estado"] in ESTADOS, fila
            assert isinstance(fila["anomalia_pct"], int), fila
            assert fila["anomalia_pct"] != 0 or fila["estado"] == "normal"
            assert fila["lectura"]
            assert "bosques, matorrales y pastizales" in fila["lectura"]
            vistos.append(fila["anomalia_pct"])
            if "code" in fila:
                assert fila["code"] in codigos
            if "muestra" in fila:
                assert fila["muestra"] in codigos
    assert any(v < 0 for v in vistos) or any(v > 0 for v in vistos)


def test_generador_no_convierte_el_hueco_en_cero():
    mod = _modulo()
    assert mod.anomalia_porcentual(None, [0.5] * 6) is None
    assert mod.anomalia_porcentual(0.4, []) is None
    assert mod.anomalia_porcentual(0.4, [0.01] * 6) is None
    # Una media negativa (agua o nieve) no da un porcentaje que signifique algo.
    assert mod.anomalia_porcentual(0.4, [-0.1] * 6) is None
    assert mod.estado_de(None) is None
    seca = mod.anomalia_porcentual(0.40, [0.50] * 6)
    assert seca == -20
    assert mod.estado_de(seca) == "muy_seca"
    assert mod.estado_de(-8) == "seca"
    assert mod.estado_de(-7) == "normal"
    assert mod.ndvi_util(None, 0) is None
    assert mod.ndvi_util(-3000, 0) is None
    assert mod.ndvi_util(7204, 3) is None
    assert abs(mod.ndvi_util(7204, 0) - 0.7204) < 1e-6
    # Un DN de 1 es suelo desnudo (0,0001), no verdor perfecto.
    assert abs(mod.ndvi_util(1, 0) - 0.0001) < 1e-9
    assert mod.ndvi_util(1, 0) < mod.VERDOR_MINIMO
    assert abs(mod.ndvi_util(0.7204, 0) - 0.7204) < 1e-9
    subset = [
        {"modis_date": "A2026257", "band": "250m_16_days_NDVI", "data": [5000]},
        {"modis_date": "A2026257", "band": "250m_16_days_pixel_reliability", "data": [0]},
    ]
    assert abs(mod.verdor_de_subset(subset, "A2026257") - 0.5) < 1e-6
    assert mod.verdor_de_subset(subset, "A2026241") is None
    assert FUENTE in SCRIPT.read_text(encoding="utf-8")
    assert "vegetacion-sequedad.json" in SCRIPT.read_text(encoding="utf-8")
    assert mod.SALIDA.name == "vegetacion-sequedad.json"


def test_ficha_explica_el_indice_y_no_cachea_el_fallo():
    texto = RIESGO.read_text(encoding="utf-8")
    assert "/web/data/vegetacion-sequedad.json" in texto
    assert URL in texto
    assert 'target="_blank"' in texto and 'rel="noopener"' in texto
    assert "sequedadPromise = null" in texto
    assert "2. Combustible acumulado" in texto
    assert "\u2014" not in texto.split("function htmlSequedad")[1].split("function rainCallout")[0]
    corrida = subprocess.run(
        ["node", "--input-type=module", "-e", _NODE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert corrida.returncode == 0, corrida.stderr or corrida.stdout
    assert json.loads(corrida.stdout)["ok"] is True
