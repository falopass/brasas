---
id: OFI-33
repo: brasas
rama: feat/estacion-dmc-cercana
modelo: swe-2-high
riesgo: C
archivos: backend/providers/dmc_stations.py, backend/routes/climate.py, web/js/views/zona.js, tests/test_dmc_estaciones.py, docs/FUENTES.md, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
---

# OFI-33 · Estación DMC más cercana: hace falta la clave del portal (decisión de Diego)

## Por qué es delicado (riesgo C) y no se lanza solo
El servicio JSON de la DMC **exige credenciales**: la documentación oficial del portal
(`https://climatologia.meteochile.gob.cl/application/documentacion/getDocumento/2`) publica la URL así:

```
…/application/servicios/getDatosRecientesEma/330020?usuario=correo@correo.cl&token=apiKey_personal
```

Es decir, correo + **apiKey personal**. BRASA no puede generar esa clave: la crea el dueño y va como
secreto del despliegue. Sin ella, la fuente no se puede integrar.

## Qué se ganaría
Hoy «Mi zona» y la ficha de riesgo muestran **pronóstico** (Open-Meteo). Con la estación más cercana
mostrarían también **lo que se midió de verdad** a pocos kilómetros: «Estación Talca, a 8 km: 31,2 °C,
22 % de humedad y 18 km/h a las 14:20». Eso corrige la lectura del pronóstico en las comunas con
estación, que es el punto P1 n.º 2 de `docs/ROADMAP.md` y el «siguiente paso documentado» de
`docs/FEATURES_INVESTIGACION.md` (§1, nota de la estación DMC).

El portal documenta además el catastro de estaciones (código nacional, lat/lon, altura) y el resumen
diario; todo con el mismo esquema de clave.

## Qué necesita de Diego
1. Registrarse en el portal de servicios climáticos de la DMC y entregarme la `apiKey` (la cargo como
   secreto de Cloudflare; no va al repo).
2. Decidir si esa observación se muestra solo cuando la estación está a menos de N km del lugar
   (propongo 25 km) y siempre con el nombre de la estación y su hora.

## Plan si se aprueba (para otra ronda)
- `backend/providers/dmc_stations.py`: catastro en caché 24 h + última lectura por estación en caché 10 min.
- `GET /api/climate/station?lat=&lon=` en `backend/routes/climate.py` (fuera de `public.py` para no chocar con otros encargos).
- Tarjeta en `web/js/views/zona.js`: observación real junto al pronóstico, con fuente y hora; si no hay estación cerca o la fuente falla, no se muestra nada (nunca un dato inventado).
- `tests/test_dmc_estaciones.py` con la respuesta JSON mockeada; `docs/FUENTES.md` con la licencia/atribución de la DMC.

Verifica con `/verificar` y entrega con `/entregar-pr` **solo si Diego aprueba y entrega la clave**. No mergees por iniciativa propia.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
