# Latencia de las páginas públicas (UX-15)

`scripts/local/presupuesto_peso.py` vigila cuántos **KB** baja un vecino;
`scripts/local/medir_latencia.py` vigila cuánto **tarda** en responder. Las dos
mitades del presupuesto de rendimiento: peso en cada commit, tiempo una vez al
día contra producción.

## Qué mide

El script hace GET a las páginas públicas (la portada de la SPA y las hojas
bajo `/web/`) y a las rutas públicas de la API que la app pide al abrirse
(`/api/health`, `/api/config`, `/api/status`, `/api/risk/<comuna>`,
`/api/incidents`, `/api/observations`, `/api/panorama`). Repite cada ruta N
veces (`--repeticiones`, por defecto 3) y anota el tiempo total de cada GET:
conexión, respuesta y descarga del cuerpo. Es solo lectura —una sonda—, la
misma regla que `smoke_produccion.py`.

Las rutas `/api/*` se miden en caliente: antes de las muestras el script
despierta el contenedor (duerme entre ciclos del cron y el arranque en frío
puede tardar minutos) y hace un GET de calentamiento por ruta, así que ni el
arranque ni la primera consulta con caches vacías cuentan como latencia. Las
páginas estáticas no se calientan: su miss de caché del borde sí se mide.
Lo que sí puede salir en la tabla es la contienda real: un GET que cae en
medio del ciclo de ingesta compite con él por el mismo proceso y se nota.

## Cada cuánto y con qué umbral

El workflow `.github/workflows/experiencia.yml` lo corre una vez al día
(13:07 UTC —a propósito lejos del minuto en punto, donde siempre cae un
ciclo de ingesta y la contienda infla el p95—) y a mano con
`workflow_dispatch`. El presupuesto es
**p95 ≤ 2500 ms** por ruta (`--umbral-ms`, por defecto 2500). Una ruta que no
respondió en ningún intento cuenta como peor que lenta. Si algo falla, el
script sale con 1, el run queda en rojo y el workflow abre o actualiza un
issue con la etiqueta «monitoreo» y la ruta más lenta en el título. La tabla
completa queda en el resumen del job (Actions → run → Summary).

## Cómo leer la tabla

| ruta | n | p50 | p95 | máx | borde | estado |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `/` | 3 | 140 ms | 150 ms | 150 ms | — | ok |
| `/api/incidents` | 3 | 2900 ms | 3100 ms | 3200 ms | hit,hit,miss | lenta |

- `n`: respuestas que llegaron de las N intentadas. Si `n` es menor, hubo
  fallos (timeout o HTTP ≠ 200) que el estado resume como `ok (k fallo(s))`.
- `p50`: la mitad de las respuestas fue más rápida que esto.
- `p95`: con 3 repeticiones es la peor de las tres; con más repeticiones es el
  percentil por rango más cercano. Es la columna del presupuesto.
- `máx`: el peor caso observado.
- `borde`: el estado de la caché del Worker por muestra (`hit`, `miss`,
  `stale` o `pass`, un valor por respuesta; `·` si la ruta no lo declara).
  Una muestra lenta con `miss` viajó hasta el contenedor; con `hit` o
  `stale` la demora está en el borde o en la red, no en el origen.
- `estado`: `ok`, `lenta` (p95 sobre el umbral) o `sin respuesta` con el último
  error.

## Si una ruta se pone lenta

1. **Caché del borde:** un miss del Worker hace que la página viaje hasta el
   contenedor; revisa `cf-cache-status` y los headers de caché de esa ruta.
2. **Peso de la vista:** si la página engordó, `python scripts/local/presupuesto_peso.py`
   y `python scripts/local/peso_arranque.py` dicen cuánto y dónde.
3. **La consulta:** si es una ruta `/api/…`, mira qué consulta la alimenta
   (`/api/status` muestra tiempos de ingesta y errores del ciclo) y si el
   payload creció (`tests/test_presupuestos_peso.py` fija techos de bytes).

## Uso local

```bash
python scripts/local/medir_latencia.py                                # producción
python scripts/local/medir_latencia.py --url http://127.0.0.1:8000    # tu servidor local
python scripts/local/medir_latencia.py --json latencia.json           # guarda la medición
python scripts/local/medir_latencia.py --dry-run --desde tests/data/latencia_muestra.json
```

`--dry-run` no toca la red: repite el informe y el veredicto sobre las muestras
de `--desde` (`{"ruta": [ms, ...]}` o la salida `--json` de una corrida
anterior), para ajustar umbrales o revisar una corrida vieja sin volver a
medir.
