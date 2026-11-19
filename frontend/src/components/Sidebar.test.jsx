import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Sidebar from './Sidebar'

describe('Sidebar', () => {
  it('links to the planning pages', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    )

    expect(screen.getByRole('link', { name: /Dashboard/ })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: /Inventory/ })).toHaveAttribute('href', '/inventory')
    expect(screen.getByRole('link', { name: /Forecasting/ })).toHaveAttribute('href', '/forecasting')
    expect(screen.getByRole('link', { name: /Purchase Orders/ })).toHaveAttribute('href', '/purchase-orders')
    expect(screen.getByText('Demand Planning Platform')).toBeInTheDocument()
    expect(screen.getByText('Synthetic demo')).toBeInTheDocument()
  })
})
