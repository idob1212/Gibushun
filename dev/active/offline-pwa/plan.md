# Offline-First PWA Implementation Plan

## Phases
1. PWA Foundation (manifest, SW, CDN removal, Flask routes)
2. Local-first data layer (Dexie.js IndexedDB, offline-bundle API, dropdown merge)
3. Sync queue + server API (SyncLog model, sync endpoints, queue drain)
4. Form interception + optimistic local updates
5. AJAX/Fetch interception for offline operation
6. UI polish (sync status bar, toasts, install prompt, logout guard)

## Key Architecture Decisions
- Dexie.js v3 for IndexedDB (handles iOS Safari quirks)
- Hand-written service worker (app has ~25 pages)
- Network-First for HTML, Cache-First for static assets
- online event + 30s polling (iOS has no Background Sync)
- Last-Write-Wins + clientId dedup for conflict resolution
- No SPA rewrite - client-side layer on existing Flask app
