import { useState, useEffect } from 'react'
import { getReorderAlerts } from '../services/api'
import { urgencyConfig } from './shared/tableStyles'

export default function ReorderAlerts() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getReorderAlerts()
      .then(r => setAlerts(r.data?.items || []))
      .catch(err => {
        setAlerts([])
        setError(err.response?.data?.detail || 'Failed to load reorder alerts.')
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: '24px', textAlign: 'center' }}>Loading alerts...</div>
  }

  if (error) {
    return (
      <div style={{
        background: 'var(--bg-white)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: '40px', textAlign: 'center',
        boxShadow: 'var(--shadow-sm)',
      }}>
        <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 6 }}>Error loading alerts</div>
        <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{error}</div>
      </div>
    )
  }

  if (alerts.length === 0) {
    return (
      <div style={{
        background: 'var(--bg-white)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: '40px', textAlign: 'center',
        color: 'var(--text-muted)', boxShadow: 'var(--shadow-sm)',
      }}>
        <svg width="40" height="40" fill="none" viewBox="0 0 24 24" stroke="var(--success)" strokeWidth="1.5" style={{ marginBottom: 12 }}>
          <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
        <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>All Clear</div>
        <div>All SKUs are above their reorder points.</div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {alerts.map(alert => {
        const cfg = urgencyConfig[alert.urgency] || urgencyConfig.low
        return (
          <div key={alert.sku} style={{
            background: 'var(--bg-white)', border: '1px solid var(--border)',
            borderLeft: `4px solid ${cfg.border}`,
            borderRadius: 'var(--radius)', padding: '16px 20px',
            display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <span style={{
              padding: '4px 12px', borderRadius: '20px', fontSize: '11px',
              fontWeight: 700, textTransform: 'uppercase',
              background: cfg.bg, color: cfg.color, minWidth: '70px', textAlign: 'center',
            }}>
              {alert.urgency || 'low'}
            </span>
            <div style={{ flex: '1 1 200px' }}>
              <div style={{ fontFamily: 'monospace', fontWeight: 600, fontSize: '14px', color: 'var(--accent)' }}>{alert.sku}</div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{alert.title}</div>
            </div>
            <div style={{ textAlign: 'right', fontSize: '13px' }}>
              <div>Stock: <strong style={{ color: 'var(--danger)' }}>{alert.current_stock}</strong></div>
              <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                Reorder at: {alert.reorder_point}
              </div>
            </div>
            <div style={{ textAlign: 'right', fontSize: '13px' }}>
              <div>Order: <strong style={{ color: 'var(--accent)' }}>{alert.suggested_reorder_qty}</strong> units</div>
              <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                {alert.days_of_stock_remaining != null
                  ? `${alert.days_of_stock_remaining}d left`
                  : 'Stockout'}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
