<script setup>
defineProps({ servings: { type: Array, default: () => [] } })
</script>

<template>
  <view class="member-servings">
    <view class="serving-heading"><text>成员份量</text><text>熟食建议 · 估算</text></view>
    <text v-if="!servings.length" class="serving-note">这份餐单尚无成员份量规划，重新生成餐单后可查看。</text>
    <view v-for="person in servings" :key="person.member_id" class="serving-row">
      <view><text class="serving-name">{{ person.name }}</text><text>约 {{ person.cooked_grams }} 克</text></view>
      <text class="serving-description">{{ person.description }}</text>
    </view>
    <text v-if="servings.length" class="serving-note">原料分配用于备菜，成品按建议熟重分取。计划份量不等于实际摄入。</text>
  </view>
</template>

<style scoped>
.member-servings{margin:20px 0;padding:18px;border:1px solid var(--ui-bubble-line);border-radius:20px;background:var(--ui-bubble)}
.serving-heading,.serving-row>view{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.serving-heading{font-size:16px;font-weight:600}.serving-heading>text+text{font-size:11px;font-weight:400;color:var(--ui-muted)}
.serving-row{padding:13px 0;border-bottom:1px solid var(--ui-line)}.serving-row>view{font-size:14px}.serving-name{flex:1;min-width:0;font-weight:500;overflow-wrap:anywhere}.serving-row>view>text+text{flex:none;white-space:nowrap}
.serving-description,.serving-note{display:block;color:var(--ui-muted);font-size:12px;line-height:1.8;overflow-wrap:anywhere}.serving-description{margin-top:5px}.serving-note{margin-top:12px;font-size:11px}
</style>
