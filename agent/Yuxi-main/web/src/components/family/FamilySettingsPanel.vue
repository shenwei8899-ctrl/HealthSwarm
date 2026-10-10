<template>
  <section>
    <div class="section-heading">
      <div>
        <h2>家庭共同生活安排</h2>
        <p class="muted">{{ family.name }} · 设置 v{{ family.version }}</p>
      </div>
      <a-button v-if="family.is_owner" @click="openEditor">编辑家庭设置</a-button>
    </div>
    <dl class="settings-grid">
      <div v-for="field in fields" :key="field.key">
        <dt>{{ field.label }}</dt>
        <dd>
          {{ family.settings?.[field.key] ?? '未填写'
          }}{{ field.unit && family.settings?.[field.key] != null ? field.unit : '' }}
        </dd>
      </div>
    </dl>
    <p class="muted">共同生活安排供家庭成员参考；配餐仍需确认当餐参与者、资料及适用规则。</p>
    <a-modal v-model:open="editing" title="家庭设置" :confirm-loading="saving" @ok="save">
      <a-form layout="vertical"
        ><a-form-item label="家庭名称" required
          ><a-input v-model:value="name" :maxlength="80" aria-label="家庭名称"
        /></a-form-item>
        <a-form-item v-for="field in fields" :key="field.key" :label="field.label">
          <a-input-number
            v-if="field.numeric"
            v-model:value="draft[field.key]"
            :min="field.min"
            :max="field.max"
            :aria-label="field.label"
          />
          <a-textarea
            v-else
            v-model:value="draft[field.key]"
            :maxlength="field.short ? 100 : 500"
            :aria-label="field.label"
            :rows="2"
          /> </a-form-item
      ></a-form>
      <a-alert v-if="error" type="error" :message="error" show-icon />
    </a-modal>
  </section>
</template>
<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { familyApi } from '@/apis/family_api'
const props = defineProps({ family: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const editing = ref(false),
  saving = ref(false),
  error = ref(''),
  name = ref(''),
  version = ref(1),
  draft = reactive({})
const fields = [
  { key: 'cook', label: '主要做饭人', short: true },
  { key: 'shopper', label: '主要采购人', short: true },
  { key: 'weekday_meals', label: '工作日 / 上学日用餐安排' },
  { key: 'weekend_meals', label: '周末用餐安排' },
  {
    key: 'cooking_minutes',
    label: '可接受的做饭时间',
    numeric: true,
    min: 1,
    max: 1440,
    unit: ' 分钟'
  },
  {
    key: 'daily_budget',
    label: '家庭每日餐饮预算',
    numeric: true,
    min: 0.01,
    max: 100000,
    unit: ' 元'
  },
  { key: 'shared_preferences', label: '家庭共同口味' }
]
defineExpose({ hasDraft: computed(() => editing.value) })
let generation = 0
function clear() {
  generation++
  editing.value = false
  saving.value = false
  error.value = ''
  name.value = ''
  for (const key of Object.keys(draft)) delete draft[key]
}
watch([() => props.family.id, () => props.family.is_owner], clear)
onBeforeUnmount(clear)
function openEditor() {
  name.value = props.family.name
  version.value = props.family.version
  for (const key of Object.keys(draft)) delete draft[key]
  Object.assign(draft, JSON.parse(JSON.stringify(props.family.settings || {})))
  error.value = ''
  editing.value = true
}
async function save() {
  if (!name.value.trim()) {
    error.value = '请填写家庭名称'
    return
  }
  const current = generation
  saving.value = true
  try {
    await familyApi.updateFamily(props.family.id, {
      expected_version: version.value,
      name: name.value.trim(),
      settings: Object.fromEntries(
        fields.map((f) => [f.key, draft[f.key] === '' ? null : (draft[f.key] ?? null)])
      )
    })
    if (current === generation) {
      editing.value = false
      emit('changed')
    }
  } catch (cause) {
    if (current === generation)
      error.value = cause.status === 409 ? '设置已有新版本，请重新打开编辑器核对' : cause.message
  } finally {
    if (current === generation) saving.value = false
  }
}
</script>
<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  margin: 24px 0;
}
dt {
  color: var(--gray-600);
  font-size: 13px;
}
dd {
  margin: 6px 0;
  overflow-wrap: anywhere;
}
@media (max-width: 640px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
