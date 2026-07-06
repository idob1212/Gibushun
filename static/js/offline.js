(function () {
  'use strict';

  // Endpoints whose JSON POSTs may be queued and replayed when offline.
  var JSON_WRITE = ['/circles/finished', '/circles/finished-act', '/update-counter-reviews'];

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  // --- IndexedDB outbox -----------------------------------------------------
  var DB;
  function db() {
    if (DB) return DB;
    DB = new Promise(function (resolve, reject) {
      var req = indexedDB.open('meymadion', 1);
      req.onupgradeneeded = function () {
        req.result.createObjectStore('outbox', { keyPath: 'id', autoIncrement: true });
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
    return DB;
  }

  function tx(mode) {
    return db().then(function (d) { return d.transaction('outbox', mode).objectStore('outbox'); });
  }

  function queue(item) {
    return tx('readwrite').then(function (store) {
      return new Promise(function (resolve, reject) {
        var r = store.add(item);
        r.onsuccess = function () { resolve(); };
        r.onerror = function () { reject(r.error); };
      });
    });
  }

  function allItems() {
    return tx('readonly').then(function (store) {
      return new Promise(function (resolve, reject) {
        var r = store.getAll();
        r.onsuccess = function () { resolve(r.result || []); };
        r.onerror = function () { reject(r.error); };
      });
    });
  }

  function remove(id) {
    return tx('readwrite').then(function (store) {
      return new Promise(function (resolve) {
        store.delete(id).onsuccess = function () { resolve(); };
      });
    });
  }

  function pendingCount() { return allItems().then(function (a) { return a.length; }); }

  // --- Connectivity banner / toast -----------------------------------------
  // Two distinct pieces of UI, so a transient toast never clobbers (or gets
  // clobbered by) the persistent offline strip:
  //   * offlineBar — sticky status, shown only while offline, sits above the dock
  //   * toastEl    — transient success/sync message, auto-dismisses
  var BAR_CSS = 'position:fixed;left:0;right:0;z-index:60;transform:translateY(150%);' +
    'transition:transform .25s ease;padding:10px 14px;text-align:center;font-weight:600;' +
    'font-size:14px;color:#fff;box-shadow:0 -2px 10px rgba(0,0,0,.18)';

  function dockOffset() {
    // Recomputed every time we show something, so the bar always clears the
    // dock even if the dock wasn't laid out yet when the element was created.
    var dock = document.querySelector('.dock');
    if (dock && getComputedStyle(dock).display !== 'none') return dock.offsetHeight;
    return 0;
  }

  var offlineBar, offlineBarShown = false;
  function ensureOfflineBar() {
    if (offlineBar) return offlineBar;
    offlineBar = document.createElement('div');
    offlineBar.id = 'net-banner';
    offlineBar.style.cssText = BAR_CSS + ';bottom:0;background:#b45309';
    document.body.appendChild(offlineBar);
    return offlineBar;
  }
  function offlineBarVisible() { return offlineBarShown; }
  function showOfflineBar(text) {
    var b = ensureOfflineBar();
    b.textContent = text;
    b.style.bottom = dockOffset() + 'px';
    b.style.transform = 'translateY(0)';
    offlineBarShown = true;
  }
  function hideOfflineBar() {
    if (offlineBar) offlineBar.style.transform = 'translateY(150%)';
    offlineBarShown = false;
  }

  var toastEl, toastTimer;
  function ensureToast() {
    if (toastEl) return toastEl;
    toastEl = document.createElement('div');
    toastEl.id = 'net-toast';
    toastEl.style.cssText = BAR_CSS + ';bottom:0;background:#16a34a';
    document.body.appendChild(toastEl);
    return toastEl;
  }
  // Transient "push": always removed after a few seconds, and stacked above the
  // dock + offline bar so it never hides the bottom navigation.
  function toast(text) {
    var t = ensureToast();
    t.textContent = text;
    var above = dockOffset() + (offlineBarVisible() ? offlineBar.offsetHeight : 0);
    t.style.bottom = above + 'px';
    t.style.transform = 'translateY(0)';
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.style.transform = 'translateY(150%)'; }, 3200);
  }

  function refreshStatus() {
    if (offline) {
      pendingCount().then(function (n) {
        showOfflineBar(n ? ('אופליין — ' + n + ' פעולות ממתינות לסנכרון') : 'אופליין — נתונים יישמרו במכשיר');
      });
    } else {
      hideOfflineBar();
    }
  }

  // --- Connectivity truth ---------------------------------------------------
  // iOS Safari fires 'online'/'offline' unreliably and navigator.onLine lies,
  // so we actively probe the server and treat a positive probe as the source of
  // truth. This is what clears a "stuck" offline banner once the net is back.
  var offline = !navigator.onLine;
  function probe() {
    return new Promise(function (resolve) {
      var done = false;
      var timer = setTimeout(function () { if (!done) { done = true; resolve(false); } }, 4000);
      nativeFetch('/sw.js', { method: 'HEAD', cache: 'no-store' })
        .then(function (r) { if (!done) { done = true; clearTimeout(timer); resolve(!!r && (r.ok || r.status === 200)); } })
        .catch(function () { if (!done) { done = true; clearTimeout(timer); resolve(false); } });
    });
  }
  function setOffline(v) {
    var changed = v !== offline;
    offline = v;
    refreshStatus();
    if (!v && changed) flush();
  }
  // Reconcile against the real network state; used on events and the heartbeat.
  function recheck() {
    if (document.hidden) return;
    probe().then(function (ok) { setOffline(!ok); });
  }

  // --- Replay ---------------------------------------------------------------
  var flushing = false;
  function flush() {
    if (flushing || offline) return Promise.resolve();
    flushing = true;
    return allItems().then(function (items) {
      if (!items.length) return 0;
      var synced = 0;
      function step(i) {
        if (i >= items.length) return Promise.resolve(synced);
        var item = items[i];
        var opts = { method: 'POST', headers: { 'X-Request-Id': item.requestId } };
        if (item.kind === 'json') {
          opts.headers['Content-Type'] = 'application/json';
          opts.body = item.body;
        } else {
          var fd = new FormData();
          item.fields.forEach(function (kv) { fd.append(kv[0], kv[1]); });
          opts.body = fd;
        }
        return nativeFetch(item.url, opts).then(function (res) {
          if (res.ok || res.redirected || res.status === 200) {
            synced++;
            return remove(item.id).then(function () { return step(i + 1); });
          }
          return step(i + 1); // server rejected (e.g. validation) — leave queued, try next
        }).catch(function () { return synced; }); // network died — stop
      }
      return step(0);
    }).then(function (synced) {
      flushing = false;
      if (synced > 0) toast('סונכרנו ' + synced + ' פעולות ✓');
      refreshStatus();
    }).catch(function () { flushing = false; });
  }

  // --- fetch wrapper for JSON write endpoints -------------------------------
  var nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    init = init || {};
    var url = typeof input === 'string' ? input : (input && input.url);
    var method = (init.method || (input && input.method) || 'GET').toUpperCase();
    var isWrite = method === 'POST' && url && JSON_WRITE.some(function (p) { return url.indexOf(p) !== -1; });

    if (!isWrite) return nativeFetch(input, init);

    var requestId = uuid();
    var bodyObj = {};
    try { bodyObj = JSON.parse(init.body || '{}'); } catch (e) {}
    bodyObj.request_id = requestId;
    var body = JSON.stringify(bodyObj);
    init.body = body;
    init.headers = Object.assign({}, init.headers, { 'X-Request-Id': requestId, 'Content-Type': 'application/json' });

    function queueAndAck() {
      return queue({ kind: 'json', url: url, body: body, requestId: requestId, ts: Date.now() }).then(function () {
        setOffline(true);  // we couldn't reach the server; show the pending strip
        return new Response(JSON.stringify({ success: true, queued: true, message: 'נשמר במכשיר — יסונכרן ברגע שתהיה רשת ✓' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } });
      });
    }

    if (!navigator.onLine) return queueAndAck();
    return nativeFetch(url, init).catch(function () { return queueAndAck(); });
  };

  // --- offline form interception (interview / note / add-candidate) ---------
  function bindForms() {
    document.querySelectorAll('form[data-offline]').forEach(function (form) {
      if (form._offlineBound) return;
      form._offlineBound = true;
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var requestId = uuid();
        var fd = new FormData(form);
        fd.append('request_id', requestId);
        var action = form.getAttribute('action') || location.pathname;
        var fields = [];
        fd.forEach(function (v, k) { fields.push([k, v]); });

        function queueIt() {
          return queue({ kind: 'form', url: action, fields: fields, requestId: requestId, ts: Date.now() }).then(function () {
            setOffline(true);  // we couldn't reach the server; show the pending strip
            toast('נשמר במכשיר — יסונכרן ברגע שתהיה רשת ✓');
            form.reset();
          });
        }

        if (!navigator.onLine) { queueIt(); return; }

        nativeFetch(action, { method: 'POST', headers: { 'X-Request-Id': requestId }, body: fd })
          .then(function (res) {
            if (res.redirected) {
              window.location.href = res.url; // PRG success — show server flash
            } else if (res.ok) {
              // 200 without redirect = validation errors re-rendered; show them
              res.text().then(function (html) {
                document.open(); document.write(html); document.close();
              });
            } else {
              queueIt();
            }
          })
          .catch(queueIt); // network failed mid-request (lie-fi) — keep the data
      });
    });
  }

  // --- wiring ---------------------------------------------------------------
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function (err) {
        console.error('SW registration failed', err);
      });
    });
  }

  // Browser hints are advisory; confirm with a probe (going online) but trust
  // 'offline' immediately (it's the safe direction).
  window.addEventListener('online', recheck);
  window.addEventListener('offline', function () { setOffline(true); });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') recheck();
  });

  // Heartbeat: periodically reconcile so a returned connection clears the
  // offline banner (and drains the outbox) even if no 'online' event fired.
  setInterval(recheck, 15000);

  document.addEventListener('DOMContentLoaded', function () {
    bindForms();
    refreshStatus();   // paint immediately from the current best guess
    recheck();         // then confirm against the server and flush if online
  });
})();
