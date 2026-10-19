# Hoja de ruta — BRASA Chile

> **Qué documento manda:** [`PLAN_NEXT_LEVEL.md`](PLAN_NEXT_LEVEL.md) es la fuente de verdad del avance por fases y [`BACKLOG_MAESTRO.md`](BACKLOG_MAESTRO.md) el del trabajo pendiente (cada ítem tiene su ID). Este ROADMAP conserva la visión por etapas; el detalle de cada versión está en [`CHANGELOG.md`](../CHANGELOG.md).

Versión 0.9.0 (+ ola OPS en `main`, sin desplegar) · 19 de octubre de 2026

## Enfoque

BRASA deja de ser un visor de datos satelitales y pasa a ser un **sistema ciudadano de alerta temprana y riesgo territorial**: primero incendios; después lluvias, aluviones y otras amenazas. La pregunta que responde es:

> **«¿Mi casa, mi parcela o mi familia están en riesgo hoy, y qué debo hacer?»**

Contexto de la temporada 2026-27: los pronósticos internacionales indican una alta probabilidad de un El Niño fuerte, con calor extremo en el centro y lluvias de verano en el norte. La gran mayoría de los incendios forestales en Chile son de origen humano. La temporada no se mueve: la Etapa 0 tiene que estar en manos de usuarios reales antes de mediados de diciembre.

**Regla de oro:** complementar a SENAPRED y CONAF, nunca competir con ellos. La ventaja de Watch Duty no es el mapa: es la **confianza**, es decir, alertas rápidas, verificadas por personas y con su fuente a la vista.

## Estado al día de hoy

**En producción (hasta 0.6.0):**

| Capacidad | Estado | Nota |
|---|---|---|
| Alerta por lugar (radio, viento a favor, deduplicación, urgente) | ✅ | Web Push; Telegram listo en código, falta crear el bot (ALR-01) |
| GOES-Este cada 10 minutos (sin clave) + relleno inicial de 6 h | ✅ | Probado con datos reales de GOES-19 y GOES-16 |
| VIIRS NOAA-20/21 NRT | ✅ | Requiere `FIRMS_MAP_KEY` |
| Comunas reales (345, BCN) en lugar de cajas | ✅ | Corrige el hueco de Coquimbo de la v0.1 |
| Semáforo 30-30-30 por comuna, 7 días | ✅ | Open-Meteo, cada 3 h |
| PWA instalable, sin conexión, mapa 2D liviano | ✅ | MapLibre con base de comunas sin conexión |
| Reportes ciudadanos con moderación | ✅ | Foto sin EXIF; nada se publica sin verificar |
| Reconstrucción de casos 2017 / 2023 / 2024 | ✅ | GOES real precalculado; VIIRS/MODIS y ERA5 bajo demanda |
| Prepárate: checklists, plan familiar, prevención | ✅ | Se guarda en el dispositivo |
| Puntos de encuentro / hospitales / Bomberos (OSM) | ✅ | Cobertura rural incompleta |
| Incidentes, ficha por incidente y fuentes CONAF (Botón Rojo, incendios informados) | ✅ | 0.6.0 |
| Modo emergencia, modo vecino/familia, persona mayor con aviso anticipado | ✅ | 0.5.x–0.6.0 |

**En `main`, pendiente de despliegue (OPS-19):**

| Capacidad | Estado | Nota |
|---|---|---|
| FWI (sequía acumulada) y riesgo combinado 30-30-30 × FWI | ✅ 0.7.0 | Van Wagner 1987 verificado contra `cffdrs` |
| Avisos oficiales de la DMC (viento y calor) por comuna | ✅ 0.7.0 | RSS + CAP 1.2, ingesta horaria |
| Lluvia de la temporada vs. normal 1991-2020 | ✅ 0.7.0 | Normales por celda de 0,5°, se completan por tandas |
| Historial de avisos por dispositivo, frescura del dato en la cabecera, avisos que abren la ficha del incidente | ✅ 0.8.0 | |
| Privacidad: página de política, exportar y borrar datos, retención con tope, términos de uso | ✅ 0.9.0 | Ley 21.719; EIPD en `docs/PRIVACIDAD_EIPD.md` |
| Ola OPS: caché y límite en el borde, Turnstile, prueba de carga k6, dependencias fijas con hashes, simulacro de restauración, monitoreo de la ingesta | ✅ en `main` | OPS-01 a OPS-10; detalle en `CHANGELOG.md` |

**Pendiente de verdad** (detalle y prioridad en `BACKLOG_MAESTRO.md`):

| Capacidad | Estado | Nota |
|---|---|---|
| 90 comunas prioritarias de CONAF | ⏳ OFI-05 | Falta el documento oficial; no se inventa |
| Bot y canal regional de Telegram | ⏳ ALR-01 | El código ya existe; falta crear el bot y la política editorial |
| Sequedad de la vegetación (Sentinel-2/NDMI) | ⏳ RISK-11 | Investigación de costo en INV-12 |
| Operaciones (brigadas, aeronaves, drones) | 🚫 | Solo con fuentes autorizadas; nunca simuladas |

## Plan por etapas

| Etapa | Cuándo | Qué | Criterio de éxito |
|---|---|---|---|
| **0** | Nov – mediados de dic 2026 | ~~Despliegue con HTTPS~~ (hecho), `FIRMS_MAP_KEY`, desplegar `main` (OPS-19), bot de Telegram (ALR-01) y moderación. **Piloto en el Maule** con juntas de vecinos y una red inicial de 10 a 20 verificadores. Carga de las 90 comunas prioritarias desde CONAF (OFI-05). | 500 lugares guardados; alertas en < 20 min desde el paso GOES; 0 alertas sin fuente. |
| **1** | Ene – mar 2027 | Operar el verano. Turnos de verificadores (Bomberos voluntarios, brigadistas, radioaficionados). Canal regional de Telegram. Medir falsas alarmas y tiempos. Aprender de los usuarios. | Tasa de falsas alarmas < 10 % en alertas urgentes; tiempo de verificación de un reporte < 15 min. |
| **2** | Abr – jun 2027 | Área quemada con Sentinel-2 (dNBR), catálogo de casos 2026-27, **mapa de riesgo de aluvión post-incendio** (área quemada × pendiente × lluvia pronosticada) — ítems AGUA-01 a AGUA-04. | Polígonos validados con CONAF; 3 comunas piloto con mapa de aluvión. |
| **3** | Invierno 2027 | Lluvias, caudales DGA en tiempo real (AGUA-07), **isoterma 0 °C** (AGUA-03) y alertas por lugar para aluviones. Primeros clientes empresa. | Alertas por lugar para dos amenazas con la misma infraestructura. |
| **4** | 2028+ | Plataforma nacional multiamenaza (calor extremo, humo y calidad del aire — AGUA-05 — sequía, marejadas) y convenios institucionales. | Convenios formales con al menos un organismo público. |

## Próximos pasos técnicos (por prioridad)

La lista completa y priorizada vive en `BACKLOG_MAESTRO.md`; esto es solo el resumen.

**P0 — antes del piloto**
1. Desplegar lo que está en `main` (0.7.0 a 0.9.0 y la ola OPS) y verificarlo en producción (OPS-19).
2. Crear el bot de Telegram y activar el webhook (ALR-01; decisión de la persona dueña).
3. Documento oficial de comunas prioritarias de CONAF (OFI-05).
4. Revisión legal: licencia del repositorio (SEC-14), asesoría *pro bono* (SEC-07) y términos de Open-Meteo para el uso que se dé (NEG-05).
5. Pruebas en terreno con celulares de gama baja y mala señal rural (QA-08).

**P1 — durante el verano**
1. Revisar a mano y publicar la máscara de fuentes fijas (DET-05) para bajar falsos positivos.
2. Cupo de Open-Meteo compartido por pronóstico, FWI, normales de lluvia y casos (RISK-14); evaluar el plan con clave por la licencia no comercial.
3. Monitoreo ya activo (OPS-01, OPS-02); mantener el congelamiento de temporada del 15 de diciembre al 28 de febrero (OPS-17).

**P2 — después**
1. Convenios con forestales y eléctricas que ya tienen cámaras y torres (ALI-08), con política de conflicto de interés.
2. Corrección de paralaje por relieve en píxeles GOES (DET-02).
3. Cicatrices de incendios previos como capa de combustible (RISK-12), base del mapa de aluvión.

## Decisiones que no se improvisan

- No vender una falsa equivalencia «foco = incendio activo».
- No hacer scraping intensivo de CONAF o SENAPRED sin permiso ni términos claros.
- No usar BRASA para decisiones de seguridad personal en lugar de las instrucciones oficiales.
- No depender de VIIRS S-NPP (fin de entrega en noviembre de 2026).
- No usar teselas comunitarias para tráfico masivo.
- **No mostrar operaciones simuladas** (drones, aeronaves, brigadas) junto a datos reales. El módulo de operaciones queda diseñado y vacío hasta tener fuentes autorizadas.

## Advertencia de capacidad

Esto es una institución, no un proyecto paralelo: alertas, verificación humana y soporte durante la temporada exigen turnos y responsables. Antes del piloto, conviene decidir si BRASA es la prioridad de este verano y quién responde cuando algo falla un sábado a las 18:00 con 35 °C y viento puelche.
