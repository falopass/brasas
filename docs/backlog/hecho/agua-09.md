---
id: AGUA-09
repo: brasas
rama: feat/lluvia-intensa-visible
modelo: swe-2-high
riesgo: C
archivos: backend/lluvia.py, backend/routes/climate.py, web/js/views/zona.js, tests/test_lluvia.py, docs/FUENTES.md, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
---

# Para decisión de Diego (no lanzar)

## Qué está pasando

La señal de **lluvia intensa + isoterma 0 °C** (AGUA-03A) ya está calculada y probada, pero **no la ve nadie**: ningún endpoint la expone y ninguna vista la muestra.

- `backend/lluvia.py:1-15` — el módulo completo: peor ventana de 3 horas, isoterma de su hora central, huecos sin inventar. Su propio docstring dice que los umbrales son iniciales, «pendientes de calibración con datos chilenos (intensidades de DMC/DGA y la isoterma de los aluviones documentados)» y que «por ahora la señal solo marca la peor ventana de lluvia: no gatilla ningún aviso todavía».
- `tests/test_lluvia.py:1-12` — la suite existe y pasa: la lógica está verificada.
- `backend/providers/weather.py:85` — el pronóstico horario pide `freezing_level_height` justamente para AGUA-03A, y aclara que «el lote de las 345 comunas no las pide»: el insumo se descarga solo cuando alguien lo pide.
- Búsqueda de importaciones (20-oct): `grep -rn "lluvia" backend scripts` no devuelve ningún `from backend import lluvia` fuera de `tests/`. O sea: código listo, datos disponibles a pedido, cero superficie de producto.
- Mientras tanto, `web/js/views/preparate.js:230` ya le promete al vecino que «con la zona quemada, la pendiente del cerro y la lluvia pronosticada, BRASA podrá avisar dónde hay riesgo de aluvión el invierno siguiente».

## Por qué es delicado (riesgo C)

Es material de **aluvión post-incendio**: una señal mal rotulada puede leerse como una alerta oficial de remoción en masa, y la decisión de umbrales (mm/3 h e isoterma) es científica y todavía no está calibrada con DMC/DGA, como el propio módulo reconoce. Por eso no lo lanzo a la fábrica: necesita tu criterio sobre qué se muestra, con qué palabra y cuándo.

## Las dos salidas posibles

**A. Exponerla como dato, nunca como aviso (recomendada si quieres avanzar ahora).** Un bloque en la ficha de comuna con zona quemada: «Lluvia prevista: hasta 12 mm en 3 horas el jueves a las 15 h; la isoterma 0 °C está a 2.100 m. Es un dato del pronóstico, no un aviso de aluvión: BRASA todavía no emite avisos de aluvión.» Sin gatillar notificaciones y con el rótulo de «escenario estimado» que ya usa la propagación. Archivos: `backend/routes/climate.py` (endpoint por comuna), `web/js/views/zona.js` (bloque), tests de contrato.

**B. Esperar la calibración (AGUA-01/AGUA-02) y dejar el módulo como está.** Costo: sigue siendo código sin superficie y la promesa de «Prepárate» queda en futuro.

## Lo que necesito de ti

Una línea: A o B. Si es A, ¿el bloque va en «Mi zona» para cualquier lugar, o solo cuando el lugar está aguas abajo de una cicatriz de incendio (lo que pide `backend/scars.py`)? Esa condición es la diferencia entre informar y alarmar.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
