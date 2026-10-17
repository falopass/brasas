# Hoja de ruta — BRASA Chile

Versión 0.2 · 17 de octubre de 2026

## Enfoque

BRASA deja de ser un visor de datos satelitales y pasa a ser un **sistema ciudadano de alerta temprana y riesgo territorial**: primero incendios; después lluvias, aluviones y otras amenazas. La pregunta que responde es:

> **«¿Mi casa, mi parcela o mi familia están en riesgo hoy, y qué debo hacer?»**

Contexto de la temporada 2026-27: los pronósticos internacionales indican una alta probabilidad de un El Niño fuerte, con calor extremo en el centro y lluvias de verano en el norte. La gran mayoría de los incendios forestales en Chile son de origen humano. La temporada no se mueve: la Etapa 0 tiene que estar en manos de usuarios reales antes de mediados de diciembre.

**Regla de oro:** complementar a SENAPRED y CONAF, nunca competir con ellos. La ventaja de Watch Duty no es el mapa: es la **confianza**, es decir, alertas rápidas, verificadas por personas y con su fuente a la vista.

## Estado de la v0.2 (implementado)

| Capacidad | Estado | Nota |
|---|---|---|
| Alerta por lugar (radio, viento a favor, deduplicación, urgente) | ✅ | Web Push y Telegram; bandeja en la app |
| GOES-Este cada 10 minutos (sin clave) + relleno inicial de 6 h | ✅ | Probado con datos reales de GOES-19 y GOES-16 |
| VIIRS NOAA-20/21 NRT | ✅ | Requiere `FIRMS_MAP_KEY` |
| Comunas reales (345, BCN) en lugar de cajas | ✅ | Corrige el hueco de Coquimbo de la v0.1 |
| Semáforo 30-30-30 por comuna, 7 días | ✅ | Open-Meteo, cada 3 h |
| PWA instalable, sin conexión, mapa 2D liviano | ✅ | MapLibre con base de comunas sin conexión |
| Reportes ciudadanos con moderación | ✅ | Foto sin EXIF; nada se publica sin verificar |
| Reconstrucción de casos 2017 / 2023 / 2024 | ✅ | GOES real precalculado; VIIRS/MODIS y ERA5 bajo demanda |
| Prepárate: checklists, plan familiar, prevención | ✅ | Se guarda en el dispositivo |
| Puntos de encuentro / hospitales / Bomberos (OSM) | ✅ | Cobertura rural incompleta |
| 90 comunas prioritarias de CONAF | ⏳ | Falta el documento oficial; no se inventa |
| Canal regional de Telegram (difusión) | ⏳ | El bot ya existe; falta la política editorial |
| Estaciones DMC, FWI (GWIS), sequedad Sentinel-2 | ⏳ | Rotuladas «próximamente» en la interfaz |
| Operaciones (brigadas, aeronaves, drones) | 🚫 | Solo con fuentes autorizadas; nunca simuladas |

## Plan por etapas

| Etapa | Cuándo | Qué | Criterio de éxito |
|---|---|---|---|
| **0** | Nov – mediados de dic 2026 | Despliegue con HTTPS, `FIRMS_MAP_KEY`, bot de Telegram y moderación. **Piloto en el Maule** con juntas de vecinos y una red inicial de 10 a 20 verificadores. Carga de las 90 comunas prioritarias desde CONAF. | 500 lugares guardados; alertas en < 20 min desde el paso GOES; 0 alertas sin fuente. |
| **1** | Ene – mar 2027 | Operar el verano. Turnos de verificadores (Bomberos voluntarios, brigadistas, radioaficionados). Canal regional de Telegram. Medir falsas alarmas y tiempos. Aprender de los usuarios. | Tasa de falsas alarmas < 10 % en alertas urgentes; tiempo de verificación de un reporte < 15 min. |
| **2** | Abr – jun 2027 | Área quemada con Sentinel-2 (dNBR), catálogo de casos 2026-27, **mapa de riesgo de aluvión post-incendio** (área quemada × pendiente × lluvia pronosticada). | Polígonos validados con CONAF; 3 comunas piloto con mapa de aluvión. |
| **3** | Invierno 2027 | Lluvias, caudales DGA en tiempo real, **isoterma 0 °C** y alertas por lugar para aluviones. Primeros clientes empresa. | Alertas por lugar para dos amenazas con la misma infraestructura. |
| **4** | 2028+ | Plataforma nacional multiamenaza (calor extremo, humo y calidad del aire, sequía, marejadas) y convenios institucionales. | Convenios formales con al menos un organismo público. |

## Próximos pasos técnicos (por prioridad)

**P0 — antes del piloto**
1. Despliegue con HTTPS (requisito de Web Push) y respaldo diario de la base.
2. Migración a PostgreSQL/PostGIS cuando haya más de un servidor (el esquema ya es equivalente).
3. Observabilidad: alerta si GOES no entrega datos en 30 minutos o si FIRMS falla 3 ciclos seguidos.
4. Revisión legal de licencias del mapa base y de los términos de Open-Meteo para el uso que se dé.
5. Pruebas en terreno con celulares de gama baja y mala señal rural.

**P1 — durante el verano**
1. Detección temprana más fina: agrupar píxeles GOES consecutivos (persistencia en 2 o 3 barridos) para bajar los falsos positivos.
2. Integración de estaciones DMC para corregir el pronóstico en las comunas con estación.
3. FWI de GWIS/Copernicus como segunda capa de riesgo.
4. Avisos de «hoy está prohibido quemar» en cuanto exista una fuente oficial utilizable.

**P2 — después**
1. Convenios con forestales y eléctricas que ya tienen cámaras y torres de vigilancia.
2. Reconstrucción con más productos (VIIRS de 375 m por pasada, perímetros diarios cuando existan).
3. Informes PDF por comuna y por caso.

## Decisiones que no se improvisan

- No vender una falsa equivalencia «foco = incendio activo».
- No hacer scraping intensivo de CONAF o SENAPRED sin permiso ni términos claros.
- No usar BRASA para decisiones de seguridad personal en lugar de las instrucciones oficiales.
- No depender de VIIRS S-NPP (fin de entrega en noviembre de 2026).
- No usar teselas comunitarias para tráfico masivo.
- **No mostrar operaciones simuladas** (drones, aeronaves, brigadas) junto a datos reales. El módulo de operaciones queda diseñado y vacío hasta tener fuentes autorizadas.

## Advertencia de capacidad

Esto es una institución, no un proyecto paralelo: alertas, verificación humana y soporte durante la temporada exigen turnos y responsables. Antes del piloto, conviene decidir si BRASA es la prioridad de este verano y quién responde cuando algo falla un sábado a las 18:00 con 35 °C y viento puelche.
