// Read-only browser acceptance: never place an order or change operator state.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const base = process.argv[2] || 'http://127.0.0.1:8173/';
  const output = process.argv[3] || 'logs/browser-local.json';
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const errors = [];
  const responses = [];
  try {
    const context = await browser.newContext({
      httpCredentials: process.env.OPZ_HTTP_USER ? {
        username: process.env.OPZ_HTTP_USER, password: process.env.OPZ_HTTP_PASSWORD || '',
      } : undefined,
    });
    await context.route('**/*', route => {
      if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
        errors.push(`Blocked write: ${route.request().method()} ${new URL(route.request().url()).pathname}`);
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('requestfailed', request => {
      const url = new URL(request.url());
      if (url.origin === new URL(base).origin) errors.push(`Request failed: ${url.pathname} ${request.failure()?.errorText || ''}`);
    });
    page.on('response', response => {
      const url = new URL(response.url());
      if (url.origin === new URL(base).origin) responses.push({ path: url.pathname + url.search, status: response.status() });
    });
    await page.goto(base, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.locator('#root').waitFor();
    await page.waitForTimeout(15000);
    const desktop = await page.locator('body').innerText();
    if (!desktop.includes('WAR ROOM')) errors.push('Missing WAR ROOM after load');
    const prefix = new URL(base).pathname.replace(/\/$/, '');
    const health = await context.request.get(`${new URL(base).origin}${prefix}/health`);
    if (health.status() !== 200 || (await health.json()).status !== 'ok') errors.push('Health is not JSON status=ok');
    const api = await context.request.get(`${new URL(base).origin}${prefix}/opz/last_actions?limit=8`);
    if (api.status() !== 200 || !(api.headers()['content-type'] || '').includes('application/json')) errors.push('API is not JSON 200');
    fs.mkdirSync(path.dirname(output), { recursive: true });
    await page.screenshot({ path: output.replace(/\.json$/, '-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: output.replace(/\.json$/, '-mobile.png'), fullPage: true });
    const bad = responses.filter(item => item.status >= 400);
    const report = { base, timestamp: new Date().toISOString(), errors, bad, responses, text: desktop.slice(0, 12000) };
    fs.writeFileSync(output, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ base, errors, bad, requests: responses.length, report: output }));
    if (errors.length || bad.length) process.exitCode = 1;
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
