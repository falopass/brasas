# Cobertura de datos por comuna

Cuántas de las 345 comunas de `web/data/comunas-index.json` cubre cada archivo de `web/data`. Una comuna faltante es una sección de la ficha que no se puede pintar: `#/riesgo` para la exposición y `#/temporada` para la temporada, por ejemplo.

Se miden los archivos que identifican la comuna por código; los que la agrupan por nombre o no tienen desglose por comuna quedan fuera.

Generado por `scripts/local/cobertura_datos.py`; no editar a mano. Las faltantes de esta tabla quedan documentadas: `--check` no falla por ellas, solo si una comuna que estaba cubierta deja de estarlo.

| Archivo | Cubiertas | Faltantes | Generado |
|---|---:|---:|---|
| `censo_2024.json` | 345/345 | 0 | 2026-10-19 13:09 UTC |
| `interfaz.json` | 332/345 | 13 | 2026-10-20 05:50 UTC |
| `rain_normals.json` | 317/345 | 28 | 2026-10-19 23:00 UTC |
| `temporada-2526.json` | 298/345 | 47 | 2026-10-19 22:34 UTC |

## Faltantes por archivo

### `censo_2024.json` — 345/345

Sin faltantes.

### `interfaz.json` — 332/345

- **Metropolitana (11):** El Bosque, Independencia, La Cisterna, La Granja, Lo Prado, Macul, Providencia, San Joaquín, San Miguel, San Ramón, Ñuñoa
- **Valparaíso (2):** Isla de Pascua, Juan Fernández

### `rain_normals.json` — 317/345

- **Arica y Parinacota (3):** Camarones, General Lagos, Putre
- **Aysén (8):** Chile Chico, Cisnes, Cochrane, Guaitecas, Lago Verde, O'Higgins, Río Ibáñez, Tortel
- **Biobío (3):** Alto Biobío, Antuco, Quilaco
- **La Araucanía (1):** Melipeuco
- **Los Lagos (5):** Chaitén, Cochamó, Futaleufú, Palena, Queilén
- **Magallanes (7):** Cabo de Hornos, Laguna Blanca, Primavera, Río Verde, San Gregorio, Timaukel, Torres del Paine
- **Ñuble (1):** San Fabián

### `temporada-2526.json` — 298/345

- **Antofagasta (7):** Antofagasta, María Elena, Mejillones, Ollagüe, Sierra Gorda, Taltal, Tocopilla
- **Atacama (4):** Caldera, Chañaral, Diego de Almagro, Freirina
- **Aysén (4):** Guaitecas, Lago Verde, O'Higgins, Tortel
- **Coquimbo (3):** Andacollo, La Higuera, Río Hurtado
- **Los Lagos (3):** Frutillar, Palena, Quemchi
- **Magallanes (4):** Cabo de Hornos, Laguna Blanca, Primavera, Timaukel
- **Metropolitana (18):** Cerrillos, Cerro Navia, El Bosque, Estación Central, Independencia, La Cisterna, La Granja, Lo Espejo, Lo Prado, Macul, Pedro Aguirre Cerda, Quinta Normal, San Joaquín, San Miguel, San Ramón, Santiago, Vitacura, Ñuñoa
- **Tarapacá (3):** Alto Hospicio, Colchane, Iquique
- **Valparaíso (1):** Juan Fernández
