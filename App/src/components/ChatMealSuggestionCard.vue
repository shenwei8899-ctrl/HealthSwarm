<script setup>
import { computed } from 'vue'
import FoodImageSlot from './FoodImageSlot.vue'
import { chatFoodCover } from '../utils/chat-food-cover.js'

const props = defineProps({ meal: { type: Object, required: true }, animate: Boolean, delay: { type: Number, default: 0 }, streaming: Boolean })
const cover = computed(() => chatFoodCover(props.meal.dishes[0]))
</script>

<template>
  <view class="meal-suggestion" :class="['tone-' + meal.type, { 'is-entering': animate }]" :style="{ 'animation-delay': delay + 'ms' }">
    <view class="suggestion-heading"><view class="meal-light" /><text class="suggestion-title">{{ meal.label }}</text></view>
    <view class="suggestion-main">
      <view class="suggestion-foods">
        <text class="suggestion-first" :selectable="!streaming">{{ meal.dishes[0] }}</text>
        <text v-if="meal.dishes.length > 1" class="suggestion-companions" :selectable="!streaming">{{ meal.dishes.slice(1).join(' · ') }}</text>
      </view>
      <view class="suggestion-photo">
        <FoodImageSlot :src="cover?.src" :label="cover?.label || meal.dishes[0]" :width="88" :height="88" :radius="19" />
        <text class="suggestion-caption">{{ cover ? '菜品示意' : '配图待补充' }}</text>
      </view>
    </view>
    <view v-if="meal.notes.length" class="suggestion-notes">
      <view v-for="(note, index) in meal.notes" :key="index" class="suggestion-note">
        <text v-if="note.label" class="suggestion-note-label">{{ note.label }}</text>
        <text class="suggestion-note-copy" :selectable="!streaming">{{ note.text }}</text>
      </view>
    </view>
  </view>
</template>

<style scoped>
.meal-suggestion{--meal-ink:#91602e;position:relative;box-sizing:border-box;width:100%;padding:19px 19px 17px;border:1px solid rgba(255,255,255,.94);border-radius:26px;background:linear-gradient(125deg,#ffe3ae 0%,#fff4d6 54%,#ffe6d2 100%);box-shadow:inset 0 1px 0 rgba(255,255,255,.95),0 5px 16px rgba(117,88,57,.055);color:#33343a;white-space:normal}
.tone-lunch{--meal-ink:#a15f49;background:linear-gradient(125deg,#ffdccf 0%,#fff0e2 54%,#ffe9c7 100%)}
.tone-dinner{--meal-ink:#397c69;background:linear-gradient(125deg,#cceede 0%,#eaf8e9 54%,#def1f5 100%)}
.tone-snack{--meal-ink:#506f96;background:linear-gradient(125deg,#dbeaff 0%,#eff6ff 54%,#e2f5f1 100%)}
.suggestion-heading{display:flex;align-items:center;gap:9px;margin-bottom:12px;min-height:26px}
.meal-light{flex-shrink:0;width:9px;height:9px;border:3px solid rgba(255,255,255,.8);border-radius:50%;background:var(--meal-ink);box-shadow:0 0 0 1px rgba(255,255,255,.5)}
.suggestion-title{display:block;font-size:18px;line-height:1.45;font-weight:650;letter-spacing:.3px;color:#343630}
.suggestion-main{display:flex;align-items:center;gap:16px;min-width:0}
.suggestion-foods{flex:1;min-width:0;padding-bottom:12px}
.suggestion-first{display:block;font-size:17px;font-weight:600;line-height:1.55;overflow-wrap:anywhere;word-break:break-word}
.suggestion-companions{display:block;margin-top:7px;font-size:15px;font-weight:500;line-height:1.75;color:#484b48;overflow-wrap:anywhere;word-break:break-word}
.suggestion-photo{flex:0 0 88px;width:88px;align-self:flex-start}
.suggestion-caption{display:block;margin-top:5px;text-align:center;font-size:10px;font-weight:500;line-height:1.4;color:var(--meal-ink)}
.suggestion-notes{margin-top:11px;padding-top:12px;border-top:1px solid rgba(117,109,82,.13)}
.suggestion-note+.suggestion-note{margin-top:9px}
.suggestion-note-label{display:block;margin-bottom:3px;color:var(--meal-ink);font-size:11px;line-height:1.5;font-weight:600;letter-spacing:.5px}
.suggestion-note-copy{display:block;font-size:14px;line-height:1.75;font-weight:500;color:#50564d;white-space:pre-wrap;overflow-wrap:anywhere}
.is-entering{animation:meal-suggestion-appear 350ms cubic-bezier(.2,.7,.25,1) backwards}
@keyframes meal-suggestion-appear{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:350px){.meal-suggestion{padding:16px 15px;border-radius:23px}.suggestion-main{gap:12px}.suggestion-first{font-size:16px}.suggestion-companions{font-size:14px}}
@media(prefers-reduced-motion:reduce){.is-entering{animation:none}}
</style>
