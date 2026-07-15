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
    # Point head assets at same-folder files and add PNG app icons.
    html = html.replace('href="/app/manifest.webmanifest"', 'href="./manifest.webmanifest"')
    html = html.replace(
        '<link rel="apple-touch-icon" href="/app/icon.svg">',
        '<link rel="apple-touch-icon" href="./icon.png">\n'
        '<link rel="apple-touch-icon" sizes="180x180" href="./icon.png">',
    )
    html = html.replace(
        '<link rel="icon" href="/app/icon.svg" type="image/svg+xml">',
        '<link rel="icon" type="image/png" href="./icon.png">\n'
        '<link rel="icon" href="./icon.svg" type="image/svg+xml">',
    )
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
const CACHE = 'testifai-static-v1';
const SHELL = ['/', './index.html', './icon.png', './icon.svg', './manifest.webmanifest',
  './data/us_states.json', './data/ai_applications.json', './data/advocacy_goals.json', './data/ai_blacklist.json'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;                  // never cache Claude POSTs
  const url = new URL(e.request.url);
  if (url.origin === location.origin) {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
"""

NETLIFY_TOML = """# Static deploy of the TESTIFAI app (bring-your-own-key). No build step:
# this command overrides any build command set in the Netlify UI.
[build]
  publish = "."
  command = "echo 'TESTIFAI static site - nothing to build'"

[[headers]]
  for = "/sw.js"
  [headers.values]
    Cache-Control = "no-cache"

[[headers]]
  for = "/manifest.webmanifest"
  [headers.values]
    Content-Type = "application/manifest+json"
"""


def make_placeholder_png(path: Path):
    """A simple red/white/blue placeholder. Replace web/icon.png with the real art."""
    from PIL import Image, ImageDraw
    import math
    NAVY, RED, BLUE, WHITE = (10, 26, 58), (224, 42, 60), (79, 131, 232), (245, 248, 255)
    S = 512
    img = Image.new("RGB", (S, S), NAVY)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([26, 26, S - 26, S - 26], radius=100, outline=RED, width=14)
    d.rounded_rectangle([44, 44, S - 44, S - 44], radius=84, outline=BLUE, width=7)
    # a document shape
    d.rounded_rectangle([158, 128, 354, 372], radius=22, fill=WHITE)
    d.rectangle([184, 244, 328, 256], fill=(120, 130, 150))
    d.rectangle([184, 278, 328, 290], fill=(120, 130, 150))
    d.rectangle([184, 312, 292, 324], fill=(120, 130, 150))
    d.rounded_rectangle([184, 158, 256, 222], radius=10, fill=BLUE)   # chip
    # star
    cx, cy, r1, r2 = 256, 428, 32, 13
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r1 if i % 2 == 0 else r2
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, fill=RED)
    img.save(path, "PNG")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)

    (OUT / "index.html").write_text(build_html())
    (OUT / "manifest.webmanifest").write_text(json.dumps(MANIFEST, indent=2))
    (OUT / "sw.js").write_text(SW_JS)
    (OUT / "icon.svg").write_text(webapp._ICON_SVG)
    (OUT / "netlify.toml").write_text(NETLIFY_TOML)

    for name in ["us_states.json", "ai_applications.json", "advocacy_goals.json", "ai_blacklist.json"]:
        shutil.copy(DATA / name, OUT / "data" / name)

    # Placeholder icon unless the real one has already been dropped in.
    icon = OUT / "icon.png"
    real = HERE / "assets" / "icon.png"
    if real.exists():
        shutil.copy(real, icon)
        print("Using real icon from assets/icon.png")
    else:
        make_placeholder_png(icon)
        print("Wrote placeholder icon.png (replace with your art at web/icon.png or assets/icon.png)")

    files = sorted(p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file())
    print("Built", OUT)
    for f in files:
        print("  ", f)


if __name__ == "__main__":
    main()
