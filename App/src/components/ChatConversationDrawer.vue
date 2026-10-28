<script setup>
import { computed, ref, watch, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { readConversations, readChatSnapshot, conversationTitle, conversationSummary } from '../services/cloud-chat.js'
import { scopedStorage, storageContext } from '../services/storage.js'
import { sessionRevision } from '../services/session.js'

const props = defineProps({ open: Boolean, memberId: String, activeThreadId: String, busy: Boolean, displayName: String })
const emit = defineEmits(['close', 'new', 'select', 'profile'])
const rows = ref([]), loading = ref(false), error = ref(''), notice = ref(''), hasMore = ref(false), nextOffset = ref(null)
let epoch = 0, disposed = false, directoryTicket = null
const today = () => new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10)
const rowDate = row => row.business_date || new Date(Date.parse(row.created_at) + 8 * 3600000).toISOString().slice(0, 10)
const groups = computed(() => {
  const date = today(), yesterday = new Date(Date.parse(date) - 86400000).toISOString().slice(0, 10)
  const result = new Map()
  for (const row of [...rows.value].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))) {
    const key = rowDate(row)
    if (!result.has(key)) result.set(key, { date: key, label: key === date ? '今天' : key === yesterday ? '昨天' : key, rows: [] })
    result.get(key).rows.push(row)
  }
  return [...result.values()].sort((a, b) => b.date.localeCompare(a.date))
})
const hasSummaryFailures = computed(() => rows.value.some(row => row.summaryFailed))
function reset() {
  epoch++; directoryTicket = null; rows.value = []; loading.value = false; error.value = ''; notice.value = ''; hasMore.value = false; nextOffset.value = null
}
function ticket() { return { epoch, memberId: props.memberId, scope: storageContext(), revision: sessionRevision() } }
function current(value) {
  return !disposed && props.open && value.epoch === epoch && value.memberId === props.memberId &&
    value.scope === storageContext() && value.revision === sessionRevision()
}
function discardChangedIdentity(value) {
  if (value.epoch === epoch && (value.scope !== storageContext() || value.revision !== sessionRevision())) reset()
}
const summaryKey = row => `conversation-summary:${props.memberId}:${row.thread_id}`
async function summaries(targets, value) {
  let index = 0
  async function worker() {
    while (index < targets.length && current(value)) {
      const row = targets[index++]
      try {
        const snapshot = await readChatSnapshot(row.thread_id)
        if (!current(value)) { discardChangedIdentity(value); return }
        row.title = conversationSummary(snapshot.messages)
        row.summaryPending = false
        try { scopedStorage.setStorageSync(summaryKey(row), { title: row.title, updatedAt: new Date().toISOString() }) } catch {}
      } catch (failure) {
        if (!current(value)) { discardChangedIdentity(value); return }
        row.summaryPending = false
        if ([403, 404, 409, 410].includes(Number(failure.code))) {
          row.unavailable = true; row.title = '该对话暂不可访问'
        } else { row.title = '暂未读取到标题'; row.summaryFailed = true }
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(4, targets.length) }, worker))
  if (!current(value)) return
  notice.value = [rows.value.some(row => row.unavailable) ? '部分对话的授权或资料来源已变化，暂不可访问。' : '',
    hasSummaryFailures.value ? '部分标题暂未读取到，可以重试。' : ''].filter(Boolean).join(' ')
}
async function load(more = false) {
  if (!props.open || disposed || loading.value || more && !hasMore.value) return
  if (!props.memberId) { reset(); error.value = '咨询资料尚未读到，请稍后重新读取。'; return }
  if (!more) reset()
  const value = ticket(), offset = more ? nextOffset.value : 0
  loading.value = true; error.value = ''; notice.value = ''
  try {
    const page = await readConversations(value.memberId, offset)
    if (!current(value)) { discardChangedIdentity(value); return }
    directoryTicket = value
    const fresh = page.items.filter(row => !rows.value.some(old => old.thread_id === row.thread_id)).map(row => {
      let cached
      try { cached = scopedStorage.getStorageSync(summaryKey(row)) } catch {}
      const title = typeof cached?.title === 'string' && cached.title.trim() ? conversationTitle(cached.title) : ''
      return { ...row, title: title || '正在读取对话…', summaryPending: !title, unavailable: false, summaryFailed: false }
    })
    rows.value = [...rows.value, ...fresh]
    hasMore.value = page.hasMore; nextOffset.value = page.nextOffset
    // Use the reactive rows; mutating the original pre-proxy objects would not update Vue's list.
    const ids = new Set(fresh.filter(row => row.summaryPending).map(row => row.thread_id))
    await summaries(rows.value.filter(row => ids.has(row.thread_id)), value)
  } catch (failure) {
    if (current(value)) {
      if ([401, 403, 404, 409, 410].includes(Number(failure.code))) { reset(); error.value = '登录或成员授权已变化，请重新进入对话。' }
      else error.value = '对话目录暂时无法读取，请重试。'
    }
    else discardChangedIdentity(value)
  } finally { if (current(value)) loading.value = false }
}
async function retryTitles() {
  if (loading.value || !props.open) return
  const value = ticket(), targets = rows.value.filter(row => row.summaryFailed)
  loading.value = true; notice.value = ''
  targets.forEach(row => { row.summaryFailed = false; row.summaryPending = true })
  try { await summaries(targets, value) } finally { if (current(value)) loading.value = false }
}
function close() { reset(); emit('close') }
function newConversation() { if (props.open && !props.busy) emit('new') }
function select(row) { if (!props.busy && !row.unavailable && directoryTicket && current(directoryTicket)) emit('select', { ...row }) }
function profile() { emit('profile') }
function loadMore() { if (hasMore.value && !loading.value) void load(true) }
watch(() => [props.open, props.memberId], () => { reset(); if (props.open) void load() }, { immediate: true })
onShow(() => { if (props.open) void load() })
onHide(reset)
onUnmounted(() => { disposed = true; reset() })
</script>

<template>
  <view v-if="open" class="conversation-drawer">
    <button class="drawer-backdrop" aria-label="关闭对话列表" @click="close" @touchmove.stop.prevent/>
    <view class="drawer-panel" role="dialog" aria-modal="true" aria-label="对话列表" @tap.stop>
      <AppNavBar below-capsule><view class="drawer-heading"><text>对话</text><button class="drawer-new" :disabled="busy" @click="newConversation"><view class="drawer-compose-icon" aria-hidden="true"><view/></view><text>新对话</text></button></view></AppNavBar>
      <text v-if="busy" class="drawer-busy" role="status">请等待当前回复结束，再新建或切换对话。</text>
      <scroll-view class="drawer-list" scroll-y :show-scrollbar="false" @scrolltolower="loadMore">
        <view v-for="group in groups" :key="group.date" class="drawer-group">
          <text class="drawer-date">{{group.label}}</text>
          <button v-for="row in group.rows" :key="row.thread_id" class="drawer-conversation" :class="{active:row.thread_id===activeThreadId,unavailable:row.unavailable}" :disabled="busy||row.unavailable" :aria-label="row.title" :aria-current="row.thread_id===activeThreadId?'true':undefined" @click="select(row)">
            <text>{{row.title}}</text>
          </button>
        </view>
        <text v-if="loading" class="drawer-status" role="status">正在读取对话…</text>
        <view v-if="error" class="drawer-error" role="alert"><text>{{error}}</text><button @click="load(rows.length>0)">重新读取</button></view>
        <view v-if="notice" class="drawer-notice" role="status"><text>{{notice}}</text><button v-if="hasSummaryFailures" :disabled="loading" @click="retryTitles">重试标题</button></view>
        <view v-if="!loading&&!error&&!rows.length" class="drawer-empty"><text>还没有对话</text><text>与你的家庭营养师聊聊，记录会保存在这里。</text></view>
        <button v-if="hasMore&&!error" class="drawer-more" :disabled="loading" @click="loadMore">{{loading?'正在读取…':'更早的对话'}}</button>
      </scroll-view>
      <view class="drawer-footer"><button class="drawer-profile" @click="profile"><view class="drawer-avatar" aria-hidden="true"><view/><view/></view><text>{{displayName||'我的'}}</text></button><button class="drawer-settings" aria-label="我的与设置" @click="profile"><view class="drawer-settings-icon" aria-hidden="true"><view/></view></button></view>
    </view>
  </view>
</template>

<style scoped>

.conversation-drawer{position:fixed;inset:0;z-index:900;overflow:hidden;color:#25262c}.drawer-backdrop{position:absolute;inset:0;width:100%;height:100%;padding:0;margin:0;border:0;border-radius:0;background:rgba(0,0,0,.6);animation:drawer-shade .18s ease-out}.drawer-backdrop:after{border:0}
.drawer-panel{position:absolute;top:0;bottom:0;left:0;width:76vw;max-width:420px;box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;padding:8px 16px calc(env(safe-area-inset-bottom) + 12px);background:radial-gradient(ellipse 110% 220px at 0% 0%,#93b8f9 0%,rgba(174,202,255,.7) 42%,transparent 100%),radial-gradient(ellipse 95% 230px at 12% 75px,rgba(198,185,255,.62),transparent 100%),linear-gradient(180deg,#edf4ff 0%,#fafafa 290px,#fafafa 100%);box-shadow:5px 0 20px rgba(0,0,0,.04);animation:drawer-enter .18s ease-out}
.drawer-heading{display:flex;align-items:center;justify-content:space-between;min-height:52px;gap:8px;padding-bottom:9px;border-bottom:1px solid rgba(255,255,255,.65)}.drawer-heading>text{font-size:23px;font-weight:600;line-height:1.4;color:#1f2430}
.drawer-new{position:relative;display:flex;align-items:center;justify-content:center;gap:7px;flex-shrink:0;width:auto;min-width:84px;min-height:44px;margin:0;padding:4px 8px;border:0;border-radius:9px;background:transparent;color:#252a32;text-align:left;font-size:14px;line-height:1.4}.drawer-new:before{content:'';position:absolute;inset:4px 0;border-radius:8px;background:rgba(255,255,255,.78)}.drawer-new>text,.drawer-new>view{position:relative;z-index:1}.drawer-new:after{border:0}.drawer-new[disabled]{opacity:.45;color:#6e7180}.drawer-compose-icon{width:15px;height:15px;border:1.5px solid currentColor;border-radius:3px;box-sizing:border-box}.drawer-compose-icon>view{position:absolute;width:12px;height:3px;right:-3px;top:0;transform:rotate(-45deg);border-radius:1px;background:currentColor;box-shadow:0 0 0 2px #f1f5ff}
.drawer-busy{display:block;flex-shrink:0;margin:12px 0 0;color:#77758a;font-size:12px;line-height:1.7}.drawer-list{flex:1;min-height:0;width:100%;margin-top:62px}.drawer-group{margin:0 0 28px}.drawer-date{display:block;padding:9px 0;color:#a0a0a6;font-size:12px;line-height:1.5}.drawer-conversation{display:flex;align-items:center;width:100%;min-height:44px;box-sizing:border-box;margin:0;padding:9px 0;border:0;border-radius:6px;background:transparent;color:#303036;text-align:left;line-height:1.5;font-size:16px}.drawer-conversation:after{border:0}.drawer-conversation>text{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.drawer-conversation.active{color:#20202a;font-weight:500}.drawer-conversation:active{background:rgba(255,255,255,.6)}.drawer-conversation[disabled]{color:#97959e;background:transparent}.drawer-conversation.unavailable{font-size:13px}
.drawer-status,.drawer-error,.drawer-notice,.drawer-empty{display:block;padding:14px 0;color:#8d8a99;font-size:13px;line-height:1.8}.drawer-error{color:#8d4c40}.drawer-error>text,.drawer-notice>text,.drawer-empty>text{display:block}.drawer-error button,.drawer-notice button,.drawer-more{display:flex;align-items:center;justify-content:center;min-height:44px;margin:12px 0;padding:8px 14px;border:1px solid #e1dded;border-radius:8px;background:rgba(255,255,255,.72);color:#675d84;font-size:13px}.drawer-error button:after,.drawer-notice button:after,.drawer-more:after{border:0}.drawer-more{width:100%;background:transparent}.drawer-empty{padding-top:20px;text-align:center}.drawer-empty>text:first-child{margin-bottom:8px;color:#555061;font-size:16px}
.drawer-footer{display:flex;align-items:center;gap:10px;flex-shrink:0;margin:12px -16px 0;padding:10px 12px 0 16px;border-top:1px solid #dddde2}.drawer-profile{display:flex;align-items:center;gap:8px;flex:1;min-width:0;min-height:44px;margin:0;padding:0;border:0;background:transparent;color:#34333a;font-size:16px;text-align:left}.drawer-profile:after,.drawer-settings:after{border:0}.drawer-profile>text{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.drawer-avatar{position:relative;flex-shrink:0;width:27px;height:27px;overflow:hidden;border:2px solid rgba(240,237,255,.9);border-radius:50%;background:linear-gradient(145deg,#eeeaff,#c5bcfa);box-shadow:0 0 5px rgba(162,149,224,.08)}.drawer-avatar>view:first-child{position:absolute;top:3px;left:7px;width:13px;height:13px;border-radius:50%;background:#fff}.drawer-avatar>view+view{position:absolute;left:3px;bottom:-5px;width:21px;height:15px;border-radius:50% 50% 0 0;background:#fff}.drawer-settings{display:flex;align-items:center;justify-content:center;flex-shrink:0;min-width:44px;min-height:44px;margin:0;padding:0;border:0;background:transparent;color:#3a3d42}.drawer-settings-icon{display:flex;align-items:center;justify-content:center;width:17px;height:19px;border:2px solid currentColor;border-radius:5px;transform:rotate(30deg)}.drawer-settings-icon>view{width:5px;height:5px;border:2px solid currentColor;border-radius:50%;transform:rotate(-30deg)}
@keyframes drawer-enter{from{transform:translateX(-100%)}to{transform:translateX(0)}}@keyframes drawer-shade{from{opacity:0}to{opacity:1}}@media(max-height:700px){.drawer-list{margin-top:38px}}@media(max-width:350px){.drawer-panel{padding-left:14px;padding-right:14px}.drawer-heading>text{font-size:21px}.drawer-new{min-width:78px;font-size:13px}.drawer-conversation{font-size:15px}.drawer-footer{margin-left:-14px;margin-right:-14px;padding-left:14px}}@media(prefers-reduced-motion:reduce){.drawer-panel,.drawer-backdrop{animation:none}}
</style>
