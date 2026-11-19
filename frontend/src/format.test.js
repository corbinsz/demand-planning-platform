import { formatCount, formatMoney, formatRatioPercent, formatSignedPercent } from './format'

describe('formatters', () => {
  it('formats counts and treats missing numbers as a dash', () => {
    expect(formatCount(1250)).toBe('1,250')
    expect(formatCount(null)).toBe('--')
    expect(formatCount(undefined)).toBe('--')
  })

  it('formats a ratio as a percent and keeps the sign on bias', () => {
    expect(formatRatioPercent(0.1834)).toBe('18.3%')
    expect(formatRatioPercent(null)).toBe('--')
    expect(formatSignedPercent(0.021)).toBe('+2.1%')
    expect(formatSignedPercent(-0.2)).toBe('-20.0%')
    expect(formatSignedPercent(0)).toBe('0.0%')
    expect(formatSignedPercent(null)).toBe('--')
  })

  it('formats money with no cents', () => {
    expect(formatMoney(1234.6)).toBe('$1,235')
    expect(formatMoney(0)).toBe('$0')
    expect(formatMoney(null)).toBe('$0')
  })
})
