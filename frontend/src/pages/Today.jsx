import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Explain from '../components/Explain'
import { getDigest, getToday } from '../services/api'
import { track } from '../analytics'

function List({ items, empty, render }) {
  if (!items.length) return <p>{empty}</p>
  return <ol>{items.map(render)}</ol>
}

export default function Today() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [email, setEmail] = useState(null)

  useEffect(() => {
    getToday()
      .then((response) => {
        setData(response.data)
        track('view_today')
      })
      .catch((err) => setError(err.response?.data?.detail || 'Today’s list didn’t load.'))
  }, [])

  if (error) {
    return (
      <div>
        <h1>Today</h1>
        <p role="alert">{error}</p>
      </div>
    )
  }
  if (!data) return <p>Preparing today’s list…</p>

  return (
    <div>
      <p className="page-kicker">{data.workspace_name}</p>
      <h1 style={{ fontSize: 32, letterSpacing: '-0.03em' }}>What to do today</h1>
      <p className="lead">{data.lead}</p>
      <div className="today-grid">
        <section className="decision-card" aria-labelledby="stockout-heading">
          <p className="page-kicker">Will run out first</p>
          <h2 id="stockout-heading">
            <Explain text="These products will hit zero before a new shipment can land. The clock is supplier lead time, not a generic 30 days.">
              {data.stockout_count} stockout {data.stockout_count === 1 ? 'risk' : 'risks'}
            </Explain>
          </h2>
          <List
            items={data.stockout_risks}
            empty="Nothing is inside lead time."
            render={(row) => (
              <li key={row.sku}>
                <strong>{row.title}</strong>
                <div>{row.plain}</div>
                <div>{row.range_plain}</div>
              </li>
            )}
          />
          <Link to="/forecasting">See every forecast</Link>
        </section>
        <section className="decision-card" aria-labelledby="buy-heading">
          <p className="page-kicker">Place these</p>
          <h2 id="buy-heading">
            <Explain text="Buy quantity covers about eight weeks of the forecast, minus what is already in the warehouse. A supplier minimum applies only when you actually need to order.">
              {data.reorder_count} to reorder
            </Explain>
          </h2>
          <List
            items={data.reorders}
            empty="No purchase needed today."
            render={(row) => (
              <li key={row.sku}>
                <strong>Buy {row.suggested_reorder_qty}</strong> · {row.title}
                <div>{row.plain}</div>
              </li>
            )}
          />
          <Link to="/purchase-orders">Open the buy list</Link>
        </section>
        <section className="decision-card" aria-labelledby="cash-heading">
          <p className="page-kicker">Cash sitting still</p>
          <h2 id="cash-heading">
            <Explain text="Valued at what you paid the supplier (cost), not the sticker price. Quiet means little or no sales for a long stretch.">
              <span className="money">${Math.round(data.dead_stock_value).toLocaleString()}</span> in quiet stock
            </Explain>
          </h2>
          <List
            items={data.dead_stock}
            empty="No quiet stock with units on hand."
            render={(row) => (
              <li key={row.sku}>
                <strong>{row.title}</strong>
                <div>{row.plain}</div>
              </li>
            )}
          />
          <Link to="/reports">Review dead stock</Link>
        </section>
      </div>

      <section style={{ marginTop: 28 }} aria-labelledby="alerts-heading">
        <h2 id="alerts-heading" style={{ fontSize: 20 }}>Alerts</h2>
        <p className="lead" style={{ fontSize: 15 }}>
          Stockouts and overstock, in sentences. A weekly email is prepared every Monday at 8:00am Mountain Time (Utah).
        </p>
        <div className="alert-list">
          {data.alerts.length === 0 && <p>No alerts.</p>}
          {data.alerts.map((alert) => (
            <article key={`${alert.kind}-${alert.sku}`} className="alert-row">
              <span className={`pill ${alert.severity}`}>{alert.headline}</span>
              <p>{alert.plain}</p>
            </article>
          ))}
        </div>
        <button
          type="button"
          className="btn ghost"
          style={{ marginTop: 12 }}
          onClick={() => getDigest().then((response) => setEmail(response.data))}
        >
          Preview the Monday email
        </button>
        {email && (
          <pre style={{
            marginTop: 12, whiteSpace: 'pre-wrap', background: '#fff',
            border: '1px solid var(--border)', borderRadius: 12, padding: 16, fontSize: 14,
          }}>{email.text}</pre>
        )}
      </section>
    </div>
  )
}
