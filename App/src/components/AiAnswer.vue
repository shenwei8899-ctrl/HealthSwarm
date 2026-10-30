<script setup>
import { computed, ref } from 'vue'
import { parseAiAnswer } from '../utils/ai-answer.js'

const props = defineProps({
  text: { type: String, default: '' },
  citations: { type: Array, default: () => [] },
  streaming: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})
const answer = computed(() => parseAiAnswer(props.text, { citations: props.citations, streaming: props.streaming }))
const sourcesOpen = ref(false)
function segmentClass(segment) { return { 'answer-strong': segment.strong, 'answer-emphasis': segment.emphasis, 'answer-inline-code': segment.code } }
</script>

<template>
  <view class="ai-answer" :class="{ 'is-streaming': streaming, 'is-compact': compact }">
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
    <view v-if="streaming&&!compact" class="answer-writing" role="status" aria-label="正在生成回复"><view class="answer-writing-dot" /><text>正在为你整理</text></view>
    <view v-if="answer.sources.length && !streaming" class="answer-sources">
      <button class="answer-source-toggle" :aria-expanded="sourcesOpen" @click="sourcesOpen = !sourcesOpen"><text>参考资料 · {{ answer.sources.length }}</text><text>{{ sourcesOpen ? '收起 −' : '查看 ＋' }}</text></button>
      <view v-if="sourcesOpen" class="answer-source-list"><view v-for="(source, index) in answer.sources" :key="source" class="answer-source"><text class="answer-source-index">{{ index + 1 }}</text><text class="answer-source-title" selectable>{{ source }}</text></view></view>
    </view>
  </view>
</template>
<style scoped>
.ai-answer{width:100%;min-width:0;color:var(--ui-text);font-size:30rpx;line-height:1.8;word-break:break-word;overflow-wrap:anywhere}.answer-block+.answer-block{margin-top:28rpx}.answer-copy,.answer-code-copy{display:block;white-space:pre-wrap}.answer-strong{font-weight:500;color:inherit}.answer-emphasis{color:#62557f}.answer-heading{margin-top:34rpx!important;font-size:33rpx;line-height:1.6;font-weight:500}.answer-heading:first-child{margin-top:0!important}.answer-heading-small{font-size:30rpx}.answer-list-items{display:flex;flex-direction:column;gap:24rpx}.answer-list-item{display:flex;align-items:flex-start;gap:14rpx}.answer-list-marker{width:26rpx;min-width:26rpx;display:flex;justify-content:center;align-items:center;min-height:54rpx}.answer-list-dot{width:7rpx;height:7rpx;border-radius:50%;background:#a59abf}.answer-list-number{margin-top:9rpx;height:36rpx;min-height:36rpx;background:var(--ui-accent-soft);border-radius:10rpx;color:#706083;font-size:23rpx}.answer-list-copy{flex:1;min-width:0;white-space:pre-wrap}.answer-indent-1{margin-left:28rpx}.answer-indent-2{margin-left:44rpx}.answer-quote{padding:22rpx 24rpx;border-radius:20rpx;background:var(--ui-soft);color:#696273;font-size:28rpx}.answer-divider{height:1rpx;background:var(--ui-line);margin:28rpx 0}.answer-table-cards{display:flex;flex-direction:column;gap:16rpx}.answer-table-row{background:var(--ui-soft);border-radius:22rpx;padding:24rpx;display:flex;flex-direction:column;gap:14rpx}.answer-table-field{display:flex;align-items:flex-start;gap:18rpx;min-width:0}.answer-table-label{width:132rpx;flex-shrink:0;color:var(--ui-muted);font-size:25rpx;line-height:1.8}.answer-table-value{flex:1;min-width:0;white-space:pre-wrap;font-size:28rpx}.answer-table-field:first-child .answer-table-value{font-weight:500}.answer-table-pending{color:var(--ui-muted);font-size:25rpx}.answer-code{padding:20rpx;border-radius:18rpx;background:var(--ui-soft)}.answer-code-copy,.answer-inline-code{font-family:monospace;font-size:26rpx}.answer-inline-code{padding:0 5rpx;background:var(--ui-soft);border-radius:5rpx}.answer-writing{display:flex;align-items:center;gap:12rpx;margin-top:20rpx;color:var(--ui-muted);font-size:24rpx}.answer-writing-dot{height:9rpx;width:9rpx;border-radius:50%;background:var(--ui-accent)}.answer-sources{border-top:1rpx solid var(--ui-line);margin-top:30rpx;padding-top:6rpx}.answer-source-toggle{width:100%;min-height:44px;padding:6rpx 0;background:transparent;display:flex;align-items:center;justify-content:space-between;gap:20rpx;color:var(--ui-muted);font-size:24rpx;line-height:1.6;text-align:left}.answer-source-toggle:after{border:0}.answer-source-toggle>text:last-child{white-space:nowrap;color:#706083}.answer-source-list{display:flex;flex-direction:column;gap:14rpx;padding:8rpx 0 10rpx}.answer-source{display:flex;gap:14rpx;font-size:24rpx;line-height:1.8;color:var(--ui-muted)}.answer-source-index{flex-shrink:0}.answer-source-title{min-width:0;word-break:break-word}
.is-compact{font-size:16px;line-height:1.75}.is-compact .answer-block+.answer-block{margin-top:16px}.is-compact .answer-heading{font-size:17px;margin-top:20px!important}.is-compact .answer-heading-small{font-size:16px}.is-compact .answer-list-items{gap:14px}.is-compact .answer-list-item{gap:8px}.is-compact .answer-list-marker{width:14px;min-width:14px;min-height:28px}.is-compact .answer-list-dot{width:4px;height:4px}.is-compact .answer-list-number{height:20px;min-height:20px;margin-top:4px;border-radius:6px;font-size:12px}.is-compact .answer-quote{padding:12px 14px;border-radius:12px;font-size:15px}.is-compact .answer-table-row{padding:14px;border-radius:14px}.is-compact .answer-table-field{gap:10px}.is-compact .answer-table-label{width:68px;font-size:13px}.is-compact .answer-table-value{font-size:14px}.is-compact .answer-sources{margin-top:18px}.is-compact .answer-source-toggle,.is-compact .answer-source{font-size:12px}.is-compact .answer-code-copy,.is-compact .answer-inline-code{font-size:13px}.is-compact .answer-divider{margin:18px 0}
@media(max-width:350px){.is-compact{font-size:15px}}
</style>
