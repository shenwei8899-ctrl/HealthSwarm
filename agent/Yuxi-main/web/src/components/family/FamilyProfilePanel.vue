<template>
  <section class="profile-panel">
    <div class="section-heading">
      <div>
        <h2>
          {{ member.name }}<span class="muted"> · {{ member.relationship }}</span>
        </h2>
        <p class="muted">档案 v{{ member.version }} · {{ profileStatus(member) }}</p>
      </div>
      <div class="button-group">
        <a-button v-if="editableKeys.length" @click="openEditor">编辑档案</a-button>
        <a-button v-if="member.is_self && !member.confirmed" :loading="saving" @click="confirm"
          >确认当前档案</a-button
        >
      </div>
    </div>
    <a-alert
      v-if="member.missing_fields.length"
      type="warning"
      show-icon
      :message="'待补充：' + member.missing_fields.map((key) => profileLabels[key]).join('、')"
      description="关键字段缺失时不能进行对应的个体化营养评估。"
    />
    <a-empty
      v-if="!editableKeys.length"
      description="健康档案尚未授权。成员本人认领并授权后才可查看。"
    />
    <dl v-else class="profile-grid">
      <div v-for="key in editableKeys" :key="key">
        <dt>{{ profileLabels[key] }}</dt>
        <dd>{{ display(key, member.profile[key]) }}</dd>
      </div>
    </dl>
    <div v-if="editableKeys.length" class="section-footer">
      <a-button type="link" @click="showHistory">查看变更记录</a-button>
      <a-button type="link" @click="exportProfile">导出当前可见档案</a-button>
      <span class="muted">未填写与明确“无”分别保留</span>
    </div>
    <a-modal
      v-model:open="editing"
      title="编辑成员健康档案"
      :confirm-loading="saving"
      @ok="save"
      :width="680"
    >
      <a-alert
        class="form-note"
        type="info"
        show-icon
        message="仅维护当前授权字段。保存后形成新版本，由本人重新确认。"
      />
      <a-form layout="vertical" :model="draft" name="family-profile">
        <div class="form-grid">
          <a-form-item
            v-for="key in editableKeys"
            :key="key"
            :name="key"
            :label="profileLabels[key]"
          >
            <a-select
              v-if="key === 'sex'"
              v-model:value="draft[key]"
              allow-clear
              :options="Object.entries(sexLabels).map(([value, label]) => ({ value, label }))"
            />
            <a-select
              v-else-if="key === 'activity_level'"
              v-model:value="draft[key]"
              allow-clear
              :options="Object.entries(activityLabels).map(([value, label]) => ({ value, label }))"
            />
            <a-input v-else-if="key === 'birth_date'" v-model:value="draft[key]" type="date" />
            <a-input-number
              v-else-if="key === 'height_cm'"
              v-model:value="draft[key]"
              :min="1"
              :max="300"
            />
            <a-select
              v-else-if="['allergens', 'avoidances'].includes(key)"
              v-model:value="draft[key]"
              mode="tags"
              placeholder="逐项输入；未填写表示未知"
            />
            <a-textarea
              v-else
              v-model:value="draft[key]"
              :rows="2"
              :maxlength="key === 'goal' ? 200 : key === 'preferences' ? 500 : 2000"
              placeholder="未填写表示未知；确认没有时请写“无”"
            />
          </a-form-item>
        </div>
      </a-form>
      <a-alert v-if="editError" type="error" :message="editError" show-icon />
    </a-modal>
    <a-drawer v-model:open="historyOpen" title="档案变更记录" :width="480">
      <a-spin :spinning="historyLoading">
        <a-alert v-if="historyError" type="error" :message="historyError" />
        <a-empty v-else-if="!history.length" description="尚无档案变更记录" />
        <section v-for="revision in history" :key="revision.version" class="revision">
          <h3>v{{ revision.version }} · {{ formatTime(revision.created_at) }}</h3>
          <p v-for="(value, key) in revision.profile" :key="key">
            {{ profileLabels[key] }}：{{ display(key, value) }}
          </p>
        </section>
      </a-spin>
    </a-drawer>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { familyApi } from '@/apis/family_api'
import {
  profileLabels,
  sexLabels,
  activityLabels,
  profileChanges,
  profileStatus,
  formatTime
} from '@/utils/familyArchives'

const props = defineProps({
  familyId: { type: String, required: true },
  member: { type: Object, required: true }
})
const emit = defineEmits(['changed'])
const editableKeys = computed(() =>
  Object.keys(profileLabels).filter((key) => props.member.allowed_fields.includes(key))
)
const editing = ref(false),
  saving = ref(false),
  editError = ref('')
const draft = reactive({})
const historyOpen = ref(false),
  historyLoading = ref(false),
  historyError = ref(''),
  history = ref([])
let generation = 0
watch(
  () => props.member,
  () => {
    generation++
    editing.value = false
    historyOpen.value = false
    history.value = []
    for (const key of Object.keys(draft)) delete draft[key]
  }
)
onBeforeUnmount(() => {
  generation++
  history.value = []
  for (const key of Object.keys(draft)) delete draft[key]
})
function display(key, value) {
  if (value === null || value === undefined || value === '') return '未填写'
  if (Array.isArray(value)) return value.length ? value.join('、') : '已确认无'
  return { sex: sexLabels, activity_level: activityLabels }[key]?.[value] ?? value
}
function openEditor() {
  for (const key of Object.keys(draft)) delete draft[key]
  for (const key of editableKeys.value) draft[key] = props.member.profile[key] ?? null
  editError.value = ''
  editing.value = true
}
async function save() {
  saving.value = true
  try {
    const payload = profileChanges(draft, props.member.allowed_fields)
    for (const key of editableKeys.value) {
      if (draft[key] === undefined || draft[key] === '') payload[key] = null
    }
    await familyApi.updateProfile(props.familyId, props.member.id, {
      expected_version: props.member.version,
      profile: payload
    })
    editing.value = false
    message.success('已保存新版本，请由本人核对确认')
    emit('changed')
  } catch (error) {
    editError.value = error.message
  } finally {
    saving.value = false
  }
}
async function confirm() {
  saving.value = true
  try {
    await familyApi.confirm(props.familyId, props.member.id, props.member.version)
    emit('changed')
    message.success('档案已确认')
  } catch (error) {
    message.error(error.message)
  } finally {
    saving.value = false
  }
}
async function showHistory() {
  const current = generation
  historyOpen.value = true
  historyLoading.value = true
  historyError.value = ''
  try {
    const rows = await familyApi.history(props.familyId, props.member.id)
    if (current === generation) history.value = rows
  } catch (error) {
    if (current === generation) historyError.value = error.message
  } finally {
    if (current === generation) historyLoading.value = false
  }
}
async function exportProfile() {
  const current = generation
  try {
    const family = await familyApi.get(props.familyId)
    if (current !== generation) return
    const member = family.members.find((row) => row.id === props.member.id)
    if (!member || !Object.keys(member.profile).length) {
      message.info('当前没有可导出的档案字段')
      emit('changed')
      return
    }
    const blob = new Blob(
      [
        JSON.stringify(
          { member: member.name, version: member.version, profile: member.profile },
          null,
          2
        )
      ],
      { type: 'application/json' }
    )
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '家庭档案.json'
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    if (current === generation) message.error(error.message)
  }
}
</script>

<style scoped lang="less">
.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 32px;
  margin: 24px 0;
  dt {
    color: var(--gray-600);
    font-size: 13px;
  }
  dd {
    margin-top: 4px;
    overflow-wrap: anywhere;
  }
}
.section-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  border-top: 1px solid var(--gray-150);
  padding-top: 12px;
}
.revision {
  padding: 16px 0;
  border-bottom: 1px solid var(--gray-150);
  h3 {
    font-size: 14px;
  }
}
.form-note {
  margin-bottom: 20px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
  :deep(.ant-input-number) {
    width: 100%;
  }
}
@media (max-width: 600px) {
  .profile-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
