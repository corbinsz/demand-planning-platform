/** Display helpers. en-US so the same number looks the same in tests and in the UI. */

export function formatCount(value) {
  if (value === null || value === undefined || value === '') return '--'
  const number = Number(value)
  if (Number.isNaN(number)) return '--'
  return number.toLocaleString('en-US')
}

export function formatMoney(value) {
  const amount = Number(value ?? 0)
  const safe = Number.isNaN(amount) ? 0 : amount
  return `$${safe.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`
}
