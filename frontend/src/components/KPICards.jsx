import InfoTooltip from './shared/InfoTooltip'

const cardStyle = {
  background: 'var(--bg-white)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '20px 24px',
  flex: '1 1 150px',
  boxShadow: 'var(--shadow-sm)',
  transition: 'box-shadow 0.2s ease',
}

function KPICard({ label, value, subtitle, color, tooltip }) {
  return (
    <div style={cardStyle}
      onMouseEnter={e => e.currentTarget.style.boxShadow = 'var(--shadow-md)'}
      onMouseLeave={e => e.currentTarget.style.boxShadow = 'var(--shadow-sm)'}
    >
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '12px',
      }}>
        <span style={{
          fontSize: '11px',
          color: 'var(--text-secondary)',
          textTransform: 'uppercase',
          letterSpacing: '0.6px',
          fontWeight: 600,
        }}>
          {label}
        </span>
        {tooltip && <InfoTooltip text={tooltip} />}
      </div>
      <div style={{
        fontSize: '24px',
        fontWeight: 700,
        color: color || 'var(--text-primary)',
        fontFamily: 'Poppins, sans-serif',
        lineHeight: 1.1,
      }}>
        {value}
      </div>
      {subtitle && (
        <div style={{
          fontSize: '12px',
          color: 'var(--text-secondary)',
          marginTop: '6px',
        }}>
          {subtitle}
        </div>
      )}
    </div>
  )
}

export default function KPICards({ data }) {
  if (!data) return null

  const fmt = (n) => n?.toLocaleString() ?? '--'
  const fmtMoney = (n) => `$${(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`

  const cards = [
    {
      label: 'Active SKUs',
      value: fmt(data.total_skus),
      tooltip: 'Total unique product variants being tracked across Shopify and ShipHero. Each size/color combination counts as a separate SKU.',
    },
    {
      label: 'On Hand Units',
      value: fmt(data.total_on_hand_units),
      tooltip: 'Total physical units sitting in your warehouses right now. This is the number ShipHero reports as physically present — not yet sold or shipped.',
    },
    {
      label: 'Orders (30d)',
      value: fmt(data.orders_last_30d),
      tooltip: 'Number of orders placed in the last 30 days from Shopify. Used to calculate sales velocity and demand forecasts.',
    },
    {
      label: 'Revenue (30d)',
      value: fmtMoney(data.revenue_last_30d),
      tooltip: 'Total revenue from orders in the last 30 days. This drives the demand forecasting engine — higher revenue SKUs get prioritized for reorder alerts.',
    },
    {
      label: 'Units Sold (30d)',
      value: fmt(data.units_sold_last_30d),
      tooltip: 'Total units sold across all SKUs in the last 30 days. Compared against on-hand inventory to calculate sell-through rate.',
    },
    {
      label: 'Sell-Through Rate',
      value: `${data.sell_through_rate ?? 0}%`,
      subtitle: 'units sold / (sold + on hand)',
      tooltip: 'How fast you\'re selling through inventory. High rate (>50%) means you\'re turning stock quickly — good for cash flow, but watch for stockouts. Low rate (<20%) suggests overstock.',
    },
    {
      label: 'Reorder Alerts',
      value: data.skus_below_reorder ?? '--',
      color: data.skus_below_reorder > 0 ? 'var(--danger)' : 'var(--success)',
      tooltip: 'SKUs that have dropped below their reorder point. These need purchase orders placed NOW to avoid stockouts, accounting for supplier lead time.',
    },
    {
      label: 'Revenue at Risk',
      value: fmtMoney(data.revenue_at_risk_daily),
      subtitle: 'daily loss from stockouts',
      color: (data.revenue_at_risk_daily ?? 0) > 0 ? 'var(--danger)' : 'var(--success)',
      tooltip: 'Estimated daily revenue you\'re LOSING because products are out of stock. Calculated from each stockout SKU\'s average daily sales velocity x price. This is money left on the table every day.',
    },
    {
      label: 'Inventory Cost',
      value: fmtMoney(data.total_inventory_cost),
      subtitle: 'total at cost price',
      tooltip: 'Total value of all inventory at cost price (what you paid your supplier). Helps track how much capital is tied up in stock. Too high = cash flow risk from overstock.',
    },
  ]

  return (
    <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
      {cards.map((c) => <KPICard key={c.label} {...c} />)}
    </div>
  )
}
