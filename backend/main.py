"""Servidor y API de BRASA Chile. Complementa a SENAPRED y CONAF; no emite alertas oficiales."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import httpx
from backend.security import content_security_policy
from backend.version import VERSION
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import og as og_mod
from backend import settings as settings_mod
from backend.geo import territory
from backend.routes import calendar as calendar_mod
from backend.routes import paginas_comuna
from backend.routes import climate, community, comuna, datos, diagnostico, internal, observability, opendata, panorama, personal, public
from backend.services import Services

ROOT = settings_mod.ROOT
WEB = ROOT / "web"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# Las pruebas inyectan aquí un httpx.MockTransport para simular proveedores externos.
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = settings_mod.load()
    client = httpx.AsyncClient(transport=HTTP_TRANSPORT, timeout=40.0) if HTTP_TRANSPORT else None
    svc = Services(cfg, client)
    territory()  # carga el índice de comunas al arrancar
    app.state.services = svc
    await svc.start()
    try:
        yield
    finally:
        await svc.close()


app = FastAPI(
    title="BRASA Chile API",
    version=VERSION,
    lifespan=lifespan,
    description="Detecciones satelitales, riesgo meteorológico y alertas por lugar. No son alertas oficiales.",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(public.router)
app.include_router(comuna.router)
app.include_router(paginas_comuna.router)
app.include_router(opendata.router)
app.include_router(personal.router)
app.include_router(community.router)
app.include_router(internal.router)
app.include_router(climate.router)
app.include_router(og_mod.router)
app.include_router(panorama.router)
app.include_router(calendar_mod.router)
app.include_router(observability.router)
app.include_router(diagnostico.router)
app.include_router(datos.router)
app.mount("/web", StaticFiles(directory=str(WEB)), name="web")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    svc = getattr(request.app.state, "services", None)
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    if svc and not svc.public_url and scheme == "https" and "." in (request.url.hostname or ""):
        await svc.learn_public_url(f"https://{request.url.netloc}")
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(self), microphone=()")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if not request.url.path.startswith(("/api/", "/web/")):
        response.headers.setdefault("Content-Security-Policy", content_security_policy(request.url.path))
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def _record_sample(request: Request, status: int, started: float) -> None:
    """Anota la medición en la ventana; si falla, la respuesta sigue igual: la telemetría no es el servicio."""
    try:
        observability.record(observability.route_of(request), status, (time.perf_counter() - started) * 1000)
    except Exception:
        pass


@app.middleware("http")
async def measure_routes(request: Request, call_next):
    """Mide las peticiones a `/api/…` para `/api/observability/routes` y `/api/diagnostico`
    (ruta, código y ms). `/api/diagnostico` se excluye para no contarse a sí mismo."""
    if not request.url.path.startswith("/api/") or request.url.path == "/api/diagnostico":
        return await call_next(request)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _record_sample(request, 500, started)
        raise
    _record_sample(request, response.status_code, started)
    return response


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return FileResponse(WEB / "robots.txt", media_type="text/plain")


@app.get("/ping", include_in_schema=False)
def ping():
    return {"ok": True}


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(WEB / "admin.html", headers={"Cache-Control": "no-cache"})


@app.get("/lista.html", include_in_schema=False)
def lista_page():
    return FileResponse(WEB / "lista.html", headers={"Cache-Control": "no-cache"})


@app.get("/focos.html", include_in_schema=False)
def focos_page():
    return FileResponse(WEB / "focos.html", headers={"Cache-Control": "no-cache"})


@app.get("/datos.html", include_in_schema=False)
def datos_page():
    return FileResponse(WEB / "datos.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    # El service worker debe servirse desde la raíz para controlar toda la aplicación.
    return FileResponse(WEB / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")
