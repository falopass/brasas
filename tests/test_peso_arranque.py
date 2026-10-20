"""Peso del arranque (QA-62): qué descarga el navegador antes de poder
mostrar la app.

Las pruebas de las funciones puras arman un proyecto de juguete en tmp_path;
las del final miden el web/ real y exigen que el arranque quepa en el presupuesto.
"""

from __future__ import annotations

import gzip
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import peso_arranque  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FUENTE_TITULOS = "/web/vendor/fonts/anybody-latin-standard-normal.woff2"

HTML_JUGUETE = """<!doctype html>
<html><head>
  <link rel="preload" href="/web/vendor/fonts/a.woff2" as="font" crossorigin />
  <link rel="stylesheet" href="/web/vendor/lib/lib.css" />
  <link rel="stylesheet" href="/web/css/app.css" />
  <link rel="manifest" href="/manifest.webmanifest" />
  <script type="module" src="/web/js/app.js"></script>
  <script src="/web/js/viejo.js"></script>
  <script type="module">import './inline.js';</script>
  <link rel="stylesheet" href="https://cdn.example.com/x.css" />
</head></html>
"""


def proyecto(tmp_path: Path) -> Path:
    archivos = {
        "web/index.html": HTML_JUGUETE,
        "web/css/app.css": b"body{}",
        "web/vendor/lib/lib.css": b".x{}",
        "web/vendor/fonts/a.woff2": b"w0f2",
        "web/js/app.js": b"import './a.js';\nimport { x } from './sub/b.js';\nconst m = import('./lazy.js');",
        "web/js/a.js": b"export const a = 1;",
        "web/js/sub/b.js": b"import '../c.js';\nexport const x = 1;",
        "web/js/c.js": b"import '/web/js/vendor/falso.js';",  # no es relativo: se ignora
        "web/js/lazy.js": b"export default {};",
        "web/js/vendor/falso.js": b"x",
        "manifest.webmanifest": b"{}",
    }
    for rel, datos in archivos.items():
        ruta = tmp_path / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(datos, str):
            datos = datos.encode()
        ruta.write_bytes(datos)
    return tmp_path


def test_referencias_html_extrae_lo_que_bloquea(tmp_path):
    """La portada, los CSS, las fuentes precargadas y el script module;
    ni el manifest, ni el script clásico, ni el inline, ni el CDN."""
    raiz = proyecto(tmp_path)
    refs = peso_arranque.referencias_html(raiz / "web" / "index.html", raiz)
    assert [(g, r.relative_to(raiz).as_posix()) for g, r in refs] == [
        ("html", "web/index.html"),
        ("css", "web/vendor/lib/lib.css"),
        ("css", "web/css/app.css"),
        ("fuente", "web/vendor/fonts/a.woff2"),
        ("js", "web/js/app.js"),
    ]


def test_modulos_arranque_solo_sigue_estaticos(tmp_path):
    """Los estáticos, from y side-effect entran; el import() dinámico no
    bloquea el arranque. Lo de vendor y las rutas no relativas quedan fuera."""
    raiz = proyecto(tmp_path)
    mods = peso_arranque.modulos_arranque([raiz / "web/js/app.js"], raiz)
    assert sorted(m.relative_to(raiz).as_posix() for m in mods) == [
        "web/js/a.js",
        "web/js/app.js",
        "web/js/c.js",
        "web/js/sub/b.js",
    ]


def test_modulos_diferidos_son_los_del_import_dinamico(tmp_path):
    """lazy.js solo se alcanza con import(): va a la sección diferida."""
    raiz = proyecto(tmp_path)
    mods = peso_arranque.modulos_diferidos([raiz / "web/js/app.js"], raiz)
    assert sorted(m.relative_to(raiz).as_posix() for m in mods) == ["web/js/lazy.js"]


def test_medir_devuelve_gzip_real(tmp_path):
    raiz = proyecto(tmp_path)
    filas = {f["archivo"]: f for f in peso_arranque.medir(raiz)}
    datos = (raiz / "web/css/app.css").read_bytes()
    assert filas["web/css/app.css"]["disco"] == len(datos)
    assert filas["web/css/app.css"]["gzip"] == len(gzip.compress(datos, compresslevel=9, mtime=0))
    # app.js también aparece por el grafo transitivo, sin duplicarse.
    assert "web/js/a.js" in filas


def test_medir_separa_bloqueante_y_diferido(tmp_path):
    """lazy.js no suma al bloqueante, pero sí al total."""
    raiz = proyecto(tmp_path)
    filas = peso_arranque.medir(raiz)
    bloqueante = [f for f in filas if f["seccion"] == "bloqueante"]
    diferido = [f for f in filas if f["seccion"] == "diferido"]
    assert "web/js/lazy.js" not in {f["archivo"] for f in bloqueante}
    assert "web/js/lazy.js" in {f["archivo"] for f in diferido}
    assert "web/js/lazy.js" in {f["archivo"] for f in filas}
    assert sum(f["gzip"] for f in filas) == sum(f["gzip"] for f in bloqueante + diferido)


def test_informe_y_json_muestran_lo_diferido(tmp_path, capsys):
    raiz = proyecto(tmp_path)
    assert peso_arranque.main(["--raiz", str(raiz), "--informe"]) == 0
    assert "DIFERIDO" in capsys.readouterr().out
    assert peso_arranque.main(["--raiz", str(raiz), "--json"]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos["bloqueante_gzip"] + datos["diferido_gzip"] == datos["total_gzip"]
    assert any(f["archivo"] == "web/js/lazy.js" for f in datos["diferido"])


def test_pagina_bajo_demanda_no_entra_al_arranque(tmp_path):
    """Una página que no se abre desde index.html no suma al arranque: su peso
    se mide aparte, en presupuesto_peso.py (DEBT-07)."""
    raiz = proyecto(tmp_path)
    antes = sum(f["gzip"] for f in peso_arranque.medir(raiz))
    (raiz / "web/lite.html").write_text("<html></html>", encoding="utf-8")
    (raiz / "web/js/lite.js").write_bytes(b"x" * 5000)
    assert sum(f["gzip"] for f in peso_arranque.medir(raiz)) == antes


def test_exceso_nombra_el_archivo_mas_pesado(tmp_path, monkeypatch, capsys):
    raiz = proyecto(tmp_path)
    (raiz / "web/js/gordo.js").write_bytes(random.Random(20261020).randbytes(5000).hex().encode())
    app = raiz / "web/js/app.js"
    app.write_text(app.read_text(encoding="utf-8") + "\nimport './gordo.js';", encoding="utf-8")
    monkeypatch.setattr(peso_arranque, "PRESUPUESTO_ARRANQUE_KB", 1)
    assert peso_arranque.main(["--raiz", str(raiz)]) == 1
    salida = capsys.readouterr().out
    assert "Peso del arranque excedido" in salida
    assert "el archivo más pesado es web/js/gordo.js" in salida


def test_arranque_real_dentro_del_presupuesto(capsys):
    assert peso_arranque.main(["--raiz", str(ROOT)]) == 0
    assert "dentro del presupuesto" in capsys.readouterr().out


def test_arranque_real_separa_bloqueante_y_total():
    """El bloqueante cabe en 180 KB, el total en 300 KB y las vistas sin
    dependencia estática de la portada quedan en la sección diferida."""
    filas = peso_arranque.medir(ROOT)
    bloqueante = sum(f["gzip"] for f in filas if f["seccion"] == "bloqueante")
    total = sum(f["gzip"] for f in filas)
    diferido = {f["archivo"] for f in filas if f["seccion"] == "diferido"}
    assert bloqueante <= peso_arranque.PRESUPUESTO_ARRANQUE_KB * 1024
    assert total <= peso_arranque.PRESUPUESTO_TOTAL_KB * 1024
    assert "web/js/views/zona.js" not in diferido
    vistas = {
        f"web/js/views/{nombre}.js"
        for nombre in (
            "mapa",
            "riesgo",
            "alertas",
            "casos",
            "temporada",
            "preparate",
            "vecino",
            "privacidad",
            "calidad",
            "quehago",
        )
    }
    assert vistas <= diferido
    # incendio.js sigue en el bloqueante porque zona.js importa INCIDENT de ahí;
    # el router igual lo pide con import(), pero el navegador ya lo tiene.
    assert "web/js/views/incendio.js" not in diferido


def _precargas_fuente(html: str) -> list[str]:
    """<link rel="preload" as="font">: las fuentes que bloquean el arranque."""
    return [
        tag
        for tag in re.findall(r"<link\b[^>]*>", html, re.I)
        if re.search(r'rel=["\']preload["\']', tag, re.I) and re.search(r'as=["\']font["\']', tag, re.I)
    ]


def _font_faces(css: str) -> dict[str, str]:
    """{ruta del .woff2: bloque @font-face} declarado en el CSS."""
    caras = {}
    for bloque in re.findall(r"@font-face\s*\{(.*?)\}", css, re.S):
        url = re.search(r'url\(["\']?([^"\')]+\.woff2)', bloque)
        if url:
            caras[url.group(1)] = bloque
    return caras


def test_arranque_real_con_diez_kb_de_holgura():
    """El arranque bloqueante no vive al borde del presupuesto: deja 10 KB
    libres para que la próxima vista no lo cruce (QA-62)."""
    bloqueante = sum(f["gzip"] for f in peso_arranque.medir(ROOT) if f["seccion"] == "bloqueante")
    tope = (peso_arranque.PRESUPUESTO_ARRANQUE_KB - 10) * 1024
    assert bloqueante <= tope, f"el arranque bloqueante mide {bloqueante / 1024:.1f} KB gzip y el tope con holgura es {tope / 1024:.0f} KB"


def test_index_precarga_como_maximo_una_fuente():
    """Solo la tipografía del texto corrido bloquea el arranque; la de títulos
    se descarga después del primer pintado."""
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    precargas = _precargas_fuente(html)
    assert len(precargas) <= 1, f"web/index.html precarga {len(precargas)} fuentes: {precargas}"


def test_fuentes_del_html_declaradas_en_css_con_swap():
    """Cada .woff2 que nombra index.html existe en app.css y su @font-face
    pinta el texto con la de respaldo mientras llega (font-display: swap)."""
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    caras = _font_faces((ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8"))
    referencias = set(re.findall(r'href=["\']([^"\']+\.woff2)["\']', html, re.I))
    assert referencias, "web/index.html no referencia ninguna fuente"
    for ruta in sorted(referencias):
        assert ruta in caras, f"{ruta} no está declarada en web/css/app.css"
        assert re.search(r"font-display\s*:\s*swap", caras[ruta]), f"{ruta}: @font-face sin font-display: swap"


def test_fuente_de_titulos_sigue_en_el_frontend_sin_bloquear():
    """La de títulos no se borra ni se mueve: sigue en web/vendor/fonts y
    declarada en app.css, solo deja de contar en el arranque."""
    assert (ROOT / FUENTE_TITULOS.lstrip("/")).is_file(), f"falta {FUENTE_TITULOS}"
    caras = _font_faces((ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8"))
    assert FUENTE_TITULOS in caras, f"{FUENTE_TITULOS} ya no está declarada en web/css/app.css"
    arranque = {f["archivo"] for f in peso_arranque.medir(ROOT)}
    assert FUENTE_TITULOS.lstrip("/") not in arranque, f"{FUENTE_TITULOS} sigue bloqueando el arranque"


def test_umbral_documentado_en_arranque_md():
    """Los dos números de docs/ARRANQUE.md coinciden con los del script."""
    doc = (ROOT / "docs" / "ARRANQUE.md").read_text(encoding="utf-8")
    assert f"{peso_arranque.PRESUPUESTO_ARRANQUE_KB} KB" in doc
    assert f"{peso_arranque.PRESUPUESTO_TOTAL_KB} KB" in doc


def test_presupuesto_del_arranque_pasa_en_el_repo_real():
    """FUSION-01: el guion que `dev.py check` exige queda en verde con el web/ actual."""
    assert peso_arranque.main([]) == 0


def test_dev_check_corre_el_presupuesto_del_arranque():
    """El check del repo mide el arranque bloqueante, no solo el peso total del frontend."""
    assert "peso_arranque.py" in (ROOT / "dev.py").read_text(encoding="utf-8")
