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
    sample = [r.get("attributes") for r in rows.get("features", [])][:2]
    layers = [f"{l.get('id')}:{l.get('name')}" for l in info.get("layers", [])][:30]
    return (f"HTTP {st} name={info.get('name')} layers={layers} count={cnt.get('count')} lastEdit={edit} "
            f"copyright={str(info.get('copyrightText'))[:150]} fields={fields} sample={json.dumps(sample, ensure_ascii=False)[:1500]}")


def search(q, num=20):
    _, res = getj(f"{AGOL}/search?" + urllib.parse.urlencode({"q": q, "f": "json", "num": num, "sortField": "modified", "sortOrder": "desc"}))
    return " ¦ ".join(f"{i.get('type')}|{i.get('title')}|{i.get('owner')}|{i.get('url') or ''}|{i.get('id')}|mod={i.get('modified')}"
                      for i in res.get("results", []))


def explore_item(label, item_id):
    head, urls, ids = item(item_id)
    note(f"{label} item {item_id}", f"{head} :: servicios={urls[:15]} :: itemIds={ids[:15]}")
    return urls, ids


group = sys.argv[1]
if group == "boton":
    # CONAF Botón Rojo (owner deigeprif): mapas base y tableros → capas reales
    seen = []
    for label, iid in [("BR mapa", "ac259f64e18447a1b70a54e6419e4d36"), ("BR mapa2", "889d0a3828024df2b0d9e6ed22053f96"),
                       ("BR tablero", "41ee3c691359437aa9df2a09d7f6124e"), ("FIRMS tablero", "b8fc5f97527345d0aa8e958df28ac581")]:
        urls, _ = explore_item(label, iid)
        seen += urls
    for url in list(dict.fromkeys(seen))[:5]:
        note(f"capa {url[-90:]}", layer(url))
    note("deigeprif items", search("owner:deigeprif", 40)[:6000])
elif group == "senapred":
    base = "https://services6.arcgis.com/dxNWeb35zWPRjaNL/arcgis/rest/services/SENAPRED_-_Alertas_vigentes_por_region_(vista)/FeatureServer"
    explore_item("alertas vigentes", "c56c291657924f709b3c1e61e804d70d")
    note("alertas vigentes FS", layer(base))
    note("alertas vigentes capa 0", layer(base + "/0"))
    urls, _ = explore_item("MINSAL tablero alertas", "bdc345e01e324af490800634d0f0e3a5")
    _, ids = item("b71b567aff804dee98a692c091dc9276")
    note("MINSAL tablero 2 itemIds", str(ids[:15]))
    for url in urls[:2]:
        note(f"capa {url[-90:]}", layer(url))
    note("busqueda alertas", search("senapred alerta vigente comuna", 20)[:6000])
    note("busqueda geoportal", search("owner:geoportalonemi OR owner:ntapia_geoportalonemi alerta", 20)[:6000])
elif group == "dmc":
    base = "https://services3.arcgis.com/aSoEm9TBK2shtWjP/arcgis/rest/services/DMC_CAP_Boletines/FeatureServer"
    note("DMC CAP FS", layer(base))
    note("DMC CAP capa 0", layer(base + "/0"))
    note("if_temporadas", layer("https://services3.arcgis.com/DmlBJVTrQbCmoXcR/arcgis/rest/services/if_temporadas_2010_2024_t/FeatureServer/0"))
    note("riesgo interfaz", layer("https://services6.arcgis.com/LCdFQd7nnAn5xeUA/arcgis/rest/services/Riesgo_IF_Interfaz_Nacional/FeatureServer/0"))
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
