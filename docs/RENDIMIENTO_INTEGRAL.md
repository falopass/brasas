# Medición integral de rendimiento en navegador real

Instrumentación de PR1, sin cambios funcionales. Se ejecuta exclusivamente en
GitHub CI/Cloud, sobre dos checkouts servidos con el build minificado y datos
sintéticos. No añade telemetría, servicios externos ni una página de métricas.

- `scripts/local/medir_rendimiento.py` — mide un despliegue (reescritura de la medición de A11Y-02; el CLI `BASE OUT` se mantiene y los perfiles «4g/3g» anteriores equivalen a `--network normal/lenta`).
- `scripts/local/comparar_rendimiento.py` — enfrenta base vs candidata en la misma instancia de Chromium.
- `tests/test_medir_rendimiento.py` — lo puro, sin navegador ni Playwright (CI).
- `scripts/local/benchmark_api.py` — API en procesos nuevos, fixture común, SQL y contienda.
- `scripts/local/perf_server.py` — servidor efímero con proveedores aislados.
- `.github/workflows/rendimiento.yml` — compilación y comparación, sin secretos ni despliegues.

Complementa (no reemplaza) los presupuestos estáticos: `peso_arranque.py` (arranque sin
red) y `presupuesto_peso.py` (presupuesto por tipo de recurso). Aquí se mide el navegador
real: red, CPU, caché y contenido usable.

## Cómo se mide

### Matriz

| Eje | Valores |
|---|---|
| Dispositivo | móvil 390×844 táctil (escala 2) · escritorio 1280×900 |
| Red | normal: 40 ms, 12 Mbps de bajada · lenta: 2000 ms, ~400 kbps (la «3G lenta» histórica del repo) |
| CPU | ×1 · ×4 (`Emulation.setCPUThrottlingRate`) |
| Caché | fría (contexto nuevo, service worker permitido) · caliente (SW con su precaché, preparación no medida) · offline (SW ya instalado, red cortada con `set_offline`, la preparación tampoco se mide) |

Por escenario y ruta se toman **N muestras (mínimo 5), cada una en un contexto nuevo e
independiente**. En la comparación, cada par de muestras se mide en orden alterno —
base/candidata y luego candidata/base — para cancelar el deriva de la máquina, siempre
sobre la misma instancia de Chromium.

El orquestador de CI asigna una IP sintética de loopback distinta por contexto,
mediante `X-Forwarded-For` en los servidores efímeros `127.0.0.1:8001/8002`.
Uvicorn confía solo en el proxy de loopback. Así las altas de dispositivos de
muestras independientes no agotan entre todas el cupo de una única IP.
Los límites del backend siguen activos, incluso dentro de cada muestra.
Este modo requiere `BRASA_BENCH_CLIENT_IPS=1`, que solo establece el orquestador;
no se aplica a las URL públicas. Las cabeceras contienen solo IP sintética.

### Pasos por ruta

1. **directo**: primer acceso a la URL completa (incluidas URLs profundas como
   `/#/casos/penco-lirquen-2026`); se separa el FCP/LCP del documento del tiempo hasta
   contenido usable.
2. **desdePortada** (solo SPA): la portada carga como documento y la ruta se alcanza por
   navegación dentro de la app (clic en el enlace de navegación o cambio de hash).
3. **reingreso**: navegación repetida — una ruta distractora y volver (módulos y datos
   ya calientes). En páginas estáticas es una recarga.

Cada transición SPA **reinicia marca, CLS y criterio** (`__brasaPerf.reset`): el tiempo de
ruta usable no se mezcla con el documento. El FCP/LCP del documento se reporta aparte.

### Contenido usable (no el título ni el esqueleto)

Cada ruta declara, consultando `web/js/views/` y las páginas estáticas, un selector de
contenido real (`listo`) y, cuando existe, uno de fallo explícito (`fallo`, bloque
«Reintentar»); opcionalmente un mínimo de texto para descartar cascarones. Estados
posibles por paso: `util`, `fallo` (estado explícito de fallo del producto) y `timeout`
(también conservado, nunca descartado).

| Ruta | Contenido usable | Fallo explícito |
|---|---|---|
| mi-zona `/#/mi-zona` | `#zona-b #add-place` o `.ember-hero`, acción principal o estado del lugar | — |
| mapa `/#/mapa` | `#map-listas h2` (las listas llegan con datos) | `#map-carga-err .callout-warn`, `#map-err .callout-warn` |
| riesgo `/#/riesgo` | `#r-search` (solo en el render con pronóstico) | `.callout-warn [data-retry]` |
| casos `/#/casos` | `.chips-region` | `.callout-warn [data-retry]` |
| caso-penco-2026 `/#/casos/penco-lirquen-2026` | `.player` o `.callout.c-nota` | `#case-err .callout-warn` |
| temporada `/#/temporada` | `.t-nota`, presente también sin temporadas o con una sola | `.callout-warn [data-retry]` |
| preparate `/#/preparate` | guía `.fold.caso`, no el placeholder del paquete | — |
| alertas `/#/alertas` | `#inbox-body .kpis`/`.empty` | `#inbox-body #retry` |
| quehago `/#/quehago` | `.fold.caso` | — |
| calidad `/#/calidad` | `.status-badge` o `#copy-diag`, estado sano o diagnóstico | `[data-retry]` |
| privacidad `/#/privacidad` | `#pr-cuerpo .lede` o `h2.section` | `#pr-cuerpo [data-retry]` |
| mas `/#/mas` | `#view ul.indice` | — |
| focos `/focos.html` | tabla o vacío sin `hidden` | `#focos-error:not([hidden])` |
| lite `/web/lite.html` | `#lite-places > *` | — |
| preguntas `/web/preguntas.html` | `main.faq` con ≥300 caracteres | — |

La detección corre dentro de la página, con sondeo de 80 ms: esa granularidad
limita la precisión y no permite afirmar mejoras menores. El inicio del acceso
directo incluye la descarga del documento. En una transición, se exige un
elemento nuevo y el hash de destino, para no aceptar contenido de la vista anterior.

### Errores y validez

Todo se conserva: errores JS (`pageerror`), de consola, HTTP ≥400, fallos de red y
timeouts quedan en la muestra con su clase:

- `producto` — falla del despliegue medido (mismo origen): hace fallar la corrida (código de salida 1).
- `externo` — tercero permitido (`--integracion-real`): se informa, no falla.
- `bloqueado` — tercero bloqueado a propósito (esperado, no falla).
- `esperado` — sin señal: respuesta 503 sintética del service worker o red caída en modo offline (el comportamiento offline se mide, no se culpa).
- `medidor` — falla propia del instrumento.

Mediana y peor se calculan **solo con muestras completas** (todos los pasos `util`); el
conteo de incompletas **invalida la comparación** de ese escenario y ruta, con sus motivos
en el informe. Las muestras incompletas siguen en el JSON con su duración y estado.

### Bytes, CPU y memoria

- Bytes por la red: `encodedDataLength` de CDP (`Network.loadingFinished`) de respuestas
  servidas por red; las servidas desde disco o por el service worker se reportan aparte
  (`bytesCache`). No se suman como bytes decodificados: CDP no entrega el tamaño
  decodificado por pedido. Los duplicados (una misma URL pedida más de una vez) se cuentan.
- Limitación documentada: las peticiones que el service worker hace por su cuenta pueden
  no aparecer en la sesión CDP de la página; se capturan las que pasan por el target de
  página (con `fromServiceWorker` marcado) y nada más.
- CPU: `Performance.getMetrics` (TaskDuration, ScriptDuration, LayoutDuration,
  RecalcStyleDuration) por diferencia entre el inicio y el fin de la parte medida; heap JS
  (usado/total) al cierre. Limitación: las métricas son del hilo principal; la memoria de
  workers (incluido el SW) no se ve.
- Tareas largas (>50 ms) del hilo principal por paso — no se llaman «tiempo de parseo».
- Interacción sintética: `pointerdown → RAF` sobre la pestaña activa. El
  callback precede al pintado y no incluye los manejadores de `click`. **No es
  INP real ni tiempo de respuesta visible de la interfaz**.

### Fuentes externas

`tiles.openfreemap.org` (teselas del mapa) y `gibs.earthdata.nasa.gov` (imagery satelital)
no dependen del despliegue. Por defecto se **bloquean idénticamente en base y candidata**
(ruta de Playwright + `Network.setBlockedURLs`): la comparación no mide el azar de
terceros. El mapa sigue existiendo (canvas y vistas) pero **sin teselas, y las capturas lo
muestran así** — no se finge un mapa completo. Con `--integracion-real` se permiten y el
informe lo registra aparte; los fallos de terceros nunca fallan la corrida.

## Contratos de CLI (exactos)

### medir_rendimiento.py (un despliegue)

```
python scripts/local/medir_rendimiento.py <BASE> <OUT_DIR> [filtros]
```

Posicionales obligatorios: `BASE` (URL del despliegue) y `OUT_DIR`. Filtros opcionales
(todos aceptan varios valores separados por coma o repitiendo la bandera):

```
--device movil|escritorio        (alias mobile|desktop; por defecto ambos)
--network normal|lenta            (alias 4g|3g|fast|slow; por defecto ambas)
--cpu 1|4                         (por defecto ambos)
--cache fria|caliente|offline     (alias fría|cold|warm; por defecto las tres)
--ruta ID | --route ID            (por defecto todas las de RUTAS)
--muestras N | --samples N        (mínimo 5, por defecto 5)
--timeout-s S                     (por paso: navegación + espera; por defecto 90)
--revision TEXTO
--hash-datos TEXTO                (repetible)
--integracion-real
--retraso-config-ms MS             (por defecto 0)
```

### comparar_rendimiento.py (base vs candidata)

```
python scripts/local/comparar_rendimiento.py \
  --base URL --candidata URL --out DIR \
  [--device movil] [--network lenta] [--cpu 4] [--cache fria] \
  [--ruta mapa] [--muestras 5] [--revision-base H] [--revision-candidata H] \
  [--hash-datos TEXTO] [--integracion-real] [--retraso-config-ms 0] [--timeout-s 90]
```

`--candidate` es alias de `--candidata`; el resto de banderas coincide con
medir_rendimiento.py. Cada muestra usa un contexto aislado, incluso con el
mismo origen. Las URL deben identificar revisiones distintas.

### Ejemplo de job de CI (porción manejable de la matriz)

```
python scripts/local/comparar_rendimiento.py \
  --base "$URL_BASE" --candidata "$URL_CANDIDATA" --out reporte/porcion-1 \
  --device movil --network normal --cpu 1 --cache fria \
  --revision-base "$SHA_BASE" --revision-candidata "$SHA_CAND" \
  --hash-datos "$HASH_DATOS" --samples 5
```

La matriz completa disponible en el CLI es grande. Desde la segunda tanda,
el workflow de PR ejercita dos dispositivos, red/CPU normales y caché fría,
con `/api/config` normal o retrasado 3.000 ms. El dispatch completo habilita
los ocho perfiles de dispositivo/red/CPU y las tres cachés, en jobs secuenciales.
El orquestador selecciona siete rutas; las demás requieren `--ruta`.
Eso no equivale a la matriz integral del encargo: los escenarios que siguen
pendientes no se dan por aprobados. Cada job conserva informes y capturas.

En el orquestador, el retraso se aplica con una espera asíncrona en el
servidor efímero, únicamente a `/api/config`, igual para base y candidata.
No detiene otras solicitudes y también alcanza los fetch del service worker
que llegan a la red. Los metadatos registran `retrasoConfigServidor: true`.
No modifica ni retrasa ninguna API de producción. `--verificar-config` añade
el recorrido funcional de configuración tardía contra el servidor candidato.

## API y arranque frío

```bash
python candidate/scripts/local/benchmark_api.py \
  --base-repo "$BASE_REPO" --candidate-repo "$CANDIDATE_REPO" \
  --out "$OUT" --samples 20 --sin-restauracion
```

El fixture común se genera en otro proceso usando la revisión base. Cada
ruta/escenario importa el backend en un proceso nuevo y abre una copia de ese
fixture, sin sembrar ni precalentar el territorio en el proceso medido. Las
tandas alternan base/candidata y candidata/base por ruta. El reloj API se fija
en `2026-11-01T12:00:00Z`; los UUID tienen prefijos estables.

Se informa primera llamada, arranque del lifespan y duración completa del
proceso (incluye importaciones, preparación, llamadas y cierre). No se
confunden esos intervalos. El escenario caliente conserva un calentamiento
explícito y veinte respuestas medidas. p95 usa rango más cercano (19.ª de
20), con p50, máximo, errores, SQL y llamadas externas sin parámetros.
La contienda escribe y agrupa detecciones reales en la base sintética,
sin evaluar ni enviar avisos. Sus cuerpos no se consideran comparables.

El tamaño API es el cuerpo decodificado de TestClient, no bytes de red.
Los hashes de cuerpos exactos y de campos estables se informan separados;
una diferencia invalida la comparación de latencia de esa ruta. El gate
caliente permanece en p95 ≤2.500 ms, al menos veinte muestras y cero errores.
La sonda de producción `medir_latencia.py` conserva sus tres GET por ruta.

La restauración opcional usa snapshots comprimidos en el límite del backend,
después del descifrado que haría el Worker. No mide cifrado, R2 ni recuperación
de extremo a extremo. El workflow inicial la declara no medida
(`--sin-restauracion`); no cambia frecuencia, durabilidad ni retención.

## Presupuestos

El workflow conserva los gates del build servido: ≤125 KiB gzip bloqueante
y ≤275 KiB gzip total. Informa además bytes crudos, gzip y hashes de todos los
assets, incluidos diferidos. Las pruebas vigentes mantienen el contrato
`web/data` de 4 MiB, shell y respuestas, y la carga 2.000 detecciones/200
incidentes en menos de cinco segundos. No se aumenta ningún tope.

### Salidas y códigos de retorno

- `medicion.json` / `comparacion.json`: se **reescriben tras cada muestra** (una corrida
  interrumpida deja el informe hasta ahí); `muestras.jsonl` / `muestras-base.jsonl` /
  `muestras-candidata.jsonl` acumulan una línea por muestra.
- Capturas comparables: mismo nombre de archivo en `capturas/` (medición) o
  `capturas/base/` y `capturas/candidata/` (comparación).
- `medicion.md` / `comparacion.md`: informe final con metadatos (revisiones, Chromium,
  Playwright, perfiles, hashes de datos provistos por CLI), medianas/peor por paso y
  validez con motivos.
- Códigos de retorno (ambos scripts): **0** = sin errores del producto y comparaciones
  válidas; **1** = errores del producto en alguna parte; **2** (solo comparar) =
  comparaciones invalidadas sin errores del producto.

## Implementado vs pendiente

### Implementado

- Matriz dispositivo × red × CPU × caché con contextos independientes por muestra (mínimo 5).
- Comparación base/candidata en la misma instancia de Chromium, pares alternos A/B y B/A.
- Tres pasos por ruta: URL profunda de golpe, navegación SPA desde la portada, reingreso.
- Contenido usable con selectores reales por vista; título, esqueleto y fallo explícito descartados.
- Caché fría/caliente/offline con preparación no medida (portada → SW listo → ruta).
- Errores JS/consola/HTTP/red/timeouts conservados y clasificados; medianas solo de completas; incompletas invalidan la comparación.
- Bytes por red vs caché con duplicados; CPU/TaskDuration y heap JS por CDP; tareas largas por paso; interacción sintética → RAF.
- Fuentes externas bloqueadas idénticamente por defecto; `--integracion-real` para medirlas de verdad.
- Informes JSON incrementales, Markdown y capturas comparables; filtros de CLI para jobs.

### No cubierto (no afirmar lo contrario)

- **Instalación real** (invitación/PWA) y **Safari**: solo Chromium headless.
- **Flujo de actualización del service worker** (nueva versión disponible, recarga): se mide siempre con el SW ya instalado o recién instalado, no la transición.
- **Respuesta visible de interacción e INP real**: solo se registra `pointerdown → RAF`.
- **Memoria de workers** (service worker incluido): las métricas CDP son del hilo principal.
- **Bytes decodificados por pedido** y **subrequests del SW fuera del target de página**: no alcanzan al instrumento.
- **`--retraso-config-ms` en el CLI independiente** solo alcanza cuando el SW todavía no controla la página (primer
  acceso): el fetch del SW puede pasar por debajo de la ruta de Playwright. Con caché
  caliente/offline su efecto es parcial; el retraso además serializa el tráfico
  concurrente durante la espera. Es una cobertura limitada, no un escenario de API lenta
  general.
- **Rutas que dependen de datos vivos**: `#/v/<token>` (enlace de familia) y
  `#/incendio/<id>` (necesita un incidente activo) no se miden por defecto.
- **Interacciones complejas** (formularios, reproducción de la reconstrucción hora a hora,
  gestos de la hoja): se mide navegación y render, no interacción profunda.
- **Sesiones largas, pestaña oculta, instalación incompleta y memoria acotada**:
  aún no hay sonda integral de esos escenarios.
- **Mapa/capa utilizable completa**: el criterio de Mapa mide el contenido de la
  hoja, no garantiza teselas, infraestructura, viento ni capas completas.
- **Comparación visual automática**: se conservan capturas, pero estos scripts
  no dictaminan equivalencia visual. La revisión habitual sigue cubriendo 320 px,
  accesibilidad, CSP y flujos en otro job.

## Verificación

Las pruebas de `tests/test_medir_rendimiento.py` (CI) cubren lo puro: matriz de perfiles,
mínimo de 5 muestras, orden alterno, reinicio por transición, resumen con medianas de
completas, conservación y clasificación de errores, validez de comparaciones, bytes
red/caché, filtros de CLI y alias. La corrida real con navegador la ejecuta el workflow
de GitHub contra los builds efímeros; la porción descrita también corre en PR.
No se ejecutan pruebas, builds, servidores ni navegadores en local.

### Línea base validada de la primera tanda

[PR #986](https://github.com/falopass/brasas/pull/986), commit candidato `1ea5162`,
base `fd9ab37`, [CI reproducible](https://github.com/falopass/brasas/actions/runs/45529952629):

- 70/70 muestras candidatas completas (siete rutas × cinco × dos dispositivos),
  cero errores de producto y comparaciones válidas.
- Ocho rutas API con cuerpos equivalentes en frío/caliente, veinte muestras
  calientes; peor p95 entre rutas: 109,629 ms, bajo el gate de 2.500 ms.
- Build servido: 121,7 KiB gzip bloqueante y 272,2 KiB total, bajo 125/275.
- Gate existente 2.000 detecciones/200 incidentes aprobado.
- [CI estándar](https://github.com/falopass/brasas/actions/runs/45529952768)
  y revisiones UX/seguridad aprobados.

Es una línea base de los escenarios declarados, no una mejora de rendimiento
ni aceptación de la matriz completa. La segunda tanda se compara contra
`358980d` (merge de la primera).
REND-02 completo sigue abierto.

### Resultado de la segunda tanda

[PR #987](https://github.com/falopass/brasas/pull/987), candidato `cd6ee70`,
base `358980d`, [CI reproducible](https://github.com/falopass/brasas/actions/runs/45553344799):

- Cuatro jobs (móvil/escritorio × `/api/config` normal y retrasada 3.000 ms),
  red/CPU normales, caché fría, cinco muestras: 7/7 comparaciones válidas en
  cada uno y cero errores de producto.
- Con retraso de 3.000 ms, acceso directo (mediana base → candidata): mi-zona
  3.521 → 533 ms en móvil y 3.514 → 538 ms en escritorio; las siete rutas
  bajan entre 84,6 % y 86,9 %. Con configuración normal la diferencia es
  pequeña (−15 % a +1 %).
- Pasos `desdePortada` y `reingreso` en escritorio: variación amplia con
  signo cambiante entre corridas (por ejemplo, mapa `desdePortada` +48 % sin
  retraso y −73 % con retraso; peores muestras de hasta 2,8 s). Con cinco
  muestras y sondeo de 80 ms no se afirma mejora ni regresión en esos pasos;
  se vuelven a medir en la tercera tanda. En móvil quedan dentro de ±5 %.
- Recorrido funcional con `/api/config` retenida (`config_check.py`): portada,
  modal de lugar, mapa y reporte usables antes de la llegada; foco, valores
  y Turnstile sin huérfanos tras ella; dos altas anónimas registradas y
  ningún envío prohibido. El fallo previo del harness se debía a una clave
  mal escrita en el registro de envíos y a leer `location` de la consola
  como objeto en lugar de dict; no a la app.
- API: cuerpos equivalentes y gate caliente aprobado (peor p95 caliente 88 ms).
- Build servido: 123,7 KiB gzip bloqueante y 274,9 KiB total, bajo 125/275,
  sin cambiar los topes.

La «Revisión en navegador» falla de forma intermitente en el recorrido por
teclado del control «Capas», también en `main` (`358980d`); pasó en el
candidato final. Queda anotado como inestabilidad previa sin corregir.
