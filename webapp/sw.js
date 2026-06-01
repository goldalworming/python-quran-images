// Service worker: keeps the PWA usable offline and lets standalone
// launches succeed even when HTTP caches are stale.
//
// Strategy: network-first for same-origin GETs, falling back to the
// runtime cache when offline. We intentionally do NOT precache by URL
// version — any mismatch (e.g. `app.js?v=008` referenced from an old
// shell URL list) would make `cache.addAll` throw and block install
// entirely. Version-agnostic caching avoids that whole class of bugs.
//
// Bump SW_VERSION whenever this file's logic changes — the byte-diff
// triggers the browser to fetch + install this SW as an update, and the
// version-suffixed CACHE_NAME makes the activate handler evict every
// older runtime cache automatically. (Do NOT put the version in the SW
// URL like `sw.js?v=011`: that registers a *different* SW under the same
// scope instead of updating the existing one.)
//
// Page AVIF images bypass the SW so the browser's HTTP cache handles
// them (there are 604 of them; we don't want to fill the runtime cache).

const SW_VERSION = "013";
const CACHE_NAME = "quran-runtime-" + SW_VERSION;
// Persistent cache for page AVIFs explicitly precached by the page when
// a surah is bookmarked. Survives SW version bumps so users don't lose
// offline pages whenever the shell is updated.
const PAGES_CACHE = "quran-pages-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("message", (event) => {
  if (event.data === "GET_VERSION" && event.source) {
    event.source.postMessage({ type: "SW_VERSION", version: SW_VERSION });
  }
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== PAGES_CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Page AVIFs: cache-first. The runtime cache is populated explicitly
  // by the page (precacheSurahPages) when a surah is bookmarked, so
  // bookmarked surahs work offline while non-bookmarked pages still go
  // straight to network without bloating the cache.
  if (url.pathname.endsWith(".avif")) {
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req))
    );
    return;
  }

  // Bypass the HTTP cache and revalidate with the server every time.
  // Server can still 304 if nothing changed, but stale shell files (which
  // previously caused blank PWA launches) can never sneak through.
  event.respondWith(
    fetch(req, { cache: "no-cache" })
      .then((resp) => {
        if (resp && resp.ok && resp.type === "basic") {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
        }
        return resp;
      })
      .catch(() =>
        caches.match(req).then((cached) => {
          if (cached) return cached;
          if (req.mode === "navigate") return caches.match("./index.html");
        })
      )
  );
});
