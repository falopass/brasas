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
python scripts/local/informe_mensual.py --url http://127.0.0.1:8000 --json        # [{"region","mes","texto","fuentes"}]
```

Solo usa la librería estándar: corre con el Python del sistema, no hace falta el
`.venv`. Lee cinco rutas del servidor indicado con `--url`:

- `/api/official-fires?hours=336` → incendios informados por CONAF, con su fecha
  de inicio y superficie.
- `/api/incidents?hours=336` → focos de calor que BRASA agrupó, con su estado y
  los sensores que los vieron.
- `/api/opendata/boton-rojo.json?days=14` → días con Botón Rojo de CONAF por
  comuna (historia y pronóstico vigente).
- `/api/risk` → avisos DMC de viento y calor **vigentes**, por comuna.
- `/api/status` → la marca de la última ingesta: la fecha de corte del informe.

Ejemplo de bloque (datos de demostración):

> Maule, octubre de 2026: CONAF informó al menos 2 incendios y 45.5 hectáreas en
> octubre de 2026 (la API conserva 14 días: cifras desde el 5 de octubre). CONAF
> declaró Botón Rojo en 2 días del mes (los días 8 y 12). La DMC emitió 2 avisos
> que siguen vigentes para la región (1 de calor extremo y 1 de viento). BRASA
> agrupó al menos 3 focos de calor en la región: 1 confirmado por CONAF, 1
> controlado o extinguido y 1 sin confirmar. Señal de los sensores ABI, VIIRS.
> Esta semana CONAF pronostica Botón Rojo en la región (los días 20): evita
> quemas, fogatas y maquinaria que eche chispas al aire libre. Fuentes: CONAF
> (incendios), CONAF (Botón Rojo), DMC (avisos CAP) y BRASA (NASA FIRMS y NOAA
> GOES), al corte del 19 de octubre a las 18:30.

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
- **DMC solo vigentes**: la DMC publica su lista vigente y BRASA la muestra tal
  cual; los avisos que ya vencieron no quedan guardados. El informe cuenta los
  vigentes emitidos en el mes, no el total histórico del mes.
- **No es estadística oficial**: es un resumen de lo que BRASA recolectó de las
  fuentes en la ventana. Cifras históricas completas de temporada están en
  CONAF-GEPRIF (ver `web/data/incendios-nominados.json` y `docs/FUENTES.md`).
- **No mide** víctimas, viviendas, evacuaciones ni causas de los incendios:
  BRASA no recoge esos datos. Para eso, SENAPRED y CONAF.
