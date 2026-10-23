---
name: smoke-reporte
description: Prueba de humo manual del camino crítico de BRASA — que un vecino pueda reportar un incendio. Solo en una sesión Cloud y solo si el dueño la pide; en local no se corre.
---

# Smoke del reporte ciudadano

**En local no se corre** (`AGENTS.md`: sin pruebas en local). En cada PR que toque reportes, el CI ya corre las
pruebas del paso 1 y el e2e; los pasos 2 y 3 se hacen solo en una sesión Cloud, cuando el dueño lo pide.

El reporte es el camino crítico: si se cae, BRASA no sirve. Esta prueba se corre **completa y en verde**
antes de abrir un PR que toque `backend/routes/community.py`, `backend/security.py` (Turnstile/CSP),
`web/js/ui.js` (formulario), `web/js/reportes.js`, caché de `/api/reports` o el service worker.

## 1. Rápido (siempre, ~40 s)

```
python dev.py test -k "report"
```

Debe pasar `test_reports_safety`, `test_reportes_publicos`, `test_reports_caducidad` y `test_alert_report`.

## 2. Flujo real en local (sin Turnstile si no hay `TURNSTILE_SECRET`)

```
python dev.py run --demo   # en otra terminal, dejarlo escuchando
```

Con el servidor arriba:

1. **Crear**: `POST /api/reports` con `lat=-35.4264&lon=-71.6554&kind=humo&description=prueba smoke`.
   Esperado: `201` y un `id`.
2. **Duplicado cercano**: repetir el mismo POST con `lat/lon` casi iguales (±0.001).
   Esperado: **no** crea otra fila; responde con el reporte existente y suma corroboración.
3. **Fuera de Chile**: `lat=-33.45&lon=-70.66` (Santiago sí es Chile) y luego `lat=-32.89&lon=-68.83`
   (Mendoza, Argentina). El segundo debe rechazarse o quedar sin comuna; nunca publicarse como chileno.
4. **Foto**: adjuntar una imagen chica (<2 MB) y comprobar que `GET /api/reports/{id}/photo` la devuelve.
5. **Estado**: abrir la portada y verificar que «Tus reportes anteriores» muestra el reporte con
   «En revisión» (no «Verificado»).
6. **Límite**: 7 POST en menos de una hora desde la misma IP → el séptimo debe responder `429`.
7. **Borrar** lo que creaste (el demo usa base efímera; si no, elimina los reportes de prueba).

## 3. Si tocaste Turnstile o la CSP

- Con `TURNSTILE_SECRET` vacío el backend **no** verifica: comprueba explícitamente que con la clave puesta
  un POST sin token responde `403` y con token inválido también.
- La CSP de `backend/security.py` y la de `deploy/cloudflare/src/index.ts` deben ser idénticas
  (`tests/test_security.py`).

## 4. Qué reportar en el PR

Pega el resultado de cada paso (código HTTP) y di qué no pudiste correr. Si algo falla, **no abras el PR**:
arréglalo primero.
