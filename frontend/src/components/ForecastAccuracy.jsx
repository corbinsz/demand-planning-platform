import { formatCount, formatRatioPercent, formatSignedPercent } from '../format'
import { tdStyle, thStyle } from './shared/tableStyles'

const cardStyle = {
  background: 'var(--bg-white)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '16px 18px',
  flex: '1 1 150px',
  boxShadow: 'var(--shadow-sm)',
}

function comparisonSentence(report) {
  const holt = report.holt_winters.wape
  const naive = report.seasonal_naive.wape
  if (holt == null || naive == null) return 'Not enough unit sales to score either method.'
  const points = (naive - holt) * 100
  const formatted = Math.abs(points).toLocaleString('en-US', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
  if (Math.abs(points) < 0.05) {
    return 'Holt-Winters and repeating the last week land on the same WAPE.'
  }
  if (points > 0) {
    return `Holt-Winters WAPE is ${formatted} points lower than repeating the last week.`
  }
  return `Holt-Winters WAPE is ${formatted} points higher than repeating the last week.`
}

function Metric({ label, value, detail }) {
  return (
    <div style={cardStyle}>
      <div style={{
        fontSize: '11px',
        color: 'var(--text-secondary)',
        textTransform: 'uppercase',
        letterSpacing: '0.6px',
        fontWeight: 600,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: '24px',
        fontWeight: 700,
        fontFamily: 'Poppins, sans-serif',
        marginTop: '8px',
        lineHeight: 1.1,
      }}>
        {value}
      </div>
      {detail && (
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '6px' }}>
          {detail}
        </div>
      )}
    </div>
  )
}

export default function ForecastAccuracy({ report, loading, error }) {
  return (
    <section>
      <div style={{ marginBottom: '14px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>
          Forecast accuracy
        </h3>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px', maxWidth: 760 }}>
          30-day holdouts on this catalog. Holt-Winters is the forecast the app uses.
          The baseline repeats the last 7 days. Positive bias means the forecast was higher than the units that sold.
          The orders are synthetic.
        </p>
      </div>

      {loading ? (
        <div style={{ ...cardStyle, color: 'var(--text-muted)', fontSize: '13px' }}>
          Scoring holdouts. The first pass fits a model per SKU and is cached for 30 minutes.
        </div>
      ) : error ? (
        <div style={{
          background: 'var(--danger-bg)',
          border: '1px solid var(--danger)',
          borderRadius: 'var(--radius)',
          padding: '16px 18px',
          color: '#b91c1c',
          fontSize: '13px',
        }}>
          {error}
        </div>
      ) : !report || report.sku_count === 0 ? (
        <div style={{ ...cardStyle, color: 'var(--text-secondary)', fontSize: '13px' }}>
          Not enough history yet. A SKU needs 150 daily observations before a 30-day holdout can be scored.
        </div>
      ) : (
        <>
          <p style={{ fontSize: '13px', color: 'var(--text-primary)', marginBottom: '12px' }}>
            {comparisonSentence(report)}
            {' '}
            {formatCount(report.sku_count)} SKUs, {formatCount(report.evaluated_origins)} holdouts.
            {report.skipped_skus === 1 && ' 1 SKU was too short to score.'}
            {report.skipped_skus > 1 && ` ${formatCount(report.skipped_skus)} SKUs were too short to score.`}
          </p>
          <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
            <Metric
              label="Holt-Winters WAPE"
              value={formatRatioPercent(report.holt_winters.wape)}
              detail="absolute error / units sold"
            />
            <Metric
              label="Holt-Winters bias"
              value={formatSignedPercent(report.holt_winters.bias)}
              detail="positive over-forecasts"
            />
            <Metric
              label="Seasonal naive WAPE"
              value={formatRatioPercent(report.seasonal_naive.wape)}
              detail="repeat the last 7 days"
            />
            <Metric
              label="Seasonal naive bias"
              value={formatSignedPercent(report.seasonal_naive.bias)}
              detail="positive over-forecasts"
            />
          </div>

          <div style={{
            marginTop: '14px',
            background: 'var(--bg-white)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            boxShadow: 'var(--shadow-sm)',
            maxHeight: 360,
            overflow: 'auto',
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>SKU</th>
                  <th style={thStyle}>Holdouts</th>
                  <th style={thStyle}>Actual units</th>
                  <th style={thStyle}>Holt-Winters WAPE</th>
                  <th style={thStyle}>Bias</th>
                  <th style={thStyle}>Naive WAPE</th>
                  <th style={thStyle}>Naive bias</th>
                </tr>
              </thead>
              <tbody>
                {report.skus.map((row) => (
                  <tr key={row.sku}>
                    <td style={tdStyle}>
                      <div style={{ fontWeight: 600 }}>{row.sku}</div>
                      <div style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>{row.title}</div>
                    </td>
                    <td style={tdStyle}>{formatCount(row.origins)}</td>
                    <td style={tdStyle}>{formatCount(row.actual_units)}</td>
                    <td style={tdStyle}>{formatRatioPercent(row.holt_winters.wape)}</td>
                    <td style={tdStyle}>{formatSignedPercent(row.holt_winters.bias)}</td>
                    <td style={tdStyle}>{formatRatioPercent(row.seasonal_naive.wape)}</td>
                    <td style={tdStyle}>{formatSignedPercent(row.seasonal_naive.bias)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
