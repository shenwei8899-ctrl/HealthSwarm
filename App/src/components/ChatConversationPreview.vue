<script setup>
import { reactive, watch, onUnmounted } from 'vue'
import { onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import AiAnswer from './AiAnswer.vue'
import HealthChatBusinessCard from './HealthChatBusinessCard.vue'
import ChatMealRecordCard from './ChatMealRecordCard.vue'
import ConversationFoodPackages from './ConversationFoodPackages.vue'
import ChatReplyActions from './ChatReplyActions.vue'
import { conversationPreviewState, createConversationPreview } from '../services/conversation-preview.js'
import { storageContext } from '../services/storage.js'
import { previewChatImage } from '../services/chat-images.js'

const props = defineProps({ row: Object, memberId: String, replying: Boolean })
const emit = defineEmits(['close', 'directory', 'denied'])
const state = reactive(conversationPreviewState())
const client = createConversationPreview({ state, context: () => storageContext() + ':' + props.memberId,
  onDenied: (threadId, status) => emit('denied', { threadId, status }) })
function load() { if (props.row?.member_id === props.memberId) void client.open(props.row, props.row.prepared); else client.clear() }
watch(() => [props.row, props.memberId], load, { immediate: true })
onHide(client.clear)
onUnmounted(client.dispose)
</script>

<template>
  <view class="history-preview" role="dialog" aria-modal="true" aria-label="历史对话预览">
    <AppNavBar below-capsule><view class="preview-heading"><button aria-label="打开对话列表" @click="emit('directory')">‹ 对话</button><text>{{row?.title||'历史对话'}}</text><button aria-label="返回当前对话" @click="emit('close')">返回</button></view></AppNavBar>
    <view class="preview-note"><text>{{replying?'原对话继续回复中，当前仅浏览历史。':'正在浏览历史对话。'}}</text><button @click="emit('close')">返回当前对话 ›</button></view>
    <scroll-view class="preview-messages" scroll-y :show-scrollbar="false">
      <view v-for="message in state.messages" :key="message.threadId+':'+message.id" class="preview-message" :class="message.role">
        <text class="preview-role">{{message.role==='user'?'我':'家庭营养师'}}</text>
        <image v-if="message.image" :src="message.image.localPath" mode="widthFix" @click="previewChatImage(message.image)"/>
        <AiAnswer v-if="message.role==='assistant'&&message.text" :text="message.text" :animate-meals="false"/>
        <text v-else-if="message.text" class="preview-text" selectable>{{message.text}}</text>
        <HealthChatBusinessCard v-if="message.business" read-only :result="message.business" :member-id="memberId"/>
        <ConversationFoodPackages v-if="message.purchaseRequestId" read-only :request-id="message.purchaseRequestId"/>
        <ChatMealRecordCard v-for="receipt in message.recordedMeals||[]" :key="receipt.id" read-only :receipt="receipt"/>
        <ChatReplyActions v-if="message.role==='assistant'&&message.text" :text="message.text" :can-quote="false"/>
      </view>
      <text v-if="state.notice" class="preview-status" role="status">{{state.notice}}</text>
      <view v-if="state.error||state.notice" class="preview-error" role="status"><text>{{state.error}}</text><button :disabled="state.loading" @click="load">重新读取</button></view>
      <text v-if="!state.loading&&!state.error&&!state.messages.length" class="preview-status">这段对话暂无可读取的消息。</text>
    </scroll-view>
  </view>
</template>

<style scoped>
.history-preview{position:fixed;inset:0;z-index:850;display:flex;flex-direction:column;box-sizing:border-box;overflow:hidden;padding:8px 20px calc(env(safe-area-inset-bottom) + 12px);background:var(--ui-canvas,#f7f7fa);color:var(--ui-text,#25262c)}
.preview-heading{display:flex;align-items:center;gap:12px;min-height:48px}.preview-heading>text{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:17px;font-weight:600}.preview-heading button,.preview-note button,.preview-error button{flex-shrink:0;min-height:44px;margin:0;padding:8px;background:transparent;color:#675d84;font-size:14px}.preview-heading button:after,.preview-note button:after,.preview-error button:after{border:0}
.preview-note{display:flex;align-items:center;justify-content:space-between;gap:8px;border-bottom:1px solid var(--ui-line,#e6e2ed);font-size:12px;color:var(--ui-muted,#77758a);line-height:1.7}.preview-note button{font-size:12px;padding-right:0}.preview-messages{flex:1;min-height:0;width:100%}.preview-message{margin:24px 0;font-size:16px;line-height:1.8;overflow-wrap:anywhere}.preview-role{display:block;margin-bottom:8px;color:var(--ui-muted,#888);font-size:12px}.preview-text{display:block;white-space:pre-line}.preview-message>image{display:block;width:210px;max-width:100%;margin-bottom:8px;border-radius:12px}.preview-message.user{text-align:right;padding-left:40px}.user .preview-text{display:inline-block;padding:12px 16px;border-radius:16px 4px 16px 16px;background:var(--ui-accent-soft,#e7def3);text-align:left}.preview-status,.preview-error{display:block;margin:16px 0;font-size:13px;line-height:1.8;color:var(--ui-muted,#888)}.preview-error>text{display:block}.preview-error button{padding-left:0}
</style>
