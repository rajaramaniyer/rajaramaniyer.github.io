// Real Chromium audio checks, using its built-in DevTools pipe (no packages).
// CHROME_PATH=/path/to/chromium node tests/webtambura.browser.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const { spawn } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');
const root = path.resolve(__dirname, '..');
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'tambura-chrome-'));
const chromePath = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
let chrome, server;
let sequence = 0, received = '', sessionId;
const pending = new Map();
function call(method, params = {}, session = sessionId) {
    return new Promise((resolve, reject) => {
        const id = ++sequence;
        const timeout = setTimeout(() => { pending.delete(id); reject(new Error('Timed out: ' + method)); }, 15000);
        pending.set(id, { resolve, reject, timeout });
        chrome.stdio[3].write(JSON.stringify({ id, method, params, sessionId: session }) + '\0');
    });
}
async function evaluate(expression) {
    const result = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, userGesture: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
}
const click = () => evaluate("document.getElementById('PlayStop').click()");
async function audible() {
    const result = await evaluate(`(async () => {
        for (let i = 0; i < 100; i++) {
            if (context && context.state === 'running' && activeSourceNodes.length) {
                var analyser = context.createAnalyser();
                gainNode.connect(analyser);
                await new Promise(resolve => setTimeout(resolve, 50));
                var data = new Float32Array(analyser.fftSize);
                analyser.getFloatTimeDomainData(data);
                gainNode.disconnect(analyser);
                analyser.disconnect();
                var rms = Math.sqrt(data.reduce((sum, x) => sum + x*x, 0) / data.length);
                if (rms > 0.00001) return { state: context.state, rms, sources: activeSourceNodes.length };
            }
            await new Promise(resolve => setTimeout(resolve, 50));
        }
        throw new Error('No measurable audio output');
    })()`);
    assert.equal(result.state, 'running'); assert.ok(result.rms > 0.00001);
    return result;
}
async function stopped() {
    assert.deepEqual(await evaluate("({sources: activeSourceNodes.length, timer: loopScheduleTimer, button: document.getElementById('PlayStop').innerText})"),
        { sources: 0, timer: null, button: 'Play' });
}
(async () => {
    server = http.createServer((req, res) => {
        const file = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname);
        if (!file.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
        fs.readFile(file, (err, data) => {
            if (err) { res.writeHead(404).end(); return; }
            res.setHeader('Content-Type', file.endsWith('.wav') ? 'audio/wav' : 'text/html');
            res.end(data);
        });
    });
    await new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(0, '127.0.0.1', resolve);
    });
    chrome = spawn(chromePath, ['--headless=new', '--remote-debugging-pipe', '--no-first-run',
        '--no-default-browser-check', '--disable-background-networking', '--disable-extensions',
        '--user-data-dir=' + profile, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'] });
    chrome.on('error', error => { console.error(error); process.exitCode = 1; });
    chrome.stdio[4].on('data', chunk => {
        received += chunk.toString();
        let end;
        while ((end = received.indexOf('\0')) >= 0) {
            const message = JSON.parse(received.slice(0, end)); received = received.slice(end + 1);
            const request = pending.get(message.id);
            if (request) {
                clearTimeout(request.timeout); pending.delete(message.id);
                if (message.error) request.reject(new Error(JSON.stringify(message.error)));
                else request.resolve(message.result);
            }
        }
    });
    const target = await call('Target.createTarget', { url: 'about:blank' });
    sessionId = (await call('Target.attachToTarget', { targetId: target.targetId, flatten: true })).sessionId;
    await call('Network.enable');
    // Isolate the audio checks from ads and third-party stylesheet availability.
    await call('Network.setBlockedURLs', { urls: ['*googlesyndication.com*', '*w3schools.com*', '*doubleclick.net*'] });
    await call('Page.enable');
    await call('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/webtambura.html` });
    for (let i = 0; i < 100 && !await evaluate("typeof onClickPlay === 'function'"); i++) await delay(50);
    await click(); console.log('Initial audio:', await audible());
    await click(); await stopped(); await click(); await audible();
    console.log('PASS immediate restart');
    await click(); await evaluate('context.suspend()'); await click(); await audible();
    console.log('PASS suspended context restart');
    await click(); await evaluate('context.close()'); await click(); await audible();
    console.log('PASS closed context recreation');
    await click(); await stopped();
    const other = await call('Target.createTarget', { url: 'about:blank' });
    await call('Target.activateTarget', { targetId: other.targetId });
    await delay(1000);
    assert.equal(await evaluate('document.visibilityState'), 'hidden');
    await call('Target.activateTarget', { targetId: target.targetId });
    await click(); await audible();
    await call('Target.closeTarget', { targetId: other.targetId });
    console.log('PASS restart after switching tabs (page confirmed hidden)');
    for (const madhyam of [false, true]) {
        for (const pitch of ['b','c','cs','d','ds','e','f','fs','g','gs','a','as']) {
            await evaluate(`document.querySelector('input[name="pitch"][value="${pitch}"]').checked = true;
                document.getElementById('madhyam').checked = ${madhyam}; changePitch();`);
            await audible();
        }
    }
    console.log('PASS measurable output for all 24 pitch/madhyam samples, including A#');
    await click();
    for (let i = 0; i < 30; i++) { await click(); await audible(); await click(); await stopped(); }
    console.log('PASS 30 restart cycles');
    await evaluate("for (let i = 0; i < 20; i++) { onClickPlay(); onClickPlay(); }");
    await delay(100); await stopped();
    console.log('PASS rapid Play/Stop');
    await evaluate("document.getElementById('myRange').value = 15; onGainChange()");
    await click(); await audible();
    assert.equal(await evaluate('gainNode.gain.value'), Math.fround(0.15));
    await evaluate("document.getElementById('myRange').value = 70; onGainChange()");
    await audible();
    assert.equal(await evaluate('gainNode.gain.value'), Math.fround(0.7));
    console.log('PASS volume before and during playback');
    await delay(20000); await audible();
    console.log('PASS continuous playback across loop boundaries');
    await click(); await stopped();
    const idleMs = Number(process.env.IDLE_MS || 180000);
    console.log(`Waiting ${idleMs / 1000}s stopped before restart...`);
    await delay(idleMs); await click(); console.log('PASS idle restart:', await audible());
    await click(); await stopped();
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
    if (chrome) {
        const exited = new Promise(resolve => chrome.once('exit', resolve));
        chrome.kill(); await exited;
    }
    if (server) await new Promise(resolve => server.close(resolve));
    fs.rmSync(profile, { recursive: true, force: true });
});
