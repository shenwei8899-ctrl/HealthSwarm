<script setup>
defineProps({ arrangement: { type: Object, required: true }, disabled: Boolean, family: Boolean })
defineEmits(['open','members','shop'])
const names={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
function dateLabel(value){const match=/^\d{4}-(\d{2})-(\d{2})$/.exec(value||'');return match ? `${Number(match[1])}月${Number(match[2])}日` : value}
</script>
<template>
  <view class="daily-arrangement-card">
    <view class="daily-heading"><text class="section-title">{{family?'家庭安排':'今日安排'}}</text><text class="arrangement-date">{{dateLabel(arrangement.date)}}</text></view>
    <view v-for="meal in arrangement.meals" :key="meal.type" class="daily-row">
      <text class="meal-label">{{names[meal.type]}}</text>
      <view class="meal-copy">
        <text class="dish-summary">{{meal.dishes.map(dish=>dish.name).join(' · ')}}</text>
        <view class="meal-actions">
          <button :disabled="disabled" class="people-button" :aria-label="names[meal.type]+'，'+meal.members.length+'人用餐，调整成员'" @click="$emit('members',meal)"><text>{{meal.members.length}}人用餐</text><text class="down-mark" /></button>
          <button class="meal-link" :disabled="disabled" @click="$emit('open',meal)"><text>查看本餐安排</text><text class="chevron">›</text></button>
        </view>
      </view>
    </view>
    <button class="shop-button" :disabled="disabled" @click="$emit('shop',arrangement)"><text>一键选购</text><text class="shop-arrow">→</text></button>
  </view>
</template>
<style scoped>
.daily-arrangement-card{margin:20px 0;padding:18px 18px 16px;background:var(--ui-surface);border:0;border-radius:var(--ui-radius);color:var(--ui-text)}.daily-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:6px}.daily-heading .section-title{font-size:19px;line-height:1.5;font-weight:500;color:var(--ui-text)}.arrangement-date{font-size:12px;color:#929292;white-space:nowrap}.daily-row{display:flex;align-items:flex-start;gap:14px;padding:16px 0 4px;min-width:0;border-bottom:1px solid var(--ui-line)}.daily-row:last-of-type{border:0}.meal-label{font-size:14px;line-height:1.8;flex-shrink:0;padding-top:1px;color:#666;min-width:28px}.meal-copy{flex:1;min-width:0}.dish-summary{display:block;font-size:16px;font-weight:400;line-height:1.75;color:var(--ui-text);overflow-wrap:anywhere}.meal-actions{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.people-button,.meal-link{display:flex;align-items:center;gap:6px;min-height:44px;background:transparent;color:var(--ui-muted);font-size:12px;padding:0;white-space:nowrap}.people-button:after,.meal-link:after{border:0}.people-button{justify-content:flex-start}.meal-link{justify-content:flex-end;color:#444}.down-mark{width:5px;height:5px;border-right:1px solid currentColor;border-bottom:1px solid currentColor;transform:rotate(45deg);margin-top:-3px}.chevron{font-size:18px;color:var(--ui-muted)}.shop-button{display:flex;align-items:center;justify-content:center;gap:20px;width:auto;min-width:146px;min-height:46px;padding:9px 18px;margin:13px 0 0 auto;background:var(--ui-accent);color:#fff;border-radius:14px;font-size:15px;line-height:1.5;font-weight:500}.shop-button:after{border:0}.shop-arrow{font-size:22px;font-weight:400}.daily-arrangement-card button[disabled]{opacity:.45}
@media(max-width:350px){.daily-arrangement-card{padding:16px}.daily-row{gap:12px}.dish-summary{font-size:15px}.meal-link,.people-button{font-size:12px}.meal-actions{gap:4px}.daily-heading .section-title{font-size:18px}}
</style>
