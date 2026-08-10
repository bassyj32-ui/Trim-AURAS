const CACHE = "trimaura-v10";
const SHELL = [
  "/",
  "/index.html",
  "/clip.html",
  "/styles.css",
  "/auth.js",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Handle push messages — show a notification for the finished job
self.addEventListener("push", (event) => {
  let payload = { title: "TrimAURA", body: "Your job finished." };
  try {
    if (event.data) payload = event.data.json();
  } catch (e) {
    /* non-JSON payload — keep defaults */
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || "TrimAURA", {
      body: payload.body || "",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: payload.data || {},
    })
  );
});

// Handle notification click — open the job URL or focus the app
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if (new URL(client.url).origin === self.location.origin && "focus" in client) {
          return client.focus();
        }
      }
      return clients.openWindow(target);
    })
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Cross-origin (fonts, Sentry) and API calls — default network behavior
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  // Navigations: network first, fall back to the cached shell when offline.
  // This keeps the app usable with no connection and avoids serving a stale
  // index from cache while the server is reachable.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE).then((cache) => cache.put("/", clone));
          return res;
        })
        .catch(() => caches.match("/").then((shell) => shell || caches.match("/index.html")))
    );
    return;
  }

  // Static assets: stale-while-revalidate — serve instantly, refresh in the
  // background so CSS/icon updates propagate without a version bump.
  event.respondWith(
    caches.match(request).then((cached) => {
      const fresh = fetch(request)
        .then((res) => {
          if (res && res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then((cache) => cache.put(request, clone));
          }
          return res;
        })
        .catch(() => cached);
      return cached || fresh;
    })
  );
});
