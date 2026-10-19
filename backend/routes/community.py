"""Reportes ciudadanos con moderación humana y reconstrucción de casos históricos."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import alerts as alerts_mod
from backend import cases as cases_mod
from backend import incidents as incidents_mod
from backend import reports as reports_mod
from backend.geo import haversine_km, territory
from backend.providers import firms, weather
from backend.routes.common import admin, clean_text, limiter, moderator_token_hash, services, subscriber
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
        r = await svc.client.post(
            TURNSTILE_VERIFY_URL,
            timeout=10,
            data={"secret": svc.settings.turnstile_secret, "response": token, "remoteip": request.client.host if request.client else ""},
        )
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
    response: Response,
    lat: float = Form(..., ge=-60, le=-17),
    lon: float = Form(..., ge=-110, le=-66),
    kind: str = Form("humo"),
    description: str = Form("", max_length=600),
    photo: UploadFile | None = File(None),
    cf_turnstile_response: str = Form("", alias="cf-turnstile-response"),
    x_brasa_token: str = Header(default="", alias="X-Brasa-Token"),
    svc: Services = Depends(services),
):
    limiter.check(request, "reports", 6, 3600)
    await verify_turnstile(request, cf_turnstile_response, svc)
    if kind not in reports_mod.KINDS:
        raise HTTPException(422, "Tipo de reporte inválido.")
    comuna = territory().locate(lat, lon)
    # Cercano y reciente: es el mismo hecho, no una fila más en la cola. Se avisa al autor en vez
    # de crear un duplicado que un moderador tendría que fusionar a mano, pero el aviso no se
    # pierde: queda como corroboración («otro vecino lo vio») del reporte original.
    previous = _similar(svc, lat, lon, kind)
    if previous:
        response.status_code = 200  # no se creó nada: 201 mentiría sobre lo que pasó
        await _adopt_photo(svc, previous, photo)
        corroborations = _corroborate(svc, previous, _author(svc, x_brasa_token))
        return {
            "id": previous["id"],
            "status": previous["status"],
            "duplicate": True,
            "corroboraciones": corroborations,
            "message": "Ya hay un reporte parecido en revisión. Tu aviso quedó como otra "
            "persona que lo vio; si ves fuego, llama al 130 (CONAF) o al 132 (Bomberos).",
        }
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
    svc.db.execute(
        "INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, photo, subscriber_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            report_id,
            stamp(),
            lat,
            lon,
            comuna.code if comuna else None,
            kind,
            clean_text(description),
            photo_name,
            _author(svc, x_brasa_token),
        ),
    )
    return {
        "id": report_id,
        "status": "no_verificado",
        "duplicate": False,
        "message": "Gracias. Tu reporte será revisado por un voluntario antes de mostrarse. "
        "Si ves fuego, llama primero al 130 (CONAF) o al 132 (Bomberos).",
    }


def _author(svc: Services, token: str) -> str | None:
    """Dispositivo que envía el reporte, si lo mandó. Reportar no exige cuenta: el token es opcional.

    Guardarlo (y no el token) es lo que permite después contestarle «tu reporte quedó verificado»
    sin abrir los reportes de nadie más.
    """
    clean = (token or "").strip()
    if len(clean) < 20:
        return None
    row = svc.db.one("SELECT id FROM subscribers WHERE id = ?", (clean,))
    return row["id"] if row else None


def _similar(svc: Services, lat: float, lon: float, kind: str) -> dict | None:
    """Reporte equivalente que todavía espera revisión: mismo tipo, cerca y reciente.

    Se consulta por comuna y tipo (índice barato) y la distancia se mide en Python: son pocas
    filas por comuna en la ventana de tres horas.
    """
    since = reports_mod.expire_cutoff(hours=reports_mod.DUPLICATE_HOURS)
    for row in svc.db.query(
        "SELECT id, lat, lon, status, created_at, photo, subscriber_id FROM reports "
        "WHERE status = 'no_verificado' AND kind = ? AND created_at >= ?",
        (kind, since),
    ):
        if haversine_km(lat, lon, row["lat"], row["lon"]) <= reports_mod.DUPLICATE_KM:
            return dict(row)
    return None


async def _adopt_photo(svc: Services, previous: dict, photo: UploadFile | None) -> None:
    """Si el primer aviso llegó sin foto, la del duplicado pasa al original: es la misma escena
    y la evidencia no se puede perder. Una foto inválida no tumba la corroboración."""
    if previous.get("photo") or photo is None or not photo.filename:
        return
    content = await photo.read(reports_mod.MAX_UPLOAD_BYTES + 1)
    name = f"{uuid.uuid4()}.jpg"
    dest = svc.settings.data_dir / "uploads" / name
    try:
        reports_mod.sanitize_photo(content, dest)
    except reports_mod.PhotoError:
        return
    if svc.storage:
        try:
            await svc.storage.put(f"photos/{name}", dest.read_bytes(), "image/jpeg")
        except Exception:
            dest.unlink(missing_ok=True)
            return
    svc.db.execute("UPDATE reports SET photo = ? WHERE id = ?", (name, previous["id"]))


def _corroborate(svc: Services, previous: dict, author: str | None) -> int:
    """Registra otro testigo del mismo hecho y devuelve cuántas corroboraciones lleva.

    Un mismo dispositivo cuenta una sola vez, y el autor del aviso original no se suma a sí
    mismo: «otro vecino» tiene que ser otra persona. Sin token no hay cómo distinguir, así que
    cada aviso anónimo cuenta.
    """
    if author:
        if author != previous.get("subscriber_id"):
            svc.db.execute(
                "INSERT INTO report_corroborations(report_id, created_at, subscriber_id) "
                "SELECT ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM report_corroborations "
                "WHERE report_id = ? AND subscriber_id = ?)",
                (previous["id"], stamp(), author, previous["id"], author),
            )
    else:
        svc.db.execute(
            "INSERT INTO report_corroborations(report_id, created_at, subscriber_id) VALUES (?, ?, NULL)", (previous["id"], stamp())
        )
    return svc.db.one("SELECT COUNT(*) AS n FROM report_corroborations WHERE report_id = ?", (previous["id"],))["n"]


def _expire_stale(svc: Services) -> int:
    """Marca los reportes que nadie revisó a tiempo, cada tipo en su ventana. Devuelve cuántos caducaron."""
    expired = 0
    for kind, hours in reports_mod.EXPIRE_HOURS_BY_KIND.items():
        expired += svc.db.execute(
            "UPDATE reports SET status = 'descartado', moderator_note = ?, moderated_at = ? "
            "WHERE status = 'no_verificado' AND kind = ? AND created_at < ?",
            (reports_mod.EXPIRED_NOTE, stamp(), kind, reports_mod.expire_cutoff(hours=hours)),
        )
    return expired


_CORROBORATIONS = "(SELECT COUNT(*) FROM report_corroborations c WHERE c.report_id = r.id) AS corroboraciones"


def _public(row: dict) -> dict:
    comuna = territory().by_code.get(row["comuna_code"])
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "lat": round(row["lat"], 3),
        "lon": round(row["lon"], 3),
        "kind": row["kind"],
        "kind_label": reports_mod.KINDS.get(row["kind"], row["kind"]),
        "description": row["description"],
        "status": row["status"],
        "status_label": reports_mod.STATUS_LABELS.get(row["status"], row["status"]),
        "moderated_at": row["moderated_at"],
        "corroboraciones": row.get("corroboraciones") or 0,
        "comuna": comuna.name if comuna else None,
        "has_photo": bool(row["photo"]),
    }


@router.get("/reports")
def verified_reports(hours: int = 72, limit: int = Query(500, ge=1, le=2000), svc: Services = Depends(services)):
    """Solo reportes verificados por moderación; la ubicación se redondea (~100 m).

    `limit` acota la respuesta y `truncated` avisa si hubo recorte: una temporada grande
    podía devolver miles de filas sin aviso. Es el mismo truco de LIMIT+1 que /api/observations.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=min(max(hours, 1), 336))).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = svc.db.query(
        f"SELECT r.*, {_CORROBORATIONS} FROM reports r WHERE status = 'verificado' AND created_at >= ? ORDER BY created_at DESC LIMIT ?",
        (since, limit + 1),
    )
    truncated = len(rows) > limit
    return {"reports": [_public(r) for r in rows[:limit]], "truncated": truncated}


@router.get("/incidents/{incident_id}/reports")
def incident_reports(
    incident_id: str, hours: int = Query(48, ge=1, le=168), km: float = Query(3, ge=1, le=10), svc: Services = Depends(services)
):
    """Reportes verificados cerca de un incidente: el contexto humano de su ficha.

    Son los mismos avisos que la evidencia usa para marcar el estado «reportado»
    (`_status` en incidents.py), ahora visibles para quien abre la ficha. Un id ya
    fusionado se resuelve al incidente vigente, igual que en la ficha misma.
    """
    inc = incidents_mod.resolve_merge(svc.db, incident_id)
    if inc is None:
        raise HTTPException(404, "Incidente no encontrado (puede haberse unido a otro o ya no tener detecciones guardadas).")
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = svc.db.query(
        f"SELECT r.*, {_CORROBORATIONS} FROM reports r WHERE status = 'verificado' AND created_at >= ? ORDER BY created_at DESC",
        (since,),
    )
    near = [(r, d) for r in rows if (d := haversine_km(inc["lat"], inc["lon"], r["lat"], r["lon"])) <= km]
    return {
        "reports": [_public(r) | {"distance_km": round(d, 1)} for r, d in near[:20]],
        "radius_km": km,
        "hours": hours,
        "truncated": len(near) > 20,
    }


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


class BatchModeration(BaseModel):
    ids: list[str]
    status: str
    note: str = ""


def _log_decision(svc: Services, actor: dict, report_id: str, action: str, note: str) -> None:
    """Toda decisión humana sobre un reporte queda con quién la tomó y su nota (SEC-10)."""
    svc.db.execute(
        "INSERT INTO moderation_log(moderator_id, action, report_id, note, created_at) VALUES (?,?,?,?,?)",
        (actor["id"], action, report_id, note, stamp()),
    )


@router.get("/admin/reports", dependencies=[Depends(admin)])
def moderation_queue(status: str = "no_verificado", comuna: int | None = None, svc: Services = Depends(services)):
    """Cola de moderación. Antes de listar se caducan los que esperaron demasiado.

    La caducidad se aplica aquí, al leer: en Cloudflare el contenedor se suspende entre ciclos y
    no hay que depender del cron para que la cola diga la verdad. Lo más viejo va primero: en
    temporada alta lo nuevo no puede tapar un reporte que ya lleva horas esperando; y entre los
    que esperan, los que varios vecinos corroboraron se revisan primero.
    """
    if status not in reports_mod.STATUSES:
        raise HTTPException(422, "Estado inválido.")
    expired_now = _expire_stale(svc)
    where, params = "status = ?", [status]
    if comuna is not None:
        where += " AND comuna_code = ?"
        params.append(comuna)
    rows = svc.db.query(
        f"SELECT r.*, {_CORROBORATIONS} FROM reports r WHERE {where} ORDER BY corroboraciones DESC, created_at ASC LIMIT 200", tuple(params)
    )
    now = datetime.now(timezone.utc)
    return {
        "reports": [
            {
                **_public(r),
                "lat": r["lat"],
                "lon": r["lon"],
                "moderator_note": r["moderator_note"],
                "comuna_code": r["comuna_code"],
                "age_s": max(0, int((now - datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))).total_seconds())),
            }
            for r in rows
        ],
        "expired_now": expired_now,
        "expire_hours": reports_mod.EXPIRE_HOURS_BY_KIND,
    }


@router.post("/admin/reports/batch")
def moderate_batch(decision: BatchModeration, actor: dict = Depends(admin), svc: Services = Depends(services)):
    """Aprobar o descartar varios reportes de una vez: el cuello de botella es humano.

    Va declarada antes de `/admin/reports/{report_id}`: si no, FastAPI toma «batch» como un id.
    """
    if decision.status not in reports_mod.STATUSES:
        raise HTTPException(422, "Estado inválido.")
    ids = [clean_text(i)[:64] for i in decision.ids if i][:200]
    if not ids:
        raise HTTPException(422, "No hay reportes que moderar.")
    note = clean_text(decision.note)[:300]
    marks = ",".join("?" * len(ids))
    # Los que de verdad pasan a «verificado» con esta decisión: solo ellos avisan (ALR-03),
    # igual que la moderación de a uno. Se lee antes del UPDATE para conocer el estado previo.
    fresh = (
        svc.db.query(f"SELECT * FROM reports WHERE id IN ({marks}) AND status != 'verificado'", tuple(ids))
        if decision.status == "verificado"
        else []
    )
    with svc.db.connect() as conn:
        updated = 0
        for report_id in ids:
            updated += conn.execute(
                "UPDATE reports SET status = ?, moderator_note = ?, moderated_at = ? WHERE id = ?",
                (decision.status, note, stamp(), report_id),
            ).rowcount
            conn.execute(
                "INSERT INTO moderation_log(moderator_id, action, report_id, note, created_at) VALUES (?,?,?,?,?)",
                (actor["id"], decision.status, report_id, note, stamp()),
            )
    # La conexión directa se salta el aviso de escritura de `Database`: sin esto, un lote no marcaba
    # la base para respaldo y las decisiones se perdían si el contenedor se reciclaba antes de copiar.
    if updated and svc.db.on_user_write:
        svc.db.on_user_write()
    # Si el PR de moderación individual está en main, se recalculan los incidentes cercanos, igual que
    # en la moderación de a uno. Se busca por atributo para no acoplar el orden de fusión.
    refresh_near = getattr(incidents_mod, "refresh_near", None)
    if refresh_near and decision.status == "verificado":
        for row in svc.db.query("SELECT lat, lon FROM reports WHERE id IN (%s)" % marks, tuple(ids)):
            refresh_near(svc.db, row["lat"], row["lon"])
    alerts_created = sum(len(alerts_mod.evaluate_report(svc.db, {**row, "status": "verificado"})) for row in fresh)
    return {"ok": True, "status": decision.status, "requested": len(ids), "updated": updated, "alerts_created": alerts_created}


@router.post("/admin/reports/{report_id}")
def moderate(report_id: str, decision: Moderation, actor: dict = Depends(admin), svc: Services = Depends(services)):
    """Aprueba o descarta un reporte. Si cambia la verificación, se recalculan los incidentes cercanos.

    Sin esto, un reporte verificado no cambiaba nada hasta que llegara una detección nueva: el
    estado «reportado» depende de la evidencia y se recalculaba solo en la ingesta (FIX-09). Vale
    también al revés: si se revoca la verificación, el incidente tiene que dejar de decir «reportado».
    """
    if decision.status not in reports_mod.STATUSES:
        raise HTTPException(422, "Estado inválido.")
    report = svc.db.one("SELECT * FROM reports WHERE id = ?", (report_id,))
    if not report:
        raise HTTPException(404, "Reporte no encontrado.")
    note = clean_text(decision.note)[:300]
    svc.db.execute(
        "UPDATE reports SET status = ?, moderator_note = ?, moderated_at = ? WHERE id = ?", (decision.status, note, stamp(), report_id)
    )
    _log_decision(svc, actor, report_id, decision.status, note)
    changed = report["status"] != decision.status
    verified_before, verified_now = report["status"] == "verificado", decision.status == "verificado"
    refreshed = 0
    if changed and (verified_before or verified_now):
        refreshed = incidents_mod.refresh_near(svc.db, report["lat"], report["lon"])
    alerts_created = 0
    if verified_now and not verified_before:  # ALR-03: solo al pasar a «verificado»
        alerts_created = len(alerts_mod.evaluate_report(svc.db, {**report, "status": "verificado"}))
    return {"ok": True, "incidents_refreshed": refreshed, "alerts_created": alerts_created}


@router.get("/reports/mine")
def my_reports(sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    """Qué pasó con los reportes de este dispositivo.

    Sin esto, quien reporta humo nunca sabe si su aviso sirvió. Solo se devuelven los reportes
    enviados por este dispositivo (token), sin datos de otras personas.
    """
    _expire_stale(svc)
    rows = svc.db.query(
        f"SELECT r.*, {_CORROBORATIONS} FROM reports r WHERE subscriber_id = ? ORDER BY created_at DESC LIMIT 50",
        (sub["id"],),
    )
    return {
        "reports": [
            {
                **_public(r),
                "moderator_note": r["moderator_note"],
                "photo_url": (f"/api/reports/{r['id']}/photo" if r["photo"] and r["status"] == "verificado" else None),
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ---------------------------------------------------------------- moderadores (SEC-10)
def _require_superuser(actor: dict) -> None:
    """Altas y revocaciones del equipo son solo del token maestro: un voluntario no crea voluntarios."""
    if not actor["superuser"]:
        raise HTTPException(403, "Solo la administración puede gestionar moderadores.")


@router.get("/admin/me")
def admin_me(actor: dict = Depends(admin)):
    """Quién entró al panel: el front muestra la gestión del equipo solo al superusuario."""
    return {"name": actor["name"], "superuser": actor["superuser"]}


class NewModerator(BaseModel):
    name: str


@router.get("/admin/moderators")
def list_moderators(actor: dict = Depends(admin), svc: Services = Depends(services)):
    _require_superuser(actor)
    return {"moderators": svc.db.query("SELECT id, name, created_at, revoked_at FROM moderators ORDER BY created_at")}


@router.post("/admin/moderators", status_code=201)
def create_moderator(payload: NewModerator, actor: dict = Depends(admin), svc: Services = Depends(services)):
    """Alta de un moderador: el token se genera acá y se devuelve una sola vez (en la base queda solo su hash)."""
    _require_superuser(actor)
    name = clean_text(payload.name)[:80]
    if not name:
        raise HTTPException(422, "Falta el nombre del moderador.")
    token = secrets.token_urlsafe(32)
    moderator_id = str(uuid.uuid4())
    svc.db.execute(
        "INSERT INTO moderators(id, name, token_hash, created_at) VALUES (?,?,?,?)",
        (moderator_id, name, moderator_token_hash(token), stamp()),
    )
    return {"id": moderator_id, "name": name, "token": token}


@router.post("/admin/moderators/{moderator_id}/revoke")
def revoke_moderator(moderator_id: str, actor: dict = Depends(admin), svc: Services = Depends(services)):
    """Revoca el acceso sin borrar la fila: el registro de decisiones conserva el nombre."""
    _require_superuser(actor)
    if not svc.db.execute("UPDATE moderators SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL", (stamp(), moderator_id)):
        raise HTTPException(404, "Moderador no encontrado o ya revocado.")
    return {"ok": True}


@router.get("/admin/moderation-log")
def moderation_log(actor: dict = Depends(admin), svc: Services = Depends(services)):
    """Las últimas decisiones con quién las tomó; «administración» es el token maestro."""
    rows = svc.db.query(
        "SELECT l.action, l.report_id, l.note, l.created_at, m.name AS moderator "
        "FROM moderation_log l LEFT JOIN moderators m ON m.id = l.moderator_id "
        "ORDER BY l.id DESC LIMIT 200"
    )
    return {"log": [{**r, "moderator": r["moderator"] or "administración"} for r in rows]}


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
    return {
        "case": case,
        "timeline": timeline,
        "scans": cases_mod.goes_scans(case),
        "polar_loaded": bool(polar),
        "firms_configured": bool(svc.settings.firms_map_key),
    }


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
        raise HTTPException(
            503,
            {
                "code": "FIRMS_KEY_MISSING",
                "message": "Este servidor aún no tiene acceso al archivo de NASA FIRMS, así que no puede sumar VIIRS y MODIS.",
            },
        )
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
    payload = {
        "source": "ERA5 (Copernicus) vía Open-Meteo Archive",
        "lat": lat,
        "lon": lon,
        "timezone": "UTC",
        "hourly": hourly,
        "note": "Reanálisis de ~25 km de resolución: describe el ambiente general, no las ráfagas locales del frente.",
    }
    svc.db.cache_set(cache_key, payload, 86400 * 365)
    return payload
