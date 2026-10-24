---
id: OPS-12
repo: brasas
rama: ops/rotar-clave-firms
modelo: swe-2-medium
riesgo: C
archivos: ninguno
e2e: no
intento: 0
---

# Encargo — OPS-12 · Rotar la clave de FIRMS (P0, solo Diego puede)

## Por qué va marcado C
Manejo de secretos: el perfil manda estos temas a Diego. La fábrica no puede ejecutarlo (requiere su cuenta de FIRMS y los paneles de Cloudflare/GitHub).

## Por qué es P0
La clave de FIRMS se pegó en una conversación de chat: hay que tratarla como **expuesta**. Es una de las acciones de la semana del 19 al 25 de oct (docs/BACKLOG_MAESTRO.md, «Ruta» y tabla de decisiones).

## Checklist para Diego (sin imprimir jamás el valor)
1. Pedir una clave nueva en FIRMS (firms.modaps.eosdis.nasa.gov/api → «Get MAP_KEY»).
2. Cargarla como secreto donde vive hoy (Cloudflare: secretos del Worker/Contenedor; y el `.env` local si aplica). **No pegarla en el chat ni en issues.**
3. Desactivar la clave anterior en FIRMS.
4. Comprobar en el siguiente ciclo: `/api/status` con `last_ingest_at` fresco y sin `failed_sources` de FIRMS; el diario de `ingest_runs` sin errores 401/403 de FIRMS.
5. Anotar la fecha de rotación en el calendario de SEC-12 (rotación de secretos) si ya está mergeado.

## Qué puede hacer la fábrica
Nada de este ítem (no ejecutable). Si Diego quiere, un encargo futuro puede dejar el procedimiento escrito en `docs/OPERACION.md` — ya cubierto por SEC-12 (en `decision/`).


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


BLOQUEADO POR DIEGO: requiere generar la clave nueva de FIRMS en la consola. Sin eso no se toca la ingesta. Se retoma cuando la entregue.

CERRADO (23-10): Diego rotó la clave — la nueva quedó como secreto `FIRMS_MAP_KEY` en Cloudflare y la anterior quedó desactivada en FIRMS. Verificado contra producción: `/api/status` muestra `firms_quota` con uso (8/5000, `error: false`), corridas VIIRS cada 10 min `ok` y `failures_24h` sin errores 401/403.
