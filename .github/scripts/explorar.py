"""Exploración de solo lectura de servicios públicos (CONAF, SENAPRED, DMC). Uso: python explorar.py <grupo>.

Cada grupo recorre sus URLs con `sonda()`, que registra {grupo, url, status, content_type, bytes, veredicto}
y deja `explorar-<grupo>.json` junto a este script, con la fecha UTC y el resumen {ok, dudoso, caido, total}.
Veredicto por sonda: `ok`; `dudoso` si respondió 200 pero vacío o sin lo esperado; `caido` si no hubo
respuesta o fue 4xx/5xx. Código de salida: 0 si al menos una sonda del grupo quedó `ok`, 2 si todas
quedaron `caido` (fuente entera abajo).

También publica anotaciones: ::warning por cada sonda que no quedó `ok`, con su URL, y ::notice con las
notas de la exploración. GitHub corta en 10 anotaciones por paso; el JSON es el registro durable.

La red ocurre solo dentro de main(): importar el módulo no hace ninguna llamada.
"""

import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "BRASA-Chile/0.5 (+https://github.com/falopass/brasas)"}
AGOL = "https://www.arcgis.com/sharing/rest"
BR = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services"
SALIDA = Path(__file__).resolve().parent
notes: list[tuple[str, str]] = []
_sondas: list[dict] = []
_grupo = ""

# Parámetros de URL que nunca se escriben en el JSON: es público y va como artefacto del run.
_SECRETO = re.compile(r"(?i)(token|key|secret|passw|auth|signature)")


def get(url, n=600_000):
    """Sonda cruda: (status, content-type, cuerpo). Sin registro y sin red al importar."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            return r.status, r.headers.get("content-type", ""), r.read(n).decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", 0), "", str(e)[:200]


def _limpia(url):
    """URL sin credenciales ni parámetros sensibles; el resto queda tal cual."""
    p = urllib.parse.urlsplit(url)
    pares = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    limpios = [(k, v) for k, v in pares if not _SECRETO.search(k)]
    query = p.query if len(limpios) == len(pares) else urllib.parse.urlencode(limpios)
    return urllib.parse.urlunsplit((p.scheme, p.netloc.rsplit("@", 1)[-1], p.path, query, ""))


def _json(body):
    """El cuerpo como JSON, o None si no lo es."""
    try:
        return json.loads(body)
    except ValueError:
        return None


def _xml(body):
    """El cuerpo como XML que no sea una página HTML (una página de error con 200 no sirve)."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return False
    return root.tag.rsplit("}", 1)[-1].lower() not in ("html", "body")


def veredicto(url, status, body, n=600_000):
    """`ok`, `dudoso` (respondió 200 pero vacío o sin lo esperado) o `caido` (sin respuesta o 4xx/5xx)."""
    if not status or status >= 400:
        return "caido"
    if not body.strip():
        return "dudoso"
    if len(body.encode("utf-8", "replace")) >= n:
        return "ok"  # truncado: no se puede juzgar el contenido
    base = url.split("?", 1)[0]
    if "f=json" in url or "/wp-json/" in url or base.endswith(".json"):
        data = _json(body)
        # ArcGIS contesta 200 con {"error": ...} cuando la capa se movió.
        if data is None or (isinstance(data, dict) and data.get("error")):
            return "dudoso"
    if base.endswith(".xml") and not _xml(body):
        return "dudoso"
    return "ok"


def sonda(url, n=600_000):
    """Como get(), pero anota la sonda y su veredicto para el JSON del grupo."""
    status, ct, body = get(url, n)
    _sondas.append(
        {
            "grupo": _grupo,
            "url": _limpia(url),
            "status": status,
            "content_type": ct,
            "bytes": len(body.encode("utf-8", "replace")) if status and status < 400 else 0,
            "veredicto": veredicto(url, status, body, n),
        }
    )
    return status, ct, body


def getj(url):
    st, _, body = sonda(url)
    try:
        return st, json.loads(body)
    except Exception:
        return st, {"_raw": body[:300]}


def note(title, msg):
    notes.append((title, msg))


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # una capa rara no debe cortar la exploración
        return f"ERROR {type(e).__name__}: {e}"[:300]


def item(item_id):
    _, meta = getj(f"{AGOL}/content/items/{item_id}?f=json")
    _, data = getj(f"{AGOL}/content/items/{item_id}/data?f=json")
    head = (
        f"type={meta.get('type')} owner={meta.get('owner')} org={meta.get('orgId')} access={meta.get('access')} "
        f"modified={meta.get('modified')} license={str(meta.get('licenseInfo'))[:200]} snippet={str(meta.get('snippet'))[:200]}"
    )
    urls = sorted(set(re.findall(r'https?://[^"\s]+?(?:FeatureServer|MapServer)(?:/\d+)?', json.dumps(data))))
    ids = sorted(set(re.findall(r'"itemId":\s*"([0-9a-f]{32})"', json.dumps(data))))
    return head, urls, ids


def layer(url):
    st, info = getj(f"{url}?f=json")
    fields = [f.get("name") for f in info.get("fields", [])][:40]
    edit = (info.get("editingInfo") or {}).get("lastEditDate")
    q = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "resultRecordCount": 2, "f": "json", "returnGeometry": "false"})
    _, rows = getj(f"{url}/query?{q}")
    _, cnt = getj(f"{url}/query?where=1%3D1&returnCountOnly=true&f=json")
    cnt = cnt if isinstance(cnt, dict) else {}
    info = info if isinstance(info, dict) else {}
    feats = rows.get("features", []) if isinstance(rows, dict) else []
    sample = [r.get("attributes") for r in feats][:2]
    layers = [f"{l.get('id')}:{l.get('name')}" for l in info.get("layers", [])][:30]
    return (
        f"HTTP {st} name={info.get('name')} layers={layers} count={cnt.get('count')} lastEdit={edit} "
        f"copyright={str(info.get('copyrightText'))[:150]} fields={fields} sample={json.dumps(sample, ensure_ascii=False)[:1500]}"
    )


def search(q, num=20):
    _, res = getj(
        f"{AGOL}/search?" + urllib.parse.urlencode({"q": q, "f": "json", "num": num, "sortField": "modified", "sortOrder": "desc"})
    )
    res = res if isinstance(res, dict) else {}
    return " ¦ ".join(
        f"{i.get('type')}|{i.get('title')}|{i.get('owner')}|{i.get('url') or ''}|{i.get('id')}|mod={i.get('modified')}"
        for i in res.get("results", [])
    )


def explore_item(label, item_id):
    try:
        head, urls, ids = item(item_id)
    except Exception as e:
        note(f"{label} item {item_id}", f"ERROR {e}")
        return [], []
    note(f"{label} item {item_id}", f"{head} :: servicios={urls[:15]} :: itemIds={ids[:15]}")
    return urls, ids


def grupo_dmc2():
    # DMC: índice RSS de avisos/alertas/alarmas y un CAP de ejemplo
    for url in [
        "https://archivos.meteochile.gob.cl/portaldmc/rss/",
        "https://www.meteochile.gob.cl/PortalDMC-web/index.xhtml",
        "https://www.meteochile.gob.cl/PortalDMC-web/pronosticos/avisos.xhtml",
        "https://archivos.meteochile.gob.cl/portaldmc/rss/meteochile_A567_2026_cap.xml",
    ]:
        st, ct, body = sonda(url)
        links = sorted(set(re.findall(r'https?://[^\s"\'<>]*(?:rss|cap|xml|feed)[^\s"\'<>]*', body, re.I)))[:40]
        rel = sorted(set(re.findall(r'(?:href|src)="([^"]*(?:rss|\.xml|cap)[^"]*)"', body, re.I)))[:40]
        note(
            f"{st} {url[-70:]}",
            f"type={ct} len={len(body)} :: links={links} :: rel={rel} :: head={body[:1200] if 'xml' in ct or url.endswith('.xml') else ''}",
        )
    note(
        "SIDCO FS",
        safe(layer, "https://services3.arcgis.com/aSoEm9TBK2shtWjP/arcgis/rest/services/IncendiosForestales_SIDCO_CONAF/FeatureServer/0"),
    )
    _, meta = getj(f"{AGOL}/content/items/034e292731694e96b6ac17fd1579ef16?f=json")
    note(
        "SIDCO item",
        f"owner={meta.get('owner')} org={meta.get('orgId')} snippet={meta.get('snippet')} desc={str(meta.get('description'))[:800]} license={str(meta.get('licenseInfo'))[:300]}",
    )
    _, org = getj(f"{AGOL}/portals/aSoEm9TBK2shtWjP?f=json")
    note("org aSoEm9TBK2shtWjP", f"name={org.get('name')} urlKey={org.get('urlKey')}")


def grupo_senapred3():
    # La sección /alertas/ es una aplicación React propia: su API está dentro del paquete main.*.js
    st, ct, page = sonda("https://senapred.cl/alertas/")
    srcs = re.findall(r'src="([^"]+\.js)"', page)
    note("alertas scripts", str(srcs))
    for src in srcs[:3]:
        url = urllib.parse.urljoin("https://senapred.cl/alertas/", src)
        st, _, js = sonda(url, 6_000_000)
        urls = sorted(set(re.findall(r"https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9_\-./?=&]*)?", js)))
        paths = sorted(set(re.findall(r'["`](/(?:api|wp-json|alertas|v\d)[A-Za-z0-9_\-./?=&]*)["`]', js)))
        note(
            f"bundle {src[-40:]}",
            f"HTTP {st} len={len(js)} :: urls="
            + " ¦ ".join(u for u in urls if not re.search(r"w3\.org|reactjs|github|mozilla|fontawesome|googleapis\.com/css", u))[:5000]
            + f" :: paths={paths[:60]}",
        )
        ctx = [js[max(0, m.start() - 160) : m.end() + 160] for m in re.finditer(r"fetch\(|axios|baseURL", js)][:6]
        note(f"fetch en {src[-30:]}", " ¦¦ ".join(ctx)[:5000])


def grupo_senapred2():
    # senapred.cl es una aplicación JS: se buscan las URL de su API dentro de los paquetes de JavaScript
    st, ct, home = sonda("https://senapred.cl/", 800_000)
    scripts = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', home)))
    note("senapred scripts", f"HTTP {st} :: {scripts[:30]}")
    found = set()
    for src in scripts[:12]:
        url = src if src.startswith("http") else urllib.parse.urljoin("https://senapred.cl/", src)
        _, _, js = sonda(url, 3_000_000)
        found |= set(re.findall(r"https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9_\-./]*)?", js))
    interesting = sorted(u for u in found if re.search(r"api|alert|arcgis|senapred|onemi|gob\.cl", u, re.I))
    note("senapred urls en JS", " ¦ ".join(interesting)[:7000])
    st, ct, body = sonda("https://senapred.cl/alertas/")
    note("senapred /alertas", f"HTTP {st} {ct} :: {body[:1900]}")
    for org in ("dxNWeb35zWPRjaNL", "A1ELWse9bRAi2JiV"):
        _, info = getj(f"{AGOL}/portals/{org}?f=json")
        note(f"org {org}", f"name={info.get('name')} urlKey={info.get('urlKey')} desc={str(info.get('description'))[:300]}")
    note("Admagolin items", search("owner:Admagolin", 30)[:5000])


def grupo_boton2():
    # Botón Rojo oficial: fechas disponibles, licencia completa y capas de pronóstico (PI, HC, VV, HR, TP)
    q = urllib.parse.urlencode(
        {"where": "1=1", "outFields": "date", "returnDistinctValues": "true", "returnGeometry": "false", "f": "json"}
    )
    _, d = getj(f"{BR}/Boton_Rojo/FeatureServer/0/query?{q}")
    note("BR fechas", json.dumps(d, ensure_ascii=False)[:1500])
    _, meta = getj(f"{AGOL}/content/items/2307e3ab30ba49d7b2f4bbc97c0d433b?f=json")
    note(
        "BR licencia",
        f"license={meta.get('licenseInfo')} :: accessInfo={meta.get('accessInformation')} :: desc={str(meta.get('description'))[:1200]}",
    )
    q = urllib.parse.urlencode({"where": "com_id=5109", "outFields": "*", "returnGeometry": "false", "f": "json"})
    _, v = getj(f"{BR}/Boton_Rojo/FeatureServer/0/query?{q}")
    note("BR Viña", json.dumps([f.get("attributes") for f in v.get("features", [])], ensure_ascii=False)[:2500])
    for name in ("PI", "HC", "VV"):
        note(f"capa {name}", safe(layer, f"{BR}/{name}/FeatureServer/0"))
    _, meta = getj(f"{AGOL}/content/items/8f3e06ddfd4a40edacb0b96052653ca0?f=json")
    note("PI item", f"snippet={meta.get('snippet')} :: desc={str(meta.get('description'))[:1500]}")


def grupo_boton():
    # CONAF Botón Rojo (owner deigeprif): mapas base y tableros → capas reales
    seen = []
    for label, iid in [
        ("BR mapa", "ac259f64e18447a1b70a54e6419e4d36"),
        ("BR mapa2", "889d0a3828024df2b0d9e6ed22053f96"),
        ("BR tablero", "41ee3c691359437aa9df2a09d7f6124e"),
        ("FIRMS tablero", "b8fc5f97527345d0aa8e958df28ac581"),
    ]:
        urls, _ = explore_item(label, iid)
        seen += urls
    for url in list(dict.fromkeys(seen))[:5]:
        note(f"capa {url[-90:]}", safe(layer, url))
    note("deigeprif items", search("owner:deigeprif", 40)[:6000])


def grupo_senapred():
    base = "https://services6.arcgis.com/dxNWeb35zWPRjaNL/arcgis/rest/services/SENAPRED_-_Alertas_vigentes_por_region_(vista)/FeatureServer"
    explore_item("alertas vigentes", "c56c291657924f709b3c1e61e804d70d")
    note("alertas vigentes FS", safe(layer, base))
    note("alertas vigentes capa 0", safe(layer, base + "/0"))
    urls, _ = explore_item("MINSAL tablero alertas", "bdc345e01e324af490800634d0f0e3a5")
    explore_item("MINSAL tablero 2", "b71b567aff804dee98a692c091dc9276")
    for url in urls[:2]:
        note(f"capa {url[-90:]}", safe(layer, url))
    note("busqueda alertas", search("senapred alerta vigente comuna", 20)[:6000])
    note("busqueda geoportal", search("owner:geoportalonemi OR owner:ntapia_geoportalonemi alerta", 20)[:6000])


def grupo_dmc():
    base = "https://services3.arcgis.com/aSoEm9TBK2shtWjP/arcgis/rest/services/DMC_CAP_Boletines/FeatureServer"
    note("DMC CAP FS", safe(layer, base))
    note("DMC CAP capa 0", safe(layer, base + "/0"))
    note(
        "if_temporadas",
        safe(layer, "https://services3.arcgis.com/DmlBJVTrQbCmoXcR/arcgis/rest/services/if_temporadas_2010_2024_t/FeatureServer/0"),
    )
    note(
        "riesgo interfaz",
        safe(layer, "https://services6.arcgis.com/LCdFQd7nnAn5xeUA/arcgis/rest/services/Riesgo_IF_Interfaz_Nacional/FeatureServer/0"),
    )
    for q in ["incendios en curso conaf", "focos activos chile", "sidco conaf", "incendio forestal activo region"]:
        note(f"busqueda «{q}»", search(q, 15)[:5000])


def grupo_web():
    pat = re.compile(
        r"https?://[^\s\"'<>]+?(?:FeatureServer|MapServer|/rest/services|\.geojson|/feed|/api/|wp-json|arcgis|dashboards|alerta)[^\s\"'<>]*",
        re.I,
    )
    for url in [
        "https://senapred.cl/",
        "https://senapred.cl/alertas/",
        "https://senapred.cl/wp-json/",
        "https://senapred.cl/wp-json/wp/v2/types",
        "https://senapred.cl/feed/",
        "https://www.conaf.cl/wp-json/wp/v2/types",
        "https://www.conaf.cl/wp-json/wp/v2/pages?search=incendios&per_page=10&_fields=link,modified,title",
        "https://sidco.conaf.cl/",
        "https://www.conaf.cl/situacion-incendios-forestales/",
    ]:
        st, ct, body = sonda(url)
        links = sorted(set(pat.findall(body)))[:40]
        names = re.findall(r'"(?:namespaces|slug|rest_base)":\s*("[^"]+"|\[[^\]]*\])', body)[:40]
        note(f"{st} {url}", f"type={ct} len={len(body)} :: claves={names} :: enlaces=" + " ¦ ".join(links)[:4500])


GRUPOS = {
    "boton2": grupo_boton2,
    "dmc2": grupo_dmc2,
    "dmc": grupo_dmc,
    "web": grupo_web,
    "boton": grupo_boton,
    "senapred": grupo_senapred,
    "senapred2": grupo_senapred2,
    "senapred3": grupo_senapred3,
}


def veredicto_grupo(sondas):
    """`ok` si todas quedaron ok, `caido` si ninguna respondió y `dudoso` en el resto."""
    vs = [s["veredicto"] for s in sondas]
    if vs and all(v == "ok" for v in vs):
        return "ok"
    if not vs or all(v == "caido" for v in vs):
        return "caido"
    return "dudoso"


def _esc(texto):
    """Escapa el texto para una anotación de GitHub Actions."""
    return texto.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def publicar(sondas):
    """Anotaciones del run: cada sonda que no quedó ok, y las notas de la exploración."""
    for s in sondas:
        if s["veredicto"] != "ok":
            print(f"::warning title={s['grupo']} {s['veredicto']}::{_esc(s['url'])} HTTP {s['status']} {s['content_type']}")
    for title, msg in notes[:10]:
        print(f"== {title}\n{msg}\n")
        print(f"::notice title={_esc(title[:120].replace(',', ' ').replace(':', ' '))}::{_esc(msg)}")


def escribir(grupo, sondas):
    """Deja explorar-<grupo>.json con fecha UTC, veredicto del grupo y resumen."""
    resumen = {v: sum(1 for s in sondas if s["veredicto"] == v) for v in ("ok", "dudoso", "caido")}
    resumen["total"] = len(sondas)
    veredicto_actual = veredicto_grupo(sondas)
    datos = {
        "grupo": grupo,
        "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "veredicto": veredicto_actual,
        "resumen": resumen,
        "sondas": sondas,
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / f"explorar-{grupo}.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return ruta, veredicto_actual


def main(argv=None):
    global _grupo
    argv = sys.argv[1:] if argv is None else argv
    grupo = argv[0] if argv else ""
    if grupo not in GRUPOS:
        print(f"grupo desconocido: {grupo or '(ninguno)'}. Grupos: {', '.join(GRUPOS)}", file=sys.stderr)
        return 1
    _grupo = grupo
    _sondas.clear()
    notes.clear()
    GRUPOS[grupo]()
    ruta, veredicto_actual = escribir(grupo, _sondas)
    publicar(_sondas)
    print(f"{grupo}: {veredicto_actual} {ruta.name}")
    return 2 if veredicto_actual == "caido" else 0


if __name__ == "__main__":
    sys.exit(main())
