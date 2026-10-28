<script setup>
import { computed, ref } from 'vue'
import { parseAiAnswer } from '../utils/ai-answer.js'

const props = defineProps({
  text: { type: String, default: '' },
  citations: { type: Array, default: () => [] },
  streaming: { type: Boolean, default: false },
})
const answer = computed(() => parseAiAnswer(props.text, { citations: props.citations, streaming: props.streaming }))
const sourcesOpen = ref(false)
function segmentClass(segment) { return { 'answer-strong': segment.strong, 'answer-emphasis': segment.emphasis, 'answer-inline-code': segment.code } }
</script>

<template>
  <view class="ai-answer" :class="{ 'is-streaming': streaming }">
    <view v-for="(block, index) in answer.blocks" :key="index" class="answer-block" :class="'answer-' + block.type">
      <template v-if="block.type === 'heading' || block.type === 'paragraph' || block.type === 'quote'">
        <text class="answer-copy" :class="{ 'answer-heading-small': block.level > 2 }" :selectable="!streaming"><text v-for="(segment, segmentIndex) in block.segments" :key="segmentIndex" :class="segmentClass(segment)">{{ segment.text }}</text></text>
      </template>
      <view v-else-if="block.type === 'list'" class="answer-list-items">
        <view v-for="(item, itemIndex) in block.items" :key="itemIndex" class="answer-list-item" :class="'answer-indent-' + item.level">
          <view class="answer-list-marker" :class="{ 'answer-list-number': item.marker }"><text v-if="item.marker">{{ item.marker }}</text><view v-else class="answer-list-dot" /></view>
          <text class="answer-list-copy" :selectable="!streaming"><text v-for="(segment, segmentIndex) in item.segments" :key="segmentIndex" :class="segmentClass(segment)">{{ segment.text }}</text></text>
        </view>
      </view>
      <view v-else-if="block.type === 'table'" class="answer-table-cards">
        <view v-for="(row, rowIndex) in block.rows" :key="rowIndex" class="answer-table-row">
          <view v-for="(cell, cellIndex) in row" :key="cellIndex" class="answer-table-field">
            <text v-if="block.headers[cellIndex]?.length" class="answer-table-label"><text v-for="(segment, segmentIndex) in block.headers[cellIndex]" :key="segmentIndex">{{ segment.text }}</text></text>
            <text class="answer-table-value" :selectable="!streaming"><text v-for="(segment, segmentIndex) in cell" :key="segmentIndex" :class="segmentClass(segment)">{{ segment.text }}</text></text>
          </view>
        </view>
        <view v-if="!block.rows.length" class="answer-table-pending"><text v-for="(header, headerIndex) in block.headers" :key="headerIndex"><text v-if="headerIndex"> · </text><text v-for="(segment, segmentIndex) in header" :key="segmentIndex">{{ segment.text }}</text></text><text v-if="streaming">，正在整理内容</text></view>
      </view>
      <text v-else-if="block.type === 'code'" class="answer-code-copy" :selectable="!streaming">{{ block.text }}</text>
    </view>
    <view v-if="streaming" class="answer-writing" role="status" aria-label="正在生成回复"><view class="answer-writing-dot" /><text>正在为你整理</text></view>
    <view v-if="answer.sources.length && !streaming" class="answer-sources">
      <button class="answer-source-toggle" :aria-expanded="sourcesOpen" @click="sourcesOpen = !sourcesOpen"><text>参考资料 · {{ answer.sources.length }}</text><text>{{ sourcesOpen ? '收起 −' : '查看 ＋' }}</text></button>
      <view v-if="sourcesOpen" class="answer-source-list"><view v-for="(source, index) in answer.sources" :key="source" class="answer-source"><text class="answer-source-index">{{ index + 1 }}</text><text class="answer-source-title" selectable>{{ source }}</text></view></view>
    </view>
  </view>
</template>

<style scoped>
.ai-answer{width:100%;min-width:0;color:#29322f;font-size:29rpx;line-height:1.88;word-break:break-word;overflow-wrap:anywhere}
.answer-block+.answer-block{margin-top:25rpx}.answer-copy,.answer-code-copy{display:block;white-space:pre-wrap}.answer-strong{font-weight:600;color:#172b24}.answer-emphasis{color:#38574a}.answer-heading{margin-top:34rpx!important;padding-left:16rpx;border-left:6rpx solid #397b5b;font-size:32rpx;line-height:1.5;font-weight:600;color:#172b24}.answer-heading:first-child{margin-top:0!important}.answer-heading-small{font-size:29rpx}.answer-list-items{display:flex;flex-direction:column;gap:22rpx}.answer-list-item{display:flex;align-items:flex-start;gap:16rpx}.answer-list-marker{width:28rpx;min-width:28rpx;display:flex;justify-content:center;align-items:center;min-height:54rpx}.answer-list-dot{width:9rpx;height:9rpx;border-radius:50%;background:#54856a}.answer-list-number{margin-top:10rpx;height:34rpx;min-height:34rpx;background:#edf5ef;border-radius:11rpx;color:#397253;font-size:23rpx;font-weight:600}.answer-list-copy{flex:1;min-width:0;white-space:pre-wrap}.answer-indent-1{margin-left:30rpx}.answer-indent-2{margin-left:48rpx}.answer-quote{padding:20rpx 24rpx;border-radius:18rpx;background:#f3f7f4;color:#4b6256;font-size:27rpx}.answer-divider{height:1rpx;background:#eaf0eb;margin:30rpx 0}.answer-table-cards{display:flex;flex-direction:column;gap:16rpx}.answer-table-row{background:#f6f8f5;border:1rpx solid #e9eee8;border-radius:20rpx;padding:22rpx 24rpx;display:flex;flex-direction:column;gap:13rpx}.answer-table-field{display:flex;align-items:flex-start;gap:20rpx;min-width:0}.answer-table-label{width:132rpx;flex-shrink:0;color:#718075;font-size:25rpx;line-height:1.85}.answer-table-value{flex:1;min-width:0;white-space:pre-wrap;font-size:27rpx}.answer-table-field:first-child .answer-table-value{font-weight:600;color:#284c38}.answer-table-pending{color:#7e8a82;font-size:25rpx}.answer-code{padding:20rpx;border-radius:16rpx;background:#f5f7f5}.answer-code-copy,.answer-inline-code{font-family:monospace;font-size:26rpx}.answer-inline-code{padding:0 5rpx;background:#edf3ee;border-radius:5rpx}.answer-writing{display:flex;align-items:center;gap:12rpx;margin-top:20rpx;color:#819087;font-size:24rpx}.answer-writing-dot{height:11rpx;width:11rpx;border-radius:50%;background:#54856a;animation:answer-breathe 1.3s ease-in-out infinite}.answer-sources{border-top:1rpx solid #e9eee9;margin-top:30rpx;padding-top:10rpx}.answer-source-toggle{width:100%;min-height:64rpx;padding:8rpx 0;background:transparent;display:flex;align-items:center;justify-content:space-between;gap:20rpx;color:#7c887e;font-size:24rpx;line-height:1.5;text-align:left}.answer-source-toggle::after{border:0}.answer-source-toggle>text:last-child{white-space:nowrap;color:#55725e}.answer-source-list{display:flex;flex-direction:column;gap:14rpx;padding:8rpx 0 10rpx}.answer-source{display:flex;gap:14rpx;font-size:24rpx;line-height:1.6;color:#6f7f72}.answer-source-index{flex-shrink:0;color:#9aa69b}.answer-source-title{min-width:0;word-break:break-word}@keyframes answer-breathe{0%,100%{opacity:.35}50%{opacity:1}}
@media(prefers-reduced-motion:reduce){.answer-writing-dot{animation:none}}
</style>
