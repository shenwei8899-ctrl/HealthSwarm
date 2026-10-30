<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AppNavBar from './AppNavBar.vue'
const props=defineProps({title:String,heading:String,description:String,scrollTop:{type:Number,default:0}})
defineEmits(['back'])
const navHeight=ref(56),keyboardOpen=ref(false)
// The hero keeps its document height: scrolling cannot feed back into layout.
const progress=computed(()=>Math.max(0,Math.min(1,props.scrollTop/88)))
function keyboard(e){keyboardOpen.value=Number(e.height||e.detail?.height||0)>0}
onMounted(()=>{
  // #ifdef MP-WEIXIN
  try{const info=uni.getWindowInfo?.()||uni.getSystemInfoSync();navHeight.value=(info.statusBarHeight||24)+50}catch{}
  uni.onKeyboardHeightChange?.(keyboard)
  // #endif
})
onUnmounted(()=>{uni.offKeyboardHeightChange?.(keyboard)})
</script>
<template>
 <view class="profile-layout" :style="{'--profile-nav-height':navHeight+'px'}">
  <view class="profile-nav" :class="{'is-collapsed':progress>.9}">
   <AppNavBar><view class="nav-row"><button class="profile-back" aria-label="返回" @click="$emit('back')">‹</button><text class="nav-title" :style="{opacity:progress}">{{title}}</text><view class="profile-nav-action"><slot name="action"/></view></view></AppNavBar>
  </view>
  <view class="profile-nav-spacer"/>
  <view class="profile-hero"><view :style="{opacity:1-progress,transform:'translateY('+(-progress*12)+'px)'}"><text class="profile-brand"><text class="profile-brand-dot"/>家庭营养师</text><text class="profile-heading">{{heading}}</text><text class="profile-description">{{description}}</text></view></view>
  <view id="profile-form-panel" class="profile-panel">
   <view class="profile-sticky"><slot name="navigation"/></view>
   <view class="profile-body"><slot/></view>
  </view>
  <view v-if="$slots.footer" class="profile-footer" :class="{'keyboard-open':keyboardOpen}"><slot name="footer"/></view>
 </view>
</template>
<style scoped>
.profile-layout{--form-accent:#7660bc;--form-tint:#f1edf9;--form-line:#eeecf2;--form-text:#292633;min-height:100vh;max-width:480px;margin:0 auto;background:#f5f5fa;color:var(--form-text);font-weight:500}
.profile-nav{position:fixed;top:0;left:0;right:0;z-index:40;padding:0 20px;background:#f5f5fa}.profile-nav.is-collapsed{background:#fff;border-bottom:1px solid var(--form-line)}.profile-nav-spacer{height:var(--profile-nav-height)}.profile-back{display:flex;align-items:center;justify-content:center;min-width:44px;height:44px;margin-left:-10px;font-size:33px;color:#51495f}.profile-nav-action{margin-left:auto;color:var(--form-accent);font-size:14px}.profile-nav-action :deep(button){min-height:44px;color:var(--form-accent);font-size:14px;font-weight:500}
.profile-hero{height:119px;box-sizing:border-box;padding:7px 24px 20px}.profile-brand{display:flex;align-items:center;gap:6px;color:#8c7ba8;font-size:11px;line-height:18px}.profile-brand-dot{width:5px;height:5px;background:#9a85ca;border-radius:50%}.profile-heading{display:block;margin:8px 0 5px;font-size:27px;font-weight:600;line-height:1.4;letter-spacing:.2px}.profile-description{display:block;font-size:13px;line-height:1.6;color:#85808e}
.profile-panel{position:relative;min-height:calc(100vh - var(--profile-nav-height));background:#fff;border-radius:26px 26px 0 0}.profile-sticky{position:sticky;top:var(--profile-nav-height);z-index:25;padding:14px 20px;background:#fff;border-radius:26px 26px 0 0}.profile-body{padding:7px 22px calc(env(safe-area-inset-bottom) + 116px)}.profile-footer{position:fixed;z-index:35;left:0;right:0;bottom:0;display:flex;gap:12px;padding:14px 22px calc(env(safe-area-inset-bottom) + 16px);background:rgba(255,255,255,.98);border-top:1px solid var(--form-line)}.profile-footer.keyboard-open{display:none}.profile-footer :deep(button){flex:1;min-height:48px;border:0;border-radius:15px;background:var(--form-accent);color:#fff;font-size:16px;font-weight:500}.profile-footer :deep(.form-cancel){flex:0 0 80px;background:#f2f0f6;color:#746982}
:deep(.profile-tabs){display:flex;gap:5px;padding:4px;background:#f5f4f8;border-radius:14px}:deep(.profile-tabs button){display:flex;align-items:center;justify-content:center;gap:5px;flex:1;min-width:0;min-height:39px;padding:7px 3px;border-radius:11px;color:#89818f;font-size:12px;font-weight:500;line-height:1.4}:deep(.profile-tabs button.active){background:#fff;color:var(--form-accent);box-shadow:0 1px 4px rgba(66,45,95,.05)}:deep(.step-number){display:flex;align-items:center;justify-content:center;width:17px;height:17px;flex-shrink:0;border-radius:50%;background:#e9e5f0;font-size:10px;color:#9c91ad}:deep(.active .step-number),:deep(.complete .step-number){background:#e8dff6;color:#765ca6}
:deep(.form-section-title){display:block;margin:5px 0 16px;font-size:16px;font-weight:600}:deep(.form-note){display:block;margin:12px 0;font-size:12px;line-height:1.7;color:#908796}:deep(.form-notice){padding:12px 14px;margin:0 0 18px;border-radius:13px;background:#f6f2fa;color:#7a648c;font-size:12px;line-height:1.8}:deep(.form-notice button){min-height:40px;color:#7660bc;font-size:13px}:deep(.form-block){margin-bottom:26px}:deep(.form-error){display:block;color:#a45f65;font-size:12px;line-height:1.7;margin:8px 0}
:deep(.field-card){padding:0;margin:0 0 26px;border:0;background:transparent;box-shadow:none}:deep(.section-title),:deep(.card-title){font-size:16px;font-weight:600;color:#393240}:deep(.label),:deep(.field-label){font-size:13px;color:#807786}:deep(.field-input),:deep(.custom-input){box-sizing:border-box;width:100%;min-height:47px;padding:0 14px;border:1px solid transparent;border-radius:12px;background:#f6f5f8;color:#393240;font-size:15px;font-weight:500}:deep(.chips){gap:9px;margin:14px 0}:deep(.chips button){min-height:42px;padding:10px 14px;border:1px solid #efedf3;border-radius:12px;background:#f7f6f9;color:#6d6477;font-size:13px}:deep(.chips button.active){border-color:#c2afd9;background:#f0eaf8;color:#7655a1}:deep(.helper),:deep(.support-copy){font-size:12px;line-height:1.7;color:#918797}:deep(.management){padding:12px;background:#f7f5f9;border-radius:12px}:deep(.text-area){box-sizing:border-box;width:100%;padding:13px;border:1px solid #eee9f3;border-radius:12px;background:#f7f5f9;color:#393240;font-size:14px}:deep(.additional-fields){padding:0;margin:0;border:0;box-shadow:none}:deep(.health-option.chosen){border-color:#c2afd9;background:#f3eef9}:deep(.option-grid button.selected){border-color:#c2afd9;background:#f0eaf8;color:#7655a1}:deep(.health-card){margin-bottom:25px}:deep(.health-option){border-radius:12px}:deep(.chosen .radio-mark){background:#8c70b2;border-color:#8c70b2}:deep(.option-grid button){border-radius:12px}:deep(.field-row){min-height:50px}:deep(button[disabled]){opacity:.55}
/* #ifdef H5 */
.profile-nav,.profile-footer{left:50%;right:auto;transform:translateX(-50%);width:100%;max-width:480px;box-sizing:border-box}
/* #endif */
@media(max-width:350px){.profile-body{padding-left:18px;padding-right:18px}.profile-sticky{padding-left:16px;padding-right:16px}.profile-heading{font-size:25px}:deep(.profile-tabs button){font-size:11px}}
</style>
