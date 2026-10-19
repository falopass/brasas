# Política de contenido de los reportes ciudadanos

Qué se acepta, qué se rechaza y cómo se modera lo que los vecinos envían a **BRASA Chile**. Complementa los [términos de uso](TERMINOS.md) y la política de privacidad de la aplicación (`#/privacidad`).

Los reportes existen para una sola cosa: avisar a otras personas de un posible incendio. Nada se publica sin revisión humana.

## Qué se acepta

Reportes sobre un hecho concreto y reciente relacionado con un incendio o su entorno:

- **Humo visible**, **llamas visibles**, **quema o fogata** y la categoría **«otro»** para lo que no calce (ceniza cayendo, olor fuerte a quemado, cortafuegos dañado).
- Ubicación aproximada del hecho (la que declara quien reporta, no el GPS del teléfono).
- Descripción corta (máximo 600 caracteres) de lo que se ve.
- Foto opcional del hecho: humo, llamas, daños, condiciones del entorno. La foto se re-codifica al subirla — se eliminan EXIF, GPS y demás metadatos — y se reduce a 1600 px y 8 MB máximo.

**Regla de oro para las fotos:** que muestren el fuego o el entorno, no a las personas. Fotos sin rostros, sin patentes, sin direcciones ni datos de terceros.

## Qué se rechaza

Un moderador descarta el reporte —y la foto se borra con él— cuando contiene o es:

- **Personas identificables**: rostros reconocibles, heridos, víctimas o cualquier imagen de una persona sin su consentimiento.
- **Datos de terceros**: patentes de vehículos, direcciones, nombres, teléfonos o cualquier dato personal de otra persona, en la foto o en el texto.
- **Violencia o contenido gráfico** ajeno al hecho, contenido ilegal, sexual o de acoso.
- **Publicidad, spam o autopromoción**; enlaces que no aportan al aviso.
- **Duplicados**: el sistema agrupa los avisos del mismo punto y tipo en una ventana de 3 horas y 1,5 km. Lo que llega repetido no abre otra fila en la cola ni se descarta a ciegas: queda registrado como **corroboración** («otro vecino lo vio») del primer aviso, y ese conteo ayuda al moderador a priorizar. Si el primer aviso no traía foto, se conserva la del segundo. La corroboración **no** es verificación oficial ni reemplaza la revisión humana: solo dice que más de una persona reportó lo mismo.
- **Contenido falso o ajeno a un incendio**: imágenes de otra fecha o lugar, bromas, pruebas del sistema.
- **Envío abusivo o automatizado**: el servicio ya frena esto con verificación de persona (Cloudflare Turnstile) y un límite de 6 reportes por hora por IP; el abuso reiterado puede llevar a descartar toda la cola del origen.

Ante la duda entre publicar o no un contenido sensible (una persona de espaldas pero reconocible, una placa legible), el criterio es **descartar**: BRASA prefiere perder un aviso antes que exponer a alguien. La Ley 21.719 manda aquí.

## Cómo se modera

- Todo reporte entra como **«En revisión»** y solo un moderador puede pasarlo a **«Verificado»** (se muestra públicamente) o **«Descartado»** (nunca se muestra).
- Cada decisión queda registrada con su hora y una nota del moderador (máximo 300 caracteres), visible para quien envió el reporte desde «mis reportes».
- Un reporte verificado puede revertirse si aparece información nueva (por ejemplo, se comprueba que era falso), y un descarte erróneo puede corregirse de la misma manera.
- Verificar un reporte es solo confirmar que el aviso es plausible y cumple esta política. **No es una verificación oficial del incendio**: la autoridad es SENAPRED/CONAF.
- Cuando un reporte reúne corroboraciones, la cola lo muestra primero y la ficha pública indica «N vecinos lo vieron». Es solo un conteo de testigos — nunca se publica quién corroboró — y la decisión de publicar sigue siendo del moderador.

## Plazos de revisión

La moderación es voluntaria y el aviso tiene fecha de vencimiento propia: un reporte que nadie revisa dentro de su ventana **caduca solo** y queda como «descartado», con la nota «Caducó sin revisar». Las ventanas, definidas en `backend/reports.py`, son:

| Tipo | Vigencia sin revisar |
|---|---|
| Humo | 6 horas |
| Llamas | 24 horas |
| Quema o fogata | 72 horas |
| Otro | 24 horas |

**Meta del equipo:** en temporada de incendios (aprox. diciembre a marzo) revisar la cola en menos de 2 horas, para que incluso el humo alcance a ser útil; fuera de temporada, al menos una vez al día. Si un reporte caduca, no es un rechazo al contenido: significa que el hecho ya no está vigente.

## Qué pasa con un reporte descartado

- Nunca se muestra en el mapa ni en la lista pública; su foto solo existía en la cola de revisión.
- El registro se conserva 90 días (coordenadas, texto y foto) por si hay que corregir un error o auditar una decisión, y después se borra junto a su foto.
- Los reportes verificados se conservan 2 años, con su foto. Plazos completos en la política de privacidad.
- Quien envió el reporte puede ver su estado y la nota del moderador desde la propia aplicación.

## Errores y apelaciones

Los reportes son anónimos por diseño: no hay cuenta ni correo asociado, así que no hay un proceso de apelación personal. Si un moderador se equivocó:

- La forma práctica de corregirlo es **enviar el reporte de nuevo** con la foto correcta.
- Para reclamos o preguntas sobre una decisión de moderación, abre un issue en [github.com/falopass/brasas](https://github.com/falopass/brasas/issues).

## Quién modera

La moderación la hace un equipo pequeño de voluntarios con acceso al panel interno (`/admin`), protegido por un token compartido (`X-Admin-Token`) que solo tienen los moderadores. Si el servidor no tiene token configurado, la moderación no está disponible y los reportes caducan sin publicarse — nunca se publican solos.

## Cambios a esta política

Los cambios se publican en este archivo y, si afectan a quienes reportan, se anuncian en la aplicación y en `CHANGELOG.md`.

*Última actualización: 19 de octubre de 2026.*
