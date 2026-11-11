<script setup>
import { computed, ref, watch, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { readConversations } from '../services/cloud-chat.js'
import { backdropOpacity, clampDragOffset, shouldCloseDrawer, DRAWER_SETTLE_MS } from '../utils/drawer-swipe.js'
import { storageContext } from '../services/storage.js'
import { sessionRevision } from '../services/session.js'

const props = defineProps({ open: Boolean, memberId: String, activeThreadId: String, busy: Boolean, browseBusy: Boolean, newBusy: Boolean, deniedThreadId: String, pendingThreadId: String, selectionError: String, displayName: String })
const emit = defineEmits(['close', 'new', 'select', 'profile', 'ready'])
// Drag-to-close from the panel's right edge. The grip is a narrow strip so vertical list scrolling is unaffected.
const dragOffset = ref(0), dragPhase = ref('')
let dragStartX = 0, dragStartAt = 0, dragWidth = 0, dragTimer = null
const panelStyle = computed(() => dragPhase.value ? { transform: `translateX(-${dragOffset.value}px)` } : {})
const backdropStyle = computed(() => dragPhase.value ? { opacity: String(backdropOpacity(dragOffset.value, dragWidth)) } : {})
function measuredPanelWidth() {
  let width = 375
  try { width = uni.getSystemInfoSync?.()?.windowWidth || width } catch {}
  return Math.min(width * 0.76, 420)
}
function clearDragTimer() { if (dragTimer !== null) { clearTimeout(dragTimer); dragTimer = null } }
function clearDrag() { clearDragTimer(); dragPhase.value = ''; dragOffset.value = 0 }
function touchPoint(event) { return event?.touches?.[0] || event?.changedTouches?.[0] || null }
function beginDrag(event) {
  if (!props.open || disposed) return
  const point = touchPoint(event)
  if (!point) return
  clearDragTimer()
  dragWidth = measuredPanelWidth()
  dragStartX = point.clientX; dragStartAt = Date.now()
  dragOffset.value = 0; dragPhase.value = 'dragging'
}
function moveDrag(event) {
  if (dragPhase.value !== 'dragging') return
  const point = touchPoint(event)
  if (!point) return
  dragOffset.value = clampDragOffset(dragStartX - point.clientX, dragWidth)
}
function endDrag() {
  if (dragPhase.value !== 'dragging') return
  const distance = dragOffset.value, duration = Math.max(1, Date.now() - dragStartAt)
  const closing = shouldCloseDrawer({ distance, width: dragWidth, duration })
  dragPhase.value = 'settling'
  dragOffset.value = closing ? dragWidth : 0
  clearDragTimer()
  dragTimer = setTimeout(() => {
    dragTimer = null
    if (disposed) return
    dragPhase.value = ''; dragOffset.value = 0
    if (closing) close()
  }, DRAWER_SETTLE_MS)
}
const rows = ref([]), loading = ref(false), error = ref(''), notice = ref(''), hasMore = ref(false), nextOffset = ref(null)
let epoch = 0, disposed = false, directoryTicket = null, retryMore = false
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
function reset() {
  clearDrag(); epoch++; directoryTicket = null; rows.value = []; loading.value = false; error.value = ''; notice.value = ''; hasMore.value = false; nextOffset.value = null
}
function ticket() { return { epoch, memberId: props.memberId, scope: storageContext(), revision: sessionRevision() } }
function sameIdentity(value) {
  return value && value.memberId === props.memberId && value.scope === storageContext() && value.revision === sessionRevision()
}
function current(value) {
  return !disposed && props.open && value.epoch === epoch && sameIdentity(value)
}
function discardChangedIdentity(value) {
  if (value.epoch === epoch && (value.scope !== storageContext() || value.revision !== sessionRevision())) reset()
}
async function load(more = false) {
  if (directoryTicket && !sameIdentity(directoryTicket)) reset()
  if (!props.open || disposed || loading.value || more && !hasMore.value) return
  if (!props.memberId) { reset(); error.value = '咨询资料尚未读到，请稍后重新读取。'; return }
  const value = ticket(), count = Math.max(1, rows.value.length), collected = new Map()
  let offset = more ? nextOffset.value : 0, page
  loading.value = true; error.value = ''; retryMore = more
  try {
    // 刷新整个已加载窗口后统一更新游标；保留可见目录，及时覆盖已知撤权标题。
    do {
      page = await readConversations(value.memberId, offset)
      if (!current(value)) { discardChangedIdentity(value); return }
      for (const row of page.items) collected.set(row.thread_id, row)
      rows.value = rows.value.map(row => collected.get(row.thread_id) || row)
      if (!page.hasMore || more || collected.size >= count) break
      if (page.nextOffset <= offset) throw new Error('对话分页未前进')
      offset = page.nextOffset
    } while (true)
    directoryTicket = value
    rows.value = more ? [...new Map([...rows.value, ...collected.values()].map(row => [row.thread_id, row])).values()] : [...collected.values()]
    hasMore.value = page.hasMore; nextOffset.value = page.nextOffset
    notice.value = rows.value.some(row => row.unavailable) ? '部分对话的授权或资料来源已变化，暂不可访问。' : ''
    emit('ready', rows.value.map(row => ({ ...row })))
  } catch (failure) {
    if (current(value)) {
      if ([401, 403, 404, 409, 410].includes(Number(failure.code))) { reset(); error.value = '登录或成员授权已变化，请重新进入对话。' }
      else error.value = '对话目录暂时无法读取，请重试。'
    }
    else discardChangedIdentity(value)
  } finally { if (current(value)) loading.value = false }
}
function suspend() { clearDrag(); epoch++; loading.value = false }
function close() { suspend(); emit('close') }
function newConversation() { if (props.open && !props.busy && !props.newBusy) emit('new') }
function select(row) {
  if (directoryTicket && !sameIdentity(directoryTicket)) { reset(); return }
  const saved = rows.value.find(item => item.thread_id === row.thread_id)
  if (props.open && !disposed && !props.browseBusy && saved && !saved.unavailable && directoryTicket) emit('select', { ...saved })
}
function profile() { emit('profile') }
function loadMore() { if (hasMore.value && !loading.value) void load(true) }
function retry() { void load(retryMore) }
watch(() => [props.open, props.memberId], (_next, previous) => {
  if (previous && previous[1] !== props.memberId || directoryTicket && !sameIdentity(directoryTicket)) reset()
  if (props.open) void load(); else suspend()
}, { immediate: true })
watch(() => props.deniedThreadId, id => {
  suspend()
  rows.value = rows.value.map(row => row.thread_id === id ? { ...row, title: '该对话暂不可访问', unavailable: true } : row)
  notice.value = '部分对话的授权或资料来源已变化，暂不可访问。'
})
onShow(() => { if (props.open) void load() })
onHide(reset)
onUnmounted(() => { disposed = true; reset() })
</script>

<template>
  <view v-show="open" class="conversation-drawer">
    <button class="drawer-backdrop" :class="{'is-dragging':dragPhase==='dragging'}" :style="backdropStyle" aria-label="关闭对话列表" @click="close" @touchmove.stop.prevent/>
    <view class="drawer-panel" :class="{'is-dragging':dragPhase==='dragging','is-settling':dragPhase==='settling'}" :style="panelStyle" role="dialog" aria-modal="true" aria-label="对话列表" @tap.stop>
      <AppNavBar below-capsule><view class="drawer-heading"><text>对话</text><button class="drawer-new" :disabled="busy||newBusy" @click="newConversation"><view class="drawer-compose-icon" aria-hidden="true"><view/></view><text>新对话</text></button></view></AppNavBar>
      <text v-if="busy" class="drawer-busy" role="status">当前对话处理中，仍可查看历史记录。</text>
      <scroll-view class="drawer-list" scroll-y :show-scrollbar="false" @scrolltolower="loadMore">
        <view v-for="group in groups" :key="group.date" class="drawer-group">
          <text class="drawer-date">{{group.label}}</text>
          <button v-for="row in group.rows" :key="row.thread_id" class="drawer-conversation" :class="{active:row.thread_id===activeThreadId,unavailable:row.unavailable}" :disabled="browseBusy||row.unavailable" :aria-label="row.title" :aria-current="row.thread_id===activeThreadId?'true':undefined" @click="select(row)">
            <text>{{row.title}}</text><text v-if="row.thread_id===pendingThreadId" class="drawer-opening" role="status" aria-label="正在打开对话">…</text>
          </button>
        </view>
        <text v-if="loading" class="drawer-status" role="status">{{rows.length?'正在更新对话…':'正在读取对话…'}}</text>
        <text v-if="selectionError" class="drawer-error" role="alert">{{selectionError}}</text>
        <view v-if="error" class="drawer-error" role="alert"><text>{{error}}</text><button @click="retry">重新读取</button></view>
        <view v-if="notice" class="drawer-notice" role="status"><text>{{notice}}</text></view>
        <view v-if="!loading&&!error&&!rows.length" class="drawer-empty"><text>还没有对话</text><text>与你的家庭营养师聊聊，记录会保存在这里。</text></view>
        <button v-if="hasMore&&!error" class="drawer-more" :disabled="loading" @click="loadMore">{{loading?'正在读取…':'更早的对话'}}</button>
      </scroll-view>
      <view class="drawer-footer"><button class="drawer-profile" @click="profile"><view class="drawer-avatar" aria-hidden="true"><view/><view/></view><text>{{displayName||'我的'}}</text></button><button class="drawer-settings" aria-label="我的与设置" @click="profile"><view class="drawer-settings-icon" aria-hidden="true"><view/></view></button></view>
      <view class="drawer-grip" aria-hidden="true" @touchstart="beginDrag" @touchmove.stop.prevent="moveDrag" @touchend="endDrag" @touchcancel="endDrag"/>
    </view>
  </view>
</template>

<style scoped>
.drawer-conversation>.drawer-opening{flex:none;min-width:18px;text-align:right;color:var(--ui-muted)}

.conversation-drawer{position:fixed;inset:0;z-index:900;overflow:hidden;color:#25262c}.drawer-backdrop{position:absolute;inset:0;width:100%;height:100%;padding:0;margin:0;border:0;border-radius:0;background:rgba(32,35,43,.34);animation:drawer-shade .18s ease-out}.drawer-backdrop:after{border:0}
.drawer-panel{position:absolute;top:0;bottom:0;left:0;width:76vw;max-width:420px;box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;padding:8px 16px calc(env(safe-area-inset-bottom) + 12px);background-color:var(--ui-canvas);
/* Keep the color wash on the panel so the safe area and heading share it while rows scroll independently. */
background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.65),rgba(125,174,255,0) 72%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.55),rgba(206,178,245,0) 75%);
background-size:100% 320px;background-position:left top;background-repeat:no-repeat;box-shadow:5px 0 20px rgba(0,0,0,.04);animation:drawer-enter .18s ease-out}
.drawer-heading{display:flex;align-items:center;justify-content:space-between;min-height:52px;gap:8px;padding-bottom:12px;border-bottom:1px solid rgba(255,255,255,.65)}.drawer-heading>text{font-size:22px;font-weight:600;line-height:1.4;color:var(--ui-text)}
.drawer-new{position:relative;display:flex;align-items:center;justify-content:center;gap:7px;flex-shrink:0;width:auto;min-width:84px;min-height:44px;margin:0;padding:4px 8px;border:0;border-radius:9px;background:transparent;color:#44414f;text-align:left;font-size:14px;font-weight:500;line-height:1.4}.drawer-new:before{content:'';position:absolute;inset:4px 0;border-radius:8px;background:rgba(255,255,255,.78)}.drawer-new>text,.drawer-new>view{position:relative;z-index:1}.drawer-new:after{border:0}.drawer-new[disabled]{opacity:.45;color:#6e7180}/* Open the outline around the pencil instead of masking it with a fixed background color. */
.drawer-compose-icon{position:relative;width:15px;height:15px;border:1.5px solid currentColor;border-top-color:transparent;border-right-color:transparent;border-radius:3px;box-sizing:border-box}.drawer-compose-icon:before,.drawer-compose-icon:after{content:'';position:absolute;background:currentColor;border-radius:1px}.drawer-compose-icon:before{left:1px;top:-1.5px;width:5px;height:1.5px}.drawer-compose-icon:after{right:-1.5px;bottom:1px;width:1.5px;height:5px}.drawer-compose-icon>view{position:absolute;width:12px;height:3px;right:-3px;top:1px;transform:rotate(-45deg);border-radius:1px;background:currentColor}
.drawer-busy{display:block;flex-shrink:0;margin:12px 0 0;color:#77758a;font-size:12px;line-height:1.7}.drawer-list{flex:1;min-height:0;width:100%;margin-top:28px}.drawer-list :deep(.uni-scroll-view){scrollbar-width:none}.drawer-list :deep(.uni-scroll-view::-webkit-scrollbar){display:none;width:0;height:0}.drawer-group{margin:0 0 28px}.drawer-date{display:block;padding:9px 0;color:var(--ui-muted);font-size:12px;line-height:1.5}.drawer-conversation{display:flex;align-items:center;width:100%;min-height:44px;box-sizing:border-box;margin:0;padding:12px;border:0;border-radius:14px;background:transparent;color:var(--ui-text);text-align:left;line-height:1.5;font-size:16px}.drawer-conversation:after{border:0}.drawer-conversation>text{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.drawer-conversation.active{color:#55436f;background:rgba(226,219,244,.55);font-weight:500}.drawer-conversation:active{background:rgba(255,255,255,.6)}.drawer-conversation[disabled]{color:#97959e;background:transparent}.drawer-conversation.unavailable{font-size:13px}
.drawer-status,.drawer-error,.drawer-notice,.drawer-empty{display:block;padding:14px 0;color:#8d8a99;font-size:13px;line-height:1.8}.drawer-error{color:#8d4c40}.drawer-error>text,.drawer-notice>text,.drawer-empty>text{display:block}.drawer-error button,.drawer-notice button,.drawer-more{display:flex;align-items:center;justify-content:center;min-height:44px;margin:12px 0;padding:8px 14px;border:1px solid #e1dded;border-radius:8px;background:rgba(255,255,255,.72);color:#675d84;font-size:13px}.drawer-error button:after,.drawer-notice button:after,.drawer-more:after{border:0}.drawer-more{width:100%;background:transparent}.drawer-empty{padding-top:20px;text-align:center}.drawer-empty>text:first-child{margin-bottom:8px;color:#555061;font-size:16px}
.drawer-footer{display:flex;align-items:center;gap:10px;flex-shrink:0;margin:12px -16px 0;padding:10px 12px 0 16px;border-top:1px solid var(--ui-line)}.drawer-profile{display:flex;align-items:center;gap:8px;flex:1;min-width:0;min-height:44px;margin:0;padding:0;border:0;background:transparent;color:#34333a;font-size:16px;text-align:left}.drawer-profile:after,.drawer-settings:after{border:0}.drawer-profile>text{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.drawer-avatar{position:relative;flex-shrink:0;width:27px;height:27px;overflow:hidden;border:2px solid rgba(240,237,255,.9);border-radius:50%;background:#d9d1eb;box-shadow:0 0 5px rgba(162,149,224,.08)}.drawer-avatar>view:first-child{position:absolute;top:3px;left:7px;width:13px;height:13px;border-radius:50%;background:#fff}.drawer-avatar>view+view{position:absolute;left:3px;bottom:-5px;width:21px;height:15px;border-radius:50% 50% 0 0;background:#fff}.drawer-settings{display:flex;align-items:center;justify-content:center;flex-shrink:0;min-width:44px;min-height:44px;margin:0;padding:0;border:0;background:transparent;color:#3a3d42}.drawer-settings-icon{display:flex;align-items:center;justify-content:center;width:17px;height:19px;border:1.6px solid currentColor;border-radius:5px;transform:rotate(30deg)}.drawer-settings-icon>view{width:5px;height:5px;border:1.6px solid currentColor;border-radius:50%;transform:rotate(-30deg)}
@keyframes drawer-enter{from{transform:translateX(-100%)}to{transform:translateX(0)}}@keyframes drawer-shade{from{opacity:0}to{opacity:1}}
/* Narrow, invisible grab strip on the panel's right edge: drag left to close. */
.drawer-grip{position:absolute;top:0;bottom:0;right:0;width:18px;z-index:3;background:transparent}
.drawer-panel.is-dragging{animation:none;transition:none}
.drawer-panel.is-settling{animation:none;transition:transform .18s ease-out}
.drawer-backdrop.is-dragging{animation:none;transition:none}@media(max-height:700px){.drawer-panel{background-size:100% 280px}.drawer-list{margin-top:20px}}@media(max-height:480px){.drawer-panel{background-size:100% 220px}}@media(max-width:350px){.drawer-panel{padding-left:14px;padding-right:14px}.drawer-heading>text{font-size:21px}.drawer-new{min-width:78px;font-size:13px}.drawer-conversation{font-size:15px}.drawer-footer{margin-left:-14px;margin-right:-14px;padding-left:14px}}@media(prefers-reduced-motion:reduce){.drawer-panel,.drawer-backdrop{animation:none}}
</style>
