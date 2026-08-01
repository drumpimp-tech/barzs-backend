"""
Build the static distribution site (testifai/web/) for Netlify or any static host.

It reuses the SAME app code served by the backend (routes/webapp.py) so the two
never drift, then flips it into "static / bring-your-own-key" mode: the user
supplies their own Anthropic key and the browser calls Claude directly, so no
server is needed.

Run:  python build_static.py
Output: testifai/web/  (deploy this folder)
"""

import json
import shutil
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "web"
DATA = HERE / "data"

import sys
sys.path.insert(0, str(HERE))
from routes import webapp  # noqa: E402


def build_html() -> str:
    html = webapp._APP_HTML
    # Turn on static / BYOK mode.
    html = html.replace(
        "<script>\n(function () {",
        "<script>window.TESTIFAI_CONFIG = { static: true };</script>\n<script>\n(function () {",
        1,
    )
    # Point every /app/ asset reference at same-folder files.
    html = html.replace("/app/manifest.webmanifest", "./manifest.webmanifest")
    html = html.replace("/app/icon.png", "./icon.png")
    html = html.replace("/app/icon.svg", "./icon.svg")
    return html


MANIFEST = {
    "name": "TESTIFAI",
    "short_name": "TESTIFAI",
    "description": "Write AI testimony to your legislators and read it on a built-in teleprompter.",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#0a1a3a",
    "theme_color": "#0a1a3a",
    "icons": [
        {"src": "./icon.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        {"src": "./icon.svg", "sizes": "any", "type": "image/svg+xml"},
    ],
}

SW_JS = """
const CACHE = 'testifai-static-v3';
self.addEventListener('install', e => { self.skipWaiting(); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;                  // never cache Claude POSTs
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;              // leave cross-origin (data/API) to the network
  // Network-first: every deploy is picked up immediately; cache is only an offline fallback.
  e.respondWith(
    fetch(e.request).then(r => { const c = r.clone(); caches.open(CACHE).then(cache => cache.put(e.request, c)); return r; })
                    .catch(() => caches.match(e.request))
  );
});
"""

NETLIFY_TOML = """# Static deploy of the TESTIFAI app. No build step:
# this command overrides any build command set in the Netlify UI.
[build]
  publish = "."
  command = "echo 'TESTIFAI static site - nothing to build'"

[functions]
  directory = "netlify/functions"

[[headers]]
  for = "/sw.js"
  [headers.values]
    Cache-Control = "no-cache"

[[headers]]
  for = "/manifest.webmanifest"
  [headers.values]
    Content-Type = "application/manifest+json"
"""

# Server-key proxy: when the site owner sets GOOGLE_AI_API_KEY (or
# ANTHROPIC_API_KEY) in the Netlify environment, the app skips the key
# onboarding entirely and generates through this function instead. Users never
# handle keys. All usage bills to the owner's key.
AI_PROXY_MJS = """
const GEMINI_MODELS = ["gemini-flash-latest", "gemini-3-flash-preview", "gemini-2.5-flash"];

export default async (req) => {
  const gKey = process.env.GOOGLE_AI_API_KEY || "";
  const aKey = process.env.ANTHROPIC_API_KEY || "";
  const configured = !!(gKey || aKey);

  if (req.method === "GET") {
    return Response.json({ configured });
  }
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }
  if (!configured) {
    return Response.json({ error: "No server key configured" }, { status: 503 });
  }

  let body;
  try { body = await req.json(); } catch (e) {
    return Response.json({ error: "Bad request" }, { status: 400 });
  }
  const system = String(body.system || "").slice(0, 20000);
  const user = String(body.user || "").slice(0, 20000);
  if (!user) return Response.json({ error: "Missing prompt" }, { status: 400 });

  try {
    if (aKey) {
      const r = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "content-type": "application/json", "x-api-key": aKey, "anthropic-version": "2023-06-01" },
        body: JSON.stringify({ model: "claude-sonnet-5", max_tokens: 4000, system, messages: [{ role: "user", content: user }] }),
      });
      if (!r.ok) return Response.json({ error: "Claude error (" + r.status + ")" }, { status: 502 });
      const d = await r.json();
      return Response.json({ text: (d.content && d.content[0] && d.content[0].text) || "" });
    }
    let lastStatus = 0;
    for (const model of GEMINI_MODELS) {
      const r = await fetch(
        "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent?key=" + encodeURIComponent(gKey),
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ systemInstruction: { parts: [{ text: system }] }, contents: [{ role: "user", parts: [{ text: user }] }] }),
        },
      );
      if (r.ok) {
        const d = await r.json();
        const parts = (d.candidates && d.candidates[0] && d.candidates[0].content && d.candidates[0].content.parts) || [];
        return Response.json({ text: parts.map((p) => p.text || "").join("") });
      }
      lastStatus = r.status;
      if (r.status !== 404) break;
    }
    return Response.json({ error: "Google AI error (" + lastStatus + ")" }, { status: 502 });
  } catch (e) {
    return Response.json({ error: "Upstream failure" }, { status: 502 });
  }
};
"""


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)

    (OUT / "index.html").write_text(build_html())
    (OUT / "manifest.webmanifest").write_text(json.dumps(MANIFEST, indent=2))
    (OUT / "sw.js").write_text(SW_JS)
    (OUT / "icon.svg").write_text(webapp._ICON_SVG)
    (OUT / "netlify.toml").write_text(NETLIFY_TOML)
    (OUT / "netlify" / "functions").mkdir(parents=True)
    (OUT / "netlify" / "functions" / "ai-proxy.mjs").write_text(AI_PROXY_MJS)

    for name in ["us_states.json", "ai_applications.json", "advocacy_goals.json", "ai_blacklist.json"]:
        shutil.copy(DATA / name, OUT / "data" / name)

    # The app icon MUST be the official TESTIFAI logo (the intro-animation
    # logo). No placeholders, no substitutes: drop the real file at
    # testifai/assets/icon.png or the build refuses to produce a site.
    icon = OUT / "icon.png"
    real = HERE / "assets" / "icon.png"
    if not real.exists():
        raise SystemExit(
            "ERROR: testifai/assets/icon.png is missing.\n"
            "Add the official TESTIFAI logo (the intro-animation logo) there and rebuild.\n"
            "No placeholder will be generated."
        )
    shutil.copy(real, icon)
    print("Using official logo from assets/icon.png")

    files = sorted(p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file())
    print("Built", OUT)
    for f in files:
        print("  ", f)


if __name__ == "__main__":
    main()
