# Pantalla pública (UX-08, extendida por UX-45)

Una página de solo lectura, pensada para mirarse a distancia (a unos 3 metros) en un
municipio, un cuartel de Bomberos o un colegio: el riesgo de hoy, el Botón Rojo y los
incendios informados de una comuna. Sin mapa, sin token, sin datos personales: solo
llama GET públicos y funciona igual en un navegador que nunca abrió BRASA.

## URL

```
https://<servidor>/web/pantalla.html?comuna=13101
https://<servidor>/web/pantalla.html?comuna=Santiago
https://<servidor>/web/pantalla.html?comunas=13201,13202,13203&rotar=60
```

`?comuna=` acepta el código de la comuna (`13101`) o su nombre, sin distinguir
tildes ni mayúsculas (`?comuna=penalolen` funciona). Sin parámetro, o con uno que no
corresponde a ninguna comuna, la página muestra un selector con las 345 comunas en
vez de quedarse en blanco.

`?comunas=` acepta varias comunas separadas por coma (códigos o nombres, con las
mismas reglas de `?comuna=`) y la pantalla **rota entre ellas** sin recargar la
página: arriba se ve «Comuna 1 de 3 · cambia en N s». `?rotar=` fija los segundos
entre comuna y comuna (mínimo 5, máximo 300; 45 por defecto). Para que dé tiempo
de leer cada pantalla, 25 segundos o más es lo razonable. Con una sola comuna la
página se comporta igual que con `?comuna=`. Si `?comunas=` viene vacío o ninguna
entrada coincide con la lista, la página cae en el selector sin romperse; y elegir
una comuna a mano en el selector sale de la rotación.

Ejemplo para un municipio que quiere rotar tres comunas de su zona:

```
https://<servidor>/web/pantalla.html?comunas=Puente Alto,Pirque,San José de Maipo&rotar=60
```

En local, con `python dev.py run --demo`:
`http://127.0.0.1:8000/web/pantalla.html?comuna=13101`

## Qué muestra

1. Nombre de la comuna, su región y la fecha de hoy.
2. El nivel del día en palabras (bajo, moderado, alto, extremo: el 30-30-30 combinado
   con el FWI), con las razones del nivel y la anomalía de lluvia de la temporada.
3. El comparador «¿Viene peor que la semana pasada?»: una fila por día con el
   pronóstico de hoy frente al que se emitió hace siete días para ese mismo día
   (Sube, Baja, Igual o Sin comparación), de `/api/risk/{code}/trend`. Mide cómo
   cambió la expectativa, no lo que ocurrió; si la consulta falla, la sección lo
   dice y el resto de la pantalla sigue funcionando.
4. Botón Rojo de CONAF: horas pronosticadas para hoy y los próximos días, con la
   proporción de la comuna en condición.
5. Avisos vigentes de la Dirección Meteorológica (viento y calor extremo) que tocan
   la comuna.
6. Incendios informados por CONAF en las últimas 48 h que tocan la comuna: los
   filtra por el nombre que reporta CONAF o por el punto dentro de la caja de la
   comuna (la caja es rectangular: un incendio en el borde de una comuna vecina
   puede aparecer; el nombre reportado siempre se muestra).
7. Las últimas detecciones satelitales de la comuna (máximo 10), con su estado.
8. «Datos: hace X min», la hora del último refresco y un botón Actualizar; la
   página se refresca sola cada 5 minutos.
9. El aviso fijo «No es una alerta oficial: sigue a SENAPRED (senapred.cl)» y los
   teléfonos de emergencia.

## Qué NO garantiza

- **No es una alerta oficial.** BRASA resume datos de CONAF, la DMC y satélites;
  no reemplaza a SENAPRED ni a la autoridad local.
- **No es en tiempo real.** Las detecciones satelitales pueden llegar con decenas
  de minutos de atraso; «Datos: hace X min» muestra esa antigüedad. Que la pantalla
  no muestre fuego no significa que no lo haya: si se ve humo o llamas, se llama al
  132 (Bomberos) o al 130 (CONAF).
- **No confirma incendios.** «Informado por CONAF» solo reproduce el reporte
  oficial; los incidentes satelitales pueden ser un incendio, una quema o una
  industria.

## Comprobación

Con el servidor corriendo (`python dev.py seed` y `python dev.py run --demo`):

```bash
.venv/bin/python scripts/local/pantalla_check.py \
  --url 'http://127.0.0.1:8000/web/pantalla.html?comuna=13101'
```

Abre la página en Chromium, verifica el nombre de la comuna, el aviso de que no es
oficial y que no haya errores de consola; sale con 0 solo si todo pasa.
