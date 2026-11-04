<script setup>
defineProps({ state: { type: Object, required: true } })
defineEmits(['close', 'retry', 'revoke'])
</script>

<template>
 <view class="invite-mask">
  <view class="invite-backdrop" aria-hidden="true" @click="$emit('close')" @touchmove.stop.prevent/>
  <view class="invite-panel" role="dialog" aria-modal="true" aria-label="邀请家人">
   <view class="invite-grab"/>
   <view class="invite-heading"><view><text class="invite-eyebrow">一起照顾每一餐</text><text class="invite-title">邀请谁加入家庭？</text></view><button class="invite-close" aria-label="关闭邀请" @click="$emit('close')">×</button></view>
   <text v-if="state.busy" class="invite-note" role="status">正在准备邀请…</text>
   <view v-if="state.error" class="invite-error" role="alert"><text>{{state.error}}</text><button :disabled="state.busy||!!state.revoking" @click="$emit('retry')">重新准备</button></view>
   <scroll-view scroll-y class="invite-options">
    <view v-for="option in state.options" :key="option.key" class="invite-row" :class="{'invite-row-other':!option.member_id}">
     <button class="invite-person" :open-type="option.code?'share':undefined" :data-invite-key="option.key" :disabled="!option.code||!!state.revoking">
      <view class="invite-avatar" :class="{'is-other':!option.member_id}">{{option.member_id?option.name.slice(0,1):'＋'}}</view>
      <view class="invite-copy"><view class="invite-name"><text>{{option.name}}</text><text v-if="option.member_id" class="invite-status">待加入</text></view><text class="invite-description">{{option.member_id?'加入后，核对你已填写的资料':'加入后，自行填写资料'}}</text></view>
      <text class="invite-arrow">↗</text>
     </button>
     <view class="invite-row-footer">
      <text v-if="option.revoked" class="invite-revoked">原邀请已撤销</text><text v-else-if="option.expires_at" class="invite-expiry">{{new Date(option.expires_at).toLocaleDateString('zh-CN')}} 前有效</text>
      <button v-if="option.code" class="invite-revoke" :disabled="!!state.revoking" @click="$emit('revoke',option.key)">{{state.revoking===option.key?'正在撤销…':'撤销邀请'}}</button>
      <button v-else class="invite-revoke" :disabled="state.busy||!!state.revoking" @click="$emit('retry')">重新准备邀请</button>
     </view>
    </view>
   </scroll-view>
   <text class="invite-note">分享卡片不展示健康资料。家人接受后即可加入。</text>
   <button class="invite-cancel" @click="$emit('close')">取消</button>
  </view>
 </view>
</template>

<style scoped>
.invite-mask{position:fixed;inset:0;z-index:240;display:flex;align-items:flex-end;justify-content:center}
.invite-backdrop{position:absolute;inset:0;background:rgba(43,40,65,.25)}
.invite-panel{position:relative;box-sizing:border-box;width:100%;max-width:480px;max-height:88vh;padding:10px 23px calc(env(safe-area-inset-bottom) + 20px);border:1px solid rgba(255,255,255,.65);border-bottom:0;border-radius:36px 36px 0 0;background:radial-gradient(ellipse at 8% 0%,rgba(255,255,255,.65),transparent 54%),linear-gradient(145deg,#e4e8f9 0%,#eee7f5 48%,#e6f1ed 100%);color:#51485f;box-shadow:0 -8px 44px rgba(61,49,97,.09),inset 0 1px 0 rgba(255,255,255,.65)}
.invite-grab{width:36px;height:4px;margin:0 auto 24px;border-radius:4px;background:rgba(139,126,163,.3)}
.invite-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px}
.invite-eyebrow{display:block;margin-bottom:7px;color:#81738f;font-size:12px;font-weight:500;letter-spacing:1px}
.invite-title{display:block;font-size:23px;font-weight:700;line-height:1.4;letter-spacing:.3px}
.invite-close{display:flex;align-items:center;justify-content:center;width:40px;min-width:40px;height:40px;margin-right:-5px;border:1px solid rgba(255,255,255,.5);border-radius:50%;background:rgba(255,255,255,.27);color:#9283a2;font-size:26px;line-height:1}
.invite-close:after,.invite-person:after,.invite-revoke:after,.invite-cancel:after{border:0}
.invite-options{box-sizing:border-box;max-height:49vh;padding:3px 2px 5px}
.invite-row{position:relative;margin-bottom:14px;padding:4px 0 1px;border:1px solid rgba(255,255,255,.76);border-radius:30px;background:linear-gradient(135deg,rgba(255,255,255,.75),rgba(255,255,255,.32) 65%,rgba(232,236,255,.4));box-shadow:inset 0 1px 2px rgba(255,255,255,.8),inset 0 -1px 0 rgba(255,255,255,.3),0 7px 20px rgba(97,80,135,.035)}
.invite-row-other{background:linear-gradient(135deg,rgba(247,255,251,.78),rgba(255,255,255,.32) 64%,rgba(220,239,231,.46))}
.invite-person{display:flex;align-items:center;gap:13px;width:100%;margin:0;padding:19px 17px 12px;background:transparent;text-align:left;line-height:1.5;color:inherit}
.invite-avatar{display:flex;flex-shrink:0;align-items:center;justify-content:center;box-sizing:border-box;width:46px;height:46px;border:1px solid rgba(255,255,255,.76);border-radius:50%;background:radial-gradient(circle at 30% 20%,rgba(255,255,255,.9),transparent 52%),linear-gradient(145deg,#e3daf5,#f0eaf8);color:#967db0;font-size:20px;font-weight:600;box-shadow:inset 0 1px 2px rgba(255,255,255,.8),0 3px 10px rgba(131,110,161,.045)}
.is-other{background:radial-gradient(circle at 30% 20%,rgba(255,255,255,.9),transparent 52%),linear-gradient(145deg,#dbece5,#edf6f0);color:#799d8d;font-size:25px}
.invite-copy{flex:1;min-width:0}
.invite-name{display:flex;align-items:center;flex-wrap:wrap;gap:8px;color:#554362;font-size:18px;font-weight:700;line-height:1.45}
.invite-status{padding:2px 7px;border-radius:9px;background:rgba(154,129,181,.09);color:#89719c;font-size:10px;font-weight:600;line-height:1.5}
.invite-description{display:block;margin-top:6px;color:#7c6a88;font-size:12px;font-weight:500;line-height:1.7}
.invite-row-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:30px;margin:0 17px 9px 76px}
.invite-revoked,.invite-expiry{color:#93829e;font-size:10px;font-weight:500;line-height:1.6}
.invite-arrow{flex-shrink:0;color:#a184b6;font-size:22px;font-weight:600}
.invite-revoke{flex-shrink:0;min-height:32px;margin:0 -5px 0 auto;padding:3px 5px;width:auto;background:transparent;color:#877093;font-size:11px;font-weight:500;line-height:26px}
.invite-note{display:block;margin:17px 2px;color:#897795;font-size:11px;font-weight:500;line-height:1.8;text-align:center}
.invite-cancel{display:flex;align-items:center;justify-content:center;width:100%;min-height:46px;border:1px solid rgba(255,255,255,.65);border-radius:23px;background:linear-gradient(120deg,rgba(255,255,255,.5),rgba(238,231,247,.42));color:#796386;font-size:15px;font-weight:600;line-height:1.5;box-shadow:inset 0 1px 0 rgba(255,255,255,.55)}
.invite-error{padding:12px;margin-bottom:13px;border-radius:18px;background:rgba(247,232,230,.78);color:#9b6760;font-size:12px;line-height:1.7}
.invite-error button{margin-top:8px;font-size:12px}
.invite-person[disabled]{opacity:.55}
</style>
