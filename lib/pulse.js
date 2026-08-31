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

  // What the notification title is allowed to be. Not the phrase: a title is
  // one narrow line that cannot be expanded — macOS clips it around 29
  // characters — so the phrase is never put there.
  var NOTIFICATION_TITLE = "MindPulse";

  /**
   * The parts of the day a phrase can be pinned to, and what each one is for.
   *
   * A phrase belongs to exactly one of these; "anytime" is the default and
   * fits every window, which is what keeps a library written before Advanced
   * Mode existed working unchanged the moment it is switched on.
   *
   * The three real windows run 06:00 to midnight. The small hours belong to
   * none of them and deliver nothing at all in Advanced Mode — see eligible().
   */
  var WINDOWS = [
    {
      id: "anytime",
      label: "Anytime",
      tone: "Fits any hour",
      placeholder: "Write a phrase worth hearing again",
    },
    {
      id: "morning",
      label: "Morning",
      from: 6 * 60,
      to: 12 * 60,
      tone: "Momentum — something to start on",
      placeholder: "Something to get you moving — “Today is yours. Take it.”",
    },
    {
      id: "afternoon",
      label: "Afternoon",
      from: 12 * 60,
      to: 18 * 60,
      tone: "Focus — something to push through with",
      placeholder: "Something to push through with — “Don’t stop at half.”",
    },
    {
      id: "evening",
      label: "Evening",
      from: 18 * 60,
      to: 24 * 60,
      tone: "Reckoning — something honest",
      placeholder: "Something honest — “Your mom is still at work right now.”",
    },
  ];

  var DEFAULT_SETTINGS = {
    intervalMs: 60 * MINUTE,
    paused: false,
    advanced: false,
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

  /** Which window a moment falls in, or null if it falls outside them all. */
  function windowAt(when) {
    var m = minutesOfDay(when || new Date());
    var hit = WINDOWS.filter(function (w) {
      return w.from != null && m >= w.from && m < w.to;
    })[0];
    return hit ? hit.id : null;
  }

  /**
   * The window a phrase is pinned to. Anything unrecognised — a phrase
   * written before categories existed, or a hand-edited import — reads as
   * anytime, so no phrase can be stranded by a value the app stops using.
   */
  function phraseWindow(phrase) {
    var id = phrase && phrase.window;
    var known = WINDOWS.filter(function (w) { return w.id === id; })[0];
    return known ? known.id : "anytime";
  }

  /**
   * The phrases that may be sent at `when`.
   *
   * With Advanced Mode off this is just the unmuted ones, exactly as before.
   * With it on, a phrase must also suit the hour: its own window, or anytime.
   * There is deliberately no fallback — if you pinned everything to Morning,
   * the evening stays quiet rather than sending a morning phrase at 9pm,
   * which is the whole point of having pinned it.
   */
  function eligible(phrases, when, settings) {
    var pool = active(phrases);
    if (!settings || !settings.advanced) return pool;

    var current = windowAt(when || new Date());

    // Outside the three windows nothing is sent. Letting anytime phrases fill
    // the small hours sounds harmless, but on a thin library it leaves a pool
    // of one — and a pool of one repeats, which is the single thing the
    // shuffle bag exists to prevent. Simulated over a week it produced runs of
    // seven identical notifications. Holding until 06:00 costs nothing anyone
    // wanted at 4am, and keeps the promise the app is built on.
    if (!current) return [];

    return pool.filter(function (p) {
      var w = phraseWindow(p);
      return w === "anytime" || w === current;
    });
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

  /**
   * Decide how a phrase is laid out across a notification's two fields.
   *
   * Measured rather than assumed: on macOS the title is clipped at about 29
   * characters with an ellipsis and cannot be expanded, while the body wraps
   * over several lines and expands when the reader opens the notification.
   * So the phrase always goes in the body and the title stays a fixed short
   * label — otherwise the app name sits in the roomy field while the words
   * that matter get cut off in the narrow one.
   *
   * The title is fixed, full stop. There was once a branch here that promoted
   * a phrase's `note` into it; nothing in the app could set that field, and if
   * anything ever had, it would have put the words worth reading into the one
   * place that clips them. An imported file may still carry a note, so the
   * field is tolerated in the data — it just never reaches a notification.
   */
  function splitForNotification(phrase) {
    return {
      title: NOTIFICATION_TITLE,
      body: String(phrase.text || "").trim(),
    };
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
  function fire(reason, now) {
    now = now || Date.now();
    return readState().then(function (state) {
      var pool = eligible(state.phrases, new Date(now), state.settings);
      if (!pool.length) return null;

      var ids = pool.map(function (p) { return p.id; });
      var result = root.MPBag.draw(state.bag, ids);
      var phrase = pool.filter(function (p) { return p.id === result.id; })[0];
      if (!phrase) return null;

      var entry = { id: phrase.id, text: phrase.text, at: now, reason: reason || "scheduled" };
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

      // Nothing to send holds the schedule where it is rather than pushing it
      // forward, so a pulse lands promptly when a window opens or a phrase is
      // written, instead of waiting out a whole interval first.
      if (state.settings.paused || !eligible(state.phrases, new Date(now), state.settings).length) {
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

      return fire("scheduled", now).then(function (delivered) {
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
    WINDOWS: WINDOWS,
    readState: readState,
    active: active,
    windowAt: windowAt,
    phraseWindow: phraseWindow,
    eligible: eligible,
    inQuiet: inQuiet,
    quietEnds: quietEnds,
    nextAfter: nextAfter,
    splitForNotification: splitForNotification,
    fire: fire,
    tick: tick,
    reanchor: reanchor,
  };
})(typeof self !== "undefined" ? self : globalThis);
