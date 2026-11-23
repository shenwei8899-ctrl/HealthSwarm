<script setup>
import { ref, watch } from 'vue'
const props=defineProps({open:Boolean,document:Object,mode:String,status:Object})
const emit=defineEmits(['confirm','close'])
const checked=ref(false)
watch(()=>[props.open,props.document?.version,props.document?.content_hash],()=>{checked.value=false})
function confirm(){if(checked.value)emit('confirm')}
</script>
<template>
 <!-- #ifdef H5 -->
 <Teleport to="body">
 <!-- #endif -->
 <!-- #ifdef MP-WEIXIN -->
 <root-portal :enable="true">
 <!-- #endif -->
 <view v-if="open&&document" class="notice-mask" @tap.self="$emit('close')" @touchmove.stop.prevent>
  <view class="notice-sheet" role="dialog" aria-modal="true" :aria-label="document.title" @tap.stop>
   <view class="notice-head"><view><text class="notice-eyebrow">家庭营养师 · 使用须知</text><text class="notice-title">{{document.title}}</text></view><button class="notice-close" aria-label="关闭声明" @tap="$emit('close')">×</button></view>
   <scroll-view class="notice-body" @touchmove.stop scroll-y :show-scrollbar="true">
    <text class="notice-version">版本 {{document.version}} · 生效日期 {{document.effective_date}}</text>
    <view v-for="(section,index) in document.sections" :key="index" class="notice-section"><text class="notice-section-title">{{section.title}}</text><text class="notice-copy" selectable>{{section.text}}</text></view>
    <text v-if="mode==='read'&&status?.acknowledged" class="notice-receipt">本账号已确认当前版本{{status.acknowledged_at?' · '+status.acknowledged_at.slice(0,10):''}}</text>
    <text v-else-if="mode==='read'&&status" class="notice-receipt">本账号尚未确认当前版本</text>
   </scroll-view>
   <view class="notice-footer">
    <checkbox-group v-if="mode!=='read'" @change="checked=$event.detail.value.includes('yes')"><label class="notice-check"><checkbox value="yes" :checked="checked" color="#8552ce"/><text>{{document.checkbox_text}}</text></label></checkbox-group>
    <button v-if="mode!=='read'" class="notice-confirm" :disabled="!checked" @tap="confirm">{{mode==='login'?'确认并继续登录':'确认并继续'}}</button>
    <button v-else class="notice-confirm" @tap="$emit('close')">关闭</button>
   </view>
  </view>
 </view>
 <!-- #ifdef MP-WEIXIN -->
 </root-portal>
 <!-- #endif -->
 <!-- #ifdef H5 -->
 </Teleport>
 <!-- #endif -->
</template>
<style scoped>
.notice-mask{position:fixed;inset:0;z-index:10000;display:flex;align-items:flex-end;justify-content:center;background:rgba(36,29,51,.48);color:#433b50;text-align:left;letter-spacing:0}
.notice-sheet{display:flex;flex-direction:column;width:100%;max-width:560px;height:86vh;height:86dvh;max-height:900px;box-sizing:border-box;border-radius:26px 26px 0 0;background:#fbf9ff;box-shadow:0 -12px 60px #30213f20;overflow:hidden}
.notice-head{display:flex;justify-content:space-between;gap:12px;flex-shrink:0;padding:24px 24px 16px;border-bottom:1px solid #eee8f5}.notice-eyebrow{display:block;font-size:11px;color:#8b7c9e;line-height:1.5}.notice-title{display:block;margin-top:6px;font-size:21px;line-height:1.5;font-weight:500;color:#49365d}
.notice-close{width:44px;min-width:44px;height:44px;min-height:44px;margin:-6px -12px 0 0;padding:0;border:0;background:transparent;font-size:29px;line-height:44px;color:#84768f}.notice-close:after,.notice-confirm:after{border:0}
.notice-body{flex:1;min-height:0;height:0;box-sizing:border-box}.notice-version{display:block;padding:18px 24px 0;font-size:11px;line-height:1.7;color:#8a7e96}.notice-section{padding:20px 24px 0}.notice-section:last-of-type{padding-bottom:24px}.notice-section-title{display:block;font-size:15px;line-height:1.6;font-weight:500;color:#674b85}.notice-copy{display:block;margin-top:8px;font-size:14px;line-height:1.95;overflow-wrap:anywhere}.notice-receipt{display:block;padding:0 24px 24px;font-size:12px;line-height:1.7;color:#80738d}
.notice-footer{flex-shrink:0;padding:16px 24px calc(18px + env(safe-area-inset-bottom));border-top:1px solid #eae3f2;background:#fff}.notice-check{display:flex;align-items:flex-start;gap:6px;font-size:12px;line-height:1.8;color:#6e607c}.notice-check checkbox{flex-shrink:0;transform:scale(.8);transform-origin:top left;width:23px;margin-top:2px}.notice-confirm{width:100%;min-height:48px;margin:14px 0 0;padding:12px;border-radius:16px;border:0;background:#8552ce;color:#fff;font-size:15px;line-height:1.6;font-weight:500}.notice-confirm[disabled]{background:#e9e2f1;color:#9c8eab}
@media(max-width:350px){.notice-head{padding:18px 18px 12px}.notice-title{font-size:19px}.notice-section{padding:16px 18px 0}.notice-version{padding-left:18px;padding-right:18px}.notice-copy{font-size:13px;line-height:1.8}.notice-footer{padding-left:18px;padding-right:18px}.notice-check{font-size:11px}}
</style>
