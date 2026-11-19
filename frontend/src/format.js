/** Display helpers. en-US so the same number looks the same in tests and in the UI. */

export function formatCount(value) {
  if (value === null || value === undefined || value === '') return '--'
  const number = Number(value)
  if (Number.isNaN(number)) return '--'
  return number.toLocaleString('en-US')
}

export function formatRatioPercent(ratio, digits = 1) {
  if (ratio === null || ratio === undefined || ratio === '') return '--'
  const number = Number(ratio)
  if (Number.isNaN(number)) return '--'
  return `${(number * 100).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`
}

export function formatSignedPercent(ratio, digits = 1) {
  if (ratio === null || ratio === undefined || ratio === '') return '--'
  const number = Number(ratio)
  if (Number.isNaN(number)) return '--'
  const absolute = Math.abs(number * 100).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
  if (number > 0) return `+${absolute}%`
  if (number < 0) return `-${absolute}%`
  return `${absolute}%`
}

export function formatMoney(value) {
  const amount = Number(value ?? 0)
  const safe = Number.isNaN(amount) ? 0 : amount
  return `$${safe.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`
}
