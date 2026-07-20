const VERSION = 'v8';
const SHELL_CACHE = 'meymadion-shell-' + VERSION;
const PAGE_CACHE = 'meymadion-pages-' + VERSION;

// Static assets the app shell needs to render offline.
const SHELL = [
  '/static/css/app.css',
  '/static/js/offline.js',
  '/static/vendor/fontawesome-free/css/all.min.css',
  '/static/img/logo-meymadion.png',
  '/static/img/my-group.jpg',
  '/static/img/physical.jpg',
  '/static/manifest.webmanifest',
  '/offline'
];

// Field pages cached for offline viewing. Exact '/' plus these prefixes.
const FIELD_PREFIXES = [
  '/circles', '/counter-review', '/new-review', '/new-group-review',
  '/interview', '/show-interview', '/new-note', '/show-notes',
  '/candidate', '/candidates', '/add-candidate', '/group-manage', '/final-status',
  '/add-name', '/login'
];

function isFieldNavigation(url) {
  if (url.pathname === '/') return true;
  return FIELD_PREFIXES.some(p => url.pathname === p || url.pathname.startsWith(p + '/') || url.pathname.startsWith(p));
}

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== SHELL_CACHE && k !== PAGE_CACHE).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  // Never touch writes — the page-level outbox handles those.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Stale-while-revalidate for static assets: serve cache instantly, refresh in
  // the background so an updated CSS/JS is picked up on the next load.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.open(SHELL_CACHE).then(cache =>
        cache.match(req).then(hit => {
          const network = fetch(req).then(res => {
            if (res && res.ok) cache.put(req, res.clone());
            return res;
          }).catch(() => hit);
          return hit || network;
        })
      )
    );
    return;
  }

  // Network-first for field navigations, cache fallback, then offline page.
  if (req.mode === 'navigate' && isFieldNavigation(url)) {
    event.respondWith(
      fetch(req).then(res => {
        const copy = res.clone();
        caches.open(PAGE_CACHE).then(c => c.put(req, copy));
        return res;
      }).catch(() =>
        caches.match(req).then(hit => hit || caches.match('/offline'))
      )
    );
    return;
  }

  // Other navigations (admin, downloads, exports) are online-only and never
  // cached — but a failure should land on our branded offline page, not the
  // browser's native error.
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match('/offline')));
    return;
  }
  // Non-navigation requests (API fetches etc.): straight to network.
});
