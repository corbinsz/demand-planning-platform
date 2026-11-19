import { formatCount, formatMoney } from './format'

describe('formatters', () => {
  it('formats counts and treats missing numbers as a dash', () => {
    expect(formatCount(1250)).toBe('1,250')
    expect(formatCount(null)).toBe('--')
    expect(formatCount(undefined)).toBe('--')
  })

  it('formats money with no cents', () => {
    expect(formatMoney(1234.6)).toBe('$1,235')
    expect(formatMoney(0)).toBe('$0')
    expect(formatMoney(null)).toBe('$0')
  })
})
