# Lo que queda en manos de Diego

Los tres encargos abiertos no se pueden cerrar desde el código: necesitan una cuenta, una clave o
una respuesta de un organismo. Aquí están los pasos concretos y los borradores listos para enviar.
Ningún valor de clave se pega en el chat, en issues ni en el repositorio.

## OFI-04 · Alerta oficial de SENAPRED en la app

Ya está el enlace «Consulta la alerta oficial vigente en SENAPRED» (opción 2, sin permiso). Para
mostrar la alerta misma hace falta un acceso formal. Envíala por el formulario de Ley de
Transparencia o de contacto de SENAPRED (<https://senapred.cl/>):

> **Asunto:** Solicitud de acceso a un feed público de alertas vigentes (CAP) para una app ciudadana
>
> Estimados: soy Diego, desarrollador de BRASA Chile (https://brasa-chile.ddiegosebastianbb.workers.dev),
> una aplicación gratuita que avisa a vecinos de focos de incendio cercanos con datos de CONAF, NASA y
> la DMC, y que remite siempre a SENAPRED como autoridad. Quisiéramos mostrar, junto a cada comuna, la
> alerta oficial vigente de SENAPRED, con su enlace y sin modificar su texto.
> ¿Existe o existirá un feed público (idealmente CAP 1.2, como el de la DMC) o un servicio de consulta
> que podamos usar, y en qué condiciones? Mientras tanto solo enlazamos a senapred.cl/alertas.
> Quedo atento. Saludos, Diego.

## OFI-10 · SINCA (calidad del aire medida)

Ya está el enlace «Ver la calidad del aire medida en SINCA» (opción 2). Para mostrar los valores, el
portal debe autorizar la reutilización: dice «Todos los derechos reservados» y no declara licencia.
Envía la consulta por Ley de Transparencia al Ministerio del Medio Ambiente (<https://mma.gob.cl/>):

> **Asunto:** Licencia de reutilización de los datos de SINCA
>
> Estimados: desarrollo BRASA Chile, una aplicación gratuita de alertas de incendio. Quisiéramos
> mostrar, para cada comuna, el MP2,5 medido de la estación SINCA más cercana, marcado como
> «preliminar», con el nombre de la estación, la hora y un enlace a sinca.mma.gob.cl.
> ¿Bajo qué licencia o condiciones se pueden reutilizar los datos de SINCA (por ejemplo CC BY 4.0)?
> Saludos, Diego.

## OFI-25 · Campamentos del MINVU

La fuente está identificada: el servicio oficial `Catastros_campamentos` del MINVU en
<https://geoide.minvu.cl/server/rest/services/Catastros/Catastros_campamentos/FeatureServer>
(ficha en el Geoportal de Chile). Su campo de licencia está vacío. Dos decisiones tuyas:
1. Si quieres que BRASA muestre cuántos campamentos y hogares hay por comuna (solo el agregado, nunca
   puntos ni nombres).
2. Si te parece, envía esta consulta al contacto de la ficha, `ideminvu@minvu.cl`:

> **Asunto:** Condiciones de reutilización del Catastro Nacional de Campamentos
>
> Estimados: desarrollo BRASA Chile, una aplicación gratuita de alertas de incendio. Quisiéramos usar
> el Catastro Nacional de Campamentos solo agregado por comuna (número de campamentos y de hogares),
> citando al MINVU, para que la exposición al riesgo considere a quienes viven en asentamientos.
> ¿Bajo qué licencia se puede reutilizar ese dato? Saludos, Diego.
