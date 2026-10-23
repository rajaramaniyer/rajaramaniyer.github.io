# Web Tambura restart checks

No packages or build step are required. Node.js 22 or newer runs the tests.

```sh
node --test tests/webtambura.test.cjs
node tests/webtambura.browser.cjs
```

The browser check uses an installed Google Chrome on macOS by default. On Linux,
set `CHROME_PATH` to the Chromium executable, for example:

```sh
CHROME_PATH=/usr/bin/chromium node tests/webtambura.browser.cjs
```

It starts a temporary localhost server and headless browser with a disposable
profile, then removes the profile on exit. Third-party ads and the stylesheet
are blocked to isolate audio testing. The default stopped interval is three
minutes; `IDLE_MS` can override it. This check measures nonzero waveform output
with a Web Audio analyser, rather than relying only on button text or sources.
It does not verify physical speakers, musical pitch by listening, or Safari.

## Findings and scope

The original `onClickPlay()` never resumes its existing AudioContext. In an
isolated Chromium run of the original page, explicitly suspending the context
after Stop reproduced a silent restart: the button said Stop and a source was
scheduled, but the context stayed suspended. This confirms a failure mechanism;
it does not establish what originally caused the reported context interruption
or prove that natural idle suspension is the only cause.

The original sample-loading and decoding callbacks also start playback after
Stop, or replace the selected pitch with an older request's result. Three
regression tests reproduced these failures on the original script.

The fix resumes within the Play gesture, recreates closed contexts, and uses a
session counter to ignore obsolete asynchronous results. Decoded samples are
cached per context. Loading, decoding and resume errors restore the Play button
and show a retry message. Gain connects to the destination once per context.
The existing loop scheduler, controls, sample rate, pitch choices, and WAV files
are unchanged.

## Automated coverage

The unit tests execute the actual inline page script with controlled audio,
network and timer lifecycles. They cover suspension, closed contexts, stale
loads/decodes, delayed resume, failed HTTP/network/timeout/decode/resume, retry,
caching, volume and 50 restart cycles.

The Chromium check covers initial playback, immediate restart, forced suspension
and closure, switching tabs with confirmed page hiding, all 24 pitch/Madhyam combinations including A-sharp, 30 restart
cycles, rapid interactions, volume, continuous playback across loop boundaries,
and restart after three minutes stopped. Every playback check requires a running
context and nonzero measured audio output.

## Manual checks still required

Run the page on localhost in Safari and Chromium on the intended machines:

```sh
python3 -m http.server 8000
```

Open <http://localhost:8000/webtambura.html> and listen through the normal audio
output. Verify immediate restart, restart after several minutes stopped,
restart after switching browser tabs, and restart after switching applications.
Repeat rapid Play/Stop, change pitch and Madhyam, and adjust volume before and
after stopping. Listen for correct pitch and unchanged sound across loop
boundaries. Confirm Stop silences output and an error allows a later retry.

To exercise suspension deterministically, press Stop, run `context.suspend()`
in browser developer tools, then press Play. The context should return to
`running` and sound should restart. Repeat with `context.close()`; Play should
create a new context.

Offline support is a separate, pending change; blocking third-party resources
in the audio test does not establish a complete offline installation workflow.
