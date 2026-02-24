import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Home from './pages/Home'
import Inventory from './pages/Inventory'
import Forecasting from './pages/Forecasting'
import PurchaseOrders from './pages/PurchaseOrders'
import Reports from './pages/Reports'
import Promotions from './pages/Promotions'
import Setup from './pages/Setup'

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        <Sidebar />
        <main style={{
          flex: 1,
          marginLeft: 'var(--sidebar-width)',
          padding: '28px 36px',
          maxWidth: 'calc(100vw - var(--sidebar-width))',
          minHeight: '100vh',
        }}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/forecasting" element={<Forecasting />} />
            <Route path="/purchase-orders" element={<PurchaseOrders />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/promotions" element={<Promotions />} />
            <Route path="/setup" element={<Setup />} />
            <Route path="*" element={
              <div style={{ padding: '60px 20px', textAlign: 'center' }}>
                <h2 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif', marginBottom: '8px' }}>Page Not Found</h2>
                <p style={{ color: '#6B7280', fontSize: '14px' }}>The page you're looking for doesn't exist.</p>
              </div>
            } />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
