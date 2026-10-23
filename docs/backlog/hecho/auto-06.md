---
id: AUTO-06
repo: brasas
rama: feat/edad-del-dato-por-fuente
modelo: swe-2-high
riesgo: B
archivos: .github/scripts/fuentes_salud.py, tests/test_fuentes_salud.py, .github/workflows/fuentes-salud.yml, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

## Objetivo

Que la revisión semanal de fuentes diga **qué tan viejo es el dato** de cada fuente, no solo si el formato sigue igual: una fuente que responde 200 con un CSV de hace cuatro días hoy pasa como «OK».

## Problema (con evidencia)

`fuentes_salud.py` revisa formato y disponibilidad. Para GOES sí mira frescura (`GOES_MAX_AGE`, `.github/scripts/fuentes_salud.py:69` y `veredicto_goes`, línea 159): si el último barrido tiene más de 60 min, devuelve «OJO». Para el resto, no:

- `veredicto_conaf` (línea 144) devuelve «OK» con solo encontrar las columnas del encabezado; el CSV puede tener la última fila de la semana pasada y el run queda verde.
- `veredicto_boton_rojo` (línea 209) hace lo mismo con los campos de la consulta ArcGIS; la capa publica un campo `date`, que hoy no se lee.
- `veredicto_dmc` (línea 314) valida el CAP, pero no la fecha del último aviso; una DMC caída se ve igual que una semana sin avisos.
- `veredicto_oni` (línea 384) lee la tabla, sin decir de qué trimestre es la última fila (el ONI se publica con semanas de atraso a propósito: hay que distinguir «atraso normal» de «tabla congelada»).

El workflow corre los lunes (`.github/workflows/fuentes-salud.yml:11`), así que un dato viejo puede pasar hasta siete días sin que nadie lo note. Eso es justo la falla que el producto tiene que detectar solo: datos viejos, fuentes caídas.

## Qué hacer

1. Cada verificador devuelve, además del estado, **la edad del dato más nuevo que publica la fuente**: `(estado, detalle, edad_horas | None)`. Calcula la edad de forma pura a partir del cuerpo (última fila del CSV de CONAF, campo `date` del Botón Rojo, `pubDate` del ítem más reciente del RSS de la DMC, `acq_date`/`acq_time` de la primera fila de FIRMS, trimestre de la última fila del ONI).
2. Umbral por fuente, en una tabla explícita y comentada: CONAF incendios 24 h, Botón Rojo 24 h, DMC 6 h, FIRMS 6 h, ONI 120 días. Si la edad supera el umbral, el estado sube a «OJO» con el texto «el dato más nuevo tiene N h»; si la fuente no publica fecha legible, «OJO» con «no se pudo fechar el dato».
3. Salida: además de las anotaciones `::warning::`/`::error::` que ya existen (línea 415-421), escribe una tabla Markdown en `$GITHUB_STEP_SUMMARY` con fuente, estado, edad y umbral, y guarda un JSON pequeño como artefacto del run.
4. Pruebas puras en `tests/test_fuentes_salud.py` con cuerpos de ejemplo (CSV con dos fechas, JSON del Botón Rojo, RSS de la DMC, tabla ONI): edad correcta, umbral superado, fecha ilegible, y que el veredicto actual no cambie cuando la fuente está sana.

## Archivos

`.github/scripts/fuentes_salud.py`, `tests/test_fuentes_salud.py`, `.github/workflows/fuentes-salud.yml`, `CHANGELOG.md`. No toques nada más: no cambies el horario del workflow, no agregues dependencias nuevas (solo biblioteca estándar), no toques `backend/` y no pidas secretos nuevos.

## Criterio de listo

- `python -m pytest tests/test_fuentes_salud.py -q` en verde con los casos nuevos.
- `python .github/scripts/fuentes_salud.py` (sin red no hace falta: con `--offline` o con las pruebas) no cambia de comportamiento visible para las fuentes sanas; el resumen final imprime la edad de cada fuente.
- `python dev.py check` en verde.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
