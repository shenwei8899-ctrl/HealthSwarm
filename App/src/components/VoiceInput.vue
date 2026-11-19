<script>
let serverVoiceAccepted = false
</script>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { createVoiceCapture } from '../services/chat-voice.js'

const props = defineProps({ disabled: { type: Boolean, default: false }, embedded: { type: Boolean, default: false } })
const emit = defineEmits(['send', 'busy'])
const state = ref({ phase: 'idle', error: '', canceling: false, hasAudio: false, permissionDenied: false })
const levels = ref(Array(44).fill(0))
const busy = computed(() => ['authorizing', 'starting', 'recording', 'stopping', 'transcribing'].includes(state.value.phase))
const overlay = computed(() => ['starting', 'recording', 'stopping'].includes(state.value.phase))
const prompt = computed(() => state.value.phase === 'stopping' ? (state.value.canceling ? '正在取消录音…' : '正在结束录音…') : state.value.canceling ? '松手取消' : state.value.phase === 'starting' ? '正在打开麦克风…' : '松手识别，上移取消')
const label = computed(() => state.value.phase === 'transcribing' ? '正在识别…' : state.value.phase === 'authorizing' ? '正在打开麦克风…' : '按住说话')
const progressVisible = computed(() => ['authorizing', 'starting', 'stopping', 'transcribing'].includes(state.value.phase))
const canCancel = computed(() => progressVisible.value && !state.value.canceling)
const progressLabel = computed(() => ['starting', 'stopping'].includes(state.value.phase) ? prompt.value : label.value)
const cancelLabel = computed(() => state.value.phase === 'transcribing' ? '取消识别' : state.value.phase === 'stopping' ? '取消发送' : '取消录音')
let voiceNoticeOpen = false
let nativeRecording = false
// #ifdef MP-WEIXIN
nativeRecording = true
// #endif
const recorder = createVoiceCapture({
  getRecorder: () => {
    if (!nativeRecording) throw new Error('请在微信小程序中使用语音输入')
    return uni.getRecorderManager()
  },
  onState: value => { state.value = value; emit('busy', ['authorizing', 'starting', 'recording', 'stopping', 'transcribing'].includes(value.phase)) },
  onLevel: level => { levels.value = [...levels.value.slice(1), level] },
  onText: text => emit('send', text),
})
function touchY(event) { const point=event.touches?.[0]||event.changedTouches?.[0]; return point?.clientY ?? point?.pageY }
function start(event) {
  if (props.disabled || busy.value) return
  if (nativeRecording && !serverVoiceAccepted) {
    if (voiceNoticeOpen) return
    voiceNoticeOpen = true
    uni.showModal({
      title: '语音转文字',
      content: '录音会上传到本小程序的服务器用于转写，识别后的文字可编辑后发送。',
      confirmText: '同意使用',
      success(result) {
        if (result.confirm) {
          serverVoiceAccepted = true
          uni.showToast({ title: '请再次按住说话', icon: 'none' })
        }
      },
      complete() { voiceNoticeOpen = false },
    })
    return
  }
  levels.value=Array(44).fill(0);recorder.begin(touchY(event)||0)
}
function end(event) { recorder.end(touchY(event)) }
function cancel() { recorder.cancel() }
function openSettings() {
  uni.openSetting({
    success: result => {
      if (result.authSetting?.['scope.record']) {
        state.value = { ...state.value, error: '', permissionDenied: false }
        uni.showToast({ title: '已开启，请按住说话', icon: 'none' })
      } else uni.showToast({ title: '请在设置中开启麦克风', icon: 'none' })
    },
    fail: () => uni.showToast({ title: '无法打开设置，请在微信真机中操作', icon: 'none' }),
  })
}
watch(() => props.disabled, value => { if (value) cancel() })
onBeforeUnmount(() => recorder.dispose())
defineExpose({ cancel })
</script>

<template>
  <view class="voice-input" :class="{'is-embedded':embedded}">
    <button class="hold-to-talk" :class="{'is-holding':overlay}" :disabled="disabled||state.phase==='transcribing'" aria-label="按住说话" @touchstart.stop.prevent="start" @touchmove.stop.prevent="recorder.move(touchY($event)||0)" @touchend.stop.prevent="end" @touchcancel.stop.prevent="recorder.cancel()" @contextmenu.prevent>{{label}}</button>
    <view v-if="progressVisible" class="voice-progress" role="status" aria-live="polite"><view class="voice-progress-copy"><text>{{progressLabel}}</text><text v-if="state.phase==='transcribing'" class="voice-progress-hint">取消后可切换文字输入</text></view><button v-if="canCancel" class="voice-progress-cancel" @click.stop="cancel">{{cancelLabel}}</button></view>
    <view v-if="state.error" class="voice-error"><text>{{state.error}}</text><button v-if="state.hasAudio" :disabled="disabled||busy" @click="recorder.retry()">重试识别</button><button v-if="state.permissionDenied" class="permission-button" @click="openSettings">去开启麦克风</button><text v-if="state.permissionDenied" class="permission-hint">开启后，返回这里按住说话</text></view>
    <view v-if="overlay" class="voice-recording-overlay" :class="{'is-canceling':state.canceling}" aria-live="polite">
      <view class="recording-wash"></view><view class="recording-glow"></view>
      <view class="recording-content"><text class="recording-prompt">{{prompt}}</text><view class="voice-waveform"><view v-for="(level,index) in levels" :key="index" class="wave-bar" :style="{height:(4+level*26)+'px',opacity:0.32+level*0.68}"></view></view></view>
    </view>
  </view>
</template>

<style scoped>
.voice-input{flex:1;width:100%;min-width:0}.voice-input .hold-to-talk{width:100%;height:68rpx;display:flex;align-items:center;justify-content:center;font-size:30rpx;font-weight:500;user-select:none;-webkit-user-select:none;touch-action:none;background:transparent;border:0;border-radius:12rpx}.hold-to-talk::after{border:0}.hold-to-talk.is-holding{color:transparent}.hold-to-talk[disabled]{opacity:.5}
.voice-input.is-embedded{height:44px;border:0;border-radius:0;background:transparent}.is-embedded .hold-to-talk{height:44px;min-height:44px;border:0;background:transparent;font-size:16px;font-weight:500;color:#292c32}.is-embedded .hold-to-talk.is-holding{color:transparent}
.voice-progress{position:absolute;z-index:81;left:0;right:0;bottom:calc(100% + 12rpx);display:flex;align-items:center;gap:12px;padding:8px 12px;border:1px solid var(--ui-line,#e5e5ea);border-radius:14px;background:var(--ui-surface,#fff);color:var(--ui-text,#35343f);font-size:13px;line-height:1.6}.voice-progress-copy{flex:1;min-width:0;overflow-wrap:anywhere}.voice-progress-copy>text{display:block}.voice-progress-hint{color:var(--ui-muted,#74717f);font-size:12px}.voice-progress-cancel{display:flex;align-items:center;justify-content:center;flex:none;min-width:64px;min-height:44px;margin:0;padding:6px 10px;border:0;border-radius:10px;background:var(--ui-accent-soft,#eef0f2);color:var(--ui-text,#35343f);font-size:13px;line-height:1.5}.voice-progress-cancel:after{border:0}.voice-progress-cancel:active{background:var(--ui-line,#e5e5ea)}
.voice-error{position:absolute;left:0;right:0;bottom:calc(100% + 12rpx);padding:20rpx 24rpx;border:1rpx solid #e5e5ea;border-radius:20rpx;background:#fff;font-size:25rpx;line-height:1.6;color:#63636b;box-shadow:0 8rpx 28rpx rgba(0,0,0,.06)}.voice-error>text{display:block}.voice-error button{display:inline-block;min-height:64rpx;margin-right:24rpx;font-size:25rpx;color:#292a2e;background:transparent}.voice-error button::after{border:0}
.voice-recording-overlay{position:fixed;left:0;right:0;bottom:0;height:460rpx;padding-bottom:env(safe-area-inset-bottom);z-index:80;pointer-events:none;color:#fff}.recording-wash{position:absolute;left:0;right:0;bottom:0;height:720rpx;background:linear-gradient(to bottom,rgba(255,255,255,0),rgba(255,255,255,.94) 28%,rgba(255,255,255,.98) 100%)}.recording-glow{position:absolute;left:0;right:0;bottom:0;height:620rpx;background:radial-gradient(ellipse at 72% 100%,rgba(20,106,244,.97) 0%,rgba(35,136,248,.88) 31%,rgba(61,179,249,.58) 56%,rgba(105,205,252,.15) 72%,rgba(255,255,255,0) 88%)}.recording-content{position:absolute;left:0;right:0;bottom:calc(env(safe-area-inset-bottom) + 70rpx);display:flex;flex-direction:column;align-items:center;gap:54rpx}.recording-prompt{font-size:28rpx;letter-spacing:1rpx;color:rgba(255,255,255,.82)}.voice-waveform{height:60px;display:flex;align-items:center;justify-content:center;gap:3px;width:70%;max-width:360px}.wave-bar{width:3px;min-width:2px;flex-shrink:1;border-radius:3px;background:#fff;transition:height 90ms linear,opacity 90ms linear}.is-canceling .recording-glow{background:radial-gradient(ellipse at 50% 100%,rgba(223,82,110,.98) 0%,rgba(236,119,147,.84) 40%,rgba(246,185,198,.25) 70%,rgba(255,255,255,0) 88%)}.is-canceling .recording-prompt{color:#fff}
.voice-error .permission-button{display:flex;align-items:center;justify-content:center;width:100%;min-height:80rpx;margin:20rpx 0 0;padding:16rpx 24rpx;border-radius:16rpx;background:#292a2e;color:#fff;font-size:28rpx;font-weight:500;line-height:1.4;box-sizing:border-box}.voice-error .permission-hint{margin-top:12rpx;font-size:25rpx;color:#767680}</style>
