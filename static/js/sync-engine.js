/* sync-engine.js - Queue drain logic for Gibushun PWA
 * Processes pending sync items oldest-first with exponential backoff
 * Triggered by: online event, 30s polling, page load, Background Sync API
 */

(function() {
  'use strict';

  var POLL_INTERVAL = 30000; // 30 seconds
  var MAX_RETRIES = 5;
  var isSyncing = false;
  var pollTimer = null;

  function getDb() {
    return window.offlineDb;
  }

  // ─── Queue Drain ──────────────────────────────────────────────────────────
  async function drain() {
    if (isSyncing || !navigator.onLine) return;
    isSyncing = true;

    var db = getDb();
    if (!db) { isSyncing = false; return; }

    try {
      var pending = await db.syncQueue
        .where('status').equals('pending')
        .sortBy('createdAt');

      if (pending.length === 0) {
        isSyncing = false;
        if (window.updateSyncBar) window.updateSyncBar('online');
        return;
      }

      if (window.updateSyncBar) window.updateSyncBar('syncing');

      var successCount = 0;
      var failCount = 0;

      for (var i = 0; i < pending.length; i++) {
        var item = pending[i];

        if (item.attempts >= MAX_RETRIES) {
          await db.syncQueue.update(item.id, { status: 'failed' });
          failCount++;
          continue;
        }

        // Mark as syncing
        await db.syncQueue.update(item.id, { status: 'syncing', attempts: item.attempts + 1 });

        try {
          var response = await fetch('/api/sync/' + item.type, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              clientId: item.clientId,
              payload: item.payload
            })
          });

          if (!response.ok) {
            throw new Error('Server returned ' + response.status);
          }

          var result = await response.json();

          if (result.status === 'ok' || result.status === 'duplicate') {
            await db.syncQueue.update(item.id, { status: 'synced' });
            successCount++;
          } else if (result.status === 'error') {
            await db.syncQueue.update(item.id, {
              status: 'pending',
              lastError: result.message
            });
            failCount++;
          }
        } catch (err) {
          // Network error - put back to pending with exponential backoff
          var backoffMs = Math.min(1000 * Math.pow(2, item.attempts), 30000);
          await db.syncQueue.update(item.id, {
            status: 'pending',
            lastError: err.message
          });
          failCount++;

          // If we lost connectivity mid-sync, stop
          if (!navigator.onLine) break;
        }
      }

      // Clean up synced items
      await db.syncQueue.where('status').equals('synced').delete();

      // If we synced anything successfully, refresh the bundle
      if (successCount > 0 && navigator.onLine) {
        refreshBundle();
      }

      // Update status bar
      var remainingPending = await db.syncQueue.where('status').equals('pending').count();
      if (remainingPending > 0) {
        if (window.updateSyncBar) window.updateSyncBar('pending');
      } else {
        if (window.updateSyncBar) window.updateSyncBar('online');
      }

      if (successCount > 0) {
        if (window.showOfflineToast) {
          window.showOfflineToast('סונכרן בהצלחה (' + successCount + ' פריטים)');
        }
      }

      if (failCount > 0 && successCount === 0) {
        if (window.showOfflineToast) {
          window.showOfflineToast('שגיאת סנכרון - ננסה שוב');
        }
      }

    } catch (err) {
      console.error('Sync drain error:', err);
    }

    isSyncing = false;
  }

  // ─── Refresh offline bundle after successful sync ─────────────────────────
  function refreshBundle() {
    var db = getDb();
    if (!db) return;

    fetch('/api/offline-bundle', { credentials: 'include' })
      .then(function(response) {
        if (!response.ok) return null;
        return response.json();
      })
      .then(function(bundle) {
        if (!bundle) return;

        // Refresh candidates
        if (bundle.candidates && bundle.candidates.length > 0) {
          db.candidates.clear().then(function() {
            db.candidates.bulkPut(bundle.candidates.map(function(c) {
              return { id: c.id, name: c.name, groupId: c.groupId, status: c.status };
            }));
          });
        }

        // Refresh reviews
        if (bundle.reviews) {
          db.reviews.clear().then(function() {
            db.reviews.bulkAdd(bundle.reviews.map(function(r) {
              return {
                serverId: r.id, subjectId: r.subjectId, station: r.station,
                grade: r.grade, note: r.note, counterValue: r.counterValue
              };
            }));
          });
        }

        // Refresh notes
        if (bundle.notes) {
          db.notes.clear().then(function() {
            db.notes.bulkAdd(bundle.notes.map(function(n) {
              return {
                serverId: n.id, subjectId: n.subjectId, type: n.type,
                text: n.text, location: n.location, date: n.date
              };
            }));
          });
        }

        console.log('Offline bundle refreshed after sync');
      })
      .catch(function(err) {
        console.log('Failed to refresh bundle:', err);
      });
  }

  // ─── Polling ──────────────────────────────────────────────────────────────
  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(function() {
      if (navigator.onLine) {
        drain();
      }
    }, POLL_INTERVAL);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // ─── Background Sync Registration (progressive enhancement) ──────────────
  function registerBackgroundSync() {
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker.ready.then(function(reg) {
      if (reg.sync) {
        reg.sync.register('sync-queue').catch(function() {
          // Background Sync not supported, polling handles it
        });
      }
    });
  }

  // ─── Initialize ───────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function() {
    // Initial drain attempt
    setTimeout(function() { drain(); }, 2000);

    // Start polling
    startPolling();

    // Register background sync if available
    registerBackgroundSync();
  });

  // Re-drain when coming back online
  window.addEventListener('online', function() {
    setTimeout(function() { drain(); }, 1000);
    registerBackgroundSync();
  });

  // ─── Public API ───────────────────────────────────────────────────────────
  window.syncEngine = {
    drain: drain,
    startPolling: startPolling,
    stopPolling: stopPolling
  };

})();
