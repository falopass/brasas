# Evaluación de impacto en protección de datos (EIPD) — BRASA Chile

**Alcance:** tratamiento de datos personales de BRASA frente a la Ley 21.719 (vigente el 1 de diciembre de 2026).
**Responsable del tratamiento:** la persona dueña del proyecto `falopass/brasas` (ver repositorio). Encargado de protección de datos: la misma persona mientras el proyecto no tenga figura jurídica.
**Fecha:** 18 de octubre de 2026. **Estado:** evaluación inicial; revisar antes de la vigencia de la ley y tras la asesoría legal (SEC-07).

## 1. Qué se trata

| Dato | Finalidad | Base | Plazo |
|---|---|---|---|
| Identificador aleatorio del dispositivo | Asociar lugares, avisos y suscripciones sin cuentas | Ejecución del servicio | Hasta supresión del usuario |
| Lugares (nombre, coordenadas, radio, tipo) | Calcular y enviar avisos relevantes | Consentimiento del uso | Hasta supresión |
| Marca «persona mayor» | Adelantar el umbral de aviso a «urgente» | Consentimiento explícito (SEC-03) | Hasta que se quite o se borre el lugar |
| Historial de avisos | Revisión del propio usuario | Ejecución del servicio | 12 meses (FIX-21) |
| Suscripciones push / Telegram | Entrega de avisos | Consentimiento al activarlas | Hasta supresión o baja del canal |
| Reportes (descripción, coordenadas, foto) | Verificación y publicación de focos | Consentimiento al reportar | 90 días sin verificar/descartados; 2 años verificados (FIX-21) |
| Enlace familiar (`share_token`) | Vista de solo lectura del lugar | Consentimiento al compartir | Hasta revocación |
| IP / User-Agent | — | **No se registran** (SEC-04). La IP vive solo en memoria del limitador de solicitudes. | — |

**Encargado:** Cloudflare (contenedor y R2), con **transferencia internacional** de datos. El respaldo de la base viaja a R2 sin cifrado propio todavía (SEC-06, pendiente).

## 2. Riesgos identificados

| Riesgo | Probabilidad | Impacto | Medida |
|---|---|---|---|
| **Mapa de casas de personas mayores:** la tabla `places` concentrada es valiosa para un delincuente | Baja | Muy alto | Sin cuentas ni identificadores personales; la base no es pública; cifrado del respaldo en R2 (SEC-06, pendiente); acceso solo con token del dispositivo |
| Acceso a lugares de otro dispositivo | Media | Alto | Token aleatorio de 32 bytes por dispositivo, requerido en `X-Brasa-Token`; sin listado ni enumeración |
| Enlace familiar expone ubicación y marca «persona mayor» | Media | Alto | Aviso explícito antes de compartir (SEC-03); revocable en cualquier momento; solo lectura |
| Foto de reporte con metadatos o caras | Media | Medio | La interfaz informa que se limpian los datos ocultos; moderación humana antes de publicar; retención acotada |
| Fuga del respaldo en R2 | Baja | Alto | Bucket privado servido solo por el Worker; cifrado previsto (SEC-06) |
| Enumeración de endpoints push/Telegram | Baja | Medio | Solo en la base interna; no se expone en ninguna API pública |
| Datos de menores (un joven marca lugares de su casa) | Media | Medio | Sin datos identificativos; minimización; política en lenguaje simple |
| Retención infinita | Resuelto | — | Purga automática por plazos (FIX-21) documentada en la política |

## 3. Medidas adoptadas (Ola 3)

- **Minimización (SEC-04):** sin cuentas, sin IP ni `User-Agent` en la base, sin nombre ni contacto en los reportes, ubicación pública redondeada a ~100 m.
- **Derechos (SEC-02):** `GET /api/me/export` (portabilidad) y `DELETE /api/me` (supresión en cascada), con botones en Ajustes.
- **Consentimiento (SEC-03):** texto informado junto a la marca «persona mayor» y aviso antes de compartir el enlace familiar.
- **Transparencia (SEC-01/SEC-08):** página `#/privacidad` en dos niveles y `docs/TERMINOS.md` con el descargo «no oficial».
- **Retención (FIX-21):** purga programada de avisos y reportes con sus fotos; las fotos remotas se sobrescriben con cero bytes (R2 no admite DELETE).

## 4. Riesgos residuales y deuda

- Respaldo de `brasa.db` en R2 sin cifrado propio: cubierto por el acceso privado del bucket; **mitigar con SEC-06**.
- Tokens de moderación compartidos (`ADMIN_TOKEN` único): un acceso indebido no se puede atribuir a una persona; **mitigar con SEC-10**.
- `share_token` en la URL: quien tenga el enlace ve el lugar; aceptado por diseño, revocable.
- Sin figura jurídica ni asesoría legal todavía: **SEC-07 decide si hace falta un responsable formal**.

## 5. Decisión

Continuar operando con las medidas de la Ola 3. El riesgo mayor (mapa de casas de personas mayores) queda en nivel bajo por diseño (sin identidad, sin acceso público) y baja aún más con el cifrado del respaldo (SEC-06). Revisar esta evaluación tras la asesoría legal (SEC-07) y al activar cualquier función que exponga datos nuevos.
