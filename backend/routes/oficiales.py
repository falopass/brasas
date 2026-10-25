"""Las alertas oficiales vigentes de SENAPRED que nombran la comuna o la región del lugar.

«La autoridad informa» (OFI-04): la lista completa se descarga una vez por ciclo de caché y
el calce con cada lugar es por el texto del título oficial (la API no trae el territorio de
la alerta poblado). Los textos son de SENAPRED, con su fecha y su enlace: BRASA nunca los
reescribe ni emite alertas propias.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from backend.geo import territory
from backend.providers import senapred
from backend.routes.common import services
from backend.services import Services

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)


@router.get("/alerts/official")
async def alertas_oficiales(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    svc: Services = Depends(services),
):
    """Alertas vigentes de SENAPRED que nombran la comuna o la región del punto.

    `alerts` sale en `[]` si el punto no cae en una comuna chilena, si ninguna alerta
    vigente lo menciona o si la fuente no responde: el vacío no es «todo tranquilo»,
    es «SENAPRED no ha publicado nada que te nombre», y siempre queda el enlace oficial.
    """
    comuna = territory().locate(lat, lon)
    if comuna is None:
        return {"alerts": [], "source": senapred.SOURCE, "source_url": senapred.SOURCE_URL,
                "fetched_at": svc.db.cache_get(senapred.CACHE_AT_KEY),
                "note": ("Alertas oficiales de SENAPRED que nombran a tu comuna o región, "
                         "con su texto, su fecha y su enlace. BRASA no emite alertas: la "
                         "autoridad es SENAPRED.")}
    try:
        alertas = await senapred.vigentes(svc.db, svc.client)
    except senapred.SenapredError as exc:
        log.warning("Alertas SENAPRED sin datos: %s", exc)
        alertas = []
    return {"alerts": senapred.para_lugar(alertas, comuna.name, comuna.region) if alertas else [],
            "source": senapred.SOURCE, "source_url": senapred.SOURCE_URL,
            "fetched_at": svc.db.cache_get(senapred.CACHE_AT_KEY),
            "note": ("Alertas oficiales de SENAPRED que nombran a tu comuna o región, "
                     "con su texto, su fecha y su enlace. BRASA no emite alertas: la "
                     "autoridad es SENAPRED.")}


@router.get("/senapred/alertas")
async def senapred_alertas(svc: Services = Depends(services)):
    """Todas las alertas vigentes de SENAPRED, para la capa nacional del mapa (OFI-207).

    Cada alerta lleva su clase (`tipo`: roja, amarilla, temprana_preventiva u otra), el
    título oficial exacto, su fecha, su enlace y los códigos BCN de las comunas que nombra;
    `comunas` vacía significa que el título no nombra territorio (la capa decide cómo
    mostrarla). Misma caché `senapred:alertas` que el resto: una caída de la fuente sale
    como `alerts` en `[]`, no como error.
    """
    try:
        alertas = await senapred.vigentes(svc.db, svc.client)
    except senapred.SenapredError as exc:
        log.warning("Alertas SENAPRED sin datos: %s", exc)
        alertas = []
    payload = {"alerts": senapred.para_mapa(alertas) if alertas else [],
               "source": senapred.SOURCE, "source_url": senapred.SOURCE_URL,
               "fetched_at": svc.db.cache_get(senapred.CACHE_AT_KEY),
               "note": ("Alertas oficiales vigentes de SENAPRED con su texto exacto, su fecha, "
                        "su enlace y las comunas que nombra cada título. BRASA no emite "
                        "alertas: la autoridad es SENAPRED.")}
    return JSONResponse(payload, headers={"Cache-Control": "public, max-age=120"})
