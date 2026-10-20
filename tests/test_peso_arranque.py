"""Peso del arranque (QA-62): qué descarga el navegador antes de poder
mostrar la app.

Las pruebas de las funciones puras arman un proyecto de juguete en tmp_path;
la última sí mide el web/ real y exige que el arranque quepa en el presupuesto.
"""

from __future__ import annotations

import gzip
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


def test_modulos_arranque_sigue_imports_relativos(tmp_path):
    """Estáticos, from, side-effect e import() dinámico relativo entran;
    lo de vendor y las rutas no relativas quedan fuera."""
    raiz = proyecto(tmp_path)
    mods = peso_arranque.modulos_arranque([raiz / "web/js/app.js"], raiz)
    assert sorted(m.relative_to(raiz).as_posix() for m in mods) == [
        "web/js/a.js",
        "web/js/app.js",
        "web/js/c.js",
        "web/js/lazy.js",
        "web/js/sub/b.js",
    ]


def test_medir_devuelve_gzip_real(tmp_path):
    raiz = proyecto(tmp_path)
    filas = {f["archivo"]: f for f in peso_arranque.medir(raiz)}
    datos = (raiz / "web/css/app.css").read_bytes()
    assert filas["web/css/app.css"]["disco"] == len(datos)
    assert filas["web/css/app.css"]["gzip"] == len(gzip.compress(datos, compresslevel=9, mtime=0))
    # app.js también aparece por el grafo transitivo, sin duplicarse.
    assert "web/js/a.js" in filas


def test_arranque_real_dentro_del_presupuesto(capsys):
    assert peso_arranque.main(["--raiz", str(ROOT)]) == 0
    assert "dentro del presupuesto" in capsys.readouterr().out


FUENTE_TITULOS = "/web/vendor/fonts/anybody-latin-standard-normal.woff2"


def _total_gzip(raiz: Path) -> int:
    return sum(f["gzip"] for f in peso_arranque.medir(raiz))


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
    """El arranque no vive al borde del presupuesto: deja 10 KB libres para
    que la próxima vista no lo cruce (QA-62)."""
    total = _total_gzip(ROOT)
    tope = (peso_arranque.PRESUPUESTO_ARRANQUE_KB - 10) * 1024
    assert total <= tope, f"el arranque mide {total / 1024:.1f} KB gzip y el tope con holgura es {tope / 1024:.0f} KB"


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
    """El número de docs/ARRANQUE.md coincide con el del script."""
    doc = (ROOT / "docs" / "ARRANQUE.md").read_text(encoding="utf-8")
    assert f"{peso_arranque.PRESUPUESTO_ARRANQUE_KB} KB" in doc
