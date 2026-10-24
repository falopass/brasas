# Cobertura de datos por comuna

Cuántas de las 345 comunas de `web/data/comunas-index.json` cubre cada archivo de `web/data`. Una comuna faltante es una sección de la ficha que no se puede pintar: `#/riesgo` para la exposición y `#/temporada` para la temporada, por ejemplo.

Se miden los archivos que identifican la comuna por código; los que la agrupan por nombre o no tienen desglose por comuna quedan fuera de esta tabla, y si tienen cadencia declarada aparecen en «Otros archivos con cadencia».

Generado por `scripts/local/cobertura_datos.py`; no editar a mano. Las faltantes de esta tabla quedan documentadas: `--check` no falla por ellas, solo si una comuna que estaba cubierta deja de estarlo o un archivo con cadencia se vence.

La columna «Estado» compara la fecha del archivo con la cadencia declarada en `CADENCIA` (en `scripts/local/cobertura_datos.py`): «al día», «por vencer» (queda menos del 15 % de la cadencia), «vencido» (ya pasó; `--check` falla y nombra el script que lo regenera), «sin fecha» (el archivo no trae marca legible) y «sin cadencia» (no hay cadencia declarada para ese archivo).

| Archivo | Cubiertas | Faltantes | Generado | Estado |
|---|---:|---:|---|---|
| `campamentos.json` | 185/345 | 160 | 2026-10-24 04:27 UTC | al día |
| `censo_2024.json` | 345/345 | 0 | 2026-10-19 13:09 UTC | al día |
| `interfaz.json` | 332/345 | 13 | 2026-10-20 05:50 UTC | al día |
| `rain_normals.json` | 317/345 | 28 | 2026-10-19 23:00 UTC | al día |
| `temporada-2526.json` | 298/345 | 47 | 2026-10-19 22:34 UTC | al día |

## Otros archivos con cadencia

Sin desglose por comuna, pero con plazo de regeneración declarado: `--check` también falla si se vencen.

| Archivo | Generado | Edad (d) | Vence cada (d) | Estado | Regenera con |
|---|---|---:|---:|---|---|
| `calibracion.json` | 2026-10-22 03:44 UTC | 2 | 180 | al día | `scripts/local/medir_adelanto.py` |
| `historia-comunas.json` | 2026-10-19 17:37 UTC | 4 | 3650 | al día | `scripts/local/build_historia_comunas.py` |
| `incendios-nominados.json` | 2026-10-19 17:37 UTC | 4 | 3650 | al día | `scripts/local/build_incendios_nominados.py` |
| `snaspe.json` | 2026-10-19 23:22 UTC | 4 | 365 | al día | `scripts/local/build_snaspe.py` |

## Faltantes por archivo

### `campamentos.json` — 185/345

- **Antofagasta (4):** María Elena, Mejillones, Ollagüe, Sierra Gorda
- **Arica y Parinacota (3):** Camarones, General Lagos, Putre
- **Atacama (2):** Caldera, Freirina
- **Aysén (7):** Chile Chico, Cochrane, Guaitecas, Lago Verde, O'Higgins, Río Ibáñez, Tortel
- **Biobío (11):** Antuco, Cabrero, Chiguayante, Florida, Nacimiento, Quilaco, Santa Bárbara, Santa Juana, Tirúa, Tucapel, Yumbel
- **Coquimbo (5):** Combarbalá, La Higuera, Paihuano, Punitaqui, Río Hurtado
- **La Araucanía (14):** Carahue, Cholchol, Cunco, Gorbea, Lautaro, Los Sauces, Lumaco, Melipeuco, Perquenco, Pitrufquén, Saavedra, Teodoro Schmidt, Traiguén, Vilcún
- **Los Lagos (17):** Chaitén, Chonchi, Cochamó, Curaco de Vélez, Dalcahue, Fresia, Futaleufú, Hualaihué, Maullín, Palena, Puqueldón, Purranque, Puyehue, Queilén, Quinchao, San Juan de la Costa, San Pablo
- **Los Ríos (3):** Futrono, Lago Ranco, Máfil
- **Magallanes (9):** Cabo de Hornos, Laguna Blanca, Natales, Porvenir, Primavera, Río Verde, San Gregorio, Timaukel, Torres del Paine
- **Maule (20):** Chanco, Colbún, Curepto, Hualañé, Licantén, Linares, Longaví, Maule, Parral, Pelarco, Pelluhue, Pencahue, Romeral, Río Claro, Sagrada Familia, San Clemente, San Javier, San Rafael, Vichuquén, Villa Alegre
- **Metropolitana (21):** Alhué, El Bosque, Independencia, La Cisterna, La Granja, La Reina, Las Condes, Lo Prado, Macul, María Pinto, Padre Hurtado, Pedro Aguirre Cerda, Peñalolén, Providencia, Quinta Normal, San Joaquín, San Miguel, San Ramón, Santiago, Vitacura, Ñuñoa
- **O'Higgins (13):** Chépica, Coltauco, La Estrella, Las Cabras, Litueche, Lolol, Marchigüe, Palmilla, Paredones, Peumo, Pichidegua, Pumanque, Quinta de Tilcoco
- **Tarapacá (4):** Camiña, Colchane, Huara, Pica
- **Valparaíso (14):** Algarrobo, Calle Larga, Catemu, Isla de Pascua, Juan Fernández, La Cruz, Olmué, Panquehue, Papudo, Rinconada, San Esteban, Santa María, Santo Domingo, Zapallar
- **Ñuble (13):** Cobquecura, Coihueco, El Carmen, Pemuco, Pinto, Portezuelo, Quillón, Ranquil, San Fabián, San Ignacio, Treguaco, Yungay, Ñiquén

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
