const CACHE = "trimaura-v1";
const STATIC_ASSETS = [
  "/",
  "/manifest.json",
  "/styles.css",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API calls — network only
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // Static assets — cache first
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((res) => {
      const clone = res.clone();
      caches.open(CACHE).then((cache) => cache.put(request, clone));
      return res;
    }))
  );
});
