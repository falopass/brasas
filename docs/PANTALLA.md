# Pantalla pública (UX-08)

Una página de solo lectura, pensada para mirarse a distancia (a unos 3 metros) en un
municipio, un cuartel de Bomberos o un colegio: el riesgo de hoy, el Botón Rojo y los
incendios informados de una comuna. Sin mapa, sin token, sin datos personales: solo
llama GET públicos y funciona igual en un navegador que nunca abrió BRASA.

## URL

```
https://<servidor>/web/pantalla.html?comuna=13101
https://<servidor>/web/pantalla.html?comuna=Santiago
```

`?comuna=` acepta el código de la comuna (`13101`) o su nombre, sin distinguir
tildes ni mayúsculas (`?comuna=penalolen` funciona). Sin parámetro, o con uno que no
corresponde a ninguna comuna, la página muestra un selector con las 345 comunas en
vez de quedarse en blanco.

En local, con `python dev.py run --demo`:
`http://127.0.0.1:8000/web/pantalla.html?comuna=13101`

## Qué muestra

1. Nombre de la comuna, su región y la fecha de hoy.
2. El nivel del día en palabras (bajo, moderado, alto, extremo: el 30-30-30 combinado
   con el FWI), con las razones del nivel y la anomalía de lluvia de la temporada.
3. Botón Rojo de CONAF: horas pronosticadas para hoy y los próximos días, con la
   proporción de la comuna en condición.
4. Avisos vigentes de la Dirección Meteorológica (viento y calor extremo) que tocan
   la comuna.
5. Incendios informados por CONAF en las últimas 48 h que tocan la comuna: los
   filtra por el nombre que reporta CONAF o por el punto dentro de la caja de la
   comuna (la caja es rectangular: un incendio en el borde de una comuna vecina
   puede aparecer; el nombre reportado siempre se muestra).
6. Las últimas detecciones satelitales de la comuna (máximo 10), con su estado.
7. «Datos: hace X min», la hora del último refresco y un botón Actualizar; la
   página se refresca sola cada 5 minutos.
8. El aviso fijo «No es una alerta oficial: sigue a SENAPRED (senapred.cl)» y los
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
