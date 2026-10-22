# INV-28 · Margen de 0,16° en la frontera: cuántos focos entran

> **Actualización (2026-10-20):** se midió contra producción y se eligió la opción 2: el filtro usa `TERRITORY_TOLERANCE_DEG = 0,03°`. El resto de este informe conserva la medición original sobre la base de demo.

> **Fecha original:** 2026-10-20. **Fuente original:** `data/demo/work.db`. **No se cambió el filtro en ese momento:** `COASTAL_TOLERANCE_DEG = 0,16` seguía igual.

> **Medido sobre la base de demo; repetir contra producción.** La base de demo tiene un solo incidente de ejemplo en Quilpué, así que no alcanza para medir la frontera. El número que decide es el de `data/work.db` o un respaldo de producción.

## Metodología

Para cada detección de `work.observations` (o de la lista JSON):

1. Se calcula la distancia al territorio chileno como la distancia euclidiana en grados entre el punto y la unión de las comunas BCN (`unary_union` + `Point.distance`).
2. Se convierte a km con la latitud del punto: `111,32 × cos(lat)` km por grado. Es la escala local de longitud; la frontera corre de norte a sur, que es la dirección que importa.
3. Se clasifica en tramos: `dentro` (0 km), `0–1`, `1–2`, `2–5`, `5–10`, `10–18` y `más de 18 km`.
4. La comuna del listado es la guardada en `comuna_code`; si es null, se muestra la que asignaría el filtro con 0,16°.

Sin red: la base se copia a un temporal y se abre en solo lectura. `--limit N` mide las N filas más recientes (en el JSON, las primeras N).

## Resultado

| Fuente | dentro | 0–1 | 1–2 | 2–5 | 5–10 | 10–18 | más de 18 km | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GOES19_FDCF | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 12 |
| VIIRS_* | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| **Total** | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 14 |

## Medición contra producción (60 días)

**Fuente:** `GET /api/explore?zone=chile&mode=historical`, 6 ventanas de 10 días entre 2026-08-22 y 2026-10-20 (3.447 detecciones FIRMS NRT dentro del margen de 0,16°). Para cada punto se comparó `Territory.locate` con 0,16° y con 0,03°.

| Franja | Detecciones | Al este de la comuna más cercana | En la costa |
|---|---:|---:|---:|
| 0,03–0,16° | 46 | 45 | 0 |

- 45 de las 46 caen al este del polígono: Pica y Colchane (Bolivia), Putre (Bolivia/Perú), Alto Biobío, Lonquimay, Lago Verde y San Pedro de Atacama (Argentina).
- La restante es un borde este-oeste en Lago Verde, a 7,3 km del polígono; no es un foco costero y no se pudo clasificar como chileno o argentino sin la línea internacional.
- Muestra de 14 días de `/api/observations`: 1 punto FIRMS en la franja, a 10,3 km dentro de Bolivia, que con 0,16° se rotulaba `Pica`.
- **Decisión:** opción 2, `TERRITORY_TOLERANCE_DEG = 0,03°`. Se pierde como máximo ~3,3 km de margen costero; en 60 días no se perdió ningún foco costero. La opción 1 no se justifica con esta evidencia.

**Límites:** la medición es de FIRMS NRT (el archivo SP tarda meses); GOES no usa esta constante. `/api/observations` solo permite 14 días. La distancia y el lado se midieron contra el polígono comunal BCN, no contra la línea internacional.

### Los diez puntos más alejados

| # | Fuente | Lat | Lon | km | Comuna |
|---:|---|---:|---:|---:|---|
| 1 | GOES19_FDCF | -33.1120 | -71.3810 | 0.0 | Quilpué |
| 2 | GOES19_FDCF | -33.1080 | -71.3840 | 0.0 | Quilpué |
| 3 | GOES19_FDCF | -33.1040 | -71.3870 | 0.0 | Quilpué |
| 4 | GOES19_FDCF | -33.1000 | -71.3900 | 0.0 | Quilpué |
| 5 | VIIRS_* | -33.0960 | -71.3930 | 0.0 | Quilpué |
| 6 | GOES19_FDCF | -33.0920 | -71.3960 | 0.0 | Quilpué |
| 7 | GOES19_FDCF | -33.0880 | -71.3990 | 0.0 | Quilpué |
| 8 | GOES19_FDCF | -33.0840 | -71.4020 | 0.0 | Quilpué |
| 9 | GOES19_FDCF | -33.0800 | -71.4050 | 0.0 | Quilpué |
| 10 | GOES19_FDCF | -33.0760 | -71.4080 | 0.0 | Quilpué |

## Lectura

- Total: 14 detecciones.
- No hay detecciones fuera del territorio en esta muestra: el margen no se puede medir con estos datos.
- Base de demo: el número no es representativo; repetir contra producción.

## Tres recomendaciones

### 1. Dejar la tolerancia en 0,16° y marcar el borde

**Qué se gana:** no se pierde ninguna isla, fiordo ni píxel costero; la ingesta no cambia y el borde queda medido y visible para decidir después.

**Qué se pierde:** los focos de Argentina, Bolivia y Perú siguen entrando y contándose como chilenos; el número no baja, solo se etiqueta.

### 2. Bajarla a 0,03° (~3,3 km)

**Qué se gana:** corta la mayor parte de la franja: los focos a más de ~3 km del territorio dejan de entrar, y con ellos buena parte del ruido extranjero.

**Qué se pierde:** la costa simplificada y los fiordos del sur vuelven a perder píxeles válidos; islas pequeñas y bordes costeros pueden quedar fuera. Antes de adoptarla hay que revisar la costa, que es la razón original de la tolerancia.

### 3. Separar la tolerancia de costa y de frontera

**Qué se gana:** 0,16° donde hace falta (costa, fiordos, islas) y 0,03° en el borde terrestre; conserva lo bueno de las dos anteriores.

**Qué se pierde:** más complejidad: hace falta una geometría de frontera o una prueba de distancia al borde terrestre, mantenerla y probarla; hay riesgo de error en los tripoints y en la costa-frontera del sur.

La decisión se tomó el 2026-10-20 con la medición de 60 días: opción 2, `TERRITORY_TOLERANCE_DEG = 0,03°`.

## Cómo repetir contra producción

```bash
python scripts/local/medir_margen_frontera.py --db data/work.db \
    --md docs/investigacion/INV-28-margen-frontera.md
```

Con un respaldo de producción, `--db respaldo-work.db`. Para una muestra rápida, `--limit 50000`.

El script conserva 0,16° para reproducir la medición original; el filtro vigente es `TERRITORY_TOLERANCE_DEG = 0,03°`.

## Límites

- La distancia se mide al polígono de comunas BCN, no a la línea internacional: la generalización del polígono puede dejar dentro puntos que en el terreno son argentinos, y al revés.
- La conversión `111,32 × cos(lat)` es la escala de longitud; para puntos al norte o al sur del territorio subestima la distancia (hasta ~5% en el extremo norte y más en el sur). Los tramos son gruesos, así que el efecto no cambia la lectura.
- `comuna_code` se guarda con la tolerancia por omisión de `Territory.locate` (0,01°), no con 0,16°; por eso muchos puntos del margen quedan sin comuna guardada. El listado muestra la comuna que asignaría el filtro.
- La base de demo no alcanza: hay que repetir contra producción.
