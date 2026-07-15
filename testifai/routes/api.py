import os
import re
import json
import base64

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from models import Legislator, ScriptRequest
from services import advocacy_service, legislators_service

router = APIRouter()

_DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def _load(name: str):
    with open(os.path.join(_DATA, name), "r") as f:
        return json.load(f)


# ── Reference data ───────────────────────────────────────────────────────────

@router.get("/states")
async def states():
    return _load("us_states.json")


@router.get("/applications")
async def applications():
    """The 100+ AI applications a script can be written about."""
    return _load("ai_applications.json")


@router.get("/goals")
async def goals():
    """The advocacy goals a script can pursue."""
    return _load("advocacy_goals.json")


@router.get("/blacklist")
async def blacklist():
    """The blackout list: AI-tell terms scrubbed from every generated script."""
    return _load("ai_blacklist.json")


# ── Legislators ──────────────────────────────────────────────────────────────

@router.get("/legislators", response_model=list[Legislator])
async def legislators(
    state: str = Query(..., description="Two-letter state abbreviation, e.g. CA"),
    chamber: str = Query("all", description="all | senate | house | federal | state"),
):
    try:
        return await legislators_service.get_legislators(state, chamber)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not load legislators: {e}")


# ── Script generation ────────────────────────────────────────────────────────

def _teleprompter_url(request: Request, title: str, script: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"title": title, "script": script}).encode("utf-8")
    ).decode("ascii")
    base = str(request.base_url).rstrip("/")
    return f"{base}/advocacy/teleprompter#data={payload}"


@router.post("/generate")
async def generate(request: Request, body: ScriptRequest):
    # Fail fast with a clear message if the server has no Claude key.
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        raise HTTPException(
            status_code=503,
            detail="The server is missing its ANTHROPIC_API_KEY. Add it to the backend environment to generate scripts.",
        )

    # Resolve reference selections.
    apps = {a["id"]: a for a in _load("ai_applications.json")}
    gls = {g["id"]: g for g in _load("advocacy_goals.json")}

    application = apps.get(body.application_id)
    if not application:
        raise HTTPException(status_code=400, detail=f"Unknown application_id: {body.application_id}")
    goal = gls.get(body.goal_id)
    if not goal:
        raise HTTPException(status_code=400, detail=f"Unknown goal_id: {body.goal_id}")

    try:
        legislator = await legislators_service.get_legislator(body.state, body.legislator_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not load legislator: {e}")
    if not legislator:
        raise HTTPException(status_code=404, detail="Legislator not found for that state")

    # Best-effort scrub of the speaker's public social presence.
    creator = await advocacy_service.gather_creator_context(body.socials.model_dump())

    try:
        result = await advocacy_service.generate_script(
            legislator=legislator,
            application=application,
            goal=goal,
            user=body.user.model_dump(),
            minutes=body.minutes,
            creator_block=creator["block"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Script generation failed: {e}")

    result["creator_summaries"] = creator["summaries"]
    result["teleprompter_url"] = _teleprompter_url(request, result["title"], result["script"])
    return result


@router.post("/download")
async def download(body: dict):
    """Return the script as a downloadable .txt file."""
    script = body.get("script", "")
    if not script:
        raise HTTPException(status_code=400, detail="script is required")
    title = body.get("title", "testifai-script")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "testifai-script"
    header = f"{title}\n{'=' * len(title)}\n\n" if body.get("include_title", True) else ""
    content = header + script + "\n"
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slug}.txt"'},
    )


# ── Teleprompter (self-contained page: colors + read-aloud) ──────────────────

@router.get("/teleprompter", response_class=HTMLResponse)
async def teleprompter():
    return _TELEPROMPTER_HTML


_TELEPROMPTER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>TESTIFAI Teleprompter</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  :root {
    --bg: #000000;
    --fg: #ffffff;
    --accent: #c9a84c;
    --font-size: 44px;
    --line-height: 1.6;
  }
  html, body { height: 100%; overflow: hidden; }
  body {
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    display: flex;
    flex-direction: column;
  }

  /* ── Top bar ── */
  #bar {
    flex: 0 0 auto;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    padding: 10px 12px;
    background: rgba(20,20,20,0.92);
    color: #eee;
    border-bottom: 1px solid #2a2a2a;
    font-size: 13px;
    backdrop-filter: blur(6px);
  }
  #bar.hidden { display: none; }
  .ctl { display: flex; align-items: center; gap: 6px; }
  .ctl label { color: #999; white-space: nowrap; }
  button {
    background: #2a2a2a; color: #eee; border: 1px solid #3a3a3a;
    border-radius: 8px; padding: 8px 14px; font-size: 13px; cursor: pointer;
    font-weight: 600;
  }
  button:hover { background: #333; }
  button.primary { background: var(--accent); color: #111; border-color: var(--accent); }
  button.active { background: var(--accent); color: #111; border-color: var(--accent); }
  input[type=range] { width: 96px; accent-color: var(--accent); }
  input[type=color] {
    width: 34px; height: 30px; border: 1px solid #3a3a3a; border-radius: 6px;
    background: none; cursor: pointer; padding: 0;
  }
  select {
    background: #2a2a2a; color: #eee; border: 1px solid #3a3a3a;
    border-radius: 6px; padding: 6px 8px; font-size: 13px; max-width: 160px;
  }
  .swatches { display: flex; gap: 5px; }
  .swatch { width: 22px; height: 22px; border-radius: 5px; border: 2px solid #444; cursor: pointer; }
  .swatch.sel { border-color: var(--accent); }

  /* ── Prompter viewport ── */
  #stage { flex: 1 1 auto; position: relative; overflow: hidden; }
  #scroller {
    position: absolute; top: 0; left: 0; right: 0;
    padding: 60vh 8vw 60vh;
    font-size: var(--font-size);
    line-height: var(--line-height);
    font-weight: 600;
    letter-spacing: 0.01em;
    white-space: pre-wrap;
    text-align: center;
    will-change: transform;
  }
  #scroller.mirror { transform: scaleX(-1); }
  #title { font-size: 0.55em; color: var(--accent); margin-bottom: 0.6em; font-weight: 700; }
  .reading { background: rgba(201,168,76,0.28); border-radius: 4px; }

  /* center guide line */
  #guide {
    position: absolute; left: 0; right: 0; top: 50%;
    height: 2px; background: linear-gradient(90deg, transparent, var(--accent), transparent);
    opacity: 0.35; pointer-events: none;
  }

  /* ── Bottom controls ── */
  #foot {
    flex: 0 0 auto;
    display: flex; gap: 8px; align-items: center; justify-content: center;
    padding: 12px; background: rgba(20,20,20,0.92);
    border-top: 1px solid #2a2a2a;
    flex-wrap: wrap;
  }
  #foot.hidden { display: none; }
  #hint {
    position: absolute; bottom: 8px; left: 0; right: 0; text-align: center;
    color: rgba(255,255,255,0.35); font-size: 12px; pointer-events: none;
  }

  /* paste screen */
  #paste {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    gap: 14px; padding: 32px; background: #0d0d0d; z-index: 5;
    align-items: center; justify-content: center;
  }
  #paste h1 { color: var(--accent); font-size: 22px; }
  #paste p { color: #999; font-size: 14px; max-width: 480px; text-align: center; }
  #paste textarea {
    width: min(640px, 100%); height: 220px; background: #161616; color: #eee;
    border: 1px solid #333; border-radius: 10px; padding: 14px; font-size: 15px;
    resize: vertical; font-family: inherit;
  }
</style>
</head>
<body>

<div id="bar">
  <button id="toggleScroll" class="primary">▶ Scroll</button>
  <button id="toggleRead">🔊 Read Aloud</button>
  <div class="ctl"><label>Speed</label><input id="speed" type="range" min="10" max="220" value="70"></div>
  <div class="ctl"><label>Size</label><input id="size" type="range" min="24" max="90" value="44"></div>
  <div class="ctl">
    <label>BG</label>
    <div class="swatches" id="bgSwatches"></div>
    <input id="bgColor" type="color" value="#000000">
  </div>
  <div class="ctl">
    <label>Text</label>
    <div class="swatches" id="fgSwatches"></div>
    <input id="fgColor" type="color" value="#ffffff">
  </div>
  <div class="ctl"><label>Voice</label><select id="voice"></select></div>
  <div class="ctl"><label>Rate</label><input id="rate" type="range" min="0.5" max="1.6" step="0.05" value="1"></div>
  <button id="mirror">🪞 Mirror</button>
  <button id="restart">⤴ Restart</button>
</div>

<div id="stage">
  <div id="guide"></div>
  <div id="scroller"><div id="title"></div><div id="body"></div></div>
  <div id="hint">Tap screen to hide/show controls</div>

  <div id="paste">
    <h1>TESTIFAI Teleprompter</h1>
    <p>No script loaded. Paste your script below, or open this page from the app with a generated script.</p>
    <textarea id="pasteText" placeholder="Paste your testimony script here..."></textarea>
    <button class="primary" id="loadPaste">Load Script</button>
  </div>
</div>

<div id="foot">
  <button id="toggleScroll2" class="primary">▶ Scroll</button>
  <button id="toggleRead2">🔊 Read Aloud</button>
  <button id="restart2">⤴ Restart</button>
</div>

<script>
(function () {
  var root = document.documentElement;
  var scroller = document.getElementById('scroller');
  var titleEl = document.getElementById('title');
  var bodyEl = document.getElementById('body');
  var stage = document.getElementById('stage');
  var paste = document.getElementById('paste');

  // ── Load script from URL (#data=base64 JSON, #script=encoded text, ?text=) ──
  function decodeData() {
    var hash = location.hash.replace(/^#/, '');
    var params = new URLSearchParams(hash);
    if (params.get('data')) {
      try {
        var b64 = params.get('data').replace(/-/g, '+').replace(/_/g, '/');
        var json = decodeURIComponent(escape(atob(b64)));
        return JSON.parse(json);
      } catch (e) {}
    }
    if (params.get('script')) {
      return { title: params.get('title') || '', script: decodeURIComponent(params.get('script')) };
    }
    var q = new URLSearchParams(location.search);
    if (q.get('text')) return { title: q.get('title') || '', script: q.get('text') };
    return null;
  }

  var words = [];   // {el, text} for read-along highlighting
  function renderScript(data) {
    titleEl.textContent = data.title || '';
    titleEl.style.display = data.title ? 'block' : 'none';
    bodyEl.innerHTML = '';
    words = [];
    // Split into word spans so we can highlight while reading.
    var tokens = (data.script || '').split(/(\s+)/);
    tokens.forEach(function (tok) {
      if (/^\s+$/.test(tok)) {
        bodyEl.appendChild(document.createTextNode(tok));
      } else if (tok.length) {
        var span = document.createElement('span');
        span.textContent = tok;
        bodyEl.appendChild(span);
        words.push(span);
      }
    });
    paste.style.display = 'none';
    currentScript = data.script || '';
  }

  var currentScript = '';
  var loaded = decodeData();
  if (loaded && loaded.script) renderScript(loaded);

  document.getElementById('loadPaste').addEventListener('click', function () {
    var txt = document.getElementById('pasteText').value.trim();
    if (txt) renderScript({ title: '', script: txt });
  });

  // ── Auto-scroll ──
  var pos = 0, scrolling = false, rafId = null, speed = 70;
  function step() {
    if (!scrolling) return;
    pos += speed / 60;
    var max = scroller.scrollHeight - stage.clientHeight * 0.5;
    if (pos > max) { pos = max; setScroll(false); }
    scroller.style.transform = (mirrored ? 'scaleX(-1) ' : '') + 'translateY(' + (-pos) + 'px)';
    rafId = requestAnimationFrame(step);
  }
  function setScroll(on) {
    scrolling = on;
    document.querySelectorAll('#toggleScroll, #toggleScroll2').forEach(function (b) {
      b.textContent = on ? '⏸ Pause' : '▶ Scroll';
      b.classList.toggle('active', on);
    });
    if (on) { cancelAnimationFrame(rafId); rafId = requestAnimationFrame(step); }
  }
  function applyTransform() {
    scroller.style.transform = (mirrored ? 'scaleX(-1) ' : '') + 'translateY(' + (-pos) + 'px)';
  }

  document.getElementById('speed').addEventListener('input', function (e) { speed = +e.target.value; });
  document.querySelectorAll('#toggleScroll, #toggleScroll2').forEach(function (b) {
    b.addEventListener('click', function () { setScroll(!scrolling); });
  });
  function restart() { pos = 0; applyTransform(); }
  document.getElementById('restart').addEventListener('click', restart);
  document.getElementById('restart2').addEventListener('click', restart);

  // ── Font size ──
  document.getElementById('size').addEventListener('input', function (e) {
    root.style.setProperty('--font-size', e.target.value + 'px');
  });

  // ── Colors ──
  var bgPresets = ['#000000', '#0d0d0d', '#101828', '#1b1b1b', '#ffffff', '#0b3d2e'];
  var fgPresets = ['#ffffff', '#c9a84c', '#ffd54a', '#7cf3a0', '#5db1ff', '#000000'];
  function buildSwatches(id, presets, cssVar, input) {
    var wrap = document.getElementById(id);
    presets.forEach(function (c) {
      var s = document.createElement('div');
      s.className = 'swatch';
      s.style.background = c;
      s.addEventListener('click', function () {
        root.style.setProperty(cssVar, c);
        input.value = c;
        wrap.querySelectorAll('.swatch').forEach(function (x) { x.classList.remove('sel'); });
        s.classList.add('sel');
      });
      wrap.appendChild(s);
    });
  }
  var bgColor = document.getElementById('bgColor');
  var fgColor = document.getElementById('fgColor');
  buildSwatches('bgSwatches', bgPresets, '--bg', bgColor);
  buildSwatches('fgSwatches', fgPresets, '--fg', fgColor);
  bgColor.addEventListener('input', function (e) { root.style.setProperty('--bg', e.target.value); });
  fgColor.addEventListener('input', function (e) { root.style.setProperty('--fg', e.target.value); });

  // ── Mirror ──
  var mirrored = false;
  document.getElementById('mirror').addEventListener('click', function () {
    mirrored = !mirrored;
    this.classList.toggle('active', mirrored);
    scroller.classList.toggle('mirror', mirrored);
    applyTransform();
  });

  // ── Read aloud (Web Speech API) ──
  var synth = window.speechSynthesis;
  var reading = false, utter = null;
  var voiceSel = document.getElementById('voice');
  var rateInput = document.getElementById('rate');

  function loadVoices() {
    if (!synth) return;
    var voices = synth.getVoices();
    voiceSel.innerHTML = '';
    voices.forEach(function (v, i) {
      var o = document.createElement('option');
      o.value = i;
      o.textContent = v.name + (v.lang ? ' (' + v.lang + ')' : '');
      if (v.default) o.selected = true;
      voiceSel.appendChild(o);
    });
  }
  if (synth) {
    loadVoices();
    synth.onvoiceschanged = loadVoices;
  }

  function clearHighlight() {
    words.forEach(function (w) { w.classList.remove('reading'); });
  }
  // Map utterance char index -> word span, to highlight & auto-scroll.
  function buildWordIndex() {
    var idx = [], cursor = 0;
    words.forEach(function (w) {
      var start = currentScript.indexOf(w.textContent, cursor);
      if (start >= 0) { idx.push({ start: start, el: w }); cursor = start + w.textContent.length; }
      else idx.push({ start: cursor, el: w });
    });
    return idx;
  }

  function setRead(on) {
    document.querySelectorAll('#toggleRead, #toggleRead2').forEach(function (b) {
      b.textContent = on ? '⏹ Stop' : '🔊 Read Aloud';
      b.classList.toggle('active', on);
    });
  }

  function startReading() {
    if (!synth) { alert('Read-aloud is not supported in this browser.'); return; }
    if (!currentScript) return;
    synth.cancel();
    utter = new SpeechSynthesisUtterance(currentScript);
    var voices = synth.getVoices();
    var vi = parseInt(voiceSel.value, 10);
    if (voices[vi]) utter.voice = voices[vi];
    utter.rate = parseFloat(rateInput.value);
    var wordIdx = buildWordIndex();
    utter.onboundary = function (ev) {
      if (ev.name && ev.name !== 'word') return;
      clearHighlight();
      var active = null;
      for (var i = 0; i < wordIdx.length; i++) {
        if (wordIdx[i].start <= ev.charIndex) active = wordIdx[i]; else break;
      }
      if (active) {
        active.el.classList.add('reading');
        // keep the spoken word near the guide line
        var rect = active.el.getBoundingClientRect();
        var target = stage.clientHeight * 0.5;
        pos += (rect.top - target);
        applyTransform();
      }
    };
    utter.onend = function () { reading = false; setRead(false); clearHighlight(); };
    reading = true; setRead(true);
    synth.speak(utter);
  }
  function stopReading() {
    if (synth) synth.cancel();
    reading = false; setRead(false); clearHighlight();
  }
  document.querySelectorAll('#toggleRead, #toggleRead2').forEach(function (b) {
    b.addEventListener('click', function () { reading ? stopReading() : startReading(); });
  });
  rateInput.addEventListener('input', function () { if (reading) startReading(); });

  // ── Tap to hide chrome ──
  stage.addEventListener('click', function (e) {
    if (e.target.closest('#paste')) return;
    document.getElementById('bar').classList.toggle('hidden');
    document.getElementById('foot').classList.toggle('hidden');
  });

  // keyboard: space = scroll, r = read
  document.addEventListener('keydown', function (e) {
    if (e.code === 'Space') { e.preventDefault(); setScroll(!scrolling); }
    else if (e.key === 'r' || e.key === 'R') { reading ? stopReading() : startReading(); }
  });
})();
</script>
</body>
</html>"""
