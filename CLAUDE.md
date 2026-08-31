# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
npm start                    # python3 -m http.server 8123 — then open http://127.0.0.1:8123
npm test                     # runs all three suites
node test/bag.test.js        # one suite on its own
node test/pulse.test.js
node test/transfer.test.js
```

There is no build step, no bundler, no linter, and no npm dependencies — `package.json` exists only for those two scripts. Editing a file and reloading the page is the whole loop.

Notifications and the service worker need a secure context: `localhost` or HTTPS. Opening `index.html` as `file://` renders the app but silently skips service worker registration.

## Architecture

A static local-first PWA. Phrases live in IndexedDB on the device and are never sent anywhere; there is no server component to deploy.

**The one structural constraint: `lib/` is shared between the page and the service worker.** `index.html` loads `lib/idb.js`, `lib/bag.js`, `lib/pulse.js` with `<script>` tags, and `sw.js` loads the same three with `importScripts()`. (`lib/transfer.js` is page-only — import/export has no meaning in the worker — so it is in the `SHELL` cache list but not in `importScripts`.) This is why they are classic IIFE scripts attaching globals to `self` (`MPStore`, `MPBag`, `MPPulse`, `MPTransfer`) rather than ES modules. Anything in `lib/` must therefore:

- work in both a window and a worker (no `document`/`window` at load time — the tests also load these files into a bare `vm` context)
- respect load order: `idb.js` → `bag.js` → `pulse.js` → `transfer.js` → `app.js`

The payoff is that a pulse delivered while the app is closed is drawn by exactly the same code as one delivered while it is open.

**Layers.** `lib/bag.js` and `lib/pulse.js` hold every decision about *which* phrase and *when*; `app.js` only reads that state, paints it, and writes back edits. Keep new scheduling or selection logic in `lib/`, not in `app.js`.

**State** is a flat key/value store in IndexedDB (db `mindpulse`, store `kv`) under the keys `phrases`, `settings`, `bag`, `schedule`, `history`. `MPPulse.readState()` is the single reader: it declares defaults in `STATE_SPEC` and re-fills missing settings fields via `Object.assign`, which is how older stored state is migrated forward. Add a new setting by extending `DEFAULT_SETTINGS` — stored objects will pick it up.

**Pure modules take their dependencies as arguments.** `lib/bag.js` takes `rnd`; `lib/transfer.js` takes an id source and a clock. That is what makes them testable without a DOM, a database, or a fake timer — follow it for anything new in `lib/`.

**The shuffle bag** (`lib/bag.js`) is pure: every function takes state and returns new state, and `rnd` is injectable so tests run against a seeded sequence. `bag = { order, cursor, last }`. `reconcile()` folds list edits into an in-flight cycle; `refill()` avoids opening a cycle with the id the last one closed on.

**What drives `tick()`:** a 1-second `setInterval` in the page, a `visibilitychange` handler that hands off to the worker with `postMessage({type:"tick"})` when the page hides, and a `periodicsync` event tagged `mindpulse-tick` in `sw.js`. `tick()` delivers at most one pulse no matter how far behind the schedule is — it re-anchors `nextAt` to now rather than chasing missed slots. Preserve that when touching it.

**Notifications:** the phrase always goes in the body, never the title (the title is one unexpandable line clipped near 29–36 characters). `test/pulse.test.js` asserts this directly; the 100/120-character constants in `app.js` are measured against what a notification body actually shows.

## Conventions that bite

- **Bump `CACHE` in `sw.js`** (currently `mindpulse-shell-v10`) whenever a shell file changes, and add any new file to the `SHELL` array — otherwise returning visitors keep the old copy. The page reloads itself once on `controllerchange` so an update lands on the visit that fetched it.
- **Every path is relative** (`./`, `lib/...`, `icons/...`) so the app works served from a subdirectory. Do not introduce root-absolute paths.
- **The CSP in `index.html` is `'self'`-only** — no CDN, no external fonts, no analytics, no inline `<script>`. Inline styles are allowed. New code must be a same-origin file.
- **Tests are plain Node with no framework**: a hand-rolled `check`/`assert` pair, a seeded PRNG, and `vm.runInContext` over the raw `lib/` source. Follow that shape rather than adding a test runner.
- `.venv/` and `.env` are leftovers from a deleted server build and are gitignored; ignore them.
