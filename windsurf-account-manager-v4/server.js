const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = __dirname;
const PORT = 17321;
const PROFILES_DIR = path.join(ROOT, 'browser-profiles');
fs.mkdirSync(PROFILES_DIR, { recursive: true });

function send(res, code, body, type = 'text/plain; charset=utf-8') {
  res.writeHead(code, { 'Content-Type': type, 'Access-Control-Allow-Origin': '*' });
  res.end(body);
}
function safeName(s) {
  return String(s || 'default').toLowerCase().replace(/[^a-z0-9._-]+/g, '_').slice(0, 80) || 'default';
}
function findBrowser() {
  const candidates = [
    process.env.CHROME_PATH,
    process.env.EDGE_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ].filter(Boolean);
  for (const c of candidates) if (fs.existsSync(c)) return c;
  return null;
}
function openProfile({ email, nickname, tool, url }) {
  const browser = findBrowser();
  if (!browser) throw new Error('未找到 Chrome/Edge。可设置 CHROME_PATH 或 EDGE_PATH 环境变量。');
  const profile = path.join(PROFILES_DIR, safeName(email || nickname || tool));
  fs.mkdirSync(profile, { recursive: true });
  const target = url || 'https://windsurf.com/profile';
  const args = [
    `--user-data-dir=${profile}`,
    '--no-first-run',
    '--new-window',
    target,
  ];
  const child = spawn(browser, args, { detached: true, stdio: 'ignore' });
  child.unref();
  return { browser, profile, url: target };
}
function mime(file) {
  if (file.endsWith('.html')) return 'text/html; charset=utf-8';
  if (file.endsWith('.js')) return 'application/javascript; charset=utf-8';
  if (file.endsWith('.css')) return 'text/css; charset=utf-8';
  if (file.endsWith('.json')) return 'application/json; charset=utf-8';
  return 'application/octet-stream';
}
const server = http.createServer((req, res) => {
  if (req.method === 'OPTIONS') return send(res, 204, '');
  if (req.method === 'POST' && req.url === '/api/open-profile') {
    let raw = '';
    req.on('data', c => raw += c);
    req.on('end', () => {
      try {
        const result = openProfile(JSON.parse(raw || '{}'));
        send(res, 200, JSON.stringify({ ok: true, ...result }), 'application/json; charset=utf-8');
      } catch (e) {
        send(res, 500, JSON.stringify({ ok: false, error: e.message }), 'application/json; charset=utf-8');
      }
    });
    return;
  }
  let file = req.url.split('?')[0];
  if (file === '/') file = '/index.html';
  const fp = path.normalize(path.join(ROOT, file));
  if (!fp.startsWith(ROOT)) return send(res, 403, 'Forbidden');
  fs.readFile(fp, (err, data) => {
    if (err) return send(res, 404, 'Not found');
    send(res, 200, data, mime(fp));
  });
});
server.listen(PORT, '127.0.0.1', () => {
  const url = `http://127.0.0.1:${PORT}/`;
  console.log(`AI Account Dashboard running: ${url}`);
  const browser = findBrowser();
  if (browser) {
    const child = spawn(browser, ['--new-window', url], { detached: true, stdio: 'ignore' });
    child.unref();
  } else {
    console.log('未找到 Chrome/Edge，请手动打开：' + url);
  }
});
