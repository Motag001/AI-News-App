/* Service worker: makes the app installable and keeps it usable offline.
 * - App shell and static files: cached on install, refreshed in the background.
 * - Pages: network first, falling back to the cached shell (the app renders every route client-side).
 * - Story and briefing data (GET only): network first, falling back to the last copy seen.
 * Only same-origin GET requests are ever cached; nothing about visitors is stored. */
const VERSION = "v1";
const SHELL_CACHE = `shell-${VERSION}`;
const DATA_CACHE = `data-${VERSION}`;
const MAX_DATA_ENTRIES = 60;
const SHELL = [
  "/",
  "/assets/app.css",
  "/assets/pulse.css",
  "/assets/streak.js",
  "/assets/pulse.js",
  "/assets/app.js",
  "/assets/pwa.js",
  "/assets/favicon.svg",
  "/assets/icons/icon-192.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => ![SHELL_CACHE, DATA_CACHE].includes(key)).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

async function trim(cache) {
  const keys = await cache.keys();
  if (keys.length > MAX_DATA_ENTRIES) await Promise.all(keys.slice(0, keys.length - MAX_DATA_ENTRIES).map((key) => cache.delete(key)));
}

async function networkFirst(request, cacheName, fallbackUrl) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
      if (cacheName === DATA_CACHE) trim(cache);
    }
    return response;
  } catch (error) {
    const cached = (await cache.match(request)) || (fallbackUrl && (await caches.match(fallbackUrl)));
    if (cached) return cached;
    throw error;
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request);
  const refresh = fetch(request).then((response) => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => cached);
  return cached || refresh;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // never touch cross-origin requests (publisher images, share links)

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, SHELL_CACHE, "/"));
  } else if (url.pathname.startsWith("/api/v1/") && !url.pathname.endsWith("/health")) {
    event.respondWith(networkFirst(request, DATA_CACHE));
  } else if (url.pathname.startsWith("/assets/") || url.pathname === "/manifest.webmanifest") {
    event.respondWith(staleWhileRevalidate(request));
  }
});
