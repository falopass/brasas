/* Punto de entrada para `node --test tests/js/`: Node trata los argumentos de --test como globs
 * y «tests/js» coincide con el propio directorio, que se ejecuta como script; sin este index.js
 * falla con MODULE_NOT_FOUND. Importar aquí cada suite *.test.mjs nueva. */
import './util.test.mjs';
import './data.test.mjs';
import './api.test.mjs';
import './satelite.test.mjs';
import './reportes.test.mjs';
import './preparate.test.mjs';
import './zona.test.mjs';
import './alertas.test.mjs';
import './charts.test.mjs';
import './capas.test.mjs';
import './trendview.test.mjs';
