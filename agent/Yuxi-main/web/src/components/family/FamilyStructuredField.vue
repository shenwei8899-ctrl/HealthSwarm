<template>
  <div class="structured-field">
    <a-select
      v-if="definition.array"
      :value="listState(modelValue)"
      :options="[
        { value: 'unknown', label: '未知 / 待补充' },
        { value: 'none', label: '已确认无' },
        { value: 'known', label: '有记录' }
      ]"
      :aria-label="profileLabels[fieldKey] + '记录状态'"
      @change="setState"
    />
    <div v-for="(record, index) in records" :key="index" class="fact-record">
      <div v-for="field in definition.fields" :key="field.key" class="fact-input">
        <label>{{ field.label }}</label>
        <a-select
          v-if="field.options"
          :value="record[field.key]"
          :aria-label="profileLabels[fieldKey] + ' ' + field.label"
          :options="Object.entries(field.options).map(([value, label]) => ({ value, label }))"
          @change="update(index, field.key, $event)"
        />
        <a-input
          v-else
          :value="record[field.key]"
          :type="field.type === 'date' ? 'date' : 'text'"
          :aria-label="profileLabels[fieldKey] + ' ' + field.label"
          :maxlength="500"
          @update:value="update(index, field.key, $event || null)"
        />
      </div>
      <a-button v-if="definition.array" danger type="link" @click="remove(index)"
        >移除此条</a-button
      >
    </div>
    <a-button v-if="definition.array" type="dashed" @click="add">添加记录</a-button>
    <p class="muted">填写已知事实及来源；未核对的信息可留空。</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { listState, profileLabels, structuredDefinitions } from '@/utils/familyArchives'
const props = defineProps({
  fieldKey: { type: String, required: true },
  modelValue: { type: [Array, Object], default: null }
})
const emit = defineEmits(['update:modelValue'])
const definition = computed(() => structuredDefinitions[props.fieldKey])
const records = computed(() =>
  definition.value.array ? props.modelValue || [] : [props.modelValue || {}]
)
function blank() {
  return Object.fromEntries(
    definition.value.fields.map((field) => [
      field.key,
      field.options
        ? Object.keys(field.options).includes('unknown')
          ? 'unknown'
          : Object.keys(field.options)[0]
        : null
    ])
  )
}
function update(index, key, value) {
  if (definition.value.array) {
    const rows = JSON.parse(JSON.stringify(props.modelValue || []))
    rows[index] = { ...rows[index], [key]: value }
    emit('update:modelValue', rows)
  } else emit('update:modelValue', { ...(props.modelValue || {}), [key]: value })
}
function add() {
  emit('update:modelValue', [...(props.modelValue || []), blank()])
}
function remove(index) {
  emit(
    'update:modelValue',
    props.modelValue.filter((_, i) => i !== index)
  )
}
function setState(state) {
  emit('update:modelValue', state === 'none' ? [] : state === 'known' ? [blank()] : null)
}
</script>

<style scoped>
.fact-record {
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  padding: 12px;
  margin: 12px 0;
}
.fact-input {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}
.fact-input label {
  font-size: 12px;
  color: var(--gray-600);
}
.structured-field > .ant-select {
  width: 100%;
}
</style>
