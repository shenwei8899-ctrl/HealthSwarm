<script setup>
import { computed, ref, watch, getCurrentInstance, nextTick, onUnmounted } from 'vue'
import { parseAiAnswer } from '../utils/ai-answer.js'
import { chatMealAnswerBlocks } from '../utils/chat-meal-suggestions.js'
import { quoteLayout } from '../utils/reply-selection.js'
import { createStreamTextPresentation } from '../services/stream-text-presentation.js'

const props = defineProps({
  text: { type: String, default: '' },
  citations: { type: Array, default: () => [] },
  streaming: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
  quoteEnabled:Boolean, selectionActive:Boolean, selectionStart:Number, selectionEnd:Number, selectionViewport:Object, selectionRevision:Number,
})
const emit = defineEmits(['selectionPress','selectionGeometry','growth'])
const presentedText = ref('')
const textPresentation = createStreamTextPresentation({onChange(text){presentedText.value=text;emit('growth')}})
watch(()=>[props.text,props.streaming],()=>textPresentation.update(props.text,props.streaming),{immediate:true,flush:'sync'})
const answer = computed(() => parseAiAnswer(presentedText.value, { citations: props.citations, streaming: props.streaming }))
const displayBlocks = computed(() => chatMealAnswerBlocks(answer.value.blocks))
const quoteContent=computed(()=>quoteLayout(displayBlocks.value,props.selectionActive))
const instance=getCurrentInstance()
const segmentClass=s=>({'answer-strong':s.strong,'answer-emphasis':s.emphasis,'answer-inline-code':s.code})
const measuredChunks=ref([])
let pressTimer=null,pressPoint=null,measureGeneration=0
function eventPoint(event){const p=event.touches?.[0]||event;return{x:p.clientX??p.pageX,y:p.clientY??p.pageY}}
function cancelTextPress(){clearTimeout(pressTimer);pressTimer=null;pressPoint=null}
function startTextPress(event){if(!props.quoteEnabled||props.streaming)return;cancelTextPress();pressPoint=eventPoint(event);pressTimer=setTimeout(()=>{pressTimer=null;emit('selectionPress',{point:pressPoint,text:quoteContent.value.text})},500)}
function moveTextPress(event){if(pressPoint){const p=eventPoint(event);if(Math.hypot(p.x-pressPoint.x,p.y-pressPoint.y)>8)cancelTextPress()}}
let measurementTimer=null
async function measureSelection(active){
 const mine=++measureGeneration;if(!active){measuredChunks.value=[];return}
 await nextTick()
 // First locate text chunks; only visible chunks expand into individual glyphs.
 uni.createSelectorQuery().in(instance.proxy).selectAll('.selection-chunk').fields({rect:true,dataset:true},async chunks=>{
  if(!props.selectionActive||mine!==measureGeneration)return
  const viewport=props.selectionViewport||{top:0,bottom:uni.getWindowInfo().windowHeight}
  measuredChunks.value=(chunks||[]).filter(row=>row.bottom>=viewport.top-100&&row.top<=viewport.bottom+100).map(row=>Number(row.dataset.start))
  await nextTick()
  if(!props.selectionActive||mine!==measureGeneration)return
  const glyphs=new Map(quoteContent.value.leaves.flatMap(leaf=>(leaf.groups||[]).flatMap(group=>group.glyphs)).map(glyph=>[glyph.start,glyph]))
  const scrollTop=props.selectionViewport?.scrollTop||0
  uni.createSelectorQuery().in(instance.proxy).selectAll('.selection-glyph').fields({rect:true,size:true,dataset:true},rows=>{
   if(!props.selectionActive||mine!==measureGeneration)return
   emit('selectionGeometry',{rects:(rows||[]).map(row=>({...row,...glyphs.get(Number(row.dataset.start))})),scrollTop})
  }).exec()
 }).exec()
}
watch(()=>[props.selectionActive,props.selectionRevision],()=>{
 measureGeneration++;clearTimeout(measurementTimer)
 measurementTimer=setTimeout(()=>measureSelection(props.selectionActive),32)
},{flush:'post'})
onUnmounted(()=>{textPresentation.dispose();measureGeneration++;clearTimeout(measurementTimer);cancelTextPress()})
</script>

<template>
  <view class="ai-answer" :class="{ 'is-streaming': streaming, 'is-compact': compact }">
    <view v-for="(block, index) in quoteContent.blocks" :key="index" class="answer-block" :class="'answer-' + block.type">
      <template v-if="block.type === 'heading' || block.type === 'paragraph' || block.type === 'quote'">
        <text class="answer-copy" :class="{ 'answer-heading-small': block.level > 2 }" :selectable="!quoteEnabled && !streaming" :user-select="!quoteEnabled && !streaming" @touchstart="startTextPress" @touchmove="moveTextPress" @touchend="cancelTextPress" @touchcancel="cancelTextPress" @contextmenu.prevent>
 <template v-if="selectionActive"><text v-for="(group,groupIndex) in block.leaf.groups" :key="groupIndex" :class="segmentClass(group)"><text v-for="chunk in group.chunks" :key="chunk.start" class="selection-chunk" :class="{'selection-mark':chunk.start>=selectionStart && chunk.glyphs[chunk.glyphs.length-1].end<=selectionEnd}" :data-start="chunk.start"><template v-if="measuredChunks.includes(chunk.start)"><text v-for="glyph in chunk.glyphs" :key="glyph.start" class="selection-glyph" :data-start="glyph.start" :class="{'selection-mark':glyph.start>=selectionStart && glyph.end<=selectionEnd}">{{glyph.text}}</text></template><template v-else>{{chunk.text}}</template></text></text></template>
 <template v-else><text v-for="(segment,segmentIndex) in block.leaf.segments" :key="segmentIndex" :class="segmentClass(segment)">{{segment.text}}</text></template>
 </text>
      </template>
      <view v-else-if="block.type === 'list'" class="answer-list-items">
        <view v-for="(item, itemIndex) in block.items" :key="itemIndex" class="answer-list-item" :class="'answer-indent-' + item.level">
          <view class="answer-list-marker" :class="{ 'answer-list-number': item.marker }"><text v-if="item.marker">{{ item.marker }}</text><view v-else class="answer-list-dot" /></view>
          <text class="answer-list-copy" :selectable="!quoteEnabled && !streaming" :user-select="!quoteEnabled && !streaming" @touchstart="startTextPress" @touchmove="moveTextPress" @touchend="cancelTextPress" @touchcancel="cancelTextPress" @contextmenu.prevent>
 <template v-if="selectionActive"><text v-for="(group,groupIndex) in item.leaf.groups" :key="groupIndex" :class="segmentClass(group)"><text v-for="chunk in group.chunks" :key="chunk.start" class="selection-chunk" :class="{'selection-mark':chunk.start>=selectionStart && chunk.glyphs[chunk.glyphs.length-1].end<=selectionEnd}" :data-start="chunk.start"><template v-if="measuredChunks.includes(chunk.start)"><text v-for="glyph in chunk.glyphs" :key="glyph.start" class="selection-glyph" :data-start="glyph.start" :class="{'selection-mark':glyph.start>=selectionStart && glyph.end<=selectionEnd}">{{glyph.text}}</text></template><template v-else>{{chunk.text}}</template></text></text></template>
 <template v-else><text v-for="(segment,segmentIndex) in item.leaf.segments" :key="segmentIndex" :class="segmentClass(segment)">{{segment.text}}</text></template>
 </text>
        </view>
      </view>
      <view v-else-if="block.type === 'table'" class="answer-table-cards">
        <view v-for="(row, rowIndex) in block.rows" :key="rowIndex" class="answer-table-row">
          <view v-for="(cell, cellIndex) in row" :key="cellIndex" class="answer-table-field">
            <text v-if="block.headers[cellIndex]?.length" class="answer-table-label" :selectable="!quoteEnabled && !streaming" :user-select="!quoteEnabled && !streaming" @touchstart="startTextPress" @touchmove="moveTextPress" @touchend="cancelTextPress" @touchcancel="cancelTextPress" @contextmenu.prevent>
 <template v-if="selectionActive"><text v-for="(group,groupIndex) in block.quoteFields[rowIndex][cellIndex].header.groups" :key="groupIndex" :class="segmentClass(group)"><text v-for="chunk in group.chunks" :key="chunk.start" class="selection-chunk" :class="{'selection-mark':chunk.start>=selectionStart && chunk.glyphs[chunk.glyphs.length-1].end<=selectionEnd}" :data-start="chunk.start"><template v-if="measuredChunks.includes(chunk.start)"><text v-for="glyph in chunk.glyphs" :key="glyph.start" class="selection-glyph" :data-start="glyph.start" :class="{'selection-mark':glyph.start>=selectionStart && glyph.end<=selectionEnd}">{{glyph.text}}</text></template><template v-else>{{chunk.text}}</template></text></text></template>
 <template v-else><text v-for="(segment,segmentIndex) in block.quoteFields[rowIndex][cellIndex].header.segments" :key="segmentIndex" :class="segmentClass(segment)">{{segment.text}}</text></template>
 </text>
            <text class="answer-table-value" :selectable="!quoteEnabled && !streaming" :user-select="!quoteEnabled && !streaming" @touchstart="startTextPress" @touchmove="moveTextPress" @touchend="cancelTextPress" @touchcancel="cancelTextPress" @contextmenu.prevent>
 <template v-if="selectionActive"><text v-for="(group,groupIndex) in block.quoteFields[rowIndex][cellIndex].value.groups" :key="groupIndex" :class="segmentClass(group)"><text v-for="chunk in group.chunks" :key="chunk.start" class="selection-chunk" :class="{'selection-mark':chunk.start>=selectionStart && chunk.glyphs[chunk.glyphs.length-1].end<=selectionEnd}" :data-start="chunk.start"><template v-if="measuredChunks.includes(chunk.start)"><text v-for="glyph in chunk.glyphs" :key="glyph.start" class="selection-glyph" :data-start="glyph.start" :class="{'selection-mark':glyph.start>=selectionStart && glyph.end<=selectionEnd}">{{glyph.text}}</text></template><template v-else>{{chunk.text}}</template></text></text></template>
 <template v-else><text v-for="(segment,segmentIndex) in block.quoteFields[rowIndex][cellIndex].value.segments" :key="segmentIndex" :class="segmentClass(segment)">{{segment.text}}</text></template>
 </text>
          </view>
        </view>
        <view v-if="!block.rows.length" class="answer-table-pending"><text v-for="(header, headerIndex) in block.headers" :key="headerIndex"><text v-if="headerIndex"> · </text><text v-for="(segment, segmentIndex) in header" :key="segmentIndex">{{ segment.text }}</text></text><text v-if="streaming">，正在整理内容</text></view>
      </view>
      <text v-else-if="block.type === 'code'" class="answer-code-copy" :selectable="!quoteEnabled && !streaming" :user-select="!quoteEnabled && !streaming" @touchstart="startTextPress" @touchmove="moveTextPress" @touchend="cancelTextPress" @touchcancel="cancelTextPress" @contextmenu.prevent>
 <template v-if="selectionActive"><text v-for="(group,groupIndex) in block.leaf.groups" :key="groupIndex" :class="segmentClass(group)"><text v-for="chunk in group.chunks" :key="chunk.start" class="selection-chunk" :class="{'selection-mark':chunk.start>=selectionStart && chunk.glyphs[chunk.glyphs.length-1].end<=selectionEnd}" :data-start="chunk.start"><template v-if="measuredChunks.includes(chunk.start)"><text v-for="glyph in chunk.glyphs" :key="glyph.start" class="selection-glyph" :data-start="glyph.start" :class="{'selection-mark':glyph.start>=selectionStart && glyph.end<=selectionEnd}">{{glyph.text}}</text></template><template v-else>{{chunk.text}}</template></text></text></template>
 <template v-else><text v-for="(segment,segmentIndex) in block.leaf.segments" :key="segmentIndex" :class="segmentClass(segment)">{{segment.text}}</text></template>
 </text>
    </view>
    <view v-if="streaming&&!compact" class="answer-writing" role="status" aria-label="正在生成回复"><view class="answer-writing-dot" /><text>正在为你整理</text></view>

  </view>
</template>
<style scoped>
.selection-glyph{user-select:none;-webkit-user-select:none}.selection-mark{background:#dcd0f1;color:inherit}


.ai-answer{width:100%;min-width:0;color:var(--ui-text);font-size:30rpx;line-height:1.8;word-break:break-word;overflow-wrap:anywhere}.answer-block+.answer-block{margin-top:28rpx}.answer-copy,.answer-code-copy{display:block;white-space:pre-wrap}.answer-strong{font-weight:500;color:inherit}.answer-emphasis{color:#62557f}.answer-heading{margin-top:34rpx!important;font-size:33rpx;line-height:1.6;font-weight:500}.answer-heading:first-child{margin-top:0!important}.answer-heading-small{font-size:30rpx}.answer-list-items{display:flex;flex-direction:column;gap:24rpx}.answer-list-item{display:flex;align-items:flex-start;gap:14rpx}.answer-list-marker{width:26rpx;min-width:26rpx;display:flex;justify-content:center;align-items:center;min-height:54rpx}.answer-list-dot{width:7rpx;height:7rpx;border-radius:50%;background:#a59abf}.answer-list-number{margin-top:9rpx;height:36rpx;min-height:36rpx;background:var(--ui-accent-soft);border-radius:10rpx;color:#706083;font-size:23rpx}.answer-list-copy{flex:1;min-width:0;white-space:pre-wrap}.answer-indent-1{margin-left:28rpx}.answer-indent-2{margin-left:44rpx}.answer-quote{padding:22rpx 24rpx;border-radius:20rpx;background:var(--ui-soft);color:#696273;font-size:28rpx}.answer-divider{height:1rpx;background:var(--ui-line);margin:28rpx 0}.answer-table-cards{display:flex;flex-direction:column;gap:16rpx}.answer-table-row{background:var(--ui-soft);border-radius:22rpx;padding:24rpx;display:flex;flex-direction:column;gap:14rpx}.answer-table-field{display:flex;align-items:flex-start;gap:18rpx;min-width:0}.answer-table-label{width:132rpx;flex-shrink:0;color:var(--ui-muted);font-size:25rpx;line-height:1.8}.answer-table-value{flex:1;min-width:0;white-space:pre-wrap;font-size:28rpx}.answer-table-field:first-child .answer-table-value{font-weight:500}.answer-table-pending{color:var(--ui-muted);font-size:25rpx}.answer-code{padding:20rpx;border-radius:18rpx;background:var(--ui-soft)}.answer-code-copy,.answer-inline-code{font-family:monospace;font-size:26rpx}.answer-inline-code{padding:0 5rpx;background:var(--ui-soft);border-radius:5rpx}.answer-writing{display:flex;align-items:center;gap:12rpx;margin-top:20rpx;color:var(--ui-muted);font-size:24rpx}.answer-writing-dot{height:9rpx;width:9rpx;border-radius:50%;background:var(--ui-accent)}
.is-compact{font-size:16px;line-height:1.75}.is-compact .answer-block+.answer-block{margin-top:16px}.is-compact .answer-heading{font-size:17px;margin-top:20px!important}.is-compact .answer-heading-small{font-size:16px}.is-compact .answer-list-items{gap:14px}.is-compact .answer-list-item{gap:8px}.is-compact .answer-list-marker{width:14px;min-width:14px;min-height:28px}.is-compact .answer-list-dot{width:4px;height:4px}.is-compact .answer-list-number{height:20px;min-height:20px;margin-top:4px;border-radius:6px;font-size:12px}.is-compact .answer-quote{padding:12px 14px;border-radius:12px;font-size:15px}.is-compact .answer-table-row{padding:14px;border-radius:14px}.is-compact .answer-table-field{gap:10px}.is-compact .answer-table-label{width:68px;font-size:13px}.is-compact .answer-table-value{font-size:14px}.is-compact .answer-code-copy,.is-compact .answer-inline-code{font-size:13px}.is-compact .answer-divider{margin:18px 0}
@media(max-width:350px){.is-compact{font-size:15px}}

</style>
