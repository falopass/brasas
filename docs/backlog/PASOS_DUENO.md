# Lo que queda en manos de Diego

Ya no queda nada por implementar: el 24-10 se integraron las tres fuentes de gobierno
(SENAPRED, SINCA, MINVU) con atribución y enlace. Lo único que sigue fuera del código es
**esperar las respuestas** de las consultas de licencia/acceso que ya quedaron enviadas (o
por enviar) por los canales oficiales:

- **SENAPRED** — solicitud de feed público de alertas (idealmente CAP) por el formulario de
  Ley de Transparencia de <https://senapred.cl/>. Si responden con un servicio oficial, se
  migra `backend/providers/senapred.py` a él; mientras, se usa el acceso anónimo del portal.
- **MMA / SINCA** — consulta de licencia de reutilización de los datos de SINCA por
  Transparencia en <https://mma.gob.cl/>. Si responden con licencia (o la niegan), se anota
  en `docs/FUENTES.md` junto a la fila de SINCA.
- **MINVU** — consulta de reutilización del Catastro de Campamentos a `ideminvu@minvu.cl`
  (o por Transparencia en minvu.cl). Igual: la respuesta se anota en `docs/FUENTES.md`.

Ningún valor de clave se pega en el chat, en issues ni en el repositorio. Si alguna
respuesta dice «no», la capa correspondiente se retira y queda solo el enlace oficial —
la app ya degrada así cuando la fuente falla.
