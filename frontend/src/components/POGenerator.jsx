import { useState, useEffect } from 'react'
import { getPOSuggestions, getPurchaseOrders } from '../services/api'
import { thStyle, tdStyle, urgencyConfig } from './shared/tableStyles'

export default function POGenerator() {
  const [suggestions, setSuggestions] = useState([])
  const [openPOs, setOpenPOs] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [suggestError, setSuggestError] = useState(null)
  const [poError, setPOError] = useState(null)
  const [tab, setTab] = useState('suggestions')

  useEffect(() => {
    Promise.all([
      getPOSuggestions()
        .then(r => setSuggestions(r.data.items || []))
        .catch(err => {
          setSuggestions([])
          setSuggestError(err.response?.data?.detail || 'Failed to load suggestions. Check that the backend is running.')
        }),
      getPurchaseOrders()
        .then(r => {
          const data = r.data
          setOpenPOs(data.items || [])
          if (data.error) setPOError(data.error)
        })
        .catch(err => {
          setOpenPOs([])
          setPOError(err.response?.data?.detail || 'Failed to load purchase orders.')
        }),
    ]).finally(() => setLoading(false))
  }, [])

  const toggleSelect = (sku) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(sku)) next.delete(sku); else next.add(sku)
      return next
    })
  }

  const selectAll = () => {
    setSelected(prev => prev.size === suggestions.length ? new Set() : new Set(suggestions.map(s => s.sku)))
  }

  const generatePO = () => {
    const items = suggestions.filter(s => selected.has(s.sku))
    // Sanitize CSV fields to prevent formula injection
    const sanitize = (val) => {
      const s = String(val ?? '')
      if (/^[=+\-@\t\r]/.test(s)) return `'${s}`
      return s
    }
    const csvEscape = (val) => {
      const s = sanitize(val)
      return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s
    }
    const csv = [
      'SKU,Title,Quantity,Unit Velocity,Lead Time',
      ...items.map(i => [
        csvEscape(i.sku ?? ''),
        csvEscape(i.title ?? ''),
        i.suggested_quantity ?? 0,
        i.daily_velocity ?? 0,
        i.lead_time_days ?? 0,
      ].join(',')),
    ].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `PO-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 100)
  }

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: '24px', textAlign: 'center' }}>Loading...</div>
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: '4px', marginBottom: '20px', background: 'var(--bg-white)', padding: '4px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', width: 'fit-content' }}>
        {['suggestions', 'open'].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: '8px 20px', borderRadius: '6px', border: 'none',
            background: tab === t ? 'var(--accent)' : 'transparent',
            color: tab === t ? '#fff' : 'var(--text-secondary)',
            fontSize: '13px', fontWeight: 600, transition: 'all 0.15s',
          }}>
            {t === 'suggestions' ? `Suggestions (${suggestions.length})` : `Open POs (${openPOs.length})`}
          </button>
        ))}
      </div>

      {tab === 'suggestions' && (
        <div style={{
          background: 'var(--bg-white)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
        }}>
          {suggestError ? (
            <div style={{ padding: '40px', textAlign: 'center' }}>
              <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 6 }}>Error loading suggestions</div>
              <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{suggestError}</div>
            </div>
          ) : suggestions.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <svg width="40" height="40" fill="none" viewBox="0 0 24 24" stroke="var(--success)" strokeWidth="1.5" style={{ marginBottom: 12 }}>
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>No orders needed</div>
              <div>All stock levels are healthy.</div>
            </div>
          ) : (
            <>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '14px 16px', borderBottom: '1px solid var(--border)',
              }}>
                <label style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                  <input type="checkbox" checked={selected.size === suggestions.length} onChange={selectAll}
                    style={{ accentColor: 'var(--accent)', width: 16, height: 16 }} />
                  Select all ({selected.size} selected)
                </label>
                <button disabled={selected.size === 0} onClick={generatePO} style={{
                  padding: '8px 20px', borderRadius: 'var(--radius-sm)', border: 'none',
                  background: selected.size > 0 ? 'var(--accent)' : 'var(--border)',
                  color: selected.size > 0 ? '#fff' : 'var(--text-muted)',
                  fontSize: '13px', fontWeight: 600, transition: 'all 0.15s',
                }}>
                  Export CSV ({selected.size})
                </button>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ ...thStyle, width: 40 }}></th>
                      <th style={thStyle}>Urgency</th>
                      <th style={thStyle}>SKU</th>
                      <th style={thStyle}>Title</th>
                      <th style={thStyle}>Stock</th>
                      <th style={thStyle}>Qty to Order</th>
                      <th style={thStyle}>Velocity/day</th>
                      <th style={thStyle}>Days Left</th>
                    </tr>
                  </thead>
                  <tbody>
                    {suggestions.map((s, i) => {
                      const cfg = urgencyConfig[s.urgency] || urgencyConfig.low
                      return (
                        <tr key={s.sku} style={{ background: i % 2 === 0 ? 'var(--bg-white)' : 'var(--bg-primary)' }}>
                          <td style={tdStyle}>
                            <input type="checkbox" checked={selected.has(s.sku)} onChange={() => toggleSelect(s.sku)}
                              style={{ accentColor: 'var(--accent)', width: 16, height: 16 }} />
                          </td>
                          <td style={tdStyle}>
                            <span style={{
                              padding: '3px 10px', borderRadius: '20px', fontSize: '11px',
                              fontWeight: 700, textTransform: 'uppercase', background: cfg.bg, color: cfg.color,
                            }}>{s.urgency}</span>
                          </td>
                          <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 600, color: 'var(--accent)' }}>{s.sku}</td>
                          <td style={tdStyle}>{s.title}</td>
                          <td style={{ ...tdStyle, color: (s.current_stock ?? 0) <= 0 ? 'var(--danger)' : 'var(--text-primary)', fontWeight: 600 }}>{s.current_stock ?? 0}</td>
                          <td style={{ ...tdStyle, fontWeight: 700, color: 'var(--accent)' }}>{s.suggested_quantity ?? 0}</td>
                          <td style={tdStyle}>{s.daily_velocity ?? 0}</td>
                          <td style={tdStyle}>{s.days_of_stock_remaining != null ? `${s.days_of_stock_remaining}d` : '0d'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'open' && (
        <div style={{
          background: 'var(--bg-white)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
        }}>
          {poError ? (
            <div style={{ padding: '40px', textAlign: 'center' }}>
              <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 6 }}>Error loading purchase orders</div>
              <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{poError}</div>
            </div>
          ) : openPOs.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
              No open purchase orders from ShipHero.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr>
                  <th style={thStyle}>PO Number</th>
                  <th style={thStyle}>Status</th>
                  <th style={thStyle}>Expected Date</th>
                  <th style={thStyle}>Line Items</th>
                </tr>
              </thead>
              <tbody>
                {openPOs.map((po, i) => (
                  <tr key={po.id} style={{ background: i % 2 === 0 ? 'var(--bg-white)' : 'var(--bg-primary)' }}>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{po.po_number || po.id}</td>
                    <td style={tdStyle}>{po.status}</td>
                    <td style={tdStyle}>{po.date_expected || '--'}</td>
                    <td style={tdStyle}>{po.line_items?.length || 0} items</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
