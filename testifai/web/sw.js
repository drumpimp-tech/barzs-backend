
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
