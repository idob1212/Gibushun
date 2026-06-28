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
  var banner;
  function ensureBanner() {
    if (banner) return banner;
    banner = document.createElement('div');
    banner.id = 'net-banner';
    // Sit above the mobile bottom dock when one is visible.
    var dock = document.querySelector('.dock');
    var offset = dock && getComputedStyle(dock).display !== 'none' ? dock.offsetHeight : 0;
    banner.style.cssText = 'position:fixed;left:0;right:0;bottom:' + offset + 'px;z-index:60;transform:translateY(150%);' +
      'transition:transform .25s ease;padding:10px 14px;text-align:center;font-weight:600;font-size:14px;' +
      'color:#fff;box-shadow:0 -2px 10px rgba(0,0,0,.15)';
    document.body.appendChild(banner);
    return banner;
  }
  function showBanner(text, color) {
    var b = ensureBanner();
    b.textContent = text;
    b.style.background = color;
    b.style.transform = 'translateY(0)';
  }
  function hideBanner() { if (banner) banner.style.transform = 'translateY(100%)'; }

  function toast(text) {
    showBanner(text, '#16a34a');
    setTimeout(hideBanner, 2600);
  }

  function refreshStatus() {
    if (!navigator.onLine) {
      pendingCount().then(function (n) {
        showBanner(n ? ('אופליין — ' + n + ' פעולות ממתינות לסנכרון') : 'אופליין — נתונים יישמרו במכשיר', '#b45309');
      });
    } else {
      pendingCount().then(function (n) { if (!n) hideBanner(); });
    }
  }

  // --- Replay ---------------------------------------------------------------
  var flushing = false;
  function flush() {
    if (flushing || !navigator.onLine) return Promise.resolve();
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
        refreshStatus();
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
            refreshStatus();
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

  window.addEventListener('online', function () { refreshStatus(); flush(); });
  window.addEventListener('offline', refreshStatus);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && navigator.onLine) flush();
  });

  document.addEventListener('DOMContentLoaded', function () {
    bindForms();
    refreshStatus();
    if (navigator.onLine) flush();
  });
})();
