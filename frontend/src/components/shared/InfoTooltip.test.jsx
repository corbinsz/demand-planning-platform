import { fireEvent, render, screen } from '@testing-library/react'
import InfoTooltip from './InfoTooltip'

describe('InfoTooltip', () => {
  it('shows the explanation while the control is hovered', () => {
    render(
      <InfoTooltip text="Lead time is how long the supplier takes to deliver.">
        <button type="button">Why</button>
      </InfoTooltip>
    )

    expect(screen.queryByText(/Lead time/)).not.toBeInTheDocument()
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Why' }))
    expect(screen.getByText(/Lead time is how long/)).toBeInTheDocument()
    fireEvent.mouseLeave(screen.getByRole('button', { name: 'Why' }))
    expect(screen.queryByText(/Lead time/)).not.toBeInTheDocument()
  })
})
