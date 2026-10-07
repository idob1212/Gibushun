const VERSION = 'v16';
const SHELL_CACHE = 'meymadion-shell-' + VERSION;
const PAGE_CACHE = 'meymadion-pages-' + VERSION;
// Candidate photos use versioned URLs (?v=N), so a cached copy never goes stale.
const PHOTO_CACHE = 'meymadion-photos-v1';

// Static assets the app shell needs to render offline.
const SHELL = [
  '/static/css/app.css',
  '/static/js/offline.js',
  '/static/js/app.js',
  '/static/vendor/fontawesome-free/css/all.min.css',
  '/static/img/logo-meymadion.png',
  '/static/img/my-group.jpg',
  '/static/img/physical.jpg',
  '/static/manifest.webmanifest',
  '/offline'
];

// Field pages cached for offline viewing. Exact '/' plus these prefixes.
const FIELD_PREFIXES = [
  '/circles', '/counter-review', '/new-review', '/new-group-review', '/acts',
  '/interview', '/show-interview', '/new-note', '/show-notes',
  '/candidate/', '/add-candidate', '/group-manage', '/final-status',
  '/final-grade', '/final-summary', '/physical-reviews', '/odt-reviews',
  '/edit-interview', '/edit-candidate', '/edit-note', '/staff',
  '/add-name', '/login'
];

function isFieldNavigation(url) {
  if (url.pathname === '/') return true;
  return FIELD_PREFIXES.some(p => url.pathname === p || url.pathname.startsWith(p + '/') || url.pathname.startsWith(p));
}

// Keep the field pages in the page cache so the app works offline after one
// online visit (iOS Safari PWA has no Background Sync). Field feedback:
// "לשמור את כל העמודים בטעינה הראשונה כשיש אינטרנט".
// The page sends the list (group accounts only). Pages are fetched ONE AT A
// TIME and at most every 5 minutes: the old version fired ~18 requests at
// once on every navigation, which queued the user's real taps behind them on
// the server and on the phone's radio — a large part of the "stuck app".
const WARM_EVERY_MS = 5 * 60 * 1000;
let lastWarm = 0;
let warming = false;
async function warmFieldPages(pages) {
  const now = Date.now();
  if (warming || now - lastWarm < WARM_EVERY_MS) return;
  warming = true;
  lastWarm = now;
  try {
    const cache = await caches.open(PAGE_CACHE);
    for (const path of pages) {
      if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) continue;
      try {
        const res = await fetch(path, { credentials: 'same-origin' });
        // Cache only a real authenticated render — never a 302→/login or error.
        if (res && res.ok && res.type === 'basic' && new URL(res.url).pathname === path) {
          await cache.put(path, res.clone());
        }
      } catch (e) {
        break; // offline/flaky — try again on a later visit
      }
    }
  } finally {
    warming = false;
  }
}

self.addEventListener('message', event => {
  const data = event.data || {};
  if (data.type === 'warm' && Array.isArray(data.pages)) {
    event.waitUntil(warmFieldPages(data.pages.slice(0, 30)));
  }
});

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== SHELL_CACHE && k !== PAGE_CACHE && k !== PHOTO_CACHE).map(k => caches.delete(k))
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

  // Versioned candidate photos: cache-first (offline profiles keep faces).
  if (url.pathname.startsWith('/candidate-photo/') && url.searchParams.has('v')) {
    event.respondWith(
      caches.open(PHOTO_CACHE).then(cache =>
        cache.match(req).then(hit => hit || fetch(req).then(res => {
          if (res && res.ok) cache.put(req, res.clone());
          return res;
        }))
      )
    );
    return;
  }

  // Network-first for field navigations, cache fallback, then offline page.
  // The network gets 5s: on lie-fi (connected but dead radio) an uncapped
  // fetch hangs navigation for the browser's full timeout. After the cap the
  // cached copy is served and the network response, if it ever lands, still
  // refreshes the cache for next time.
  if (req.mode === 'navigate' && isFieldNavigation(url)) {
    const network = fetch(req).then(res => {
      // Cache only a real authenticated render — a session-expiry 302→/login
      // would otherwise poison the cache entry for this page.
      if (res && res.ok && new URL(res.url).pathname === url.pathname) {
        const copy = res.clone();
        caches.open(PAGE_CACHE).then(c => c.put(req, copy));
      }
      return res;
    });
    event.respondWith(
      Promise.race([
        network.catch(() => undefined),
        new Promise(resolve => setTimeout(() => resolve(undefined), 5000))
      ]).then(res => {
        if (res) return res;
        // Timed out or failed: cached page if we have one, else wait the
        // network out in full, else the branded offline page.
        return caches.match(req).then(hit =>
          hit || network.catch(() => caches.match('/offline'))
        );
      })
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
