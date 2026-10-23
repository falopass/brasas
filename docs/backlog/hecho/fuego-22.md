---
id: FUEGO-22
repo: brasas
rama: feat/pendiente-del-terreno
modelo: swe-2-high
riesgo: C
archivos: scripts/local/build_pendientes.py, web/data/pendientes-comunas.json, backend/fwi.py, backend/routes/public.py, tests/test_pendientes.py, docs/FUENTES.md, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
---

# FUEGO-22 · La pendiente del terreno en el escenario de propagación (decisión: fuente, licencia y costo)

**Por qué es delicado (va a decisión de Diego).** Toca la parte científica del producto: agrega una fuente de datos geoespaciales nueva, su licencia, un archivo de datos derivado y una afirmación más en la ficha del incendio. Eso no lo decide un agente solo.

**Qué falta hoy, y es la mitad de la prioridad de esta ronda.** La prioridad de producto dice que la propagación debe explicar «viento, pendiente y humedad» en términos que un vecino entienda. Hoy hay dos de tres:

- **Viento:** de `risk_hourly` (`backend/routes/public.py:339-355`).
- **Humedad del combustible:** por el FFMC de `fwi_daily` dentro del ISI (`backend/fwi.py:304-330`).
- **Pendiente:** **no existe**. El propio código lo declara: `propagation_scenario` acepta `slope_deg` y `aspect_deg` (`backend/fwi.py:304-309`) pero nadie se los pasa, y el supuesto siempre dice «Terreno plano: BRASA aún no tiene modelo de elevaciones; la pendiente puede acelerar el avance» (`backend/fwi.py:357-360`).

En una región como el Maule, donde el fuego sube por quebradas y laderas de pinar, decirle al vecino «terreno plano» no es neutro: subestima el avance justo en la dirección que importa. El FBP ya está implementado (`_slope_factor`, `backend/fwi.py:287-290`, con el tope de 70 %), así que **la física está lista; falta el insumo**.

**La decisión que se pide.**

1. **Fuente y licencia.** ¿SRTM 30 m (NASA/USGS, dominio público), Copernicus GLO-30 (licencia abierta con atribución) u otra? Hay que poder citarla en `docs/FUENTES.md` y en `assumptions`, igual que se hace con FCFDG y Open-Meteo.
2. **Dónde se calcula.** Dos caminos:
   - **(A) Fuera de línea, por comuna:** `scripts/local/build_pendientes.py` descarga el tile que cubre el centro de cada comuna chilena, calcula pendiente y orientación medias en una ventana de ~1-2 km y escribe `web/data/pendientes-comunas.json` (~350 KB, sin dependencias nuevas en runtime). El escenario usaría la pendiente del entorno de la comuna y lo diría: «pendiente aproximada del entorno de la comuna (12°), no del punto exacto del fuego».
   - **(B) En línea, por punto del fuego:** exige un DEM dentro del contenedor (o un recorte servido), una dependencia nueva (`rasterio`/`GDAL`) y peso en la imagen de Docker. Más fino y más caro de operar.
3. **Cómo se rotula.** Mantener `kind: "escenario_estimado"` y reemplazar el supuesto de «terreno plano» por el valor y su fuente; nunca presentarlo como pendiente del punto exacto cuando es la de la comuna.

**Recomendación del planificador (sujeta a tu OK):** camino (A) con SRTM 30 m. Es dominio público, el cálculo queda reproducible en `scripts/local/`, no agrega dependencias al contenedor, no toca el presupuesto de peso del arranque (el JSON se consulta por comuna, no se importa) y deja la ficha mejor sin volverla más lenta. El escenario ganaría la dirección de la ladera solo cuando exista orientación; si no, se mantiene el supuesto actual.

**Qué haría el encargo una vez aprobado.** `scripts/local/build_pendientes.py` (descarga y cálculo, con caché local), `web/data/pendientes-comunas.json` (dato versionado con `source`, `license`, `fetched_at`), lectura en `backend/fwi.py` (nuevo `slope_for_comuna()`) usada por `_incident_spread` (`backend/routes/public.py:327`), `tests/test_pendientes.py` (sin red: pendiente plana = 0, ladera conocida = valor esperado, comuna sin dato = supuesto «terreno plano»), `docs/FUENTES.md` (fuente, licencia, resolución, fecha) y `CHANGELOG.md`.

**Criterio de listo (verificable, cuando se apruebe).** `python dev.py test -k pendientes` en verde sin red; la ficha de un incidente en una comuna con pendiente muestra el supuesto nuevo con su fuente, y en una sin dato sigue diciendo «terreno plano»; `python dev.py check` en «Todo en orden»; `docs/FUENTES.md` con la licencia y la fecha de descarga del DEM.

**Qué tiene que decidir Diego.** (1) ¿SRTM 30 m u otra fuente? (2) ¿camino (A) fuera de línea por comuna, o (B) DEM en el contenedor? (3) ¿se acepta el texto «pendiente aproximada del entorno de la comuna» como suficiente para un vecino?

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
