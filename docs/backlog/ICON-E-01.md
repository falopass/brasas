---
id: ICON-E-01
repo: brasas
rama: feat/iconos-topograficos-e
modelo: swe-2-high
riesgo: B
archivos: web/icons/, backend/og.py, web/manifest.webmanifest, web/*.html, backend/routes/paginas_comuna.py, scripts/, tests/, CHANGELOG.md
e2e: si
estado_desde: 2026-11-10
---

**Objetivo aprobado por el dueño.** Reemplazar el set de anillos por la dirección E:
mapa topográfico oscuro visto desde arriba, curvas finas naranjas y un foco satelital
naranja brillante que marca un lugar. Fondo `#0d0c0b`, brasa `#FF4B1F`, crema `#f4efe7`.
No son datos cartográficos reales: es un motivo de marca, sin cifras ni alertas inventadas.

**Entregables reales en `web/icons/`.**

- `favicon.ico` con imágenes 16, 32 y 48 px; `favicon.svg` optimizado para pequeño.
- `apple-touch-icon.png` de 180×180; `icon-192.png`, `icon-512.png` y
  `icon-maskable-512.png`, con motivo esencial dentro del círculo central seguro
  de radio 40 % y fondo hasta el borde.
- `icon.svg` de compatibilidad con la misma marca E, sin conservar los anillos.
- `og.png` de 1200×630 para portada y `og-focos.png` para la página de focos,
  legibles reducidos. El renderer existente `backend/og.py` adopta la misma dirección,
  preservando datos públicos, escapes, caché y semántica de incidentes/incendios.
- OG específica de comuna en `/og/comuna/<codigo>.png`, nombre real del territorio,
  sin métricas sintéticas. Metas correctas en portada, focos y fichas de comuna.
- Manifest y consumidores HTML actualizados: ICO/SVG, Apple 180, imágenes
  `any`/`maskable` separadas y Open Graph/Twitter con URL absoluta, dimensiones y alt.

**Dirección por escala.** A 16 px, 2–3 curvas claras y foco grande: no reducir la OG.
En app/Apple, pocas curvas asimétricas con espacio y foco dominante; en la OG, campo
topográfico más rico y jerarquía tipográfica BRASA/Chile. Nada de ilustración de
montaña en perspectiva ni marcador de pin genérico. Sin rediseñar el resto de la app.

**Bloques paralelos y ownership.**

1. Activos/renderer: `web/icons/`, `backend/og.py`, generador reproducible pequeño y
   pruebas de activos/OG. Renderiza los binarios en devin-vm con Pillow ya instalado.
2. Integración: `web/manifest.webmanifest`, HTML públicos, `backend/routes/paginas_comuna.py`
   y pruebas de metadata/manifest. Consume exactamente las rutas y nombres anteriores.
3. Root: este encargo, índice del backlog, CHANGELOG, revisión visual final y entrega.
   Ningún worker toca esos archivos compartidos ni revierte trabajo ajeno.

**Criterio de listo.**

- Examinar cada tamaño real, especialmente 16 px, 180 px y OG reducida; revisar
  recortes circular/cuadrado redondeado del maskable sin perder el foco.
- Dimensiones, tamaños internos del ICO, contenido de manifest y metas comprobados
  por pruebas pertinentes en CI. Sin suites ni navegador en el notebook.
- Rama + PR con `ICON-E-01` en título/cuerpo, auto-merge y CI requerido verde.
  Corregir los comentarios de revisión; no tocar `deploy/`, secretos ni dependencias
  por rutina. SSH solo `desktop` o `devin-vm`; Instabox queda excluida.
- Después del despliegue automático: GET de favicon/SVG/PNG, manifest válido y
  metadatos de portada/focos/comuna; descargar y mirar las OG servidas en producción.
  Evidencia y resumen de main/producción, sin compras ni escrituras productivas.

**Verificación pendiente.** Se completa tras la implementación; no se anticipan resultados.
