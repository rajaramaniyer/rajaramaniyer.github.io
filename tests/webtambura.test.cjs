const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Run the actual page script with controllable Web Audio and network lifecycles.
function setup() {
    const elements = {
        PlayStop: { innerText: 'Play', focus() {} },
        myRange: { value: 30 }, volumeLevel: {}, madhyam: { checked: false }
    };
    const pitch = { value: 'c' };
    const requests = [], contexts = [], timers = new Map(), alerts = [];
    let timerId = 0;
    class AudioContext {
        constructor() {
            this.state = 'running'; this.sampleRate = 44100; this.currentTime = 0;
            this.destination = {}; this.sources = []; this.decodes = []; this.resumeCalls = 0;
            contexts.push(this);
        }
        createGain() {
            return { gain: { value: 0 }, connections: 0, connect() { this.connections++; } };
        }
        createBufferSource() {
            const node = {
                connect() {}, disconnect() {},
                start(time) { assert.equal(this.started, undefined); this.started = time; },
                stop() { this.stopped = true; }
            };
            this.sources.push(node); return node;
        }
        resume() {
            this.resumeCalls++;
            if (this.resumeError) return Promise.reject(this.resumeError);
            this.state = 'running'; return Promise.resolve();
        }
        decodeAudioData(data, success, failure) { this.decodes.push({ success, failure }); }
    }
    class XMLHttpRequest {
        constructor() { requests.push(this); this.handlers = {}; }
        open(method, url) { this.url = url; }
        addEventListener(name, callback) { this.handlers[name] = callback; }
        send() {}
        respond(status = 200) {
            this.status = status; this.response = new ArrayBuffer(16);
            this.handlers.load();
        }
        fail(name) { this.handlers[name](); }
    }
    const sandbox = {
        AudioContext, XMLHttpRequest, console: { log() {}, warn() {}, error() {} },
        document: { getElementById: id => elements[id], querySelector: () => pitch },
        setTimeout: callback => { timers.set(++timerId, callback); return timerId; },
        clearTimeout: id => timers.delete(id), alert: message => alerts.push(message)
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    const html = fs.readFileSync(require('node:path').join(__dirname, '../webtambura.html'), 'utf8');
    vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], sandbox);
    const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };
    const decode = async (index = requests.length - 1, buffer = { duration: 9 }) => {
        requests[index].respond();
        contexts.at(-1).decodes.at(-1).success(buffer);
        await flush();
    };
    return { app: sandbox, elements, pitch, requests, contexts, timers, alerts, flush, decode };
}

test('Play resumes a suspended context and starts fresh sources on restart', async () => {
    const s = setup();
    s.app.onClickPlay(); await s.decode();
    const context = s.contexts[0], first = context.sources[0];
    s.app.onClickPlay();
    assert.equal(first.stopped, true);
    context.state = 'suspended';
    s.app.onClickPlay();
    if (s.requests.length > 1) await s.decode();
    await s.flush();
    assert.equal(context.state, 'running');
    assert.ok(context.resumeCalls > 0);
    assert.notEqual(context.sources.at(-1), first);
    assert.equal(s.elements.PlayStop.innerText, 'Stop');
});

test('Stop during loading or decoding prevents delayed playback', async () => {
    for (const stage of ['loading', 'decoding']) {
        const s = setup(); s.app.onClickPlay();
        if (stage === 'decoding') s.requests[0].respond();
        s.app.onClickPlay();
        if (stage === 'loading') s.requests[0].respond();
        if (s.contexts[0].decodes.length) s.contexts[0].decodes[0].success({ duration: 9 });
        await s.flush();
        assert.equal(s.contexts[0].sources.length, 0, stage);
        assert.equal(s.timers.size, 0);
        assert.equal(s.elements.PlayStop.innerText, 'Play');
    }
});

test('an older pitch decode cannot replace a later session', async () => {
    const s = setup(); s.app.onClickPlay(); s.requests[0].respond();
    s.pitch.value = 'as'; s.app.changePitch();
    await s.decode(1, { duration: 8, pitch: 'as' });
    s.contexts[0].decodes[0].success({ duration: 9, pitch: 'c' }); await s.flush();
    assert.equal(s.app.audioBuffer.pitch, 'as');
    assert.equal(s.contexts[0].sources.length, 1);
});

test('closed contexts are recreated with their own gain and sample cache', async () => {
    const s = setup(); s.app.onClickPlay(); await s.decode();
    s.app.onClickPlay(); s.contexts[0].state = 'closed';
    s.app.onClickPlay(); await s.decode();
    assert.equal(s.contexts.length, 2);
    assert.equal(s.contexts[1].sources.length, 1);
    assert.equal(s.app.gainNode.connections, 1);
});

test('cached samples, volume, and many rapid restarts keep one active loop', async () => {
    const s = setup(); s.app.onClickPlay(); await s.decode();
    for (let i = 0; i < 50; i++) {
        s.app.onClickPlay();
        assert.equal(s.timers.size, 0);
        s.elements.myRange.value = i + 1; s.app.onGainChange();
        s.app.onClickPlay(); await s.flush();
        assert.equal(s.timers.size, 1);
        assert.equal(s.app.gainNode.gain.value, (i + 1) / 100);
    }
    assert.equal(s.requests.length, 1);
    assert.equal(s.app.gainNode.connections, 1);
    assert.equal(s.contexts[0].sources.filter(node => !node.stopped).length, 1);
});

test('HTTP, network, timeout, decode and resume failures allow retry', async () => {
    for (const failure of ['http', 'error', 'timeout', 'decode', 'resume']) {
        const s = setup();
        if (failure === 'resume') {
            s.app.context = new s.app.AudioContext();
            s.app.context.state = 'suspended';
            s.app.context.resumeError = new Error('resume failed');
        }
        s.app.onClickPlay();
        if (failure === 'http') s.requests[0].respond(404);
        else if (failure === 'error' || failure === 'timeout') s.requests[0].fail(failure);
        else {
            s.requests[0].respond();
            const decode = s.contexts[0].decodes[0];
            if (failure === 'decode') decode.failure(new Error('bad audio'));
            else decode.success({ duration: 9 });
        }
        await s.flush();
        assert.equal(s.elements.PlayStop.innerText, 'Play', failure);
        assert.equal(s.timers.size, 0, failure);
        assert.equal(s.alerts.length, 1, failure);
        // Use a fresh context on retry for the injected resume failure.
        if (failure === 'resume') s.app.context.state = 'closed';
        s.app.onClickPlay(); await s.decode();
        assert.equal(s.elements.PlayStop.innerText, 'Stop', failure);
        assert.equal(s.contexts.at(-1).sources.length, 1, failure);
    }
});

test('a stale failure cannot stop a newer successful session', async () => {
    const s = setup(); s.app.onClickPlay();
    s.app.onClickPlay(); s.app.onClickPlay(); await s.decode(1);
    s.requests[0].fail('error'); await s.flush();
    assert.equal(s.elements.PlayStop.innerText, 'Stop');
    assert.equal(s.alerts.length, 0);
    assert.equal(s.timers.size, 1);
});

test('Stop while resume is pending prevents playback after it resolves', async () => {
    const s = setup(); s.app.onClickPlay(); await s.decode(); s.app.onClickPlay();
    const context = s.contexts[0]; context.state = 'suspended';
    let finishResume;
    context.resume = () => new Promise(resolve => { finishResume = resolve; });
    s.app.onClickPlay(); s.app.onClickPlay();
    context.state = 'running'; finishResume(); await s.flush();
    assert.equal(context.sources.length, 1);
    assert.equal(s.timers.size, 0);
    assert.equal(s.elements.PlayStop.innerText, 'Play');
});
