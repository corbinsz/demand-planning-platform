import { render, screen } from '@testing-library/react'
import KPICards from './KPICards'

const data = {
  total_skus: 55,
  total_on_hand_units: 1200,
  orders_last_30d: 640,
  revenue_last_30d: 18420,
  units_sold_last_30d: 900,
  sell_through_rate: 42.8,
  skus_below_reorder: 3,
  revenue_at_risk_daily: 25,
  total_inventory_cost: 4100,
}

describe('KPICards', () => {
  it('renders nothing until the dashboard has loaded', () => {
    const { container } = render(<KPICards data={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the planning numbers from the API', () => {
    render(<KPICards data={data} />)
    expect(screen.getByText('55')).toBeInTheDocument()
    expect(screen.getByText('$18,420')).toBeInTheDocument()
    expect(screen.getByText('42.8%')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('$25')).toBeInTheDocument()
  })
})
