import { lazy, Suspense, useState } from 'react'
import { BrowserRouter, Link, NavLink, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useSession } from './session'
import Landing from './pages/Landing'
import Login from './pages/Login'
import { Privacy, Terms } from './pages/Legal'
import ShareReport from './pages/ShareReport'
import Today from './pages/Today'

const Inventory = lazy(() => import('./pages/Inventory'))
const Forecasting = lazy(() => import('./pages/Forecasting'))
const PurchaseOrders = lazy(() => import('./pages/PurchaseOrders'))
const Reports = lazy(() => import('./pages/Reports'))
const Promotions = lazy(() => import('./pages/Promotions'))
const Setup = lazy(() => import('./pages/Setup'))
const Numbers = lazy(() => import('./pages/Home'))

const links = [
  ['/today', 'Today'],
  ['/purchase-orders', 'What to buy'],
  ['/forecasting', 'Forecast'],
  ['/inventory', 'Stock'],
  ['/reports', 'Quiet stock'],
  ['/numbers', 'More numbers'],
  ['/promotions', 'Promotions'],
  ['/connections', 'Connections'],
]

function Shell() {
  const { session } = useSession()
  const [open, setOpen] = useState(false)
  const demo = session?.workspace?.is_demo || session?.demo_anonymous
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className={open ? 'sidebar open' : 'sidebar'}>
        <div style={{ padding: '22px 20px 12px', color: '#fff' }}>
          <strong>Inventory Intel</strong>
          <div style={{ fontSize: 12, opacity: 0.8 }}>{session?.workspace?.name || 'Demand planning'}</div>
        </div>
        <nav aria-label="Primary" style={{ display: 'flex', flexDirection: 'column', padding: '8px 12px', gap: 4 }}>
          {links.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              style={({ isActive }) => ({
                color: '#fff',
                background: isActive ? 'rgba(152,105,227,0.28)' : 'transparent',
                borderRadius: 8,
                padding: '10px 12px',
                fontWeight: isActive ? 700 : 500,
                textDecoration: 'none',
              })}
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div style={{ marginTop: 'auto', padding: 16, fontSize: 12, color: 'rgba(255,255,255,0.8)' }}>
          <Link to="/" style={{ color: '#fff' }}>Product home</Link>
        </div>
      </aside>
      <main id="main" className="main">
        <button type="button" className="menu-btn btn ghost" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          Menu
        </button>
        {demo && (
          <p className="demo-banner">
            Sample brand: Northline Athletics, Salt Lake City. Fictional catalog. Not a customer’s data.
          </p>
        )}
        <Suspense fallback={<p>Loading…</p>}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  )
}

function RequireSession() {
  const { session, loading } = useSession()
  if (loading) return <p style={{ padding: 24 }}>Loading…</p>
  if (!session) return <Navigate to="/login" replace />
  return <Outlet />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/share/:token" element={<ShareReport />} />
        <Route element={<RequireSession />}>
          <Route element={<Shell />}>
            <Route path="/today" element={<Today />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/forecasting" element={<Forecasting />} />
            <Route path="/purchase-orders" element={<PurchaseOrders />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/numbers" element={<Numbers />} />
            <Route path="/promotions" element={<Promotions />} />
            <Route path="/connections" element={<Setup />} />
            <Route path="/setup" element={<Navigate to="/connections" replace />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
