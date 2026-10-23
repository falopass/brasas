---
id: OFI-25
repo: brasas
rama: feat/campamentos-minvu
modelo: swe-2-high
riesgo: C
archivos: scripts/local/build_campamentos.py, web/data/campamentos.json, tests/test_campamentos.py, docs/FUENTES.md, CHANGELOG.md
e2e: no
intento: 0
---

# OFI-09 · Campamentos del MINVU por comuna (delicado: fuente nueva y licencia por verificar)

## Objetivo
Tener, agregado por comuna, cuántos campamentos y hogares hay en cada una, para que la exposición del riesgo incluya a las personas que viven en asentamientos (fueron de las más afectadas en Valparaíso 2024).

## Ítem del backlog
`docs/BACKLOG_MAESTRO.md:303` — OFI-09 «Campamentos (MINVU)», P2 · S, ⬜.

## Por qué es delicado (riesgo C) y no se lanza solo
1. **Fuente nueva sin licencia verificada.** El backlog dice «se vio una capa `campamentos_minvu` en ArcGIS: verificar que sea oficial y pública». No está confirmado que la capa sea del MINVU, ni su licencia de redistribución, ni su fecha de actualización. Publicar datos sin licencia clara es exactamente lo que el foco de esta ronda pide evitar.
2. **Datos habitacionales.** Aunque se publique solo el agregado por comuna, un mapa de campamentos a nivel de punto puede señalar hogares vulnerables. La política del proyecto (SEC-01..SEC-05) exige minimizar.
3. **Decisión de producto.** Mostrar «campamentos» en la interfaz toca la manera en que BRASA habla de vulnerabilidad; eso no lo decide un agente.

## Qué haría falta para lanzarlo (cuando Diego lo apruebe)
- Verificar el ítem de ArcGIS: dueño, organización, licencia declarada, fecha de edición y si la consulta es anónima.
- Guardar **solo agregado por comuna** (`comuna_code`, `n_campamentos`, `n_hogares`, `fuente`, `fecha_corte`), nunca coordenadas ni nombres.
- Script offline `scripts/local/build_campamentos.py` que descarga, agrega y escribe `web/data/campamentos.json` con su `source_url`.
- `docs/FUENTES.md`: registrar la fuente, la licencia y la limitación.
- Test que valide esquema, cobertura de comunas y que no haya coordenadas en el archivo.
- La superficie en la interfaz se decide después, en otro ítem.

## Decisión para Diego
¿Se integra la capa de campamentos del MINVU, solo agregada por comuna y con cita, una vez verificada su licencia? Si la respuesta es sí, se desbloquea y se lanza; si no, se queda documentada como no integrada.

Verifica con `/verificar` y entrega con `/entregar-pr`.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
