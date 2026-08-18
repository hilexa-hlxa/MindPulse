/**
 * MindPulse Service Worker
 *
 * Responsibilities (spec 7.3):
 *  - install / activate lifecycle
 *  - push: display a notification carrying the phrase text
 *  - notificationclick: focus an existing app window or open a new one
 */

const CACHE_NAME = "mindpulse-shell-v1";
const APP_SHELL = ["/", "/index.html", "/style.css", "/app.js", "/manifest.json"];

self.addEventListener("install", (event) => {
  // Activate this SW as soon as it finishes installing, without waiting
  // for the old one to be released (no open tabs to keep alive here).
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => {
      // Precaching is a nice-to-have for offline shell load; a failure
      // here (e.g. dev server quirk) shouldn't block install.
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("push", (event) => {
  let data = { title: "MindPulse", body: "Keep going — you've got this." };
  if (event.data) {
    try {
      data = { ...data, ...event.data.json() };
    } catch {
      data.body = event.data.text();
    }
  }

  const title = data.title || "MindPulse";
  const body = data.author ? `${data.body} — ${data.author}` : data.body;

  const options = {
    body,
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    tag: "mindpulse-notification",
    renotify: true,
    data: { url: "/" },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        const clientUrl = new URL(client.url);
        if (clientUrl.pathname === targetUrl && "focus" in client) {
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
