// AI守秘人 - Service Worker v1.0.0
const CACHE_NAME = 'coc-keeper-v1';

// 需要预缓存的资源
const PRECACHE_URLS = [
  '/',
  '/static/manifest.json',
];

// 安装事件：预缓存核心资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
    })
  );
  // 强制等待中的 Service Worker 被激活
  self.skipWaiting();
});

// 激活事件：清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  // 立即接管所有页面
  self.clients.claim();
});

// 网络优先策略（API 请求走网络，静态资源走缓存）
self.addEventListener('fetch', (event) => {
  const request = event.request;

  // 只处理 GET 请求
  if (request.method !== 'GET') return;

  // API 请求：网络优先，超时回退到缓存
  if (request.url.includes('/api/')) {
    event.respondWith(networkFirstWithTimeout(request, 5000));
    return;
  }

  // 静态资源：缓存优先，网络回退
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      return cachedResponse || fetch(request).then((networkResponse) => {
        // 将新资源加入缓存
        if (networkResponse && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseClone);
          });
        }
        return networkResponse;
      }).catch(() => {
        // 完全离线时返回 fallback
        return caches.match('/');
      });
    })
  );
});

/**
 * 网络优先，超时降级到缓存
 */
async function networkFirstWithTimeout(request, timeoutMs) {
  const timeoutPromise = new Promise((_, reject) =>
    setTimeout(() => reject(new Error('timeout')), timeoutMs)
  );

  try {
    const networkResponse = await Promise.race([
      fetch(request),
      timeoutPromise,
    ]);
    if (networkResponse && networkResponse.status === 200) {
      const responseClone = networkResponse.clone();
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, responseClone);
    }
    return networkResponse;
  } catch {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // 如果缓存也没有，返回一个离线提示
    return new Response(
      JSON.stringify({ error: '离线模式，无法连接服务器' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
