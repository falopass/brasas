---
id: OFI-10
repo: brasas
rama: feat/aire-medido-sinca
modelo: swe-2-high
riesgo: C
archivos: backend/providers/sinca.py, backend/routes/climate.py, web/js/views/zona.js, tests/test_sinca.py, docs/FUENTES.md, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
---

# OFI-10 · SINCA (MP2,5 medido): la fuente es pública pero no declara licencia (decisión de Diego)

## Por qué es delicado (riesgo C) y no se lanza solo
La investigación INV-26 (PR #233) verificó con GET reales que SINCA (MMA) publica un JSON **sin clave**
con 119 estaciones, su comuna y el MP2,5 de las últimas 24 h (más ICAP), con ~2 h de latencia, y una
descarga horaria por estación. Pero el portal dice **«Todos los derechos reservados»** y marca los datos
como «preliminares» hasta su validación: no hay una licencia de reutilización declarada.

Redistribuir esos valores en BRASA es la misma clase de decisión que el CSV de CONAF: la toma el dueño,
no un agente.

## Qué se ganaría
AGUA-05 ya muestra el **pronóstico** de humo (CAMS). Con SINCA, «Mi zona» podría responder «lo que se
mide ahora»: «Estación Curicó: 8 µg/m³ de MP2,5 (ICAP 16, bueno)». Para asma, personas mayores y niños,
el dato medido pesa más que el pronóstico.

## Opciones (elige una)
1. **Integrar con atribución y enlace** al portal SINCA, marcando el valor como «preliminar» — mismo
   criterio con que ya se citan CONAF y la DMC.
2. **Solo enlazar**: un enlace «Ver la calidad del aire medida en SINCA ↗» en la ficha de comuna, sin
   copiar los números. Coste casi cero y sin riesgo de licencia.
3. **No hacerlo** por ahora.

## Plan si se aprueba la opción 1 (para otra ronda)
- `backend/providers/sinca.py`: listado en caché 30 min, lectura por estación en caché 10 min, sin claves.
- `GET /api/climate/air?lat=&lon=` en `backend/routes/climate.py` (fuera de `public.py`).
- En `web/js/views/zona.js`: el valor medido **junto** al pronóstico, con estación, hora y «preliminar»; si falla, no se muestra nada.
- `tests/test_sinca.py` con JSON mockeado; `docs/FUENTES.md` con la atribución y la salvedad de licencia.

Verifica con `/verificar` y entrega con `/entregar-pr` **solo si Diego elige la opción 1**. No mergees por iniciativa propia.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

Hecho (24-10): Diego eligió la opción 1 («haz la implementación completa de todo lo del
gobierno»). `backend/providers/sinca.py` destila `listadomapa2k19` (JSON público sin clave,
~119 estaciones) a una fila por estación con su PM2,5 vigente (media móvil 24 h, ICAP y
estado del `tableRow`); la hora es hora de Chile y se interpreta en `America/Santiago`.
`GET /api/climate/air?lat=&lon=` comparte la descarga en caché de 30 min y sirve solo la
estación a ≤60 km con lectura de ≤6 h; sin ella `air` sale null. En «Mi zona» la línea
«Aire medido en la estación…» va junto al pronóstico con el sello «preliminar» y el enlace
a sinca.mma.gob.cl. La consulta de licencia quedó enviada al MMA por Transparencia; si
llega respuesta, se anota en FUENTES.md.
