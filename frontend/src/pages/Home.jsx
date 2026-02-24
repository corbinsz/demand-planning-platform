import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip } from 'recharts'
import KPICards from '../components/KPICards'
import ReorderAlerts from '../components/ReorderAlerts'
import { getDashboard, getSalesTrend, triggerShopifySync, triggerShipHeroSync } from '../services/api'

function DataFreshness({ syncData }) {
  if (!syncData) return null

  const lastAt = syncData.last_sync?.at
  let label = 'Never synced'
  let stale = true

  if (lastAt) {
    const diff = Date.now() - new Date(lastAt).getTime()
    const hours = Math.floor(diff / 3600000)
    const mins = Math.floor((diff % 3600000) / 60000)
    if (hours > 0) {
      label = `Last synced ${hours}h ${mins}m ago`
    } else {
      label = `Last synced ${mins}m ago`
    }
    stale = hours >= 6
  }

  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: '6px',
      fontSize: '12px', color: stale ? 'var(--warning)' : 'var(--text-muted)',
    }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%',
        background: stale ? 'var(--warning)' : 'var(--success)',
        display: 'inline-block',
      }} />
      {label}
      {stale && <span style={{ fontWeight: 600 }}> (stale)</span>}
    </div>
  )
}

function SyncButton({ onSync }) {
  const [syncing, setSyncing] = useState(false)

  const handleSync = async () => {
    setSyncing(true)
    try {
      await Promise.all([triggerShopifySync(), triggerShipHeroSync()])
      if (onSync) onSync()
    } catch { /* ignore */ }
    setTimeout(() => setSyncing(false), 3000)
  }

  return (
    <button onClick={handleSync} disabled={syncing} style={{
      padding: '7px 18px', borderRadius: 'var(--radius-sm)',
      border: '1px solid var(--border)', background: 'var(--bg-white)',
      color: syncing ? 'var(--text-muted)' : 'var(--accent)',
      fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px',
      transition: 'all 0.15s',
    }}>
      <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"
        style={{ animation: syncing ? 'spin 1s linear infinite' : 'none' }}>
        <path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
      </svg>
      {syncing ? 'Syncing...' : 'Sync Now'}
    </button>
  )
}

function SalesTrendChart() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getSalesTrend(30)
      .then(r => setData(r.data?.items || []))
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>Loading chart...</div>
  if (data.length === 0) return null

  return (
    <div style={{
      background: 'var(--bg-white)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '24px', boxShadow: 'var(--shadow-sm)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>Sales Trend (30 Days)</h3>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
          <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis yAxisId="left" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} width={45} />
          <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} width={60} />
          <Tooltip
            contentStyle={{
              background: 'var(--bg-white)', border: '1px solid var(--border)',
              borderRadius: 8, fontSize: 12, boxShadow: 'var(--shadow-md)',
            }}
            formatter={(val, name) => [
              name === 'revenue' ? `$${(val ?? 0).toLocaleString()}` : (val ?? 0).toLocaleString(),
              name === 'revenue' ? 'Revenue' : name === 'units' ? 'Units' : 'Orders',
            ]}
          />
          <Line yAxisId="left" type="monotone" dataKey="units" stroke="var(--accent)" strokeWidth={2} dot={false} />
          <Line yAxisId="right" type="monotone" dataKey="revenue" stroke="var(--success)" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
      <div style={{ display: 'flex', gap: '20px', justifyContent: 'center', marginTop: '8px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ width: 12, height: 3, background: 'var(--accent)', borderRadius: 2, display: 'inline-block' }} /> Units Sold
        </span>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ width: 12, height: 3, background: 'var(--success)', borderRadius: 2, display: 'inline-block' }} /> Revenue
        </span>
      </div>
    </div>
  )
}

export default function Home() {
  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadDashboard = () => {
    setLoading(true)
    getDashboard()
      .then(r => { setDashboard(r.data); setError(null) })
      .catch(err => {
        setDashboard(null)
        setError(err.response?.data?.detail || 'Failed to load dashboard. Check that the backend is running.')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadDashboard() }, [])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '28px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>Demand Planning Dashboard</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '12px' }}>
            Forecast demand, prevent stockouts, and automate reorders across Shopify + ShipHero
            {dashboard && <DataFreshness syncData={dashboard} />}
          </p>
        </div>
        <SyncButton onSync={loadDashboard} />
      </div>

      {loading ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px' }}>Loading dashboard...</div>
      ) : error ? (
        <div style={{
          background: 'var(--danger-bg)', border: '1px solid var(--danger)',
          borderRadius: 'var(--radius)', padding: '20px 24px',
          color: '#b91c1c', fontSize: '14px',
        }}>
          <div style={{ fontWeight: 600, marginBottom: '4px' }}>Dashboard Error</div>
          <div style={{ fontSize: '13px' }}>{error}</div>
        </div>
      ) : !dashboard ? (
        <div style={{
          background: 'var(--bg-white)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: '48px', textAlign: 'center',
          boxShadow: 'var(--shadow-sm)',
        }}>
          <div style={{
            width: 56, height: 56, borderRadius: 16,
            background: 'linear-gradient(135deg, #9869E3, #E82888)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
          }}>
            <svg width="24" height="24" fill="white" viewBox="0 0 24 24"><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
          </div>
          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '8px', fontFamily: 'Poppins, sans-serif' }}>
            Stop guessing what to reorder.
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '20px', maxWidth: 460, margin: '0 auto 20px' }}>
            Inventory Intel uses AI-powered demand forecasting to predict exactly what you'll sell, when you'll run out, and how much to reorder. Connect your Shopify store and ShipHero warehouse to get started.
          </p>
          <Link to="/setup" style={{
            display: 'inline-block', padding: '10px 28px', borderRadius: 'var(--radius-sm)',
            background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: '14px',
            transition: 'background 0.15s',
          }}>
            Get Started
          </Link>
        </div>
      ) : (
        <>
          <KPICards data={dashboard} />

          <div style={{ marginTop: '28px' }}>
            <SalesTrendChart />
          </div>

          <div style={{ marginTop: '28px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>
                Reorder Alerts
              </h3>
              <Link to="/purchase-orders" style={{ fontSize: '13px', fontWeight: 500 }}>
                View all &rarr;
              </Link>
            </div>
            <ReorderAlerts />
          </div>
        </>
      )}

    </div>
  )
}
