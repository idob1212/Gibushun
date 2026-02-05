/* offline-manager.js - Local-first data layer for Gibushun PWA
 * Phase 2+ implementation: IndexedDB schema, data sync, dropdown merge, form interception
 */

(function() {
  'use strict';

  // ─── IndexedDB Schema (Dexie) ──────────────────────────────────────────────
  var db = new Dexie('gibushun-offline');
  db.version(1).stores({
    syncQueue:    '++id, type, status, createdAt, groupId',
    candidates:   'id, groupId',
    stations:     'id, type',
    reviews:      '++localId, subjectId, station, [subjectId+station]',
    notes:        '++localId, subjectId',
    interviews:   'subjectId',
    authState:    'key',
    meta:         'key'
  });

  // Make db globally accessible
  window.offlineDb = db;

  // ─── UUID Generator ────────────────────────────────────────────────────────
  function uuid() {
    if (crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      var r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }
  window.offlineUuid = uuid;

  // ─── Toast Helper ──────────────────────────────────────────────────────────
  function showToast(message, duration) {
    duration = duration || 3000;
    var container = document.getElementById('toast-container');
    if (!container) return;
    var toast = document.createElement('div');
    toast.className = 'offline-toast';
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(function() {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      setTimeout(function() { toast.remove(); }, 300);
    }, duration);
  }
  window.showOfflineToast = showToast;

  // ─── Sync Status Bar ──────────────────────────────────────────────────────
  function updateSyncBar(status) {
    var bar = document.getElementById('sync-status-bar');
    if (!bar) return;
    bar.className = status; // 'online', 'offline', 'syncing', 'pending'
  }
  window.updateSyncBar = updateSyncBar;

  // ─── Check online status on load ──────────────────────────────────────────
  function updateOnlineStatus() {
    if (navigator.onLine) {
      db.syncQueue.where('status').equals('pending').count().then(function(count) {
        updateSyncBar(count > 0 ? 'pending' : 'online');
      });
    } else {
      updateSyncBar('offline');
    }
  }

  window.addEventListener('online', function() {
    updateOnlineStatus();
    if (window.syncEngine && window.syncEngine.drain) {
      window.syncEngine.drain();
    }
  });
  window.addEventListener('offline', function() { updateSyncBar('offline'); });

  // ─── Initial data load ────────────────────────────────────────────────────
  function loadOfflineBundle() {
    return fetch('/api/offline-bundle', { credentials: 'include' })
      .then(function(response) {
        if (!response.ok) return null;
        return response.json();
      })
      .then(function(bundle) {
        if (!bundle) return;

        // Store auth state
        db.authState.put({ key: 'current', userId: bundle.auth.userId, userName: bundle.auth.userName, isAdmin: bundle.auth.isAdmin });

        // Store candidates
        if (bundle.candidates && bundle.candidates.length > 0) {
          db.candidates.bulkPut(bundle.candidates.map(function(c) {
            return { id: c.id, name: c.name, groupId: c.groupId, status: c.status };
          }));
        }

        // Store stations
        var stationRecords = [];
        (bundle.stations.cognitive || []).forEach(function(s) {
          stationRecords.push({ id: 'cognitive:' + s, name: s, type: 'cognitive' });
        });
        (bundle.stations.physical || []).forEach(function(s) {
          stationRecords.push({ id: 'physical:' + s, name: s, type: 'physical' });
        });
        (bundle.stations.counter || []).forEach(function(s) {
          stationRecords.push({ id: 'counter:' + s, name: s, type: 'counter' });
        });
        if (stationRecords.length > 0) {
          db.stations.bulkPut(stationRecords);
        }

        // Store reviews
        if (bundle.reviews && bundle.reviews.length > 0) {
          db.reviews.clear().then(function() {
            db.reviews.bulkAdd(bundle.reviews.map(function(r) {
              return {
                serverId: r.id, subjectId: r.subjectId, station: r.station,
                grade: r.grade, note: r.note, counterValue: r.counterValue
              };
            }));
          });
        }

        // Store notes
        if (bundle.notes && bundle.notes.length > 0) {
          db.notes.clear().then(function() {
            db.notes.bulkAdd(bundle.notes.map(function(n) {
              return {
                serverId: n.id, subjectId: n.subjectId, type: n.type,
                text: n.text, location: n.location, date: n.date
              };
            }));
          });
        }

        // Store interviews
        if (bundle.interviews && bundle.interviews.length > 0) {
          db.interviews.bulkPut(bundle.interviews);
        }

        // Store static options
        db.meta.put({ key: 'staticOptions', value: bundle.staticOptions });

        // Request persistent storage
        if (navigator.storage && navigator.storage.persist) {
          navigator.storage.persist();
        }

        console.log('Offline bundle loaded successfully');
      })
      .catch(function(err) {
        console.log('Failed to load offline bundle:', err);
      });
  }

  // ─── Pre-cache all pages via Service Worker ───────────────────────────────
  function precachePages() {
    fetch('/api/offline/page-list', { credentials: 'include' })
      .then(function(response) { return response.json(); })
      .then(function(pages) {
        if (navigator.serviceWorker && navigator.serviceWorker.controller) {
          navigator.serviceWorker.controller.postMessage({
            type: 'PRECACHE_PAGES',
            urls: pages
          });
          console.log('Sent', pages.length, 'pages to SW for pre-caching');
        }
      })
      .catch(function(err) {
        console.log('Failed to fetch page list for pre-caching:', err);
      });
  }

  // ─── Merge local candidates into server-rendered dropdowns ────────────────
  function mergeDropdowns() {
    db.authState.get('current').then(function(auth) {
      if (!auth) return;
      var groupId = auth.userId;
      if (groupId === 0) return; // Admin doesn't need local candidate merge

      db.candidates.where('groupId').equals(groupId).toArray().then(function(localCandidates) {
        var selects = document.querySelectorAll('select[name="subject"], select[name="id"]');
        selects.forEach(function(select) {
          var existingIds = new Set();
          for (var i = 0; i < select.options.length; i++) {
            existingIds.add(select.options[i].value);
          }
          localCandidates.forEach(function(c) {
            if (c.status === "פרש") return;
            var num = c.id.split('/')[1];
            if (!existingIds.has(num)) {
              var opt = new Option(num, num);
              select.add(opt);
            }
          });
          // Sort options numerically
          var options = Array.from(select.options);
          options.sort(function(a, b) {
            return parseInt(a.value) - parseInt(b.value);
          });
          select.innerHTML = '';
          options.forEach(function(opt) { select.add(opt); });
        });
      });
    });
  }

  // ─── Intercept AJAX GET endpoints when offline ────────────────────────────
  var originalFetch = window.fetch;
  window.fetch = function(url, options) {
    if (!navigator.onLine && typeof url === 'string') {
      var subjectMatch = url.match(/\/subjects\/(\d+)/);
      if (subjectMatch) {
        var gId = parseInt(subjectMatch[1]);
        return db.candidates.where('groupId').equals(gId).toArray().then(function(candidates) {
          var subjects = candidates
            .filter(function(c) { return c.status !== "פרש"; })
            .map(function(c) { return { id: parseInt(c.id.split('/')[1]) }; })
            .sort(function(a, b) { return a.id - b.id; });
          return new Response(JSON.stringify({ subjects: subjects }), {
            headers: { 'Content-Type': 'application/json' }
          });
        });
      }

      var physMatch = url.match(/\/physicals\/(\d+)/);
      if (physMatch) {
        return db.stations.where('type').equals('physical').toArray().then(function(stations) {
          return new Response(JSON.stringify({
            stations: stations.map(function(s) { return { id: s.name }; })
          }), { headers: { 'Content-Type': 'application/json' } });
        });
      }

      var stationsMatch = url.match(/\/stations\/(\d+)/);
      if (stationsMatch) {
        return db.stations.toArray().then(function(stations) {
          return new Response(JSON.stringify({
            stations: stations.map(function(s) { return { id: s.name }; })
          }), { headers: { 'Content-Type': 'application/json' } });
        });
      }

      var reviewsMatch = url.match(/\/get-station-reviews\/(.+)/);
      if (reviewsMatch) {
        var stationName = decodeURIComponent(reviewsMatch[1]);
        return db.authState.get('current').then(function(auth) {
          if (!auth) return new Response(JSON.stringify({ reviews: [] }));
          return db.candidates.where('groupId').equals(auth.userId).toArray().then(function(candidates) {
            var activeCandidates = candidates
              .filter(function(c) { return c.status !== "פרש"; })
              .map(function(c) { return parseInt(c.id.split('/')[1]); })
              .sort(function(a, b) { return a - b; });

            return db.reviews.where('station').equals(stationName).toArray().then(function(reviews) {
              var reviewMap = {};
              reviews.forEach(function(r) {
                var num = r.subjectId.split('/')[1];
                reviewMap[num] = r;
              });

              var result = activeCandidates.map(function(candidateId) {
                var r = reviewMap[String(candidateId)];
                return {
                  subject: candidateId,
                  counter_value: r ? (r.counterValue || 0) : 0,
                  note: r ? (r.note || '') : ''
                };
              });

              return new Response(JSON.stringify({ reviews: result }), {
                headers: { 'Content-Type': 'application/json' }
              });
            });
          });
        });
      }
    }

    return originalFetch.apply(this, arguments);
  };

  // ─── Form Interception ────────────────────────────────────────────────────

  // URL to operation type mapping
  var FORM_URL_MAP = {
    '/add-candidate': 'add-candidate',
    '/add-candidate-batch': 'add-candidate-batch',
    '/new-review': 'new-review',
    '/add-all': 'group-review',
    '/interview/': 'interview',
    '/new-note': 'new-note'
  };

  function serializeForm(form) {
    var data = {};
    var formData = new FormData(form);
    formData.forEach(function(value, key) {
      if (key === 'csrf_token') return;
      if (data[key]) {
        if (!Array.isArray(data[key])) data[key] = [data[key]];
        data[key].push(value);
      } else {
        data[key] = value;
      }
    });
    return data;
  }

  function handleFormOffline(form, operationType, formData) {
    var clientId = uuid();
    var payload = formData;

    // Optimistic local updates
    return db.authState.get('current').then(function(auth) {
      if (!auth) return;
      var groupId = auth.userId;

      if (operationType === 'add-candidate') {
        var candidateId = groupId + '/' + (payload.id || payload.number || '').toString().trim();
        db.candidates.put({
          id: candidateId,
          name: payload.name || '',
          groupId: groupId,
          status: null
        });
        payload.number = (payload.id || payload.number || '').toString().trim();
      }

      if (operationType === 'new-review') {
        db.reviews.add({
          subjectId: groupId + '/' + payload.subject,
          station: payload.station,
          grade: parseFloat(payload.grade),
          note: payload.note || ''
        });
      }

      if (operationType === 'new-note') {
        db.notes.add({
          subjectId: groupId + '/' + payload.subject,
          type: payload.type,
          text: payload.text || '',
          location: payload.location || '',
          date: new Date().toLocaleString('he-IL')
        });
      }

      if (operationType === 'interview') {
        db.interviews.put({
          subjectId: groupId + '/' + payload.id,
          interviewer: payload.interviewer || '',
          interviewGrade: payload.grade || '',
          interviewNote: payload.note || '',
          tashProb: payload.tash || '',
          medicalProb: payload.medical || ''
        });
      }

      if (operationType === 'group-review') {
        var station = payload.station;
        var grades = Array.isArray(payload.grade) ? payload.grade : [payload.grade];
        var notes = Array.isArray(payload.note) ? payload.note : [payload.note];
        var reviewItems = grades.map(function(g, i) {
          return { grade: g, note: notes[i] || '' };
        });
        payload = { station: station, odt: payload.odt || '', reviews: reviewItems };
      }

      // Add to sync queue
      return db.syncQueue.add({
        clientId: clientId,
        type: operationType,
        payload: payload,
        groupId: groupId,
        status: 'pending',
        createdAt: Date.now(),
        attempts: 0,
        lastError: null
      });
    }).then(function() {
      showToast('נשמר מקומית');
      updateOnlineStatus();
    });
  }

  // Listen for form submissions
  document.addEventListener('submit', function(e) {
    var form = e.target;
    if (!form || form.tagName !== 'FORM') return;

    var action = form.getAttribute('action') || window.location.pathname;
    var operationType = null;

    for (var url in FORM_URL_MAP) {
      if (action === url || action.startsWith(url)) {
        operationType = FORM_URL_MAP[url];
        break;
      }
    }

    if (!operationType) return; // Not a form we intercept

    if (!navigator.onLine) {
      e.preventDefault();
      var formData = serializeForm(form);
      handleFormOffline(form, operationType, formData).then(function() {
        // Show success - redirect to same page
        window.location.reload();
      });
    } else {
      // Online: also add to queue as backup, but let form submit normally
      var formData = serializeForm(form);
      db.authState.get('current').then(function(auth) {
        if (!auth) return;
        // Just save to queue, the normal form submission will handle the server side
        // We don't need to add to queue when online since the form submits directly
      });
    }
  });

  // ─── Intercept AJAX POST endpoints when offline ───────────────────────────

  // Counter review debounce
  var counterDebounceTimer = null;

  var originalXHROpen = XMLHttpRequest.prototype.open;
  var originalXHRSend = XMLHttpRequest.prototype.send;

  // Also intercept fetch POST for offline
  var baseFetch = window.fetch;
  window.fetch = function(url, options) {
    options = options || {};
    if (!navigator.onLine && options.method && options.method.toUpperCase() === 'POST') {
      var urlStr = typeof url === 'string' ? url : url.toString();

      // Counter reviews
      if (urlStr.includes('/update-counter-reviews')) {
        var body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
        return db.authState.get('current').then(function(auth) {
          if (!auth) return;
          return db.syncQueue.add({
            clientId: uuid(),
            type: 'counter-review',
            payload: body,
            groupId: auth.userId,
            status: 'pending',
            createdAt: Date.now(),
            attempts: 0,
            lastError: null
          });
        }).then(function() {
          showToast('נשמר מקומית');
          updateOnlineStatus();
          return new Response(JSON.stringify({ success: true, message: 'נשמר מקומית' }), {
            headers: { 'Content-Type': 'application/json' }
          });
        });
      }

      // Circles finished
      if (urlStr.includes('/circles/finished')) {
        var body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
        return db.authState.get('current').then(function(auth) {
          if (!auth) return;
          return db.syncQueue.add({
            clientId: uuid(),
            type: 'circles-finished',
            payload: body,
            groupId: auth.userId,
            status: 'pending',
            createdAt: Date.now(),
            attempts: 0,
            lastError: null
          });
        }).then(function() {
          showToast('נשמר מקומית');
          updateOnlineStatus();
          return new Response(JSON.stringify({ success: true, message: 'נשמר מקומית' }), {
            headers: { 'Content-Type': 'application/json' }
          });
        });
      }

      // Add review candidate (AJAX single review)
      if (urlStr.includes('/add-review-candidate')) {
        var formBody = options.body;
        var payload = {};
        if (formBody instanceof FormData) {
          formBody.forEach(function(val, key) { if (key !== 'csrf_token') payload[key] = val; });
        }
        return db.authState.get('current').then(function(auth) {
          if (!auth) return;
          return db.syncQueue.add({
            clientId: uuid(),
            type: 'add-review-candidate',
            payload: payload,
            groupId: auth.userId,
            status: 'pending',
            createdAt: Date.now(),
            attempts: 0,
            lastError: null
          });
        }).then(function() {
          showToast('נשמר מקומית');
          return new Response('User updated', { headers: { 'Content-Type': 'text/plain' } });
        });
      }

      // Batch add candidates
      if (urlStr.includes('/add-candidate-batch')) {
        var body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
        return db.authState.get('current').then(function(auth) {
          if (!auth) return;
          return db.syncQueue.add({
            clientId: uuid(),
            type: 'add-candidate-batch',
            payload: body,
            groupId: auth.userId,
            status: 'pending',
            createdAt: Date.now(),
            attempts: 0,
            lastError: null
          });
        }).then(function() {
          showToast('נשמר מקומית');
          return new Response(JSON.stringify({ success: true }), {
            headers: { 'Content-Type': 'application/json' }
          });
        });
      }
    }

    return baseFetch.apply(this, arguments);
  };

  // ─── Initialize on page load ──────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function() {
    updateOnlineStatus();

    // Only load bundle if user is authenticated (check for logout link presence)
    var logoutLink = document.getElementById('logout-link');
    if (logoutLink) {
      // Load bundle and precache (only when online)
      if (navigator.onLine) {
        loadOfflineBundle();
        precachePages();
      }
      // Always merge local data into dropdowns
      mergeDropdowns();

      // Logout guard
      logoutLink.addEventListener('click', function(e) {
        e.preventDefault();
        db.syncQueue.where('status').equals('pending').count().then(function(count) {
          if (count > 0) {
            if (confirm('יש ' + count + ' פריטים שטרם סונכרנו. בטוח שברצונך להתנתק?')) {
              window.location.href = logoutLink.getAttribute('data-href');
            }
          } else {
            window.location.href = logoutLink.getAttribute('data-href');
          }
        });
      });
    }
  });

  // ─── Listen for SW messages ───────────────────────────────────────────────
  if (navigator.serviceWorker) {
    navigator.serviceWorker.addEventListener('message', function(event) {
      if (event.data && event.data.type === 'TRIGGER_SYNC') {
        if (window.syncEngine && window.syncEngine.drain) {
          window.syncEngine.drain();
        }
      }
    });
  }

})();
