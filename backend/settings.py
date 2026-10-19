"""Configuración leída de variables de entorno / .env. Ningún secreto se envía al navegador."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    firms_map_key: str = ""
    cesium_ion_token: str = ""
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    admin_token: str = ""
    public_base_url: str = "http://127.0.0.1:8000"
    vapid_contact: str = "mailto:contacto@example.org"
    data_dir: Path = field(default_factory=lambda: ROOT / "data")
    scheduler_enabled: bool = True
    ingest_interval_min: int = 10
    risk_interval_min: int = 180
    goes_enabled: bool = True
    storage_url: str = ""
    internal_token: str = ""
    telegram_webhook_secret: str = ""
    firms_sources: tuple[str, ...] = ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
    explore_daily_limit: int = 200
    rain_normals_per_run: int = 12
    turnstile_site_key: str = ""
    turnstile_secret: str = ""
    conaf_perimetro_enabled: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "brasa.db"


def load() -> Settings:
    sources = tuple(s.strip() for s in os.getenv("FIRMS_SOURCES", "").split(",") if s.strip())
    return Settings(
        firms_map_key=os.getenv("FIRMS_MAP_KEY", "").strip(),
        cesium_ion_token=os.getenv("CESIUM_ION_PUBLIC_TOKEN", "").strip(),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@"),
        admin_token=os.getenv("ADMIN_TOKEN", "").strip(),
        # Vacío: se aprende de la primera visita por HTTPS (útil en *.workers.dev).
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/"),
        vapid_contact=os.getenv("VAPID_CONTACT", "mailto:contacto@example.org").strip(),
        data_dir=Path(os.getenv("BRASA_DATA_DIR", "").strip() or ROOT / "data"),
        scheduler_enabled=_bool("BRASA_SCHEDULER", True),
        ingest_interval_min=max(5, _int("INGEST_INTERVAL_MIN", 10)),
        risk_interval_min=max(60, _int("RISK_INTERVAL_MIN", 180)),
        goes_enabled=_bool("GOES_ENABLED", True),
        storage_url=os.getenv("BRASA_STORAGE_URL", "").strip(),
        internal_token=os.getenv("INTERNAL_TOKEN", "").strip(),
        telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip(),
        firms_sources=sources or ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"),
        # Tope diario de consultas al archivo satelital por IP (/api/explore). FIRMS tiene su propia
        # cuota y cada consulta cuesta: este tope protege la cuota compartida del servidor.
        explore_daily_limit=max(1, _int("EXPLORE_DAILY_LIMIT", 200)),
        # Antibot en el formulario de reportes (Cloudflare Turnstile). La de sitio es pública;
        # la secreta no sale del servidor. Sin secreta no hay verificación (desarrollo local).
        turnstile_site_key=os.getenv("TURNSTILE_SITE_KEY", "").strip(),
        turnstile_secret=os.getenv("TURNSTILE_SECRET", "").strip(),
        # OFI-17: perímetro oficial «Perimetro_final» de CONAF en la ficha del incidente.
        # Apagado hasta la autorización formal de la capa (OFI-03): la declaración de uso
        # público está en algunos tableros de GEPRIF, no en los servicios ArcGIS.
        conaf_perimetro_enabled=_bool("CONAF_PERIMETRO_ENABLED", False),
        # Normales de lluvia: son 153 celdas de 30 años de archivo. Se completan de a poco en cada
        # vuelta del ciclo (cada 6 h) para no agotar el cupo de Open-Meteo ni competir con el FWI.
        # 0 las congela: la anomalía se sigue calculando con las comunas que ya tengan normal.
        rain_normals_per_run=max(0, min(60, _int("RAIN_NORMALS_PER_RUN", 12))),
    )
