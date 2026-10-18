"""Exploración de solo lectura de servicios públicos (CONAF, SENAPRED, DMC). Uso: python explorar.py <grupo>.

Publica lo encontrado como anotaciones ::notice (GitHub guarda hasta 10 por paso; por eso va en grupos).
"""
import json
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "BRASA-Chile/0.5 (+https://github.com/falopass/brasas)"}
AGOL = "https://www.arcgis.com/sharing/rest"
notes: list[tuple[str, str]] = []


def get(url, n=600_000):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            return r.status, r.headers.get("content-type", ""), r.read(n).decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", 0), "", str(e)[:200]


def getj(url):
    st, _, body = get(url)
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
    head = (f"type={meta.get('type')} owner={meta.get('owner')} org={meta.get('orgId')} access={meta.get('access')} "
            f"modified={meta.get('modified')} license={str(meta.get('licenseInfo'))[:200]} snippet={str(meta.get('snippet'))[:200]}")
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
    return (f"HTTP {st} name={info.get('name')} layers={layers} count={cnt.get('count')} lastEdit={edit} "
            f"copyright={str(info.get('copyrightText'))[:150]} fields={fields} sample={json.dumps(sample, ensure_ascii=False)[:1500]}")


def search(q, num=20):
    _, res = getj(f"{AGOL}/search?" + urllib.parse.urlencode({"q": q, "f": "json", "num": num, "sortField": "modified", "sortOrder": "desc"}))
    res = res if isinstance(res, dict) else {}
    return " ¦ ".join(f"{i.get('type')}|{i.get('title')}|{i.get('owner')}|{i.get('url') or ''}|{i.get('id')}|mod={i.get('modified')}"
                      for i in res.get("results", []))


def explore_item(label, item_id):
    try:
        head, urls, ids = item(item_id)
    except Exception as e:
        note(f"{label} item {item_id}", f"ERROR {e}")
        return [], []
    note(f"{label} item {item_id}", f"{head} :: servicios={urls[:15]} :: itemIds={ids[:15]}")
    return urls, ids


group = sys.argv[1]
BR = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services"
if group == "senapred3":
    # La sección /alertas/ es una aplicación React propia: su API está dentro del paquete main.*.js
    st, ct, page = get("https://senapred.cl/alertas/")
    srcs = re.findall(r'src="([^"]+\.js)"', page)
    note("alertas scripts", str(srcs))
    for src in srcs[:3]:
        url = urllib.parse.urljoin("https://senapred.cl/alertas/", src)
        st, _, js = get(url, 6_000_000)
        urls = sorted(set(re.findall(r'https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9_\-./?=&]*)?', js)))
        paths = sorted(set(re.findall(r'["`](/(?:api|wp-json|alertas|v\d)[A-Za-z0-9_\-./?=&]*)["`]', js)))
        note(f"bundle {src[-40:]}", f"HTTP {st} len={len(js)} :: urls=" + " ¦ ".join(u for u in urls if not re.search(r"w3\.org|reactjs|github|mozilla|fontawesome|googleapis\.com/css", u))[:5000] + f" :: paths={paths[:60]}")
        ctx = [js[max(0, m.start() - 160): m.end() + 160] for m in re.finditer(r"fetch\(|axios|baseURL", js)][:6]
        note(f"fetch en {src[-30:]}", " ¦¦ ".join(ctx)[:5000])
elif group == "senapred2":
    # senapred.cl es una aplicación JS: se buscan las URL de su API dentro de los paquetes de JavaScript
    st, ct, home = get("https://senapred.cl/", 800_000)
    scripts = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', home)))
    note("senapred scripts", f"HTTP {st} :: {scripts[:30]}")
    found = set()
    for src in scripts[:12]:
        url = src if src.startswith("http") else urllib.parse.urljoin("https://senapred.cl/", src)
        _, _, js = get(url, 3_000_000)
        found |= set(re.findall(r'https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9_\-./]*)?', js))
    interesting = sorted(u for u in found if re.search(r"api|alert|arcgis|senapred|onemi|gob\.cl", u, re.I))
    note("senapred urls en JS", " ¦ ".join(interesting)[:7000])
    st, ct, body = get("https://senapred.cl/alertas/")
    note("senapred /alertas", f"HTTP {st} {ct} :: {body[:1900]}")
    for org in ("dxNWeb35zWPRjaNL", "A1ELWse9bRAi2JiV"):
        _, info = getj(f"{AGOL}/portals/{org}?f=json")
        note(f"org {org}", f"name={info.get('name')} urlKey={info.get('urlKey')} desc={str(info.get('description'))[:300]}")
    note("Admagolin items", search("owner:Admagolin", 30)[:5000])
elif group == "boton2":
    # Botón Rojo oficial: fechas disponibles, licencia completa y capas de pronóstico (PI, HC, VV, HR, TP)
    q = urllib.parse.urlencode({"where": "1=1", "outFields": "date", "returnDistinctValues": "true", "returnGeometry": "false", "f": "json"})
    _, d = getj(f"{BR}/Boton_Rojo/FeatureServer/0/query?{q}")
    note("BR fechas", json.dumps(d, ensure_ascii=False)[:1500])
    _, meta = getj(f"{AGOL}/content/items/2307e3ab30ba49d7b2f4bbc97c0d433b?f=json")
    note("BR licencia", f"license={meta.get('licenseInfo')} :: accessInfo={meta.get('accessInformation')} :: desc={str(meta.get('description'))[:1200]}")
    q = urllib.parse.urlencode({"where": "com_id=5109", "outFields": "*", "returnGeometry": "false", "f": "json"})
    _, v = getj(f"{BR}/Boton_Rojo/FeatureServer/0/query?{q}")
    note("BR Viña", json.dumps([f.get("attributes") for f in v.get("features", [])], ensure_ascii=False)[:2500])
    for name in ("PI", "HC", "VV"):
        note(f"capa {name}", safe(layer, f"{BR}/{name}/FeatureServer/0"))
    _, meta = getj(f"{AGOL}/content/items/8f3e06ddfd4a40edacb0b96052653ca0?f=json")
    note("PI item", f"snippet={meta.get('snippet')} :: desc={str(meta.get('description'))[:1500]}")
elif group == "boton":
    # CONAF Botón Rojo (owner deigeprif): mapas base y tableros → capas reales
    seen = []
    for label, iid in [("BR mapa", "ac259f64e18447a1b70a54e6419e4d36"), ("BR mapa2", "889d0a3828024df2b0d9e6ed22053f96"),
                       ("BR tablero", "41ee3c691359437aa9df2a09d7f6124e"), ("FIRMS tablero", "b8fc5f97527345d0aa8e958df28ac581")]:
        urls, _ = explore_item(label, iid)
        seen += urls
    for url in list(dict.fromkeys(seen))[:5]:
        note(f"capa {url[-90:]}", safe(layer, url))
    note("deigeprif items", search("owner:deigeprif", 40)[:6000])
elif group == "senapred":
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
elif group == "dmc":
    base = "https://services3.arcgis.com/aSoEm9TBK2shtWjP/arcgis/rest/services/DMC_CAP_Boletines/FeatureServer"
    note("DMC CAP FS", safe(layer, base))
    note("DMC CAP capa 0", safe(layer, base + "/0"))
    note("if_temporadas", safe(layer, "https://services3.arcgis.com/DmlBJVTrQbCmoXcR/arcgis/rest/services/if_temporadas_2010_2024_t/FeatureServer/0"))
    note("riesgo interfaz", safe(layer, "https://services6.arcgis.com/LCdFQd7nnAn5xeUA/arcgis/rest/services/Riesgo_IF_Interfaz_Nacional/FeatureServer/0"))
    for q in ["incendios en curso conaf", "focos activos chile", "sidco conaf", "incendio forestal activo region"]:
        note(f"busqueda «{q}»", search(q, 15)[:5000])
elif group == "web":
    pat = re.compile(r"https?://[^\s\"'<>]+?(?:FeatureServer|MapServer|/rest/services|\.geojson|/feed|/api/|wp-json|arcgis|dashboards|alerta)[^\s\"'<>]*", re.I)
    for url in ["https://senapred.cl/", "https://senapred.cl/alertas/", "https://senapred.cl/wp-json/",
                "https://senapred.cl/wp-json/wp/v2/types", "https://senapred.cl/feed/", "https://www.conaf.cl/wp-json/wp/v2/types",
                "https://www.conaf.cl/wp-json/wp/v2/pages?search=incendios&per_page=10&_fields=link,modified,title",
                "https://sidco.conaf.cl/", "https://www.conaf.cl/situacion-incendios-forestales/"]:
        st, ct, body = get(url)
        links = sorted(set(pat.findall(body)))[:40]
        names = re.findall(r'"(?:namespaces|slug|rest_base)":\s*("[^"]+"|\[[^\]]*\])', body)[:40]
        note(f"{st} {url}", f"type={ct} len={len(body)} :: claves={names} :: enlaces=" + " ¦ ".join(links)[:4500])

for title, msg in notes[:10]:
    print(f"== {title}\n{msg}\n")
    clean = msg.replace("%", "%25").replace("\r", " ").replace("\n", " ")
    print(f"::notice title={title[:120].replace(',', ' ').replace(':', ' ')}::{clean}")
