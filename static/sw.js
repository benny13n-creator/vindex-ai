// sw.js — Vindex AI Service Worker
// Serviran sa /sw.js (root) — scope "/" pokriva /app i /api/*

const CACHE_NAME = "vindex-v22";

const PRECACHE = [
  "/offline",
  "/static/supabase.min.js",
  "/static/manifest.json",
  "/static/icon-192-v3.png",
  "/static/icon-512-v3.png",
];

// ── Install ──────────────────────────────────────────────────────────────────
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE).catch(e => console.warn("[SW] precache:", e)))
      .then(() => self.skipWaiting())
  );
});

// ── Activate — briši stare cache-ove ────────────────────────────────────────
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// ── Fetch ────────────────────────────────────────────────────────────────────
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);

  if (event.request.method !== "GET") return;

  // Supabase i eksterni auth/API servisi — nikad ne keširati
  if (
    url.hostname.includes("supabase.co") ||
    url.hostname.includes("supabase.io")
  ) {
    return; // browser handles natively, no SW interference
  }

  // API — network-first, offline JSON fallback
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/strategija/") ||
    url.pathname.startsWith("/billing/") ||
    url.pathname.startsWith("/portfolio/") ||
    url.pathname.startsWith("/notifications") ||
    url.pathname.startsWith("/analytics/") ||
    url.pathname.startsWith("/copilot/") ||
    url.pathname.startsWith("/retrieve/") ||
    url.pathname.startsWith("/export/") ||
    url.pathname.startsWith("/push/") ||
    url.pathname.startsWith("/email-notif/") ||
    url.pathname.startsWith("/gdpr/")
  ) {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(
          JSON.stringify({ error: "Nema internet konekcije.", offline: true }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    return;
  }

  // CDN resursi — cache-first
  if (
    url.hostname.includes("fonts.googleapis.com") ||
    url.hostname.includes("fonts.gstatic.com") ||
    url.hostname.includes("cdnjs.cloudflare.com") ||
    url.hostname.includes("cdn.jsdelivr.net") ||
    url.hostname.includes("unpkg.com")
  ) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(resp => {
          if (resp.ok) caches.open(CACHE_NAME).then(c => c.put(event.request, resp.clone()));
          return resp;
        }).catch(() => new Response("", { status: 503 }));
      })
    );
    return;
  }

  // HTML navigacija (/app, /) — network-first da se uvek dobije sveža verzija
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).then(resp => {
        if (resp.ok) caches.open(CACHE_NAME).then(c => c.put(event.request, resp.clone()));
        return resp;
      }).catch(() =>
        caches.match(event.request).then(c => c || caches.match("/offline"))
      )
    );
    return;
  }

  // Staticki fajlovi (JS, CSS, slike) — stale-while-revalidate
  event.respondWith(
    caches.open(CACHE_NAME).then(cache =>
      cache.match(event.request).then(cached => {
        const network = fetch(event.request).then(resp => {
          if (resp.ok) cache.put(event.request, resp.clone());
          return resp;
        }).catch(() => null);
        return cached || network || caches.match("/offline");
      })
    )
  );
});

// ── Message — SKIP_WAITING za auto-update flow ───────────────────────────────
self.addEventListener("message", event => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

// ── Push notifikacije ─────────────────────────────────────────────────────────
self.addEventListener("push", event => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(
    self.registration.showNotification(data.title || "Vindex AI", {
      body:    data.body || "Imate novi podsetnik",
      icon:    "/static/icon-192.png",
      badge:   "/static/icon-192.png",
      data:    { url: data.url || "/app" },
      actions: [
        { action: "otvori",  title: "Otvori" },
        { action: "zatvori", title: "Zatvori" },
      ],
    })
  );
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  if (event.action !== "zatvori") {
    event.waitUntil(clients.openWindow(event.notification.data.url || "/app"));
  }
});

// ── Background Sync — retry offline akcija ──────────────────────────────────
self.addEventListener("sync", event => {
  if (event.tag === "sync-pending-actions") {
    event.waitUntil(
      caches.open("vindex-pending").then(async cache => {
        const keys = await cache.keys();
        const promises = keys.map(async req => {
          try {
            const cached = await cache.match(req);
            const body   = await cached.json();
            const resp   = await fetch(req.url, {
              method:  "POST",
              headers: { "Content-Type": "application/json", ...body._headers },
              body:    JSON.stringify(body._body),
            });
            if (resp.ok) await cache.delete(req);
          } catch (e) {
            // Ostavi u kesu za sledeći sync
          }
        });
        return Promise.all(promises);
      })
    );
  }
});

// ── Periodic Background Sync — podsetnici (ako browser podrzava) ────────────
self.addEventListener("periodicsync", event => {
  if (event.tag === "check-rokovi") {
    event.waitUntil(
      fetch("/api/notifications/rokovi-check", { method: "POST" }).catch(() => {})
    );
  }
});
