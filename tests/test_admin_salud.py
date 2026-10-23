"""Guardas de la pestaña «Salud» del panel de administración (OPS-29, que
absorbe AUTO-09): el botón y su sección existen con nombre accesible y
encabezado propio, el bloque no trae scripts en línea ni innerHTML, y
/api/status se consulta como GET público —nunca por `call(`, que es el
helper que adjunta `X-Admin-Token`. Solo HTML estático con `html.parser`
y lectura de `admin.js` como texto, igual que `test_accesibilidad_estatica.py`.
"""

from html.parser import HTMLParser

from backend.settings import ROOT

ADMIN = ROOT / "web" / "admin.html"
ADMIN_JS = ROOT / "web" / "js" / "admin.js"


class _Doc(HTMLParser):
    """Botones data-tab, secciones por id y lo que hay dentro de <section id="salud">."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tabs = {}       # data-tab → {"texto", "aria_pressed"}
        self.secciones = {}  # id → atributos
        self._boton = None
        self._en_salud = False
        self.salud = {"scripts": 0, "h2": 0, "ids": set(), "refresh": False}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "button" and a.get("data-tab"):
            self._boton = a["data-tab"]
            self.tabs[self._boton] = {"texto": "", "aria_pressed": a.get("aria-pressed")}
        if tag == "section" and a.get("id"):
            self.secciones[a["id"]] = a
            self._en_salud = a["id"] == "salud"
        if self._en_salud:
            if tag == "script":
                self.salud["scripts"] += 1
            if tag == "h2":
                self.salud["h2"] += 1
            if a.get("id"):
                self.salud["ids"].add(a["id"])
            if "data-refresh" in a:
                self.salud["refresh"] = True

    def handle_endtag(self, tag):
        if tag == "button":
            self._boton = None
        if tag == "section":
            self._en_salud = False

    def handle_data(self, data):
        if self._boton:
            self.tabs[self._boton]["texto"] += data


def _doc():
    doc = _Doc()
    doc.feed(ADMIN.read_text(encoding="utf-8"))
    doc.close()
    return doc


def test_pestana_salud_existe_con_nombre_accesible():
    doc = _doc()
    assert "salud" in doc.tabs, 'admin.html: falta <button data-tab="salud">'
    assert doc.tabs["salud"]["texto"].strip(), "el botón «Salud» no tiene nombre accesible"
    assert doc.tabs["salud"]["aria_pressed"] == "false", "la pestaña sigue el patrón aria-pressed de las demás"
    assert "salud" in doc.secciones, 'admin.html: falta <section id="salud">'
    assert doc.secciones["salud"].get("aria-labelledby"), "la sección «salud» no declara su encabezado"
    assert doc.salud["h2"] == 1, "la sección «salud» debe tener su propio <h2>"


def test_salud_tiene_actualizar_y_ultima_consulta():
    doc = _doc()
    assert doc.salud["refresh"], "falta el botón «Actualizar» (data-refresh)"
    assert "salud-ultima" in doc.salud["ids"], "falta el párrafo de «última consulta»"
    assert "salud-items" in doc.salud["ids"], "falta el contenedor de las tarjetas"


def test_salud_sin_script_en_linea_ni_innerhtml():
    doc = _doc()
    assert doc.salud["scripts"] == 0, "la pestaña «Salud» trae un <script> en línea"
    js = ADMIN_JS.read_text(encoding="utf-8")
    bloque = js[js.index("Pestaña Salud"):]
    if "// Los listeners" in bloque:
        bloque = bloque[: bloque.index("// Los listeners")]
    assert "innerHTML" not in bloque, "la pestaña «Salud» se pinta con textContent, no con innerHTML"


def test_status_es_get_publico_sin_token():
    js = ADMIN_JS.read_text(encoding="utf-8")
    assert "'/api/status'" in js, "admin.js no consulta /api/status"
    assert "call('/api/status'" not in js and 'call("/api/status"' not in js, (
        "/api/status es un GET público: no debe ir por call(, que adjunta X-Admin-Token"
    )
