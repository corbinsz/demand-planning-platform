/** Error hook. Reports a short message to our API. No third-party SDK is bundled. */
export function installMonitoring() {
  const send = (message) => {
    const text = String(message || '').slice(0, 300)
    if (!text) return
    const dsn = import.meta.env.VITE_ERROR_SINK_URL || '/api/client-errors'
    fetch(dsn, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, path: window.location.pathname }),
    }).catch(() => {})
  }
  window.addEventListener('error', (event) => send(event.message))
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason
    send(reason && reason.message ? reason.message : reason)
  })
}
