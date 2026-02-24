import { useState, useEffect, useMemo } from 'react'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import { getABCClassification, getDeadStock, getExcessStock, exportABCCsv, exportDeadStockCsv, exportExcessStockCsv } from '../services/api'
import { thStyle, tdStyle } from '../components/shared/tableStyles'
import Pagination from '../components/shared/Pagination'
import SortableHeader from '../components/shared/SortableHeader'
import InfoTooltip from '../components/shared/InfoTooltip'

function downloadBlob(resp, fallbackName) {
  const blob = new Blob([resp.data], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fallbackName
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 100)
}

const tabBtnStyle = (active) => ({
  padding: '9px 22px', borderRadius: '6px', border: 'none',
  background: active ? 'var(--accent)' : 'transparent',
  color: active ? '#fff' : 'var(--text-secondary)',
  fontSize: '13px', fontWeight: 600, transition: 'all 0.15s', cursor: 'pointer',
})

const ABC_COLORS = { A: '#9869E3', B: '#c4a6f0', C: '#e2d5f7' }
const ABC_LABELS = {
  A: { bg: 'rgba(152,105,227,0.15)', color: '#9869E3', desc: 'Your best sellers', long: 'These products drive ~80% of your revenue. Never let them stock out — a stockout here directly hurts your bottom line. Prioritize these for fast reorders and keep safety stock high.' },
  B: { bg: 'rgba(152,105,227,0.08)', color: '#a78bda', desc: 'Steady movers', long: 'These drive the next ~15% of revenue. Important but not critical. Standard reorder rules work fine — monitor monthly.' },
  C: { bg: 'rgba(152,105,227,0.04)', color: '#c4b5d9', desc: 'Slow or niche', long: 'These contribute the bottom ~5% of revenue. Order conservatively — overstock here ties up cash with low return. Consider bundling, discounting, or discontinuing.' },
}

function ABCBadge({ cls }) {
  const cfg = ABC_LABELS[cls] || ABC_LABELS.C
  return (
    <InfoTooltip text={cfg.long}>
      <span style={{
        padding: '3px 14px', borderRadius: '20px', fontSize: '12px',
        fontWeight: 700, background: cfg.bg, color: cfg.color, cursor: 'help',
      }}>{cls}</span>
    </InfoTooltip>
  )
}

function SummaryCard({ label, value, sub, color }) {
  return (
    <div style={{
      background: 'var(--bg-white)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '18px 22px', flex: '1 1 160px',
      boxShadow: 'var(--shadow-sm)',
    }}>
      <div style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600, marginBottom: '8px' }}>{label}</div>
      <div style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'Poppins, sans-serif', color: color || 'var(--text-primary)' }}>{value}</div>
      {sub && <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>{sub}</div>}
    </div>
  )
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]
  return (
    <div style={{
      background: 'var(--bg-white)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-sm)', padding: '10px 14px', fontSize: '12px',
      boxShadow: 'var(--shadow-md)',
    }}>
      <div style={{ fontWeight: 600 }}>{d.name}</div>
      <div style={{ color: 'var(--text-secondary)' }}>{(d.value ?? 0).toLocaleString()} ({d.payload?.pct ?? 0}%)</div>
    </div>
  )
}

const exportBtnStyle = {
  padding: '7px 16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
  background: 'var(--bg-white)', color: 'var(--text-primary)', fontSize: '12px',
  fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
}

// ---- ABC Tab ----
function ErrorBanner({ message }) {
  return (
    <div style={{
      background: 'var(--bg-white)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '40px', textAlign: 'center',
      boxShadow: 'var(--shadow-sm)',
    }}>
      <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 6 }}>Error loading report</div>
      <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{message}</div>
    </div>
  )
}

function ABCTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [sortBy, setSortBy] = useState('total_revenue')
  const [sortDir, setSortDir] = useState('desc')

  const handleSort = (field, dir) => { setSortBy(field); setSortDir(dir) }

  useEffect(() => {
    setLoading(true)
    setError(null)
    getABCClassification({ page, per_page: 50 })
      .then(r => {
        setData(r.data)
        setPages(r.data.pages || 1)
      })
      .catch(err => {
        setData(null)
        setError(err.response?.data?.detail || 'Failed to load ABC classification.')
      })
      .finally(() => setLoading(false))
  }, [page])

  const sortedItems = useMemo(() => {
    if (!data?.items) return []
    const sorted = [...data.items]
    sorted.sort((a, b) => {
      const av = a[sortBy] ?? 0, bv = b[sortBy] ?? 0
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return sorted
  }, [data, sortBy, sortDir])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Calculating ABC classification...</div>
  if (error) return <ErrorBanner message={error} />
  if (!data || data.items?.length === 0) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No sales data for classification. Sync orders first.</div>

  const summary = data.summary || {}
  const pieData = Object.entries(summary).map(([cls, v]) => ({
    name: `Class ${cls}`, value: v?.revenue ?? 0, pct: v?.pct_of_skus ?? 0, count: v?.count ?? 0,
  }))

  return (
    <div>
      {/* Explainer */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(152,105,227,0.08), rgba(232,40,136,0.05))',
        border: '1px solid rgba(152,105,227,0.2)',
        borderRadius: 'var(--radius)', padding: '18px 24px', marginBottom: '24px',
        fontSize: '13px', lineHeight: 1.7, color: 'var(--text-secondary)',
      }}>
        <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6, fontSize: '14px' }}>
          What is ABC Classification?
        </div>
        ABC analysis ranks your products by how much revenue they generate.
        A small number of products usually drive most of your sales (the <strong style={{ color: '#9869E3' }}>Pareto principle</strong>).
        This helps you decide <strong>where to focus</strong>:
        <strong style={{ color: '#9869E3' }}> Class A</strong> = never let these stock out,
        <strong style={{ color: '#a78bda' }}> Class B</strong> = monitor regularly,
        <strong style={{ color: '#c4b5d9' }}> Class C</strong> = order conservatively. Hover any badge for specific advice.
      </div>

      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        {Object.entries(summary).map(([cls, v]) => (
          <SummaryCard
            key={cls}
            label={`Class ${cls} — ${ABC_LABELS[cls]?.desc}`}
            value={`${v?.count ?? 0} SKUs`}
            sub={`$${(v?.revenue ?? 0).toLocaleString()} revenue · ${v?.pct_of_skus ?? 0}% of catalog`}
            color={ABC_COLORS[cls]}
          />
        ))}
      </div>

      <div style={{ display: 'flex', gap: '20px', marginBottom: '28px', flexWrap: 'wrap' }}>
        <div style={{
          background: 'var(--bg-white)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: '24px', flex: '1 1 320px',
          boxShadow: 'var(--shadow-sm)',
        }}>
          <h4 style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'Poppins, sans-serif', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            Revenue Distribution
          </h4>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" paddingAngle={3}>
                {pieData.map((_, i) => <Cell key={i} fill={Object.values(ABC_COLORS)[i]} />)}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
              <Legend formatter={(val) => <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{val}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div style={{
          background: 'var(--bg-white)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: '24px', flex: '1 1 320px',
          boxShadow: 'var(--shadow-sm)',
        }}>
          <h4 style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'Poppins, sans-serif', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            SKU Count by Class
          </h4>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={pieData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
              <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
              <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                {pieData.map((_, i) => <Cell key={i} fill={Object.values(ABC_COLORS)[i]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
        <button style={exportBtnStyle} onClick={() => exportABCCsv().then(r => downloadBlob(r, 'abc-classification.csv'))}>
          Export CSV
        </button>
      </div>

      <div style={{
        background: 'var(--bg-white)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
      }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '900px' }}>
            <thead>
              <tr>
                <th style={thStyle}>Class</th>
                <SortableHeader label="SKU" field="sku" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Title" field="title" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Revenue" field="total_revenue" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Units Sold" field="total_units" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="% of Revenue" field="pct_of_revenue" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <th style={thStyle}>Cumulative %</th>
                <SortableHeader label="Stock" field="current_stock" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Days of Stock" field="days_of_stock" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Velocity/day" field="daily_velocity" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((item, i) => (
                <tr key={item.sku || i} style={{ background: i % 2 === 0 ? 'var(--bg-white)' : 'var(--bg-primary)' }}>
                  <td style={tdStyle}><ABCBadge cls={item.abc_class} /></td>
                  <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 600, color: 'var(--accent)' }}>{item.sku}</td>
                  <td style={tdStyle}>{item.title}</td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>${(item.total_revenue ?? 0).toLocaleString()}</td>
                  <td style={tdStyle}>{(item.total_units ?? 0).toLocaleString()}</td>
                  <td style={tdStyle}>{item.pct_of_revenue ?? 0}%</td>
                  <td style={tdStyle}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'var(--border-light)', overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${Math.min(item.cumulative_pct ?? 0, 100)}%`, background: ABC_COLORS[item.abc_class], borderRadius: 3, transition: 'width 0.3s' }} />
                      </div>
                      <span style={{ fontSize: '12px', minWidth: 40, textAlign: 'right' }}>{item.cumulative_pct ?? 0}%</span>
                    </div>
                  </td>
                  <td style={tdStyle}>{(item.current_stock ?? 0).toLocaleString()}</td>
                  <td style={tdStyle}>{item.days_of_stock != null ? `${item.days_of_stock}d` : '--'}</td>
                  <td style={tdStyle}>{item.daily_velocity ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Pagination page={page} pages={pages} onPageChange={setPage} />
    </div>
  )
}

// ---- Dead Stock Tab ----
function DeadStockTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [sortBy, setSortBy] = useState('inventory_value')
  const [sortDir, setSortDir] = useState('desc')

  const handleSort = (field, dir) => { setSortBy(field); setSortDir(dir) }

  useEffect(() => {
    setLoading(true)
    setError(null)
    getDeadStock({ page, per_page: 50 })
      .then(r => {
        setData(r.data)
        setPages(r.data.pages || 1)
      })
      .catch(err => {
        setData(null)
        setError(err.response?.data?.detail || 'Failed to load dead stock report.')
      })
      .finally(() => setLoading(false))
  }, [page])

  const sortedItems = useMemo(() => {
    if (!data?.items) return []
    const sorted = [...data.items]
    sorted.sort((a, b) => {
      const av = a[sortBy] ?? 0, bv = b[sortBy] ?? 0
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return sorted
  }, [data, sortBy, sortDir])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Analyzing dead stock...</div>
  if (error) return <ErrorBanner message={error} />
  if (!data || data.items?.length === 0) return (
    <div style={{
      background: 'var(--bg-white)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '48px', textAlign: 'center',
      boxShadow: 'var(--shadow-sm)',
    }}>
      <svg width="40" height="40" fill="none" viewBox="0 0 24 24" stroke="var(--success)" strokeWidth="1.5" style={{ marginBottom: 12 }}>
        <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>No Dead Stock</div>
      <div style={{ color: 'var(--text-muted)' }}>All stocked SKUs have recent sales activity.</div>
    </div>
  )

  return (
    <div>
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <SummaryCard label="Dead Stock SKUs" value={data.total} color="var(--danger)" />
        <SummaryCard label="Capital at Risk" value={`$${(data.total_value ?? 0).toLocaleString()}`} color="var(--danger)" sub={`${(data.total_units ?? 0).toLocaleString()} units tied up`} />
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
        <button style={exportBtnStyle} onClick={() => exportDeadStockCsv().then(r => downloadBlob(r, 'dead-stock.csv'))}>
          Export CSV
        </button>
      </div>

      <div style={{
        background: 'var(--bg-white)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
      }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1000px' }}>
            <thead>
              <tr>
                <th style={thStyle}>Class</th>
                <SortableHeader label="SKU" field="sku" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Title" field="title" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Stock" field="current_stock" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Value" field="inventory_value" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <th style={thStyle}>Last Sold</th>
                <SortableHeader label="Days Silent" field="days_since_last_sale" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Units (90d)" field="total_units_sold_90d" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Velocity" field="daily_velocity" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <th style={thStyle}>Recommendation</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((item, i) => (
                <tr key={item.sku || i} style={{ background: i % 2 === 0 ? 'var(--bg-white)' : 'var(--bg-primary)' }}>
                  <td style={tdStyle}><ABCBadge cls={item.abc_class} /></td>
                  <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 600, color: 'var(--accent)' }}>{item.sku}</td>
                  <td style={tdStyle}>{item.title}</td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{item.current_stock ?? 0}</td>
                  <td style={{ ...tdStyle, fontWeight: 600, color: 'var(--danger)' }}>${(item.inventory_value ?? 0).toLocaleString()}</td>
                  <td style={{ ...tdStyle, fontSize: '12px' }}>{item.last_sold_date ? new Date(item.last_sold_date).toLocaleDateString() : 'Never'}</td>
                  <td style={{
                    ...tdStyle, fontWeight: 600,
                    color: (item.days_since_last_sale ?? 999) > 90 ? 'var(--danger)' : 'var(--warning)',
                  }}>
                    {item.days_since_last_sale != null ? `${item.days_since_last_sale}d` : 'Never'}
                  </td>
                  <td style={tdStyle}>{item.total_units_sold_90d ?? 0}</td>
                  <td style={tdStyle}>{item.daily_velocity ?? 0}/day</td>
                  <td style={tdStyle}>
                    <span style={{
                      padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 600,
                      background: (item.recommendation || '').includes('Liquidate') ? 'var(--danger-bg)' :
                                  (item.recommendation || '').includes('discount') ? 'var(--warning-bg)' : 'var(--info-bg)',
                      color: (item.recommendation || '').includes('Liquidate') ? 'var(--danger)' :
                             (item.recommendation || '').includes('discount') ? 'var(--warning)' : 'var(--info)',
                    }}>
                      {item.recommendation}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Pagination page={page} pages={pages} onPageChange={setPage} />
    </div>
  )
}

// ---- Excess Stock Tab ----
function ExcessStockTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [sortBy, setSortBy] = useState('excess_value')
  const [sortDir, setSortDir] = useState('desc')

  const handleSort = (field, dir) => { setSortBy(field); setSortDir(dir) }

  useEffect(() => {
    setLoading(true)
    setError(null)
    getExcessStock({ page, per_page: 50 })
      .then(r => {
        setData(r.data)
        setPages(r.data.pages || 1)
      })
      .catch(err => {
        setData(null)
        setError(err.response?.data?.detail || 'Failed to load excess stock report.')
      })
      .finally(() => setLoading(false))
  }, [page])

  const sortedItems = useMemo(() => {
    if (!data?.items) return []
    const sorted = [...data.items]
    sorted.sort((a, b) => {
      const av = a[sortBy] ?? 0, bv = b[sortBy] ?? 0
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return sorted
  }, [data, sortBy, sortDir])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Analyzing excess inventory...</div>
  if (error) return <ErrorBanner message={error} />
  if (!data || data.items?.length === 0) return (
    <div style={{
      background: 'var(--bg-white)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '48px', textAlign: 'center',
      boxShadow: 'var(--shadow-sm)',
    }}>
      <svg width="40" height="40" fill="none" viewBox="0 0 24 24" stroke="var(--success)" strokeWidth="1.5" style={{ marginBottom: 12 }}>
        <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>No Excess Stock</div>
      <div style={{ color: 'var(--text-muted)' }}>All SKUs are within target stock cover (90 days).</div>
    </div>
  )

  return (
    <div>
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <SummaryCard label="Overstocked SKUs" value={data.total} color="var(--excess)" />
        <SummaryCard label="Excess Value" value={`$${(data.total_excess_value ?? 0).toLocaleString()}`} color="var(--excess)" sub={`${(data.total_excess_units ?? 0).toLocaleString()} excess units`} />
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
        <button style={exportBtnStyle} onClick={() => exportExcessStockCsv().then(r => downloadBlob(r, 'excess-stock.csv'))}>
          Export CSV
        </button>
      </div>

      <div style={{
        background: 'var(--bg-white)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
      }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1000px' }}>
            <thead>
              <tr>
                <th style={thStyle}>Class</th>
                <SortableHeader label="SKU" field="sku" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Title" field="title" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Stock" field="current_stock" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Velocity" field="daily_velocity" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Days of Stock" field="days_of_stock" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <th style={thStyle}>Target</th>
                <SortableHeader label="Excess Units" field="excess_units" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableHeader label="Excess Value" field="excess_value" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                <th style={thStyle}>Recommendation</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((item, i) => (
                <tr key={item.sku || i} style={{ background: i % 2 === 0 ? 'var(--bg-white)' : 'var(--bg-primary)' }}>
                  <td style={tdStyle}><ABCBadge cls={item.abc_class} /></td>
                  <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 600, color: 'var(--accent)' }}>{item.sku}</td>
                  <td style={tdStyle}>{item.title}</td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{(item.current_stock ?? 0).toLocaleString()}</td>
                  <td style={tdStyle}>{item.daily_velocity ?? 0}/day</td>
                  <td style={{
                    ...tdStyle, fontWeight: 600,
                    color: (item.days_of_stock ?? 0) > 180 ? 'var(--danger)' : 'var(--warning)',
                  }}>
                    {item.days_of_stock ?? 0}d
                  </td>
                  <td style={{ ...tdStyle, color: 'var(--text-muted)' }}>{item.target_days ?? 90}d</td>
                  <td style={{ ...tdStyle, fontWeight: 600, color: 'var(--excess)' }}>{(item.excess_units ?? 0).toLocaleString()}</td>
                  <td style={{ ...tdStyle, fontWeight: 600, color: 'var(--excess)' }}>${(item.excess_value ?? 0).toLocaleString()}</td>
                  <td style={tdStyle}>
                    <span style={{
                      padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 600,
                      background: (item.recommendation || '').includes('liquidate') ? 'var(--danger-bg)' :
                                  (item.recommendation || '').includes('Pause') ? 'var(--warning-bg)' : 'var(--info-bg)',
                      color: (item.recommendation || '').includes('liquidate') ? 'var(--danger)' :
                             (item.recommendation || '').includes('Pause') ? 'var(--warning)' : 'var(--info)',
                    }}>
                      {item.recommendation}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Pagination page={page} pages={pages} onPageChange={setPage} />
    </div>
  )
}

// ---- Main Reports Page ----
export default function Reports() {
  const [tab, setTab] = useState('abc')

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>Inventory Reports</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          Understand which products matter most, find dead weight, and spot overstock before it drains cash flow.
        </p>
      </div>

      <div style={{
        display: 'flex', gap: '4px', marginBottom: '24px',
        background: 'var(--bg-white)', padding: '4px', borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--border)', width: 'fit-content',
      }}>
        <button onClick={() => setTab('abc')} style={tabBtnStyle(tab === 'abc')}>Best Sellers (ABC)</button>
        <button onClick={() => setTab('dead')} style={tabBtnStyle(tab === 'dead')}>Dead Stock</button>
        <button onClick={() => setTab('excess')} style={tabBtnStyle(tab === 'excess')}>Overstock</button>
      </div>

      {tab === 'abc' && <ABCTab />}
      {tab === 'dead' && <DeadStockTab />}
      {tab === 'excess' && <ExcessStockTab />}
    </div>
  )
}
