// 静态服务 + Chrome CDP 2x 整页截图。用法：node shoot.mjs <root> <outDir> <name:file:height> ...
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const [root, outDir, ...jobs] = process.argv.slice(2);
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json' };

const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (!p.startsWith(path.resolve(root)) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream' });
  fs.createReadStream(p).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const port = server.address().port;

const prof = fs.mkdtempSync(path.join(path.dirname(outDir), 'chrome-prof-'));
const chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + prof, '--hide-scrollbars', '--no-first-run', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const wsUrl = await new Promise((resolve, reject) => {
  let buf = '';
  chrome.stderr.on('data', (d) => { buf += d; const m = buf.match(/ws:\/\/[^\s]+/); if (m) resolve(m[0]); });
  setTimeout(() => reject(new Error('chrome did not start')), 20000);
});

const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === 'Runtime.exceptionThrown') console.log('  EXC', JSON.stringify(m.params.exceptionDetails).slice(0, 600));
  if (m.method === 'Runtime.consoleAPICalled' && /error|warn/.test(m.params.type)) console.log('  CONSOLE', m.params.type, m.params.args.map((a) => a.value || a.description).join(' ').slice(0, 600));
});
const send = (method, params = {}, sessionId) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params, sessionId })); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

fs.mkdirSync(outDir, { recursive: true });
for (const job of jobs) {
  const [name, file, h] = job.split(':');
  const { result: { targetId } } = await send('Target.createTarget', { url: 'about:blank' });
  const { result: { sessionId } } = await send('Target.attachToTarget', { targetId, flatten: true });
  await send('Page.enable', {}, sessionId);
  await send('Runtime.enable', {}, sessionId);
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: Number(h), deviceScaleFactor: 2, mobile: false }, sessionId);
  await send('Page.navigate', { url: `http://127.0.0.1:${port}/project/${file}` }, sessionId);
  await sleep(6000);
  const ev = await send('Runtime.evaluate', { expression: 'JSON.stringify({h: document.documentElement.scrollHeight, t: document.body.innerText.length, err: (document.body.innerText.match(/error|错误|Error/g)||[]).length})', returnByValue: true }, sessionId);
  const info = JSON.parse(ev.result.result.value);
  const height = Math.max(Number(h), info.h);
  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: 0, width: 1440, height, scale: 1 } }, sessionId);
  fs.writeFileSync(path.join(outDir, name + '.png'), Buffer.from(shot.result.data, 'base64'));
  console.log(name, 'css', 1440 + 'x' + height, 'textLen', info.t, 'errWords', info.err);
  await send('Target.closeTarget', { targetId });
}
ws.close(); chrome.kill(); server.close();
