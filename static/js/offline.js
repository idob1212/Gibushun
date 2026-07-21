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

  function put(item) {
    return tx('readwrite').then(function (store) {
      return new Promise(function (resolve) {
        store.put(item).onsuccess = function () { resolve(); };
      });
    });
  }

  function pendingCount() { return allItems().then(function (a) { return a.length; }); }

  // --- Connectivity banner / toast -----------------------------------------
  // Two distinct pieces of UI, so a transient toast never clobbers (or gets
  // clobbered by) the persistent offline strip:
  //   * offlineBar — sticky status, shown only while offline
  //   * toastEl    — transient success/sync message, auto-dismisses
  // Both sit at the TOP of the screen, under the navbar — at the bottom they
  // covered action rows and the dock (field feedback: "למעלה זה היה טוב").
  // pointer-events:none — taps pass through to the page beneath; the ✕ button
  // is the one interactive exception.
  var BAR_CSS = 'position:fixed;left:0;right:0;z-index:60;pointer-events:none;opacity:0;visibility:hidden;' +
    'transition:opacity .25s ease,visibility .25s;padding:10px 14px;text-align:center;font-weight:600;' +
    'font-size:14px;color:#fff;box-shadow:0 2px 10px rgba(0,0,0,.25)';

  function topOffset() {
    // The navbar is sticky top-0, so its rect ends where the banners should
    // start. Recomputed on every show — covers rotation and safe-area changes.
    var nav = document.querySelector('.app-topbar');
    return nav ? Math.max(0, nav.getBoundingClientRect().bottom) : 0;
  }
  function setVisible(el, on) {
    el.style.opacity = on ? '1' : '0';
    el.style.visibility = on ? 'visible' : 'hidden';
  }

  var offlineBar, offlineBarText, offlineBarShown = false, offlineBarDismissed = false;
  function ensureOfflineBar() {
    if (offlineBar) return offlineBar;
    offlineBar = document.createElement('div');
    offlineBar.id = 'net-banner';
    offlineBar.style.cssText = BAR_CSS + ';background:#b45309';
    offlineBarText = document.createElement('span');
    var close = document.createElement('button');
    close.type = 'button';
    close.textContent = '✕';
    close.setAttribute('aria-label', 'סגור');
    // Generous padding: the previous 4px-wide target was effectively
    // untappable on a phone (field feedback: "האיקס לא עובד").
    close.style.cssText = 'pointer-events:auto;background:rgba(0,0,0,.15);border:0;border-radius:8px;' +
      'color:#fff;font-weight:700;font-size:16px;line-height:1;margin-inline-start:12px;' +
      'padding:8px 12px;cursor:pointer;vertical-align:middle';
    close.addEventListener('click', function () {
      offlineBarDismissed = true; // stays hidden until we're back online
      hideOfflineBar();
    });
    offlineBar.appendChild(offlineBarText);
    offlineBar.appendChild(close);
    document.body.appendChild(offlineBar);
    return offlineBar;
  }
  function offlineBarVisible() { return offlineBarShown; }
  // Reserve space in the page flow so the bar never covers the top of the content.
  function reserveBarSpace() {
    var main = document.querySelector('main');
    if (main) main.style.paddingTop = (offlineBarShown && offlineBar) ? (offlineBar.offsetHeight + 12) + 'px' : '';
  }
  function showOfflineBar(text) {
    var b = ensureOfflineBar();
    offlineBarText.textContent = text;
    if (offlineBarDismissed) return;
    b.style.top = topOffset() + 'px';
    setVisible(b, true);
    offlineBarShown = true;
    reserveBarSpace();
  }
  function hideOfflineBar() {
    if (offlineBar) setVisible(offlineBar, false);
    offlineBarShown = false;
    reserveBarSpace();
  }
  // Rotation/resize can change the navbar height — keep the shown bar under it.
  function repositionOfflineBar() {
    if (offlineBarShown && offlineBar) offlineBar.style.top = topOffset() + 'px';
  }
  window.addEventListener('resize', repositionOfflineBar);
  window.addEventListener('orientationchange', repositionOfflineBar);

  var toastEl, toastTimer;
  function ensureToast() {
    if (toastEl) return toastEl;
    toastEl = document.createElement('div');
    toastEl.id = 'net-toast';
    toastEl.style.cssText = BAR_CSS + ';background:#16a34a';
    document.body.appendChild(toastEl);
    return toastEl;
  }
  // Transient "push": always removed after a few seconds, stacked under the
  // navbar and the offline bar (if shown).
  function toast(text) {
    var t = ensureToast();
    t.textContent = text;
    t.style.top = (topOffset() + (offlineBarVisible() ? offlineBar.offsetHeight + 6 : 0)) + 'px';
    setVisible(t, true);
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { setVisible(t, false); }, 3200);
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
      // 8s: field 5G can be slow enough that a healthy round-trip takes >4s,
      // and a false negative here is what makes the offline banner stick.
      var timer = setTimeout(function () { if (!done) { done = true; resolve(false); } }, 8000);
      nativeFetch('/sw.js', { method: 'HEAD', cache: 'no-store' })
        .then(function (r) { if (!done) { done = true; clearTimeout(timer); resolve(!!r && (r.ok || r.status === 200)); } })
        .catch(function () { if (!done) { done = true; clearTimeout(timer); resolve(false); } });
    });
  }
  function setOffline(v) {
    var changed = v !== offline;
    offline = v;
    if (!v) offlineBarDismissed = false; // a dismissed bar may show again next time we go offline
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
      if (!items.length) return { synced: 0, dropped: 0 };
      var synced = 0, dropped = 0;
      function step(i) {
        if (i >= items.length) return Promise.resolve({ synced: synced, dropped: dropped });
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
          // Server actively rejected it (validation, auth, 500). Retrying
          // forever is what left the "N pending" banner stuck — cap it.
          item.tries = (item.tries || 0) + 1;
          if (item.tries >= 5) {
            dropped++;
            console.error('outbox item dropped after 5 rejections', item.url, res.status);
            return remove(item.id).then(function () { return step(i + 1); });
          }
          return put(item).then(function () { return step(i + 1); });
        }).catch(function () { return { synced: synced, dropped: dropped }; }); // network died — stop
      }
      return step(0);
    }).then(function (r) {
      flushing = false;
      var parts = [];
      if (r.synced > 0) parts.push('סונכרנו ' + r.synced + ' פעולות ✓');
      if (r.dropped > 0) parts.push(r.dropped + ' פעולות נדחו על ידי השרת והוסרו');
      if (parts.length) toast(parts.join(' · '));
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
    return nativeFetch(url, init).then(function (res) {
      // A write just reached the server — we're online, whatever the flag
      // said. Clears a stale banner and drains the outbox immediately.
      if (res && res.ok && offline) setOffline(false);
      return res;
    }).catch(function () { return queueAndAck(); });
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
              // PRG success. fetch already followed the redirect and that GET
              // consumed the one-shot flash message — navigating again would
              // render the page without it. Paint the HTML we already have.
              res.text().then(function (html) {
                history.replaceState(null, '', res.url);
                document.open(); document.write(html); document.close();
              });
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

  // --- online-only forms ----------------------------------------------------
  // Any form NOT marked data-offline needs the server right now (login, batch
  // add, report filters). Offline, block it with a clear message instead of
  // letting the browser navigate to its native error page. Capture phase so we
  // run before the form's own submit handlers.
  document.addEventListener('submit', function (e) {
    if (!offline) return;
    var form = e.target;
    if (!form || form.hasAttribute('data-offline')) return; // queued by bindForms
    e.preventDefault();
    e.stopPropagation();
    toast('אין חיבור לרשת — פעולה זו דורשת אינטרנט');
  }, true);

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
