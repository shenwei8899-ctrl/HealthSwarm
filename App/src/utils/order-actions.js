import { getOrder, updateOrder } from './orders.js'
const clone = value => JSON.parse(JSON.stringify(value))
export const batchItems = (order, index) => order.deliveryBatches?.find(batch => batch.index === index)?.items || order.items || []
export const afterSales = order => order?.afterSales?.length ? order.afterSales : (order?.afterSale ? [order.afterSale] : [])
export const currentAfterSale = (order, index) => afterSales(order).find(entry => entry.batchIndex === (order.deliveryBatches?.length ? index : null) && !['已完成', '已撤销', '已拒绝'].includes(entry.status))
export function mutableBatches(order) {
  return (order.deliveryBatches || []).filter(batch => !order.receivedBatchIndices?.includes(batch.index) && !['shipped', 'delivered', 'cancelled'].includes(batch.fulfillmentStatus))
}
export function canOrderAction(order, action, index = 1) {
  if (!order) return false
  if (order.allowedActions !== undefined) {
    const allowed = Array.isArray(order.allowedActions) ? order.allowedActions.includes(action) : order.allowedActions[action] === true
    if (!allowed) return false
  } else if (!order.isDemo) return false
  const paid = order.paymentStatus ? order.paymentStatus === 'paid' : !['pending', 'cancelled'].includes(order.status)
  const batch = order.deliveryBatches?.find(item => item.index === index)
  const received = batch ? order.receivedBatchIndices?.includes(index) : order.status === 'delivered'
  if (action === 'receive') return paid && !received && order.status !== 'cancelled' && (!batch || batch.fulfillmentStatus !== 'cancelled')
  if (action === 'afterSale') return paid && order.status !== 'cancelled'
  if (!paid || ['cancelled', 'refund_pending', 'delivered'].includes(order.status)) return false
  if (action === 'changeAddress') return Boolean(batch && mutableBatches(order).some(item => item.index === index))
  if (action === 'resume') return Boolean(order.planPaused || order.status === 'paused') && mutableBatches(order).length > 0
  if (action === 'pause') return !order.planPaused && order.status !== 'paused' && mutableBatches(order).length > 0
  if (action === 'cancelRemaining') return mutableBatches(order).length > 0
  return false
}
function requiredOrder(id, action, index) {
  const order = getOrder(id)
  if (!canOrderAction(order, action, index)) throw new Error('当前状态不支持此操作，请刷新订单')
  return order
}
function aggregateStatus(order, received = order.receivedBatchIndices || []) {
  if (order.refundStatus === 'pending' || order.status === 'refund_pending') return 'refund_pending'
  if (order.deliveryBatches?.length && received.length === order.deliveryBatches.length) return 'delivered'
  if (order.planPaused || order.status === 'paused') return 'paused'
  if (order.deliveryBatches?.length) return received.length === order.deliveryBatches.length ? 'delivered' : received.length ? 'partial' : 'paid'
  return 'delivered'
}
export function receiveOrder(id, index = 1) {
  const existing = getOrder(id)
  if (existing?.receivedBatchIndices?.includes(index) || !existing?.deliveryBatches?.length && existing?.status === 'delivered') return existing
  const order = requiredOrder(id, 'receive', index)
  const received = order.deliveryBatches?.length ? [...new Set([...(order.receivedBatchIndices || []), index])].sort((a, b) => a - b) : []
  return updateOrder(id, { receivedBatchIndices: received, status: aggregateStatus(order, received),
    planPaused: order.deliveryBatches?.length && received.length === order.deliveryBatches.length ? false : Boolean(order.planPaused || order.status === 'paused'),
    fulfillmentStatus: order.deliveryBatches?.length && received.length < order.deliveryBatches.length ? 'partial' : 'delivered',
    deliveryBatches: (order.deliveryBatches || []).map(batch => batch.index === index ? { ...batch, fulfillmentStatus: 'delivered', deliveredAt: new Date().toISOString() } : batch),
    deliveredAt: new Date().toISOString() })
}
export function pauseOrder(id) {
  const order = requiredOrder(id, 'pause')
  return updateOrder(id, { planPaused: true, status: 'paused',
    deliveryBatches: order.deliveryBatches.map(batch => mutableBatches(order).some(item => item.index === batch.index) ? { ...batch, fulfillmentStatus: 'paused' } : batch) })
}
const resumeSignature = order => JSON.stringify([order.planPaused, order.status, order.deliveryBatches, order.receivedBatchIndices])
export function previewResume(id) {
  const order = requiredOrder(id, 'resume')
  const changeable = mutableBatches(order)
  let next = new Date(); next.setHours(12, 0, 0, 0); next.setDate(next.getDate() + 2)
  const fixedDates = order.deliveryBatches.filter(batch => !changeable.some(item => item.index === batch.index)).map(batch => new Date(batch.date + 'T12:00:00')).filter(date => !Number.isNaN(date.getTime()))
  for (const date of fixedDates) if (date >= next) { next = new Date(date); next.setDate(next.getDate() + 1) }
  const batches = changeable.map(batch => {
    const current = new Date(batch.date + 'T12:00:00')
    if (current > next) next = current
    const date = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-${String(next.getDate()).padStart(2, '0')}`
    next.setDate(next.getDate() + 1)
    return { ...clone(batch), date, label: date, fulfillmentStatus: 'preparing' }
  })
  return { signature: resumeSignature(order), expiresAt: Date.now() + 300000, batches, isDemo: true }
}
export function resumeOrder(id, preview) {
  const order = requiredOrder(id, 'resume')
  if (!preview || preview.expiresAt < Date.now() || preview.signature !== resumeSignature(order)) throw new Error('排程已变化，请重新预览')
  const next = { ...order, planPaused: false, status: 'paid' }
  return updateOrder(id, { planPaused: false, status: aggregateStatus(next), deliveryBatches: order.deliveryBatches.map(batch => preview.batches.find(item => item.index === batch.index) || batch) })
}
export function changeOrderBatchAddress(id, index, address) {
  const order = requiredOrder(id, 'changeAddress', index)
  if (!address?.id || !address.name?.trim() || !/^1\d{10}$/.test(address.phone || '') || !address.region?.trim() || !address.detail?.trim()) throw new Error('请选择完整有效的收货地址')
  return updateOrder(id, { deliveryBatches: order.deliveryBatches.map(batch => batch.index === index ? { ...batch, addressSnapshot: clone(address) } : batch) })
}
export function submitOrderAfterSale(id, form) {
  const order = requiredOrder(id, 'afterSale', form.batchIndex || 1)
  const index = order.deliveryBatches?.length ? form.batchIndex : null
  if (order.deliveryBatches?.length && !order.deliveryBatches.some(batch => batch.index === index)) throw new Error('请选择有效批次')
  const existing = currentAfterSale(order, index)
  if (existing) return order
  const available = batchItems(order, index)
  if((form.items||[]).some(item=>!Number.isInteger(Number(item.quantity))||Number(item.quantity)<0))throw new Error('请选择商品并填写有效的申请数量')
  const items = (form.items || []).filter(item => Number(item.quantity) > 0)
  if (!items.length || items.some(item => !Number.isInteger(Number(item.quantity)) || !available.some(product => String(product.id) === String(item.id) && Number(item.quantity) <= product.quantity))) throw new Error('请选择商品并填写有效的申请数量')
  if (!['希望补发', '希望退款', '请工作人员联系我'].includes(form.expectation) || !form.reason?.trim()) throw new Error('请填写售后原因和期望处理方式')
  const entry = { id: 'AS-' + Date.now() + '-' + afterSales(order).length, batchIndex: index, items: clone(items), expectation: form.expectation,
    reason: form.reason.trim(), description: (form.description || '').trim(), attachments: [...(form.attachments || [])].slice(0, 3), status: '已提交', createdAt: new Date().toISOString(), isDemo: true }
  return updateOrder(id, { afterSales: [...afterSales(order), entry], afterSale: entry })
}
export function remainingRefundPreview(id) {
  const order = requiredOrder(id, 'cancelRemaining')
  return { batchIndices: mutableBatches(order).map(batch => batch.index), amountCents: null, explanation: '退款金额需由商城服务计算；测试申请不会产生退款' }
}
export function cancelOrderRemaining(id) {
  const preview = remainingRefundPreview(id)
  return updateOrder(id, { status: 'refund_pending', refundStatus: 'pending', refundPreview: preview })
}
