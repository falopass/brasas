# Guía para municipios y juntas de vecinos

Cómo adoptar BRASA en una municipalidad o junta de vecinos sin inventar nada: qué es, qué se puede enlazar, qué datos se pueden citar y qué le pedimos al municipio.

## 1. Qué es BRASA

BRASA es una herramienta ciudadana que reúne datos públicos (satélites NASA FIRMS y GOES, reportes de incendios de CONAF, pronóstico Botón Rojo y modelos meteorológicos) y los muestra en palabras simples: focos cercanos a un lugar guardado, riesgo por comuna a 7 días y reconstrucción de incendios históricos. Responde una pregunta concreta: *«¿mi casa o mi familia están en riesgo hoy?»*.

**Lo que no es:** un sistema oficial de alerta. La autoridad en emergencias es **SENAPRED**; las instrucciones de SENAPRED, CONAF, Bomberos, Carabineros o el propio municipio siempre prevalecen sobre lo que muestre BRASA, y los mensajes SAE del celular no se reemplazan. El descargo completo está en [`TERMINOS.md`](TERMINOS.md).

Emergencias reales: **130 CONAF · 132 Bomberos · 131 SAMU · 133 Carabineros · 134 PDI**.

## 2. Cómo usarlo en el municipio

- **Enlace público:** la aplicación vive en `https://brasa-chile.ddiegosebastianbb.workers.dev`. Se puede enlazar libremente desde el sitio web municipal, redes o material impreso (un QR apunta a esa misma dirección).
- **Pantalla en sala de espera o hall:** hoy se usa el enlace normal en un navegador; la vista `#/mapa` muestra los focos recientes y `#/riesgo` el semáforo por comuna. Un modo dedicado para pantallas fijas **aún no existe** en la aplicación; está previsto, pero no debe ofrecerse como disponible.
- **Personas usuarias:** cada vecino guarda sus propios lugares (casa, parcela, familia) en su dispositivo, sin crear cuenta. Nada que instalar: es una web.

**Qué no se debe hacer:**

- Presentar BRASA como canal oficial de alerta ni como reemplazo del SAE, de SENAPRED o de la oficina de emergencias municipal.
- Prometer avisos que la aplicación no entrega (por ejemplo, «aviso de evacuación» o «alerta municipal»): BRASA avisa focos de calor cercanos y riesgo meteorológico, nada más.
- Prometer disponibilidad: es un proyecto ciudadano sin SLA (ver sección 6).

## 3. Qué datos se pueden citar y cómo

| Dato | Fuente | Atribución sugerida |
|---|---|---|
| Incendios informados por CONAF (estado oficial, superficie, comuna) | Reporte público de la Gerencia de Protección contra Incendios Forestales de CONAF (GEPRIF) | «Incendios informados por CONAF (GEPRIF)», con enlace al tablero o a la fuente indicada en [`FUENTES.md`](FUENTES.md) |
| Pronóstico Botón Rojo a 5 días por comuna | Capa pública de CONAF (Depto. de Desarrollo e Investigación, GEPRIF) | «Pronóstico Botón Rojo de CONAF», con enlace al tablero de CONAF indicado en `FUENTES.md` |

Reglas:

- Al citar un dato visto en BRASA, la atribución va a la **fuente original** (CONAF, NASA FIRMS, NOAA, Open-Meteo), que es lo que la propia aplicación muestra en pantalla junto a cada cifra.
- **No se autoriza aún redistribuir los datos propios de BRASA** (incidentes reconstruidos, observaciones, estado de alerta calculado). La licencia del repositorio está pendiente de decisión (ítem SEC-14 del backlog); hasta que se defina, citar el dato con su fuente oficial y enlazar a la aplicación es la forma correcta.

## 4. Qué necesita BRASA del municipio

Dos cosas, ambas baratas:

1. **Información de emergencia comunal, en cualquier formato** (plano, PDF, lista, KML, GeoJSON, planilla):
   - Rutas de evacuación y puntos de encuentro (ítem OFI-15).
   - Albergues y cómo se comunica cuáles están activos durante una emergencia (ítem OFI-16).
   - Hoy BRASA solo usa lo publicado en OpenStreetMap; lo que el municipio entregue se incorpora con su fuente citada.
2. **Una persona de contacto técnica** (oficina de emergencias, prevención o informática) para resolver dudas de formato y avisar cuando la información cambie.

No se pide dinero, exclusividad ni desarrollo a medida.

## 5. Guion de reunión (20 minutos)

1. **(3 min)** Qué es BRASA y qué no es: complemento ciudadano, no alerta oficial; la autoridad es SENAPRED.
2. **(5 min)** Demostración en vivo: abrir la aplicación, guardar un lugar en la comuna, mostrar estado del lugar, mapa de focos, semáforo de riesgo y un caso histórico de la zona si existe.
3. **(3 min)** Cómo lo usa un vecino: enlace, sin instalación ni cuenta; enlace familiar de solo lectura para personas mayores.
4. **(3 min)** Qué puede hacer el municipio hoy: enlazarlo en su web y RRSS con el descargo («herramienta ciudadana, no oficial»).
5. **(4 min)** La petición: rutas de evacuación, puntos de encuentro y albergues en cualquier formato, más un contacto técnico.
6. **(2 min)** Cierre: qué no prometemos (sección 6) y próximo paso concreto con fecha.

## 6. Contacto y qué no prometemos

- **Contacto:** el canal de contacto del proyecto está por definir; mientras tanto, la vía es el repositorio público del proyecto.
- **Sin SLA:** el servicio puede estar caído, desactualizado o equivocado; no hay garantía de disponibilidad ni tiempos de respuesta.
- **Sin alertas oficiales:** BRASA nunca reemplaza al SAE ni a la autoridad; una pantalla sin focos no significa que no haya fuego.
- **Sin cobertura garantizada:** la detección depende de pasadas satelitales y condiciones (nubes, humo); los avisos al celular dependen de la conectividad de cada persona.

*Última actualización: octubre de 2026.*
