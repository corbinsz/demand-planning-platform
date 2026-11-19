import { render, screen } from '@testing-library/react'
import ForecastAccuracy from './ForecastAccuracy'

const report = {
  sku_count: 2,
  skipped_skus: 1,
  evaluated_origins: 8,
  holt_winters: { wape: 0.22, bias: 0.04 },
  seasonal_naive: { wape: 0.31, bias: -0.02 },
  skus: [
    {
      sku: 'VE-SHIFT',
      title: 'Shifted Tee',
      origins: 4,
      actual_units: 800,
      holt_winters: { wape: 0.4, bias: 0.1 },
      seasonal_naive: { wape: 0.5, bias: -0.05 },
    },
    {
      sku: 'VE-FLAT',
      title: 'Flat Tee',
      origins: 4,
      actual_units: 240,
      holt_winters: { wape: 0.05, bias: 0 },
      seasonal_naive: { wape: 0.05, bias: 0 },
    },
  ],
}

describe('ForecastAccuracy', () => {
  it('says the backtest is still running', () => {
    render(<ForecastAccuracy report={null} loading error={null} />)
    expect(screen.getByText(/Scoring holdouts/)).toBeInTheDocument()
  })

  it('shows the error from the API', () => {
    render(<ForecastAccuracy report={null} loading={false} error="Forecast accuracy could not be computed." />)
    expect(screen.getByText('Forecast accuracy could not be computed.')).toBeInTheDocument()
  })

  it('explains when no SKU has a long enough history', () => {
    render(<ForecastAccuracy report={{ sku_count: 0 }} loading={false} error={null} />)
    expect(screen.getByText(/Not enough history yet/)).toBeInTheDocument()
  })

  it('shows overall WAPE and one row per SKU', () => {
    render(<ForecastAccuracy report={report} loading={false} error={null} />)
    expect(screen.getByText('22.0%')).toBeInTheDocument()
    expect(screen.getByText('+4.0%')).toBeInTheDocument()
    expect(screen.getByText('31.0%')).toBeInTheDocument()
    expect(screen.getByText(/9.0 points lower/)).toBeInTheDocument()
    expect(screen.getByText('VE-SHIFT')).toBeInTheDocument()
    expect(screen.getByText('Shifted Tee')).toBeInTheDocument()
    expect(screen.getByText(/1 SKU was too short to score/)).toBeInTheDocument()
  })
})
