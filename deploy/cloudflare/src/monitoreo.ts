// Disparo del workflow «Monitoreo de ingesta» desde el Cron Trigger del Worker.
// GitHub Actions retrasa los cron programados (en producción corría ~4 veces al día), así que el
// Worker abre una corrida workflow_dispatch cada 15 minutos; la sonda y el issue siguen en Actions.
const GITHUB_REPO = 'falopass/brasas';
const WORKFLOW = 'monitoreo.yml';
const API_VERSION = '2022-11-28';

export const INGEST_CRON = '*/10 * * * *';
export const MONITORING_CRON = '*/15 * * * *';

export async function dispatchMonitoring(env: { GITHUB_MONITOR_TOKEN?: string }, fetchImpl: typeof fetch = fetch): Promise<void> {
  const token = env.GITHUB_MONITOR_TOKEN;
  if (!token) throw new Error('Falta el secreto GITHUB_MONITOR_TOKEN en el Worker.');
  const response = await fetchImpl(`https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': API_VERSION,
      'User-Agent': 'brasa-chile-monitoreo',
    },
    body: JSON.stringify({ ref: 'main' }),
  });
  if (response.status !== 204) {
    const detail = await response.text().catch(() => '');
    throw new Error(`GitHub respondió HTTP ${response.status} al disparar ${WORKFLOW}: ${detail.slice(0, 200)}`);
  }
}
