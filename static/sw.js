const VERSION = 'v13';
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
  '/final-grade', '/station-reviews', '/physical-reviews', '/odt-reviews',
  '/edit-interview', '/edit-candidate', '/edit-note',
  '/add-name', '/login'
];

function isFieldNavigation(url) {
  if (url.pathname === '/') return true;
  return FIELD_PREFIXES.some(p => url.pathname === p || url.pathname.startsWith(p + '/') || url.pathname.startsWith(p));
}

// Warm ALL field pages into the page cache the moment any page loads online,
// carrying the live session cookie — so the whole app is usable offline after
// the first online load (iOS Safari PWA has no Background Sync). Field
// feedback: "לשמור את כל העמודים בטעינה הראשונה כשיש אינטרנט".
const WARM_PAGES = [
  '/', '/new-review', '/new-group-review', '/counter-review', '/circles',
  '/candidates/', '/interview/', '/show-interview/', '/new-note', '/show-notes',
  '/group-manage', '/final-status/', '/final-grade/', '/add-candidate',
  '/station-reviews/', '/physical-reviews/', '/odt-reviews/', '/add-name'
];
let lastWarm = 0;
function warmFieldPages() {
  const now = Date.now();
  if (now - lastWarm < 60000) return; // throttle: at most once a minute
  lastWarm = now;
  caches.open(PAGE_CACHE).then(cache => {
    WARM_PAGES.forEach(path => {
      fetch(path, { credentials: 'same-origin' }).then(res => {
        // Cache only a real authenticated render — never a 302→/login or error.
        if (res && res.ok && res.type === 'basic' && new URL(res.url).pathname === path) {
          cache.put(path, res.clone());
        }
      }).catch(() => {}); // offline/flaky at warm time — retry on the next online load
    });
  });
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
      warmFieldPages();
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
