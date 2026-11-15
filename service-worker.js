'use strict';

// Offline shell and local Python runtime. Bump the cache name when packaged files change.
const CACHE_NAME = 'codeflow-shell-v9';
const SHELL_ASSETS = [
  './index.html',
  './app.js',
  './assets/sakura-watercolor-hero.jpg',
  './reference.html',
  './reference.js',
  './manifest.json',
  './codeflow.ico',
  './icons/codeflow-180.png',
  './icons/codeflow-192.png',
  './icons/codeflow-512.png',
  './python-runner-worker.js',
];
const PYODIDE_ASSETS = [
  './pyodide/pyodide.js',
  './pyodide/pyodide.mjs',
  './pyodide/pyodide.asm.mjs',
  './pyodide/pyodide.asm.wasm',
  './pyodide/python_stdlib.zip',
  './pyodide/pyodide-lock.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      // Cache the complete local runtime too: successful installation is offline-ready.
      await cache.addAll([...SHELL_ASSETS, ...PYODIDE_ASSETS]);
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys();
      const staleShellCaches = cacheNames.filter(
        (name) => name.startsWith('codeflow-shell-') && name !== CACHE_NAME,
      );
      await Promise.all(staleShellCaches.map((name) => caches.delete(name)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener('fetch', (event) => {
  const fetchRequest = event.request;
  if (fetchRequest.method !== 'GET') return;

  const requestUrl = new URL(fetchRequest.url);
  if (requestUrl.origin !== self.location.origin) return;

  // The local tutor API must reach the server and must never enter the offline cache.
  const apiBasePath = new URL('./api/', self.registration.scope).pathname;
  if (requestUrl.pathname.startsWith(apiBasePath)) return;

  if (fetchRequest.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const networkResponse = await fetch(fetchRequest);
          if (networkResponse.ok) {
            const cache = await caches.open(CACHE_NAME);
            await cache.put(fetchRequest, networkResponse.clone());
          }
          return networkResponse;
        } catch (_) {
          return (
            (await caches.match(fetchRequest, { ignoreSearch: true })) ||
            (await caches.match('./index.html')) ||
            Response.error()
          );
        }
      })(),
    );
    return;
  }

  event.respondWith(
    (async () => {
      const cachedResponse = await caches.match(fetchRequest, { ignoreSearch: true });
      if (cachedResponse) return cachedResponse;

      const networkResponse = await fetch(fetchRequest);
      if (networkResponse.ok && networkResponse.type === 'basic') {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(fetchRequest, networkResponse.clone());
      }
      return networkResponse;
    })(),
  );
});
