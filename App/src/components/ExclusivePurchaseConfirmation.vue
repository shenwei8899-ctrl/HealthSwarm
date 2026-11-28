<script setup>
import { computed, ref, watch } from 'vue'
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
import FoodImageSlot from './FoodImageSlot.vue'
import { mealDateStart, PLAN_DELIVERY_TIMES } from '../services/meal-commerce-state.js'
import { deliveryBatchKey, deliveryBatchItems } from '../services/exclusive-delivery-preview.js'

const props = defineProps({
  open:Boolean, tierName:String, memberCount:Number, address:Object, slotId:[String,Number],
  dates:{type:Array,default:()=>[]}, firstMealDate:String,
  products:{type:Array,default:()=>[]}, quote:Object, busy:Boolean, addressBusy:Boolean,
  error:String, pending:Boolean, accessRequired:Boolean, editingBusy:Boolean, subtotal:Number,
  picked:{type:Array,default:()=>[]}, gaps:{type:Array,default:()=>[]}, notice:String, quantityWarning:Boolean,
  previewBatches:{type:Array,default:()=>[]},
})
const emit=defineEmits(['close','address','slot','date','retry','recover','toggle','quantity'])
const ingredientsOpen=ref(false), feesOpen=ref(false), preparationOpen=ref(false)
const activeBatchKey=ref(''), batchItemsOpen=ref(false)
const money=value=>Number.isSafeInteger(value)&&value>=0?'¥'+(value/100).toFixed(2):'待确认'
const dateLabel=value=>value?Number(value.slice(5,7))+'月'+Number(value.slice(8,10))+'日':''
const shortDate=value=>value?value.slice(5).replace('-','/'):''
const weekday=value=>value?'周'+['日','一','二','三','四','五','六'][new Date(value+'T00:00:00Z').getUTCDay()]:''
const range=computed(()=>props.quote?.exclusive_delivery?dateLabel(props.quote.exclusive_delivery.first_meal_date)+'—'+dateLabel(props.quote.exclusive_delivery.last_meal_date):'')
const isPreview=computed(()=>!props.quote&&props.previewBatches.length>0)
const batches=computed(()=>props.quote?props.quote.delivery_batches||[]:props.previewBatches)
const activeBatch=computed(()=>batches.value.find(batch=>deliveryBatchKey(batch)===activeBatchKey.value)||batches.value[0])
const activeItems=computed(()=>deliveryBatchItems(activeBatch.value,props.products))
const visibleItems=computed(()=>batchItemsOpen.value?activeItems.value:activeItems.value.slice(0,3))
const lines=computed(()=>props.products.map(product=>({sku_id:product.id,product,quantity:product.quantity,
  selected:props.picked.includes(String(product.id)),name:product.name,spec:product.packLabel,image:product.imageUrl,
  line_amount_cent:Number.isSafeInteger(product.priceCents)&&product.priceCents>=0?product.priceCents*product.quantity:null})))
const available=line=>line.product?.availableQuantity!==0&&line.product?.saleStatus!=='unavailable'
watch(()=>props.open,()=>{ingredientsOpen.value=false;feesOpen.value=false;preparationOpen.value=false;activeBatchKey.value=batches.value.length?deliveryBatchKey(batches.value[0]):'';batchItemsOpen.value=false})
watch(batches,value=>{
  if(!value.some(batch=>deliveryBatchKey(batch)===activeBatchKey.value))activeBatchKey.value=value.length?deliveryBatchKey(value[0]):''
},{immediate:true})
watch(activeBatchKey,()=>{batchItemsOpen.value=false})
function selectBatch(batch){activeBatchKey.value=deliveryBatchKey(batch)}
function selectDate(event){if(!props.pending)emit('date',event.detail.value)}
</script>

<template>
  <view v-if="open" class="exclusive-confirmation" role="dialog" aria-modal="true" aria-label="确认采购">
    <view class="confirmation-nav"><AppNavBar title="确认采购"><template #left><button class="back-button" aria-label="返回计划" @click="$emit('close')">‹</button></template></AppNavBar></view>
    <scroll-view scroll-y class="confirmation-scroll" :show-scrollbar="false">
      <view class="confirmation-content">
        <view class="plan-heading">
          <view class="plan-identity"><view class="plan-symbol"><AppIcon name="record" :size="34"/></view><text>AI 专属计划</text></view>
          <view class="plan-title-row"><text class="tier-name">{{tierName||'AI 专属计划'}}</text><text class="plan-period">7天 · 每日三餐</text></view>
          <text class="plan-meta">7天家庭计划<text v-if="memberCount"> · {{memberCount}}人用餐</text><text v-if="range" class="period"> · {{range}}</text></text>
        </view>
        <view v-if="accessRequired" class="confirmation-card"><slot name="access"/></view>
        <button v-if="products.length||busy" class="confirmation-card address-card" :disabled="addressBusy" aria-label="选择收货地址" @click="$emit('address')">
          <view class="address-icon"><AppIcon name="location" :size="38"/></view>
          <view class="address-copy"><text class="eyebrow">收货地址</text><template v-if="address"><text class="recipient">{{address.name||address.receiver}}<text class="phone">{{address.phone||address.mobile}}</text></text><text class="address-detail">{{address.region}} {{address.detail}}</text></template><text v-else class="recipient">{{addressBusy?'正在读取地址…':'选择收货地址'}}</text></view><text class="chevron">›</text>
        </button>
        <view v-if="products.length||busy" class="confirmation-card settings-card">
          <picker mode="date" :start="dates[0]||mealDateStart()" :end="dates[dates.length-1]" :value="firstMealDate||dates[0]||mealDateStart()" :disabled="pending" aria-label="选择开始用餐日期" @change="selectDate">
            <view class="date-control" :data-date="firstMealDate"><AppIcon name="calendar" :size="36"/><text class="section-label">开始用餐日期</text><text class="date-value">{{firstMealDate?dateLabel(firstMealDate)+' '+weekday(firstMealDate):'选择日期'}}</text><text class="chevron">›</text></view>
          </picker>
          <view class="slot-heading"><AppIcon name="history" :size="34"/><text class="section-label">配送时段</text></view>
          <view class="slot-options"><button v-for="time in PLAN_DELIVERY_TIMES" :key="time" class="slot-option" :class="{selected:time===slotId}" :disabled="pending" :aria-pressed="time===slotId" @click="$emit('slot',time)">{{time}}</button></view>
        </view>
        <view v-if="error" class="confirmation-card error-card" role="alert"><text>{{error}}</text><view class="error-actions"><button :disabled="busy" @click="$emit('retry')">重新核对</button><button @click="ingredientsOpen=true">核对食材数量</button></view></view>

        <view class="delivery-card">
          <view class="section-heading delivery-heading"><text class="section-label">本周配送</text><text class="count-label">{{batches.length?'共'+batches.length+'趟'+(isPreview?' · 预览':''):'待确认'}}</text></view>
          <scroll-view v-if="batches.length" scroll-x class="trip-tabs" :scroll-into-view="'trip-tab-'+activeBatchKey" :show-scrollbar="false">
            <view class="trip-tabs-inner" role="tablist" aria-label="本周配送批次"><button v-for="(batch,index) in batches" :id="'trip-tab-'+deliveryBatchKey(batch)" :key="deliveryBatchKey(batch)" class="delivery-tab" :class="{selected:activeBatchKey===deliveryBatchKey(batch)}" role="tab" :aria-label="'查看第'+(index+1)+'趟配送'" :aria-selected="activeBatchKey===deliveryBatchKey(batch)" :aria-controls="'delivery-panel-'+deliveryBatchKey(batch)" @click="selectBatch(batch)"><text>第{{String(index+1).padStart(2,'0')}}趟</text><text class="tab-date">{{shortDate(batch.delivery_date)}}</text></button></view>
          </scroll-view>
          <view v-if="activeBatch" :id="'delivery-panel-'+deliveryBatchKey(activeBatch)" class="confirmation-card delivery-trip" role="tabpanel" :aria-labelledby="'trip-tab-'+deliveryBatchKey(activeBatch)">
            <view class="trip-heading"><view class="trip-date"><view class="trip-dot"/><text>{{dateLabel(activeBatch.delivery_date)}} <text class="weekday">{{weekday(activeBatch.delivery_date)}}</text></text></view><text class="trip-time">{{activeBatch.slot_name}}</text></view>
            <view v-if="activeBatch.contains_weekly_staples" class="trip-tag"><AppIcon name="record" :size="28"/><text>耐放食材首趟送齐</text></view>
            <view class="trip-items"><view v-for="item in visibleItems" :key="item.key" class="trip-item">
              <FoodImageSlot :src="item.image" :label="item.name" :fallback-icon="true" :lazy-load="true" :width="54" :height="54" :radius="12"/>
              <view class="trip-item-copy"><text class="trip-item-name">{{item.name}}</text><text class="help-text">{{item.spec}} · {{item.uses}}</text><text class="trip-quantity">{{isPreview?'包装数量待分配':item.quantity!==null?'×'+item.quantity+'包':'数量待核对'}}</text></view>
            </view></view>
            <button v-if="activeItems.length>3" class="detail-toggle" :aria-expanded="batchItemsOpen" @click="batchItemsOpen=!batchItemsOpen">{{batchItemsOpen?'收起本次食材':'查看本次全部 '+activeItems.length+' 种食材'}}<text>{{batchItemsOpen?'⌃':'⌄'}}</text></button>
          </view>
          <view v-else class="confirmation-card delivery-empty"><text class="empty-schedule">{{busy?'正在读取配送建议…':!products.length?'暂无需要配送的商品。':!picked.length?'请在食材清单中选择需要购买的食材。':!firstMealDate?'选择开始用餐日期后，即可预览每趟配送食材。':'配送建议暂未读取到，请重新核对。'}}</text><button v-if="firstMealDate&&picked.length" class="detail-toggle" :disabled="busy" @click="$emit('retry')">重新核对配送建议</button></view>
        </view>

        <view class="confirmation-card review-card">
          <button class="ingredients-heading review-heading" :aria-expanded="ingredientsOpen" @click="ingredientsOpen=!ingredientsOpen"><AppIcon name="grid" :size="34"/><text class="section-label">已选食材</text><text class="count-label">共{{picked.length}}项</text><text class="chevron">{{ingredientsOpen?'⌃':'›'}}</text></button>
          <text v-if="quantityWarning&&!ingredientsOpen" class="help-text compact-warning">包装用量待核对</text>
          <view v-if="ingredientsOpen" class="ingredient-lines">
            <text v-if="notice||quantityWarning" class="help-text quantity-note">{{notice||'包装数量请按家庭实际需要核对，当前数量不代表足够一周。'}}</text>
            <text v-if="!lines.length" class="help-text">暂无可购买食材，可查看下方自行准备清单。</text>
            <view v-for="line in lines" :key="line.sku_id" class="ingredient-line" :class="{'not-selected':!line.selected}">
              <button class="ingredient-select" :aria-label="(line.selected?'取消选择':'选择')+line.name" :aria-pressed="line.selected" :disabled="editingBusy||!line.selected&&!available(line)" @click="$emit('toggle',String(line.sku_id))"><view class="ingredient-check" :class="{checked:line.selected}">{{line.selected?'✓':''}}</view></button>
              <FoodImageSlot :src="line.image" :label="line.name" :fallback-icon="true" :width="42" :height="46" :radius="11"/>
              <view class="ingredient-copy"><text>{{line.name}}</text><text class="help-text">{{line.spec}}</text><view class="ingredient-quantity"><button :aria-label="'减少'+line.name+'数量'" :disabled="editingBusy||!line.selected||line.quantity<=1" @click="$emit('quantity',line.product,-1)">−</button><text>{{line.quantity}}包</text><button :aria-label="'增加'+line.name+'数量'" :disabled="editingBusy||!line.selected||!available(line)||Number.isFinite(line.product?.availableQuantity)&&line.quantity>=line.product.availableQuantity" @click="$emit('quantity',line.product,1)">＋</button></view><text v-if="!available(line)" class="help-text">暂不可选</text></view><text class="ingredient-amount">{{money(line.line_amount_cent)}}</text>
            </view>
          </view>
          <view class="fee-card"><button class="fees-heading review-heading" :aria-expanded="feesOpen" @click="feesOpen=!feesOpen"><AppIcon name="record" :size="34"/><text class="section-label">费用明细</text><text class="count-label">{{money(quote?.payable_amount_cent)}}</text><text class="chevron">{{feesOpen?'⌃':'›'}}</text></button>
            <view v-if="feesOpen" class="fee-details"><view class="fee-row"><text>商品金额</text><text>{{money(quote?.goods_amount_cent??subtotal)}}</text></view><view class="fee-row"><text>整周配送费<text v-if="quote&&batches.length">（{{batches.length}}次）</text></text><text>{{money(quote?.shipping_fee_cent)}}</text></view><view v-if="quote?.discount_amount_cent>0" class="fee-row"><text>优惠</text><text>−{{money(quote.discount_amount_cent)}}</text></view><view class="fee-row fee-total"><text>合计</text><text>{{money(quote?.payable_amount_cent)}}</text></view></view>
          </view>
          <view v-if="gaps.length" class="preparation-card"><button class="preparation-heading review-heading" :aria-expanded="preparationOpen" @click="preparationOpen=!preparationOpen"><AppIcon name="calendar" :size="34"/><text class="section-label">需自行准备</text><text class="count-label">{{gaps.length}}项</text><text class="chevron">{{preparationOpen?'⌃':'›'}}</text></button><view v-if="preparationOpen" class="preparation-items"><text v-for="(gap,index) in gaps" :key="index" class="help-text preparation-item">{{gap.label||gap.ingredient}}：{{gap.detail}}</text></view></view>
        </view>
        <text v-if="batches.length" class="readonly-note">{{isPreview?'配送预览，尚未预约；实际送达及分包数量待核对。':'配送趟次由系统安排，仅支持核对查看。'}}</text>
      </view>
    </scroll-view>
    <view class="confirmation-footer"><view class="footer-total"><text>合计<text v-if="quote" class="includes-delivery">含整周配送费</text></text><text class="footer-amount">{{money(quote?.payable_amount_cent)}}</text></view><button v-if="pending" class="footer-button" :disabled="busy" @click="$emit('recover')">核对上次订单</button><button v-else-if="!products.length" class="footer-button" disabled>暂无可购买食材</button><button v-else-if="!address" class="footer-button" :disabled="addressBusy" @click="$emit('address')">选择收货地址</button><button v-else class="footer-button" disabled>{{busy?'正在核对…':'暂未开放下单'}}</button></view>
  </view>
</template>

<style scoped>
/* #ifdef H5 */
:global(.uni-picker-container){z-index:4000}
/* #endif */
.exclusive-confirmation{position:fixed;inset:0;z-index:3900;display:flex;flex-direction:column;box-sizing:border-box;color:#3c354c;background-color:#e9e3f7;background-image:radial-gradient(ellipse at 100% 95%,#e8d9f4 0%,transparent 52%),linear-gradient(180deg,#d3defb 0%,#e0e4fc 34%,#eae6f7 100%);font-size:14px;line-height:1.5;text-align:left}
.exclusive-confirmation button{margin:0;padding:0;border:0;border-radius:0;background:transparent;color:inherit;font-size:inherit;line-height:inherit;font-weight:400}.exclusive-confirmation button::after{border:0}.exclusive-confirmation button:focus-visible{outline:2px solid #8051bc;outline-offset:2px}
.confirmation-nav{flex:none;padding:0 20px}.back-button{width:44px;height:44px;text-align:left;font-size:32px!important;color:#685c7d!important}.confirmation-scroll{flex:1;min-height:0;height:0;width:100%}.confirmation-content{padding:15px 20px 24px;box-sizing:border-box}
.plan-heading{margin:0 1px 20px}.plan-identity{display:flex;align-items:center;gap:8px;font-size:12px;color:#766789}.plan-symbol{display:flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:8px;color:#fff;background:linear-gradient(145deg,#be97fb,#8651de);box-shadow:inset 1px 1px 1px #ffffff91,0 3px 7px #8356c42a}.plan-title-row{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:10px}.tier-name{min-width:0;overflow-wrap:anywhere;color:#3b324d;font-size:29px;line-height:1.3;font-weight:600}.plan-period{flex:none;padding:6px 9px;border:1px solid #fff;border-radius:20px;background:#ffffff7d;font-size:11px;color:#765d94;white-space:nowrap}.plan-meta{display:block;margin-top:7px;color:#716581;font-size:12px}.period{font-size:11px}
.confirmation-card{padding:15px;margin-bottom:14px;border:1px solid #fff;border-radius:22px;background:#fff;box-sizing:border-box;box-shadow:0 8px 22px #54476e06}.section-label{font-size:16px;font-weight:500}.help-text,.count-label,.eyebrow{display:block;font-size:12px;line-height:1.6;color:#817489}.chevron{flex:none;font-size:23px;color:#a18cb6;line-height:1}.address-card{display:flex!important;align-items:center;gap:12px;width:100%;padding:12px 14px!important;margin-bottom:14px!important;border-radius:22px!important;background:#fff!important;text-align:left}.address-icon{display:flex;align-items:center;justify-content:center;flex:none;width:42px;height:48px;border-radius:14px;background:#f2edfa;color:#9879c1}.address-copy{flex:1;min-width:0}.eyebrow{font-size:10px;line-height:1.2;margin-bottom:2px}.recipient{display:block;font-size:14px;line-height:1.3;overflow-wrap:anywhere}.phone{margin-left:9px;font-size:12px;color:#817489}.address-detail{display:block;margin-top:3px;font-size:11px;line-height:1.4;color:#817489;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.settings-card{padding:0 14px 12px}.date-control{display:flex;align-items:center;gap:8px;min-height:50px;border-bottom:1px solid #eae3f2;color:#9374b8}.date-control>.section-label{flex:1;color:#4c3c5c;font-size:14px}.date-value{font-size:13px;color:#4c3c5c;white-space:nowrap}.slot-heading{display:flex;align-items:center;gap:8px;margin-top:10px;color:#9374b8}.slot-heading>.section-label{color:#4c3c5c;font-size:14px}.slot-options{display:flex;gap:7px;margin-top:9px}.slot-option{display:flex;align-items:center;justify-content:center;flex:1;min-width:0;min-height:40px;padding:7px 3px!important;border:1px solid #ffffffd9!important;border-radius:11px!important;background:#f1edf9!important;color:#7b6d90!important;font-size:12px!important;white-space:nowrap;font-variant-numeric:tabular-nums}.slot-option.selected{border-color:#bb96eb!important;background:#e1d0fa!important;color:#6738a7!important}.date-status{margin-top:8px;font-size:10px}
.delivery-card{margin-top:20px}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:10px}.delivery-heading{margin-bottom:12px}.delivery-heading>.section-label{font-size:18px;font-weight:600}.count-label{white-space:nowrap}.trip-tabs{display:block;width:100%;white-space:nowrap;margin-bottom:12px}.trip-tabs-inner{display:flex;gap:8px;width:100%;padding-bottom:5px}.delivery-tab{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;flex:1 0 calc((100% - 16px)/3);min-width:82px;min-height:58px;padding:7px!important;border:1px solid #ffffffdc!important;border-radius:13px!important;background:#ffffff80!important;color:#7b6d90!important;font-size:15px!important;box-sizing:border-box}.delivery-tab.selected{border-color:#8552ce!important;background:#8552ce!important;color:#fff!important;box-shadow:0 4px 9px #8357c523}.tab-date{font-size:12px}.delivery-trip{overflow:hidden;padding:0 14px;margin-bottom:14px}.trip-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:55px;border-bottom:1px solid #eae3f2}.trip-date{display:flex;align-items:center;gap:7px;min-width:0;font-size:16px;font-weight:500}.trip-dot{flex:none;width:7px;height:7px;border-radius:50%;background:#9865e1}.weekday{font-size:12px;font-weight:400}.trip-time{flex:none;padding:4px 7px;border-radius:9px;background:#f1e9fc;color:#795299;font-size:11px;white-space:nowrap}.trip-tag{display:flex;align-items:center;gap:7px;min-height:32px;margin:9px 0 0;padding:5px 9px;border-radius:10px;background:#f3edfb;color:#8056ad;font-size:12px}.trip-item{display:flex;align-items:center;gap:12px;min-height:85px;padding:11px 0;border-bottom:1px solid #edeaf2}.trip-item:last-child{border-bottom:0}.trip-item-copy{flex:1;min-width:0}.trip-item-name{display:block;font-size:16px;color:#3d354b;overflow-wrap:anywhere}.trip-item .help-text{margin-top:3px;font-size:11px;overflow-wrap:anywhere}.trip-quantity{display:block;margin-top:3px;font-size:11px;color:#9888a4}.trip-item :deep(.food-image-slot),.ingredient-line :deep(.food-image-slot){background:#f1edf7}.trip-item :deep(.fallback-plate),.ingredient-line :deep(.fallback-plate){border-color:#b29acb;box-shadow:inset 0 0 0 6px #f6f1fb;background:#e4d8f2}.detail-toggle{display:flex!important;align-items:center;justify-content:center;gap:8px;min-height:44px;width:calc(100% + 28px);margin:0 -14px!important;padding:10px 12px!important;background:#f3edfb!important;color:#8056ad!important;font-size:13px!important}.empty-schedule{display:block;padding:7px 0;color:#817489;font-size:13px}.delivery-empty .detail-toggle{margin-top:12px!important;margin-bottom:-15px!important;border-radius:0 0 22px 22px}
.review-card{padding:0 14px}.review-heading{display:flex!important;align-items:center;gap:9px;width:100%;min-height:52px;text-align:left}.review-heading>.app-icon{color:#9879c1}.review-heading>.section-label{flex:1;font-size:14px}.review-heading>.count-label{margin-left:auto}.review-heading>.chevron{font-size:20px}.compact-warning{margin:-5px 0 9px 26px;font-size:10px}.fee-card,.preparation-card{border-top:1px solid #eae3f2}.quantity-note{padding:8px 0;font-size:11px}.ingredient-line{display:flex;align-items:center;gap:9px;padding:12px 0;border-top:1px solid #edeaf2;font-size:13px}.ingredient-copy{flex:1;min-width:0}.ingredient-copy>text{display:block;overflow-wrap:anywhere}.ingredient-copy .help-text{font-size:10px}.ingredient-select{display:flex;align-items:center;justify-content:center;flex:none;min-width:23px;min-height:44px}.ingredient-check{width:17px;height:17px;border:1px solid #b9a6ce;border-radius:4px;color:#fff;text-align:center;font-size:12px;line-height:15px}.ingredient-check.checked{background:#8552ce;border-color:#8552ce}.ingredient-quantity{display:flex;align-items:center;gap:8px;margin-top:6px;font-size:12px;color:#8056ad}.ingredient-quantity>button{display:flex;align-items:center;justify-content:center;width:29px;height:29px;border-radius:50%;background:#f1e9fc;color:#8056ad;font-size:19px}.ingredient-amount{flex:none;font-size:12px;font-variant-numeric:tabular-nums}.not-selected{opacity:.6}.fee-details,.preparation-items{padding:0 0 12px}.fee-row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;font-size:13px}.fee-row>text:first-child{color:#817489}.fee-total{margin-top:6px;padding-top:11px;border-top:1px solid #eae3f2}.fee-total>text:last-child{color:#8056ad;font-weight:500}.preparation-item{padding:5px 0}.readonly-note{display:block;margin:0 3px;color:#8b7a9b;font-size:11px;line-height:1.6}
.confirmation-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;flex:none;padding:13px 20px calc(13px + env(safe-area-inset-bottom));border-top:1px solid #ffffffb0;background:#ffffffdf}.footer-total{min-width:0}.footer-total>text{display:block;font-size:12px}.includes-delivery{margin-left:5px;font-size:9px;color:#817489}.footer-total .footer-amount{font-size:24px;font-weight:500;line-height:1.4;color:#7951a9}.footer-button{flex:none;min-height:47px;padding:11px 20px!important;border-radius:16px!important;background:#424b60!important;color:#fff!important;font-size:14px!important;white-space:nowrap}.footer-button[disabled]{background:#7b7c8e!important;color:#f0edf5!important;opacity:.7}.error-card{color:#9b655f;font-size:12px}.error-actions{display:flex;gap:20px;margin-top:9px}.error-actions>button{min-height:36px;color:#8056ad;font-size:12px}.confirmation-card[disabled]{opacity:.7}
@media(max-width:350px){.confirmation-nav{padding-left:16px;padding-right:16px}.confirmation-content{padding-left:16px;padding-right:16px}.tier-name{font-size:27px}.plan-period{padding:5px 7px;font-size:10px}.confirmation-card{padding-left:12px;padding-right:12px}.date-control{gap:6px}.date-control>.section-label{font-size:13px}.date-value{font-size:11px}.slot-options{gap:5px}.slot-option{font-size:11px!important}.trip-date{font-size:14px;gap:5px}.weekday{font-size:11px}.trip-time{font-size:10px;padding:4px 6px}.trip-item{gap:10px}.trip-item-name{font-size:15px}.detail-toggle{width:calc(100% + 24px);margin-left:-12px!important;margin-right:-12px!important}.ingredient-line{gap:7px}.confirmation-footer{padding-left:16px;padding-right:16px}.footer-button{padding-left:15px!important;padding-right:15px!important;font-size:13px!important}.includes-delivery{display:none}}
</style>
