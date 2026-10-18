# Síntesis y features priorizadas

> Cierre de la sesión de investigación del 18 de octubre de 2026. Cuatro documentos previos, una lista de features ordenada por valor ciudadano y coste, y una lista explícita de lo que la investigación recomienda **no** hacer.

## Los cuatro documentos

| Documento | Qué responde |
|---|---|
| [01-datos-oficiales.md](01-datos-oficiales.md) | Qué ofrecen SENAPRED, CONAF, DMC y NASA FIRMS, y qué se puede integrar de verdad |
| [02-30-30-30-y-fwi.md](02-30-30-30-y-fwi.md) | Qué sostiene el 30-30-30, qué sostiene el FWI y con qué datos se calcula |
| [03-mega-incendios-2017-2024.md](03-mega-incendios-2017-2024.md) | Cifras oficiales de los grandes incendios y disponibilidad de dato por comuna |
| [04-deteccion-temprana-comunitaria.md](04-deteccion-temprana-comunitaria.md) | Qué hacen otros países con el reporte ciudadano y qué conviene copiar |

## Cómo se priorizó

Tres criterios, en este orden:

1. **Sustento:** que la fuente sea oficial, pública y verificable en esta sesión. Una idea sin fuente no entra, por buena que suene.
2. **Riesgo:** legal y técnico. Un dato sin licencia o una API sin contrato sube el riesgo y baja la prioridad.
3. **Valor ciudadano:** cuánto cambia lo que la persona puede hacer. Un índice más preciso que no cambia ninguna decisión vale menos que un aviso que llega a tiempo.

Coste en días de una persona; es una estimación, no una medición.

## Lista priorizada

### P0 — Confianza y corrección (primer sprint)

| # | Feature | Qué cambia | Sustento | Coste | Riesgo |
|---|---|---|---|---|---|
| 1 | **Avisos DMC con contrato de datos**: deduplicar por `identifier`, respetar `onset`/`expires`, traducir el polígono a comunas, cachear la última versión válida y asumir que no hay SLA | Un aviso de viento o calor llega con geometría y vigencia, no como titular | [01](01-datos-oficiales.md), §3 | 1-2 días | Bajo: el emisor declara `public domain` |
| 2 | **Sello de procedencia en toda cifra**: organismo, fecha de corte, enlace y serie de correcciones (24→26; 137→138) | La vista Historia deja de discutir con la prensa | [03](03-mega-incendios-2017-2024.md), §3 y §5 | 1-2 días | Bajo |
| 3 | **Separar temporada, incendio y comuna**: 2017 y 2023 se rotulan como temporada; 2024 muestra 8.656,5 ha del complejo y 15.219,9 ha regionales | Se acaba la comparación falsa entre 570.000 ha y 8.656 ha | [03](03-mega-incendios-2017-2024.md), §1 | 2-3 días | Bajo |
| 4 | **Arrastre del DC del FWI**: inicializar la sequía profunda con la temporada anterior, no con 60 días | El riesgo de enero deja de subestimarse justo cuando importa | [02](02-30-30-30-y-fwi.md), §2.4 | 1-2 días | Bajo |
| 5 | **Percentiles locales del FWI y etiqueta «peligro meteorológico»**: el mismo FWI se lee distinto en una comuna húmeda y en una seca; nunca decir «riesgo» ni «probabilidad» | El número se vuelve comparable y honesto | [02](02-30-30-30-y-fwi.md), §5 y §6 | 2-3 días | Medio: requiere histórico por comuna |

### P1 — Producto (segundo sprint)

| # | Feature | Qué cambia | Sustento | Coste | Riesgo |
|---|---|---|---|---|---|
| 6 | **Reporte ciudadano con umbral y código de conducta publicado**: dos reportes independientes en 3 km y 30 minutos, o uno con evidencia satelital; revisión antes de publicar; corrección fechada | El vecino aporta sin convertir la app en un tablón de rumores | [04](04-deteccion-temprana-comunitaria.md), §2.1 y §6 | 3-5 días | Medio: moderación |
| 7 | **«Tu comuna en 2017»**: ingesta del XLSX por comuna con validación contra el total oficial de temporada; si no cuadra, se rechaza | Cada comuna puede ver su propia historia con cifra oficial | [03](03-mega-incendios-2017-2024.md), §2.1 | 3-4 días | Medio: el archivo no es una base de datos |
| 8 | **Incendios nominados desde el SHP por temporada** (2022-2024), con comuna, causa y superficie | La Historia pasa de tres casos a decenas de incendios con nombre | [03](03-mega-incendios-2017-2024.md), §2.2 | 3-4 días | Bajo: licencia de atribución |
| 9 | **Página de calidad de los datos**: latencia p50/p90 por fuente, ingestas fallidas, licencia de cada capa | La transparencia se vuelve una vista, no una promesa | [01](01-datos-oficiales.md), §5; [04](04-deteccion-temprana-comunitaria.md), §2.3 | 2-3 días | Bajo |

### P2 — Apostar después (tercer sprint o más)

| # | Feature | Qué cambia | Sustento | Coste | Riesgo |
|---|---|---|---|---|---|
| 10 | **Radar de respuesta oficial**: mediana de minutos entre `f_deteccion`, `f_aviso`, `f_despacho` y `f_arribo` por comuna, con datos de CONAF | Una pregunta que nadie responde con datos: cuánto tarda en llegar | [01](01-datos-oficiales.md), §2.2 | 3-5 días | Medio: el CSV no tiene licencia y solo cubre la temporada en curso |
| 11 | **API pública de solo lectura con licencia por fuente**: cada registro declara su origen y su licencia; los datos de CONAF no se relicencian | Terceros pueden auditar y reutilizar sin apropiarse de lo ajeno | [04](04-deteccion-temprana-comunitaria.md), §6.1 | 5-8 días | Medio: hay que separar licencias por capa |
| 12 | **GWIS como capa de contexto** (CC BY 4.0), nunca como alerta | Contexto global con crédito, sin duplicar el FWI propio | [04](04-deteccion-temprana-comunitaria.md), §6.4 | 1-2 días | Bajo |
| 13 | **Backtesting de FWI y 30-30-30** contra incendios observados por comuna y temporada | Convierte el índice en una afirmación contrastable, no en una fe | [02](02-30-30-30-y-fwi.md), §7 | 5-10 días | Medio: puede salir mal, y hay que publicarlo igual |

### Fuera de la lista: decisiones institucionales, no features

- **Autorización de CONAF** para redistribuir el CSV y las estadísticas (sin licencia declarada).
- **Convenio con SENAPRED** para acceder a sus alertas. Es la única vía legítima; la API es interna y autenticada.
- **Bot de Telegram y proveedor de SMS**, que dependen de presupuesto y de la persona dueña.

## Lo que la investigación recomienda no hacer

| No hacer | Por qué | Fuente |
|---|---|---|
| Scraping de las alertas de SENAPRED | Su API es AppSync con Cognito/IAM; no hay CAP ni términos. Una alerta de evacuación mal fechada es peor que no mostrarla | [01](01-datos-oficiales.md), §1 |
| Publicar el reporte ciudadano sin moderación | Ningún sistema revisado lo hace; el resultado son rumores con mapa | [04](04-deteccion-temprana-comunitaria.md), §3 |
| Invertir primero en cámaras o IA | Coste por hectárea desproporcionado para una app pequeña | [04](04-deteccion-temprana-comunitaria.md), §3 |
| Presentar el 30-30-30 como índice o probabilidad | La DMC dice que «no pronostica incendios forestales» y que es «información sin control de calidad»; la tesis de la UdeC midió cumplimiento nulo en Chile | [02](02-30-30-30-y-fwi.md), §1.2 y §1.4 |
| Sumar el XLSX por comuna sin validarlo | Sus totales dan 2,8 veces el total oficial de temporada: hay filas repetidas o subtotales | [03](03-mega-incendios-2017-2024.md), §2.1 |
| Reconstruir la historia desde el CSV rodante de CONAF | Cubre solo la temporada en curso (162 filas del 2026) y no tiene licencia | [01](01-datos-oficiales.md), §2.2 |
| Relicenciar datos de CONAF como si fueran propios | El repositorio de origen no declara licencia; la atribución es obligatoria y la titularidad no es de Brasas | [01](01-datos-oficiales.md), §2.2 |

## Hoja de ruta sugerida

- **Sprint A (2 semanas):** features 1 a 5. No añaden superficie visible; añaden confianza y corrigen el riesgo.
- **Sprint B (2-3 semanas):** features 6 a 9. Convierten la confianza en producto: reporte con umbral, Historia por comuna y página de calidad.
- **Sprint C (a partir de ahí):** features 10 a 13, más las tres decisiones institucionales.

## Por qué este orden

La investigación deja una idea que ordena todo lo demás: **Brasas no necesita más datos, necesita que cada dato diga de dónde viene, de cuándo es y qué no garantiza.** El 30-30-30 que la DMC no considera un pronóstico, el FWI que se calibró en Canadá, las cifras que cambian con el balance y un CSV sin licencia son el mismo problema visto desde cuatro ángulos. Las features 1 a 5 atacan ese problema; las demás lo aprovechan.

## Fuentes

Las de cada documento. Esta síntesis no introduce afirmaciones nuevas: solo ordena las que ya están citadas en los cuatro documentos.