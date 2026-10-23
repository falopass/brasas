---
id: FUEGO-34
repo: brasas
rama: fix/fuego-34
modelo: ninguno
riesgo: C
archivos: ninguno (decisión)
e2e: no
intento: 0
ronda_review: 0
---

# Decisión para Diego: la pendiente del terreno en el escenario de propagación

**Qué pide el foco:** que la propagación explique viento, pendiente y humedad en palabras de vecino.

**Qué hay hoy:** `backend/fwi.py:316` lo dice explícito en un comentario del cálculo: «grados; sin ella (hoy: BRASA no tiene DEM) el escenario es de terreno plano», y `:364` marca el resultado como `kind: "escenario_estimado"`. O sea, el escenario hoy **no puede explicar la pendiente** porque no tiene modelo digital de elevación: entran viento y humedad, la ladera no. En Chile el fuego sube cerros, así que esa es justamente la variable que un vecino del Maule quiere oír, y hoy el texto no puede decirla sin mentir.

**Por qué es delicado (C):**
1. Agregar un DEM es una **fuente de datos nueva** (Copernicus GLO-30, SRTM u otra), con su licencia y su peso: el repo no tiene ningún raster de elevación y el presupuesto de peso tiene guarda (`PESO-01`, PR abierto).
2. Cambia la **ciencia del cálculo**: un factor de pendiente mal calibrado infla el escenario y asusta de más, o lo aplana y miente. Exige nota de método y, idealmente, contraste con KITRAL (`RISK-10`) antes de publicarlo.
3. Hay trabajo previo esperando decisión: `fusion-despues/fuego-22.md` (pendiente media por comuna con GLO-30). No conviene abrir dos frentes para lo mismo.

**Opciones para ti:**
- (a) Ítem acotado: precalcular la pendiente media por comuna con Copernicus GLO-30 en `scripts/local/`, versionada en `web/data/`, y que el escenario use esa pendiente media rotulándola como «pendiente media de la comuna», nunca como pendiente del punto. Riesgo contenido y verificable con tests.
- (b) Dejar el escenario plano y cambiar el texto para que diga qué **no** considera («este escenario no considera la pendiente del terreno»), que es honesto y cabe en un PR de una hora.
- (c) Posponer hasta tener KITRAL o validación externa (`ALI-06`).

Mi recomendación: (a) si quieres avanzar en realismo esta temporada; (b) si prefieres no tocar ciencia sin contraste. En las dos, el rótulo «escenario estimado» se mantiene y la guarda `scripts/local/chequeo_lenguaje.py` sigue corriendo en la suite.


DECISION (21-10, Diego delegó): Aprobado: la pendiente entra al escenario de propagacion con el modelo actual; se ajusta con Fusion y geo-reviewer.
