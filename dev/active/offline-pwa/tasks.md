# Implementation Tasks

## Phase 1: PWA Foundation
- [x] Create static/manifest.json
- [x] Generate PWA icons (192x192, 512x512) from logo
- [x] Create static/js/sw.js (service worker)
- [x] Add Flask routes: /sw.js, /manifest.json, /api/offline/page-list
- [x] Modify header.html: remove CDN refs, add manifest link, Apple PWA meta, SW registration
- [x] Remove CDN references from all 33 templates

## Phase 2: Local-first Data Layer
- [x] Vendor Dexie.js v3 (81KB)
- [x] Create static/js/offline-manager.js with IndexedDB schema
- [x] Add /api/offline-bundle Flask endpoint
- [x] Implement dropdown merge logic
- [x] Implement AJAX GET endpoint interception (subjects, physicals, stations, get-station-reviews)

## Phase 3: Sync Queue + Server API
- [x] Create static/js/sync-engine.js
- [x] Add SyncLog model to main.py
- [x] Add POST /api/sync/<type> endpoints (9 operation types)
- [x] Implement clientId deduplication
- [x] Exponential backoff + 30s polling

## Phase 4: Form Interception
- [x] Intercept traditional form submissions (submit event listener)
- [x] Implement optimistic local updates (candidates, reviews, notes, interviews)
- [x] URL → operation type mapping

## Phase 5: AJAX/Fetch Interception
- [x] Wrap fetch for offline POST interception
- [x] Counter review, circles, batch candidate interception
- [x] Add-review-candidate AJAX interception

## Phase 6: UI Polish
- [x] Sync status bar (4px fixed bar: green/blue/orange/red)
- [x] Toast messages (נשמר מקומית, סונכרן בהצלחה, שגיאת סנכרון)
- [x] Install prompt (install-prompt.js - iOS/Android/Desktop)
- [x] Logout guard (pending items warning)
- [x] Logout link changed to data-href for JS interception
