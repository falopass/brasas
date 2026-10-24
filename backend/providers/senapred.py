"""Alertas oficiales vigentes de SENAPRED (portal público <https://senapred.cl/alertas/>).

La página de alertas es una app React que lee una API GraphQL (AWS AppSync). El acceso de
lectura es el mismo que recibe cualquier navegante del portal: el *identity pool* de Cognito
entrega credenciales anónimas de solo lectura y cada consulta se firma SigV4 (`AWS_IAM`).
No es un servicio documentado ni un feed CAP: si SENAPRED lo cambia o lo restringe, la capa
se degrada a `[]` y la app sigue enlazando a la página oficial (OFI-04).

El filtrado por lugar es textual: el título oficial es formulaico («…para la comuna de Angol
por…», «…para la Región del Maule por…») y la relación `comunas`/`regiones` del esquema viene
vacía, así que el calce se hace sobre el título con el nombre de la comuna o de la región.
Las alertas se muestran con su texto exacto, su fecha y su enlace —BRASA no emite alertas—.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend.geo import VARIANTES_COMUNA, _fold, territory
from backend.providers import _retry

IDENTITY_POOL = "us-east-1:17c696bc-53e1-49a2-991f-f1b65f752fda"
REGION = "us-east-1"
HOST = "rz2uv7ifxbgflh2bqmp6kmh4le.appsync-api.us-east-1.amazonaws.com"
ENDPOINT = f"https://{HOST}/graphql"
COGNITO_URL = f"https://cognito-identity.{REGION}.amazonaws.com/"
SOURCE = "SENAPRED · alertas oficiales"
SOURCE_URL = "https://senapred.cl/alertas/"
VENTANA_DIAS = 45          # solo alertas emitidas en esta ventana pueden seguir vigentes
MAX_PAGINAS = 3            # tope de páginas por ciclo (limit 200 c/u; sobra para alertas)

_QUERY = """query A($type: String!, $fh: ModelStringKeyConditionInput, $limit: Int, $nextToken: String) {
  alertasByDate(type: $type, fechaHora: $fh, sortDirection: DESC, limit: $limit,
                nextToken: $nextToken, filter: {isDeleted: {eq: false}, isActive: {eq: true}}) {
    items { id titulo fechaHora urlAccess isActive isDeleted }
    nextToken
  }
}"""


class SenapredError(Exception):
    pass


# --- credenciales anónimas del identity pool (las mismas que usa el sitio público) ---

_creds_cache: dict[str, Any] = {}


async def _cognito(client: httpx.AsyncClient, target: str, payload: dict) -> dict:
    try:
        r = await _retry.request(client, "POST", COGNITO_URL, json=payload,
                                 timeout=httpx.Timeout(15.0), headers={
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"AWSCognitoIdentityService.{target}"})
    except _retry.Failure as exc:
        raise SenapredError(f"Cognito no respondió en {target} ({exc.detail}).") from exc.cause
    try:
        data = r.json()
    except json.JSONDecodeError as exc:
        raise SenapredError("La respuesta de Cognito no es JSON.") from exc
    if not isinstance(data, dict):
        raise SenapredError("La respuesta de Cognito no tiene el formato esperado.")
    return data


async def _credentials(client: httpx.AsyncClient) -> dict:
    """Credenciales temporales del rol anónimo; se reusan hasta su `Expiration`."""
    vence = _creds_cache.get("expiration")
    if isinstance(vence, datetime) and vence - datetime.now(timezone.utc) > timedelta(minutes=5):
        return _creds_cache
    identity = await _cognito(client, "GetId", {"IdentityPoolId": IDENTITY_POOL})
    if not isinstance(identity.get("IdentityId"), str):
        raise SenapredError("Cognito no entregó un IdentityId.")
    creds = (await _cognito(client, "GetCredentialsForIdentity",
                            {"IdentityId": identity["IdentityId"]})).get("Credentials")
    if not isinstance(creds, dict) or not all(
            isinstance(creds.get(k), str)
            for k in ("AccessKeyId", "SecretKey", "SessionToken")):
        raise SenapredError("Cognito no entregó credenciales válidas.")
    _creds_cache.clear()
    _creds_cache.update(creds)
    if isinstance(creds.get("Expiration"), (int, float)):
        _creds_cache["expiration"] = datetime.fromtimestamp(creds["Expiration"], timezone.utc)
    else:
        _creds_cache["expiration"] = (datetime.now(timezone.utc)
                                      + timedelta(minutes=50))  # duración típica ~1 h
    return _creds_cache


def _sigv4_headers(body: str, creds: dict, now: datetime) -> dict[str, str]:
    """Firma AWS SigV4 del POST GraphQL (servicio `appsync`, us-east-1), solo stdlib."""
    amz = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    headers = {"content-type": "application/json", "host": HOST,
               "x-amz-date": amz, "x-amz-security-token": creds["SessionToken"]}
    signed = ";".join(sorted(headers))
    canonical = "\n".join(["POST", "/graphql", "",
                           "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
                           signed, hashlib.sha256(body.encode()).hexdigest()])
    scope = f"{day}/{REGION}/appsync/aws4_request"
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz, scope,
                                hashlib.sha256(canonical.encode()).hexdigest()])

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    key = _sign(("AWS4" + creds["SecretKey"]).encode(), day)
    for parte in (REGION, "appsync", "aws4_request"):
        key = _sign(key, parte)
    firma = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return {**headers, "Authorization":
            f"AWS4-HMAC-SHA256 Credential={creds['AccessKeyId']}/{scope}, "
            f"SignedHeaders={signed}, Signature={firma}"}


async def fetch_alerts(client: httpx.AsyncClient,
                       now: datetime | None = None) -> list[dict[str, Any]]:
    """Alertas vigentes (`isActive`) emitidas en la ventana reciente, de la más nueva a la más vieja."""
    now = now or datetime.now(timezone.utc)
    creds = await _credentials(client)
    inicio = (now - timedelta(days=VENTANA_DIAS)).strftime("%Y-%m-%dT%H:%M:%S")
    fin = (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
    out, token = [], None
    for _ in range(MAX_PAGINAS):
        body = json.dumps({"query": _QUERY, "variables": {
            "type": "Alerta", "fh": {"between": [inicio, fin]}, "limit": 200,
            "nextToken": token}})
        try:
            r = await _retry.request(client, "POST", ENDPOINT, content=body.encode(),
                                     headers=_sigv4_headers(body, creds,
                                                            datetime.now(timezone.utc)),
                                     timeout=httpx.Timeout(20.0))
        except _retry.Failure as exc:
            raise SenapredError(f"AppSync de SENAPRED no respondió ({exc.detail}).") from exc.cause
        try:
            data = r.json()
        except json.JSONDecodeError as exc:
            raise SenapredError("La respuesta de SENAPRED no es JSON.") from exc
        if data.get("errors"):
            raise SenapredError("SENAPRED rechazó la consulta GraphQL.")
        pagina = ((data.get("data") or {}).get("alertasByDate") or {})
        for a in pagina.get("items") or []:
            if not (a.get("isActive") and not a.get("isDeleted") and a.get("titulo")):
                continue
            titulo = a["titulo"].strip()
            if _CANCELA.match(_fold(titulo)):
                continue      # un aviso de cancelación no es una alerta vigente
            out.append({"id": a.get("id"), "title": titulo,
                        "issued_at": a.get("fechaHora"),
                        "url": f"https://senapred.cl/alertas/{a['urlAccess']}"
                        if a.get("urlAccess") else SOURCE_URL})
        token = pagina.get("nextToken")
        if not token:
            break
    return out


# --- calce por territorio: la comuna o la región nombradas en el título oficial ---

# Avisos de levantamiento/cierre que SENAPRED publica con isActive por un rato: el bloque
# dice «alertas vigentes» y un «se cancela…» ahí sobre-informa el riesgo.
_CANCELA = re.compile(r"^(se cancela|se levanta|se declara (el )?termino|se deja sin efecto)")

# Cómo termina la lista de nombres en el título formulaico: «…de Angol por evento…»;
# también se corta al pasar de lista comunal a regional («comuna de X y la región del…»).
_CORTE_SEG = re.compile(r"\s+por\s|\s+ante\s|\s+(?:y|e)\s+la\s+(?:region|comuna)")

_ALIAS: dict[str, str] | None = None    # grafía plegada (nombre o variante) → canónico


def _alias() -> dict[str, str]:
    """Toda grafía conocida de cada comuna → su nombre canónico plegado.

    SENAPRED puede escribir la grafía del índice o una variante («Coihaique»), así que el
    árbitro de nombres conoce ambas (`VARIANTES_COMUNA`, único diccionario del repo).
    """
    global _ALIAS
    if _ALIAS is None:
        m = {_fold(c.name): _fold(c.name) for c in territory().comunas}
        for origen, canonical in VARIANTES_COMUNA.items():
            m[_fold(origen)] = _fold(canonical)
        _ALIAS = m
    return _ALIAS


def _segmento(titulo: str, prep: str) -> str:
    """Lo nombrado tras «comuna de», «región del»… hasta « por »/« ante » o el final."""
    m = re.search(r"(?<!\w)(?:" + prep + r")\s+", titulo)
    if m is None:
        return ""
    seg = titulo[m.end():]
    corte = _CORTE_SEG.search(seg)
    return (seg[:corte.start()] if corte else seg).strip()


def _comunas_mencionadas(seg: str) -> set[str]:
    """Comunas nombradas en el segmento, por *maximal munch*: gana el nombre más largo.

    «comuna de Chillán Viejo» nombra a Chillán Viejo y no a Chillán; «comunas de Padre
    Las Casas y Cunco» nombra a ambas (cada nombre se busca dentro del segmento).
    """
    claimed: list[tuple[int, int]] = []
    hits: set[str] = set()
    alias = _alias()
    for nombre in sorted(alias, key=len, reverse=True):
        for m in re.finditer(r"(?<!\w)" + re.escape(nombre) + r"(?!\w)", seg):
            s = m.span()
            if any(a <= s[0] and b >= s[1] for a, b in claimed):
                continue                        # ya cubierto por un nombre más largo
            claimed.append(s)
            hits.add(alias[nombre])
    return hits


def _frase(texto: str, nombre: str) -> bool:
    return bool(nombre) and re.search(r"(?<!\w)" + re.escape(nombre) + r"(?!\w)",
                                      texto) is not None


def _region_mencionada(seg: str, region: str) -> bool:
    """La región del lugar aparece en lo nombrado (o al revés).

    SENAPRED alterna la forma corta y la larga: «Región del Maule» («maule») y «Región
    del Libertador General Bernardo O'Higgins»; el índice guarda «O'Higgins», así que el
    calce es por contención en cualquiera de las dos direcciones.
    """
    return _frase(seg, region) or _frase(region, seg)


def para_lugar(alertas: list[dict[str, Any]], comuna: str, region: str,
               maximo: int = 3) -> list[dict[str, Any]]:
    """Alertas vigentes que nombran a la comuna (alcance «comuna») o a la región («region»).

    Los títulos de SENAPRED son formulaicos: «para la comuna de X», «para las comunas de X
    e Y», «para la Región del Maule». Las de provincia solo calzan si además nombran la
    comuna (no hay mapa provincia→comuna aquí); queda documentado como limitación.
    """
    com, reg = _fold(comuna), _fold(region)
    out = []
    for a in alertas:
        t = _fold(a.get("title") or "")
        alcance = None
        if com in _comunas_mencionadas(_segmento(t, r"comunas? del?")):
            alcance = "comuna"
        elif _region_mencionada(_segmento(t, r"region(?:es)?(?: del?| de la)?"), reg):
            alcance = "region"
        if alcance:
            out.append({**a, "scope": alcance})
    out.sort(key=lambda a: a.get("issued_at") or "", reverse=True)
    # Un «Monitoreo» república la misma alerta (mismo slug) en otro registro: una por URL.
    # Las que no traen slug comparten el enlace genérico: para ellas la clave es el `id`.
    vistos: set[str] = set()
    out = [a for a in out if not ((k := a["url"] if a["url"] != SOURCE_URL
                                   else f"id:{a.get('id')}") in vistos or vistos.add(k))]
    out.sort(key=lambda a: a["scope"] != "comuna")   # estable: la comunal primero
    return out[:maximo]
