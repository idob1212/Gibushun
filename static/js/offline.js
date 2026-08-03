(function () {
  'use strict';

  // The PRG path in bindForms re-renders via document.write, which re-executes
  // this file into the SAME window. Window-level generation state keeps that
  // from stacking fetch wrappers, heartbeats and window listeners.
  var GEN = window.__mmOfflineGen = (window.__mmOfflineGen || 0) + 1;
  function isCurrent() { return GEN === window.__mmOfflineGen; }

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

  // "dead" items were rejected by the server (bad choice, stale CSRF, 5×4xx/5xx).
  // They are kept — visibly — instead of vanishing with a "synced" toast.
  function pendingItems() { return allItems().then(function (a) { return a.filter(function (i) { return !i.dead; }); }); }
  function deadItems() { return allItems().then(function (a) { return a.filter(function (i) { return i.dead; }); }); }
  function pendingCount() { return pendingItems().then(function (a) { return a.length; }); }
  function clearDead() {
    return deadItems().then(function (items) {
      return Promise.all(items.map(function (i) { return remove(i.id); }));
    });
  }

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
  var barKind = null; // 'offline' | 'login' | 'dead' — drives color and ✕ behavior
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
      if (barKind === 'dead') {
        // Dismissing the rejected-items bar is an explicit acknowledgment —
        // the items are deleted, so it never nags again.
        if (!window.confirm('להסיר את הפעולות שנדחו? לא ניתן יהיה לשחזר אותן מהמכשיר.')) return;
        clearDead().then(function () { hideOfflineBar(); refreshStatus(); });
        return;
      }
      offlineBarDismissed = true; // stays hidden until the condition changes
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
  function showOfflineBar(text, kind) {
    var b = ensureOfflineBar();
    if (kind !== barKind) offlineBarDismissed = false; // new condition — show again
    barKind = kind;
    b.style.background = kind === 'dead' ? '#dc2626' : '#b45309';
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
  // Window listeners survive document.write (unlike document listeners), so
  // stale generations must go inert instead of fighting the current one.
  window.addEventListener('resize', function () { if (isCurrent()) repositionOfflineBar(); });
  window.addEventListener('orientationchange', function () { if (isCurrent()) repositionOfflineBar(); });

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
    allItems().then(function (all) {
      var pending = 0, dead = 0;
      all.forEach(function (i) { if (i.dead) dead++; else pending++; });
      if (needLogin && pending) {
        showOfflineBar('ההתחברות פגה — התחבר מחדש כדי לסנכרן ' + pending + ' פעולות ממתינות', 'login');
      } else if (offline) {
        showOfflineBar(pending ? ('אופליין — ' + pending + ' פעולות ממתינות לסנכרון') : 'אופליין — נתונים יישמרו במכשיר', 'offline');
      } else if (dead) {
        showOfflineBar(dead + ' פעולות נדחו על ידי השרת ולא נשמרו — בדוק והזן אותן מחדש', 'dead');
      } else {
        hideOfflineBar();
      }
    });
  }

  // --- Connectivity truth ---------------------------------------------------
  // iOS Safari fires 'online'/'offline' unreliably and navigator.onLine lies,
  // so we actively probe the server and treat a positive probe as the source of
  // truth. This is what clears a "stuck" offline banner once the net is back.
  var offline = !navigator.onLine;
  var needLogin = false; // last replay bounced to /login — items are kept
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
  // Form endpoints where success is ALWAYS a redirect (PRG). A plain 200 from
  // one of these is a re-render with errors (bad choice, stale CSRF) — a
  // rejection, not a save. /new-review is absent on purpose: its success path
  // renders 200 directly, so 200 must keep counting as success there.
  var PRG_FORM_PATHS = ['/add-all', '/interview/', '/final-grade/', '/final-status/', '/new-note'];
  function pathOf(u) {
    try { return new URL(u, location.origin).pathname; } catch (e) { return u; }
  }

  var flushing = false;
  function flush() {
    if (flushing || offline) return Promise.resolve();
    flushing = true;
    needLogin = false; // re-verify each drain; a re-login may have fixed it
    return pendingItems().then(function (items) {
      if (!items.length) return { synced: 0, dead: 0 };
      var synced = 0, dead = 0;
      function step(i) {
        if (i >= items.length) return Promise.resolve({ synced: synced, dead: dead });
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
          // Session expired: the POST bounced to the login page. That page is
          // a 200, which the old code counted as "synced" — silently deleting
          // the data. Keep everything and stop; the banner asks for a login.
          if (pathOf(res.url) === '/login') {
            needLogin = true;
            return { synced: synced, dead: dead };
          }
          if (res.ok) {
            var rejected = item.kind === 'form' && !res.redirected &&
              PRG_FORM_PATHS.indexOf(pathOf(item.url)) !== -1;
            if (!rejected) {
              synced++;
              return remove(item.id).then(function () { return step(i + 1); });
            }
            // Deterministic rejection — same payload gives the same answer,
            // so no retries. Dead-letter it where the user can see it.
            item.dead = true;
            dead++;
            return put(item).then(function () { return step(i + 1); });
          }
          // 4xx/5xx may be transient (worker hiccup) — retry a few times.
          item.tries = (item.tries || 0) + 1;
          if (item.tries >= 5) {
            item.dead = true;
            dead++;
            console.error('outbox item dead-lettered after 5 rejections', item.url, res.status);
          }
          return put(item).then(function () { return step(i + 1); });
        }).catch(function () { return { synced: synced, dead: dead }; }); // network died — stop
      }
      return step(0);
    }).then(function (r) {
      flushing = false;
      var parts = [];
      if (r.synced > 0) parts.push('סונכרנו ' + r.synced + ' פעולות ✓');
      if (r.dead > 0) parts.push(r.dead + ' פעולות נדחו על ידי השרת');
      if (parts.length) toast(parts.join(' · '));
      refreshStatus();
      // View pages (e.g. the scores board) opt in to a reload after a sync,
      // so freshly synced reviews actually appear without a manual refresh.
      if (r.synced > 0 && document.querySelector('[data-refresh-on-sync]')) {
        setTimeout(function () { location.reload(); }, 1500);
      }
    }).catch(function () { flushing = false; });
  }

  // --- fetch wrapper for JSON write endpoints -------------------------------
  // The true native fetch is stashed on window once: a re-executed script must
  // not capture the previous generation's wrapper as its "native", or wrappers
  // nest one level deeper on every PRG re-render.
  var nativeFetch = window.__mmNativeFetch = window.__mmNativeFetch || window.fetch.bind(window);
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
        // Native validation still works under novalidate when called by hand.
        // Without this, an offline submit with an empty required field is
        // queued, then silently rejected by the server on replay.
        if (!form.checkValidity()) { form.reportValidity(); return; }
        // A page can arm a confirmation (e.g. "you are about to overwrite an
        // existing interview") by setting data-confirm on the form.
        var confirmMsg = form.getAttribute('data-confirm');
        if (confirmMsg && !window.confirm(confirmMsg)) return;
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
  window.addEventListener('online', function () { if (isCurrent()) recheck(); });
  window.addEventListener('offline', function () { if (isCurrent()) setOffline(true); });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') recheck();
  });

  // Heartbeat: periodically reconcile so a returned connection clears the
  // offline banner (and drains the outbox) even if no 'online' event fired.
  // setInterval survives document.write — clear the previous generation's.
  if (window.__mmHeartbeat) clearInterval(window.__mmHeartbeat);
  window.__mmHeartbeat = setInterval(recheck, 15000);

  // --- logout guard ----------------------------------------------------------
  // Logging out with unsynced items would replay them under the NEXT login —
  // possibly a different group. Warn, and clear the outbox on a confirmed
  // logout so nothing leaks across accounts. (document-level listener: dies
  // with the document, so PRG re-renders never stack it.)
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href$="/logout"]') : null;
    if (!a) return;
    e.preventDefault();
    e.stopPropagation();
    allItems().then(function (all) {
      var pending = all.filter(function (i) { return !i.dead; }).length;
      if (pending && !window.confirm(pending + ' פעולות עדיין לא סונכרנו ויימחקו אם תתנתק. להתנתק בכל זאת?')) return;
      Promise.all(all.map(function (i) { return remove(i.id); })).then(
        function () { location.href = a.href; },
        function () { location.href = a.href; }
      );
    });
  }, true);

  document.addEventListener('DOMContentLoaded', function () {
    bindForms();
    refreshStatus();   // paint immediately from the current best guess
    recheck();         // then confirm against the server
    // Always try to drain the outbox on load. setOffline(false) only flushes
    // on an offline→online EDGE, so items queued in a previous page load
    // never synced when the app reopened already-online.
    flush();
  });

  // Small API for pages that want to reflect the outbox state (e.g. the
  // scores board shows "pending sync"), plus dead-letter inspection.
  window.MeymadionOffline = { pendingCount: pendingCount, deadItems: deadItems, clearDead: clearDead };
})();
