---
id: OFI-17
repo: brasas
rama: feat/perimetro-oficial-conaf
modelo: swe-2-high
riesgo: B
archivos: backend/providers/conaf_dei.py, backend/routes/public.py, web/js/views/incendio.js, tests/test_conaf_dei.py, CHANGELOG.md
e2e: si
aprobado: si
decision_por: Hermes (delegado por Diego 19-10)
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

NOTA DE LA FÁBRICA: Tu PR #209 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #209 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: el PR #209 tiene conflicto con main. Antes de nada: `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica y sube con `--force-with-lease`.

# Encargo — OFI-17 · Perímetro oficial de CONAF en la ficha del incidente (DECISIÓN, no lanzar)

## Objetivo (una frase)
Cuando un incidente quede confirmado con CONAF, mostrar la huella oficial de su «Perímetro final» en la ficha, como estado final y con atribución — nunca como avance hora a hora.

Ítem del backlog: **OFI-17** (P1, M), propuesto en la investigación INV-FUENTES del 19-oct-2026 (`docs/research/fuentes-meteologix-geprif.md`, §2).

## Evidencia
- El catálogo público de GEPRIF-CONAF (`services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/Perimetro_final/FeatureServer/0/query`) respondió sin clave el 19-oct-2026; campos útiles: `ID_IF` («558-SAN RAMON»), `REGION`, `Superficie_hectareas`, patrón de propagación; última edición observada ~2026-03.
- La regla de interpretación n.º 4 de `docs/FUENTES.md` ya exige mostrarlo solo como estado final.

## Por qué es decisión C (no se lanza solo)
Es una **fuente externa nueva** de CONAF con licencia declarada como «uso público citando a CONAF» solo en algunos tableros, **no** en los servicios; antes de redistribuirla hay que confirmar el permiso ítem por ítem (puerta OFI-03: correo a GEPRIF) y registrar la capa en `docs/FUENTES.md`. Lo lanza el dueño cuando apruebe la fuente.

## Qué haría (para cuando se apruebe)
1. `backend/providers/conaf_dei.py`: consulta por proximidad (envelope) al confirmar un incidente con CONAF, caché en `kv` con «última versión válida» y degradación suave (patrón del Botón Rojo).
2. Adjuntar el polígono al detalle de `/api/incidents/{id}` (GeoJSON simplificado, con `ID_IF` y superficie).
3. En `web/js/views/incendio.js`: dibujarlo con etiqueta «Perímetro oficial CONAF · <ha> ha · <fecha>» + atribución y enlace; solo lectura detallada.
4. Pruebas con fixtures (sin red en las pruebas) y actualización de `docs/FUENTES.md` con la licencia verificada.

Criterio de «listo» (cuando se apruebe): prueba verde con fixture, la ficha muestra la huella oficial en un incidente confirmado de la demo, y `python dev.py check` en «Todo en orden».

Verifica con `/verificar` y entrega con `/entregar-pr`. **No mergees por iniciativa propia.**


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
