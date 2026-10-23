---
id: RISK-15
repo: brasas
rama: feat/comuna-con-su-historia
modelo: swe-2-high
riesgo: B
archivos: backend/historia.py, backend/routes/comuna.py, tests/test_comuna_historia.py, CHANGELOG.md
e2e: no
revision_ronda: 0
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que la ficha de cada comuna pueda responder «¿esto es normal aquí?»: sumar a `GET /api/comuna/{code}` un bloque `historia` con las temporadas en que esa comuna tuvo incendios, la peor, el promedio y cómo va la temporada en curso frente a ese promedio. Es el contexto que hoy solo existe escondido en un JSON, y es justo lo que un vecino del Maule necesita para entender su riesgo de hoy.

# Ítem del backlog

CONT-13/Historia por comuna (el archivo versionado ya existe) y RISK-03 («riesgo explicado»: contexto histórico como parte de la exposición). El foco de esta ronda pide features que acerquen al vecino a entender su riesgo hoy.

# Qué pasa hoy y por qué está mal

- `web/data/historia-comunas.json` ya trae, por comuna, `temporadas: [{season, n, ha}]` y `top: [{name, ha, season}]` (por ejemplo Algarrobo: 6 temporadas, la peor 2003-2004 con 2.200 ha). Ese dato está en el repo y hoy no lo ve nadie.
- `backend/routes/comuna.py:79-95` devuelve `comuna`, `risk`, `boton_rojo`, `exposicion`, `incendios_oficiales` y `data_as_of`, y **ninguna** referencia histórica: la ficha dice cómo está hoy, no si la comuna se quema todos los veranos.
- El vecino que abre su comuna ve «riesgo moderado» sin saber que en su comuna hubo 4 incendios en 20 años o que la última temporada con incendios fue 2021-2022. Sin ese contexto, el número no se interpreta.
- No hay endpoint ni módulo que lea ese archivo: búscalo y confírmalo antes de escribir código (grep `historia-comunas` en `backend/`); si aparece un lector, reúsalo en vez de duplicarlo.

# Qué hacer

1. `backend/historia.py` (nuevo): cargar `web/data/historia-comunas.json` una vez (caché en memoria, igual que `backend/censo.py`), con búsqueda por nombre de comuna normalizado (sin tildes, minúsculas) y tolerante a los artículos («LA SERENA» vs «La Serena»). Devolver `None` si la comuna no está, sin inventar ceros.
2. En `backend/routes/comuna.py`, sumar al payload `historia`: `{temporadas_con_incendios, ultima_temporada, peor: {season, ha, n}, promedio_incendios_por_temporada, esta_temporada: {season, n, ha} | null, nota}` donde `nota` explica en una frase que son incendios informados por CONAF y que la comparación es contra el promedio de las temporadas registradas. `esta_temporada` sale de `web/data/temporada-2526.json` si la comuna está ahí.
3. Si la comuna no tiene historia: `historia: null` y la clave `nota` diciendo «sin registro histórico para esta comuna», nunca un objeto con ceros.
4. `tests/test_comuna_historia.py`: Algarrobo con sus 6 temporadas y su peor temporada 2003-2004; una comuna inexistente en el JSON → `null`; una comuna con temporada en curso → `esta_temporada` coherente; nombres con tildes y artículos resuelven igual.
5. Una línea en `CHANGELOG.md`.

**Archivos a tocar:** `backend/historia.py`, `backend/routes/comuna.py`, `tests/test_comuna_historia.py`, `CHANGELOG.md`. **No toques nada más**: no edites `web/data/historia-comunas.json` ni `temporada-2526.json`, no toques `backend/routes/public.py` (otro encargo lo ocupa), ni `web/js/views/*` (la interfaz va en otro ítem), ni `backend/services.py`.

# Criterio de listo (verificable)

- `python dev.py test -k historia_comuna` en verde con los cuatro casos.
- `GET /api/comuna/5101` (o el código de Algarrobo en el índice de comunas) contra la app de demostración devuelve `historia.temporadas_con_incendios == 6` y `historia.peor.season == "2003-2004"`.
- `python dev.py check` dice «Todo en orden» y `/api/comuna/{code}` sigue devolviendo las claves actuales sin cambios.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
