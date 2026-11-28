<script setup>
defineOptions({ options: { virtualHost: true } })
import { ref, computed, onUnmounted } from 'vue'
import { journalMealLabels, coarsePortions, createJournalDraft, syncJournalDraft, journalDraftMeal } from '../../../services/diet-journal-presentation.js'
import {mealTime} from '../../../services/meal-record-entry.js'
import MealItemPortionFields from '../../../components/MealItemPortionFields.vue'
import { previewMealPhoto } from '../../../services/health-upload.js'
import { storageContext } from '../../../services/storage.js'

const props = defineProps({ record: { type: Object, required: true }, busy: Boolean, pending: Object, error: String, modelDraft:Object, navigation:Object })
const emit = defineEmits(['close', 'save', 'withdraw', 'retry', 'select', 'record', 'reload'])
const localDraft=ref(createJournalDraft(props.record))
const draft=computed(()=>props.modelDraft||localDraft.value)
const recordOptions=computed(()=>[...(props.navigation?.records||[]).map(r=>({id:r.id,label:mealTime(r.snapshot.meal.eaten_at)+' · '+r.snapshot.meal.items.filter(i=>!i.excluded).map(i=>i.name).join('、')})),{id:'new',label:'补记一条'}])
function change(field,value){if(props.navigation)emit('select',{[field]:value});else draft.value[field==='day'?'date':field]=value}
const localError = ref(''), photoBusy = ref(false), keyboardHeight = ref(0)
const mealTypes = Object.keys(journalMealLabels), mealNames = Object.values(journalMealLabels)
const locked = computed(() => props.busy || !!props.pending)
const formLocked=computed(()=>locked.value||!!props.navigation&&!props.modelDraft)
const quote = computed(() => (props.record.original_quotes || []).join('\n'))
let alive = true
onUnmounted(() => { alive = false })

function syncText() {
  syncJournalDraft(draft.value)
  localError.value = ''
}
function save() {
  if (props.pending) { emit('retry'); return }
  try {
    syncText()
    emit('save', journalDraftMeal(props.record, draft.value))
  } catch (error) { localError.value = error.message }
}
async function photo() {
  if (photoBusy.value) return
  const scope = storageContext()
  photoBusy.value = true
  localError.value = ''
  try {
    const urls = []
    for (const source of props.record.snapshot.meal.photos || []) {
      const url = await previewMealPhoto(source.upload_id, source.upload_page_index)
      if (!alive || scope !== storageContext()) return
      urls.push(url)
    }
    if (urls.length) uni.previewImage({ urls, current: urls[0] })
  } catch (error) { if (alive && scope === storageContext()) localError.value = error.message }
  finally { if (alive) photoBusy.value = false }
}
function keyboard(event) { keyboardHeight.value = Number(event.detail?.height) || 0 }
</script>

<template>
  <view class="diet-edit-mask">
    <view class="diet-edit-backdrop" @tap="!busy && emit('close')" @touchmove.stop.prevent />
    <view class="diet-edit-panel" :style="{ bottom: keyboardHeight + 'px', height: keyboardHeight ? 'calc(100vh - ' + keyboardHeight + 'px - 16px)' : '86vh' }" @tap.stop role="dialog" aria-modal="true" aria-label="修改饮食记录">
      <view class="diet-edit-grip" />
      <view class="diet-edit-heading"><text>编辑饮食记录</text><button aria-label="关闭修改" :disabled="busy" @tap.stop="emit('close')">×</button></view>
      <scroll-view scroll-y class="diet-edit-body" :show-scrollbar="false" :bounces="false">
        <view class="diet-edit-content">
        <view v-if="navigation?.members?.length>1" class="diet-editor-select"><text class="diet-field-label">成员</text><picker :range="navigation.members.map(m=>m.display_name||'成员')" :value="Math.max(0,navigation.members.findIndex(m=>m.id===navigation.memberId))" :disabled="locked" @change="change('memberId',navigation.members[Number($event.detail.value)].id)"><view class="diet-field-value"><text class="disclosure-label">{{navigation.members.find(m=>m.id===navigation.memberId)?.display_name}}</text><view class="diet-field-arrow disclosure-chevron" aria-hidden="true"/></view></picker></view>
        <view class="diet-edit-fields">
          <view><text class="diet-field-label">日期</text><picker mode="date" :value="draft.date" :disabled="locked" @change="change('day',$event.detail.value)"><view class="diet-field-value"><text>{{ draft.date }}</text></view></picker></view>
          <view><text class="diet-field-label">餐次</text><picker :range="mealNames" :value="mealTypes.indexOf(draft.mealType)" :disabled="locked" @change="change('mealType',mealTypes[Number($event.detail.value)])"><view class="diet-field-value"><text>{{ journalMealLabels[draft.mealType] }}</text><view class="diet-field-arrow disclosure-chevron" aria-hidden="true"/></view></picker></view>
        </view>
        <view v-if="navigation?.records?.length" class="diet-editor-select"><text class="diet-field-label">本餐记录</text><picker :range="recordOptions.map(r=>r.label)" :value="Math.max(0,recordOptions.findIndex(r=>r.id===(record.id||'new')))" :disabled="locked" @change="emit('record',recordOptions[Number($event.detail.value)].id)"><view class="diet-field-value"><text class="disclosure-label">{{recordOptions.find(r=>r.id===(record.id||'new'))?.label}}</text><view class="diet-field-arrow disclosure-chevron" aria-hidden="true"/></view></picker></view>
        <text v-if="navigation&&!record.id" class="diet-field-label">本餐尚未保存这条记录，可填写后补记。</text>
        <text class="diet-field-label">吃了什么</text>
        <textarea v-model="draft.foodText" class="diet-food-input" :disabled="formLocked" :fixed="true" :adjust-position="false" maxlength="4000" placeholder="每行一种食物，例如：牛肉面一碗" @input="syncText" @keyboardheightchange="keyboard" @blur="keyboardHeight=0" />
        <view v-for="row in draft.rows" :key="row.key" class="diet-food-portion">
          <text class="diet-food-name">{{ row.text }}</text>
          <MealItemPortionFields :portion="row.portion" :grams="row.grams" :disabled="formLocked" @update:portion="row.portion=$event" @update:grams="row.grams=$event" @keyboard="keyboard"/>
        </view>
        <view v-if="quote" class="diet-original"><text>当时你说</text><text>{{ quote }}</text></view>
        <button v-if="record.snapshot.meal.photos?.length" class="diet-original-photo" :disabled="photoBusy" @tap.stop="photo">{{ photoBusy ? '正在读取原照片…' : '查看原照片' }}</button>
        <button v-if="error&&!pending" class="diet-original-photo" :disabled="busy" @tap.stop="emit('reload')">重新读取当前记录</button>
        <text v-if="localError || error" class="diet-edit-error" role="alert">{{ localError || error }}</text>
        <text v-if="pending" class="diet-edit-error">上次操作结果待核对，请重试原请求。</text>
        </view>
      </scroll-view>
      <view class="diet-edit-actions"><button v-if="record.id" class="diet-delete" :disabled="locked" @tap.stop="emit('withdraw')">删除这条</button><button class="diet-save" :disabled="busy||formLocked&&!pending" @tap.stop="save">{{ busy ? '正在保存…' : pending ? '重试原请求' : record.id ? '保存修改' : '保存记录' }}</button></view>
    </view>
  </view>
</template>

<style scoped>
@import "../../../styles/disclosure-chevron.css";
.diet-editor-select{margin-bottom:16px}.diet-editor-select .diet-field-value{justify-content:flex-start;overflow:hidden;padding-right:32px}.diet-editor-select .disclosure-label{flex:1;text-align:left}

.diet-edit-mask{position:fixed;inset:0;z-index:100}.diet-edit-backdrop{position:absolute;inset:0;background:rgba(57,45,70,.22);backdrop-filter:blur(2px)}.diet-edit-panel{position:absolute;left:0;right:0;display:flex;flex-direction:column;min-height:0;overflow:hidden;box-sizing:border-box;border-radius:28px 28px 0 0;background:#fff;color:#51465f;font-weight:400}.diet-edit-grip{width:32px;height:4px;flex:none;border-radius:4px;background:#e5ddec;margin:10px auto 12px}.diet-edit-heading{position:relative;display:flex;align-items:center;justify-content:center;min-height:57px;padding:0 54px 13px;flex:none;font-size:20px;line-height:1.4;font-weight:500;text-align:center}.diet-edit-heading button{position:absolute;right:10px;top:0;display:flex;align-items:center;justify-content:center;width:44px;height:44px;min-height:44px;padding:0;margin:0;font-size:27px;line-height:1;background:transparent;color:#ac96ba;border:0}.diet-edit-body{flex:1;min-height:0;height:0;width:100%;overflow:hidden}.diet-edit-content{padding:0 22px 20px;box-sizing:border-box}.diet-edit-fields{display:flex;gap:14px;margin:7px 0 20px}.diet-edit-fields>view{flex:1;min-width:0}.diet-field-label{display:block;font-size:14px;font-weight:400;line-height:1.5;color:#776a84;margin-bottom:9px}.diet-field-value{position:relative;display:flex;justify-content:center;align-items:center;height:44px;padding:0 24px;box-sizing:border-box;background:#fbf8fd;border:1px solid #e9e0f0;border-radius:11px;font-size:16px;font-weight:400;line-height:1.5;text-align:center;white-space:nowrap}.diet-edit-fields>view:first-child .diet-field-value{padding-left:10px;padding-right:10px}.diet-field-arrow{position:absolute;right:12px;top:50%;transform:translateY(-50%)}.diet-food-input{width:100%;height:104px;box-sizing:border-box;padding:12px 13px;background:#fdfbff;border:1px solid #e1d2ec;border-radius:12px;font-size:16px;font-weight:400;line-height:1.65;color:#51465f}.diet-food-portion{padding:15px 0;border-bottom:1px solid #f0eaf4}.diet-food-name{display:block;font-size:14px;font-weight:400;line-height:1.6;color:#62566d;overflow-wrap:anywhere}.diet-original{padding:13px;margin:18px 0 12px;border-radius:12px;background:#f7f3fa;font-size:14px;font-weight:400;line-height:1.65;color:#776a84;white-space:pre-wrap;overflow-wrap:anywhere}.diet-original>text{display:block}.diet-original>text:first-child{font-size:12px;color:#776a84;margin-bottom:5px}.diet-original-photo{display:flex;align-items:center;justify-content:center;width:100%;min-height:44px;margin:12px 0;padding:10px;line-height:1.5;text-align:center;background:#f7f2fb;border-radius:11px;color:#79528e;font-size:14px;font-weight:400}.diet-edit-error{display:block;font-size:12px;line-height:1.7;color:#a95057;margin:12px 0}.diet-edit-actions{position:relative;display:flex;flex:none;gap:12px;padding:15px 22px calc(env(safe-area-inset-bottom) + 18px);box-sizing:border-box;border-top:1px solid #f0eaf4;background:#fff}.diet-edit-actions button{height:46px;min-height:46px;padding:0;margin:0;border-radius:13px;font-size:15px;font-weight:400;line-height:1.5;text-align:center;display:flex;align-items:center;justify-content:center;box-sizing:border-box}.diet-delete{flex:1;border:1px solid #e7dbee;color:#79528e;background:#fff}.diet-save{flex:2;background:#9677ad;color:#fff;font-weight:500}.diet-edit-panel button:after{border:0}.diet-edit-panel button[disabled]{opacity:.45}/* #ifdef H5 */
.diet-edit-panel{max-width:480px;margin:0 auto}
/* #endif */
</style>
