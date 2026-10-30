export function packagePrice(value) {
  const cents = typeof value === 'number' ? value
    : typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : NaN
  return Number.isSafeInteger(cents) && cents >= 0 ? (cents / 100).toFixed(2) : null
}

export function packageTone(offer) {
  const identity = String(offer.sku_id || offer.name || '')
  return Array.from(identity).reduce((sum, letter) => sum + letter.codePointAt(0), 0) % 3
}
