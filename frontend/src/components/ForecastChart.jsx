import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Cell,
} from 'recharts'
import { getForecasts } from '../services/api'
import InfoTooltip from './shared/InfoTooltip'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const item = payload[0]?.payload
  return (
    <div style={{
      background: 'var(--bg-white)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-sm)', padding: '12px 16px',
      fontSize: '12px', boxShadow: 'var(--shadow-md)', maxWidth: 260,
    }}>
      <p style={{ fontWeight: 700, marginBottom: '4px', color: 'var(--text-primary)' }}>{item?.fullTitle || label}</p>
      <p style={{ color: 'var(--text-muted)', marginBottom: 8, fontSize: '11px' }}>{item?.fullSku}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color, marginBottom: 2 }}>
          {p.name}: <strong>{Math.round(p.value ?? 0).toLocaleString()}</strong> units
        </p>
      ))}
      {item?.daysLeft != null && (
        <p style={{ marginTop: 6, fontWeight: 600, color: item.daysLeft < 30 ? 'var(--danger)' : 'var(--text-secondary)' }}>
          {item.daysLeft}d of stock remaining
        </p>
      )}
    </div>
  )
}

export default function ForecastChart() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [mode, setMode] = useState('urgent') // 'urgent' | 'volume'

  useEffect(() => {
    getForecasts({ page: 1, per_page: 200 })
      .then(r => {
        const items = r.data?.items || []
        setData(items)
      })
      .catch(err => {
        setData([])
        setError(err.response?.data?.detail || 'Failed to load forecast data.')
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: '24px', textAlign: 'center' }}>Loading forecasts...</div>
  }

  if (error) {
    return (
      <div style={{
        background: 'var(--bg-white)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: '40px', textAlign: 'center',
        boxShadow: 'var(--shadow-sm)',
      }}>
        <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 6 }}>Error loading forecasts</div>
        <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{error}</div>
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div style={{
        background: 'var(--bg-white)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: '40px', textAlign: 'center',
        color: 'var(--text-muted)', boxShadow: 'var(--shadow-sm)',
      }}>
        No forecast data available. Sync inventory and orders first.
      </div>
    )
  }

  // Prepare chart data based on mode
  let chartItems
  if (mode === 'urgent') {
    // Top 15 by lowest days remaining (most urgent)
    chartItems = [...data]
      .filter(f => f.days_of_stock_remaining != null && f.rolling_30d_avg > 0)
      .sort((a, b) => (a.days_of_stock_remaining ?? 999) - (b.days_of_stock_remaining ?? 999))
      .slice(0, 15)
      .map(f => ({
        sku: f.sku.length > 14 ? f.sku.slice(0, 14) + '..' : f.sku,
        fullSku: f.sku,
        fullTitle: f.title,
        daysLeft: f.days_of_stock_remaining,
        '30-day': f.forecast_30d ?? 0,
        stock: f.current_stock ?? 0,
        urgent: f.days_of_stock_remaining < f.lead_time_days,
      }))
  } else {
    // Top 15 by highest 30-day forecast (highest demand)
    chartItems = [...data]
      .sort((a, b) => (b.forecast_30d ?? 0) - (a.forecast_30d ?? 0))
      .slice(0, 15)
      .map(f => ({
        sku: f.sku.length > 14 ? f.sku.slice(0, 14) + '..' : f.sku,
        fullSku: f.sku,
        fullTitle: f.title,
        daysLeft: f.days_of_stock_remaining,
        '30-day': f.forecast_30d ?? 0,
        '60-day': f.forecast_60d ?? 0,
        '90-day': f.forecast_90d ?? 0,
      }))
  }

  return (
    <div style={{
      background: 'var(--bg-white)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '24px',
      boxShadow: 'var(--shadow-sm)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: 10 }}>
        <h3 style={{
          fontSize: '14px', fontWeight: 600,
          color: 'var(--text-secondary)', fontFamily: 'Poppins, sans-serif',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          {mode === 'urgent' ? 'Most Urgent — Stock vs. 30-Day Demand' : 'Highest Demand — Forecast by SKU'}
          <InfoTooltip text={mode === 'urgent'
            ? 'SKUs sorted by days until stockout. The purple bar is predicted 30-day demand, the teal bar is current stock. When demand exceeds stock, you need to reorder.'
            : 'Top 15 SKUs ranked by predicted sales volume. Stacked bars show 30, 60, and 90-day demand forecasts.'
          } />
        </h3>
        <div style={{ display: 'flex', gap: 4, background: 'var(--bg-primary)', padding: 3, borderRadius: 'var(--radius-sm)' }}>
          <button onClick={() => setMode('urgent')} style={{
            padding: '4px 12px', borderRadius: 5, border: 'none', fontSize: '11px', fontWeight: 600,
            background: mode === 'urgent' ? 'var(--accent)' : 'transparent',
            color: mode === 'urgent' ? '#fff' : 'var(--text-secondary)', cursor: 'pointer',
          }}>Urgent</button>
          <button onClick={() => setMode('volume')} style={{
            padding: '4px 12px', borderRadius: 5, border: 'none', fontSize: '11px', fontWeight: 600,
            background: mode === 'volume' ? 'var(--accent)' : 'transparent',
            color: mode === 'volume' ? '#fff' : 'var(--text-secondary)', cursor: 'pointer',
          }}>Volume</button>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={360}>
        {mode === 'urgent' ? (
          <BarChart data={chartItems} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
            <XAxis dataKey="sku" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} angle={-45} textAnchor="end" height={70} />
            <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Bar dataKey="30-day" name="30-Day Demand" fill="#9869E3" radius={[4, 4, 0, 0]} />
            <Bar dataKey="stock" name="Current Stock" radius={[4, 4, 0, 0]}>
              {chartItems.map((item, i) => (
                <Cell key={i} fill={item.urgent ? '#ef4444' : '#22c5a0'} />
              ))}
            </Bar>
          </BarChart>
        ) : (
          <BarChart data={chartItems} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
            <XAxis dataKey="sku" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} angle={-45} textAnchor="end" height={70} />
            <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Bar dataKey="30-day" name="30-Day" fill="#9869E3" radius={[4, 4, 0, 0]} />
            <Bar dataKey="60-day" name="60-Day" fill="#c4a6f0" radius={[4, 4, 0, 0]} />
            <Bar dataKey="90-day" name="90-Day" fill="#e2d5f7" radius={[4, 4, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
