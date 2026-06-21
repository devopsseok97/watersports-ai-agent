// 서퍼스트 PWA 서비스 워커 — 설치 가능성 확보용 (캐싱 없음, 항상 네트워크 우선)
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());
