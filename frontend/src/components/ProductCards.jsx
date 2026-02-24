import InfoTooltip from './shared/InfoTooltip'

const HEALTH_INFO = {
  'Out of Stock': 'Zero units available — you are losing sales right now.',
  'Low Stock': 'Below 10 units. At risk of stocking out soon.',
  'Excess': 'Over 500 units. Capital may be tied up in overstock.',
  'Healthy': 'Stock levels are in a good range.',
}

function StockBar({ available, onHand }) {
  const pct = onHand > 0 ? Math.min((available / onHand) * 100, 100) : 0
  let color = 'var(--success)'
  if (available <= 0) color = 'var(--danger)'
  else if (available <= 10) color = 'var(--warning)'
  else if (available > 500) color = 'var(--excess)'
  return (
    <div style={{ height: 6, borderRadius: 3, background: 'var(--border-light)', overflow: 'hidden', marginTop: 6 }}>
      <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width 0.3s' }} />
    </div>
  )
}

function HealthBadge({ available }) {
  let label, bg, color
  if (available <= 0) { label = 'Out of Stock'; bg = 'var(--danger-bg)'; color = 'var(--danger)' }
  else if (available <= 10) { label = 'Low Stock'; bg = 'var(--warning-bg)'; color = 'var(--warning)' }
  else if (available > 500) { label = 'Excess'; bg = 'var(--excess-bg)'; color = 'var(--excess)' }
  else { label = 'Healthy'; bg = 'var(--success-bg)'; color = 'var(--success)' }
  return (
    <InfoTooltip text={HEALTH_INFO[label]}>
      <span style={{ padding: '3px 10px', borderRadius: '20px', fontSize: '10px', fontWeight: 700, background: bg, color, whiteSpace: 'nowrap', cursor: 'help' }}>
        {label}
      </span>
    </InfoTooltip>
  )
}

export default function ProductCards({ items, onSelectSku }) {
  if (!items || items.length === 0) return null

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '16px' }}>
      {items.map((item, i) => (
        <div
          key={`${item.sku}-${i}`}
          onClick={() => onSelectSku(item.sku)}
          style={{
            background: 'var(--bg-white)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', overflow: 'hidden', cursor: 'pointer',
            boxShadow: 'var(--shadow-sm)', transition: 'box-shadow 0.2s, transform 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.boxShadow = 'var(--shadow-md)'; e.currentTarget.style.transform = 'translateY(-2px)' }}
          onMouseLeave={e => { e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; e.currentTarget.style.transform = 'none' }}
        >
          {/* Image */}
          <div style={{
            height: 160, background: 'var(--bg-primary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            borderBottom: '1px solid var(--border-light)',
          }}>
            {item.image_url ? (
              <img src={item.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              <svg width="40" height="40" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth="1">
                <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>
              </svg>
            )}
          </div>

          {/* Info */}
          <div style={{ padding: '14px 16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
              <span style={{ fontFamily: 'monospace', fontSize: '12px', fontWeight: 700, color: 'var(--accent)' }}>{item.sku}</span>
              <HealthBadge available={item.quantity_available} />
            </div>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8, lineHeight: 1.3 }}>
              {item.title || 'Unknown'}
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-secondary)' }}>
              <span>On Hand: <strong style={{ color: 'var(--text-primary)' }}>{item.quantity_on_hand}</strong></span>
              <span>Avail: <strong style={{ color: item.quantity_available <= 0 ? 'var(--danger)' : 'var(--text-primary)' }}>{item.quantity_available}</strong></span>
            </div>
            <StockBar available={item.quantity_available} onHand={item.quantity_on_hand} />

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontSize: '11px', color: 'var(--text-muted)' }}>
              <span>{item.warehouse || 'No warehouse'}</span>
              {item.cost_price != null && <span style={{ fontWeight: 600 }}>${item.cost_price.toFixed(2)}</span>}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
