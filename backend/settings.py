"""Configuración leída de variables de entorno / .env. Ningún secreto se envía al navegador."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

_TRUTHY = {"1", "true", "yes", "si", "sí", "on"}
_FALSY = {"0", "false", "no", "off"}
# El valor crudo de estas variables nunca va a los registros del contenedor.
_SENSITIVE = ("TOKEN", "KEY", "SECRET", "PASSWORD")


def _reason(name: str, value: str) -> str:
    if any(tag in name for tag in _SENSITIVE):
        return "valor no reconocido"
    return f"valor no reconocido: {value.strip()!r}"


def _warn(warnings: list[dict], name: str, reason: str, used) -> None:
    warnings.append({"name": name, "reason": reason, "used": used})
    log.warning("variable de entorno %s: %s; se usa %r", name, reason, used)


def _bool(name: str, default: bool, warnings: list[dict]) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    text = value.strip().lower()
    if text in _TRUTHY:
        return True
    if text not in _FALSY:
        _warn(warnings, name, _reason(name, value), False)
    return False


def _int(name: str, default: int, warnings: list[dict]) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        _warn(warnings, name, _reason(name, value), default)
        return default


def _url(name: str, default: str, warnings: list[dict], vacio: str | None = None) -> str:
    """URL pública: sin esquema los enlaces de los avisos salen rotos; se le antepone
    https:// y se avisa. `vacio` es el valor sano cuando la variable está definida pero
    en blanco: PUBLIC_BASE_URL vacío significa «aprender del primer HTTPS», no el default
    local. El valor usado va en `used` porque no es sensible."""
    value = os.getenv(name)
    if value is None:
        return default
    text = value.strip()
    if not text:
        return default if vacio is None else vacio
    if text.startswith(("http://", "https://")):
        return text
    fixed = f"https://{text}"
    _warn(warnings, name, _reason(name, value), fixed)
    return fixed


def _contacto(name: str, default: str, warnings: list[dict]) -> str:
    """Contacto VAPID (mailto: o https://): sin prefijo el servicio de push rechaza la
    firma y todos los avisos fallan como «no se pudo entregar», sin decir por qué.
    Un correo pelado se corrige a mailto:; otra cosa inválida cae al default."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    text = value.strip()
    if text.startswith(("mailto:", "https://")):
        return text
    if "@" in text and not any(c.isspace() for c in text):
        fixed = f"mailto:{text}"
        _warn(warnings, name, _reason(name, value), fixed)
        return fixed
    _warn(warnings, name, _reason(name, value), default)
    return default


def _data_dir(name: str, default: Path, warnings: list[dict]) -> Path:
    """Directorio de datos: se prueba crearlo aquí para que una ruta inválida avise
    en el arranque en vez de romper la base días después."""
    raw = os.getenv(name, "").strip()
    path = Path(raw) if raw else default
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        _warn(warnings, name, _reason(name, raw), str(default))
        return default
    if not path.is_dir():
        _warn(warnings, name, _reason(name, raw), str(default))
        return default
    return path


def _secreto(name: str, default: str, warnings: list[dict]) -> str:
    """Secreto de texto: muy corto o con espacios apunta a copia mal hecha. Se usa igual
    (sigue siendo secreto; apagarlo rompería el endpoint o el webhook en silencio), pero
    se avisa. La advertencia lleva solo nombre y motivo, nunca el valor."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    text = value.strip()
    if any(c.isspace() for c in text):
        _warn(warnings, name, "contiene espacios", "<omitido>")
    elif len(text) < 16:
        _warn(warnings, name, "menos de 16 caracteres", "<omitido>")
    return text


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
    dmc_usuario: str = ""
    dmc_token: str = ""
    conaf_perimetro_enabled: bool = False
    # Variables de entorno con valor presente pero no reconocido ({name, reason, used}).
    warnings: tuple[dict, ...] = field(default_factory=tuple)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "brasa.db"


def load() -> Settings:
    warnings: list[dict] = []
    sources = tuple(s.strip() for s in os.getenv("FIRMS_SOURCES", "").split(",") if s.strip())
    return Settings(
        firms_map_key=os.getenv("FIRMS_MAP_KEY", "").strip(),
        cesium_ion_token=os.getenv("CESIUM_ION_PUBLIC_TOKEN", "").strip(),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@"),
        admin_token=os.getenv("ADMIN_TOKEN", "").strip(),
        # Vacío: se aprende de la primera visita por HTTPS (útil en *.workers.dev).
        public_base_url=_url("PUBLIC_BASE_URL", "http://127.0.0.1:8000", warnings, vacio="").rstrip("/"),
        vapid_contact=_contacto("VAPID_CONTACT", "mailto:contacto@example.org", warnings),
        data_dir=_data_dir("BRASA_DATA_DIR", ROOT / "data", warnings),
        scheduler_enabled=_bool("BRASA_SCHEDULER", True, warnings),
        ingest_interval_min=max(5, _int("INGEST_INTERVAL_MIN", 10, warnings)),
        risk_interval_min=max(60, _int("RISK_INTERVAL_MIN", 180, warnings)),
        goes_enabled=_bool("GOES_ENABLED", True, warnings),
        storage_url=os.getenv("BRASA_STORAGE_URL", "").strip(),
        internal_token=_secreto("INTERNAL_TOKEN", "", warnings),
        telegram_webhook_secret=_secreto("TELEGRAM_WEBHOOK_SECRET", "", warnings),
        firms_sources=sources or ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"),
        # Tope diario de consultas al archivo satelital por IP (/api/explore). FIRMS tiene su propia
        # cuota y cada consulta cuesta: este tope protege la cuota compartida del servidor.
        explore_daily_limit=max(1, _int("EXPLORE_DAILY_LIMIT", 200, warnings)),
        # Antibot en el formulario de reportes (Cloudflare Turnstile). La de sitio es pública;
        # la secreta no sale del servidor. Sin secreta no hay verificación (desarrollo local).
        turnstile_site_key=os.getenv("TURNSTILE_SITE_KEY", "").strip(),
        turnstile_secret=os.getenv("TURNSTILE_SECRET", "").strip(),
        # OFI-33: credenciales personales del portal de servicios climáticos de la DMC
        # (correo del registro + apiKey). Van como secretos del despliegue; sin ellas la
        # estación más cercana no se consulta y la tarjeta de «medido de verdad» no aparece.
        dmc_usuario=os.getenv("DMC_USUARIO", "").strip(),
        dmc_token=_secreto("DMC_TOKEN", "", warnings),
        # OFI-17: perímetro oficial «Perimetro_final» de CONAF en la ficha del incidente.
        # Apagado hasta la autorización formal de la capa (OFI-03): la declaración de uso
        # público está en algunos tableros de GEPRIF, no en los servicios ArcGIS.
        conaf_perimetro_enabled=_bool("CONAF_PERIMETRO_ENABLED", False, warnings),
        # Normales de lluvia: son 153 celdas de 30 años de archivo. Se completan de a poco en cada
        # vuelta del ciclo (cada 6 h) para no agotar el cupo de Open-Meteo ni competir con el FWI.
        # 0 las congela: la anomalía se sigue calculando con las comunas que ya tengan normal.
        rain_normals_per_run=max(0, min(60, _int("RAIN_NORMALS_PER_RUN", 12, warnings))),
        # Último kwarg: los _bool/_int de arriba ya dejaron sus avisos en la lista.
        warnings=tuple(warnings),
    )
