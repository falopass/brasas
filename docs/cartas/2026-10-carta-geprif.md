# Borrador — Carta a GEPRIF-CONAF (OFI-03 / ALI-01)

> **Estado:** borrador para que Diego revise, firme y envíe. No enviada.
> **Destinatario:** Departamento de Estudios e Investigación, Gerencia de Protección contra Incendios Forestales (GEPRIF), CONAF — `dei.geprif@conaf.cl` (contacto declarado en los ítems públicos del hub `deigeprif.com`; ver `docs/research/fuentes-meteologix-geprif.md:48`).

---

**Asunto:** Autorización de uso con atribución — datos públicos de incendios y catálogo ArcGIS de GEPRIF — aplicación ciudadana BRASA Chile

Estimado equipo del Departamento de Estudios e Investigación de GEPRIF:

## 1. Quién escribe

Me llamo **[Nombre y apellido de Diego]**, y desarrollo **BRASA Chile**, una aplicación ciudadana sin fines de lucro que reúne datos públicos de satélites (NASA FIRMS, GOES-19), de CONAF y de modelos meteorológicos, y los acerca a la ciudadanía en palabras simples: dónde hay un incendio informado, qué riesgo hay en mi comuna y qué hacer. BRASA **no es un sistema oficial de alerta** ni habla en nombre de ninguna institución; así lo declaramos explícitamente en nuestros términos públicos (ver `docs/TERMINOS.md`, sección «BRASA no es un sistema oficial de alerta»).

## 2. Qué datos de ustedes usa hoy

- El reporte público de incendios **`reporte/incendios.csv`**, publicado en el repositorio `deigeprif/public` en GitHub (verificado en `docs/FUENTES.md:61`).
- El **Botón Rojo** de CONAF como referencia de nivel de alerta.
- Frecuencia de consulta: **cada 10 minutos**, con caché y degradación elegante si el servicio no responde. En todos los casos la aplicación **cita a CONAF como fuente** del dato, con enlace.

## 3. Qué solicito

1. **Autorización de uso con atribución** del CSV de incendios, del Botón Rojo y de las capas públicas del catálogo ArcGIS de la organización (`services5.arcgis.com/A1ELWse9bRAi2JiV`), listadas en el anexo. Observamos que algunos ítems del catálogo declaran «uso público con cita a CONAF» (p. ej. Zonas Interfaz y FIRMS; ver `docs/research/fuentes-meteologix-geprif.md:65`), pero la declaración no aparece en los servicios mismos, por lo que agradeceríamos confirmar su alcance capa por capa.
2. **Aviso de cambios de formato**: si cambian nombres de capa, columnas o URLs, un correo de aviso nos permite mantener el servicio sin interrupciones ni datos erróneos.
3. **Un contacto técnico** del equipo para coordinar consultas puntuales sobre los datos.

## 4. Qué ofrecemos a cambio

- **Validación de detección como dato abierto**: una comparación de cuántos minutos antes o después que el registro de CONAF detecta BRASA cada incendio vía satélite, publicada abiertamente. Puede servirles como una medición ciudadana e independiente de sus tiempos operativos (iniciativa ALI-01 del proyecto, `docs/BACKLOG_MAESTRO.md:483`).
- **Un aviso de seguridad por esta vía privada**: al revisar el catálogo público detectamos que **parte de sus servicios ArcGIS tiene habilitada la escritura anónima** (`allowAnonymousToUpdate`), una mala configuración que permite que cualquier persona modifique datos sin autenticación (`docs/research/fuentes-meteologix-geprif.md:82`). Preferimos informarlo aquí y no en público; con gusto compartimos los detalles concretos si los solicitan. BRASA solo realiza consultas de lectura (`Query`) y nunca escribirá en sus servicios.

## 5. Cierre

Agradezco el trabajo del departamento: la apertura de estos datos ya es hoy una contribución concreta a la ciudadanía. Quedo atento a cualquier orientación sobre condiciones de uso, y disponible para una llamada si resulta más expedito.

Sin otro particular, saluda atentamente,

**[Firma y nombre de Diego]**
BRASA Chile — proyecto ciudadano sin fines de lucro
Correo de respuesta: **[correo que Diego indique]**

---

## Anexo — Recursos de GEPRIF-CONAF que BRASA consulta o consultaría

| Recurso | Dónde está publicado | Estado en BRASA | Respaldo |
|---|---|---|---|
| `reporte/incendios.csv` (reporte de incendios de la temporada) | Repositorio `deigeprif/public` en GitHub | En uso hoy, cada 10 min | `docs/FUENTES.md:61` |
| Botón Rojo CONAF | Dashboard `41ee3c691359437aa9df2a09d7f6124e` | En uso hoy | `docs/research/fuentes-meteologix-geprif.md` §2, tabla del hub |
| `PI` — Probabilidad de ignición (capas `d0`–`d4`, grilla ~2 km) | `…/A1ELWse9bRAi2JiV/…/PI/FeatureServer` | Propuesta (OFI-02/OFI-18) | investigación §2, tabla catálogo |
| `HC`, `VV`, `HR`, `TP` — humedad de combustible, viento, humedad relativa, temperatura | mismo catálogo, patrón `…/<var>/FeatureServer` | Propuesta (OFI-02/OFI-18) | investigación §2, tabla catálogo |
| `Perimetro_final` — perímetros oficiales por incendio | `…/Perimetro_final/FeatureServer/0` | Propuesta (OFI-17) | investigación §2, tabla catálogo |
| `PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO` | `…/PERÍMETROS_HISTORICOS_2014_2024…/FeatureServer/0` | Propuesta (OFI-19) | investigación §2, tabla catálogo |
| `PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA` | `…/PUNTOS_DE_INICIO…/FeatureServer/0` | Propuesta (OFI-19) | investigación §2, tabla catálogo |
| `incendios_base` — puntos de la temporada en curso | `…/incendios_base/FeatureServer/0` | Respaldo del CSV | investigación §2, tabla catálogo |
| `firms` — detecciones satelitales con comuna y hora local | `…/firms/FeatureServer/0` | Propuesta (redundancia) | investigación §2, tabla catálogo |
| `incendios_totales_25_26.csv`, `firms.csv`, `incendios_coords.csv` | Repositorio `deigeprif/public`, carpeta `reporte/` | Propuesta (OFI-19) | investigación §2, tabla del repo |

*Nota: los nombres de servicio se transcriben tal como aparecen en la investigación del 19-10-2026 (`docs/research/fuentes-meteologix-geprif.md`). Las capas operativas internas del catálogo (maniobras, recursos, tracks) quedan expresamente fuera del alcance de esta solicitud.*

---

<!--
Fuentes de los datos citados en esta carta:
- Contacto dei.geprif@conaf.cl y oficialidad del hub: docs/research/fuentes-meteologix-geprif.md:48
- Declaración «uso público con cita a CONAF» limitada a dos ítems: docs/research/fuentes-meteologix-geprif.md:65
- Escritura anónima en parte del catálogo (tratamiento privado): docs/research/fuentes-meteologix-geprif.md:82
- CSV de incendios, frecuencia 10 min, falta de licencia: docs/FUENTES.md:61
- «No es un sistema oficial»: docs/TERMINOS.md:7
- OFI-03 (pedir permiso, avisos de cambio, contacto técnico): docs/BACKLOG_MAESTRO.md:297
- ALI-01 (ofrecer validación de detección): docs/BACKLOG_MAESTRO.md:483
-->
