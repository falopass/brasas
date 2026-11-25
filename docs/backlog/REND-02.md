---
id: REND-02
repo: falopass/brasas
rama: perf/medicion-integral
riesgo: alto
archivos: scripts/local/, tests/, .github/workflows/, docs/, web/, backend/
e2e: true
---

# Rendimiento integral de BRASA

Encargo aprobado el 25-11-2026. Sin rediseño, pérdida funcional, reducción de
cobertura, precisión, accesibilidad o seguridad. Sin telemetría de usuarios
ni servicios externos nuevos. Validación exclusivamente en CI/Cloud.

## Secuencia y condición de avance

1. Instrumentación y base reproducible, sin optimizaciones funcionales.
2. Configuración no bloqueante y limpieza de trabajo compartido del cliente.
3. Secundarios de Mi zona según cadencias de las fuentes y repintados de vistas.
4. Contabilidad meteorológica efectiva y reservas persistentes atómicas.
5. Infraestructura particionada equivalente y costos medidos de mapa/viento.
6. Precarga SW priorizada y coherencia offline/versiones.
7. APIs, validadores con representación completa y consultas medidas.
8. Persistencia/restauración, solo si hay beneficio demostrado.
9. Comparación final, documentación y gates.

Las tandas posteriores dependen de mediciones válidas de la primera. No se
da por terminado el encargo completo al entregar instrumentación. Una
intervención sin beneficio demostrado se corrige o se omite, documentando
el motivo. Avisos se modifican únicamente en PR independiente con revisión
geográfica y de seguridad.

## Contrato de medición

Base y candidata alternadas; mismo Chromium, compilador, datos y condiciones.
Cinco muestras independientes por escenario de navegador, mediana y peor,
con errores y timeouts conservados. API reproducible con veinte muestras
como mínimo para p95; primera llamada y proceso nuevo separados del caliente.
Sondas GET de producción acotadas, sin multiplicar sus repeticiones.

Móvil táctil 390×844 y escritorio 1280×900; revisión visual también a 320 px.
Red y CPU normales/limitadas; primera visita, regreso, URL profunda,
instalada; caché fría, caliente con SW, incompleta, actualización y offline.
Navegación y uso real de filtros/capas/viento/reproducción/2D-3D, pestaña
oculta y sesiones repetidas. Demo, 2.000 detecciones/200 incidentes y casos
históricos versionados mayores. Contienda con ingesta simulada y fases de
respaldo/restauración, sin datos personales.

FCP/LCP solo del documento. Contenido utilizable por ruta con marcas
reiniciadas por transición; interacción sintética no se llama INP de usuarios.
Bytes crudos y transferidos separados; límites de CPU, memoria, workers y
recursos del mapa explícitos. Comparación visual, offline, CSP, accesibilidad
y reportes cuando corresponda.

## Gates sin aumentarlos

- Build servido: bloqueante ≤125 KiB gzip, total ≤275 KiB gzip.
- `web/data`: contrato vigente de 4 MiB; shell y respuestas mantienen sus topes.
- Prueba vigente de 2.000 detecciones/200 incidentes <5 s.
- API caliente p95 ≤2.500 ms; frío se informa aparte.
- Open-Meteo: 9.000 ubicaciones diarias, reserva, límites por minuto y pausas.
- Sin poda de `risk_daily`, `fwi_daily`, reportes ni historial.

El estado de escenarios ejercidos y limitaciones queda en
[`../RENDIMIENTO_INTEGRAL.md`](../RENDIMIENTO_INTEGRAL.md). Los resultados son
artefactos técnicos de CI, nunca promesas ni puntuaciones aisladas.

## Estado

Primera tanda fusionada en [PR #986](https://github.com/falopass/brasas/pull/986)
con nueve checks verdes, revisiones de seguridad/UX aprobadas y línea base
válida para siete rutas, móvil/escritorio, red/CPU normales y caché fría.
Segunda tanda en implementación: configuración no bloqueante y consumidores
que mantienen su función cuando llega tarde. No hay ahorros entregados todavía.
La matriz integral y las tandas 3–9 siguen pendientes.
