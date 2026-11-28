<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { onShow, onHide, onUnload, onBackPress } from '@dcloudio/uni-app'
import { mealDay } from '../../../services/cloud-meals.js'
import { createJournalPageClient, journalPageState } from '../../../services/diet-journal-page.js'
import { journalMealLabels, journalWeek, quantityText, recordSource } from '../../../services/diet-journal-presentation.js'
import { sortMealRecords } from '../../../services/meal-record-entry.js'
import DietRecordEditSheet from './DietRecordEditSheet.vue'
import AppIcon from '../../../components/AppIcon.vue'
import {journalEditorState,createJournalEditor} from '../journal-editor.js'

const props = defineProps({ detailId: String, memberId: String, initialDate: String })
const state = reactive(journalPageState())
const client = createJournalPageClient({ state })
const editorState=reactive(journalEditorState()),editorPage=reactive(journalPageState())
const editor=createJournalEditor({state:editorState,page:editorPage,client:createJournalPageClient({state:editorPage}),onDenied:error=>{client.hide();state.error=error}})
const editorRecord=computed(()=>editorState.record||{id:'',snapshot:{meal:{eaten_at:(editorState.day||state.day)+'T12:00:00+08:00',meal_type:editorState.mealType,photos:[],items:[]}}})
let initialDetailOpened = false
const validDay = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') && mealDay(value + 'T12:00:00+08:00') === value
if (validDay(props.initialDate)) state.day = props.initialDate
const week = computed(() => journalWeek(state.day))
const month = computed(() => Number(state.day.slice(0, 4)) + '年' + Number(state.day.slice(5, 7)) + '月')
const memberOptions = computed(() => [...state.members.map(member => ({ id: member.id, name: member.is_owner && member.relationship_label === '本人' ? '我' : member.display_name })), { id: 'all', name: '全家' }])
const memberIndex = computed(() => Math.max(0, memberOptions.value.findIndex(member => member.id === state.memberId)))
const groups = computed(() => Object.entries(journalMealLabels).map(([key, label]) => ({
  key, label, records: sortMealRecords(state.records).filter(record => record.snapshot.meal.meal_type === key),
})).filter(group => group.records.length))
const dateLabel = computed(() => Number(state.day.slice(5, 7)) + '月' + Number(state.day.slice(8)) + '日')
const isToday = computed(() => state.day === mealDay(new Date().toISOString()))
const memberName = id => memberOptions.value.find(member => member.id === id)?.name || '成员'

async function load() {
  await client.load(props.memberId || state.memberId)
  if (props.detailId && props.memberId && !initialDetailOpened && !state.error) {
    initialDetailOpened = true
    const record=await client.detail({id:props.detailId,member_id:props.memberId});if(record)await open(record)
  }
}
async function selectDay(day) {
  if (!validDay(day) || state.saving) return
  await client.load(state.memberId, day)
}
async function open(record) {
 const memberId=record?.member_id|| (state.memberId!=='all'?state.memberId:state.members.find(m=>m.is_owner&&m.relationship_label==='本人')?.id||state.members[0]?.id)
 if(!memberId)return
 await editor.open({memberId,day:record?mealDay(record.snapshot.meal.eaten_at):state.day,mealType:record?.snapshot?.meal?.meal_type||groups.value[0]?.key||'breakfast',id:record?.id})
}
function close(){if(!editorPage.saving)editor.clear()}
async function save(){const result=await editor.save();if(result){await client.load(state.memberId,result.day);uni.showToast({title:'已保存',icon:'none'})}}
async function withdraw(){
 if(editorPage.pending||editorPage.saving)return
 const answer=await new Promise(resolve=>uni.showModal({title:'删除这条记录？',content:'仅删除当前这条记录，保留本餐其他记录。',confirmText:'删除',success:resolve,fail:()=>resolve({confirm:false})}))
 if(!answer.confirm)return
 const result=await editor.withdraw();if(result){await client.load(state.memberId,result.day);uni.showToast({title:'已删除记录',icon:'none'})}
}
function chat() { uni.navigateTo({ url: '/pages/chat/index' }) }
function capture(key) {
  uni.navigateTo({ url: '/pages/scan/index?date=' + state.day + (typeof key === 'string' && journalMealLabels[key] ? '&meal=' + key : '') + (state.memberId !== 'all' ? '&memberId=' + encodeURIComponent(state.memberId) : '') })
}
function tableAction(){if(!state.busy&&!state.saving)void open()}
watch(() => props.initialDate, value => { if (validDay(value) && value !== state.day) void selectDay(value) })
onShow(load)
onHide(()=>{editor.clear();client.hide()})
onUnload(()=>{editor.clear();client.hide()})
onBackPress(() => { if (editorState.open) { close(); return true } return false })
</script>

<template>
  <view class="diet-journal">
    <view class="diet-heading"><view><text class="diet-kicker">我的饮食日记</text><text class="diet-title">吃过的，都记得。</text></view><picker :range="memberOptions.map(member=>member.name)" :value="memberIndex" :disabled="state.saving" @change="client.load(memberOptions[Number($event.detail.value)].id)"><view class="diet-member"><text class="disclosure-label">{{ memberOptions[memberIndex]?.name || '我' }}</text><view class="disclosure-chevron" aria-hidden="true"/></view></picker></view>
    <view class="diet-month"><text>{{ month }}</text><picker mode="date" :value="state.day" :disabled="state.saving" @change="selectDay($event.detail.value)"><view class="diet-calendar" aria-label="选择日期"><AppIcon name="calendar" :size="36" /></view></picker></view>
    <view class="diet-week"><button v-for="day in week" :key="day.date" :class="{ selected: state.day===day.date }" :disabled="state.saving" :aria-label="day.date" @click="selectDay(day.date)"><text>{{ day.label }}</text><text>{{ day.number }}</text><view class="diet-day-dot" :class="{ recorded: state.recordedDates.includes(day.date) }" /></button></view>
    <text v-if="state.error && !state.detail" class="diet-error" role="alert">{{ state.error }}<button @click="load">重新读取</button></text>
    <view v-if="state.recoveryError" class="diet-error"><text>{{ state.recoveryError }}</text><button @click="load">重新读取</button></view><view class="diet-paper" :aria-busy="state.busy">
      <view class="diet-table-title"><view><text>{{ isToday ? '今天的饮食' : dateLabel + '的饮食' }}</text><text>{{ state.busy ? '正在读取…' : state.records.length + ' 条记录' }}</text></view><button :disabled="state.busy || state.saving" @click="tableAction"><text>✎</text>编辑</button></view>
      <view class="diet-table-head"><text>餐次</text><text>吃了什么</text></view>
      <view v-for="(group,index) in groups" :key="group.key" class="diet-table-group" :class="{ tinted:index%2===1 }">
        <text class="diet-meal-label">{{ group.label }}</text>
        <view class="diet-records"><button v-for="record in group.records" :key="record.id" class="diet-record" :disabled="state.busy" :aria-label="'查看'+group.label+'记录'" @click="open(record)">
          <text v-if="state.memberId==='all'" class="diet-record-member">{{ memberName(record.member_id) }}</text>
          <view v-for="item in record.snapshot.meal.items.filter(item=>!item.excluded)" :key="item.item_id" class="diet-food-line"><text>{{ item.name }}</text><text v-if="quantityText(item)">{{ quantityText(item) }}</text></view>
          <view class="diet-record-meta"><text>{{ recordSource(record) }}</text></view>
        </button></view>
      </view>
      <view v-if="!groups.length" class="diet-empty">{{ state.busy ? '正在读取饮食记录…' : state.error ? '请重新读取这一天的记录' : '这一天还没有记录' }}</view>
      <view class="diet-table-footer"><text><text class="diet-green-dot">•</text> 已保存的实际饮食</text><text>{{ dateLabel }}</text></view>
    </view>
    <button class="diet-add" @click="capture">＋ 记一餐 / 拍照记餐</button>
    <view class="diet-bottom"><button class="diet-chat" @click="chat"><AppIcon name="chat" :size="34" /><text>回到聊天，随手记一餐</text><text>›</text></button><text>也可以在聊天里补充或更正</text></view>
    <DietRecordEditSheet v-if="editorState.open" :key="editorRecord.id+':'+(editorRecord.source_version||0)" :record="editorRecord" :model-draft="editorState.draft" :navigation="{...editorState,members:editorPage.members}" :busy="editorPage.busy||editorPage.saving" :pending="editorPage.pending" :error="editorPage.error" @select="editor.select" @record="editor.record" @reload="editor.reload" @close="close" @save="save" @withdraw="withdraw" @retry="save" />
  </view>
</template>

<style scoped>
@import "../../../styles/disclosure-chevron.css";
.diet-journal{--diet-ink:#51465f;--diet-muted:#776a84;--diet-accent:#79528e;padding:10px 7px 0;color:var(--diet-ink);font-weight:400}.diet-heading{display:flex;justify-content:space-between;align-items:center;padding:6px 1px 0}.diet-heading>view{min-width:0}.diet-kicker{display:block;font-size:12px;letter-spacing:.2px;color:var(--diet-muted);margin-bottom:8px}.diet-title{font-size:23px;font-weight:500;line-height:1.6;color:#51485c;letter-spacing:.2px}.diet-member{display:flex;align-items:center;justify-content:center;gap:9px;padding:0 12px;min-height:44px;max-width:110px;border:1px solid #e8dff0;border-radius:25px;background:rgba(255,255,255,.7);font-size:14px;color:var(--diet-accent)}.diet-member>.disclosure-label{min-width:0}
.diet-month{display:flex;align-items:center;justify-content:space-between;margin:17px 2px 10px;font-size:14px;color:var(--diet-muted)}.diet-calendar{display:flex;align-items:center;justify-content:center;width:44px;height:44px;color:#b39ac3}
.diet-week{display:flex;justify-content:space-between;margin:0 -3px 18px}.diet-week button{width:40px;min-width:0;height:65px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:6px;background:transparent;border-radius:18px;color:var(--diet-muted);padding:0;font-size:12px;font-weight:400;line-height:1.4}.diet-week button>text:nth-child(2){font-size:17px;line-height:1.4;color:var(--diet-ink)}.diet-day-dot{width:3px;height:3px;border-radius:50%;background:transparent}.diet-day-dot.recorded{background:#c4afd3}.diet-week button.selected{background:#a58cb7;color:#efe7f4}.diet-week .selected>text:nth-child(2){color:#fff}.diet-week .selected .recorded{background:#eee5f4}
.diet-paper{overflow:hidden;border:1px solid rgba(255,255,255,.95);border-radius:22px;background:rgba(255,255,255,.96);box-shadow:0 8px 25px rgba(119,97,136,.025)}.diet-table-title{display:flex;align-items:center;justify-content:space-between;min-height:58px;padding:5px 17px;gap:7px}.diet-table-title>view{min-width:0;flex:1;display:flex;align-items:center;gap:8px;flex-wrap:wrap}.diet-table-title>view>text:first-child{font-size:15px;font-weight:500;color:var(--diet-ink)}.diet-table-title>view>text+text{font-size:12px;font-weight:400;color:var(--diet-muted)}.diet-table-title button{display:flex;align-items:center;gap:4px;min-height:44px;padding:0;color:var(--diet-accent);background:transparent;font-size:13px;font-weight:400;line-height:1.5;flex:none}
.diet-table-head{display:flex;align-items:center;height:35px;padding:0 18px;background:#f8f5fb;font-size:13px;font-weight:400;color:var(--diet-muted)}.diet-table-head>text:first-child{width:60px;flex:none}.diet-table-group{display:flex;padding:0 18px}.diet-table-group.tinted{background:#f8f5fb}.diet-meal-label{width:60px;flex:none;padding-top:19px;font-size:13px;font-weight:400;color:var(--diet-muted);line-height:1.7}.diet-records{flex:1;min-width:0}.diet-record{display:block;width:100%;text-align:left;padding:16px 0 12px;background:transparent;border-radius:0;line-height:1.7;white-space:normal}.diet-record+.diet-record{border-top:1px solid #eee7f3}.diet-record.editable{border-bottom:1px dashed #dfd0e9}.diet-food-line{display:flex;align-items:baseline;gap:11px;flex-wrap:wrap;row-gap:0;font-size:16px;font-weight:400;line-height:1.65;overflow-wrap:anywhere;color:var(--diet-ink)}.diet-food-line+.diet-food-line{margin-top:4px}.diet-food-line>text+text{font-size:13px;color:var(--diet-muted)}.diet-record-member{display:block;color:var(--diet-muted);font-size:12px;margin-bottom:5px}.diet-record-meta{display:flex;align-items:center;justify-content:space-between;font-size:12px;line-height:1.5;color:var(--diet-muted);margin-top:5px}.diet-table-footer{display:flex;justify-content:space-between;align-items:center;min-height:39px;padding:0 18px;font-size:12px;line-height:1.5;color:var(--diet-muted)}.diet-green-dot{color:#b7cfc2}.diet-empty{padding:35px 15px;text-align:center;font-size:14px;font-weight:400;line-height:1.6;color:var(--diet-muted)}
.diet-error{display:block;margin:14px 0;padding:12px;border-radius:12px;background:#fff4f4;color:#a75b65;font-size:12px;line-height:1.7}.diet-error button{font-size:12px;min-height:44px;color:#946fa8;background:transparent}.diet-add{width:100%;min-height:44px;margin-top:8px;color:var(--diet-accent);font-size:14px;font-weight:400;line-height:1.5;background:transparent}.diet-bottom{margin:25px 0 9px;text-align:center}.diet-chat{width:100%;min-height:46px;display:flex;align-items:center;justify-content:center;gap:9px;border:1px solid #e5d9ed;background:rgba(255,255,255,.65);border-radius:15px;font-size:15px;font-weight:400;line-height:1.5;color:var(--diet-accent)}.diet-chat>text:last-child{font-size:19px;margin-left:6px}.diet-bottom>text{display:block;font-size:12px;line-height:1.5;color:var(--diet-muted);margin-top:12px}.diet-table-footer{gap:8px;flex-wrap:wrap}.diet-table-footer>text:last-child{white-space:nowrap}.diet-journal button:after{border:0}.diet-journal button[disabled]{opacity:.5}
@media(max-width:350px){.diet-title{font-size:21px}.diet-table-group,.diet-table-head{padding-left:13px;padding-right:13px}.diet-meal-label,.diet-table-head>text:first-child{width:49px}.diet-week button{width:35px}.diet-journal{padding-left:3px;padding-right:3px}}
</style>
