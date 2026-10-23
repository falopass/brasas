---
id: MAPA-105
repo: brasas
rama: fix/mapa-105
modelo: ninguno
riesgo: C
archivos: ninguno (decisión)
e2e: no
intento: 0
ronda_review: 0
---

# Decisión para Diego: las capas base del mapa y sus licencias

**Qué ve hoy el usuario:** el mapa abre con la base vectorial de OpenFreeMap (`web/js/map.js:8` y `:66`) y ofrece dos alternativas en el selector: **Satélite**, con teselas de Sentinel-2 cloudless 2023 de EOX (`map.js:10-15`), y **Relieve**, con OpenTopoMap (`map.js:16-21`). Las tres se piden directo a servicios de terceros desde el navegador de cada persona.

**Los dos problemas:**
1. **Licencia no comercial.** La atribución que el propio código declara dice que las teselas satelitales son **CC BY-NC-SA 4.0** (`map.js:13`), es decir, uso no comercial. El backlog ya tiene `NEG-05` abierto justamente para revisar «las licencias no comerciales de Open-Meteo y Sentinel-2 cloudless antes de cobrar»: si BRASA llega a tener versión institucional o cobra un piloto municipal, esa capa queda fuera de licencia. Y hoy es la capa que más se usa para mirar un incendio de cerca.
2. **Servicios voluntarios sin SLA.** OpenTopoMap (`a.` y `b.tile.opentopomap.org`) es un servicio comunitario con política de uso que no garantiza disponibilidad; en un megaincendio es lo primero que se cae. No hay caché propia ni límite por cliente para esas teselas, y el manejo de error solo marca `basemapOffline` (`map.js:282-285`), sin decirle a la persona qué pasó.

**Por qué es delicado (C):** cambia una dependencia externa visible y toca licencias; puede cambiar lo que se ve en el mapa en plena emergencia. La fábrica no lo lanza sola.

**Opciones para ti:**
- (a) Mantener todo y **mostrar la licencia** en el pie del mapa (un enlace «Licencias de las capas») más una nota en la página de privacidad y datos. Es un PR chico y deja el riesgo documentado.
- (b) Reemplazar la base satelital por una de uso comercial permitido (por ejemplo Esri World Imagery con su atribución, o teselas propias en R2), aceptando el costo de peso y de licencia.
- (c) Quitar «Relieve» del selector para no depender de OpenTopoMap y quedarte con dos bases.

Mi recomendación: (a) ahora mismo y (b) cuando exista la versión institucional. Si eliges (a), el ítem puede ir en la próxima ronda como riesgo B con archivos `web/js/map.js`, `web/index.html` y `docs/FUENTES.md`.


DECISION (21-10, Diego delegó): Aprobado: usar capas base con licencia abierta (OSM/IGN Chile) y credito visible. Se implementa con Fusion.
