// Offline support. Every page load and data request goes to the network first (bypassing the browser
// cache), so new projections appear as soon as they are published; the saved copy is used only offline.
const CACHE = 'butler-ff-__BUILD__';
const SHELL = ['./', './index.html', './data.json', './history.json', './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png'];
self.addEventListener('install', e => {
  // one missing file (history.json early in a season) must not block the install
  e.waitUntil(caches.open(CACHE).then(c => Promise.allSettled(SHELL.map(u => c.add(new Request(u, {cache: 'reload'}))))));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return; // Sleeper, fonts: straight to network
  const fresh = e.request.mode === 'navigate'
    ? fetch(url.href, {cache: 'no-store', credentials: 'same-origin'})
    : fetch(e.request.url, {cache: 'no-store'});
  e.respondWith(fresh.then(r => {
    if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request.mode === 'navigate' ? './index.html' : e.request, copy)); }
    return r;
  }).catch(() => caches.match(e.request).then(r => r || caches.match('./index.html'))));
});
