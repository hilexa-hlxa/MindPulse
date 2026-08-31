/**
 * Turning "it's time" into a notification.
 *
 * Both the page and the service worker call tick(). Keeping the decision in
 * one place means a pulse delivered while the app is closed is drawn by
 * exactly the same rules as one delivered while you are looking at it.
 *
 * Classic script — sw.js loads it with importScripts(). Depends on MPStore
 * and MPBag being loaded first.
 */
(function (root) {
  "use strict";

  var MINUTE = 60 * 1000;

  // Roughly what a notification title shows before the OS cuts it off.
  // Past this the phrase moves into the body, which has room to wrap.
  var TITLE_MAX = 76;

  var DEFAULT_SETTINGS = {
    intervalMs: 60 * MINUTE,
    paused: false,
    quiet: { enabled: false, from: "22:00", to: "07:00" },
  };

  var STATE_SPEC = {
    phrases: [],
    settings: DEFAULT_SETTINGS,
    bag: null,
    schedule: { nextAt: null, lastAt: null },
    history: [],
  };

  function readState() {
    return root.MPStore.getAll(STATE_SPEC).then(function (state) {
      // Settings gain fields across versions; fill in anything missing.
      state.settings = Object.assign({}, DEFAULT_SETTINGS, state.settings || {});
      state.settings.quiet = Object.assign({}, DEFAULT_SETTINGS.quiet, state.settings.quiet || {});
      state.bag = state.bag || root.MPBag.emptyBag();
      return state;
    });
  }

  /** Phrases eligible to be sent — muted ones stay in the list but sit out. */
  function active(phrases) {
    return (phrases || []).filter(function (p) { return !p.muted; });
  }

  function minutesOfDay(date) {
    return date.getHours() * 60 + date.getMinutes();
  }

  function parseClock(hhmm) {
    var parts = String(hhmm || "0:00").split(":");
    return (parseInt(parts[0], 10) || 0) * 60 + (parseInt(parts[1], 10) || 0);
  }

  /**
   * Quiet hours normally wrap past midnight (22:00 to 07:00), so the window
   * is "after from OR before to" whenever from is later than to.
   */
  function inQuiet(when, quiet) {
    if (!quiet || !quiet.enabled) return false;
    var from = parseClock(quiet.from);
    var to = parseClock(quiet.to);
    if (from === to) return false;
    var m = minutesOfDay(when);
    return from < to ? m >= from && m < to : m >= from || m < to;
  }

  /** The moment quiet hours next lift, given a time inside them. */
  function quietEnds(when, quiet) {
    var end = new Date(when);
    var to = parseClock(quiet.to);
    end.setHours(Math.floor(to / 60), to % 60, 0, 0);
    if (end <= when) end = new Date(end.getTime() + 24 * 60 * MINUTE);
    return end.getTime();
  }

  /** When the pulse after `now` should land, pushed past any quiet window. */
  function nextAfter(now, settings) {
    var at = now + settings.intervalMs;
    if (inQuiet(new Date(at), settings.quiet)) at = quietEnds(new Date(at), settings.quiet);
    return at;
  }

  /** Trim to a whole word, so a phrase never breaks mid-word. */
  function clipToWord(text, max) {
    if (text.length <= max) return text;
    var cut = text.slice(0, max);
    var space = cut.lastIndexOf(" ");
    if (space > max * 0.55) cut = cut.slice(0, space);
    return cut.replace(/[\s,;:.!?—–-]+$/, "") + "…";
  }

  /**
   * Decide how a phrase is laid out across a notification's two fields.
   *
   * The title is a single hard-truncated line on every platform, while the
   * body wraps over several and can be expanded by the reader. So a short
   * phrase goes in the title, where it reads as the headline it is; a long
   * one leads in the title and repeats in full in the body, where there is
   * room for it. Either way nothing is lost to the truncation.
   */
  function splitForNotification(phrase) {
    var text = String(phrase.text || "").trim();
    if (text.length <= TITLE_MAX) {
      return { title: text, body: phrase.note || "MindPulse" };
    }
    return { title: clipToWord(text, TITLE_MAX), body: text };
  }

  function showNotification(phrase) {
    if (typeof Notification === "undefined" || Notification.permission !== "granted") {
      return Promise.resolve(false);
    }
    var reg = root.registration
      ? Promise.resolve(root.registration)
      : navigator.serviceWorker.ready;

    var parts = splitForNotification(phrase);
    return reg.then(function (r) {
      return r.showNotification(parts.title, {
        body: parts.body,
        icon: "icons/icon-192.png",
        badge: "icons/icon-192.png",
        tag: "mindpulse-pulse",
        renotify: true,
        data: { phraseId: phrase.id },
      });
    }).then(function () { return true; }, function () { return false; });
  }

  /**
   * Draw and deliver one phrase, whatever the clock says. Used by the
   * scheduler and by the "Pulse now" button.
   */
  function fire(reason) {
    return readState().then(function (state) {
      var pool = active(state.phrases);
      if (!pool.length) return null;

      var ids = pool.map(function (p) { return p.id; });
      var result = root.MPBag.draw(state.bag, ids);
      var phrase = pool.filter(function (p) { return p.id === result.id; })[0];
      if (!phrase) return null;

      var entry = { id: phrase.id, text: phrase.text, at: Date.now(), reason: reason || "scheduled" };
      var history = [entry].concat(state.history || []).slice(0, 60);

      return Promise.all([
        root.MPStore.set("bag", result.bag),
        root.MPStore.set("history", history),
        showNotification(phrase),
      ]).then(function () {
        return { phrase: phrase, entry: entry, cycled: result.cycled };
      });
    });
  }

  /**
   * Advance the schedule to `now`, delivering a pulse if one is due.
   *
   * Only ever one: reopening the app after a day away should not fire
   * twenty-four backlogged notifications, so the next pulse is re-anchored
   * to now rather than chased forward from the missed slot.
   */
  function tick(now) {
    now = now || Date.now();
    return readState().then(function (state) {
      var schedule = state.schedule || { nextAt: null, lastAt: null };

      if (state.settings.paused || !active(state.phrases).length) {
        return { state: state, schedule: schedule, delivered: null };
      }

      if (!schedule.nextAt) {
        schedule = { nextAt: nextAfter(now, state.settings), lastAt: schedule.lastAt };
        return root.MPStore.set("schedule", schedule).then(function () {
          return { state: state, schedule: schedule, delivered: null };
        });
      }

      if (now < schedule.nextAt) return { state: state, schedule: schedule, delivered: null };

      if (inQuiet(new Date(now), state.settings.quiet)) {
        schedule = { nextAt: quietEnds(new Date(now), state.settings.quiet), lastAt: schedule.lastAt };
        return root.MPStore.set("schedule", schedule).then(function () {
          return { state: state, schedule: schedule, delivered: null };
        });
      }

      return fire("scheduled").then(function (delivered) {
        schedule = { nextAt: nextAfter(now, state.settings), lastAt: now };
        return root.MPStore.set("schedule", schedule).then(function () {
          return { state: state, schedule: schedule, delivered: delivered };
        });
      });
    });
  }

  /** Re-anchor the countdown to start from now (after a settings change). */
  function reanchor(now) {
    now = now || Date.now();
    return readState().then(function (state) {
      var schedule = {
        nextAt: state.settings.paused ? null : nextAfter(now, state.settings),
        lastAt: (state.schedule || {}).lastAt || null,
      };
      return root.MPStore.set("schedule", schedule).then(function () { return schedule; });
    });
  }

  root.MPPulse = {
    DEFAULT_SETTINGS: DEFAULT_SETTINGS,
    readState: readState,
    active: active,
    inQuiet: inQuiet,
    quietEnds: quietEnds,
    nextAfter: nextAfter,
    splitForNotification: splitForNotification,
    fire: fire,
    tick: tick,
    reanchor: reanchor,
  };
})(typeof self !== "undefined" ? self : globalThis);
