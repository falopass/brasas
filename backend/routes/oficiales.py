"""Las alertas oficiales vigentes de SENAPRED que nombran la comuna o la región del lugar.

«La autoridad informa» (OFI-04): la lista completa se descarga una vez por ciclo de caché y
el calce con cada lugar es por el texto del título oficial (la API no trae el territorio de
la alerta poblado). Los textos son de SENAPRED, con su fecha y su enlace: BRASA nunca los
reescribe ni emite alertas propias.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from backend.geo import territory
from backend.providers import senapred
from backend.routes.common import services
from backend.services import Services

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)

TTL_S = 600      # el listado de alertas no cambia minuto a minuto; una descarga sirve a todos
RETRY_S = 300


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
    payload = {"alerts": [], "source": senapred.SOURCE, "source_url": senapred.SOURCE_URL,
               "note": ("Alertas oficiales de SENAPRED que nombran a tu comuna o región, "
                        "con su texto, su fecha y su enlace. BRASA no emite alertas: la "
                        "autoridad es SENAPRED.")}
    comuna = territory().locate(lat, lon)
    if comuna is None:
        return payload
    alertas = svc.db.cache_get("senapred:alertas")
    if alertas is None:
        try:
            alertas = await senapred.fetch_alerts(svc.client)
        except senapred.SenapredError as exc:
            log.warning("Alertas SENAPRED sin datos: %s", exc)
            alertas = []
        svc.db.cache_set("senapred:alertas", alertas, TTL_S if alertas else RETRY_S)
    if alertas:
        payload["alerts"] = senapred.para_lugar(alertas, comuna.name, comuna.region)
    return payload
