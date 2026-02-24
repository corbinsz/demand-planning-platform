import { useState, useEffect, useMemo } from 'react'
import ForecastChart from '../components/ForecastChart'
import SkuDetailModal from '../components/SkuDetailModal'
import { getForecasts } from '../services/api'
import { thStyle, tdStyle } from '../components/shared/tableStyles'
import SortableHeader from '../components/shared/SortableHeader'
import InfoTooltip from '../components/shared/InfoTooltip'
import Pagination from '../components/shared/Pagination'

const filterBtnStyle = (active) => ({
  padding: '6px 14px', borderRadius: '6px', border: 'none',
  background: active ? 'var(--accent)' : 'transparent',
  color: active ? '#fff' : 'var(--text-secondary)',
  fontSize: '12px', fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
})

function SummaryCard({ label, value, sub, color, tooltip }) {
  return (
    <div style={{
      background: 'var(--bg-white)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '18px 22px', flex: '1 1 150px',
      boxShadow: 'var(--shadow-sm)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>{label}</span>
        {tooltip && <InfoTooltip text={tooltip} />}
      </div>
      <div style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif', color: color || 'var(--text-primary)', lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

function DaysLeftBar({ days, leadTime }) {
  if (days == null) return <span style={{ color: 'var(--text-muted)' }}>--</span>
  const maxDays = 180
  const pct = Math.min((days / maxDays) * 100, 100)
  const danger = days < leadTime
  const warning = days < leadTime * 2
  const color = danger ? 'var(--danger)' : warning ? 'var(--warning)' : 'var(--success)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'var(--border-light)', overflow: 'hidden', minWidth: 50 }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width 0.3s' }} />
      </div>
      <span style={{ fontSize: '12px', fontWeight: 600, color, minWidth: 35, textAlign: 'right' }}>{days}d</span>
    </div>
  )
}

export default function Forecasting() {
  const [forecasts, setForecasts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedSku, setSelectedSku] = useState(null)
  const [sortBy, setSortBy] = useState('days_of_stock_remaining')
  const [sortDir, setSortDir] = useState('asc')
  const [filter, setFilter] = useState('all') // 'all' | 'reorder' | 'critical' | 'healthy'
  const [page, setPage] = useState(1)
  const perPage = 25

  useEffect(() => {
    getForecasts({ page: 1, per_page: 200 })
      .then(r => setForecasts(r.data?.items || []))
      .catch(err => {
        setForecasts([])
        setError(err.response?.data?.detail || 'Failed to load forecasts. Make sure the backend is running and data has been synced.')
      })
      .finally(() => setLoading(false))
  }, [])

  const handleSort = (field, dir) => { setSortBy(field); setSortDir(dir); setPage(1) }

  // Computed summaries
  const summary = useMemo(() => {
    if (!forecasts.length) return {}
    const reorderCount = forecasts.filter(f => f.below_reorder_point).length
    const criticalCount = forecasts.filter(f => f.days_of_stock_remaining != null && f.days_of_stock_remaining < f.lead_time_days).length
    const seasonalCount = forecasts.filter(f => f.has_seasonality).length
    const avgDaysLeft = forecasts.filter(f => f.days_of_stock_remaining != null)
    const avgDays = avgDaysLeft.length > 0 ? Math.round(avgDaysLeft.reduce((s, f) => s + f.days_of_stock_remaining, 0) / avgDaysLeft.length) : null
    const totalForecast30 = forecasts.reduce((s, f) => s + (f.forecast_30d ?? 0), 0)
    return { reorderCount, criticalCount, seasonalCount, avgDays, totalForecast30 }
  }, [forecasts])

  const filteredForecasts = useMemo(() => {
    let items = [...forecasts]
    if (filter === 'reorder') items = items.filter(f => f.below_reorder_point)
    else if (filter === 'critical') items = items.filter(f => f.days_of_stock_remaining != null && f.days_of_stock_remaining < f.lead_time_days)
    else if (filter === 'healthy') items = items.filter(f => !f.below_reorder_point)

    items.sort((a, b) => {
      let av = a[sortBy], bv = b[sortBy]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return items
  }, [forecasts, sortBy, sortDir, filter])

  const totalPages = Math.max(1, Math.ceil(filteredForecasts.length / perPage))
  const pageItems = filteredForecasts.slice((page - 1) * perPage, page * perPage)

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>Demand Forecasting</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          AI-powered demand predictions using exponential smoothing with seasonality detection. Tells you exactly what to reorder and when.
        </p>
      </div>

      {/* Summary KPIs */}
      {!loading && !error && forecasts.length > 0 && (
        <div style={{ display: 'flex', gap: '14px', marginBottom: '24px', flexWrap: 'wrap' }}>
          <SummaryCard
            label="Total 30-Day Demand"
            value={Math.round(summary.totalForecast30 ?? 0).toLocaleString()}
            sub="predicted units across all SKUs"
            color="var(--accent)"
            tooltip="Total units the forecasting engine predicts you'll sell across ALL products in the next 30 days. This is the aggregate demand signal for your entire catalog."
          />
          <SummaryCard
            label="Need Reorder"
            value={summary.reorderCount ?? 0}
            sub="SKUs below reorder point"
            color={(summary.reorderCount ?? 0) > 0 ? 'var(--danger)' : 'var(--success)'}
            tooltip="SKUs where current stock has dropped below the reorder point. These need purchase orders placed NOW — factor in supplier lead time to avoid stockouts."
          />
          <SummaryCard
            label="Critical Risk"
            value={summary.criticalCount ?? 0}
            sub="will stock out before PO arrives"
            color={(summary.criticalCount ?? 0) > 0 ? 'var(--danger)' : 'var(--success)'}
            tooltip="SKUs where days of stock remaining is LESS than their lead time. Even if you order today, these will likely stock out before the shipment arrives. Consider expedited shipping or transferring stock between warehouses."
          />
          <SummaryCard
            label="Avg Days of Stock"
            value={summary.avgDays != null ? `${summary.avgDays}d` : '--'}
            sub="across all SKUs"
            tooltip="Average runway across all SKUs. Below 30 days means your catalog is running thin. Above 120 days may indicate overstock across the board."
          />
          <SummaryCard
            label="Seasonal SKUs"
            value={summary.seasonalCount ?? 0}
            sub="detected repeating patterns"
            color="var(--accent)"
            tooltip="SKUs where the algorithm detected weekly or monthly sales cycles (autocorrelation > 0.3). These get seasonal adjustments in their forecast instead of a flat average."
          />
        </div>
      )}

      <ForecastChart />

      <div style={{ marginTop: '32px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: 10 }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, fontFamily: 'Poppins, sans-serif', display: 'flex', alignItems: 'center', gap: 8 }}>
            SKU Forecast Details
            <InfoTooltip text="Click any row to open the full SKU detail with stock drawdown chart, sales history, and reorder rule editor. The 'Days Left' bar shows how much runway you have — red means you'll stock out before a new PO can arrive." />
          </h3>
          <div style={{ display: 'flex', gap: 4, background: 'var(--bg-white)', padding: 3, borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            {[
              { key: 'all', label: 'All' },
              { key: 'reorder', label: `Reorder (${summary.reorderCount ?? 0})` },
              { key: 'critical', label: `Critical (${summary.criticalCount ?? 0})` },
              { key: 'healthy', label: 'Healthy' },
            ].map(f => (
              <button key={f.key} onClick={() => { setFilter(f.key); setPage(1) }} style={filterBtnStyle(filter === f.key)}>{f.label}</button>
            ))}
          </div>
        </div>

        <div style={{
          background: 'var(--bg-white)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
        }}>
          {loading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Generating forecasts...</div>
          ) : error ? (
            <div style={{ padding: '40px', textAlign: 'center' }}>
              <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: '6px' }}>Error loading forecasts</div>
              <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{error}</div>
            </div>
          ) : filteredForecasts.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
              {filter !== 'all' ? 'No SKUs match this filter.' : 'No forecast data available. Sync your inventory and orders first.'}
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1100px' }}>
                <thead>
                  <tr>
                    <SortableHeader label="SKU" field="sku" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                    <SortableHeader label="Title" field="title" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                    <th style={thStyle}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        Velocity <InfoTooltip text="Average units sold per day over the last 30 days. This is the most important number — it drives all forecast calculations." />
                      </span>
                    </th>
                    <SortableHeader label="30d Forecast" field="forecast_30d" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                    <SortableHeader label="60d Forecast" field="forecast_60d" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                    <SortableHeader label="90d Forecast" field="forecast_90d" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                    <SortableHeader label="Stock" field="current_stock" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                    <th style={{ ...thStyle, minWidth: 150 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        Days Left <InfoTooltip text="Days until stockout at current sell rate. Red = will run out before a PO can arrive (lead time). Yellow = less than 2x lead time. Green = comfortable runway." />
                      </span>
                    </th>
                    <th style={thStyle}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        Seasonal <InfoTooltip text="Whether weekly or monthly sales patterns were detected. If yes, the forecast accounts for upcoming high/low periods instead of using a flat average." />
                      </span>
                    </th>
                    <th style={thStyle}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        Status <InfoTooltip text="REORDER = stock is below the reorder point, you should place a purchase order. Healthy = enough runway based on current velocity." />
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {pageItems.map((f, i) => (
                    <tr key={f.sku}
                      style={{ background: i % 2 === 0 ? 'var(--bg-white)' : 'var(--bg-primary)', cursor: 'pointer' }}
                      onClick={() => setSelectedSku(f.sku)}
                      onMouseEnter={e => { if (i % 2 === 0) e.currentTarget.style.background = 'var(--bg-primary)' }}
                      onMouseLeave={e => { if (i % 2 === 0) e.currentTarget.style.background = 'var(--bg-white)' }}
                    >
                      <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 600, color: 'var(--accent)' }}>{f.sku}</td>
                      <td style={{ ...tdStyle, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.title}</td>
                      <td style={{ ...tdStyle, fontWeight: 600 }}>{f.rolling_30d_avg ?? 0}/day</td>
                      <td style={{ ...tdStyle, fontWeight: 500 }}>{Math.round(f.forecast_30d ?? 0).toLocaleString()}</td>
                      <td style={{ ...tdStyle, fontWeight: 500 }}>{Math.round(f.forecast_60d ?? 0).toLocaleString()}</td>
                      <td style={{ ...tdStyle, fontWeight: 500 }}>{Math.round(f.forecast_90d ?? 0).toLocaleString()}</td>
                      <td style={{ ...tdStyle, fontWeight: 600 }}>{(f.current_stock ?? 0).toLocaleString()}</td>
                      <td style={tdStyle}>
                        <DaysLeftBar days={f.days_of_stock_remaining} leadTime={f.lead_time_days} />
                      </td>
                      <td style={tdStyle}>
                        {f.has_seasonality ? (
                          <span style={{ padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600, background: 'var(--accent-light)', color: 'var(--accent)' }}>Yes</span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>No</span>
                        )}
                      </td>
                      <td style={tdStyle}>
                        {f.below_reorder_point ? (
                          <InfoTooltip text={`Stock (${f.current_stock}) is below reorder point (${f.reorder_point}). Suggested reorder: ${f.suggested_reorder_qty} units. Lead time: ${f.lead_time_days} days.`}>
                            <span style={{ padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 700, background: 'var(--danger-bg)', color: 'var(--danger)', cursor: 'help' }}>REORDER</span>
                          </InfoTooltip>
                        ) : (
                          <span style={{ padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600, background: 'var(--success-bg)', color: 'var(--success)' }}>Healthy</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        {filteredForecasts.length > perPage && (
          <Pagination page={page} pages={totalPages} onPageChange={setPage} />
        )}
      </div>

      {selectedSku && <SkuDetailModal sku={selectedSku} onClose={() => setSelectedSku(null)} />}
    </div>
  )
}
