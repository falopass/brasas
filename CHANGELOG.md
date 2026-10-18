# Cambios

Formato: lo que nota una persona primero; lo técnico, después. Fechas de despliegue en producción.

## 0.6.0 — 18 de octubre de 2026

**Para las personas**
- **Incidentes:** las detecciones cercanas se agrupan en un incidente con estado (señal de calor, posible incendio, visto por vecinos, confirmado por CONAF, controlado, sin calor nuevo). Los volcanes y los puntos que arden muchos días seguidos (industria) no generan avisos.
- **Ficha de incidente** (`#/incendio/<id>`): qué vio cada satélite y cuándo, y cómo fue cambiando hora a hora.
- **CONAF en BRASA:** el pronóstico oficial **Botón Rojo** en Riesgo y en los días de cada lugar, y los **incendios informados por CONAF** en el mapa. Si CONAF informa un incendio nuevo cerca de un lugar guardado, llega un aviso «CONAF informa».
- **Modo emergencia:** si un lugar está en urgente, Mi zona muestra solo lo esencial: a qué distancia está, qué dijo la autoridad, botones grandes para llamar y 4 pasos.
- **Prepárate:** 2 L de agua por persona al día; evacuar a pie si así se indica; no dejar animales amarrados; avisar por mensaje en vez de llamar; no regresar aunque ya no se vean llamas; qué hacer en un parque.
- **Historia:** seis casos (nuevos: Penco–Lirquén 2026 con GOES-19, Valparaíso 2014, Torres del Paine 2011-12). Cada cifra muestra su fuente, su fecha y cómo cambió. Valparaíso 2024 corregido: 138 fallecidos (Fiscalía).
- Textos más exactos: «urgente» ya no afirma que el viento va hacia el lugar cuando la causa es la cercanía; las distancias menores a 3 km se muestran con un decimal.

**Técnico**
- `backend/incidents.py`; tablas `incidents`, `incident_observations`, `boton_rojo` y `official_fires` en `work.db`.
- `work.db` comprimida en R2 cada hora (`db/work.db.gz`) y restaurada al arrancar.
- `backend/providers/conaf.py`; API `/api/incidents`, `/api/incidents/{id}` y `/api/official-fires`; `boton_rojo` en `/api/risk`; `incident_id` en `/api/observations`.
- Exploración de fuentes oficiales desde GitHub Actions (`explorar-fuentes.yml`); hallazgos en `docs/FUENTES.md`.
- Entorno local: `dev.py` (setup, run, seed, test, check, e2e, clean), datos de demostración, revisión en navegador, configuración de VS Code, `docs/DESARROLLO_LOCAL.md`, `CONTRIBUTING.md` y `CLAUDE.md`.

## 0.5.x — octubre de 2026

- Modo vecino (`#/v/<token>`) con aviso anticipado cuando vive una persona mayor en el lugar.
- Identidad «Isoterma», lectura sencilla o detallada y letra grande.
- Ciclo del cron en segundo plano, respaldo en R2 por una ruta protegida del Worker, CSP y HSTS.
