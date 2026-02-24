import { useState, useEffect } from 'react'
import { BarChart, Bar, AreaChart, Area, ReferenceLine, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip } from 'recharts'
import { getSkuDetail, getSkuForecast, updateReorderRule } from '../services/api'
import InfoTooltip from './shared/InfoTooltip'

const overlayStyle = {
  position: 'fixed', inset: 0, background: 'rgba(18,11,70,0.35)',
  zIndex: 1000, display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
  padding: '40px 20px', overflowY: 'auto',
}

const modalStyle = {
  background: 'var(--bg-white)', borderRadius: 'var(--radius)',
  width: '100%', maxWidth: 860, boxShadow: 'var(--shadow-lg)',
  border: '1px solid var(--border)',
}

const sectionStyle = {
  padding: '20px 28px', borderBottom: '1px solid var(--border-light)',
}

const labelStyle = {
  fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase',
  letterSpacing: '0.5px', fontWeight: 600, marginBottom: '4px',
}

const valStyle = {
  fontSize: '18px', fontWeight: 700, fontFamily: 'Poppins, sans-serif',
}

function MiniStat({ label, value, color }) {
  return (
    <div style={{ flex: '1 1 120px' }}>
      <div style={labelStyle}>{label}</div>
      <div style={{ ...valStyle, color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
  )
}

export default function SkuDetailModal({ sku, onClose }) {
  const [data, setData] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editingRule, setEditingRule] = useState(false)
  const [ruleForm, setRuleForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  // Escape key to close
  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  // Prevent background scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      getSkuDetail(sku).then(r => r.data).catch(() => null),
      getSkuForecast(sku).then(r => r.data).catch(() => null),
    ]).then(([detail, fc]) => {
      if (cancelled) return
      if (!detail) { setError('SKU not found'); return }
      setData(detail)
      setForecast(fc)
      if (detail.reorder_rule) {
        setRuleForm({ ...detail.reorder_rule })
      } else {
        setRuleForm({ reorder_point: 0, reorder_quantity: 1, lead_time_days: 14, safety_stock: 0 })
      }
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [sku])

  const handleSaveRule = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      await updateReorderRule(sku, ruleForm)
      setEditingRule(false)
      const r = await getSkuDetail(sku)
      setData(r.data)
    } catch (err) {
      setSaveError(err.response?.data?.detail || 'Failed to save reorder rule.')
    } finally {
      setSaving(false)
    }
  }

  const stock = data?.current_stock ?? {}
  const sales = data?.sales_90d ?? {}

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '20px 28px', borderBottom: '1px solid var(--border)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            {data?.image_url ? (
              <img src={data.image_url} alt="" style={{ width: 56, height: 56, borderRadius: 10, objectFit: 'cover', border: '1px solid var(--border-light)' }} />
            ) : (
              <div style={{ width: 56, height: 56, borderRadius: 10, background: 'var(--border-light)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
              </div>
            )}
            <div>
              <span style={{ fontFamily: 'monospace', fontSize: '16px', fontWeight: 700, color: 'var(--accent)' }}>{sku}</span>
              {data && <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '2px' }}>{data.title}</div>}
              {data?.parent_sku && <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>Parent: {data.parent_sku}</div>}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', padding: '6px',
            color: 'var(--text-muted)', fontSize: '20px', lineHeight: 1,
          }}>&times;</button>
        </div>

        {loading ? (
          <div style={{ padding: '60px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading SKU detail...</div>
        ) : error ? (
          <div style={{ padding: '60px', textAlign: 'center', color: 'var(--danger)' }}>{error}</div>
        ) : data && (
          <>
            {/* Stock Overview */}
            <div style={sectionStyle}>
              <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                <MiniStat label={<>On Hand <InfoTooltip text="Physical units in the warehouse. This is the total count ShipHero reports before any allocations." /></>} value={(stock.on_hand ?? 0).toLocaleString()} />
                <MiniStat label={<>Allocated <InfoTooltip text="Units reserved for orders that are placed but not yet shipped. On Hand minus Allocated = Available." /></>} value={(stock.allocated ?? 0).toLocaleString()} />
                <MiniStat label={<>Available <InfoTooltip text="Units actually available to sell. This is the number that matters for stockout risk. When this hits zero, you're losing sales." /></>} value={(stock.available ?? 0).toLocaleString()}
                  color={(stock.available ?? 0) <= 0 ? 'var(--danger)' : undefined} />
                <MiniStat label="Warehouse" value={stock.warehouse || '--'} />
                <MiniStat label={<>Velocity <InfoTooltip text="Average units sold per day over the last 30 days. This is the core input for demand forecasting — it determines when you'll stock out and how much to reorder." /></>} value={`${sales.daily_avg ?? 0}/day`} />
                {data.cost_price != null && (
                  <MiniStat label="Unit Cost" value={`$${data.cost_price.toFixed(2)}`} />
                )}
                {data.cost_price != null && (stock.available ?? 0) > 0 && (
                  <MiniStat label={<>Stock Value <InfoTooltip text="Capital tied up in this SKU (unit cost x available units). High stock value on slow-moving items = cash flow risk." /></>} value={`$${(data.cost_price * (stock.available ?? 0)).toLocaleString()}`} color="var(--accent)" />
                )}
              </div>
            </div>

            {/* Sales Stats */}
            <div style={sectionStyle}>
              <div style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'Poppins, sans-serif', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: 8 }}>
                Sales (Last 90 Days)
                <InfoTooltip text="Historical sales data from Shopify orders. This 90-day window feeds the demand forecasting engine, which uses exponential smoothing to predict future demand." />
              </div>
              <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '16px' }}>
                <MiniStat label="Units Sold" value={(sales.total_units ?? 0).toLocaleString()} />
                <MiniStat label="Revenue" value={`$${(sales.total_revenue ?? 0).toLocaleString()}`} />
                <MiniStat label="Orders" value={(sales.total_orders ?? 0).toLocaleString()} />
              </div>
              {sales.timeline?.length > 0 && (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={sales.timeline} margin={{ top: 5, right: 5, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                    <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} width={35} />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-white)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                      formatter={(val, name) => [val, name === 'units' ? 'Units' : 'Revenue']}
                    />
                    <Bar dataKey="units" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Forecast */}
            {forecast && (
              <div style={sectionStyle}>
                <div style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'Poppins, sans-serif', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: 8 }}>
                  Demand Forecast
                  <InfoTooltip text="AI-generated demand predictions using Holt-Winters exponential smoothing on your sales history. These numbers tell you how many units you're expected to sell, so you know how much inventory to hold." />
                </div>
                <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                  <MiniStat label={<>30-Day <InfoTooltip text="Predicted units to be sold in the next 30 days. Use this for short-term reorder decisions." /></>} value={Math.round(forecast.forecast_30d ?? 0).toLocaleString()} color="var(--accent)" />
                  <MiniStat label={<>60-Day <InfoTooltip text="Predicted units to be sold in the next 60 days. Use this for mid-range planning with longer lead times." /></>} value={Math.round(forecast.forecast_60d ?? 0).toLocaleString()} color="var(--accent)" />
                  <MiniStat label={<>90-Day <InfoTooltip text="Predicted units to be sold in the next 90 days. Use this for quarterly purchasing and production planning." /></>} value={Math.round(forecast.forecast_90d ?? 0).toLocaleString()} color="var(--accent)" />
                  <MiniStat label={<>Days of Stock <InfoTooltip text="How many days until this SKU stocks out at current sell rate. Below 30 days is urgent — factor in supplier lead time (usually 14-35 days) to determine if you need to reorder NOW." /></>}
                    value={forecast.days_of_stock_remaining != null ? `${forecast.days_of_stock_remaining}d` : '--'}
                    color={forecast.below_reorder_point ? 'var(--danger)' : 'var(--success)'}
                  />
                  <MiniStat label={<>Seasonal <InfoTooltip text="Whether this SKU shows repeating sales patterns (weekly or monthly cycles). If yes, the forecast adjusts for seasonality instead of using a flat average." /></>} value={forecast.has_seasonality ? 'Yes' : 'No'} />
                </div>
              </div>
            )}

            {/* Stockout Timeline */}
            {forecast && forecast.rolling_30d_avg > 0 && (
              <div style={sectionStyle}>
                <div style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'Poppins, sans-serif', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: 8 }}>
                  Stock Drawdown Projection
                  <InfoTooltip text="Visual projection of when this SKU will stock out based on current sell velocity. The dashed line shows your reorder point — when stock crosses it, you should have already placed a PO (accounting for lead time)." />
                </div>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart
                    data={(() => {
                      const days = 90
                      const velocity = forecast.rolling_30d_avg
                      const start = stock.available ?? 0
                      const rp = forecast.reorder_point ?? 0
                      const points = []
                      const today = new Date()
                      for (let d = 0; d <= days; d++) {
                        const dt = new Date(today)
                        dt.setDate(dt.getDate() + d)
                        const level = Math.max(start - velocity * d, 0)
                        points.push({
                          date: `${dt.getMonth() + 1}/${dt.getDate()}`,
                          stock: Math.round(level),
                          reorder: rp,
                        })
                        if (level <= 0) break
                      }
                      return points
                    })()}
                    margin={{ top: 5, right: 5, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                    <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} width={45} />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-white)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                      formatter={(val, name) => [val, name === 'stock' ? 'Projected Stock' : 'Reorder Point']}
                    />
                    <Area type="monotone" dataKey="stock" stroke="var(--accent)" fill="var(--accent-light)" strokeWidth={2} />
                    <Area type="monotone" dataKey="reorder" stroke="var(--warning)" fill="none" strokeWidth={1.5} strokeDasharray="5 5" />
                  </AreaChart>
                </ResponsiveContainer>
                <div style={{ display: 'flex', gap: '16px', marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
                  <span><span style={{ display: 'inline-block', width: 12, height: 3, background: 'var(--accent)', marginRight: 4, verticalAlign: 'middle' }} /> Projected Stock</span>
                  <span><span style={{ display: 'inline-block', width: 12, height: 3, background: 'var(--warning)', marginRight: 4, verticalAlign: 'middle', borderTop: '1.5px dashed var(--warning)' }} /> Reorder Point</span>
                  {forecast.days_of_stock_remaining != null && (
                    <span style={{ marginLeft: 'auto', fontWeight: 600, color: forecast.days_of_stock_remaining < 30 ? 'var(--danger)' : 'var(--text-secondary)' }}>
                      Stockout in ~{Math.round(forecast.days_of_stock_remaining)} days
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Reorder Rule */}
            <div style={{ ...sectionStyle, borderBottom: 'none' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'Poppins, sans-serif', display: 'flex', alignItems: 'center', gap: 8 }}>
                  Reorder Rule
                  <InfoTooltip text="Automated reorder settings for this SKU. Reorder Point = when to reorder (stock level trigger). Reorder Qty = how much to order. Lead Time = days until supplier delivers. Safety Stock = buffer to prevent stockouts during lead time." />
                </div>
                {!editingRule && (
                  <button onClick={() => setEditingRule(true)} style={{
                    padding: '5px 14px', borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border)', background: 'var(--bg-white)',
                    fontSize: '12px', fontWeight: 600, color: 'var(--accent)',
                  }}>Edit</button>
                )}
              </div>
              {editingRule && ruleForm ? (
                <div>
                  <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '14px' }}>
                    {[
                      { key: 'reorder_point', label: 'Reorder Point', min: 0 },
                      { key: 'reorder_quantity', label: 'Reorder Qty', min: 1 },
                      { key: 'lead_time_days', label: 'Lead Time (days)', min: 1 },
                      { key: 'safety_stock', label: 'Safety Stock', min: 0 },
                    ].map(f => (
                      <div key={f.key} style={{ flex: '1 1 140px' }}>
                        <label style={{ ...labelStyle, display: 'block' }}>{f.label}</label>
                        <input
                          type="number" min={f.min}
                          value={ruleForm[f.key]}
                          onChange={e => {
                            const val = parseInt(e.target.value)
                            setRuleForm({ ...ruleForm, [f.key]: isNaN(val) ? f.min : Math.max(val, f.min) })
                          }}
                          style={{
                            width: '100%', padding: '8px 12px', borderRadius: 'var(--radius-sm)',
                            border: '1px solid var(--border)', fontSize: '13px', outline: 'none',
                          }}
                        />
                      </div>
                    ))}
                  </div>
                  {saveError && (
                    <div style={{ color: 'var(--danger)', fontSize: '12px', marginBottom: '10px' }}>{saveError}</div>
                  )}
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button onClick={handleSaveRule} disabled={saving} style={{
                      padding: '8px 20px', borderRadius: 'var(--radius-sm)',
                      border: 'none', background: 'var(--accent)', color: '#fff',
                      fontSize: '13px', fontWeight: 600, opacity: saving ? 0.6 : 1,
                    }}>
                      {saving ? 'Saving...' : 'Save'}
                    </button>
                    <button onClick={() => { setEditingRule(false); setSaveError(null) }} style={{
                      padding: '8px 20px', borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border)', background: 'var(--bg-white)',
                      fontSize: '13px', fontWeight: 500,
                    }}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                  {data.reorder_rule ? (
                    <>
                      <MiniStat label="Reorder Point" value={data.reorder_rule.reorder_point} />
                      <MiniStat label="Reorder Qty" value={data.reorder_rule.reorder_quantity} />
                      <MiniStat label="Lead Time" value={`${data.reorder_rule.lead_time_days}d`} />
                      <MiniStat label="Safety Stock" value={data.reorder_rule.safety_stock} />
                    </>
                  ) : (
                    <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
                      No reorder rule configured. Click "Edit" to set one up.
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
