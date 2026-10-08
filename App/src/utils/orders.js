const ORDER_KEY = 'demo-orders-v1'
let lastOrderTime = 0
let orderSequence = 0

export const ORDER_STATUS = {
  pending: { label: '待支付', detail: '等待支付前确认' },
  paid: { label: '待配送', detail: '已支付，商家正在备货' },
  partial: { label: '配送中', detail: '部分批次已确认收到' },
  paused: { label: '计划暂停', detail: '未发货批次已暂停，已发货批次不变' },
  refund_pending: { label: '退款处理中', detail: '剩余计划取消申请已提交' },
  cancelled: { label: '已取消', detail: '取消或退款流程已有最终结果' },
  delivered: { label: '已送达', detail: '用户已确认收到演示食材' },
}

export function getOrders() {
  const orders = uni.getStorageSync(ORDER_KEY) || []
  return [...orders].sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)))
}

export function getOrder(id) { return getOrders().find(order => order.id === id) || null }

function writeOrders(orders) { uni.setStorageSync(ORDER_KEY, JSON.parse(JSON.stringify(orders))) }

export function createDemoOrder({ items, totalCents, meal, caseId = '', sourcePlanId = '', bundleId = '', planName = '', deliveryBatches = [], cookingGuide = null, cookingGuides = [], addressSnapshot = null }) {
  const now = new Date()
  const timestamp = now.getTime()
  orderSequence = timestamp === lastOrderTime ? orderSequence + 1 : 0
  lastOrderTime = timestamp
  const order = {
    id: 'FN' + String(timestamp).slice(-10) + String(orderSequence).padStart(2, '0'),
    createdAt: now.toISOString(),
    displayTime: `${now.getMonth() + 1}月${now.getDate()}日 ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`,
    status: 'paid',
    statusUpdatedAt: now.toISOString(),
    meal,
    caseId,
    sourcePlanId,
    planName,
    bundleId,
    deliveryBatches,
    cookingGuide,
    cookingGuides,
    receivedBatchIndices: [],
    totalCents,
    address: addressSnapshot ? addressSnapshot.region+' '+addressSnapshot.detail : '演示地址：幸福路 88 号 1 幢 101 室',
    addressSnapshot: addressSnapshot ? JSON.parse(JSON.stringify(addressSnapshot)) : null,
    contact: addressSnapshot ? addressSnapshot.name+' · '+addressSnapshot.phone : '林女士（虚拟） · 138****0000',
    items: items.map(item => ({ id: item.id, icon: item.icon, name: item.name, quantity: item.quantity, unit: item.unit, pack: item.pack, priceCents: item.priceCents })),
    afterSale: null,
    isDemo: true,
  }
  const orders = getOrders()
  orders.unshift(order)
  writeOrders(orders)
  return order
}

export function updateOrder(id, patch) {
  const orders = getOrders()
  const index = orders.findIndex(order => order.id === id)
  if (index < 0) return null
  orders[index] = { ...orders[index], ...patch, statusUpdatedAt: new Date().toISOString() }
  writeOrders(orders)
  return orders[index]
}

export function pendingOrderCount() { return getOrders().filter(order => order.status === 'paid' || order.status === 'partial').length }
export function clearOrders() { writeOrders([]) }

export function orderStatus(order) {
  if (ORDER_STATUS[order?.status] && !['partial','delivered'].includes(order.status)) return ORDER_STATUS[order.status]
  if (order?.sourcePlanId && order.status === 'partial') return { label: '配送中', detail: `已收到 ${(order.receivedBatchIndices || []).length} / ${order.deliveryBatches?.length || 21} 批` }
  if (order?.sourcePlanId && order.status === 'delivered' && !order.receivedBatchIndices?.length) return { label: '首批已送达', detail: '旧演示订单已确认首批收货' }
  if (order?.sourcePlanId && order.status === 'delivered') return { label: '全部已送达', detail: '计划配送批次均已确认收到' }
  return ORDER_STATUS[order?.status] || ORDER_STATUS.paid
}
