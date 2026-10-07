/* מימדיון — app-wide UI behaviour: the scroll shell, instant tap feedback,
   double-submit protection and the quick-note sheet. Data/offline concerns
   (outbox, replay, connectivity) stay in offline.js, which loads first. */
(function () {
  'use strict';

  // offline.js re-renders PRG responses with document.write, which re-runs
  // this file in the same window. Window-level listeners from an older run
  // are removed through this cleanup list so they never stack.
  if (window.__mmAppCleanup) window.__mmAppCleanup.forEach(function (fn) { try { fn(); } catch (e) {} });
  var cleanup = window.__mmAppCleanup = [];
  function onWindow(target, type, fn, opts) {
    target.addEventListener(type, fn, opts);
    cleanup.push(function () { target.removeEventListener(type, fn, opts); });
  }

  var root = document.documentElement;
  var main = document.getElementById('app-main');

  // --- The document never scrolls -------------------------------------------
  // Only <main> scrolls (input.css). On iPhone the page itself can still end
  // up offset — after the keyboard closes or an overscroll — which is what
  // left the bottom nav floating mid-screen. Snap it back whenever nobody is
  // typing.
  function isTextEntry(el) {
    if (!el) return false;
    if (el.isContentEditable || el.tagName === 'TEXTAREA') return true;
    if (el.tagName !== 'INPUT') return false;
    return !/^(checkbox|radio|file|button|submit|reset|range|color|image)$/i.test(el.type);
  }
  function resetDocumentScroll() {
    if (isTextEntry(document.activeElement)) return;
    var vv = window.visualViewport;
    if (vv && vv.scale > 1.01) return; // pinch-zoomed on purpose — leave it
    if (window.scrollX || window.scrollY || (vv && (vv.offsetTop > 0.5 || vv.offsetLeft > 0.5))) {
      window.scrollTo(0, 0);
    }
  }
  var resetTimer;
  function scheduleReset() {
    clearTimeout(resetTimer);
    resetTimer = setTimeout(resetDocumentScroll, 90);
  }
  onWindow(document, 'focusout', scheduleReset);
  onWindow(window, 'scroll', scheduleReset, { passive: true });
  if (window.visualViewport) {
    var onViewport = function () {
      var vv = window.visualViewport;
      // iOS does not shrink the layout viewport for the keyboard; bottom
      // sheets use this to sit on top of it instead of underneath.
      var kb = Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop));
      root.style.setProperty('--kb-inset', (kb > 80 ? kb : 0) + 'px');
      scheduleReset();
    };
    onWindow(window.visualViewport, 'resize', onViewport);
    onWindow(window.visualViewport, 'scroll', onViewport);
  }

  // --- Scroll position of <main> survives back/forward ----------------------
  // The browser restores only the document's scroll, not an inner scroller's.
  var scrollKey = 'mm-scroll:' + location.pathname + location.search;
  if (main) {
    onWindow(window, 'pagehide', function () {
      try { sessionStorage.setItem(scrollKey, String(Math.round(main.scrollTop))); } catch (e) {}
    });
    var nav = performance.getEntriesByType ? performance.getEntriesByType('navigation')[0] : null;
    if (nav && nav.type === 'back_forward') {
      try {
        var y = parseInt(sessionStorage.getItem(scrollKey), 10);
        if (y > 0) main.scrollTop = y;
      } catch (e) {}
    }
  }

  // --- Instant feedback: progress bar + busy buttons ------------------------
  var busyTimer;
  // Progress bar only — never blocks the page (see input.css).
  function setBusy(on) {
    root.classList.toggle('is-loading', !!on);
    clearTimeout(busyTimer);
    // Never spin forever (e.g. a download that did not navigate away).
    if (on) busyTimer = setTimeout(function () { root.classList.remove('is-loading'); }, 15000);
  }
  function markButton(btn, on) {
    if (!btn) return;
    if (on) {
      if (btn.classList.contains('is-busy')) return;
      btn.classList.add('is-busy');
      btn.setAttribute('aria-busy', 'true');
      var spinner = document.createElement('span');
      spinner.className = 'loading loading-spinner loading-sm app-spinner';
      spinner.setAttribute('aria-hidden', 'true');
      btn.insertBefore(spinner, btn.firstChild);
    } else {
      btn.classList.remove('is-busy');
      btn.removeAttribute('aria-busy');
      btn.disabled = false;
      var s = btn.querySelector('.app-spinner');
      if (s) s.remove();
    }
  }
  function submitterOf(form, e) {
    return (e && e.submitter) || form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
  }
  // Used by offline.js for forms it submits through fetch.
  function setFormBusy(form, btn, on) {
    form.__mmSubmitting = !!on;
    markButton(btn || submitterOf(form), on);
    setBusy(on);
  }
  function resetAll() {
    setBusy(false);
    document.querySelectorAll('form').forEach(function (f) { f.__mmSubmitting = false; });
    document.querySelectorAll('.is-busy').forEach(function (b) { markButton(b, false); });
    root.classList.remove('is-loading');
    document.querySelectorAll('.is-pressed').forEach(function (a) { a.classList.remove('is-pressed'); });
  }
  // Back/forward cache restores the page exactly as it was left (spinning).
  onWindow(window, 'pageshow', function (e) { if (e.persisted) resetAll(); });

  // Same-origin link navigations: show progress right away so a slow server
  // never looks like a missed tap.
  onWindow(document, 'click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return;
    var url;
    try { url = new URL(a.href, location.href); } catch (err) { return; }
    if (url.origin !== location.origin) return;
    if (url.hash && url.pathname === location.pathname && url.search === location.search) return;
    a.classList.add('is-pressed');
    setBusy(true);
  });

  // Regular (non-offline) forms: one submission per tap, with a spinner.
  // Bubble phase — page scripts and offline.js's online-only guard ran first.
  onWindow(document, 'submit', function (e) {
    var form = e.target;
    if (!form || form.hasAttribute('data-offline') || form.hasAttribute('data-no-busy')) return;
    if (form.__mmSubmitting) { e.preventDefault(); return; }
    if (e.defaultPrevented) return;
    form.__mmSubmitting = true;
    var btn = submitterOf(form, e);
    markButton(btn, true);
    setBusy(true);
    // Disable only after the form data was collected (a disabled submitter
    // would drop its own name/value from the request).
    setTimeout(function () { if (btn) btn.disabled = true; }, 0);
  });

  function toast(text, kind) {
    if (window.MeymadionOffline && window.MeymadionOffline.toast) window.MeymadionOffline.toast(text, kind);
  }

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  window.AppUI = { setBusy: setBusy, markButton: markButton, setFormBusy: setFormBusy, toast: toast, uuid: uuid };

  // --- Quick note sheet -----------------------------------------------------
  var sheet = document.getElementById('qn-sheet');
  if (sheet) initQuickNote(sheet);

  function initQuickNote(sheet) {
    var cfg;
    try { cfg = JSON.parse(document.getElementById('qn-config').textContent); } catch (e) { return; }
    var form = sheet.querySelector('#qn-form');
    var chips = sheet.querySelector('#qn-candidates');
    var picked = sheet.querySelector('#qn-picked');
    var groupSel = sheet.querySelector('#qn-group');
    var text = sheet.querySelector('#qn-text');
    var loc = sheet.querySelector('#qn-location');
    var err = sheet.querySelector('#qn-error');
    var submit = sheet.querySelector('#qn-submit');
    var typeButtons = Array.prototype.slice.call(sheet.querySelectorAll('.qn-type'));
    var fab = document.querySelector('.app-fab');
    var state = {
      group: cfg.groups.length ? cfg.groups[0].id : null,
      number: null,
      type: cfg.fixedType || null,
      requestId: null,
      sending: false,
      reload: false
    };
    var closeToken = 0;

    function currentGroup() {
      for (var i = 0; i < cfg.groups.length; i++) if (cfg.groups[i].id === state.group) return cfg.groups[i];
      return null;
    }
    function nameOf(number) {
      var g = currentGroup();
      if (!g) return '';
      for (var i = 0; i < g.candidates.length; i++) if (g.candidates[i][0] === number) return g.candidates[i][1];
      return '';
    }
    function renderPicked() {
      picked.textContent = state.number === null ? '' : ('מגובש ' + state.number + (nameOf(state.number) ? ' · ' + nameOf(state.number) : ''));
      chips.querySelectorAll('.qn-chip').forEach(function (b) {
        b.setAttribute('aria-checked', String(+b.dataset.number === state.number));
      });
    }
    function renderChips() {
      var g = currentGroup();
      chips.innerHTML = '';
      if (!g || !g.candidates.length) {
        var p = document.createElement('p');
        p.className = 'text-sm opacity-60 col-span-full';
        p.textContent = 'אין מגובשים פעילים בקבוצה';
        chips.appendChild(p);
        return;
      }
      g.candidates.forEach(function (c) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'qn-chip';
        b.dataset.number = c[0];
        b.textContent = c[0];
        b.setAttribute('role', 'radio');
        b.setAttribute('aria-label', 'מגובש ' + c[0] + (c[1] ? ' — ' + c[1] : ''));
        chips.appendChild(b);
      });
      renderPicked();
    }
    function renderTypes() {
      typeButtons.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.type === state.type)); });
    }
    function showError(message, field) {
      err.textContent = message;
      err.classList.remove('hidden');
      if (field) {
        field.classList.remove('qn-invalid');
        void field.offsetWidth; // restart the shake
        field.classList.add('qn-invalid');
        if (field.scrollIntoView) field.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
    function clearError() { err.classList.add('hidden'); }

    chips.addEventListener('click', function (e) {
      var b = e.target.closest('.qn-chip');
      if (!b) return;
      state.number = +b.dataset.number;
      renderPicked();
      clearError();
    });
    typeButtons.forEach(function (b) {
      b.addEventListener('click', function () {
        state.type = b.dataset.type;
        renderTypes();
        clearError();
        // Number and type picked: go straight to typing (opens the keyboard,
        // still inside this tap's user gesture so iOS allows it).
        if (state.number !== null && !text.value) text.focus();
      });
    });
    if (groupSel) {
      groupSel.addEventListener('change', function () {
        state.group = +groupSel.value;
        state.number = null;
        renderChips();
      });
    }

    function open(opts) {
      opts = opts || {};
      state.reload = !!opts.reload;
      if (opts.group !== undefined && opts.group !== null && opts.group !== '') {
        state.group = +opts.group;
        if (groupSel) groupSel.value = String(state.group);
        renderChips();
      }
      if (opts.candidate !== undefined && opts.candidate !== null && opts.candidate !== '') {
        state.number = +opts.candidate;
      }
      renderPicked();
      renderTypes();
      // The page tells us where we are (the selected station), if anywhere.
      if (!loc.value && typeof window.quickNoteLocation === 'function') {
        try { loc.value = window.quickNoteLocation() || ''; } catch (e) {}
      }
      if (!state.requestId) state.requestId = uuid(); // one id per note: a double tap is a duplicate
      clearError();
      closeToken++; // a close still animating must not shut the reopened sheet
      sheet.classList.remove('is-closing', 'to-fab');
      if (!sheet.open) {
        if (sheet.showModal) sheet.showModal(); else sheet.setAttribute('open', '');
      }
    }
    function close(toFab) {
      if (!sheet.open) return;
      var token = ++closeToken;
      sheet.classList.add('is-closing');
      if (toFab && fab) sheet.classList.add('to-fab');
      var done = function () {
        sheet.removeEventListener('animationend', done);
        if (token !== closeToken) return;
        sheet.classList.remove('is-closing', 'to-fab');
        if (sheet.open) sheet.close();
      };
      sheet.addEventListener('animationend', done);
      setTimeout(done, 400); // reduced motion / no animation support
    }
    function celebrate() {
      if (!fab) return;
      fab.classList.remove('is-done');
      void fab.offsetWidth;
      fab.classList.add('is-done');
      setTimeout(function () { fab.classList.remove('is-done'); }, 1800);
    }

    onWindow(document, 'click', function (e) {
      var opener = e.target.closest ? e.target.closest('[data-qn-open]') : null;
      if (opener) {
        e.preventDefault();
        open({
          candidate: opener.getAttribute('data-qn-candidate'),
          group: opener.getAttribute('data-qn-group'),
          reload: opener.hasAttribute('data-qn-reload')
        });
        return;
      }
      if (e.target.closest && e.target.closest('[data-qn-close]')) close(false);
    });
    // Tap on the dimmed backdrop closes; Esc is handled by <dialog> itself.
    sheet.addEventListener('click', function (e) { if (e.target === sheet) close(false); });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (state.sending) return;
      var note = text.value.trim();
      if (state.number === null) return showError('בחרו מגובש', sheet.querySelector('#qn-candidate-field'));
      if (!state.type) return showError('בחרו סוג הערה', sheet.querySelector('#qn-type-field'));
      if (!note) { showError('כתבו את ההערה', text); text.focus(); return; }
      clearError();
      state.sending = true;
      markButton(submit, true);
      var payload = {
        group: state.group, subject: state.number, type: state.type,
        text: note, location: loc.value.trim(), request_id: state.requestId
      };
      fetch('/notes/quick', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Request-Id': state.requestId },
        body: JSON.stringify(payload)
      }).then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      }).then(function (r) {
        if (!r.ok || !r.data.success) throw new Error(r.data.message || 'השמירה נכשלה');
        toast(r.data.message || 'ההערה נשמרה ✓');
        text.value = '';
        loc.value = '';
        state.type = cfg.fixedType || null;
        state.requestId = null;
        close(true);
        celebrate();
        // Pages that list notes show the new one (unless it is still queued).
        if (state.reload && !r.data.queued) setTimeout(function () { location.reload(); }, 700);
      }).catch(function (error) {
        showError(error && error.message && !/JSON|fetch|network/i.test(error.message)
          ? error.message : 'השמירה נכשלה — נסו שוב');
      }).then(function () {
        state.sending = false;
        markButton(submit, false);
      });
    });

    renderChips();
    renderTypes();
    window.QuickNote = { open: open, close: close };
  }

  // --- File pickers that upload on choose -----------------------------------
  // <form data-file-upload> with its file input inside a .btn label: picking
  // a file sends it right away (one tap less on a phone), with a spinner on
  // the label. Offline, offline.js blocks the submit and shows why.
  document.querySelectorAll('form[data-file-upload]').forEach(function (form) {
    var input = form.querySelector('input[type="file"]');
    if (!input) return;
    var label = input.closest('label');
    form.addEventListener('submit', function () { markButton(label, true); });
    input.addEventListener('change', function () {
      if (!input.files || !input.files.length) return;
      if (form.requestSubmit) {
        form.requestSubmit();
      } else {
        var ev = new Event('submit', { bubbles: true, cancelable: true });
        if (form.dispatchEvent(ev)) form.submit();
      }
      // Blocked: let the same file be picked again.
      setTimeout(function () { if (!form.__mmSubmitting) input.value = ''; }, 0);
    });
  });

  // --- "Already interviewed" sheet ------------------------------------------
  var piSheet = document.getElementById('pi-sheet');
  if (piSheet) initPriorInterviews(piSheet);

  function initPriorInterviews(sheet) {
    var storeKey = 'mm-pi-seen:' + (sheet.getAttribute('data-scope') || '');
    var keys = (sheet.getAttribute('data-keys') || '').split(/\s+/).filter(Boolean);
    var closeToken = 0;

    function seenKeys() {
      try { return JSON.parse(localStorage.getItem(storeKey) || '[]') || []; } catch (e) { return []; }
    }
    function markSeen() {
      try { localStorage.setItem(storeKey, JSON.stringify(keys)); } catch (e) {}
    }
    function open() {
      closeToken++; // a close still animating must not shut the reopened sheet
      sheet.classList.remove('is-closing');
      if (!sheet.open) {
        if (sheet.showModal) sheet.showModal(); else sheet.setAttribute('open', '');
      }
      markSeen();
    }
    function close() {
      if (!sheet.open) return;
      var token = ++closeToken;
      sheet.classList.add('is-closing');
      var done = function () {
        sheet.removeEventListener('animationend', done);
        if (token !== closeToken) return;
        sheet.classList.remove('is-closing');
        if (sheet.open) sheet.close();
      };
      sheet.addEventListener('animationend', done);
      setTimeout(done, 400); // reduced motion / no animation support
    }

    onWindow(document, 'click', function (e) {
      if (!e.target.closest) return;
      if (e.target.closest('[data-pi-open]')) { e.preventDefault(); open(); return; }
      if (e.target.closest('[data-pi-close]')) close();
    });
    sheet.addEventListener('click', function (e) { if (e.target === sheet) close(); });

    // Pops up by itself for a match this phone has not seen yet (a new sync,
    // or a candidate who was just named), and right after the admin synced.
    // It opens with the page, never later: a sheet that slides in after the
    // first paint lands under a tap meant for something else.
    var seen = seenKeys();
    var fresh = keys.some(function (k) { return seen.indexOf(k) === -1; });
    if ((sheet.hasAttribute('data-open-now') || fresh) && !document.querySelector('dialog[open]')) open();
    window.PriorInterviews = { open: open, close: close };
  }
})();
