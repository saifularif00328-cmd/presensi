/* Service worker Portal Presensi: menyimpan tampilan dasar (CSS, ikon) agar portal cepat
   dibuka dan tetap menampilkan pesan saat HP sedang offline. Data siswa TIDAK disimpan. */
const CACHE = 'portal-v1';
const ASET = ['{{ url_for("static", filename="css/app.css") }}', '{{ url_for("static", filename="icons.svg") }}'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(ASET); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener('fetch', function (e) {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(caches.match(e.request).then(function (r) { return r || fetch(e.request); }));
    return;
  }
  if (e.request.mode === 'navigate') {
    e.respondWith(fetch(e.request).catch(function () {
      return new Response('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">' +
        '<body style="font-family:sans-serif;padding:2rem;text-align:center;color:#344054">' +
        '<h2>Sedang offline</h2><p>Periksa koneksi internet HP Anda, lalu muat ulang halaman.</p></body>',
        {headers: {'Content-Type': 'text/html; charset=utf-8'}});
    }));
  }
});
