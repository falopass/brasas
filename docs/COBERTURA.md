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
| `vegetacion-sequedad.json` | 17/345 | 328 | 2026-11-04 21:58 UTC | sin cadencia |

## Otros archivos con cadencia

Sin desglose por comuna, pero con plazo de regeneración declarado: `--check` también falla si se vencen.

| Archivo | Generado | Edad (d) | Vence cada (d) | Estado | Regenera con |
|---|---|---:|---:|---|---|
| `calibracion.json` | 2026-10-22 03:44 UTC | 13 | 180 | al día | `scripts/local/medir_adelanto.py` |
| `historia-comunas.json` | 2026-10-19 17:37 UTC | 16 | 3650 | al día | `scripts/local/build_historia_comunas.py` |
| `incendios-nominados.json` | 2026-10-19 17:37 UTC | 16 | 3650 | al día | `scripts/local/build_incendios_nominados.py` |
| `snaspe.json` | 2026-10-19 23:22 UTC | 15 | 365 | al día | `scripts/local/build_snaspe.py` |

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

### `vegetacion-sequedad.json` — 17/345

- **Antofagasta (9):** Antofagasta, Calama, María Elena, Mejillones, Ollagüe, San Pedro de Atacama, Sierra Gorda, Taltal, Tocopilla
- **Arica y Parinacota (4):** Arica, Camarones, General Lagos, Putre
- **Atacama (9):** Alto del Carmen, Caldera, Chañaral, Copiapó, Diego de Almagro, Freirina, Huasco, Tierra Amarilla, Vallenar
- **Aysén (10):** Aysén, Chile Chico, Cisnes, Cochrane, Coyhaique, Guaitecas, Lago Verde, O'Higgins, Río Ibáñez, Tortel
- **Biobío (30):** Alto Biobío, Antuco, Arauco, Cabrero, Cañete, Chiguayante, Concepción, Contulmo, Coronel, Curanilahue, Hualpén, Hualqui, Laja, Lebu, Los Alamos, Los Angeles, Lota, Mulchén, Nacimiento, Negrete, Quilaco, Quilleco, San Pedro de la Paz, San Rosendo, Santa Bárbara, Talcahuano, Tirúa, Tomé, Tucapel, Yumbel
- **Coquimbo (15):** Andacollo, Canela, Combarbalá, Coquimbo, Illapel, La Higuera, La Serena, Los Vilos, Monte Patria, Ovalle, Paihuano, Punitaqui, Río Hurtado, Salamanca, Vicuña
- **La Araucanía (29):** Carahue, Cholchol, Collipulli, Cunco, Curacautín, Curarrehue, Ercilla, Freire, Galvarino, Gorbea, Lautaro, Loncoche, Lonquimay, Los Sauces, Lumaco, Melipeuco, Nueva Imperial, Padre Las Casas, Perquenco, Pitrufquén, Pucón, Renaico, Saavedra, Temuco, Teodoro Schmidt, Toltén, Traiguén, Vilcún, Villarrica
- **Los Lagos (30):** Ancud, Calbuco, Castro, Chaitén, Chonchi, Cochamó, Curaco de Vélez, Dalcahue, Fresia, Frutillar, Futaleufú, Hualaihué, Llanquihue, Los Muermos, Maullín, Osorno, Palena, Puerto Montt, Puerto Octay, Puerto Varas, Puqueldón, Purranque, Puyehue, Queilén, Quellón, Quemchi, Quinchao, Río Negro, San Juan de la Costa, San Pablo
- **Los Ríos (10):** Corral, Futrono, La Unión, Lago Ranco, Lanco, Los Lagos, Mariquina, Máfil, Paillaco, Río Bueno
- **Magallanes (10):** Cabo de Hornos, Laguna Blanca, Natales, Porvenir, Primavera, Punta Arenas, Río Verde, San Gregorio, Timaukel, Torres del Paine
- **Maule (26):** Chanco, Colbún, Curepto, Curicó, Hualañé, Licantén, Linares, Longaví, Maule, Molina, Parral, Pelarco, Pelluhue, Pencahue, Rauco, Retiro, Romeral, Río Claro, Sagrada Familia, San Clemente, San Javier, San Rafael, Teno, Vichuquén, Villa Alegre, Yerbas Buenas
- **Metropolitana (52):** Alhué, Buin, Calera de Tango, Cerrillos, Cerro Navia, Colina, Conchalí, Curacaví, El Bosque, El Monte, Estación Central, Huechuraba, Independencia, Isla de Maipo, La Cisterna, La Florida, La Granja, La Pintana, La Reina, Lampa, Las Condes, Lo Barnechea, Lo Espejo, Lo Prado, Macul, Maipú, María Pinto, Melipilla, Padre Hurtado, Paine, Pedro Aguirre Cerda, Peñaflor, Peñalolén, Pirque, Providencia, Pudahuel, Puente Alto, Quilicura, Quinta Normal, Recoleta, Renca, San Bernardo, San Joaquín, San José de Maipo, San Miguel, San Pedro, San Ramón, Santiago, Talagante, Tiltil, Vitacura, Ñuñoa
- **O'Higgins (33):** Chimbarongo, Chépica, Codegua, Coinco, Coltauco, Doñihue, Graneros, La Estrella, Las Cabras, Litueche, Lolol, Machalí, Malloa, Marchigüe, Mostazal, Nancagua, Navidad, Olivar, Palmilla, Paredones, Peralillo, Peumo, Pichidegua, Pichilemu, Placilla, Pumanque, Quinta de Tilcoco, Rancagua, Rengo, Requínoa, San Fernando, San Vicente, Santa Cruz
- **Tarapacá (7):** Alto Hospicio, Camiña, Colchane, Huara, Iquique, Pica, Pozo Almonte
- **Valparaíso (34):** Algarrobo, Cabildo, Calera, Calle Larga, Cartagena, Casablanca, Catemu, Concón, El Quisco, El Tabo, Hijuelas, Isla de Pascua, Juan Fernández, La Cruz, La Ligua, Limache, Llaillay, Los Andes, Nogales, Olmué, Panquehue, Papudo, Petorca, Puchuncaví, Putaendo, Quillota, Quintero, Rinconada, San Antonio, San Esteban, San Felipe, Santa María, Santo Domingo, Zapallar
- **Ñuble (20):** Bulnes, Chillán, Chillán Viejo, Cobquecura, Coelemu, Coihueco, El Carmen, Ninhue, Pemuco, Pinto, Portezuelo, Quirihue, Ranquil, San Carlos, San Fabián, San Ignacio, San Nicolás, Treguaco, Yungay, Ñiquén
