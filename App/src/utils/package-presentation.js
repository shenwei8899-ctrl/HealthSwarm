export function packagePrice(value) {
  const cents = typeof value === 'number' ? value
    : typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : NaN
  return Number.isSafeInteger(cents) && cents >= 0 ? (cents / 100).toFixed(2) : null
}

export function packageSpec(value) {
  return String(value || '').trim().replace(/^(\d+)\.(\d+)([^\d.]*)$/, (_, whole, fraction, unit) => {
    const decimals = fraction.replace(/0+$/, '')
    return whole + (decimals ? '.' + decimals : '') + unit
  })
}
