<script setup>
import { computed, ref } from 'vue'
import MealItemPortionFields from './MealItemPortionFields.vue'
import { confirmCapturePortions } from '../services/meal-item-intake.js'
const props=defineProps({people:Array,dishes:Array,busy:Boolean,error:String})
const emit=defineEmits(['close','confirm'])
const draft=ref(JSON.parse(JSON.stringify(props.people))),member=ref(draft.value[0]?.memberId),error=ref(''),keyboardHeight=ref(0)
const current=computed(()=>draft.value.find(p=>p.memberId===member.value))
function keyboard(event){keyboardHeight.value=Number(event.detail?.height)||0}
function toggle(row){if(props.busy)return;row.selected=!row.selected;current.value.noneConfirmed=false;error.value=''}
function none(){if(props.busy)return;current.value.noneConfirmed=true;current.value.rows.forEach(row=>row.selected=false);error.value=''}
function confirm(){if(props.busy)return;try{emit('confirm',confirmCapturePortions(draft.value,props.dishes))}catch(e){error.value=e.message}}
</script>
<template>
 <view class="capture-portion-mask"><view class="capture-portion-backdrop" @tap="!busy&&emit('close')" @touchmove.stop.prevent/>
  <view class="capture-portion-panel" :style="{bottom:keyboardHeight+'px',height:keyboardHeight?'calc(100vh - '+keyboardHeight+'px - 16px)':'86vh'}" @tap.stop role="dialog" aria-modal="true" aria-label="核对吃过的菜和份量">
   <view class="capture-portion-grip"/><view class="capture-portion-heading"><text>核对吃过的菜和份量</text><button :disabled="busy" aria-label="关闭核对" @tap="emit('close')">×</button></view>
   <scroll-view scroll-y class="capture-portion-body" :bounces="false" :show-scrollbar="false"><view v-if="current" class="capture-portion-content">
    <view class="capture-member-row"><view class="capture-member-tabs"><button v-for="p in draft" :key="p.memberId" :class="{active:member===p.memberId}" :disabled="busy" @tap="member=p.memberId">{{p.name}}</button></view><button class="capture-none" :class="{active:current.noneConfirmed}" :disabled="busy" @tap="none">本餐未吃</button></view>
    <text class="capture-portion-help">只勾选吃过的菜，每道菜分别填写。</text><text v-if="current.legacyTotal" class="capture-portion-help">之前记录的合计 {{current.legacyTotal}}g，请分别核对，合计不会自动分配。</text>
    <view v-for="row in current.rows" :key="row.itemId" class="capture-food-row"><button class="capture-food-heading" :disabled="busy" :aria-label="row.name+(row.selected?'，已勾选':'，未勾选')" @tap="toggle(row)"><view class="capture-food-check" :class="{checked:row.selected}">{{row.selected?'✓':''}}</view><text>{{row.name}}</text></button><MealItemPortionFields v-if="row.selected" :portion="row.portion" :grams="row.grams" :disabled="busy" @update:portion="row.portion=$event" @update:grams="row.grams=$event" @keyboard="keyboard"/></view>
    <text v-if="current.noneConfirmed" class="capture-portion-help">该成员本餐不创建摄入记录。</text><text v-if="error||props.error" class="capture-portion-error" role="alert">{{error||props.error}}</text>
   </view></scroll-view>
   <view class="capture-portion-footer"><text>确认后返回记餐页，保存后记入饮食记录。</text><view><button :disabled="busy" class="capture-portion-cancel" @tap="emit('close')">取消</button><button :disabled="busy" class="capture-portion-confirm" @tap="confirm">确认本次核对</button></view></view>
  </view>
 </view>
</template>
<style scoped>
.capture-portion-mask{position:fixed;inset:0;z-index:100}.capture-portion-backdrop{position:absolute;inset:0;background:rgba(57,45,70,.22);backdrop-filter:blur(2px)}.capture-portion-panel{position:absolute;left:0;right:0;display:flex;flex-direction:column;min-height:0;overflow:hidden;box-sizing:border-box;border-radius:28px 28px 0 0;background:#fff;color:#51465f;font-weight:400}.capture-portion-grip{width:32px;height:4px;flex:none;border-radius:4px;background:#e5ddec;margin:10px auto 12px}.capture-portion-heading{position:relative;display:flex;align-items:center;justify-content:center;min-height:57px;padding:0 46px 13px;flex:none;font-size:19px;line-height:1.4;font-weight:500;text-align:center}.capture-portion-heading button{position:absolute;right:10px;top:0;display:flex;align-items:center;justify-content:center;width:44px;height:44px;padding:0;margin:0;font-size:27px;line-height:1;background:transparent;color:#ac96ba}.capture-portion-body{flex:1;min-height:0;height:0;width:100%;overflow:hidden}.capture-portion-content{padding:0 20px 18px;box-sizing:border-box}.capture-member-row{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin:8px 0 14px}.capture-member-tabs{display:flex;gap:8px;flex-wrap:wrap;min-width:0;flex:1}.capture-member-tabs button,.capture-none{display:flex;align-items:center;justify-content:center;min-height:44px;max-width:100%;margin:0;padding:8px 12px;border:1px solid #e9e0f0;border-radius:12px;background:#fbf8fd;font-size:14px;line-height:1.5;font-weight:400;color:#776a84;overflow-wrap:anywhere}.capture-none{flex:none;white-space:nowrap}.capture-member-row .active{background:#eee4f6;border-color:#c7afd8;color:#79528e;font-weight:500}.capture-portion-help{display:block;margin:0 0 12px;font-size:13px;line-height:1.6;color:#776a84}.capture-food-row{padding:14px 0 18px;border-bottom:1px solid #eee7f3}.capture-food-heading{display:flex;align-items:center;gap:10px;width:100%;min-height:40px;margin:0;padding:0;background:transparent;text-align:left;font-size:16px;font-weight:400;line-height:1.6;color:#51465f;overflow-wrap:anywhere}.capture-food-heading>text{flex:1;min-width:0}.capture-food-check{flex:none;display:flex;align-items:center;justify-content:center;width:20px;height:20px;border:1px solid #d9c9e5;border-radius:5px;color:white;font-size:15px;line-height:1}.capture-food-check.checked{background:#a184b6;border-color:#a184b6}.capture-portion-error{display:block;margin:12px 0;color:#a95057;font-size:14px;line-height:1.6}.capture-portion-footer{flex:none;padding:12px 20px calc(env(safe-area-inset-bottom) + 16px);border-top:1px solid #f0eaf4;background:#fff}.capture-portion-footer>text{display:block;text-align:center;font-size:12px;line-height:1.5;color:#776a84;margin-bottom:12px}.capture-portion-footer>view{display:flex;gap:12px}.capture-portion-footer button{display:flex;align-items:center;justify-content:center;height:46px;min-height:46px;padding:0;margin:0;border-radius:13px;font-size:15px;line-height:1.5;font-weight:400}.capture-portion-cancel{flex:1;border:1px solid #e7dbee;color:#79528e;background:#fff}.capture-portion-confirm{flex:1.5;color:#fff;background:#9677ad;font-weight:500!important}.capture-portion-panel button:after{border:0}.capture-portion-panel button[disabled]{opacity:.45}
/* #ifdef H5 */
.capture-portion-panel{max-width:480px;margin:0 auto}
/* #endif */
@media(max-width:350px){.capture-portion-heading{font-size:17px}}
</style>
