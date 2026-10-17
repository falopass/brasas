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
    )
