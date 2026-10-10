#!/usr/bin/env node
// Renders src/index.html frame by frame with Playwright/Chromium and pipes
// the PNG frames into ffmpeg to produce a silent H.264 video.
//
//   node scripts/render.mjs --out build/video_noaudio.mp4 --timeline build/timeline.json
//   node scripts/render.mjs --frame 12.5 --png build/f12.png     (single frame)
//   node scripts/render.mjs --frames 0,5,10 --pngdir build/check  (several stills)
//
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const requireGlobal = createRequire('/opt/node22/lib/node_modules/_.js');
let chromium;
try { ({ chromium } = requireGlobal('playwright')); }
catch { ({ chromium } = await import('playwright')); }

const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf('--' + name); return i >= 0 ? argv[i + 1] : def; };
const has = name => argv.includes('--' + name);

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const htmlPath = path.join(root, 'src', 'index.html');
const fps = Number(opt('fps', 30));
const out = opt('out', path.join(root, 'build', 'video_noaudio.mp4'));
const timelinePath = opt('timeline', path.join(root, 'build', 'timeline.json'));
const crf = opt('crf', '19');
const W = 1080, H = 1920;

const browser = await chromium.launch({ args: ['--font-render-hinting=none'] });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
page.on('pageerror', e => { console.error('page error:', e.message); });
await page.goto('file://' + htmlPath);
await page.evaluate(() => window.ready);
const timeline = await page.evaluate(() => window.TIMELINE);
fs.mkdirSync(path.dirname(timelinePath), { recursive: true });
fs.writeFileSync(timelinePath, JSON.stringify(timeline, null, 1));
const duration = Number(opt('duration', timeline.duration));

async function shot(t) {
  await page.evaluate(t => window.render(t), t);
  return page.screenshot({ type: 'png' });
}

if (has('frame') || has('frames')) {
  const times = has('frame') ? [Number(opt('frame'))] : opt('frames').split(',').map(Number);
  const dir = opt('pngdir', path.join(root, 'build', 'stills'));
  fs.mkdirSync(dir, { recursive: true });
  for (const t of times) {
    const buf = await shot(t);
    const file = has('frame') && has('png') ? opt('png') : path.join(dir, `t${t.toFixed(2).replace('.', '_')}.png`);
    fs.writeFileSync(file, buf);
    console.log('wrote', file);
  }
  await browser.close();
  process.exit(0);
}

fs.mkdirSync(path.dirname(out), { recursive: true });
const ff = spawn('ffmpeg', [
  '-y', '-loglevel', 'error',
  '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-',
  '-c:v', 'libx264', '-preset', 'medium', '-crf', crf, '-pix_fmt', 'yuv420p',
  '-movflags', '+faststart', out,
], { stdio: ['pipe', 'inherit', 'inherit'] });
const ffDone = new Promise((res, rej) => ff.on('close', code => code === 0 ? res() : rej(new Error('ffmpeg exit ' + code))));

const nFrames = Math.round(duration * fps);
const started = Date.now();
for (let i = 0; i < nFrames; i++) {
  const buf = await shot(i / fps);
  if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
  if (i % 150 === 0 || i === nFrames - 1) {
    const el = (Date.now() - started) / 1000;
    console.log(`frame ${i + 1}/${nFrames}  t=${(i / fps).toFixed(2)}s  elapsed ${el.toFixed(0)}s`);
  }
}
ff.stdin.end();
await ffDone;
await browser.close();
console.log('video written:', out);
