/* Service Worker for מימדיון PWA */

const CACHE_VERSION = 'v1';
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const PAGES_CACHE = `pages-${CACHE_VERSION}`;

const STATIC_ASSETS = [
  '/static/css/clean-blog.min.css',
  '/static/vendor/bootstrap/css/bootstrap.min.css',
  '/static/vendor/fontawesome-free/css/all.min.css',
  '/static/vendor/jquery/jquery.min.js',
  '/static/vendor/bootstrap/js/bootstrap.bundle.min.js',
  '/static/js/clean-blog.min.js',
  '/static/js/dexie.min.js',
  '/static/js/offline-manager.js',
  '/static/js/sync-engine.js',
  '/static/js/install-prompt.js',
  '/static/img/logo-meymadion.png',
  '/static/manifest.json'
];

/* ── Install: pre-cache static assets ── */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

/* ── Activate: clean old caches ── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== STATIC_CACHE && key !== PAGES_CACHE)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

/* ── Message handler: pre-cache all page URLs on login ── */
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'PRECACHE_PAGES') {
    const urls = event.data.urls || [];
    event.waitUntil(
      caches.open(PAGES_CACHE).then(cache =>
        Promise.allSettled(
          urls.map(url =>
            fetch(url, { credentials: 'include' })
              .then(response => {
                if (response.ok) {
                  return cache.put(url, response);
                }
              })
              .catch(() => { /* skip failed URLs silently */ })
          )
        )
      )
    );
  }
});

/* ── Fetch handler ── */
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  // Skip non-GET requests (form submissions, API writes)
  if (request.method !== 'GET') return;

  // API endpoints: Network-First
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request, PAGES_CACHE));
    return;
  }

  // Static assets (CSS, JS, images, fonts): Cache-First
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // HTML pages: Network-First
  if (request.headers.get('accept') && request.headers.get('accept').includes('text/html')) {
    event.respondWith(networkFirst(request, PAGES_CACHE));
    return;
  }

  // AJAX data endpoints (subjects, physicals, stations, etc): Network-First
  if (url.pathname.match(/^\/(subjects|physicals|stations|get-station-reviews)\//)) {
    event.respondWith(networkFirst(request, PAGES_CACHE));
    return;
  }

  // Default: Network-First
  event.respondWith(networkFirst(request, PAGES_CACHE));
});

/* ── Caching strategies ── */

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    // If it was an HTML request, return a fallback offline page
    if (request.headers.get('accept') && request.headers.get('accept').includes('text/html')) {
      return new Response(
        '<html dir="rtl"><body style="font-family:sans-serif;text-align:center;padding:50px">' +
        '<h1>אופליין</h1><p>העמוד לא זמין במצב אופליין. נסה שוב כשיש חיבור.</p></body></html>',
        { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
      );
    }
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    throw err;
  }
}

/* ── Background Sync (progressive enhancement for Chrome/Android) ── */
self.addEventListener('sync', event => {
  if (event.tag === 'sync-queue') {
    event.waitUntil(
      self.clients.matchAll().then(clients => {
        clients.forEach(client => {
          client.postMessage({ type: 'TRIGGER_SYNC' });
        });
      })
    );
  }
});
