/**
 * MindPulse — the screen.
 *
 * The rules about what to send and when live in lib/pulse.js and lib/bag.js,
 * shared with the service worker. This file only reads that state, paints it,
 * and writes back what the person changes.
 */
(function () {
  "use strict";

  var Store = self.MPStore;
  var Bag = self.MPBag;
  var Pulse = self.MPPulse;

  var MINUTE = 60 * 1000;

  // Measured on a macOS notification banner: the body renders three lines and
  // clips just past 110 characters. Under FITS_IN_NOTIFICATION a phrase is
  // certain to arrive whole; MAX_LENGTH leaves a little room above that for
  // anyone who would rather have the words than the guarantee.
  var FITS_IN_NOTIFICATION = 100;
  var MAX_LENGTH = 120;
  var INTERVALS = [
    { label: "15m", ms: 15 * MINUTE },
    { label: "30m", ms: 30 * MINUTE },
    { label: "1h", ms: 60 * MINUTE },
    { label: "2h", ms: 120 * MINUTE },
    { label: "4h", ms: 240 * MINUTE },
    { label: "8h", ms: 480 * MINUTE },
  ];

  var el = {};
  ["status", "status-text", "permit", "permit-text", "permit-btn", "last-when", "phrase",
   "timer-label", "countdown", "rail", "pulse-now", "toggle-pause", "deck", "deck-tally",
   "intervals", "quiet-on", "quiet-times", "quiet-from", "quiet-to", "library-tally",
   "composer", "composer-input", "counter", "list", "empty", "delivery-note", "export", "import",
   "import-file", "toast"].forEach(function (id) {
    el[id] = document.getElementById(id);
  });

  /** Everything the screen is currently drawn from. */
  var state = null;
  var editingId = null;
  var lastRemaining = null;
  var lastDeliveredAt = null;
  var ticking = false;
  var lastTickAt = 0;

  // --- small helpers ------------------------------------------------------

  function newId() {
    if (self.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function pad(n) { return n < 10 ? "0" + n : String(n); }

  function formatCountdown(ms) {
    if (ms < 0) ms = 0;
    var total = Math.ceil(ms / 1000);
    var h = Math.floor(total / 3600);
    var m = Math.floor((total % 3600) / 60);
    var s = total % 60;
    return h ? h + ":" + pad(m) + ":" + pad(s) : pad(m) + ":" + pad(s);
  }

  function formatAgo(ts) {
    var mins = Math.round((Date.now() - ts) / MINUTE);
    if (mins < 1) return "just now";
    if (mins === 1) return "1 minute ago";
    if (mins < 60) return mins + " minutes ago";
    var hrs = Math.round(mins / 60);
    if (hrs === 1) return "1 hour ago";
    if (hrs < 24) return hrs + " hours ago";
    var days = Math.round(hrs / 24);
    return days === 1 ? "yesterday" : days + " days ago";
  }

  function intervalLabel(ms) {
    var match = INTERVALS.filter(function (i) { return i.ms === ms; })[0];
    return match ? match.label : Math.round(ms / MINUTE) + "m";
  }

  /** Report length against what a notification can actually show. */
  function renderCounter() {
    var length = el["composer-input"].value.trim().length;
    if (!length) {
      el.counter.textContent = "";
      el.counter.classList.remove("is-tight");
      return;
    }
    var tight = length > FITS_IN_NOTIFICATION;
    el.counter.textContent = tight
      ? length + " / " + MAX_LENGTH + " · may be cut off in the notification"
      : length + " / " + MAX_LENGTH;
    el.counter.classList.toggle("is-tight", tight);
  }

  var toastTimer = null;
  function toast(message) {
    el.toast.textContent = message;
    el.toast.classList.add("is-shown");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.toast.classList.remove("is-shown"); }, 3200);
  }

  function svg(paths) {
    return '<svg viewBox="0 0 16 16" aria-hidden="true">' + paths + "</svg>";
  }

  // --- reading and writing state ------------------------------------------

  function refresh() {
    return Pulse.readState().then(function (next) {
      state = next;
      render();
      return state;
    });
  }

  function saveSettings(patch) {
    var settings = Object.assign({}, state.settings, patch);
    state.settings = settings;
    return Store.set("settings", settings)
      .then(function () { return Pulse.reanchor(); })
      .then(refresh);
  }

  function savePhrases(phrases) {
    state.phrases = phrases;
    return Store.set("phrases", phrases).then(function () {
      // A first phrase should start the clock rather than wait for a tick.
      if (!state.schedule.nextAt && !state.settings.paused && phrases.length) return Pulse.reanchor();
    }).then(refresh);
  }

  // --- painting -----------------------------------------------------------

  /** Which phrases are still to come in the cycle currently running. */
  function pendingSet() {
    var ids = Pulse.active(state.phrases).map(function (p) { return p.id; });
    if (!ids.length) return new Set();
    var bag = Bag.reconcile(state.bag || Bag.emptyBag(), ids);
    var pending = bag.cursor >= bag.order.length ? bag.order : bag.order.slice(bag.cursor);
    return new Set(pending);
  }

  function renderStatus() {
    var activeCount = Pulse.active(state.phrases).length;
    var permission = typeof Notification === "undefined" ? "denied" : Notification.permission;
    var value, text;

    if (state.settings.paused) { value = "paused"; text = "Paused"; }
    else if (!activeCount) { value = "off"; text = "Idle"; }
    else if (permission !== "granted") { value = "off"; text = "Silent"; }
    else { value = "live"; text = "Live"; }

    el.status.dataset.state = value;
    el["status-text"].textContent = text;

    el["toggle-pause"].textContent = state.settings.paused ? "Resume" : "Pause";
    el["toggle-pause"].setAttribute("aria-pressed", String(!!state.settings.paused));
    el["pulse-now"].disabled = activeCount === 0;
  }

  function renderPermit() {
    if (typeof Notification === "undefined") {
      el.permit.hidden = false;
      el["permit-text"].textContent =
        "This browser can't show notifications. Everything else works — pulses appear here in the app.";
      el["permit-btn"].hidden = true;
      return;
    }
    if (Notification.permission === "granted") { el.permit.hidden = true; return; }

    el.permit.hidden = false;
    if (Notification.permission === "denied") {
      el["permit-text"].textContent =
        "Notifications are blocked for this site. Allow them in your browser's site settings, then reload.";
      el["permit-btn"].hidden = true;
    } else {
      el["permit-text"].textContent =
        "Pulses arrive as notifications. Turn them on so they reach you when the app isn't in front of you.";
      el["permit-btn"].hidden = false;
    }
  }

  function renderReadout() {
    var latest = (state.history || [])[0];
    if (latest) {
      el.phrase.textContent = latest.text;
      el["last-when"].textContent = formatAgo(latest.at);
      if (lastDeliveredAt !== latest.at) {
        lastDeliveredAt = latest.at;
        el.phrase.classList.remove("is-fresh");
        void el.phrase.offsetWidth; // restart the animation
        el.phrase.classList.add("is-fresh");
      }
    } else {
      el.phrase.innerHTML = '<span class="phrase__placeholder">Nothing dealt yet.</span>';
      el["last-when"].textContent = "";
    }
  }

  /** Runs every second — the only thing on screen that moves on its own. */
  function paintClock(now) {
    var schedule = state.schedule || {};
    var paused = state.settings.paused;
    var activeCount = Pulse.active(state.phrases).length;

    if (paused || !activeCount || !schedule.nextAt) {
      el["timer-label"].textContent =
        paused ? "Paused" : !activeCount ? "Waiting for a phrase" : "Next pulse in";
      el.countdown.textContent = "--:--";
      el.rail.style.width = "0%";
      return;
    }

    var remainingMs = schedule.nextAt - now;
    el["timer-label"].textContent = "Next pulse in";
    el.countdown.textContent = formatCountdown(remainingMs);

    var span = state.settings.intervalMs;
    var elapsed = span - remainingMs;
    var progress = Math.max(0, Math.min(1, elapsed / span));
    el.rail.style.width = (progress * 100).toFixed(2) + "%";
  }

  function renderDeck() {
    var pending = pendingSet();
    var actives = Pulse.active(state.phrases);
    var remaining = pending.size;

    // The deck relights all at once when a cycle turns over, which is the
    // moment the "no repeats" promise resets. Only then is it worth animating.
    var relight = lastRemaining !== null && remaining > lastRemaining;
    lastRemaining = remaining;

    el.deck.innerHTML = "";
    actives.forEach(function (phrase, i) {
      var li = document.createElement("li");
      li.className = "tile" + (pending.has(phrase.id) ? " is-pending" : "") + (relight ? " is-relit" : "");
      li.style.setProperty("--i", i);
      el.deck.appendChild(li);
    });

    el["deck-tally"].textContent = actives.length
      ? remaining + " of " + actives.length + " left"
      : "empty";
  }

  function renderRhythm() {
    el.intervals.innerHTML = "";
    INTERVALS.forEach(function (option) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.textContent = option.label;
      button.setAttribute("aria-pressed", String(state.settings.intervalMs === option.ms));
      button.addEventListener("click", function () {
        saveSettings({ intervalMs: option.ms }).then(function () {
          toast("Sending one every " + option.label + ".");
        });
      });
      el.intervals.appendChild(button);
    });

    var quiet = state.settings.quiet;
    el["quiet-on"].checked = !!quiet.enabled;
    el["quiet-times"].hidden = !quiet.enabled;
    el["quiet-from"].value = quiet.from;
    el["quiet-to"].value = quiet.to;
  }

  function renderLibrary() {
    // The scheduler refreshes the screen every 25 seconds. Rebuilding the
    // list under an open editor would throw away what is being typed, so
    // leave it standing until the edit is saved or cancelled.
    if (editingId !== null && el.list.querySelector(".row__edit")) return;

    var phrases = state.phrases || [];
    var pending = pendingSet();

    el["library-tally"].textContent = String(phrases.length);
    el.empty.hidden = phrases.length > 0;
    el.list.innerHTML = "";

    phrases.forEach(function (phrase) {
      var li = document.createElement("li");
      li.className = "row" +
        (phrase.muted ? " is-muted" : "") +
        (!phrase.muted && pending.has(phrase.id) ? " is-pending" : "");

      if (editingId === phrase.id) {
        li.appendChild(buildEditor(phrase));
      } else {
        var marker = document.createElement("span");
        marker.className = "row__marker";
        marker.setAttribute("aria-hidden", "true");

        var text = document.createElement("p");
        text.className = "row__text";
        text.textContent = phrase.text;

        var actions = document.createElement("div");
        actions.className = "row__actions";
        actions.appendChild(iconButton(
          phrase.muted ? "Unmute this phrase" : "Mute this phrase",
          phrase.muted
            ? svg('<path d="M4 6a4 4 0 0 1 8 0v3l1 2H3l1-2z"/><path d="M2 2l12 12"/>')
            : svg('<path d="M4 6a4 4 0 0 1 8 0v3l1 2H3l1-2z"/><path d="M6.4 13.2a1.8 1.8 0 0 0 3.2 0"/>'),
          function () { toggleMute(phrase.id); }
        ));
        actions.appendChild(iconButton("Edit this phrase",
          svg('<path d="M11.6 2.4a1.4 1.4 0 0 1 2 2L5.4 12.6l-2.7.7.7-2.7z"/>'),
          function () { editingId = phrase.id; render(); }
        ));
        var del = iconButton("Delete this phrase",
          svg('<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.6 4.5l.6 8.5h5.6l.6-8.5"/>'),
          function () { removePhrase(phrase.id); }
        );
        del.dataset.act = "delete";
        actions.appendChild(del);

        li.append(marker, text, actions);
      }

      el.list.appendChild(li);
    });
  }

  function iconButton(label, markup, onClick) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "iconbtn";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.innerHTML = markup;
    button.addEventListener("click", onClick);
    return button;
  }

  function buildEditor(phrase) {
    var wrap = document.createElement("div");
    wrap.className = "row__edit";

    var field = document.createElement("textarea");
    field.rows = 2;
    field.maxLength = MAX_LENGTH;
    field.value = phrase.text;
    field.setAttribute("aria-label", "Edit phrase");

    var actions = document.createElement("div");
    actions.className = "row__edit-actions";

    var save = document.createElement("button");
    save.type = "button";
    save.className = "btn btn--solid";
    save.textContent = "Save";
    save.addEventListener("click", function () {
      var text = field.value.trim();
      if (!text) { toast("A phrase needs some words."); field.focus(); return; }
      editingId = null;
      savePhrases(state.phrases.map(function (p) {
        return p.id === phrase.id ? Object.assign({}, p, { text: text }) : p;
      })).then(function () { toast("Phrase updated."); });
    });

    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", function () { editingId = null; render(); });

    actions.append(save, cancel);
    wrap.append(field, actions);
    setTimeout(function () { field.focus(); field.selectionStart = field.value.length; }, 0);
    return wrap;
  }

  function renderDeliveryNote() {
    var background = "serviceWorker" in navigator && "PeriodicSyncManager" in self;
    el["delivery-note"].textContent =
      "Your phrases never leave this device. Pulses arrive while MindPulse is open, including in a background tab, and anything missed is delivered when you come back." +
      (background ? " Installed to your home screen, this browser can deliver while it's closed too." : "");
  }

  function render() {
    if (!state) return;
    renderStatus();
    renderPermit();
    renderReadout();
    renderDeck();
    renderRhythm();
    renderLibrary();
    paintClock(Date.now());
  }

  // --- actions ------------------------------------------------------------

  function addPhrase(text) {
    var phrase = { id: newId(), text: text, note: "", muted: false, createdAt: Date.now() };
    return savePhrases((state.phrases || []).concat([phrase]));
  }

  function removePhrase(id) {
    if (editingId === id) editingId = null;
    var phrase = state.phrases.filter(function (p) { return p.id === id; })[0];
    savePhrases(state.phrases.filter(function (p) { return p.id !== id; })).then(function () {
      toast(phrase ? "Deleted “" + truncate(phrase.text, 32) + "”" : "Phrase deleted.");
    });
  }

  function toggleMute(id) {
    var nowMuted = null;
    var next = state.phrases.map(function (p) {
      if (p.id !== id) return p;
      nowMuted = !p.muted;
      return Object.assign({}, p, { muted: nowMuted });
    });
    savePhrases(next).then(function () {
      toast(nowMuted ? "Muted — it stays in the list but sits out." : "Back in the rotation.");
    });
  }

  function truncate(text, max) {
    return text.length > max ? text.slice(0, max - 1).trimEnd() + "…" : text;
  }

  function runTick() {
    if (ticking) return Promise.resolve();
    ticking = true;
    lastTickAt = Date.now();
    return Pulse.tick().then(function () { return refresh(); })
      .catch(function () { /* a failed tick retries on the next frame */ })
      .then(function () { ticking = false; });
  }

  function requestPermission() {
    Notification.requestPermission().then(function (result) {
      renderPermit();
      renderStatus();
      if (result === "granted") {
        registerBackgroundSync();
        toast("Notifications on. Pulses will arrive from here.");
      } else {
        toast("Still off — pulses will only show inside the app.");
      }
    });
  }

  /**
   * Best effort only: browsers grant periodic sync sparingly, and to
   * installed apps. Everything still works without it.
   */
  function registerBackgroundSync() {
    if (!("serviceWorker" in navigator) || !("PeriodicSyncManager" in self)) return;
    navigator.serviceWorker.ready.then(function (reg) {
      if (!reg.periodicSync) return;
      return navigator.permissions
        .query({ name: "periodic-background-sync" })
        .then(function (status) {
          if (status.state !== "granted") return;
          return reg.periodicSync.register("mindpulse-tick", { minInterval: 15 * MINUTE });
        });
    }).catch(function () { /* unsupported or refused — the open app still ticks */ });
  }

  function exportPhrases() {
    var payload = {
      app: "MindPulse",
      version: 1,
      exportedAt: new Date().toISOString(),
      phrases: state.phrases,
      settings: state.settings,
    };
    var url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    var a = document.createElement("a");
    a.href = url;
    a.download = "mindpulse-phrases.json";
    a.click();
    URL.revokeObjectURL(url);
    toast("Exported " + state.phrases.length + " phrases.");
  }

  /** Import adds what's missing and leaves what's already here alone. */
  function importPhrases(file) {
    file.text().then(function (raw) {
      var data = JSON.parse(raw);
      var incoming = Array.isArray(data) ? data : data.phrases;
      if (!Array.isArray(incoming)) throw new Error("no phrases");

      var have = new Set(state.phrases.map(function (p) { return p.text.trim(); }));
      var added = incoming
        .map(function (p) { return typeof p === "string" ? { text: p } : p; })
        .filter(function (p) { return p && typeof p.text === "string" && p.text.trim(); })
        .filter(function (p) { return !have.has(p.text.trim()); })
        .map(function (p) {
          return { id: newId(), text: p.text.trim(), note: p.note || "", muted: !!p.muted, createdAt: Date.now() };
        });

      if (!added.length) { toast("Nothing new to add — those phrases are already here."); return; }
      savePhrases(state.phrases.concat(added)).then(function () {
        toast("Added " + added.length + (added.length === 1 ? " phrase." : " phrases."));
      });
    }).catch(function () {
      toast("That file isn't a MindPulse export.");
    });
  }

  // --- wiring -------------------------------------------------------------

  function autoGrow(field) {
    field.style.height = "auto";
    field.style.height = field.scrollHeight + "px";
  }

  el.composer.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = el["composer-input"].value.trim();
    if (!text) return;
    addPhrase(text).then(function () {
      el["composer-input"].value = "";
      autoGrow(el["composer-input"]);
      renderCounter();
      el["composer-input"].focus();
      toast("Added. It's in the cycle already running.");
    });
  });

  el["composer-input"].addEventListener("input", function () {
    autoGrow(this);
    renderCounter();
  });
  el["composer-input"].addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      el.composer.requestSubmit();
    }
  });

  el["pulse-now"].addEventListener("click", function () {
    Pulse.fire("manual").then(function (result) {
      if (!result) { toast("Write a phrase first."); return; }
      return refresh().then(function () {
        if (typeof Notification !== "undefined" && Notification.permission === "granted") return;
        toast("Dealt — turn on notifications to get these outside the app.");
      });
    });
  });

  el["toggle-pause"].addEventListener("click", function () {
    var paused = !state.settings.paused;
    saveSettings({ paused: paused }).then(function () {
      toast(paused ? "Paused. Nothing sends until you resume."
                   : "Running again — next one in " + intervalLabel(state.settings.intervalMs) + ".");
    });
  });

  el["permit-btn"].addEventListener("click", requestPermission);

  el["quiet-on"].addEventListener("change", function () {
    var quiet = Object.assign({}, state.settings.quiet, { enabled: this.checked });
    saveSettings({ quiet: quiet }).then(function () {
      toast(quiet.enabled ? "Overnight pulses held until " + quiet.to + "." : "Sending around the clock.");
    });
  });

  ["quiet-from", "quiet-to"].forEach(function (id) {
    el[id].addEventListener("change", function () {
      var quiet = Object.assign({}, state.settings.quiet);
      quiet[id === "quiet-from" ? "from" : "to"] = this.value;
      saveSettings({ quiet: quiet });
    });
  });

  el.export.addEventListener("click", exportPhrases);
  el.import.addEventListener("click", function () { el["import-file"].click(); });
  el["import-file"].addEventListener("change", function () {
    if (this.files && this.files[0]) importPhrases(this.files[0]);
    this.value = "";
  });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      runTick();
    } else if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      // Hand the schedule to the worker on the way out.
      navigator.serviceWorker.controller.postMessage({ type: "tick" });
    }
  });

  // --- boot ---------------------------------------------------------------

  function frame() {
    if (!state) return;
    var now = Date.now();
    paintClock(now);

    var due = state.schedule.nextAt && now >= state.schedule.nextAt &&
              !state.settings.paused && Pulse.active(state.phrases).length;
    if (due || now - lastTickAt > 25000) runTick();
  }

  /**
   * Storage can simply not be there — Safari's private browsing has blocked
   * IndexedDB, and any browser can have site data switched off. The app has
   * nowhere to put phrases in that case, so say what happened rather than
   * leaving a screen that looks broken.
   */
  function reportStorageFailure() {
    el.permit.hidden = false;
    el["permit-text"].textContent =
      "MindPulse can't reach this browser's storage, so it has nowhere to keep your phrases. " +
      "That usually means private browsing, or site data being blocked for this site.";
    el["permit-btn"].hidden = true;
    el["timer-label"].textContent = "Storage unavailable";
    el.countdown.textContent = "--:--";
    el["pulse-now"].disabled = true;
    el["toggle-pause"].disabled = true;
    el.export.disabled = true;
    el.import.disabled = true;

    // Writing is what fails, so close the door rather than letting someone
    // type a phrase that would silently go nowhere.
    el["composer-input"].disabled = true;
    var add = el.composer.querySelector("button[type=submit]");
    if (add) add.disabled = true;

    // These two sections only ever draw from stored state, so without it
    // they render as empty headings. Better absent than broken-looking.
    document.querySelector(".deck").hidden = true;
    document.querySelector(".rhythm").hidden = true;

    // The empty state invites you to write a first phrase; that invitation is
    // false when there is nowhere to write it to.
    el.empty.hidden = true;
  }

  refresh().then(function () {
    renderDeliveryNote();
    return runTick();
  }).catch(reportStorageFailure);

  setInterval(frame, 1000);

  if ("serviceWorker" in navigator) {
    // A new worker takes over as soon as it installs, but the page it takes
    // over is still running the old scripts it loaded from the previous
    // cache. Nothing here is unsaved, so the honest thing is to reload once
    // and be on the new version — otherwise an update only lands on the
    // visit after the one that fetched it.
    var reloading = false;
    navigator.serviceWorker.addEventListener("controllerchange", function () {
      if (reloading) return;
      reloading = true;
      location.reload();
    });

    window.addEventListener("load", function () {
      navigator.serviceWorker.register("sw.js").then(function () {
        if (typeof Notification !== "undefined" && Notification.permission === "granted") {
          registerBackgroundSync();
        }
      }).catch(function () { /* file:// or no HTTPS — the app still runs */ });
    });
  }
})();
