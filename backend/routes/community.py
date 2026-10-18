"""Reportes ciudadanos con moderación humana y reconstrucción de casos históricos."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import cases as cases_mod
from backend import reports as reports_mod
from backend.geo import territory
from backend.providers import firms, weather
from backend.routes.common import admin, clean_text, limiter, services
from backend.services import Services, stamp

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- reportes ciudadanos
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(request: Request, token: str, svc: Services) -> None:
    """Comprobación antibot (Cloudflare Turnstile): solo corre si el servidor tiene la clave secreta."""
    if not svc.settings.turnstile_secret:
        return
    if not token:
        raise HTTPException(403, "No pudimos comprobar que eres una persona. Recarga la página e intenta otra vez.")
    try:
        r = await svc.client.post(TURNSTILE_VERIFY_URL, timeout=10, data={
            "secret": svc.settings.turnstile_secret, "response": token,
            "remoteip": request.client.host if request.client else ""})
        outcome = r.json()
    except Exception:
        # Si el verificador de Cloudflare no responde, el reporte entra a moderación igual:
        # nada se publica sin revisión humana, así que el riesgo es solo trabajo extra para el equipo.
        return
    if not outcome.get("success"):
        raise HTTPException(403, "No pudimos comprobar que eres una persona. Intenta otra vez en unos minutos.")


@router.post("/reports", status_code=201)
async def create_report(
    request: Request,
    lat: float = Form(..., ge=-60, le=-17),
    lon: float = Form(..., ge=-110, le=-66),
    kind: str = Form("humo"),
    description: str = Form("", max_length=600),
    photo: UploadFile | None = File(None),
    cf_turnstile_response: str = Form("", alias="cf-turnstile-response"),
    svc: Services = Depends(services),
):
    limiter.check(request, "reports", 6, 3600)
    await verify_turnstile(request, cf_turnstile_response, svc)
    if kind not in reports_mod.KINDS:
        raise HTTPException(422, "Tipo de reporte inválido.")
    report_id = str(uuid.uuid4())
    photo_name = None
    if photo is not None and photo.filename:
        content = await photo.read(reports_mod.MAX_UPLOAD_BYTES + 1)
        try:
            photo_name = f"{report_id}.jpg"
            dest = svc.settings.data_dir / "uploads" / photo_name
            reports_mod.sanitize_photo(content, dest)
        except reports_mod.PhotoError as exc:
            raise HTTPException(422, str(exc)) from None
        if svc.storage:  # el disco del contenedor es efímero: la foto se guarda también en R2
            try:
                await svc.storage.put(f"photos/{photo_name}", dest.read_bytes(), "image/jpeg")
            except Exception:
                raise HTTPException(503, "No se pudo guardar la foto. Intenta nuevamente.") from None
    comuna = territory().locate(lat, lon)
    svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, photo) VALUES (?,?,?,?,?,?,?,?)",
                   (report_id, stamp(), lat, lon, comuna.code if comuna else None, kind, clean_text(description), photo_name))
    return {"id": report_id, "status": "no_verificado",
            "message": "Gracias. Tu reporte será revisado por un voluntario antes de mostrarse. "
                       "Si ves fuego, llama primero al 130 (CONAF) o al 132 (Bomberos)."}


def _public(row: dict) -> dict:
    comuna = territory().by_code.get(row["comuna_code"])
    return {"id": row["id"], "created_at": row["created_at"], "lat": round(row["lat"], 3), "lon": round(row["lon"], 3),
            "kind": row["kind"], "kind_label": reports_mod.KINDS.get(row["kind"], row["kind"]),
            "description": row["description"], "status": row["status"], "moderated_at": row["moderated_at"],
            "comuna": comuna.name if comuna else None, "has_photo": bool(row["photo"])}


@router.get("/reports")
def verified_reports(hours: int = 72, svc: Services = Depends(services)):
    """Solo reportes verificados por moderación; la ubicación se redondea (~100 m)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=min(max(hours, 1), 336))).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = svc.db.query("SELECT * FROM reports WHERE status = 'verificado' AND created_at >= ? ORDER BY created_at DESC", (since,))
    return {"reports": [_public(r) for r in rows]}


@router.get("/reports/{report_id}/photo")
async def report_photo(report_id: str, request: Request, svc: Services = Depends(services)):
    row = svc.db.one("SELECT * FROM reports WHERE id = ?", (report_id,))
    if not row or not row["photo"]:
        raise HTTPException(404, "Sin foto.")
    if row["status"] != "verificado":
        admin(request, request.headers.get("X-Admin-Token", ""))
    path = svc.settings.data_dir / "uploads" / row["photo"]
    if not path.exists() and svc.storage:
        content = await svc.storage.get(f"photos/{row['photo']}")
        if content is None:
            raise HTTPException(404, "Foto no disponible.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    if not path.exists():
        raise HTTPException(404, "Foto no disponible.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})


class Moderation(BaseModel):
    status: str
    note: str = ""


@router.get("/admin/reports", dependencies=[Depends(admin)])
def moderation_queue(status: str = "no_verificado", svc: Services = Depends(services)):
    if status not in reports_mod.STATUSES:
        raise HTTPException(422, "Estado inválido.")
    rows = svc.db.query("SELECT * FROM reports WHERE status = ? ORDER BY created_at DESC LIMIT 200", (status,))
    return {"reports": [{**_public(r), "lat": r["lat"], "lon": r["lon"], "moderator_note": r["moderator_note"]} for r in rows]}


@router.post("/admin/reports/{report_id}", dependencies=[Depends(admin)])
def moderate(report_id: str, decision: Moderation, svc: Services = Depends(services)):
    if decision.status not in reports_mod.STATUSES:
        raise HTTPException(422, "Estado inválido.")
    if not svc.db.execute("UPDATE reports SET status = ?, moderator_note = ?, moderated_at = ? WHERE id = ?",
                          (decision.status, clean_text(decision.note)[:300], stamp(), report_id)):
        raise HTTPException(404, "Reporte no encontrado.")
    return {"ok": True}


# ---------------------------------------------------------------- casos históricos
@router.get("/cases")
def list_cases():
    catalog = cases_mod.catalog()
    return {"note": catalog["note"], "cases": catalog["cases"]}


def _case_or_404(case_id: str) -> dict:
    case = cases_mod.get_case(case_id)
    if not case:
        raise HTTPException(404, "Caso no encontrado.")
    return case


def _case_observations(case: dict, svc: Services) -> tuple[list[dict], list[dict]]:
    goes_obs = cases_mod.load_goes(case)
    polar = svc.db.cache_get(f"case-firms:{case['id']}") or []
    return goes_obs, polar


@router.get("/cases/{case_id}")
def case_detail(case_id: str, svc: Services = Depends(services)):
    case = _case_or_404(case_id)
    goes_obs, polar = _case_observations(case, svc)
    timeline = None if polar else cases_mod.static_timeline(case)
    if timeline is None:
        cache_key = f"case-timeline:{case_id}:{cases_mod.TIMELINE_VERSION}:{len(goes_obs)}:{len(polar)}"
        timeline = svc.db.cache_get(cache_key)
        if timeline is None:
            timeline = cases_mod.build_timeline(case, goes_obs + polar)
            svc.db.cache_set(cache_key, timeline, 86400 * 60)
    return {"case": case, "timeline": timeline, "scans": cases_mod.goes_scans(case),
            "polar_loaded": bool(polar), "firms_configured": bool(svc.settings.firms_map_key)}


@router.get("/cases/{case_id}/polar")
def case_polar(case_id: str, svc: Services = Depends(services)):
    case = _case_or_404(case_id)
    return {"points": svc.db.cache_get(f"case-firms:{case['id']}") or []}


@router.post("/cases/{case_id}/polar")
async def load_case_polar(case_id: str, svc: Services = Depends(services)):
    """Descarga (una vez) las detecciones VIIRS/MODIS del archivo científico FIRMS para el caso."""
    case = _case_or_404(case_id)
    key = svc.settings.firms_map_key
    if not key:
        raise HTTPException(503, {"code": "FIRMS_KEY_MISSING", "message": "Este servidor aún no tiene acceso al archivo de NASA FIRMS, así que no puede sumar VIIRS y MODIS."})
    start = cases_mod.parse_utc(case["start_utc"]).date()
    end = cases_mod.parse_utc(case["end_utc"]).date()
    try:
        points, notices = await firms.fetch_hotspots(key, case["bbox"], case["firms_sources"], start=start, end=end, client=svc.client)
    except firms.UpstreamError as exc:
        raise HTTPException(502, str(exc)) from None
    svc.db.cache_set(f"case-firms:{case_id}", points, 86400 * 365)
    return {"count": len(points), "notices": notices}


@router.get("/cases/{case_id}/weather")
async def case_weather(case_id: str, svc: Services = Depends(services)):
    """Reanálisis ERA5 horario en el centro del caso (Open-Meteo Archive)."""
    case = _case_or_404(case_id)
    cache_key = f"case-weather:{case_id}"
    cached = svc.db.cache_get(cache_key)
    if cached:
        return cached
    lon, lat = case["camera"][0], case["camera"][1]
    try:
        hourly = await weather.archive_hourly(svc.client, lat, lon, case["start_utc"][:10], case["end_utc"][:10])
    except weather.WeatherError as exc:
        raise HTTPException(502, "No fue posible obtener el reanálisis meteorológico.") from exc
    payload = {"source": "ERA5 (Copernicus) vía Open-Meteo Archive", "lat": lat, "lon": lon, "timezone": "UTC", "hourly": hourly,
               "note": "Reanálisis de ~25 km de resolución: describe el ambiente general, no las ráfagas locales del frente."}
    svc.db.cache_set(cache_key, payload, 86400 * 365)
    return payload
