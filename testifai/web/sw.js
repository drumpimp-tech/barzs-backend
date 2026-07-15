
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
