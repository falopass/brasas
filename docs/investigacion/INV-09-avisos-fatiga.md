# INV-09 · Comprensión de avisos y fatiga en personas mayores

> Investigación para BRASA Chile. **Consulta:** 18 de octubre de 2026. **Alcance:** revisión de literatura y diseño de pruebas; no es una prueba con usuarios. Cada afirmación lleva su fuente. Lo que no se pudo verificar se marca **NO VERIFICADO**. Las recomendaciones de umbral se separan de la evidencia: son un presupuesto de prueba, no un número universal.

## Resumen ejecutivo

1. **No existe un número universal de avisos que una familia tolere.** La evidencia muestra que la fatiga depende de la frecuencia, la relevancia y el contenido del aviso, no solo del conteo. Por eso FIX-08 no puede resolverse con «tres avisos por semana» como si fuera una ley: hay que combinar reglas de relevancia, acción y repetición, y medir.
2. **La fatiga es real y tiene consecuencias:** desensibilización, queja y abandono del canal (opt-out). En personas mayores, las alertas previas que no terminaron en incendio son una razón explícita para retrasar la evacuación.
3. **Los términos de BRASA no están validados.** «Señal de calor», «posible incendio» y «Botón Rojo» son jerga interna o marcas institucionales; una persona mayor puede no entenderlos. El 53 % de los adultos chilenos está en nivel 1 o inferior de comprensión lectora, y las personas mayores pueden tener además menos familiaridad con las herramientas digitales de emergencia.
4. **Recomendación para FIX-08:** urgente solo con acción protectora clara y estado «posible» o superior; el resto es «aviso» sin push urgente. Tope inicial: 1 urgente por incidente y lugar, 1 urgente por lugar cada 24 h y 3 push por lugar cada 7 días, con excepción de un evento que escala. Medir con ALR-05 y ajustar.
5. **Guion UX-01:** 5 tareas, 5 personas mayores, 5 adultos y 3 expertos; SUS al final; criterios de éxito observables. El objetivo no es «que les guste», sino comprobar si entienden qué pasó, qué deben hacer y de dónde viene el dato.

## 1. Preguntas y método

**Preguntas**

- ¿Una persona mayor entiende «posible incendio», «señal de calor» y «Botón Rojo»?
- ¿Cuántos avisos por semana tolera antes de ignorarlos?
- ¿Qué umbral conviene para la persona mayor (FIX-08)?
- ¿Qué guion de 5 tareas permite probar la comprensión en UX-01?

**Método**

- Revisión de literatura académica y de organismos oficiales sobre fatiga de alertas, respuesta a advertencias y accesibilidad cognitiva.
- Revisión de estudios sobre personas mayores y evacuación por incendios.
- Revisión de guías de notificaciones y de pruebas de usabilidad.
- Traducción de la evidencia a reglas de producto y a un guion de pruebas.
- No se hizo una prueba con usuarios ni una encuesta chilena: eso es precisamente UX-01.

## 2. Qué dice la evidencia sobre la fatiga de avisos

### 2.1 La fatiga no es solo «demasiados avisos»

Un estudio reciente y directamente relevante sobre alertas públicas define la fatiga de advertencia como un fenómeno con tres partes:

- **Antecedentes:** frecuencia de las alertas, relevancia y contenido del mensaje.
- **Síntomas:** tensión mental, estrés emocional y fisiológico, fatiga evaluativa.
- **Consecuencias:** desensibilización, queja y abandono del canal (opt-out).

Fuente: Sutton y Wood, «Opting Out: Over-Alerting and Warning Fatigue in the Era of Wireless Emergency Alerts», *Journal of Contingencies and Crisis Management* 33(3): e70076, 2025, [DOI 10.1111/1468-5973.70076](https://doi.org/10.1111/1468-5973.70076). El resumen está verificado en [Crossref](https://api.crossref.org/works/10.1111/1468-5973.70076).

La consecuencia práctica es que **subir el número de avisos no es el único problema**. La frecuencia y la relevancia se combinan: un aviso frecuente pero irrelevante también cansa. Y un aviso relevante, con una acción clara y en el momento oportuno, puede justificar la interrupción.

### 2.2 La fatiga es un motivo documentado para descartar advertencias

La investigación australiana sobre incendios de interfaz encontró que la fatiga de advertencia es una razón principal por la que se descartan las advertencias y se subestima el riesgo de incendio. Además, la fatiga era más alta al comienzo de la temporada y disminuía durante la temporada, lo que sugiere que no es un simple contador acumulativo: también depende del contexto y de la experiencia previa.

Fuente: Bushfire CRC, «Warning fatigue is not a myth», 30 de marzo de 2014, <https://www.bushfirecrc.com/news/news-item/warning-fatigue-not-myth>; Fire Note 122, <http://bushfirecrc.com/sites/default/files/managed/resource/fire_note_122_low_res.pdf>.

### 2.3 En personas mayores, la fatiga retrasa la evacuación

Un estudio con 61 residentes mayores en tres zonas de alto riesgo de Australia del Sur encontró que **solo el 10 % seguiría el consejo de salir temprano** en un día de peligro catastrófico. Entre las razones para quedarse, los investigadores mencionan la fatiga de advertencia: las alertas pasadas que no terminaron en incendios fueron señaladas como razón para retrasar la evacuación. Los participantes también describieron la información como abrumadora y confusa, y muchos dependían de redes familiares y comunitarias más que de herramientas digitales.

Fuente: Flinders University, «Preparing for catastrophic fire danger days a challenge for many older Australians», 21 de marzo de 2025, <https://news.flinders.edu.au/blog/2025/03/21/preparing-for-catastrophic-fire-danger-days-a-challenge-for-many-older-australians/>.

**Implicación para BRASA:** el problema no es solo que la familia «ignore» el aviso; es que un aviso que no se entiende o que no se traduce en una acción concreta puede **retrasar** la acción correcta. La interfaz debe decir qué hacer, no solo que hay calor.

### 2.4 El volumen compite con todo lo demás

Un estudio de Telefonica Research encontró que los usuarios recibían una mediana de **56 notificaciones por día**; Nielsen Norman Group lo resume y advierte que las notificaciones mal diseñadas pueden llevar a desactivarlas o a borrar la aplicación.

Fuente: Nielsen Norman Group, «Five Mistakes in Designing Mobile Push Notifications», 18 de noviembre de 2018, <https://www.nngroup.com/articles/push-notification/>; Pielot, Vradi y Park, «Dismissed! A Detailed Exploration of How Mobile Phone Users Handle Push Notifications», MobileHCI 2018, [DOI 10.1145/3229434.3229445](https://doi.org/10.1145/3229434.3229445).

NN/g recomienda, entre otras cosas:

- no pedir permiso de notificaciones en el primer arranque;
- explicar qué contendrán las notificaciones;
- **no enviar ráfagas**: si hay más de cinco avisos a la vez, combinarlos en uno;
- no compartir contenido irrelevante;
- facilitar el apagado.

**Implicación para BRASA:** el aviso de BRASA no compite contra el silencio; compite contra decenas de notificaciones. La relevancia y la brevedad no son estética: son supervivencia del canal.

### 2.5 La accesibilidad cognitiva pide limitar interrupciones, salvo emergencias

La guía de accesibilidad cognitiva del W3C incluye el patrón «Limit Interruptions»: evitar interrupciones y dar a la persona «una forma fácil de controlar las interrupciones, los recordatorios y los cambios de contenido, salvo que los inicie la persona o impliquen una emergencia». También recomienda que la persona pueda limitar los tipos de contenido que la distraen.

Fuente: W3C WAI, «Cognitive Accessibility Design Pattern: Limit Interruptions», <https://www.w3.org/WAI/WCAG2/supplemental/patterns/o5p01-minimal-interruptions/>.

La misma guía incluye patrones aplicables a los textos de BRASA:

- «Keep Text Succinct» (texto breve): <https://www.w3.org/WAI/WCAG2/supplemental/patterns/o3p05-succinct-text/>.
- «Separate Each Instruction» (separar cada instrucción): <https://www.w3.org/WAI/WCAG2/supplemental/patterns/o3p09-separated-instructions/>.
- «Do Not Rely on Users Calculations or Memorizing Information» (no depender de la memoria): <https://www.w3.org/WAI/WCAG2/supplemental/patterns/o6p05-low-cognition/>.

**Implicación para BRASA:** la emergencia justifica la interrupción, pero no justifica la ambigüedad. Un aviso urgente debe tener una acción, no cinco.

### 2.6 La lectura en Chile

La Evaluación de Competencias de la Población Adulta (PIAAC) 2023 encontró que **el 53 % de los adultos chilenos (16 a 65 años) alcanzó el nivel 1 o inferior en comprensión lectora**, frente a un promedio de 26 % en la OCDE. Ese nivel indica baja competencia para integrar información y hacer inferencias con textos densos.

Fuente: OECD, «Evaluación de Competencias de la Población Adulta 2023: Chile», <https://www.oecd.org/content/dam/oecd/es/publications/reports/2024/12/survey-of-adults-skills-2023-country-notes_df7b4a60/chile_043083fb/dbf64059-es.pdf>; resumen en <https://www.oecd-ilibrary.org/es/publications/evaluacion-de-competencias-de-la-poblacion-adulta-2023_f79f56e3-es/chile_dbf64059-es.html>.

**Cuidado con la inferencia:** PIAAC cubre de 16 a 65 años, no a las personas de 65 y más. No se puede usar para decir «el 53 % de las personas mayores no entiende». Sirve para lo contrario: **incluso en la población general, un texto denso es una barrera**. En personas mayores, la barrera es mayor por visión, audición, memoria de trabajo y familiaridad digital (W3C COGA; Flinders, 2025).

### 2.7 Lo que la evidencia no permite afirmar

| Afirmación | ¿Se sostiene? | Comentario |
|---|---|---|
| «Una familia tolera X avisos por semana antes de ignorarlos» | **No** | No hay un estudio que fije un número universal; los estudios identifican mecanismos, no umbrales |
| «Más avisos siempre mejoran la seguridad» | **No** | La fatiga y la desensibilización pueden reducir la respuesta |
| «Los avisos de emergencia siempre se ignoran» | **No** | El problema es la relevancia y la acción, no la categoría «emergencia» |
| «Las personas mayores no usan tecnología» | **No** | El estudio de Flinders muestra heterogeneidad; muchos usan redes familiares y algunos usan teléfono; la barrera es la familiaridad y el diseño |
| «Basta con texto grande» | **No** | La comprensión depende de la estructura, el lenguaje, la memoria y la acción; el tamaño ayuda, pero no alcanza |

## 3. Comprensión de los términos de BRASA

No hay evidencia directa sobre «señal de calor», «posible incendio» o «Botón Rojo» en Chile. Lo que sí hay es evidencia sobre cómo se procesan los términos abstractos y la jerga:

- Las personas mayores pueden tener menor acceso a la información y menos familiaridad con herramientas digitales de emergencia (Flinders, 2025).
- La guía de accesibilidad cognitiva recomienda palabras claras, frases cortas, una instrucción por paso y no depender de la memoria (W3C COGA).
- «Botón Rojo» es una condición oficial de CONAF (ver [`docs/FUENTES.md`](https://github.com/falopass/brasas/blob/main/docs/FUENTES.md)); sin contexto, no dice qué es ni qué hacer. Es el mismo problema que FIX-23 señala para la sigla «BR».

**Hipótesis para UX-01 (a confirmar, no afirmar):**

1. «Señal de calor» se interpreta como «hay un incendio» o como «algo de calor», no como «detección satelital no confirmada».
2. «Posible incendio» se interpreta como «puede haber un incendio» o como «incendio probable»; la diferencia con «confirmado» no es evidente.
3. «Botón Rojo» se interpreta como un botón de la aplicación o como una alerta de la aplicación, no como una condición oficial de CONAF.
4. «Urgente» se interpreta como «debo evacuar ya» aunque el aviso sea preventivo.

Estas hipótesis son el corazón de UX-01. Si se confirman, el texto debe cambiar antes de la temporada.

## 4. Recomendación de umbral para FIX-08

### 4.1 Principios

1. **Acción:** un aviso urgente debe tener una acción protectora concreta. Si no hay acción, no es urgente.
2. **Relevancia:** el aviso debe ser sobre el lugar guardado, no sobre la comuna entera ni sobre un incidente lejano.
3. **Novedad:** no se repite el mismo aviso si no cambió el estado ni la acción.
4. **Canal:** el push es para lo urgente; la bandeja y el resumen semanal son para el resto.
5. **Control:** la persona puede pausar los avisos no urgentes y elegir el canal; la emergencia no se pausa.
6. **Medición:** cada regla se evalúa con ALR-05 («¿te sirvió?») y con UX-01.

### 4.2 Regla propuesta (v0)

| Nivel | Cuándo se usa | Push | Tope | Texto base |
|---|---|---|---|---|
| **Urgente** | Incidente en «posible» o superior **y** una acción protectora clara: a ≤ 5 km del lugar, o viento hacia el lugar, o incendio oficial de CONAF a ≤ 5 km, o evacuación ordenada | Sí, con sonido y persistencia | 1 por incidente y lugar; 1 por lugar cada 24 h; 3 push totales por lugar cada 7 días | «Actúa ahora: posible incendio a 3 km. Si ves fuego, llama al 130. Si la autoridad ordena evacuar, sal ahora.» |
| **Aviso** | Detección confiable dentro del radio, sin acción protectora inmediata | No por defecto; queda en la bandeja; como máximo 1 push al día si la persona lo activó | 3 por lugar cada 7 días | «El satélite vio calor a 8 km. Puede ser una quema o un incendio pequeño. Mantente atento.» |
| **Riesgo** | Botón Rojo, 30-30-30 alto o aviso DMC que toca el lugar | Solo si la persona lo activó; preferir resumen semanal | 1 por día; 1 resumen semanal | «Hoy hay riesgo alto en tu comuna. Evita cualquier chispa.» |
| **Quema conocida** | Quema autorizada identificada | No | — | Etiqueta en la bandeja: «Puede ser una quema autorizada» |
| **Informativo** | Cambio de estado, control, novedades | No | — | Bandeja o resumen |

**El tope no se aplica a un evento que escala.** Si un incidente pasa de «posible» a «confirmado» y hay una nueva acción, se puede enviar un segundo urgente. Lo que se evita es la repetición del mismo aviso y el empuje de lo no urgente.

### 4.3 Por qué 3 por semana y no otro número

No hay evidencia para un número universal. El 3/7 es un **presupuesto de prueba**, elegido por tres razones:

- Es mucho más bajo que el volumen cotidiano (56 notificaciones/día) y obliga a priorizar.
- Permite cubrir una semana de temporada con pocos eventos relevantes sin convertir el canal en ruido.
- Es medible: si el 3/7 produce quejas, opt-out o «no me sirvió», se baja; si deja eventos importantes sin avisar, se sube.

**Una familia no es un usuario.** Si cuatro miembros reciben el mismo aviso, el volumen familiar es cuatro veces el volumen por persona. El tope debe medirse por lugar y por persona, y el modo familia no debe duplicar el envío a quien ya recibió el mismo aviso por el lugar compartido. Es una implicación de diseño, no un hallazgo de la literatura.

**Confianza:** media-baja para el número; alta para los principios (acción, relevancia, novedad, control). El número debe validarse en UX-01 y en la temporada.

### 4.4 Reglas de texto

- **Una acción por aviso.** Si hay que evacuar y llamar, la acción principal es evacuar; el teléfono va como apoyo.
- **Qué pasó, dónde, cuándo y qué hacer.** En ese orden, no al revés.
- **Fuente y hora.** «Sensor VIIRS, 16:40. No es confirmación oficial.»
- **Incertidumbre explícita.** «Puede ser un incendio; CONAF no lo confirmó.»
- **Sin jerga.** Nada de «anomalía», «píxel», «FRP», «detección» en el nivel sencillo.
- **Botón Rojo siempre con CONAF y con explicación.** «CONAF declaró Botón Rojo: hoy es muy fácil que se inicie un incendio.»
- **Nunca decir “confirmado” sin CONAF.** Es la regla del repositorio y la única forma de no confundir a la familia.

### 4.5 Textos propuestos (sencillo / técnico)

| Concepto actual | Problema | Sencillo | Técnico |
|---|---|---|---|
| «Señal de calor» | Suena a incendio o a calor ambiental | «El satélite vio calor» | «Detección de foco térmico (VIIRS/GOES), sin confirmación oficial» |
| «Posible incendio» | No queda clara la incertidumbre | «Puede ser un incendio» | «Incidente en estado posible: detección satelital, sin reporte oficial» |
| «Urgente» | Puede leerse como «evacuar ya» | «Actúa ahora» | «Nivel urgente: acción protectora recomendada» |
| «Aviso» | No dice qué hacer | «Atento» | «Nivel aviso: seguimiento, sin acción inmediata» |
| «Riesgo alto» | Abstracto | «Hoy es fácil que se inicie un incendio» | «Índice de riesgo alto (FWI/30-30-30)» |
| «Botón Rojo» | Marca institucional sin contexto | «Botón Rojo de CONAF: riesgo alto» | «Botón Rojo CONAF: condición oficial de riesgo» |
| «BR» | Sigla interna | «CONAF» + ícono de botón | «Botón Rojo CONAF» |
| «Anomalía» | Jerga | «Primera detección» | «Detección inicial sin persistencia» |
| «Confirmado» | Se usa mal | «CONAF confirmó el incendio» | «Incendio confirmado por CONAF» |

## 5. Guion de 5 tareas para UX-01

### 5.1 Participantes y logística

| Grupo | N | Perfil | Qué se busca |
|---|---|---|---|
| Personas mayores | 5 | 65 años o más, mix de hombres y mujeres, con y sin experiencia con aplicaciones; al menos 2 que vivan solas o con apoyo familiar | Comprensión, legibilidad, miedo, confianza, uso del teléfono |
| Adultos | 5 | 25 a 64 años, cuidadores o familiares de personas mayores | Comparación de comprensión y de carga |
| Expertos | 3 | Emergencias, gerontología o UX/accesibilidad | Riesgo de falsa alarma, precisión, accesibilidad |

**Justificación del tamaño:** con 5 usuarios por grupo se descubre la mayor parte de los problemas de usabilidad; con grupos distintos, 3 a 4 por grupo es suficiente para cubrir la diversidad. Fuente: Nielsen, «Why You Only Need to Test with 5 Users», 18 de marzo de 2000, <https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/>.

**Duración:** 60 a 75 minutos por sesión. **Materiales:** build de demostración con datos falsos, teléfono de prueba, tarjetas de escenario, hoja de registro, consentimiento. **No usar** datos reales de personas ni incidentes reales.

### 5.2 Reglas de moderación

- Explicar que se prueba la aplicación, no a la persona.
- Pedir que piense en voz alta; no corregir; no dar pistas.
- Usar preguntas abiertas: «¿Qué crees que pasó?», «¿Qué harías ahora?», «¿De dónde crees que viene este dato?».
- Si la persona se angustia, detener la tarea y ofrecer una pausa.
- Registrar citas textuales y conducta observable; no interpretar en el momento.
- Grabar solo con consentimiento; si no hay consentimiento, tomar notas.

### 5.3 Las cinco tareas

| # | Tarea | Escenario y consigna | Criterio de éxito | Qué observar |
|---|---|---|---|---|
| **1** | **Guardar la casa de mi mamá** | «Tu mamá vive sola en [comuna]. Quieres que BRASA te avise si hay fuego cerca. Guarda su casa y dime qué datos quedaron guardados.» | Guarda el lugar; encuentra cómo marcar «persona mayor»; explica para qué sirve; encuentra cómo borrarlo | ¿Entiende el consentimiento? ¿La marca «persona mayor» la estigmatiza? ¿Sabe que los avisos son aparte? |
| **2** | **Entender un aviso urgente** | Mostrar un push simulado: «Actúa ahora: posible incendio a 3 km de la casa de tu mamá». «¿Qué pasó? ¿Qué harías? ¿De dónde viene este aviso?» | Dice que el satélite vio calor y que no está confirmado; identifica una acción (llamar al 130, prepararse, salir si la autoridad lo ordena); no dice «BRASA confirma» | ¿«Posible» se entiende? ¿«Urgente» paraliza o activa? ¿Busca el teléfono? ¿Mira la hora/fuente? |
| **3** | **Decidir si evacuar** | «La autoridad ordenó evacuar tu comuna. BRASA muestra un incendio cerca. ¿Qué haces primero?» | Sigue la orden oficial; sabe que BRASA no es autoridad; tiene a mano 130/132 y un punto de encuentro | ¿Espera una confirmación de BRASA? ¿Cree que BRASA puede ordenar evacuar? ¿Sabe qué llevar? |
| **4** | **Compartir con la familia** | «Quieres que tu hermana reciba los avisos de la casa de tu mamá. Comparte el lugar con ella y explícale qué va a ver.» | Comparte el enlace o token; explica qué datos ve la familia y cuáles no; encuentra cómo revocar | ¿Cree que la familia verá la condición médica o la marca «necesita ayuda»? ¿Entiende el token? ¿Sabe revocar? |
| **5** | **Leer el riesgo de hoy** | «Abre el riesgo de tu comuna. ¿Qué significa para ti? ¿Por qué está así? ¿Qué harías hoy?» | Explica el nivel en sus palabras; encuentra el «por qué» (calor, viento, humedad, Botón Rojo); identifica una acción | ¿Lee el color solo o también el texto? ¿Entiende «Botón Rojo»? ¿Confunde riesgo con incendio activo? |

### 5.4 Guion de preguntas por tarea

Después de cada tarea, preguntar:

1. ¿Qué crees que pasó?
2. ¿Qué harías ahora, en los próximos 10 minutos?
3. ¿De dónde crees que viene este dato? ¿Es oficial?
4. ¿Qué te faltó para decidir?
5. ¿Qué cambiarías del texto?

No preguntar «¿te gustó?» antes de las preguntas de comprensión: la simpatía no es el objetivo.

### 5.5 Métricas

| Métrica | Escala | Cómo se registra |
|---|---|---|
| Éxito de la tarea | 0 = no logra; 1 = logra con ayuda; 2 = logra solo | Observación |
| Comprensión | 0 = incorrecta; 1 = parcial; 2 = correcta | Respuesta a «¿qué pasó?» y «¿qué harías?» |
| Confianza | 1 a 5 | «¿Qué tan seguro estás de lo que harías?» |
| Tiempo | Segundos | Cronómetro desde la consigna hasta la acción |
| Errores | Conteo y tipo | Toque equivocado, abandono, duda prolongada |
| Citas | Texto | Hoja de registro |

### 5.6 SUS y cierre

Al final, aplicar la System Usability Scale (SUS): 10 ítems, escala de 1 a 5, puntaje de 0 a 100. Fuente: Brooke, «SUS: A “Quick and Dirty” Usability Scale», en *Usability Evaluation in Industry*, 1996. No usar un corte universal: comparar entre grupos y contra una línea base propia.

Cerrar con:

- ¿Qué fue lo más difícil?
- ¿Qué aviso te haría apagar las notificaciones?
- ¿Qué necesitarías para confiar en BRASA?
- ¿Qué le dirías a una persona mayor que empieza?

### 5.7 Análisis y entrega

- Agrupar hallazgos por tarea y por tema (lenguaje, confianza, privacidad, acción).
- Priorizar por frecuencia × impacto: un problema que impide la acción correcta es crítico, aunque aparezca una vez.
- Registrar en `docs/USUARIOS.md` con citas anonimizadas, fecha, perfil y versión del build.
- Producir una lista de cambios de texto y de flujo, no solo un informe.
- Repetir con 5 nuevos usuarios después de los cambios; no mezclar la primera y la segunda ronda en el mismo análisis.

## 6. Qué medir durante diciembre (ALR-05)

| Métrica | Definición | Uso |
|---|---|---|
| Avisos por lugar y semana | Push enviados / lugares activos / semana | Ver si el volumen se dispara |
| Apertura | Avisos abiertos / enviados | Señal de relevancia, no de calidad |
| «Me sirvió» | Sí / no / era una quema | Calidad percibida |
| «Era una quema» | Falsos positivos de quema | Ajustar la regla de quema |
| Opt-out | Personas que desactivan push / activas | Señal de fatiga |
| Tiempo hasta abrir | Minutos desde el push | Urgencia real |
| Avisos urgentes por incidente | Repeticiones | Detectar duplicados |

**Umbrales de alarma para el equipo (propuesta):**

- Si más del 20 % de los avisos respondidos son «no me sirvió», revisar la regla de relevancia.
- Si el opt-out supera el 5 % en una semana, pausar los avisos no urgentes y revisar.
- Si un mismo incidente genera más de 2 push al mismo lugar, corregir la deduplicación.
- Si menos del 50 % de los urgentes se abren en 10 minutos, revisar el texto y el horario.

Estos umbrales son de gestión, no de ley; se ajustan con datos.

## 7. Fuentes consultadas (18 de octubre de 2026)

| Fuente | URL | Fecha | Qué sostiene |
|---|---|---|---|
| Sutton y Wood, *Opting Out* | <https://doi.org/10.1111/1468-5973.70076> | 2025 | Definición y mecanismos de la fatiga; frecuencia, relevancia y contenido |
| Crossref, metadatos del artículo | <https://api.crossref.org/works/10.1111/1468-5973.70076> | Consultado 18-oct-2026 | Resumen verificado |
| Bushfire CRC, «Warning fatigue is not a myth» | <https://www.bushfirecrc.com/news/news-item/warning-fatigue-not-myth> | 30-mar-2014 | La fatiga como razón para descartar advertencias |
| Bushfire CRC, Fire Note 122 | <http://bushfirecrc.com/sites/default/files/managed/resource/fire_note_122_low_res.pdf> | 2014 | Síntesis de la tesis de Mackie |
| Flinders University | <https://news.flinders.edu.au/blog/2025/03/21/preparing-for-catastrophic-fire-danger-days-a-challenge-for-many-older-australians/> | 21-mar-2025 | Personas mayores, fatiga y retraso de evacuación |
| Nielsen Norman Group, push notifications | <https://www.nngroup.com/articles/push-notification/> | 18-nov-2018 | 56 notificaciones/día; ráfagas; relevancia; apagado |
| Pielot, Vradi y Park, *Dismissed!* | <https://doi.org/10.1145/3229434.3229445> | 2018 | Estudio de notificaciones móviles |
| W3C, Limit Interruptions | <https://www.w3.org/WAI/WCAG2/supplemental/patterns/o5p01-minimal-interruptions/> | 2021 | Control de interrupciones; excepción de emergencia |
| W3C, Cognitive Accessibility Guidance | <https://www.w3.org/WAI/WCAG2/supplemental/> | 2021 | Patrones de texto claro, instrucciones separadas y memoria |
| OECD, PIAAC 2023 Chile | <https://www.oecd.org/content/dam/oecd/es/publications/reports/2024/12/survey-of-adults-skills-2023-country-notes_df7b4a60/chile_043083fb/dbf64059-es.pdf> | 2024 | 53 % en nivel 1 o inferior en comprensión lectora |
| Nielsen, 5 users | <https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/> | 18-mar-2000 | Tamaño de muestra para pruebas de usabilidad |
| Brooke, SUS | *Usability Evaluation in Industry*, 1996 | 1996 | Escala de usabilidad de 10 ítems |

## 8. Límites de esta investigación

- **No hay un estudio chileno** sobre cuántos avisos tolera una familia. La respuesta honesta es que no se sabe; UX-01 y ALR-05 deben medirlo.
- **No hay un número universal** en la literatura. Los estudios identifican frecuencia, relevancia y contenido como factores; no fijan un umbral.
- **La muestra de UX-01 es cualitativa**, no representativa. Cinco personas por grupo sirven para descubrir problemas, no para estimar prevalencia.
- **La literatura es de Australia, Estados Unidos y Europa.** La respuesta a la autoridad, la desconfianza institucional y el uso de WhatsApp en Chile pueden cambiar los resultados.
- **PIAAC no cubre a las personas de 65 y más.** Se usa como contexto de lectura de la población adulta, no como dato específico de personas mayores.
- **Los textos propuestos no están probados.** Son hipótesis de diseño para UX-01; no se deben publicar como «mejores» sin la prueba.
- **El umbral 3/7 es un presupuesto de prueba**, no una recomendación basada en evidencia causal. Se debe ajustar con datos de la temporada.
