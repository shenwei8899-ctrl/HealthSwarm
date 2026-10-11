export function checkoutFingerprint(input) {
  // Include all purchasing inputs: unchanged packaging does not imply unchanged diners or delivery.
  return JSON.stringify(input)
}
export function createCheckoutQuote(input, now = Date.now()) {
  return { signature: checkoutFingerprint(input), expiresAt: now + 300000, clientRequestId: 'checkout-' + now + '-' + Math.random().toString(36).slice(2) }
}
export function validateCheckoutQuote(quote, input, now = Date.now()) {
  if (!quote || now >= quote.expiresAt) throw new Error('报价已过期，请重新核对结算')
  if (quote.signature !== checkoutFingerprint(input)) throw new Error('成员、菜品、地址或报价已变化，请重新核对结算')
}
