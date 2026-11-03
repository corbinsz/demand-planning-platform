/** Privacy-friendly analytics. No cookies, no vendor, off unless the owner sets an endpoint. */
export function track(name, props = {}) {
  if (typeof navigator !== 'undefined' && navigator.doNotTrack === '1') return
  const endpoint = import.meta.env.VITE_ANALYTICS_ENDPOINT
  if (!endpoint) return
  const body = JSON.stringify({
    event: String(name).slice(0, 80),
    path: window.location.pathname,
    props,
    t: Date.now(),
  })
  if (navigator.sendBeacon) {
    navigator.sendBeacon(endpoint, new Blob([body], { type: 'application/json' }))
    return
  }
  fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {})
}
