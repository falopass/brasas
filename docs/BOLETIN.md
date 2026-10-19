# Boletín radial de 60 segundos (IDEA-05 / ALI-09)

`scripts/local/boletin.py` genera, con reglas y plantillas fijas (sin modelos de
lenguaje), el texto que una radio comunitaria puede leer al aire: un bloque por
región con el nivel de condiciones más alto, el Botón Rojo de CONAF, los incendios
activos informados por CONAF y el recordatorio del 132.

## Cómo correrlo

Con el servidor BRASA arriba (local con `python dev.py run --demo`, o el de
producción):

```bash
python scripts/local/boletin.py --url http://127.0.0.1:8000            # las 16 regiones, de norte a sur
python scripts/local/boletin.py --url http://127.0.0.1:8000 --region Maule
python scripts/local/boletin.py --url http://127.0.0.1:8000 --fecha 2026-10-19   # pronóstico de otro día
python scripts/local/boletin.py --url http://127.0.0.1:8000 --json     # [{"region","texto","palabras","fuentes"}]
```

Solo usa la librería estándar: corre con el Python del sistema, no hace falta el
`.venv`. Lee tres rutas del servidor indicado con `--url`:

- `/api/risk` → nivel de condiciones por comuna (Open-Meteo vía BRASA) y Botón Rojo (CONAF).
- `/api/official-fires` → incendios informados por CONAF con su estado oficial.
- `/api/incidents` → focos de calor agrupados por BRASA aún sin confirmar.

Si una fuente no responde, el bloque lo dice («sin datos de CONAF en este
momento») y sigue con las demás. Ninguna cifra se inventa: cada bloque termina
con «Fuente: CONAF (Botón Rojo e incendios) y Open-Meteo vía BRASA al HH:MM» y
nunca pasa de 90 palabras.

## Cómo leerlo al aire

- Un bloque son ~60 segundos a ritmo pausado. Lee el de tu región completo, tal
  cual está escrito: está redactado para voz, sin siglas ni símbolos.
- Lee la línea «Fuente: …» también: es lo que permite al oyente verificar cada
  cifra por sí mismo.
- «Nivel de condiciones» es el indicador meteorológico de BRASA (regla 30-30-30
  combinada con el FWI): describe qué tan favorables están las condiciones para
  que un incendio se propague. **No** es la probabilidad de que ocurra uno ni un
  incendio detectado.
- «Botón Rojo» es el pronóstico oficial de CONAF de condiciones favorables:
  tampoco significa que haya un incendio.
- «Foco de calor sin confirmar» es una agrupación de detecciones satelitales de
  BRASA: puede ser un incendio, una quema o una industria. Hasta que CONAF lo
  informe, se lee «sin confirmar».

## Qué NO se debe leer al aire

- Nada que BRASA no pueda sostener con su fuente: ni cifras de superficie que
  CONAF no haya publicado, ni estados («controlado», «extinguido») distintos de
  los oficiales, ni causas o responsables de un incendio (BRASA no los recoge).
- No conviertas un foco satelital en «incendio»: el texto ya usa las palabras
  correctas; no las «mejores» al leerlas.
- No agregues evacuaciones, cortes de ruta ni cifras de afectados: BRASA no los
  tiene y decirlo al aire sería inventarlo. Para eso, las fuentes oficiales son
  SENAPRED y CONAF.
- Si el bloque dice «sin datos de …», léelo así: informa que la fuente está
  caída, no que «no pasa nada».
