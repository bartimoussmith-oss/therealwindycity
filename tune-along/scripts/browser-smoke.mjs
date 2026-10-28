/**
 * Real-browser smoke test (headless Chrome) of the whole learn → recognise loop.
 *
 * Not part of `npm test` (it needs a browser and takes ~2.5 minutes because the demo
 * song plays in real time). To run it:
 *   npm run build && npx vite preview --port 4173 &
 *   WRITE_DEMO_WAV=/tmp/demo.wav DEMO_WAV_DEGRADE=1 npx vitest run test/tools.test.ts
 *   npm i --no-save puppeteer-core @sparticuz/chromium     # or set CHROME=/path/to/chrome
 *   node scripts/browser-smoke.mjs
 * (In minimal Linux containers the bundled Chromium may need its libraries on
 *  LD_LIBRARY_PATH — see README.)
 *
 * Phase A: demo song first play (learn) → second play (must be recognised).
 * Phase B: microphone path — Chrome's fake microphone plays a degraded WAV of the
 *          same song (echo, low-pass, hiss); it must be recognised.
 * Phase C: the pop-out overlay (Document Picture-in-Picture) must render.
 * Exits non-zero if any phase fails or the page logs errors.
 */
import puppeteer from 'puppeteer-core';
import { mkdirSync, rmSync } from 'node:fs';

const BASE = process.env.BASE ?? 'http://127.0.0.1:4173/';
const OUT = process.env.OUT ?? 'test-output/browser';
const WAV = process.env.FAKE_MIC_WAV ?? '/tmp/demo.wav';
const profile = `${OUT}/profile`;
mkdirSync(OUT, { recursive: true });
rmSync(profile, { recursive: true, force: true });

let executablePath = process.env.CHROME;
let extraArgs = [];
if (!executablePath) {
  const chromium = (await import('@sparticuz/chromium')).default;
  executablePath = await chromium.executablePath();
  extraArgs = chromium.args.filter((a) => !a.startsWith('--single-process') && !a.startsWith('--use-gl'));
}

const t0 = Date.now();
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s]`, ...a);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok, detail }); log(ok ? 'PASS' : 'FAIL', name, detail); };

const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  userDataDir: profile,
  args: [
    ...extraArgs,
    '--autoplay-policy=no-user-gesture-required',
    '--use-fake-ui-for-media-stream',
    '--use-fake-device-for-media-stream',
    `--use-file-for-fake-audio-capture=${WAV}`,
  ],
});
const page = await browser.newPage();
const problems = [];
page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) problems.push(`${m.type()}: ${m.text()}`); });
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
await page.setViewport({ width: 1280, height: 900 });

async function clickText(sel, text) {
  const ok = await page.evaluate((sel, text) => {
    const el = [...document.querySelectorAll(sel)].find((e) => e.textContent.includes(text) && !e.disabled);
    if (el) { el.click(); return true; }
    return false;
  }, sel, text);
  if (!ok) throw new Error(`no ${sel} containing "${text}"`);
}
async function waitText(text, timeout) {
  const start = Date.now();
  await page.waitForFunction((t) => document.body.innerText.includes(t), { timeout, polling: 250 }, text);
  return (Date.now() - start) / 1000;
}
const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });

try {
  // ---- Phase A
  await page.goto(BASE + '#/listen', { waitUntil: 'networkidle0' });
  await shot('01-start');
  await clickText('button', 'Windy City Shuffle');
  await waitText('Learning a new song', 15000);
  await sleep(24000);
  const learningText = await page.evaluate(() => document.body.innerText);
  check('live tuning estimate during first listen', /Eb Standard/.test(learningText) && /A = 43[5-7]\.\d Hz/.test(learningText), learningText.match(/A = [\d.]+ Hz/)?.[0] ?? '');
  await shot('02-learning');
  await waitText('Play it again', 160000);
  check('song learned and saved after it ended', true);
  await clickText('button', 'Play it again');
  const recog = await waitText('Playing along', 30000);
  check('demo recognised on second play', recog < 10, `${recog.toFixed(1)} s`);
  await sleep(Math.max(1000, 14000 - recog * 1000));
  await shot('03-recognised');
  await clickText('button', 'Shapes I play');
  await sleep(1500);
  const shapesText = await page.evaluate(() => document.querySelector('.now-next')?.innerText ?? '');
  check('shapes mode shows E-family shapes for Eb tuning', /sounds (Eb|Ab|Bb|Cm)/.test(shapesText), shapesText.replace(/\n/g, ' '));
  await shot('04-shapes-mode');
  await clickText('button', 'Sounding names');
  await clickText('button', 'Stop');
  await waitText('Hear it once', 15000);
  await page.goto(BASE + '#/songs', { waitUntil: 'networkidle0' });
  await sleep(500);
  await clickText('button.song-row', 'Windy City Shuffle');
  await sleep(800);
  const songText = await page.evaluate(() => document.body.innerText);
  check('song page has chords over words', songText.includes('Wind comes off the lake at dawn') && songText.includes('Heard 2×'));
  await shot('05-song');
  await page.emulateMediaType('print');
  await page.pdf({ path: `${OUT}/06-chord-sheet.pdf`, format: 'Letter' });
  await page.emulateMediaType('screen');

  // ---- Phase B + C
  await page.goto(BASE + '#/listen', { waitUntil: 'networkidle0' });
  await sleep(500);
  await clickText('button.listen-btn', 'Listen');
  const micT = await waitText('Playing along', 45000).catch(() => -1);
  check('microphone path recognised (degraded fake mic)', micT > 0, micT > 0 ? `${micT.toFixed(1)} s` : 'timeout');
  await sleep(6000);
  await shot('07-mic-recognised');
  await clickText('button', 'Pop out');
  await sleep(2500);
  const pipText = await page.evaluate(() => window.documentPictureInPicture?.window?.document.body.innerText ?? null);
  check('pop-out overlay renders chords', !!pipText && /Windy City Shuffle/.test(pipText), pipText ? pipText.replace(/\n/g, ' | ') : 'no window');
  await clickText('button', 'Stop').catch(() => undefined);
  await sleep(1500);
} catch (err) {
  check('run completed', false, String(err));
  await shot('zz-failure').catch(() => undefined);
}
check('no console errors or warnings', problems.length === 0, problems.slice(0, 5).join(' / '));
await browser.close();
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
