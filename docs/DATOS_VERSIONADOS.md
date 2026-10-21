# Datos versionados: qué caduca, cómo se regenera y qué hace la sonda

`web/data/` guarda fotos de datos que la app lee como si fueran de hoy: totales de la
temporada, exposición por comuna, normales de lluvia, comunas prioritarias y la medida de
adelanto de BRASA. Si nadie los regenera, la interfaz sigue mostrando la foto vieja sin
avisar. AUTO-45 cubre ese hueco: una sonda semanal mide la edad declarada por cada archivo
(`fetched_at` o `generated_at`, en la raíz o dentro de `source`) y abre un issue con la
etiqueta «datos» cuando alguno vence.

Complementa a OPS-01 (`backend/freshness.py` + `monitoreo.yml`), que mira la ingesta viva;
esto mira los JSON publicados en el repo.

## La sonda

```bash
python scripts/local/revisar_datos_versionados.py            # tabla legible, sale 1 si hay vencidos
python scripts/local/revisar_datos_versionados.py --json     # salida JSON
python scripts/local/revisar_datos_versionados.py --hoy 2027-06-01   # fuerza la fecha de referencia
```

El workflow `.github/workflows/datos-versionados.yml` la corre cada lunes y a mano
(`workflow_dispatch`). Un archivo sale en uno de estos estados: **vigente**, **vencido**
(edad mayor que la caducidad), **sin reloj** (tiene política pero no declara fecha),
**exento** (lista explícita), **sin política** o **ilegible**. El código de salida es 1
solo si hay vencidos.

## Caducidad por archivo

| Archivo | Caduca a los | Se regenera con |
|---|---|---|
| `temporada-*.json` | 45 días | `python scripts/local/build_temporada_2526.py --refresh` |
| `calibracion.json` | 120 días | `python scripts/local/medir_adelanto.py` |
| `censo_2024.json` | 365 días | `python scripts/local/build_censo.py` |
| `rain_normals.json` | 365 días | `python scripts/local/build_rain_normals.py` |
| `interfaz.json` | 365 días | `python scripts/local/build_interfaz.py` |
| `snaspe.json` | 365 días | `python scripts/local/build_snaspe.py` |
| `historia-comunas.json` | 365 días | `python scripts/local/build_historia_comunas.py` |
| `incendios-nominados.json` | 365 días | `python scripts/local/build_incendios_nominados.py` |
| `prioritarias.json` | 365 días | A mano, cuando CONAF publique el listado oficial (el `note` del JSON explica qué falta) |
| `comunas.geojson`, `regiones.geojson`, `comunas-index.json` | 365 días | `python scripts/build_territory.py` (hoy no declaran fecha: salen «sin reloj») |

Exentos (se informan, no caducan): `cases.json` y `cases/*.json` (historia curada: cada caso
lleva sus propias fechas) y `persistent_hotspots.json` (cada punto declara su propio
`valid_from`/`valid_to`).

La tabla vive en `scripts/local/revisar_datos_versionados.py` (`CADUCIDAD_DIAS`, `EXENTOS`,
`REGENERA`) y el test `tests/test_revisar_datos_versionados.py` obliga a declararle una
política a cada dato nuevo que entre a `web/data/`.

## Qué hacer cuando la sonda avisa

1. Abre el issue «datos»: trae la tabla con cada archivo vencido y el comando que lo regenera.
2. Corre ese comando en local (algunos bajan datos de la fuente; `build_territory.py` pide
   los geojson de entrada de `caracena/chile-geojson`).
3. Revisa el diff del JSON —que cambie lo esperado y nada más—, súbelo en rama + PR.
4. Cierra el issue cuando el dato regenerado ya esté en `main`.

Casos borde:

- **Sin reloj**: el archivo tiene política pero no declara fecha. Agrégale `fetched_at` o
  `generated_at` (raíz o `source`) al generador que corresponda; hasta entonces la sonda no
  puede medirlo.
- **Sin política**: alguien agregó un JSON sin fila en `CADUCIDAD_DIAS` ni `EXENTOS`.
  Declárala en la misma PR que lo introduce; el inventario del test la exige.
- **Vencido pero no conviene regenerar** (p. ej. la fuente se cayó): comenta el porqué en el
  issue y ajústale la caducidad o muévelo a `EXENTOS` con motivo, nunca lo dejes morir en
  silencio.
