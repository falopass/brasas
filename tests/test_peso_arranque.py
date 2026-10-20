"""Peso del arranque (QA-62): qué descarga el navegador antes de poder
mostrar la app.

Las pruebas de las funciones puras arman un proyecto de juguete en tmp_path;
la última sí mide el web/ real y exige que el arranque quepa en el presupuesto.
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import peso_arranque  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

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


def test_umbral_documentado_en_arranque_md():
    """El número de docs/ARRANQUE.md coincide con el del script."""
    doc = (ROOT / "docs" / "ARRANQUE.md").read_text(encoding="utf-8")
    assert f"{peso_arranque.PRESUPUESTO_ARRANQUE_KB} KB" in doc
