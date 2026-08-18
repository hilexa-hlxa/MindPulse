/**
 * MindPulse frontend — vanilla JS, no framework (intentional, spec 2.2).
 *
 * Handles: view routing, REST calls to the FastAPI backend, the
 * notification permission/subscribe flow, and the four views
 * (Dashboard, Phrases, Add, Settings).
 */

const API = "/api";
const STORAGE_KEY = "mindpulse_subscribed";

let cachedPhrases = [];
let intervalDebounce = null;

// ---------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------

async function apiRequest(path, { method = "GET", body } = {}) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      /* ignore parse failure, keep statusText */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

let toastTimer = null;
function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2400);
}

function formatDate(iso) {
  if (!iso) return "Never";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

// ---------------------------------------------------------------------
// View routing (bottom tab bar)
// ---------------------------------------------------------------------

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  document.querySelectorAll("nav.tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "phrases") loadPhrases();
  if (name === "settings") loadSettings();
}

document.querySelectorAll("nav.tabbar button").forEach((btn) => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});

// ---------------------------------------------------------------------
// Service worker + push subscription
// ---------------------------------------------------------------------

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js");
  } catch (err) {
    console.error("Service worker registration failed:", err);
    return null;
  }
}

// ---------------------------------------------------------------------
// "Add to Home Screen" install affordance (US-01)
//
// Chrome/Edge/Android fire `beforeinstallprompt`, which we capture and
// replay from a real button tap (browsers ignore prompt() calls that
// aren't triggered by user gesture). iOS Safari never fires that event
// at all — it only supports the manual Share → Add to Home Screen flow —
// so it gets an instructional hint instead.
// ---------------------------------------------------------------------

let deferredInstallPrompt = null;

function isStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function isIos() {
  return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}

function refreshInstallCard() {
  const card = document.getElementById("install-card");
  const hint = document.getElementById("install-hint");
  const btn = document.getElementById("btn-install");

  if (isStandalone()) {
    card.hidden = true;
    return;
  }

  if (deferredInstallPrompt) {
    card.hidden = false;
    btn.hidden = false;
    hint.textContent = "Install MindPulse on your home screen for the full native-app feel.";
  } else if (isIos()) {
    card.hidden = false;
    btn.hidden = true;
    hint.textContent = "Tap the Share icon, then “Add to Home Screen” to install MindPulse.";
  } else {
    // No install signal available (e.g. desktop Firefox) — nothing useful to show.
    card.hidden = true;
  }
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  refreshInstallCard();
});

window.addEventListener("appinstalled", () => {
  deferredInstallPrompt = null;
  toast("MindPulse installed 🎉");
  refreshInstallCard();
});

document.getElementById("btn-install").addEventListener("click", async () => {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt();
  await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null;
  refreshInstallCard();
});

function updatePermissionPill() {
  const pill = document.getElementById("perm-pill");
  const supported = "Notification" in window && "PushManager" in window;
  const subscribed = localStorage.getItem(STORAGE_KEY) === "true";

  if (!supported) {
    pill.textContent = "Unsupported";
    pill.className = "pill off";
  } else if (Notification.permission === "granted" && subscribed) {
    pill.textContent = "Enabled";
    pill.className = "pill on";
  } else if (Notification.permission === "denied") {
    pill.textContent = "Blocked";
    pill.className = "pill off";
  } else {
    pill.textContent = "Disabled";
    pill.className = "pill off";
  }

  const enableBtn = document.getElementById("btn-enable");
  if (Notification.permission === "granted" && subscribed) {
    enableBtn.textContent = "✅ Notifications Enabled";
    enableBtn.disabled = true;
  }
}

async function enableNotifications() {
  const btn = document.getElementById("btn-enable");

  if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
    toast("Push notifications aren't supported in this browser.");
    return;
  }

  if (Notification.permission === "denied") {
    toast("Notifications are blocked — enable them in your browser's site settings.");
    return;
  }

  btn.disabled = true;
  try {
    // Permission is only ever requested here, on an explicit tap —
    // never automatically on page load (spec 7.2 / US-02).
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      toast("Permission not granted.");
      return;
    }

    const registration = await navigator.serviceWorker.ready;
    const { publicKey } = await apiRequest("/vapid-public-key");
    if (!publicKey) {
      toast("Server has no VAPID key configured yet.");
      return;
    }

    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
    }

    await apiRequest("/subscriptions", { method: "POST", body: subscription.toJSON() });
    localStorage.setItem(STORAGE_KEY, "true");
    toast("Notifications enabled 🎉");
  } catch (err) {
    console.error(err);
    toast("Couldn't enable notifications — see console for details.");
  } finally {
    updatePermissionPill();
    btn.disabled = Notification.permission === "granted" && localStorage.getItem(STORAGE_KEY) === "true";
  }
}

// ---------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------

async function loadDashboard() {
  try {
    const settings = await apiRequest("/settings");
    document.getElementById("dash-interval").textContent = `Every ${settings.interval_minutes} min`;
    document.getElementById("dash-last-sent").textContent = formatDate(settings.last_sent_at);

    const schedulerPill = document.getElementById("scheduler-pill");
    schedulerPill.textContent = settings.is_running ? "Running" : "Paused";
    schedulerPill.className = `pill ${settings.is_running ? "on" : "off"}`;
  } catch (err) {
    console.error(err);
  }
}

async function previewPhrase() {
  const preview = document.getElementById("dash-preview");
  try {
    const phrase = await apiRequest("/phrases/random");
    preview.textContent = phrase.author ? `"${phrase.text}" — ${phrase.author}` : `"${phrase.text}"`;
  } catch {
    preview.textContent = "No active phrases yet — add one in the Add tab.";
  }
}

async function triggerNow() {
  const btn = document.getElementById("btn-trigger");
  btn.disabled = true;
  try {
    const result = await apiRequest("/settings/trigger", { method: "POST" });
    toast(result.sent ? "Notification sent 🚀" : `Nothing sent: ${result.reason || "no active phrases"}`);
    loadDashboard();
  } catch (err) {
    toast("Trigger failed — see console.");
    console.error(err);
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------
// Phrases list
// ---------------------------------------------------------------------

function renderPhrases() {
  const list = document.getElementById("phrase-list");
  if (cachedPhrases.length === 0) {
    list.innerHTML = '<div class="empty-state">No phrases yet. Add your first one in the Add tab.</div>';
    return;
  }

  list.innerHTML = "";
  for (const phrase of cachedPhrases) {
    const item = document.createElement("div");
    item.className = `phrase-item${phrase.is_active ? "" : " inactive"}`;
    item.dataset.id = phrase.id;

    item.innerHTML = `
      <label class="switch">
        <input type="checkbox" ${phrase.is_active ? "checked" : ""} class="toggle-active" />
        <span class="slider"></span>
      </label>
      <div class="phrase-body">
        <div class="phrase-text" spellcheck="false">${escapeHtml(phrase.text)}</div>
        <div class="phrase-meta">${phrase.author ? escapeHtml(phrase.author) + " · " : ""}sent ${phrase.times_sent}×</div>
      </div>
      <div class="phrase-actions">
        <button class="icon-btn edit-btn" title="Edit">✏️</button>
        <button class="icon-btn danger delete-btn" title="Delete">🗑️</button>
      </div>
    `;

    const textEl = item.querySelector(".phrase-text");
    const editBtn = item.querySelector(".edit-btn");
    const deleteBtn = item.querySelector(".delete-btn");
    const toggleEl = item.querySelector(".toggle-active");

    toggleEl.addEventListener("change", () => togglePhraseActive(phrase.id, toggleEl.checked));

    editBtn.addEventListener("click", () => {
      const editing = textEl.getAttribute("contenteditable") === "true";
      if (editing) {
        commitPhraseEdit(phrase.id, textEl);
      } else {
        textEl.setAttribute("contenteditable", "true");
        textEl.focus();
        editBtn.textContent = "💾";
      }
    });

    textEl.addEventListener("blur", () => {
      if (textEl.getAttribute("contenteditable") === "true") commitPhraseEdit(phrase.id, textEl);
    });
    textEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        textEl.blur();
      }
    });

    deleteBtn.addEventListener("click", () => deletePhrase(phrase.id));

    list.appendChild(item);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadPhrases() {
  try {
    cachedPhrases = await apiRequest("/phrases");
    renderPhrases();
  } catch (err) {
    console.error(err);
    toast("Couldn't load phrases.");
  }
}

async function togglePhraseActive(id, isActive) {
  try {
    await apiRequest(`/phrases/${id}`, { method: "PATCH", body: { is_active: isActive } });
    const phrase = cachedPhrases.find((p) => p.id === id);
    if (phrase) phrase.is_active = isActive;
    renderPhrases();
  } catch (err) {
    toast("Update failed.");
    console.error(err);
    loadPhrases();
  }
}

async function commitPhraseEdit(id, textEl) {
  textEl.removeAttribute("contenteditable");
  const item = textEl.closest(".phrase-item");
  const editBtn = item.querySelector(".edit-btn");
  editBtn.textContent = "✏️";

  const newText = textEl.textContent.trim();
  const phrase = cachedPhrases.find((p) => p.id === id);
  if (!newText || !phrase || newText === phrase.text) {
    if (phrase) textEl.textContent = phrase.text;
    return;
  }

  try {
    const updated = await apiRequest(`/phrases/${id}`, { method: "PATCH", body: { text: newText } });
    phrase.text = updated.text;
    toast("Phrase updated.");
  } catch (err) {
    toast("Couldn't save edit.");
    console.error(err);
    textEl.textContent = phrase.text;
  }
}

async function deletePhrase(id) {
  if (!confirm("Delete this phrase? This can't be undone.")) return;
  try {
    await apiRequest(`/phrases/${id}`, { method: "DELETE" });
    cachedPhrases = cachedPhrases.filter((p) => p.id !== id);
    renderPhrases();
    toast("Phrase deleted.");
  } catch (err) {
    toast("Delete failed.");
    console.error(err);
  }
}

// ---------------------------------------------------------------------
// Add phrase
// ---------------------------------------------------------------------

document.getElementById("add-phrase-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const textInput = document.getElementById("add-text");
  const authorInput = document.getElementById("add-author");

  const text = textInput.value.trim();
  if (!text) return;

  try {
    await apiRequest("/phrases", {
      method: "POST",
      body: { text, author: authorInput.value.trim() || null },
    });
    textInput.value = "";
    authorInput.value = "";
    toast("Phrase added ✅");
    showView("phrases");
  } catch (err) {
    toast("Couldn't add phrase.");
    console.error(err);
  }
});

// ---------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------

async function loadSettings() {
  try {
    const settings = await apiRequest("/settings");
    const range = document.getElementById("interval-range");
    const display = document.getElementById("interval-display");
    const running = document.getElementById("settings-running");

    range.value = settings.interval_minutes;
    display.textContent = settings.interval_minutes;
    running.checked = settings.is_running;
  } catch (err) {
    console.error(err);
  }
}

const intervalRange = document.getElementById("interval-range");
intervalRange.addEventListener("input", () => {
  document.getElementById("interval-display").textContent = intervalRange.value;
});
intervalRange.addEventListener("change", () => {
  clearTimeout(intervalDebounce);
  intervalDebounce = setTimeout(async () => {
    try {
      await apiRequest("/settings", { method: "PATCH", body: { interval_minutes: Number(intervalRange.value) } });
      toast(`Interval set to ${intervalRange.value} min`);
      loadDashboard();
    } catch (err) {
      toast("Couldn't update interval.");
      console.error(err);
    }
  }, 200);
});

document.getElementById("settings-running").addEventListener("change", async (e) => {
  const isRunning = e.target.checked;
  try {
    await apiRequest("/settings", { method: "PATCH", body: { is_running: isRunning } });
    toast(isRunning ? "Scheduler resumed" : "Scheduler paused");
    loadDashboard();
  } catch (err) {
    e.target.checked = !isRunning;
    toast("Couldn't update scheduler state.");
    console.error(err);
  }
});

// ---------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------

document.getElementById("btn-enable").addEventListener("click", enableNotifications);
document.getElementById("btn-preview").addEventListener("click", previewPhrase);
document.getElementById("btn-trigger").addEventListener("click", triggerNow);

window.addEventListener("load", () => {
  registerServiceWorker();
  updatePermissionPill();
  refreshInstallCard();
  loadDashboard();
});
