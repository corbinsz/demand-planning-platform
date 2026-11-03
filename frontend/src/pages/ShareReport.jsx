import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getSharedBrief } from '../services/api'

export default function ShareReport() {
  const { token } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    getSharedBrief(token)
      .then((response) => setData(response.data))
      .catch(() => setError('This link is no longer available.'))
  }, [token])
  if (error) return <div className="landing"><p role="alert">{error}</p></div>
  if (!data) return <div className="landing"><p>Opening the brief…</p></div>
  const summary = data.summary || {}
  return (
    <article className="landing legal">
      <p className="page-kicker">Read-only brief</p>
      <h1>{data.workspace_name}</h1>
      <p>
        {summary.stockout_risk_count} stockout risks · {summary.reorder_count} reorder lines ·
        {' '}${Math.round(summary.dead_stock_value || 0).toLocaleString()} in quiet stock at cost.
      </p>
      {data.is_demo && <p>Sample data for a fictional brand. Not a customer.</p>}
      <h2>Stockout risk</h2>
      <ul>
        {(data.stockout_risks || []).map((row) => (
          <li key={row.sku}>{row.title}: {row.days_of_stock_remaining} days left, buy {row.suggested_reorder_qty}.</li>
        ))}
      </ul>
      <h2>Reorder</h2>
      <ul>
        {(data.reorders || []).map((row) => (
          <li key={row.sku}>{row.title}: buy {row.suggested_reorder_qty}.</li>
        ))}
      </ul>
      <h2>Quiet stock</h2>
      <ul>
        {(data.dead_stock || []).map((row) => (
          <li key={row.sku}>{row.title}: ${Math.round(row.inventory_value).toLocaleString()} at cost. {row.recommendation}.</li>
        ))}
      </ul>
      <p><a href={`/api/reports/share/${token}/pdf`}>Download PDF</a></p>
    </article>
  )
}
