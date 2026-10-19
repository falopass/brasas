# Cómo contribuir a BRASA Chile

Gracias por ayudar. BRASA avisa a personas reales sobre incendios reales: la exactitud y la honestidad sobre lo que no sabemos importan más que cualquier función nueva.

Para preparar tu equipo, lee [`docs/DESARROLLO_LOCAL.md`](docs/DESARROLLO_LOCAL.md).

## Principios que no se negocian

1. **Nunca inventar datos.** Ninguna capa se completa con datos simulados en una vista real; si una fuente no responde, se dice. Los datos de `dev.py seed` llevan «demo» en el id o el nombre y viven solo en `data/demo`.
2. **Fuente, hora y confianza a la vista.** Toda cifra o capa oficial se muestra con su nombre y un enlace. Las cifras de casos históricos van como revisiones `{valor, fuente, enlace, fecha}`.
3. **Un punto de calor no es un incendio.** «Confirmado» solo con CONAF. BRASA complementa a SENAPRED y CONAF, nunca los reemplaza ni imita sus alertas.
4. **Privacidad.** Sin cuentas: un token aleatorio por dispositivo. Las fotos se re-codifican sin EXIF. Nada de un reporte ciudadano se publica sin moderación.
5. **Secretos fuera del repositorio** (es público): van en `.env` o en los secretos de GitHub, nunca en el código ni como entradas de un workflow.

## Flujo de trabajo

1. Crea una rama desde `main`: `git switch -c tema-corto`.
2. Haz el cambio con pruebas. Cada regla nueva (un estado, un umbral, una fuente) lleva su prueba en `tests/`.
3. `python dev.py check` debe terminar en «Todo en orden». Si tocaste la interfaz, además `python dev.py e2e` con el servidor corriendo.
   `python dev.py setup` instala un gancho `pre-commit` que corre ese mismo `check` antes de cada commit (no pisa un gancho existente). Para desactivarlo, borra `.git/hooks/pre-commit` o usa `git commit --no-verify` en un commit puntual.
   El `check` incluye el presupuesto de peso del frontend (`scripts/local/presupuesto_peso.py`, umbrales al inicio del archivo): si el crecimiento es intencional, sube ahí el tope y explica por qué en `CHANGELOG.md`.
4. Si agregas una fuente de datos, documenta acceso, licencia y uso en `docs/FUENTES.md`.
5. Si el cambio se nota para las personas, súmalo a `CHANGELOG.md`.
6. Abre un pull request explicando qué cambia y cómo lo verificaste.

## Dependencias

- **Python:** el Dockerfile instala desde `requirements.lock` con `--require-hashes`. Si agregas o subes un paquete en `requirements.txt`, regenera el lock en el mismo PR: `uv pip compile requirements.txt -o requirements.lock --python-version 3.12 --generate-hashes`.
- **npm (deploy/cloudflare):** `package.json` + `package-lock.json` como siempre.
- Dependabot abre PRs semanales para pip, npm y las acciones de GitHub (`.github/dependabot.yml`).

## Estilo

**Textos**
- Español neutro, **sin voseo** (código, comentarios, interfaz, documentos y commits).
- Interfaz en dos niveles con `dual(sencillo, técnico)`: la versión sencilla, para cualquier persona; la técnica, para quien activa «Lectura detallada».
- Frases cortas y concretas. Nada de «incendio detectado» para un punto de calor ni para el Botón Rojo.

**Python**
- `from __future__ import annotations`, tipos en las firmas, funciones pequeñas.
- Comentarios en español que explican el porqué, no el qué. Docstring al inicio de cada módulo.
- Fechas en UTC con formato `AAAA-MM-DDTHH:MM:SSZ`; la hora de Chile solo al mostrar (`America/Santiago`).
- Errores de proveedores con una excepción propia; una fuente caída no debe detener el ciclo.

**Frontend**
- Módulos ES sin compilación, sin dependencias nuevas sin una buena razón (y nunca desde un CDN sin fijar la versión).
- Todo HTML dinámico pasa por `html\`\`` (escapa por defecto). Nada de `innerHTML` con datos sin escapar.
- Sin scripts en línea nuevos: la CSP los bloquea (ver `backend/security.py`).
- Colores como variables en `web/css/app.css`; claro y oscuro; contraste AA.
- Las reglas de diseño las revisa `design-taste-frontend` en `dev.py check`. Si una regla tiene una excepción justificada, anótala con `/* taste-skill-ignore: motivo */`.

## Commits

- Título en español, en presente y descriptivo: «Ficha de incidente en vivo y posibles incendios en el mapa».
- Cuerpo con el porqué y una lista breve de cambios cuando son varios.
- Un commit por cambio coherente; no mezclar una corrección con un rediseño.

## Reportar un problema

Abre un *issue* con: qué esperabas, qué pasó, la vista (`#/…`), el ancho de pantalla, la hora aproximada y, si puedes, una captura. Si es un dato equivocado, incluye la fuente correcta con enlace.
