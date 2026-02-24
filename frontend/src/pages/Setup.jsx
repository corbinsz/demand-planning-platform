import { useState } from 'react'
import { testShopifyConnection, testShipHeroConnection } from '../services/api'

const sectionStyle = {
  background: 'var(--bg-white)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '28px 32px',
  boxShadow: 'var(--shadow-sm)',
  marginBottom: '20px',
}

const codeBlock = {
  background: '#1e1e2e',
  color: '#cdd6f4',
  padding: '16px 20px',
  borderRadius: 'var(--radius-sm)',
  fontSize: '13px',
  fontFamily: 'Consolas, Monaco, "Courier New", monospace',
  overflowX: 'auto',
  lineHeight: 1.7,
  margin: '12px 0',
}

const stepNum = {
  width: 28, height: 28, borderRadius: '50%',
  background: 'var(--accent)', color: '#fff',
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  fontSize: '13px', fontWeight: 700, marginRight: '12px', flexShrink: 0,
}

const h3Style = {
  fontSize: '16px', fontWeight: 700, fontFamily: 'Poppins, sans-serif',
  marginBottom: '16px', display: 'flex', alignItems: 'center',
}

function Accordion({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={sectionStyle}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: 'none', border: 'none', width: '100%',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: 0, cursor: 'pointer',
        }}
      >
        <h3 style={{ ...h3Style, marginBottom: 0 }}>{title}</h3>
        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth="2"
          style={{ transform: open ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.2s' }}>
          <path d="M19 9l-7 7-7-7"/>
        </svg>
      </button>
      {open && <div style={{ marginTop: '20px' }}>{children}</div>}
    </div>
  )
}

function ConnectionTest({ type }) {
  const [result, setResult] = useState(null)
  const [testing, setTesting] = useState(false)

  const runTest = async () => {
    setTesting(true)
    setResult(null)
    try {
      const fn = type === 'shopify' ? testShopifyConnection : testShipHeroConnection
      const r = await fn()
      setResult(r.data)
    } catch (err) {
      setResult({ success: false, error: err.response?.data?.detail || 'Connection failed' })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div style={{ marginTop: '16px' }}>
      <button onClick={runTest} disabled={testing} style={{
        padding: '9px 22px', borderRadius: 'var(--radius-sm)',
        border: 'none', background: 'var(--accent)', color: '#fff',
        fontSize: '13px', fontWeight: 600, opacity: testing ? 0.6 : 1,
        transition: 'opacity 0.15s',
      }}>
        {testing ? 'Testing...' : `Test ${type === 'shopify' ? 'Shopify' : 'ShipHero'} Connection`}
      </button>

      {result && (
        <div style={{
          marginTop: '12px', padding: '14px 18px',
          borderRadius: 'var(--radius-sm)',
          border: `1px solid ${result.success ? 'var(--success)' : 'var(--danger)'}`,
          background: result.success ? 'var(--success-bg)' : 'var(--danger-bg)',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            fontWeight: 600, fontSize: '13px',
            color: result.success ? '#166534' : '#b91c1c',
            marginBottom: result.success ? '8px' : '0',
          }}>
            {result.success ? (
              <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            ) : (
              <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            )}
            {result.success ? 'Connected successfully' : 'Connection failed'}
          </div>
          {result.success && type === 'shopify' && (
            <div style={{ fontSize: '12px', color: '#166534' }}>
              Store: <strong>{result.store_name}</strong> &middot; {result.domain} &middot; {result.plan} &middot; {result.currency}
            </div>
          )}
          {result.success && type === 'shiphero' && (
            <div style={{ fontSize: '12px', color: '#166534' }}>
              Account ID: <strong>{result.account_id}</strong>
            </div>
          )}
          {!result.success && (
            <div style={{ fontSize: '12px', color: '#b91c1c', marginTop: '4px' }}>{result.error}</div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Setup() {
  return (
    <div style={{ maxWidth: 800 }}>
      <div style={{ marginBottom: '28px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>Setup Guide</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          Follow these steps to connect your integrations and start using Inventory Intel.
        </p>
      </div>

      {/* Overview */}
      <div style={{ ...sectionStyle, borderLeft: '4px solid var(--accent)' }}>
        <h3 style={h3Style}>How It Works</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.8 }}>
          Inventory Intel connects to your <strong>Shopify</strong> store and <strong>ShipHero</strong> warehouse
          to create a unified view of your inventory. It automatically syncs product data, orders, and stock
          levels on a schedule, then uses AI-powered demand forecasting to tell you exactly what to reorder and when.
        </p>
        <div style={{ display: 'flex', gap: '16px', marginTop: '20px', flexWrap: 'wrap' }}>
          {[
            { label: 'Shopify Sync', desc: 'Products, orders, inventory levels', time: 'Nightly at 2am UTC' },
            { label: 'ShipHero Sync', desc: 'On-hand, allocated, available stock', time: 'Every 4 hours' },
            { label: 'Forecasting', desc: 'Demand prediction & reorder alerts', time: 'Nightly at 3am UTC' },
            { label: 'Reconciliation', desc: 'Cross-source inventory matching', time: 'Every 4 hours' },
          ].map(item => (
            <div key={item.label} style={{
              flex: '1 1 160px', padding: '14px 16px',
              background: 'var(--bg-primary)', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-light)',
            }}>
              <div style={{ fontWeight: 600, fontSize: '13px', marginBottom: '4px' }}>{item.label}</div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{item.desc}</div>
              <div style={{ fontSize: '11px', color: 'var(--accent)', marginTop: '6px', fontWeight: 500 }}>{item.time}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Shopify Integration */}
      <Accordion title={<><span style={stepNum}>1</span> Connect Shopify</>} defaultOpen={true}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px' }}>
          Inventory Intel uses Shopify's Admin REST API with a custom/private app access token to pull your
          product catalog, historical orders (up to 365 days), and real-time inventory levels.
        </p>

        <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '10px' }}>Step 1: Create a Custom App in Shopify</h4>
        <ol style={{ color: 'var(--text-secondary)', fontSize: '13px', lineHeight: 2, paddingLeft: '20px', marginBottom: '16px' }}>
          <li>Go to your Shopify Admin &rarr; <strong>Settings</strong> &rarr; <strong>Apps and sales channels</strong></li>
          <li>Click <strong>Develop apps</strong> (top right), then <strong>Create an app</strong></li>
          <li>Name it something like <em>"Inventory Intel"</em></li>
          <li>Go to <strong>Configuration</strong> tab and click <strong>Configure Admin API scopes</strong></li>
          <li>Enable these scopes:
            <div style={codeBlock}>
              read_products{'\n'}
              read_orders{'\n'}
              read_inventory{'\n'}
              read_locations
            </div>
          </li>
          <li>Click <strong>Save</strong>, then go to <strong>API credentials</strong> tab</li>
          <li>Click <strong>Install app</strong>, then <strong>Reveal token once</strong></li>
          <li>Copy the <strong>Admin API access token</strong> (starts with <code style={{ background: 'var(--bg-primary)', padding: '1px 6px', borderRadius: 4, fontSize: '12px' }}>shpat_</code>)</li>
        </ol>

        <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '10px' }}>Step 2: Add to Environment</h4>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '8px' }}>
          Open <code style={{ background: 'var(--bg-primary)', padding: '1px 6px', borderRadius: 4, fontSize: '12px' }}>backend/.env</code> and set:
        </p>
        <div style={codeBlock}>
          SHOPIFY_STORE_DOMAIN=your-store.myshopify.com{'\n'}
          SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxx
        </div>
        <div style={{
          background: 'var(--warning-bg)', border: '1px solid var(--warning)',
          borderRadius: 'var(--radius-sm)', padding: '12px 16px', marginTop: '12px',
          fontSize: '13px', color: '#92400e',
        }}>
          <strong>Important:</strong> Your store domain is the <code>.myshopify.com</code> version, not a custom domain.
          For example: <code>my-brand.myshopify.com</code>
        </div>

        <ConnectionTest type="shopify" />

        <h4 style={{ fontSize: '14px', fontWeight: 600, margin: '20px 0 10px' }}>What Gets Synced</h4>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid var(--border)', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase' }}>Data</th>
              <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid var(--border)', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase' }}>Details</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Products & Variants', 'All products with SKUs, titles, variant IDs'],
              ['Orders', 'Last 365 days of orders with line items, quantities, prices'],
              ['Inventory Levels', 'Current available quantities per Shopify location'],
            ].map(([data, detail], i) => (
              <tr key={i}>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-light)', fontWeight: 500 }}>{data}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-light)', color: 'var(--text-secondary)' }}>{detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Accordion>

      {/* ShipHero Integration */}
      <Accordion title={<><span style={stepNum}>2</span> Connect ShipHero</>}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px' }}>
          ShipHero integration uses their GraphQL API to pull real-time warehouse inventory, open purchase
          orders, and recent inventory adjustments. ShipHero is the <strong>source of truth</strong> for all
          on-hand, allocated, and available quantities.
        </p>

        <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '10px' }}>Step 1: Get Your API Token</h4>
        <ol style={{ color: 'var(--text-secondary)', fontSize: '13px', lineHeight: 2, paddingLeft: '20px', marginBottom: '16px' }}>
          <li>Log into <strong>ShipHero</strong> &rarr; <strong>My Account</strong> &rarr; <strong>API</strong></li>
          <li>Under <strong>Third Party Developer Access Tokens</strong>, click <strong>Generate Token</strong></li>
          <li>Give it a name like <em>"Inventory Intel"</em></li>
          <li>Copy the generated <strong>Bearer token</strong></li>
          <li>Make sure your ShipHero account has <strong>read access</strong> to:
            <div style={codeBlock}>
              Inventory (on_hand, allocated, available){'\n'}
              Purchase Orders (PO number, expected dates, line items){'\n'}
              Inventory Changes / Adjustments (last 30 days)
            </div>
          </li>
        </ol>

        <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '10px' }}>Step 2: Add to Environment</h4>
        <div style={codeBlock}>
          SHIPHERO_API_TOKEN=your_shiphero_bearer_token_here
        </div>

        <ConnectionTest type="shiphero" />

        <h4 style={{ fontSize: '14px', fontWeight: 600, margin: '20px 0 10px' }}>What Gets Synced</h4>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid var(--border)', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase' }}>Data</th>
              <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid var(--border)', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase' }}>Details</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Inventory by SKU', 'On-hand, allocated, and available quantities across all warehouses'],
              ['Purchase Orders', 'Open POs with expected receipt dates and line item details'],
              ['Inventory Adjustments', 'Changes from the last 30 days with reasons and locations'],
            ].map(([data, detail], i) => (
              <tr key={i}>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-light)', fontWeight: 500 }}>{data}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-light)', color: 'var(--text-secondary)' }}>{detail}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{
          background: 'var(--info-bg)', border: '1px solid var(--info)',
          borderRadius: 'var(--radius-sm)', padding: '12px 16px', marginTop: '16px',
          fontSize: '13px', color: '#1e40af',
        }}>
          <strong>API Endpoint:</strong> All ShipHero queries go to{' '}
          <code style={{ background: 'rgba(59, 130, 246, 0.1)', padding: '1px 6px', borderRadius: 4 }}>
            https://public-api.shiphero.com/graphql
          </code>
        </div>
      </Accordion>

      {/* Running the App */}
      <Accordion title={<><span style={stepNum}>3</span> Running the App</>}>
        <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '10px' }}>Local Development</h4>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '12px' }}>
          After adding your API keys to <code style={{ background: 'var(--bg-primary)', padding: '1px 6px', borderRadius: 4, fontSize: '12px' }}>backend/.env</code>, start both servers:
        </p>
        <div style={codeBlock}>
          <span style={{ color: '#89b4fa' }}># Terminal 1 - Backend</span>{'\n'}
          cd backend{'\n'}
          python -m uvicorn app.main:app --reload --port 8000{'\n'}
          {'\n'}
          <span style={{ color: '#89b4fa' }}># Terminal 2 - Frontend</span>{'\n'}
          cd frontend{'\n'}
          npm run dev
        </div>

        <h4 style={{ fontSize: '14px', fontWeight: 600, margin: '20px 0 10px' }}>With Docker</h4>
        <div style={codeBlock}>
          docker compose up --build
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '8px' }}>
          This starts PostgreSQL, the backend, and the frontend together. The database will be automatically created and migrations run on startup.
        </p>

        <h4 style={{ fontSize: '14px', fontWeight: 600, margin: '20px 0 10px' }}>URLs</h4>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <tbody>
            {[
              ['Frontend', 'http://localhost:5173', 'The dashboard UI'],
              ['Backend API', 'http://localhost:8000', 'FastAPI REST endpoints'],
              ['API Docs', 'http://localhost:8000/docs', 'Interactive Swagger documentation'],
              ['Health Check', 'http://localhost:8000/api/health', 'Verify the backend is running'],
            ].map(([name, url, desc], i) => (
              <tr key={i}>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-light)', fontWeight: 600, width: 120 }}>{name}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-light)', fontFamily: 'monospace', color: 'var(--accent)' }}>{url}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-light)', color: 'var(--text-secondary)' }}>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Accordion>

      {/* Inventory Reconciliation */}
      <Accordion title={<><span style={stepNum}>4</span> Understanding Reconciliation</>}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.8, marginBottom: '16px' }}>
          Inventory Intel automatically reconciles data between Shopify and ShipHero every 4 hours. Here's how it works:
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {[
            { title: 'SKU Matching', desc: 'Products are matched between platforms using their SKU code. Make sure SKUs are identical in both Shopify and ShipHero.' },
            { title: 'Source of Truth', desc: 'ShipHero is used as the source of truth for on-hand quantities (since it reflects actual warehouse stock). Shopify is the source of truth for sales velocity (since it captures all order data).' },
            { title: 'Discrepancy Detection', desc: 'If Shopify and ShipHero show different available quantities for the same SKU, it gets flagged. Check the Inventory page for discrepancies.' },
            { title: 'Unified View', desc: 'The reconciled data powers the dashboard KPIs, forecasting engine, and purchase order suggestions.' },
          ].map((item, i) => (
            <div key={i} style={{ display: 'flex', gap: '12px', padding: '12px 16px', background: 'var(--bg-primary)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ ...stepNum, background: 'var(--accent-light)', color: 'var(--accent)', fontSize: '11px', width: 24, height: 24, marginRight: 0, marginTop: 2 }}>
                {i + 1}
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '13px', marginBottom: '2px' }}>{item.title}</div>
                <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </Accordion>

      {/* Forecasting */}
      <Accordion title={<><span style={stepNum}>5</span> How Forecasting Works</>}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.8, marginBottom: '16px' }}>
          The forecasting engine runs nightly at 3am UTC and generates 30, 60, and 90-day demand predictions for every SKU:
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {[
            { title: 'Daily Sales Aggregation', desc: 'Order line items are aggregated into daily sales per SKU over the last 365 days, with missing days filled as zero.' },
            { title: 'Outlier Removal', desc: 'Z-score method removes anomalous spikes (flash sales, data errors) to produce a clean signal.' },
            { title: 'Exponential Smoothing', desc: 'Holt-Winters exponential smoothing with additive trend is applied. If seasonality is detected, seasonal components are added.' },
            { title: 'Seasonality Detection', desc: 'Autocorrelation at 7-day and 30-day lags detects repeating patterns. If correlation > 0.3, seasonal forecasting is used.' },
            { title: 'Reorder Point', desc: 'Calculated as: (Average Daily Sales x Lead Time Days) + Safety Stock. SKUs below this threshold trigger reorder alerts.' },
            { title: 'Suggested Quantity', desc: 'Based on an 8-week supply target: (Daily Velocity x 56 days) - Current Stock. Minimum is the configured reorder quantity.' },
          ].map((item, i) => (
            <div key={i} style={{ display: 'flex', gap: '12px', padding: '12px 16px', background: 'var(--bg-primary)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ ...stepNum, background: 'var(--accent-light)', color: 'var(--accent)', fontSize: '11px', width: 24, height: 24, marginRight: 0, marginTop: 2 }}>
                {i + 1}
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '13px', marginBottom: '2px' }}>{item.title}</div>
                <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </Accordion>

      {/* Stock Health */}
      <Accordion title={<><span style={stepNum}>6</span> Stock Health Status</>}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.8, marginBottom: '16px' }}>
          Every SKU is assigned a health status based on its current stock level relative to reorder thresholds:
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {[
            { label: 'Out of Stock', color: 'var(--danger)', bg: 'var(--danger-bg)', desc: 'Available quantity is 0. Immediate action required.' },
            { label: 'Low Stock', color: 'var(--warning)', bg: 'var(--warning-bg)', desc: 'Below safety stock threshold. Order soon to avoid stockout.' },
            { label: 'Healthy', color: 'var(--success)', bg: 'var(--success-bg)', desc: 'Above safety stock. No action needed.' },
            { label: 'Excess', color: 'var(--excess)', bg: 'var(--excess-bg)', desc: 'Well above stock cover target. Consider slowing orders or running promotions.' },
          ].map((item, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: '14px',
              padding: '12px 16px', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-light)',
            }}>
              <span style={{
                padding: '4px 14px', borderRadius: '20px', fontSize: '12px',
                fontWeight: 600, background: item.bg, color: item.color, minWidth: 100, textAlign: 'center',
              }}>{item.label}</span>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{item.desc}</span>
            </div>
          ))}
        </div>
      </Accordion>

      {/* Environment Variables Reference */}
      <Accordion title={<><span style={stepNum}>7</span> Environment Variables Reference</>}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px' }}>
          All configuration is done via the <code style={{ background: 'var(--bg-primary)', padding: '1px 6px', borderRadius: 4, fontSize: '12px' }}>backend/.env</code> file:
        </p>
        <div style={codeBlock}>
          <span style={{ color: '#89b4fa' }}># Database (auto-configured for SQLite locally)</span>{'\n'}
          DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db{'\n'}
          {'\n'}
          <span style={{ color: '#89b4fa' }}># Shopify (required)</span>{'\n'}
          SHOPIFY_STORE_DOMAIN=your-store.myshopify.com{'\n'}
          SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxx{'\n'}
          {'\n'}
          <span style={{ color: '#89b4fa' }}># ShipHero (required)</span>{'\n'}
          SHIPHERO_API_TOKEN=your_bearer_token{'\n'}
          {'\n'}
          <span style={{ color: '#89b4fa' }}># App settings</span>{'\n'}
          SECRET_KEY=random-secret-string{'\n'}
          CORS_ORIGINS=http://localhost:3000,http://localhost:5173{'\n'}
          LOG_LEVEL=INFO
        </div>
      </Accordion>
    </div>
  )
}
