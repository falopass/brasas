---
id: OFI-32
repo: brasas
rama: data/historia-desde-geprif
modelo: swe-2-high
riesgo: C
archivos: scripts/local/build_historia_geprif.py, web/data/incendios-nominados.json, tests/test_historia_geprif.py, docs/FUENTES.md, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
---

# OFI-32 · Historia desde el catálogo GEPRIF: perímetros 2014-2024 e incendios nominados ≥50 ha (decisión)

## Por qué es delicado (va a decisión de Diego)

Redistribuye **capas nuevas de CONAF** cuya licencia no está declarada por escrito. La investigación encontró que la frase «los datos son de uso público, citando a CONAF como fuente» aparece solo en dos ítems del hub («Zonas Interfaz» y «FIRMS»), no en el catálogo de servicios ni en `deigeprif/public`. Antes de versionar esos datos en `web/data/` hace falta la puerta de OFI-03 (correo a GEPRIF) o una verificación ítem por ítem. Es decisión del dueño, no del agente.

## Qué se ganaría

Dos capas estáticas del catálogo `services5.arcgis.com/A1ELWse9bRAi2JiV` que hoy no usa nadie (`docs/research/fuentes-meteologix-geprif.md:76-77`):

- **`PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO`** — polígonos por incendio y semana del año. Alimenta la vista Historia con cicatrices reales por comuna, sin depender del SHP de IDE Minagri.
- **`PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA`** — puntos con `Temporada`, `Comuna`, `Nombre`, `Lat/Lon`, `Superficie`, `Inicio`, `Duración_`. Es la base de «tu comuna en 2017» y de incendios con nombre propio, sin el XLSX con cookie de sesión.

Ambas son **estáticas** (no hay que refrescarlas) y encajan con lo que el producto ya tiene: `#/casos` (tres casos), OFI-28 (historia de la comuna por temporada, PR abierto) y OFI-30 (temporada 2025-26 como dato versionado, PR abierto).

## Evidencia

- `docs/research/fuentes-meteologix-geprif.md:76-77` — los dos recursos, sus campos y su valor.
- `docs/research/fuentes-meteologix-geprif.md:95` — la condición de uso: la declaración «uso público con cita» está solo en dos ítems; **cada capa nueva se verifica antes de redistribuirla** y el permiso formal sigue en OFI-03.
- `docs/BACKLOG_MAESTRO.md:297` — OFI-03 («autorización formal de CONAF») sigue abierto.
- `docs/research/fuentes-meteologix-geprif.md:122` — el ítem ya está propuesto como OFI-19, P2, tamaño M.

## Qué tiene que decidir Diego

1. ¿Se espera el permiso de OFI-03 antes de versionar datos de CONAF, o basta la cita «CONAF GEPRIF» con enlace y fecha de corte?
2. ¿Se publica como **dato derivado agregado** (conteo y hectáreas por comuna y temporada, sin geometrías) —menor riesgo— o se copian también los polígonos?
3. ¿Dónde vive: `web/data/` versionado (lo usa la app sin red) o un endpoint que consulte el FeatureServer en vivo (más frágil, sin copia de datos de CONAF)?

Si dice que sí, el encargo: `scripts/local/build_historia_geprif.py` (descarga la capa, valida totales contra el reporte oficial de temporada, escribe `web/data/incendios-nominados.json` con `source`, `fetched_at` y `license_note`), `tests/test_historia_geprif.py` (esquema y que los totales cuadren), y la vista Historia consume el dato con su atribución. Nada de geometrías si la licencia no está clara.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
