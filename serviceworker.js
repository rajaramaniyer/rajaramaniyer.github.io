// 1. Versioning: Change this string every time you update your app!
const staticDevCoffee = "web-harmonium-v2"; 

const assets = [
  "/",
  "/webharmonium.html",
  "/harmonium-kannan-orig.wav"
];

self.addEventListener("install", installEvent => {
  // 2. Immediate Takeover: Forces this new worker to become active right away
  self.skipWaiting();
  
  installEvent.waitUntil(
    caches.open(staticDevCoffee).then(cache => {
      return cache.addAll(assets);
    })
  );
});

// Clean up old caches when the new version activates
self.addEventListener("activate", activateEvent => {
  activateEvent.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== staticDevCoffee)
            .map(key => caches.delete(key))
      );
    })
  );
});

self.addEventListener("fetch", fetchEvent => {
  fetchEvent.respondWith(
    caches.match(fetchEvent.request).then(res => {
      // 3. Network First (or Stale-While-Revalidate)
      // This logic says: If we have it in cache, return it, 
      // but also go get the fresh version from the network.
      return res || fetch(fetchEvent.request);
    })
  );
});