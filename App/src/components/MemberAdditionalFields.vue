<script setup>
import ArchiveField from './ArchiveField.vue'
import { profileFields, recordGroups, objectGroups } from '../services/family-archive-fields.js'
const props=defineProps({draft:Object,source:Object,editing:Boolean})
const represented=new Set(['sex','birth_date','height_cm','goal','doctor_instructions','allergens','avoidances'])
const visible=key=>props.source?.allowed_fields?.includes(key)
const disabled=key=>!props.editing||!props.source?.editable_fields?.includes(key)
function add(group){props.draft[group.key].push(Object.fromEntries(group.fields.map(f=>[f.key,f.type==='select'?f.options[0][0]:''])))}
</script>
<template><view class="card additional-fields"><text class="section-title">补充健康资料</text>
  <ArchiveField v-for="field in profileFields.filter(f=>!represented.has(f.key)&&visible(f.key))" :key="field.key" v-model="draft[field.key]" :field="field" :disabled="disabled(field.key)"/>
  <view v-for="group in recordGroups.filter(g=>visible(g.key))" :key="group.key"><text class="section-title">{{group.label}}</text><text v-if="!draft[group.key]?.length">尚未填写</text>
    <view v-for="(row,i) in draft[group.key]" :key="i"><ArchiveField v-for="field in group.fields" :key="field.key" v-model="row[field.key]" :field="field" :disabled="disabled(group.key)"/><button v-if="!disabled(group.key)" @click="draft[group.key].splice(i,1)">移除此项</button></view>
    <button v-if="!disabled(group.key)" class="secondary-button" @click="add(group)">添加{{group.label}}</button>
  </view>
  <view v-for="group in objectGroups.filter(g=>visible(g.key))" :key="group.key"><text class="section-title">{{group.label}}</text><ArchiveField v-for="field in group.fields" :key="field.key" v-model="draft[group.key][field.key]" :field="field" :disabled="disabled(group.key)"/></view>
</view></template>
<style scoped>.additional-fields{padding:28rpx;margin:22rpx 0}.section-title{display:block;margin:22rpx 0}text{font-size:26rpx;line-height:1.6}</style>
