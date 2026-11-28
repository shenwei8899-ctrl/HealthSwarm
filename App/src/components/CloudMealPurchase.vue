<script setup>
import {referenceIngredientLabel,referenceGapDetail} from '../utils/meal-presentation.js'
import FoodImageSlot from './FoodImageSlot.vue'
import PurchaseCheckoutSheet from './PurchaseCheckoutSheet.vue'
import ExclusivePurchaseConfirmation from './ExclusivePurchaseConfirmation.vue'
import MealPurchasePanel from './MealPurchasePanel.vue'
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { openAddressPicker } from '../services/address-navigation.js'
import { onShow, onHide } from '@dcloudio/uni-app'
import CommerceAccess from './CommerceAccess.vue'
import { commerce } from '../services/commerce.js'
import { useMealCommercePage } from '../services/meal-commerce-page.js'
import { commerceMealView, nonnegativeInteger, productAmountCents, selectedSubtotalCents, validMealDate, PLAN_DELIVERY_TIMES, deliverySlotTime } from '../services/meal-commerce-state.js'
import { request } from '../services/request.js'
import { getSession } from '../services/session.js'
import { scopedStorage, storageContext } from '../services/storage.js'
import { exclusiveDeliveryPreview } from '../services/exclusive-delivery-preview.js'

// 微信原生宿主节点会截断插槽内的 flex 和百分比高度。
defineOptions({options:{virtualHost:true}})
const props = defineProps({ meal: Object, route: Object, embedded: Boolean, reference: Object, exclusive: Object, exclusivePage:Boolean, selection:Object, managed: Boolean, unified: Boolean, visible:{type:Boolean,default:true} })
const emit=defineEmits(['checkout','ordered','scroll','back'])
const preview = ref(null), publication = ref(null), selected = ref([]), draftQuantities = ref({})
const preferredTime = ref(PLAN_DELIVERY_TIMES[0])
const writing=ref(false)
const submitting=ref(false), quoteWaiting=ref(false)
let quoteTimer=null
let refreshRequested=false
const busy = ref(false), error = ref(''), checkoutOpen = ref(false), loginOpen = ref(false)
let alive = true, initialized = false, ownerScope = storageContext()
let directRevision = 0
const direct = computed(() => Boolean(props.exclusive || props.unified && props.selection))
const page = useMealCommercePage(() => ({
  enabled: Boolean(publication.value), meal: props.route.meal, date: props.route.date,
  packageSn: publication.value?.package_sn, packageVersion: publication.value?.package_version,
  members: props.meal.members || [],
  direct: direct.value, exclusive: Boolean(props.exclusive), loadMenu: loadSelectedMenu,
  preferredTime: props.exclusivePage ? preferredTime.value : undefined,
  initialChoices: () => {
    const saved = scopedStorage.getStorageSync(selectionKey())
    return saved?.known ? { selected: saved.selected || [], quantities: saved.quantities || {} } : null
  },
}))
const state = page.state
const selectable = item => Boolean(item) && (!(props.reference && !state.ready) || item.saleStatus === 'available' && item.availableQuantity !== 0)
const purchaseReady = computed(() => Boolean(preview.value?.available || preview.value?.confirmation_pending))
const purchaseGaps = computed(() => (props.selection ? preview.value?.gaps || [] : props.reference?.gaps || preview.value?.gaps || []).map(gap => ({
  ...gap, label: gap.ingredient_label || referenceIngredientLabel(props.reference?.ingredientLabels, gap.ingredient), detail: referenceGapDetail(gap),
})))
const referenceProducts = computed(() => (props.reference?.items || []).flatMap(item => Array.isArray(item.skus)&&item.skus.length
  ? item.skus.map(sku=>({id:String(sku.sku_id),productId:String(item.product_id),name:item.product_name,packLabel:sku.sku_name||'规格待核对',quantity:draftQuantities.value[String(sku.sku_id)]??1,imageUrl:sku.image_url||item.image_url||'',needLabel:'参考用量未核算',priceCents:nonnegativeInteger(sku.price_cent),availableQuantity:nonnegativeInteger(sku.available_quantity),saleStatus:sku.sale_status,ingredientRefs:item.ingredient_refs||[]}))
  : item.sku_id!=null?[{id:String(item.sku_id),productId:item.product_id!=null?String(item.product_id):null,name:item.product_name,packLabel:item.sku_name||'规格待核对',quantity:draftQuantities.value[String(item.sku_id)]??item.quantity,imageUrl:item.image_url||'',needLabel:'参考用量未核算',priceCents:nonnegativeInteger(item.price_cent),availableQuantity:nonnegativeInteger(item.available_quantity),saleStatus:item.sale_status??'available',ingredientRefs:item.ingredient_refs||[]}]:[]))
const products = computed(() => props.reference && !state.ready ? (preview.value?referenceProducts.value:[]) : state.ready ? page.plan.value.products : commerceMealView({
  items: (preview.value?.items || []).filter(item => item.sku?.sku_id),
  ingredient_requirements: preview.value?.ingredient_requirements || [],
  available: preview.value?.available,
}).products.map(item=>({...item,quantity:draftQuantities.value[item.id]??item.quantity})))
const productSpecSelection = computed(() => Boolean(props.reference?.items?.some(item => item?.product_id != null && Array.isArray(item.skus)) && preview.value && !state.ready))
const picked = computed(() => state.ready ? state.selected : selected.value)
const deliveryPreview = computed(() => props.exclusivePage ? exclusiveDeliveryPreview(preview.value?.delivery_suggestions||props.exclusive?.initialPurchase?.delivery_suggestions,products.value,picked.value,state.firstMealDate,preferredTime.value) : [])
const total = computed(() => selectedSubtotalCents(products.value,picked.value))
const totalKnown=computed(()=>!busy.value&&!state.busy&&!error.value&&!state.error&&purchaseReady.value&&products.value.length>0&&!(props.reference?.needsMatching&&!state.ready)&&total.value!==null)
const money = cents => (Number(cents || 0) / 100).toFixed(2)
const active = scope => alive && scope === storageContext()
function failure(e,scope){
  if(!alive||ownerScope!==scope)return
  if(scope!==storageContext()||[401,403,404,409,410].includes(Number(e.code))||e.code==='SESSION_CHANGED'){
    preview.value=null;publication.value=null;selected.value=[];draftQuantities.value={};checkoutOpen.value=false;loginOpen.value=false;initialized=false;page.reset()
  }
  error.value=e.message;busy.value=false
}
const scopePath=()=>'/api/family/'+encodeURIComponent(props.selection.familyId)+'/daily-meal-plans/'+props.selection.date+'/meals/'+props.selection.mealType+'/purchase'
const scopeQuery=()=>'?version='+props.selection.version+(props.selection.dishKeys||[]).map(key=>'&dish_keys='+encodeURIComponent(key)).join('')
const path = () => '/api/family/' + encodeURIComponent(getSession().householdId) + '/daily-arrangements/' + props.route.date + (props.route.meal === 'daily' ? '' : '/meals/' + props.route.meal) + '/purchase'
const version = () => ({ arrangement_id: props.route.arrangement, version: Number(props.route.version), ...(props.route.daily_plan_version!=null?{daily_plan_version:Number(props.route.daily_plan_version)}:{}), ...(props.route.meal === 'daily' ? { meals: props.route.meals } : {}) })
const selectionKey = () => (props.selection?'saved:'+props.selection.version+':'+(props.selection.dishKeys||[]).join(',')+':':'')+'meal-purchase-selection:' + props.route.arrangement + ':' + props.route.meal + ':' + (props.route.meals || []).join(',')
function rememberSelection() { scopedStorage.setStorageSync(selectionKey(), { known: products.value.map(item => item.id), selected: [...picked.value], quantities: {...draftQuantities.value,...(state.ready?state.quantities:{})}, firstMealDate:state.firstMealDate, preferredTime:preferredTime.value, version: props.route.version, dailyPlanVersion: props.route.daily_plan_version }) }
function receipt(data) {
  if(props.selection){if(data.version!==props.selection.version||!Array.isArray(data.purchase?.items))throw new Error('餐单采购已变化，请重新读取。');return data.purchase}
  if (data.arrangement_id !== props.route.arrangement || data.version !== Number(props.route.version)) throw new Error('本餐已更新，请返回今日安排重新读取。')
  if (!data.purchase || !Array.isArray(data.purchase.items)) throw new Error('本餐采购内容不完整，请重新读取。')
  return data.purchase
}
const returnKey = () => 'meal-checkout-address-return:' + (props.selection
  ? ['selection',props.selection.familyId,props.selection.date,props.selection.mealType,props.selection.version,[...(props.selection.dishKeys||[])].sort().join(',')]
  : [props.route.arrangement, props.route.version, props.route.date, props.route.meal, (props.route.meals || []).join(',')]).join(':')
function chooseAddress() {
  if (direct.value ? submitting.value || !state.addressReady : busy.value || state.busy) return
  const key = returnKey(), scope = storageContext()
  page.invalidateQuote()
  scopedStorage.setStorageSync(key, { at: Date.now(), scope })
  openAddressPicker({ selectedId: state.address?.id, onSelected: id => { state.preferredAddressId = id; page.invalidateQuote() }, onCancel: () => { if (active(scope)) scopedStorage.setStorageSync(key, null) } })
}
async function loadSelectedMenu() {
  if (props.exclusive) {
    if (publication.value && preview.value?.available && !purchaseExpired()) return {...preview.value,dishes:[]}
    const scope = storageContext(), revision = directRevision
    const source = {path:props.exclusive.path, scopeHash:props.exclusive.scopeHash}
    const {data} = await request({path:source.path,method:'POST',data:{scope_hash:source.scopeHash},timeout:30000})
    if (!active(scope) || revision !== directRevision || !props.visible || props.exclusive.path !== source.path || props.exclusive.scopeHash !== source.scopeHash) throw new Error('采购选择已变化，请重新打开。')
    if (data.scope_hash !== source.scopeHash || !data.package?.package_sn || !Number.isSafeInteger(data.package.package_version) || !Array.isArray(data.items)) throw new Error('计划或商品已变化，请返回重新打开购买。')
    const purchase = {...data,...data.package,items:data.items,dishes:[]}
    preview.value = purchase; publication.value = purchase
    return purchase
  }
  if (publication.value && preview.value?.available && !purchaseExpired()) return {...preview.value,dishes:[]}
  const scope = storageContext(), revision = directRevision
  const selectedScope = {...props.selection,dishKeys:[...(props.selection.dishKeys||[])]}
  const selectedPath = scopePath()
  const {data} = await request({path:selectedPath,method:'POST',data:{version:selectedScope.version,dish_keys:selectedScope.dishKeys},timeout:30000})
  if (!active(scope) || revision !== directRevision || !props.visible) throw new Error('采购选择已变化，请重新打开。')
  const purchase = receipt(data)
  preview.value = purchase; publication.value = purchase
  // Publication already returns current authoritative SKUs. Reading the package again adds no UI data.
  return {...purchase,available:purchase.available===true,items:purchase.items||[],dishes:[]}
}
function purchaseExpired() {
  const expiry = Date.parse(state.menu?.expires_at || publication.value?.expires_at || '')
  return state.sourceExpired || Number.isFinite(expiry) && expiry <= Date.now()
}
function clearExpiredPurchase() {
  const choices = { selected: [...picked.value], ids: products.value.map(item => item.id) }
  draftQuantities.value = {...draftQuantities.value, ...state.quantities}
  selected.value = [...picked.value]
  rememberSelection()
  publication.value = null
  state.ready = false
  state.sourceExpired = false
  page.invalidateQuote()
  return choices
}
async function loadSelectedPurchase(retryExpired = true) {
  if (!props.visible || props.exclusive && state.loading) return
  if (submitting.value) { refreshRequested=true; return }
  state.pending = commerce.pendingOrder() || state.pending
  if (state.pending || state.orderSn) { state.checkoutError='上次下单结果尚未确认，请先确认原订单。'; error.value=state.checkoutError; return }
  refreshRequested=false
  const revision = ++directRevision, scope = storageContext()
  if(ownerScope!==scope){ownerScope=scope;page.reset();preview.value=null;publication.value=null;preferredTime.value=PLAN_DELIVERY_TIMES[0]}
  const renewing = purchaseExpired(), previousIds = products.value.map(item => item.id)
  if (renewing) clearExpiredPurchase()
  page.invalidateQuote();error.value=''
  try {
    await commerce.connect()
    if (!active(scope) || revision!==directRevision || !props.visible) return
    loginOpen.value=false
    await page.load()
    if (!active(scope) || revision!==directRevision || !props.visible) return
    if(!state.ready&&state.error){preview.value=null;publication.value=null;return}
    if (renewing && (previousIds.length !== products.value.length || products.value.some(item => !previousIds.includes(item.id)))) {
      error.value = '商品范围已变化，请核对食材列表后重新结算。'
      return
    }
    await prepareQuote(false)
    if (state.sourceExpired && retryExpired && !state.pending && !state.orderSn) {
      return loadSelectedPurchase(false)
    }
    if(!state.ready&&state.checkoutError){preview.value=null;publication.value=null}
  } catch (e) { if(active(scope)&&revision===directRevision){loginOpen.value=!commerce.session()?.token;failure(e,scope)} }
}
async function resumeCheckout(scope) {
  if (!active(scope)) return
  const key = returnKey(), pending = scopedStorage.getStorageSync(key)
  if (!pending) return
  scopedStorage.setStorageSync(key, null)
  if (!preview.value?.available || error.value || pending.scope !== scope || !Number.isFinite(pending.at) || Date.now() - pending.at > 15 * 60 * 1000 || pending.at > Date.now()) return
  await checkout()
}
async function verifyReference() {
  if(props.exclusive){const {data}=await request({path:props.exclusive.path});if(data.scope_hash!==props.exclusive.scopeHash)throw new Error('计划或商品已变化，请返回重新打开购买。');return}
  const ref=props.reference
  if(props.selection)return // Publication, quotation and order each validate the source server-side.
  if(!ref || ref.dailyPlanVersion==null)return
  const scope=storageContext()
  const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-meal-plans/'+props.route.date})
  if(!active(scope))throw new Error('账号或家庭已变化，请重新读取。')
  if(data.date!==props.route.date || data.version!==ref.dailyPlanVersion || !data.purchase_options?.some(o=>o.kind==='reference'&&o.id===ref.previewId&&ref.mealTypes.length>0&&new Set(ref.mealTypes).size===ref.mealTypes.length&&ref.mealTypes.every(t=>o.meal_types.includes(t))))throw new Error('参考餐单已更新，请关闭详情后重新核对。')
}
async function refresh(initial = false) {
  if (ownerScope !== storageContext()) {
    ownerScope = storageContext(); preview.value = null; publication.value = null; selected.value = []; draftQuantities.value={}
    initialized = false; checkoutOpen.value = false; loginOpen.value = false; busy.value = false; preferredTime.value=PLAN_DELIVERY_TIMES[0]; page.reset()
  }
  if (busy.value) return
  const scope = storageContext(); busy.value = true; error.value = ''; page.invalidateQuote()
  try {
    // The parent has just read this receipt; checkout still revalidates it server-side.
    const initialReceipt = initial === true && props.exclusive?.initialPurchase
    const seeded = initialReceipt && initialReceipt.scope_hash === props.exclusive.scopeHash
    const { data } = seeded ? {data:null} : props.selection ? await request({path:scopePath()+scopeQuery()}) : props.reference ? (await verifyReference(), {data:null}) : await request({ path: path() + '?arrangement_id=' + encodeURIComponent(props.route.arrangement) + '&version=' + Number(props.route.version) + (props.route.daily_plan_version!=null?'&daily_plan_version='+Number(props.route.daily_plan_version):'') + (props.route.meals || []).map(meal => '&meals=' + meal).join('') })
    if (!active(scope)) return
    preview.value = props.reference ? {available:referenceProducts.value.length>0||props.reference.needsMatching,items:[]} : receipt(data)
    if (!initialized) {
      const saved = scopedStorage.getStorageSync(selectionKey()); if(saved?.version===props.route.version&&saved?.dailyPlanVersion===props.route.daily_plan_version){draftQuantities.value=saved.quantities||{};if(props.exclusive&&validMealDate(saved.firstMealDate))state.firstMealDate=saved.firstMealDate;if(props.exclusivePage&&PLAN_DELIVERY_TIMES.includes(saved.preferredTime))preferredTime.value=saved.preferredTime}
      const defaults=props.reference?products.value.filter((item,index,all)=>item.saleStatus==='available'&&item.availableQuantity!==0&&all.findIndex(other=>(other.productId||other.id)===(item.productId||item.id)&&other.saleStatus==='available'&&other.availableQuantity!==0)===index):products.value
      selected.value = saved?.known ? products.value.filter(item => selectable(item)&&saved.known.includes(item.id)&&saved.selected.includes(item.id)).map(item => item.id) : defaults.map(item=>item.id)
      initialized = true
    }
    selected.value = selected.value.filter(id => selectable(products.value.find(item => item.id === id)))
    if (publication.value && commerce.session()?.token) {
      const slotId = state.slotId, addressId = state.address?.id
      await page.load()
      if (!props.exclusivePage && active(scope) && addressId === state.address?.id && state.slots.some(slot => slot.id === slotId)) state.slotId = slotId
    }
  } catch (e) { if(active(scope))preview.value=null;failure(e,scope) }
  finally { if (active(scope)) busy.value = false }
  if (!props.unified) await resumeCheckout(scope)
}
function toggle(id) { if (busy.value || state.busy) return; const target=products.value.find(item=>item.id===id);if(!target||!picked.value.includes(id)&&!selectable(target))return;if (state.ready) page.toggle(id); else {selected.value = selected.value.includes(id) ? selected.value.filter(value => value !== id) : [...selected.value.filter(value=>!target.productId||products.value.find(item=>item.id===value)?.productId!==target.productId), id]}; rememberSelection();scheduleQuote() }
async function prepareQuote(retryExpired = true) {
  if ((props.unified || direct.value) && (!props.visible || !state.ready || !state.address || !state.selected.length || !state.slots.some(slot=>String(slot.id)===String(state.slotId)) || state.pending || state.orderSn)) return
  await page.prepare(direct.value?{requireSlot:true}:props.unified?{reuseCart:true,requireSlot:true}:undefined)
  if (retryExpired && state.sourceExpired && !busy.value && !state.pending && !state.orderSn) {
    if (direct.value) return loadSelectedPurchase()
    return checkout()
  }
}
function scheduleQuote() {
  if (!props.unified && !props.exclusivePage) return
  if(props.exclusivePage)state.mealDates=[]
  clearTimeout(quoteTimer); page.invalidateQuote(); quoteWaiting.value=true
  quoteTimer=setTimeout(async()=>{
    quoteTimer=null
    try { if (alive && props.visible) await prepareQuote() }
    finally { quoteWaiting.value=false }
  },250)
}
async function refreshUnified() {
  if (direct.value) return loadSelectedPurchase()
  if (!props.visible) return
  if (busy.value || state.busy || submitting.value) { refreshRequested=true; return }
  refreshRequested=false
  clearTimeout(quoteTimer);quoteWaiting.value=false
  await refresh()
  if (!alive || !props.visible || error.value || !purchaseReady.value) return
  if (productSpecSelection.value) return
  await checkout()
}
const unifiedReady=computed(()=>state.ready&&state.menu?.available===true)
const canSubmit=computed(()=>productSpecSelection.value?picked.value.length>0&&!busy.value&&!state.busy&&!error.value:unifiedReady.value&&picked.value.length>0&&state.address&&state.deliverySupported===true&&state.slots.some(slot=>String(slot.id)===String(state.slotId))&&state.quote?.checkout_token&&['goods_amount_cent','shipping_fee_cent','payable_amount_cent'].every(key=>Number.isSafeInteger(state.quote[key])&&state.quote[key]>=0)&&!quoteWaiting.value&&!state.pricing&&!state.loading&&!busy.value&&!state.busy&&!error.value&&!state.error&&!state.checkoutError)
async function checkout() {
  if (direct.value) {
    if (props.exclusive) { checkoutOpen.value=true; rememberSelection() }
    return loadSelectedPurchase()
  }
  if (busy.value || state.busy) return
  const scope = storageContext(); busy.value = true; writing.value=true; error.value = ''; checkoutOpen.value = !props.unified
  try {
    try { await commerce.connect() }
    catch (e) { if (active(scope)) loginOpen.value = true; throw e }
    if (!active(scope)) return
    loginOpen.value = false
    state.pending = commerce.pendingOrder() || state.pending
    if (state.pending || state.orderSn) throw new Error('上次下单结果尚未确认，请先确认原订单。')
    for (let attempt = 0; attempt < 2; attempt++) {
      const renewing = purchaseExpired()
      const previousChoices = renewing ? clearExpiredPurchase() : null
      await checkoutAttempt(scope, previousChoices)
      if (!active(scope) || !state.sourceExpired || state.pending || state.orderSn) return
    }
  } catch (e) { failure(e,scope) }
  finally { writing.value=false; if (active(scope)) busy.value = false }
}
async function checkoutAttempt(scope, previousChoices) {
    await verifyReference()
    if (publication.value && state.ready) {
      await prepareQuote(false)
      return
    }
    const previous = previousChoices?.selected || [...picked.value], previousIds = previousChoices?.ids || products.value.map(item => item.id)
    const ref=props.reference
    const productChoices=productSpecSelection.value?products.value.filter(item=>item.productId&&previous.includes(item.id)).map(item=>({product_id:item.productId,sku_id:item.id,quantity:item.quantity})):[]
    const { data } = await request(props.selection?{path:scopePath(),method:'POST',data:{version:props.selection.version,dish_keys:props.selection.dishKeys},timeout:30000}:ref ? {path:ref.dailyPlanVersion!=null?'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-meal-plans/'+props.route.date+'/purchase':'/api/health/v1/reference-meal-plans/'+encodeURIComponent(ref.previewId)+'/purchase',method:'POST',data:ref.dailyPlanVersion!=null?{preview_id:ref.previewId,version:ref.dailyPlanVersion,meal_types:ref.mealTypes,...(productChoices.length?{product_choices:productChoices}:{})}:{...(productChoices.length?{product_choices:productChoices}:{})},timeout:30000} : { path: path(), method: 'POST', data: version(), timeout: 30000 })
    if (!active(scope)) return
    if(props.reference && (data.preview_id!==props.reference.previewId||!data.package?.package_sn))throw new Error('采购来源无法核对，请重试。')
    publication.value = props.reference ? data.package : receipt(data)
    const previousAddress = state.address?.id, previousSlot = state.slotId
    await page.load()
    if (!active(scope) || !state.ready || state.error) return
    if (String(state.address?.id) === String(previousAddress) && state.slots.some(slot => String(slot.id) === String(previousSlot))) state.slotId = previousSlot
    if(props.reference && state.menu?.scope!=='daily_reference')throw new Error('参考采购来源已变化，请重新核对。')
    await verifyReference()
    if (previousChoices && (previousIds.length !== page.plan.value.products.length || page.plan.value.products.some(item => !previousIds.includes(item.id)))) {
      state.selected = page.plan.value.products.filter(item => previous.includes(item.id)).map(item => item.id)
      throw new Error('商品范围已变化，请核对食材列表后重新结算。')
    }
    state.selected = page.plan.value.products.filter(item => previous.includes(item.id) || !previousIds.includes(item.id)).map(item => item.id)
    const quantityChanges=page.plan.value.products.filter(item=>draftQuantities.value[item.id]!=null)
    if(quantityChanges.some(item=>draftQuantities.value[item.id]>item.availableQuantity))throw new Error('库存已有变化，请返回食材列表重新确认包装数量。')
    for(const item of quantityChanges)page.quantity(item.id,draftQuantities.value[item.id])
    rememberSelection()
    await prepareQuote(false)
}
async function submit() {
  uni.showToast({ title: '尚未接入微信支付', icon: 'none' })
}
async function recover() {
  if(writing.value)return
  writing.value=true;submitting.value=true
  try{await page.recover();if(alive&&state.orderSn)uni.showToast({ title: '尚未接入微信支付', icon: 'none' })}
  finally{writing.value=false;submitting.value=false}
}

function changeQuantity(item,delta){if(busy.value||state.busy||!selectable(item))return;const value=item.quantity+delta;if(value<1||Number.isFinite(item.availableQuantity)&&value>item.availableQuantity)return;if(state.ready)page.quantity(item.id,value);draftQuantities.value={...draftQuantities.value,[item.id]:value};rememberSelection();scheduleQuote()}
async function selectSlot(id){
  if(props.exclusivePage){
    if(submitting.value||state.pending||state.orderSn||preferredTime.value===id||!PLAN_DELIVERY_TIMES.includes(id))return
    preferredTime.value=id;state.slotId=state.slots.find(s=>deliverySlotTime(s)===id)?.id||0
    page.invalidateQuote();rememberSelection()
    if(!state.loading)await prepareQuote()
    return
  }
  if(props.exclusive)id=state.slots.find(s=>deliverySlotTime(s)===id)?.id||id
  if(busy.value||state.busy||String(state.slotId)===String(id))return;state.slotId=id;page.invalidateQuote();if(props.unified)scheduleQuote();else await checkout()
}
async function selectMealDate(date) {
  if (submitting.value || state.pending || state.orderSn || !validMealDate(date) || date === state.firstMealDate) return
  clearTimeout(quoteTimer);quoteWaiting.value=false
  state.firstMealDate=date
  page.invalidateQuote()
  rememberSelection()
  if(state.loading)return
  await prepareQuote()
}

watch(checkoutOpen,value=>{emit('checkout',value);if(!value&&props.exclusive){directRevision++;page.suspend()}})
defineExpose({refresh:()=>props.unified?refreshUnified():refresh(),closeCheckout:()=>{if(!writing.value)checkoutOpen.value=false},isBusy:computed(()=>props.unified?submitting.value:writing.value)})
watch(()=>props.visible,(visible,previous)=>{if(!props.unified)return;if(!visible){clearTimeout(quoteTimer);quoteWaiting.value=false;if(direct.value){directRevision++;page.reset();preview.value=null;publication.value=null}else page.invalidateQuote()}else if(previous===false)void refreshUnified()})
watch(()=>JSON.stringify([props.selection,props.exclusive?.path,props.exclusive?.scopeHash]),()=>{if(direct.value){directRevision++;page.reset();preview.value=null;publication.value=null;if(props.visible&&(!props.exclusive||checkoutOpen.value))void(props.exclusive?loadSelectedPurchase():refreshUnified())}},{flush:'sync'})
watch(()=>[busy.value,state.busy,submitting.value],()=>{if(props.unified&&props.visible&&refreshRequested&&!busy.value&&!state.busy&&!submitting.value)void refreshUnified()})
onMounted(async()=>{
  if(props.exclusivePage&&props.exclusive){
    await refresh(true)
    if(alive&&props.visible&&!error.value&&props.exclusive.initialPurchase?.available!==false)await checkout()
  }else return props.unified?refreshUnified():refresh(true)
})
// Exclusive procurement is reloaded by its parent page on every show.
onShow(()=>{if(props.exclusivePage&&!initialized)return;if(props.exclusive&&(checkoutOpen.value||props.exclusivePage)){void loadSelectedPurchase();return}if(!props.embedded&&!props.exclusive)void(props.unified?refreshUnified():refresh())})
onHide(()=>{if(props.unified||props.exclusive){clearTimeout(quoteTimer);quoteWaiting.value=false;if(direct.value){directRevision++;page.suspend()}else page.invalidateQuote()}})
onUnmounted(() => { alive = false; clearTimeout(quoteTimer); page.dispose() })

</script>

<template>
   <view class="meal-purchase" :class="{'is-embedded':embedded,'is-exclusive':!!exclusive}">
  <MealPurchasePanel v-if="unified" :gaps="purchaseGaps" :products="products" :picked="picked" :address="state.address" :slots="state.slots" :slot-id="state.slotId" :quote="state.quote" :busy="busy||state.busy||submitting" :pricing="quoteWaiting||state.pricing" :independent="direct" :products-loading="state.productsLoading" :address-ready="state.addressReady" :address-loading="state.addressLoading" :slots-loading="state.slotsLoading" :address-error="state.addressError" :ready="unifiedReady" :choices-ready="productSpecSelection" :pending="!!(state.pending||state.orderSn)" :error="error||state.error||state.addressError||state.checkoutError||state.deliveryMessage" :access-required="loginOpen" :can-submit="!!canSubmit" @address="chooseAddress" @slot="selectSlot" @toggle="toggle" @quantity="changeQuantity" @confirm="submit" @recover="recover" @retry="refreshUnified" @scroll="emit('scroll',$event)"><template #access><CommerceAccess entry @ready="refreshUnified"/></template></MealPurchasePanel>
  <template v-else>
  <template v-if="!exclusivePage">
  <scroll-view v-show="!embedded||!checkoutOpen" :scroll-y="embedded" :show-scrollbar="false" class="purchase-scroll">
  <view v-if="!exclusive" class="section-head"><text class="section-title">{{route.meal==='daily'&&route.meals?.length>1?'所选餐次食材汇总':'本餐所需食材'}}</text><text>家中已有可取消</text></view>
  <text v-if="!exclusive&&reference?.needsMatching&&!state.ready" class="safe-note">将按本餐核对商品；进入结算后可调整包装数量。</text><text v-if="reference&&!exclusive" class="safe-note">参考餐单用量未核算，请核对实际需要；未匹配的食材需自行准备。</text><text v-if="busy||state.busy" class="safe-note">正在核对商品与配送…</text>
  <view v-if="error||state.error" class="card status" role="alert"><text>{{error||state.error}}</text><button class="secondary-button" :disabled="busy||state.busy" @click="refresh">重新核对本餐食材</button></view>
  <text v-if="preview&&!preview.available" class="inline-error">{{preview.message||'当前食材暂不可采购，请重新核对。'}}</text><view v-if="!exclusive&&reference?.gaps?.length" class="purchase-gaps"><text>这些食材不进入购物车</text><text v-for="(gap,i) in reference.gaps" :key="i">{{referenceIngredientLabel(reference?.ingredientLabels,gap.ingredient)}}：{{['no_match','needs_confirmation'].includes(gap.reason)?'自行购买 · 暂无价格；':''}}{{referenceGapDetail(gap)}}</text></view>
  <view class="products"><view v-for="item in products" :key="item.id" class="product"><button class="product-select" :disabled="busy||state.busy||!selectable(item)" :aria-pressed="picked.includes(item.id)" :aria-label="(picked.includes(item.id)?'取消选择':'选择')+item.name" @click="toggle(item.id)"><view class="check" :class="{selected:picked.includes(item.id)}">{{picked.includes(item.id)?'✓':''}}</view></button><view class="product-image"><FoodImageSlot :src="item.imageUrl" :label="item.name" :width="52" :height="60" :radius="15"/></view><view class="product-copy"><text class="product-name">{{item.name}}</text><text v-if="!exclusive">{{item.needLabel}}</text><text>{{item.packLabel}}</text><view class="quantity-control"><button :aria-label="'减少'+item.name+'数量'" :disabled="busy||state.busy||!selectable(item)||item.quantity<=1" @click="changeQuantity(item,-1)">−</button><text>{{item.quantity}} 包</text><button :aria-label="'增加'+item.name+'数量'" :disabled="busy||state.busy||!selectable(item)||(Number.isFinite(item.availableQuantity)&&item.quantity>=item.availableQuantity)" @click="changeQuantity(item,1)">＋</button></view><text v-if="!selectable(item)" class="stock-alert">暂不可选</text><text v-else-if="Number.isFinite(item.availableQuantity)&&item.availableQuantity<item.quantity" class="stock-alert">库存不足</text></view><text class="product-price">{{productAmountCents(item)!==null?'¥'+money(productAmountCents(item)):'待核价'}}</text></view></view>
  </scroll-view>
  <view v-show="!embedded||!checkoutOpen" class="meal-bottom-bar"><view class="selection-summary"><text>{{exclusive?'商品小计':route.meal==='daily'?(route.meals||[]).map(m=>({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}[m])).join('、')+' · 商品小计':'商品小计 · '+picked.length+' 项'}}</text><text class="amount">{{totalKnown?'¥'+money(total):'价格待核对'}}</text></view><button class="checkout-button" :disabled="busy||state.busy||!purchaseReady||(!picked.length&&!reference?.needsMatching)||!!error" @click="checkout">{{preview?.confirmation_pending?'确认上次采购结果':'去结算'}}<text v-if="!preview?.confirmation_pending">→</text></button></view>
  </template>
  <ExclusivePurchaseConfirmation v-if="exclusive" :open="exclusivePage||checkoutOpen" :picked="picked" :subtotal="total" :editing-busy="busy||submitting||state.loading||state.busy||!!(state.pending||state.orderSn)" :gaps="exclusivePage?(reference?.gaps||[]):[]" :notice="exclusivePage?exclusive.initialPurchase?.notice:undefined" :quantity-warning="exclusivePage&&exclusive.initialPurchase?.items?.some(item=>item.quantity_confirmed===false)" :tier-name="exclusive.initialPurchase?.tier_name" :member-count="meal.members?.length" :address="state.address" :slot-id="exclusivePage?preferredTime:deliverySlotTime(state.slots.find(s=>String(s.id)===String(state.slotId))||{})" :dates="state.mealDates" :first-meal-date="state.firstMealDate" :products="exclusivePage?products:products.filter(p=>picked.includes(p.id))" :quote="state.quote" :preview-batches="deliveryPreview" :busy="busy||submitting||state.loading||state.pricing||quoteWaiting" :address-busy="submitting||!state.addressReady" :error="error||state.error||state.addressError||state.checkoutError||state.deliveryMessage" :pending="!!(state.pending||state.orderSn)" :access-required="loginOpen" @close="exclusivePage?emit('back'):checkoutOpen=false" @toggle="toggle" @quantity="changeQuantity" @address="chooseAddress" @slot="selectSlot" @date="selectMealDate" @retry="checkout" @recover="recover"><template #access><CommerceAccess entry @ready="checkout"/></template></ExclusivePurchaseConfirmation>
  <PurchaseCheckoutSheet v-else :embedded="embedded" :open="checkoutOpen" :title="route.meal==='daily'&&route.meals?.length>1?'确认采购订单':'确认本餐订单'" :address="state.address" :slots="state.slots" :slot-id="state.slotId" :products="products.filter(p=>picked.includes(p.id))" :quote="state.quote" :busy="direct?(submitting||state.loading||state.pricing):busy||state.busy" :address-busy="direct?(submitting||!state.addressReady):undefined" :slots-busy="direct?(submitting||state.slotsLoading):undefined" :error="error||state.error||state.addressError||state.checkoutError||state.deliveryMessage" :pending="!!(state.pending||state.orderSn)" :access-required="loginOpen" @close="checkoutOpen=false" @address="chooseAddress" @slot="selectSlot" @confirm="submit" @recover="recover" @quote="checkout"><template #access><CommerceAccess entry @ready="checkout"/></template></PurchaseCheckoutSheet>
  </template>
 </view>
</template>
<style scoped>
.section-head{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:10rpx;margin:30rpx 0 14rpx}.section-title{font-size:29rpx;font-weight:500}.section-head>text:last-child{font-size:23rpx;color:var(--ui-muted)}.products{border:1rpx solid #e9edf3;border-radius:26rpx;background:#fff;padding:0 18rpx}.product{display:flex;align-items:center;gap:16rpx;padding:18rpx 0;border-bottom:1rpx solid #eff2f6;width:100%;text-align:left;box-sizing:border-box}.product:last-child{border:0}.check{display:flex;align-items:center;justify-content:center;width:34rpx;height:34rpx;border:2rpx solid #bcc4d3;border-radius:8rpx;flex-shrink:0;font-size:26rpx;color:#fff}.check.selected{background:var(--ui-accent);border-color:var(--ui-accent)}.product-image{width:108rpx;height:116rpx;border-radius:18rpx}.product-copy{flex:1;min-width:0}.product-copy text{display:block;color:var(--ui-muted);font-size:24rpx;line-height:1.6}.product-copy .product-name{color:#252a34;font-size:28rpx;font-weight:500;line-height:1.45;margin-bottom:6rpx;overflow-wrap:anywhere}.product-price{align-self:flex-end;padding-bottom:4rpx;flex-shrink:0;font-size:27rpx;font-weight:500;white-space:nowrap;font-variant-numeric:tabular-nums}.product-copy .stock-alert{color:#b83532}.meal-bottom-bar{position:fixed;z-index:10;left:0;right:0;bottom:0;padding:18rpx 32rpx calc(env(safe-area-inset-bottom) + 18rpx);display:flex;align-items:center;justify-content:space-between;gap:20rpx;background:#fff;border-top:1rpx solid #eceff4;box-sizing:border-box}.selection-summary{display:flex;align-items:baseline;justify-content:space-between;gap:16rpx;flex:1;min-width:0;font-size:24rpx}.selection-summary>text:first-child{line-height:1.5;max-width:50%;color:#465064}.amount{font-size:40rpx;font-weight:500;font-variant-numeric:tabular-nums;color:#20242c;white-space:nowrap}.checkout-button{display:flex;align-items:center;justify-content:center;gap:16rpx;background:var(--ui-accent);border-radius:999rpx;color:#fff;min-height:92rpx;padding:18rpx 24rpx;font-size:28rpx;line-height:1.5;max-width:46%;box-sizing:border-box}.status{padding:24rpx;font-size:27rpx;line-height:1.6}.status button{margin-top:16rpx}button[disabled]{opacity:.45}
@media(max-width:350px){.product{gap:12rpx}.product-image{width:86rpx;height:100rpx}.product-price{font-size:26rpx}.selection-summary{flex-direction:column;gap:0}.selection-summary>text:first-child{max-width:100%}.amount{font-size:38rpx}}
/* #ifdef H5 */
.meal-bottom-bar{max-width:480px;margin:0 auto}
/* #endif */
</style>

<style scoped>
@media(max-width:350px){.product-copy text,.section-head>text:last-child,.selection-summary{font-size:12px}.section-title,.product-copy .product-name{font-size:14px}}
</style>

<style scoped>
.is-embedded.meal-purchase{height:100%;display:flex;flex-direction:column;min-height:0;overflow:hidden}.is-embedded .purchase-scroll{height:0;flex:1;min-height:0;box-sizing:border-box;padding:0 20px 20px}.is-embedded .meal-bottom-bar{position:relative;inset:auto;flex-shrink:0;width:100%;padding:14px 20px calc(env(safe-area-inset-bottom) + 14px);margin:0;max-width:none}.is-embedded .selection-summary .amount{font-size:22px}.purchase-scroll{height:auto}
</style>

<style scoped>
.meal-purchase{color:var(--ui-text)}.products{border:1px solid #fff;border-radius:24px;background:var(--ui-bubble);box-shadow:inset 0 1px 1px #fff,0 4px 18px rgba(62,47,82,.035);padding:0 12px}.product{gap:9px;background:transparent}.product-select{display:flex;justify-content:center;align-items:center;width:30px;min-width:30px;min-height:44px;margin:0;padding:0;background:transparent}.product-select:after{border:0}.product-image{width:52px;height:60px;border-radius:15px}.product-price{font-size:14px;align-self:flex-start;margin-top:8px}.product-copy .product-name{font-size:15px;font-weight:500}.quantity-control{display:flex;align-items:center;gap:9px;margin-top:7px}.quantity-control button{display:flex;align-items:center;justify-content:center;margin:0;padding:0;min-width:32px;width:32px;min-height:36px;border-radius:99px;background:#f1ecf7;font-size:15px;color:var(--ui-accent)}.quantity-control button:after{border:0}.quantity-control>text{font-size:12px;color:var(--ui-text)}.section-head{margin-top:18px}.safe-note{display:block;margin:8px 0;font-size:12px;line-height:1.7;color:var(--ui-muted)}.meal-bottom-bar{background:linear-gradient(150deg,#fff,#faf8fd);border-top:1px solid white}.checkout-button{border-radius:99px;background:var(--ui-accent);box-shadow:none}.is-embedded .purchase-scroll{padding:0 18px 20px}.product-copy text{font-size:12px}.selection-summary>text:first-child{font-size:11px}.is-embedded .selection-summary .amount{font-size:21px}
</style>

<style scoped>.purchase-gaps{padding:14px 16px;margin:12px 0;border:1px solid #eee4d6;border-radius:20px;background:#fbf8f1;color:#9a805c;font-size:12px;line-height:1.8}.purchase-gaps text{display:block}.purchase-gaps text:first-child{font-weight:500;margin-bottom:4px}</style>

<style scoped>
.is-exclusive .quantity-control button{background:#eaf2ff;color:#537bb8}.is-exclusive .product-copy .product-name{color:#424b60}.is-exclusive .safe-note{text-align:left}.is-exclusive .meal-bottom-bar{background:#ffffffef}.is-exclusive .checkout-button{background:#6386bb}
</style>

<style scoped>
.product{gap:10px;padding:16px 0;align-items:flex-start}.product-select{flex:0 0 24px;min-width:24px;width:24px;margin-top:8px}.product-image{display:block;flex:0 0 52px;width:52px;min-width:52px;height:60px;overflow:hidden;border-radius:15px;margin-top:2px}.product-copy{flex:1;min-width:0;width:0}.product-copy .product-name{white-space:normal;overflow-wrap:anywhere;word-break:break-all;line-height:1.5;margin-bottom:4px}.product-price{flex:0 0 auto;max-width:90px;font-size:13px;line-height:1.6;margin-top:2px;padding:0}.quantity-control{gap:6px;flex-wrap:nowrap;margin-top:8px}.quantity-control button{flex:0 0 28px;min-width:28px;width:28px;min-height:30px}.quantity-control>text{flex:none;white-space:nowrap}
</style>

<style scoped>
.is-exclusive .meal-bottom-bar{gap:16px;padding:12px 18px calc(env(safe-area-inset-bottom) + 12px);align-items:center}.is-exclusive .selection-summary{flex-direction:row;align-items:center;justify-content:space-between;gap:10px;line-height:1.5}.is-exclusive .selection-summary>text:first-child{max-width:none;flex:none;white-space:nowrap;font-size:14px;line-height:1.5}.is-exclusive .selection-summary .amount{font-size:14px;font-weight:500;line-height:1.5;color:#424b60}.is-exclusive .checkout-button{flex:none;max-width:none;min-height:42px;padding:10px 16px;gap:6px;font-size:14px;font-weight:500;line-height:1.5;white-space:nowrap}
</style>
