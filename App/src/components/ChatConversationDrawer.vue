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
const avatar = computed(() => Array.from(props.displayName?.trim() || '我')[0])
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
      <AppNavBar below-capsule><view class="drawer-heading"><text>对话</text><button class="drawer-close" aria-label="关闭对话列表" @click="close">×</button></view></AppNavBar>
      <button class="drawer-new" :disabled="busy" @click="newConversation"><text aria-hidden="true">＋</text><text>新对话</text></button>
      <text v-if="busy" class="drawer-busy" role="status">请等待当前回复结束，再新建或切换对话。</text>
      <scroll-view class="drawer-list" scroll-y :show-scrollbar="false" @scrolltolower="loadMore">
        <view v-for="group in groups" :key="group.date" class="drawer-group">
          <text class="drawer-date">{{group.label}}</text>
          <button v-for="row in group.rows" :key="row.thread_id" class="drawer-conversation" :class="{active:row.thread_id===activeThreadId,unavailable:row.unavailable}" :disabled="busy||row.unavailable" :aria-label="row.title" @click="select(row)">
            <text>{{row.title}}</text><text v-if="row.thread_id===activeThreadId" class="drawer-current">当前</text>
          </button>
        </view>
        <text v-if="loading" class="drawer-status" role="status">正在读取对话…</text>
        <view v-if="error" class="drawer-error" role="alert"><text>{{error}}</text><button @click="load(rows.length>0)">重新读取</button></view>
        <view v-if="notice" class="drawer-notice" role="status"><text>{{notice}}</text><button v-if="hasSummaryFailures" :disabled="loading" @click="retryTitles">重试标题</button></view>
        <view v-if="!loading&&!error&&!rows.length" class="drawer-empty"><text>还没有对话</text><text>与你的家庭营养师聊聊，记录会保存在这里。</text></view>
        <button v-if="hasMore&&!error" class="drawer-more" :disabled="loading" @click="loadMore">{{loading?'正在读取…':'更早的对话'}}</button>
      </scroll-view>
      <view class="drawer-footer"><button class="drawer-profile" @click="profile"><text class="drawer-avatar">{{avatar}}</text><text>{{displayName||'我的'}}</text></button><button class="drawer-settings" aria-label="我的与设置" @click="profile">设置</button></view>
    </view>
  </view>
</template>

<style scoped>
.conversation-drawer{position:fixed;inset:0;z-index:900;overflow:hidden;color:#171717}.drawer-backdrop{position:absolute;inset:0;width:100%;height:100%;padding:0;margin:0;border:0;border-radius:0;background:rgba(0,0,0,.42);animation:drawer-shade .18s ease-out}.drawer-backdrop:after{border:0}.drawer-panel{position:absolute;top:0;bottom:0;left:0;width:82vw;max-width:380px;box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;padding:8px 20px calc(env(safe-area-inset-bottom) + 16px);background:#fafafa;box-shadow:8px 0 30px rgba(0,0,0,.08);animation:drawer-enter .18s ease-out}.drawer-heading{display:flex;align-items:center;justify-content:space-between;min-height:48px;gap:12px}.drawer-heading>text{font-size:23px;font-weight:600;line-height:1.4}.drawer-close{display:flex;align-items:center;justify-content:center;width:44px;min-width:44px;height:44px;margin:0 -10px 0 auto;padding:0;border:0;background:transparent;color:#555;font-size:31px;font-weight:300}.drawer-close:after{border:0}.drawer-new{display:flex;align-items:center;gap:10px;flex-shrink:0;width:100%;min-height:48px;margin:8px 0 16px;padding:10px 14px;border:1px solid #ddd;border-radius:10px;background:#fff;color:#202020;text-align:left;font-size:16px;line-height:1.5}.drawer-new>text:first-child{font-size:24px;line-height:1}.drawer-new:after{border:0}.drawer-new[disabled]{background:#f2f2f2;color:#999}.drawer-busy{display:block;flex-shrink:0;margin:-2px 0 12px;color:#777;font-size:12px;line-height:1.7}.drawer-list{flex:1;min-height:0;width:100%}.drawer-group{margin:4px 0 20px}.drawer-date{display:block;padding:10px 10px 8px;color:#858585;font-size:12px;line-height:1.5}.drawer-conversation{display:flex;align-items:center;gap:8px;width:100%;min-height:48px;box-sizing:border-box;margin:2px 0;padding:12px 10px;border:0;border-radius:8px;background:transparent;color:#262626;text-align:left;line-height:1.5;font-size:15px}.drawer-conversation:after{border:0}.drawer-conversation>text:first-child{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.drawer-conversation.active{background:#eaeaea;color:#111}.drawer-conversation:active{background:#eee}.drawer-conversation[disabled]{color:#909090;background:transparent}.drawer-conversation.active[disabled]{background:#eaeaea}.drawer-conversation.unavailable{font-size:13px}.drawer-current{flex-shrink:0;font-size:10px;color:#777}.drawer-status,.drawer-error,.drawer-notice,.drawer-empty{display:block;padding:14px 10px;color:#888;font-size:13px;line-height:1.8}.drawer-error{color:#8d4c40}.drawer-error>text,.drawer-notice>text,.drawer-empty>text{display:block}.drawer-error button,.drawer-notice button,.drawer-more{display:flex;align-items:center;justify-content:center;min-height:44px;margin:12px 0;padding:8px 14px;border:1px solid #ddd;border-radius:8px;background:#fff;color:#333;font-size:13px}.drawer-error button:after,.drawer-notice button:after,.drawer-more:after{border:0}.drawer-more{width:100%;background:transparent}.drawer-empty{padding-top:44px;text-align:center}.drawer-empty>text:first-child{margin-bottom:8px;color:#444;font-size:16px}.drawer-footer{display:flex;align-items:center;gap:10px;flex-shrink:0;margin-top:12px;padding-top:16px;border-top:1px solid #e6e6e6}.drawer-profile{display:flex;align-items:center;gap:10px;flex:1;min-width:0;min-height:44px;margin:0;padding:0;border:0;background:transparent;color:#333;font-size:14px;text-align:left}.drawer-profile:after,.drawer-settings:after{border:0}.drawer-profile>text:last-child{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.drawer-avatar{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:32px;height:32px;border-radius:50%;background:#202020;color:#fff;font-size:14px}.drawer-settings{flex-shrink:0;min-width:44px;min-height:44px;margin:0;padding:8px 0;border:0;background:transparent;color:#777;font-size:13px}@keyframes drawer-enter{from{transform:translateX(-100%)}to{transform:translateX(0)}}@keyframes drawer-shade{from{opacity:0}to{opacity:1}}@media(max-width:350px){.drawer-panel{padding-left:16px;padding-right:16px}.drawer-conversation{font-size:14px}}@media(prefers-reduced-motion:reduce){.drawer-panel,.drawer-backdrop{animation:none}}
</style>
