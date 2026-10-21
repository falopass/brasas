# Informe mensual «Así fue el mes en incendios» (IDEA-04)

`scripts/local/informe_mensual.py` genera, con reglas y plantillas fijas (sin
modelos de lenguaje), un bloque por región pensado para radios comunitarias y
municipios: qué pasó en el mes en incendios, con la fuente de cada cifra al
pie. Es el hermano mensual del [boletín de 60 segundos](BOLETIN.md) (IDEA-05).

## Cómo correrlo

Con el servidor BRASA arriba (local con `python dev.py run --demo`, o el de
producción):

```bash
python scripts/local/informe_mensual.py --url http://127.0.0.1:8000              # las 16 regiones, mes en curso
python scripts/local/informe_mensual.py --url http://127.0.0.1:8000 --region Maule
python scripts/local/informe_mensual.py --url http://127.0.0.1:8000 --mes 2026-09  # un mes ya cerrado
python scripts/local/informe_mensual.py --url http://127.0.0.1:8000 --json        # [{"region","mes","texto","fuentes","comparacion","sin_comparacion"}]
```

Solo usa la librería estándar: corre con el Python del sistema, no hace falta el
`.venv`. Lee seis rutas del servidor indicado con `--url`:

- `/api/official-fires?hours=336` → incendios informados por CONAF, con su fecha
  de inicio y superficie.
- `/api/incidents?hours=336` → focos de calor que BRASA agrupó, con su estado y
  los sensores que los vieron.
- `/api/opendata/boton-rojo.json?days=14` → días con Botón Rojo de CONAF por
  comuna (historia y pronóstico vigente).
- `/api/risk` → avisos DMC de viento y calor **vigentes**, por comuna.
- `/api/risk/<comuna>/trend?weeks=1` → el comparador semanal: una consulta por
  cada comuna de la región (unas 30 en el Maule; por eso el informe completo de
  las 16 regiones demora varios minutos).
- `/api/status` → la marca de la última ingesta: la fecha de corte del informe.

Ejemplo de bloque real (Región del Maule, producción, 21 de octubre de 2026;
ese día el comparador aún no tenía la foto de la semana pasada y el bloque lo
declaró en vez de inventar una comparación):

> Maule, octubre de 2026: CONAF informó al menos 4 incendios y 9.7 hectáreas en
> octubre de 2026 (la API conserva 14 días: cifras desde el 7 de octubre). CONAF
> no declaró Botón Rojo en la región en los días que conserva el registro (desde
> el 17 de octubre). La DMC emitió 1 aviso que sigue vigente para la región (1
> de viento). BRASA agrupó al menos 3 focos de calor en la región: 3 controlados
> o extinguidos (la API conserva 14 días: cifras desde el 7 de octubre). Señal
> de los sensores ABI, VIIRS. Cómo viene la semana: el nivel más alto
> pronosticado es moderado, pero no hay pronóstico de la semana pasada guardado
> con qué comparar. Esta semana: limpia techos y canales, repasa el plan
> familiar de evacuación y, si ves fuego o humo, llama al 132 (Bomberos).
> Fuentes: CONAF (incendios), CONAF (Botón Rojo), DMC (avisos CAP), BRASA (NASA
> FIRMS y NOAA GOES) y BRASA (comparador de pronósticos), al corte del 21 de
> octubre a las 04:20.

Cuando la semana anterior sí está guardada, la línea compara: «Cómo viene la
semana: el nivel más alto pronosticado es alto. Frente al pronóstico de hace una
semana para estos mismos días, sube de nivel en 2 comunas, baja en 1 y se
mantiene en 27.»

## Qué mide cada línea

- **Incendios CONAF y hectáreas**: incendios con fecha de inicio dentro del mes
  que CONAF informa en su reporte público, y la suma de su superficie. La
  superficie es la que declara CONAF, no una estimación de BRASA.
- **Días con Botón Rojo**: días del mes en que CONAF declaró condición Botón
  Rojo en al menos una comuna de la región. Botón Rojo es un pronóstico de
  condiciones favorables: no significa que haya habido un incendio.
- **Avisos DMC**: avisos de viento o calor extremo de la Dirección
  Meteorológica de Chile que tocan comunas de la región y siguen vigentes. Un
  aviso que cubre varias comunas cuenta una sola vez.
- **Incidentes BRASA**: focos de calor que BRASA agrupó por primera vez en el
  mes, con su estado al corte («confirmado por CONAF», «controlado o
  extinguido», «sin confirmar», «descartado») y los sensores que los
  aportaron. Un foco es una agrupación de detecciones satelitales: puede ser
  un incendio, una quema o una industria; «confirmado» solo lo dice CONAF.
- **Cómo viene la semana**: el nivel de riesgo más alto pronosticado en las
  comunas de la región y, frente al pronóstico emitido hace una semana para los
  mismos días, en cuántas comunas el nivel sube, baja o se mantiene (comparador
  `/api/risk/<comuna>/trend?weeks=1`, agregado por comuna: cada comuna «sube» si
  su nivel máximo de la semana supera al que se pronosticaba una semana antes).
  Es contexto de la semana en curso, no del mes informado. En el JSON va en
  `comparacion` (con `fuente` y `corte`); cuando no alcanza, va `sin_comparacion`
  con la razón.
- **Cierre**: si CONAF pronostica Botón Rojo en los próximos días, el cierre es
  la prevención acorde; si no, es el recordatorio semanal de preparación y el
  132 de Bomberos.

## Qué NO mide (límites de la API pública)

El informe no inventa cifras: cuando la fuente no alcanza, el bloque lo dice en
vez de poner ceros.

- **Ventana de 14 días**: `/api/official-fires` e `/api/incidents` entregan a lo
  más los últimos 14 días, y el registro público de Botón Rojo conserva 14 días
  de historia más el pronóstico vigente. Corrido a mitad de mes, el informe
  dice «al menos N…» y «cifras desde el <día>»; para un mes ya cerrado y fuera
  de la ventana dice «sin datos de … para este mes». Para el cierre mensual
  completo hay que correrlo a más tardar el día 14 del mes siguiente.
- **La comparación es semanal, nunca «mes contra mes»**: la ventana no permite
  comparar un mes con otro, así que «Cómo viene la semana» compara el pronóstico
  vigente con el emitido siete días antes para los mismos días. El comparador
  solo funciona si `risk_snapshot` ya guardó la foto de hace una semana; si no
  existe — porque la función es reciente o la comuna no tenía pronóstico — el
  bloque dice «no hay pronóstico de la semana pasada guardado con qué comparar»
  en vez de comparar con nada.
- **DMC solo vigentes**: la DMC publica su lista vigente y BRASA la muestra tal
  cual; los avisos que ya vencieron no quedan guardados. El informe cuenta los
  vigentes emitidos en el mes, no el total histórico del mes.
- **No es estadística oficial**: es un resumen de lo que BRASA recolectó de las
  fuentes en la ventana. Cifras históricas completas de temporada están en
  CONAF-GEPRIF (ver `web/data/incendios-nominados.json` y `docs/FUENTES.md`).
- **No mide** víctimas, viviendas, evacuaciones ni causas de los incendios:
  BRASA no recoge esos datos. Para eso, SENAPRED y CONAF.
