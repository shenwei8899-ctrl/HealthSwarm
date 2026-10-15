const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
const units = { g: 'g', kg: 'kg', piece: '个', ml: 'ml', l: 'L' }
const same = (a, b) => String(a) === String(b)
const memberKey = members => JSON.stringify((members || []).map(m => String(m.id)).sort())
const textIngredient = item => typeof item === 'string' ? item : [item?.name, item?.amount ?? item?.required_value, units[item?.unit ?? item?.required_unit] || item?.unit || item?.required_unit].filter(v => v !== undefined && v !== '').join(' ')

export function emptyCommerceMeal(members = [], meal = 'dinner') {
  return { meal: mealNames[meal] || meal, members, count: members.length, dishes: [], products: [], memberNotes: [], nutrition: null, blocked: [], sourceType: 'api', paid: false, safetyText: '个体化营养与个人份量尚未接入，请核对实际食材与已知饮食限制。' }
}

export function commerceRecipe(recipe) {
  return {
    name: recipe.recipe_name || recipe.name || '', recipeId: recipe.recipe_ref, recipeVersion: recipe.recipe_version,
    detail: (recipe.ingredients || []).map(textIngredient).join(' · '), icon: '菜', color: '#e4f0d3',
    image: recipe.image_url || '', minutes: Number(recipe.minutes) > 0 ? Number(recipe.minutes) : null,
    ingredients: (recipe.ingredients || []).map(textIngredient),
    steps: (recipe.steps || []).map(step => typeof step === 'string' ? step : step.text || step.description || '').filter(Boolean),
    notes: recipe.notes || [], stepImages: recipe.step_images || [], videoUrl: recipe.video_url || '', nutrition: null, kcal: null,
  }
}

export function commerceMealView(menu, { members = [], meal = 'dinner', quantities = {}, contextIssue = '' } = {}) {
  const plan = emptyCommerceMeal(members, meal)
  if (!menu) return plan
  plan.dishes = (menu.dishes || []).map(commerceRecipe)
  plan.isLocalFixture = menu.is_local_fixture === true
  plan.packageSn = menu.package_sn
  plan.packageVersion = menu.package_version
  plan.source = plan.isLocalFixture ? '本地联调菜单' : '服务端已保存菜单'
  plan.blocked = (menu.issues || []).map(issue => issue.message || issue.issue_code).filter(Boolean)
  if (!menu.available) plan.blocked.push(menu.message || '本餐菜单或食材尚不可购买，请重新核对。')
  if (contextIssue) plan.blocked.push(contextIssue)
  plan.products = (menu.items || []).map(item => {
    const sku = item.sku
    const requirements = (menu.ingredient_requirements || []).filter(r => same(r.ingredient_id, item.ingredient_id))
    const required = requirements.length && requirements.every(r => Number.isFinite(Number(r.required_value)) && r.required_unit === requirements[0].required_unit)
      ? requirements.reduce((sum, r) => sum + Number(r.required_value), 0) : null
    const unit = units[sku.net_content?.unit] || sku.net_content?.unit || ''
    const id = String(sku.sku_id), quantity = Number(quantities[id] ?? item.quantity)
    return {
      id, skuId: id, name: sku.product_name, skuName: sku.sku_name || '', icon: '食材', imageUrl: sku.image_url || '',
      need: required, needLabel: required === null ? '用量待确认' : required + (units[requirements[0].required_unit] || requirements[0].required_unit),
      pack: Number(sku.net_content?.value) || null, unit, packLabel: sku.net_content?.value ? Number(sku.net_content.value) + unit + '/包' : sku.sku_name || '规格待确认',
      quantity, priceCents: Number(sku.price_cent), availableQuantity: Number(sku.available_quantity),
      valid: Number.isInteger(quantity) && quantity > 0 && quantity <= Number(sku.available_quantity),
    }
  })
  return plan
}

export function newMealCommerceState() {
  return { menu: null, cart: [], address: null, slots: [], slotId: 0, quote: null, selected: [], quantities: {}, ready: false, busy: false, error: '', checkoutError: '', deliveryMessage: '', deliverySupported: null, contextIssue: '', baselineMembers: '', baselineProfile: '', pending: null, orderSn: '' }
}

export function createMealCommerceController({ state, api, scope, context }) {
  let epoch = 0, disposed = false, currentScope = scope()
  function reset() { epoch++; Object.assign(state, newMealCommerceState()); currentScope = scope() }
  function sync() { if (currentScope !== scope()) reset() }
  function invalidateQuote() { state.quote = null; state.checkoutError = '' }
  function membersChanged(invalidate = true) {
    if (invalidate) invalidateQuote()
    const input = context()
    const changed = memberKey(input.members) !== state.baselineMembers || JSON.stringify(input.members || []) !== state.baselineProfile
    const issue = changed ? '就餐者或健康档案已调整，需要营养师重新确认本餐菜单和采购量；当前重配服务尚未接入。' : ''
    if (issue !== state.contextIssue) invalidateQuote()
    state.contextIssue = issue
  }
  async function run(work, checkout = false) {
    sync()
    if (disposed || state.busy) return null
    const ticket = epoch, account = scope()
    const active = () => !disposed && ticket === epoch && account === scope()
    state.busy = true
    if (checkout) state.checkoutError = ''; else state.error = ''
    try { return await work(active) }
    catch (error) { if (active()) { if (checkout) state.checkoutError = error.message; else state.error = error.message } return null }
    finally { sync(); if (active()) state.busy = false }
  }
  const sameMenu = (a, b) => a?.package_sn && a.package_sn === b?.package_sn && a.package_version === b?.package_version
  const ownsLine = line => line.source_type === 'recommendation_package' && same(line.source_ref, state.menu?.package_sn) && same(line.source_version, state.menu?.package_version)
  function guard() {
    const input = context()
    if (input.unsupported) throw new Error('当前按单餐采购；三餐合并和周期计划的交易契约尚未接入。')
    if (!state.ready || !state.menu?.available) throw new Error('本餐菜单和食材尚未确认，请刷新后重试。')
    membersChanged(false)
    if (state.contextIssue) throw new Error(state.contextIssue)
    if (!state.selected.length) throw new Error('请至少选择一件本餐食材。')
    const products = commerceMealView(state.menu, { quantities: state.quantities }).products
    if (state.selected.some(id => !products.some(p => same(p.id, id) && p.valid))) throw new Error('所选食材已不可购买，请核对库存与数量。')
  }
  async function load() {
    return run(async active => {
      const input = context()
      if (!input.enabled) return
      if (input.unsupported) { state.ready = false; state.error = '当前按单餐采购；三餐合并和周期计划的交易契约尚未接入。'; return }
      state.ready = false; invalidateQuote()
      const [menu, basket, addresses] = await Promise.all([api.meal(input.meal, input.date), api.cart(), api.addresses()])
      if (!active()) return
      const unchanged = sameMenu(state.menu, menu)
      state.menu = menu; state.cart = basket.items; invalidateQuote()
      if (!unchanged) {
        const menuLines = basket.items.filter(ownsLine)
        state.quantities = Object.fromEntries((menu.items || []).map(item => [String(item.sku.sku_id), menuLines.find(line => same(line.sku_id, item.sku.sku_id))?.quantity ?? item.quantity]))
        state.selected = menuLines.length ? menuLines.filter(line => line.selected).map(line => String(line.sku_id)) : (menu.items || []).map(item => String(item.sku.sku_id))
      }
      if (!state.baselineMembers || !unchanged) { state.baselineMembers = memberKey(input.members); state.baselineProfile = JSON.stringify(input.members || []) }
      membersChanged()
      state.address = addresses.find(address => address.isDefault) || null
      state.pending = api.pendingOrder(); state.ready = true
      state.slots = []; state.deliveryMessage = ''; state.deliverySupported = null; state.slotId = 0
      if (state.address) {
        try {
          const result = await api.slots(state.address.id)
          if (active()) {
            state.deliverySupported = result.supported !== false
            state.deliveryMessage = result.supported === false ? (result.message || '当前地址暂不支持配送，请更换收货地址') : ''
            state.slots = state.deliverySupported ? result.items.filter(slot => slot.available) : []; state.slotId = state.slots[0]?.id || 0
          }
        } catch (error) {
          if (active()) {
            if ([401, 'SESSION_CHANGED'].includes(error.code)) throw error
            state.deliverySupported = Number(error.code) === 40914 ? false : null
            state.deliveryMessage = state.deliverySupported === false ? error.message : '配送状态暂时无法确认，请刷新后重试。'
          }
        }
      }
    })
  }
  function toggle(id) {
    sync(); if (state.busy) return
    invalidateQuote(); state.selected = state.selected.includes(String(id)) ? state.selected.filter(value => !same(value, id)) : [...state.selected, String(id)]
  }
  function quantity(id, value) {
    sync(); if (state.busy) return
    const item = state.menu?.items.find(item => same(item.sku.sku_id, id))
    if (!item || !Number.isInteger(value) || value < 1 || value > Number(item.sku.available_quantity)) return
    invalidateQuote(); state.quantities = { ...state.quantities, [String(id)]: value }
  }
  async function prepare() {
    return run(async active => {
      guard()
      state.pending = api.pendingOrder()
      if (state.pending) throw new Error('上次下单结果尚未确认，请先重试并确认原订单。')
      if (!state.address) throw new Error('请选择配送地址，再核对订单金额。')
      if (state.deliverySupported !== true) throw new Error(state.deliveryMessage || '请先确认配送状态。')
      // Entering the page is read-only. Only an explicit checkout synchronizes its own meal cart lines.
      let basket = await api.addMeal(state.menu)
      if (!active()) return null
      basket = await api.cart()
      if (!active()) return null
      for (const item of state.menu.items) {
        let line = basket.items.find(line => ownsLine(line) && same(line.sku_id, item.sku.sku_id))
        if (!line) throw new Error('本餐购物车来源已变化，请重新确认。')
        const desired = state.quantities[String(item.sku.sku_id)] ?? item.quantity
        if (line.quantity !== desired) {
          basket = await api.quantity(line, desired)
          if (!active()) return null
          line = basket.items.find(value => same(value.cart_item_id, line.cart_item_id))
        }
        const selected = state.selected.some(id => same(id, item.sku.sku_id))
        if (line.selected !== selected) { basket = await api.select(line, selected); if (!active()) return null }
      }
      state.cart = basket.items
      if (!state.address) throw new Error('请选择配送地址，再核对订单金额。')
      const result = await api.quote(basket.items.filter(ownsLine), state.address.id, state.slotId, state.menu)
      if (active()) { state.quote = result; state.orderSn = ''; return result }
      return null
    }, true)
  }
  async function submit() {
    return run(async active => {
      guard()
      state.pending = api.pendingOrder()
      if (state.pending) throw new Error('上次下单结果尚未确认，请先确认原订单。')
      if (!state.quote?.checkout_token || !Number.isFinite(Date.parse(state.quote.expires_at)) || Date.parse(state.quote.expires_at) <= Date.now()) { invalidateQuote(); throw new Error('报价已失效，请重新核对价格和配送地址。') }
      try {
        const result = await api.createOrder(state.quote.checkout_token)
        if (active()) { state.orderSn = result.order_sn; state.quote = null; return result }
        return null
      } finally { if (active()) state.pending = api.pendingOrder() }
    }, true)
  }
  async function recover() {
    return run(async active => {
      try {
        const result = state.orderSn ? { order_sn: state.orderSn } : await api.retryOrder()
        if (active()) { state.orderSn = result.order_sn; state.quote = null; return result }
        return null
      } finally { if (active()) state.pending = api.pendingOrder() }
    }, true)
  }
  return { load, prepare, submit, recover, toggle, quantity, membersChanged, invalidateQuote, sync, reset, dispose() { disposed = true; reset() } }
}
