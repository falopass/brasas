/* Estado del servicio en palabras (OPS-14 / ESTADO-01).
 *
 * Traduce el JSON de /api/status a tres bloques que entiende cualquiera: frescura de
 * los datos, estado de cada fuente y respaldo del ciclo. No inventa datos: si falta
 * un campo, lo dice; la página solo llama a esta función con lo que respondió el
 * servidor y, si no respondió, muestra su propio mensaje con «Reintentar».
 *
 * `summarizeStatus` es pura para poder probarla con node:test sin navegador.
 */

const PRODUCT_NAMES = {
  GOES19_FDCF: 'GOES',
  GOES16_FDCF: 'GOES',
  'ABI-L2-FDCF': 'GOES',
  'ABI-L2-ADPF': 'el humo de GOES',
  GOES19_GLM: 'los rayos de GOES',
  GLM_L2_LCFA: 'los rayos de GOES',
  VIIRS_NOAA20_NRT: 'VIIRS',
  VIIRS_NOAA21_NRT: 'VIIRS',
  VIIRS_SNPP_NRT: 'VIIRS',
  MODIS_NRT: 'MODIS',
  DMC_CAP: 'los avisos de la DMC',
  BOTON_ROJO: 'el Botón Rojo',
  CONAF_INCENDIOS: 'los incendios de CONAF',
};

const nombreFuente = (clave) => {
  const key = String(clave || '');
  if (PRODUCT_NAMES[key]) return PRODUCT_NAMES[key];
  const limpio = key.replace(/_/g, ' ').trim().toLowerCase();
  return limpio || 'una fuente';
};

const capitalizar = (texto) => (texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : texto);

/** Duración en palabras: «menos de un minuto», «47 minutos», «3 horas», «2 días». */
function hace(segundos) {
  if (!Number.isFinite(segundos)) return null;
  if (segundos < 60) return 'menos de un minuto';
  if (segundos < 3600) return `${Math.round(segundos / 60)} minutos`;
  if (segundos < 86400) return `${Math.round(segundos / 3600)} horas`;
  return `${Math.round(segundos / 86400)} días`;
}

function edadDe(marca) {
  if (typeof marca !== 'string' || !marca) return null;
  const momento = Date.parse(marca);
  if (!Number.isFinite(momento)) return null;
  return Math.max(0, Math.round((Date.now() - momento) / 1000));
}

const recortar = (texto, tope = 160) => (texto.length > tope ? `${texto.slice(0, tope - 1)}…` : texto);

export function summarizeStatus(payload = {}) {
  const datos = payload && typeof payload === 'object' ? payload : {};
  const frescura = datos.freshness && typeof datos.freshness === 'object' ? datos.freshness : {};
  const edad = Number.isFinite(frescura.age_seconds) ? frescura.age_seconds : null;
  const freshness = edad === null
    ? 'No hay dato de la última lectura de los satélites.'
    : frescura.stale
      ? `Atrasados: la última lectura es de hace ${hace(edad)}.`
      : `Datos de los satélites: hace ${hace(edad)}.`;

  const errores = datos.errors && typeof datos.errors === 'object' && !datos.errors.error ? datos.errors : {};
  const porProducto = errores.by_product && typeof errores.by_product === 'object' ? errores.by_product : {};
  const corridas = Array.isArray(datos.runs) ? datos.runs : [];
  const ultima = new Map();
  for (const corrida of corridas) {
    if (corrida && corrida.product && !ultima.has(corrida.product)) ultima.set(corrida.product, corrida);
  }
  const claves = [...new Set([...Object.keys(porProducto), ...ultima.keys()])];
  const sources = claves.map((clave) => {
    const info = porProducto[clave] && typeof porProducto[clave] === 'object' ? porProducto[clave] : {};
    const fallos = Number(info.failed) || 0;
    const corridasN = Number(info.runs) || 0;
    const nombre = nombreFuente(clave);
    const fallo = fallos
      ? `${capitalizar(nombre)} falló ${fallos} ${fallos === 1 ? 'vez' : 'veces'} en las últimas 24 horas.`
      : `${capitalizar(nombre)} no falló en las últimas 24 horas.`;
    const corrida = ultima.get(clave);
    const edadCorrida = corrida ? edadDe(corrida.finished_at || corrida.started_at) : null;
    const ultimaTexto = corrida
      ? `La última corrida ${corrida.ok ? 'terminó bien' : 'terminó con error'}${edadCorrida === null ? '' : ` hace ${hace(edadCorrida)}`}.`
      : 'No hay dato de la última corrida.';
    return { product: clave, name: nombre, runs: corridasN, failed: fallos, text: `${fallo} ${ultimaTexto}` };
  });

  const ciclo = datos.last_cycle && typeof datos.last_cycle === 'object' ? datos.last_cycle : {};
  const errorRespaldo = typeof ciclo.backup_error === 'string' ? ciclo.backup_error.trim() : '';
  const detalleRespaldo = errorRespaldo ? `: ${recortar(errorRespaldo)}` : '';
  let backup;
  if (ciclo.backup === false) {
    backup = `El respaldo falló${detalleRespaldo}. Es la copia de seguridad fuera del servidor: los datos nuevos no tienen copia hasta que vuelva a funcionar.`;
  } else if (ciclo.backup === true) {
    backup = `El respaldo se subió bien${detalleRespaldo}.`;
  } else {
    backup = `No hay dato del respaldo${detalleRespaldo}.`;
  }

  const partesCiclo = [];
  if (ciclo.finished_at) {
    const edadCiclo = edadDe(ciclo.finished_at);
    partesCiclo.push(edadCiclo === null ? 'No hay dato del último ciclo.' : `El último ciclo terminó hace ${hace(edadCiclo)}.`);
  } else {
    partesCiclo.push('No hay dato del último ciclo.');
  }
  if (ciclo.error) partesCiclo.push(`El último ciclo terminó con un error (${ciclo.error}).`);
  const cycle = partesCiclo.join(' ');

  return {
    freshness,
    sources,
    backup,
    cycle,
    text: [freshness, ...sources.map((s) => s.text), backup, cycle].join(' '),
  };
}

/* La página solo se engancha cuando hay DOM; node:test importa la función pura. */
function iniciar() {
  const app = document.getElementById('estado');
  const reintentar = document.getElementById('reintentar');
  if (!app || !reintentar) return;

  const bloque = (titulo, lineas) => {
    const h = document.createElement('h2');
    h.textContent = titulo;
    const ul = document.createElement('ul');
    for (const linea of lineas.filter(Boolean)) {
      const li = document.createElement('li');
      li.textContent = linea;
      ul.append(li);
    }
    return [h, ul];
  };

  const pintar = (payload) => {
    const resumen = summarizeStatus(payload);
    const fuentes = resumen.sources.length
      ? resumen.sources.map((s) => s.text)
      : ['No hay fuentes con corridas recientes.'];
    app.replaceChildren(
      ...bloque('Datos de los satélites', [resumen.freshness]),
      ...bloque('Fuentes', fuentes),
      ...bloque('Respaldo y ciclo', [resumen.backup, resumen.cycle]),
    );
  };

  const cargar = async () => {
    reintentar.hidden = true;
    app.replaceChildren();
    const espera = document.createElement('p');
    espera.className = 'muted';
    espera.textContent = 'Consultando el estado…';
    app.append(espera);
    try {
      const respuesta = await fetch('/api/status', { headers: { accept: 'application/json' } });
      if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
      pintar(await respuesta.json());
    } catch {
      app.replaceChildren();
      const aviso = document.createElement('p');
      const fuerte = document.createElement('b');
      fuerte.textContent = 'No pudimos consultar el estado.';
      aviso.append(fuerte, ' Revisa tu conexión y vuelve a intentarlo.');
      app.append(aviso);
      reintentar.hidden = false;
    }
  };

  reintentar.addEventListener('click', cargar);
  cargar();
}

if (typeof document !== 'undefined') iniciar();
