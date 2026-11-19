/* OPS-06 — minifica los assets de web/ (JS y CSS) antes de desplegar.

El repositorio guarda el código legible: la minificación ocurre solo en el
workspace del despliegue (deploy-cloudflare.yml), así el CI y las pruebas
siguen viendo el fuente y revertir es quitar el paso del workflow. No toca:

- Los HTML: la CSP fija los hashes de los scripts en línea (backend/security.py
  y deploy/cloudflare/src/index.ts).
- web/sw.js: el workflow le escribe la versión del commit después de minificar.
- web/vendor: ya viene minificado (MapLibre) y no entra en el presupuesto.

Uso:
  node build-web.mjs                    minifica ../../web en el lugar
  node build-web.mjs --salida <dir>     copia web/ a <dir> y minifica la copia
                                        (para medir el resultado sin tocar el fuente)
*/
import { cp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { transform } from 'esbuild';

const AQUI = dirname(fileURLToPath(import.meta.url));
const WEB = join(AQUI, '..', '..', 'web');

function argumento(nombre) {
  const i = process.argv.indexOf(nombre);
  return i === -1 ? null : process.argv[i + 1];
}

async function archivos(dir, extension, out = []) {
  for (const entrada of await readdir(dir, { withFileTypes: true })) {
    const ruta = join(dir, entrada.name);
    if (entrada.isDirectory()) await archivos(ruta, extension, out);
    else if (entrada.name.endsWith(extension)) out.push(ruta);
  }
  return out;
}

async function minificar(web) {
  const trabajos = [
    ...(await archivos(join(web, 'js'), '.js')).map((ruta) => ({ ruta, loader: 'js' })),
    ...(await archivos(join(web, 'css'), '.css')).map((ruta) => ({ ruta, loader: 'css' })),
  ];
  // En tandas: esbuild es rápido, pero 75 transformaciones a la vez saturan la VM.
  const LOTE = 8;
  let hechos = 0;
  for (let i = 0; i < trabajos.length; i += LOTE) {
    await Promise.all(
      trabajos.slice(i, i + LOTE).map(async ({ ruta, loader }) => {
        const fuente = await readFile(ruta, 'utf8');
        const opciones = loader === 'js' ? { loader, format: 'esm', minify: true } : { loader, minify: true };
        const { code } = await transform(fuente, opciones);
        await writeFile(ruta, code);
        hechos += 1;
      }),
    );
  }
  console.log(`OPS-06: ${hechos} archivos minificados en ${web}`);
}

const salida = argumento('--salida');
let web = WEB;
if (salida) {
  await mkdir(dirname(salida), { recursive: true });
  await cp(WEB, salida, { recursive: true });
  web = salida;
}
await minificar(web);
