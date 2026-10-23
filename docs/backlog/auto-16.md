---
id: AUTO-16
repo: brasas
rama: feat/datos-versionados-con-edad
modelo: swe-2-high
riesgo: B
archivos: backend/dataversion.py, backend/routes/datos.py, backend/main.py, tests/test_dataversion.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que BRASA sepa y diga **qué tan viejos son sus propios datos versionados** —los JSON de `web/data/` que el vecino termina viendo en pantalla— y publique esa edad en un GET pequeño, con la acción concreta cuando uno se pasó de su ventana. Hoy el producto vigila la frescura de la ingesta satelital (`backend/freshness.py`: 30 minutos para el último barrido) pero no dice nada de estos archivos, que cambian cada temporada o cada año.

# Ítem del backlog

OPS-14 (diagnóstico sin acceso a registros) y el foco de auto-mejora de esta ronda: que el producto detecte y reporte sus propias fallas, no solo las de las fuentes externas.

# Qué pasa hoy y por qué está mal

- `backend/freshness.py:24-34` solo mide la edad de `last_ingest_at` (ingesta). No existe nada que mire los archivos versionados.
- Los consume el backend sin saber si están al día: `backend/censo.py:1` (censo 2024), `backend/rain.py:34` y `:132` (normales de lluvia, FIX-25), `backend/services.py:604-628` (misma tabla), y el frontend usa `web/data/interfaz.json`, `historia-comunas.json`, `temporada-2526.json`, `persistent_hotspots.json`.
- Si mañana CONAF publica los campamentos y el archivo se regenera, o si el censo se queda con una versión vieja, **nadie se entera**: no hay una fecha publicada, ni una ventana esperada, ni un «qué hacer». El vecino puede estar viendo exposición de una comuna con datos de hace dos años sin que la aplicación lo advierta.

# Qué hacer

1. `backend/dataversion.py` (nuevo): una tabla de los archivos versionados que importan —`censo_2024.json`, `rain_normals.json`, `interfaz.json`, `historia-comunas.json`, `temporada-2526.json`, `persistent_hotspots.json`, `prioritarias.json`— con su nombre legible, la fuente oficial, la ventana de actualización esperada en días y el `que_hacer` en español neutro (por ejemplo «vuelve a correr `scripts/local/build_censo.py` con el archivo del INE y sube el JSON»). Para cada archivo: `version` (el campo de fecha del JSON si lo trae —`fetched_at`, `source.date`— y, si no, la fecha del archivo, **dicha como tal**), `edad_dias`, `estado` en {`al_dia`, `viejo`, `falta`}, y `tamano_kb`. Si el archivo no existe, `estado: "falta"`; nunca inventes una fecha.
2. `backend/routes/datos.py` (nuevo): `GET /api/datos-versionados`, público, solo lectura, `include_in_schema=True`, con `{type, generated_at, archivos:[...], resumen:{al_dia, viejos, faltan}}`. Sin datos personales y sin rutas absolutas del sistema.
3. Registrar el router en `backend/main.py` (junto a los otros `include_router`).
4. `tests/test_dataversion.py`: con un directorio temporal y fechas fijas — archivo con fecha de hace 3 días y ventana de 30 → `al_dia`; con fecha de hace 400 días y ventana de 365 → `viejo` con su `que_hacer`; archivo ausente → `falta`; archivo sin campo de fecha → usa la fecha del archivo y lo dice en `version_fuente: "mtime"`.
5. Una línea en `CHANGELOG.md`.

**Archivos a tocar:** `backend/dataversion.py`, `backend/routes/datos.py`, `backend/main.py`, `tests/test_dataversion.py`, `CHANGELOG.md`. **No toques nada más**: no modifiques `backend/routes/public.py` (otro encargo lo ocupa), ni `/api/status`, ni `backend/freshness.py`, ni los JSON de `web/data/`, ni `web/js/`.

# Criterio de listo (verificable)

- `python dev.py test -k datos_versionados` en verde con los cuatro casos de arriba.
- `GET /api/datos-versionados` contra la app de demostración devuelve los 7 archivos con su estado, y `prioritarias.json` (vacío hoy) aparece como `al_dia` o `viejo` según su fecha, nunca como error.
- `python dev.py check` dice «Todo en orden».

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
