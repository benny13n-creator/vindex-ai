// sw.js — Vindex AI Service Worker (F6)
const CACHE_NAME = "vindex-v1";
const STATIC_ASSETS = ["/app", "/static/manifest.json"];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  if (
    event.request.url.includes("/api/") ||
    event.request.url.includes("/strategija/") ||
    event.request.url.includes("/export/") ||
    event.request.url.includes("/push/") ||
    event.request.url.includes("/api-kljucevi/") ||
    event.request.method !== "GET"
  ) {
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then(response => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

self.addEventListener("push", event => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "Vindex AI";
  const options = {
    body: data.body || "Imate novi podsetnik",
    icon: "/static/icon-192.png",
    badge: "/static/icon-192.png",
    data: { url: data.url || "/app" },
    actions: [
      { action: "otvori", title: "Otvori Vindex" },
      { action: "zatvori", title: "Zatvori" }
    ]
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  if (event.action === "otvori" || !event.action) {
    event.waitUntil(clients.openWindow(event.notification.data.url || "/app"));
  }
});
