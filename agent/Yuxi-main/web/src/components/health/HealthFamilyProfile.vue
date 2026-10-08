<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { familyApi } from '@/apis/family_api'
import { profileLabels, profileStatus } from '@/utils/familyArchives'

const props = defineProps({
  member: { type: Object, default: null },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['consult'])
const router = useRouter()
const user = useUserStore()
const link = ref(null)
const profile = ref(null)
const source = ref(null)
const candidates = ref([])
const selectedKey = ref('')
const confirmedIdentity = ref(false)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const isSelf = computed(
  () => props.member?.is_owner && props.member?.relationship_label === '本人'
)
const canRead = computed(
  () => !!props.member?.id && isSelf.value && props.member.scopes?.includes('profile_view')
)
const canEdit = computed(() => canRead.value && props.member.scopes?.includes('profile_edit'))
const linked = computed(() => !!link.value?.source_member_id)
const selected = computed(() => candidates.value.find((item) => item.key === selectedKey.value))
const busy = computed(() => loading.value || saving.value || props.disabled)
const ready = computed(
  () => profile.value?.status === 'ready' && profile.value?.profile_available === true
)
const statusLabel = computed(() => {
  if (!linked.value) return '尚未关联'
  if (ready.value) return '当前档案已确认'
  if (profile.value?.code === 'profile_unconfirmed') return '当前版本待本人确认'
  if (profile.value?.code === 'profile_incomplete') return '档案待补充'
  return '档案暂不可用'
})
const missing = computed(() => profile.value?.missing_fields || source.value?.missingFields || [])
let sequence = 0
let disposed = false

/** 切换成员或账号后立即清除私有状态，迟到响应不得重新填入。 */
function clearState() {
  link.value = null
  profile.value = null
  source.value = null
  candidates.value = []
  selectedKey.value = ''
  confirmedIdentity.value = false
  error.value = ''
  success.value = ''
  saving.value = false
}

function active(ticket) {
  return !disposed && ticket === sequence
}

function fieldNames(fields) {
  return [...new Set(fields.map((key) => profileLabels[key] || '其他档案信息'))].join('、')
}

function errorText(cause, writing = false) {
  if (cause?.status === 403) return '当前档案权限不足，请核对授权后刷新。'
  if (cause?.status === 404) return '本人档案不存在或当前不可访问，请前往家庭档案核对后刷新。'
  if (cause?.status === 409) return '关联已发生变化，请刷新核对当前来源。已关联档案不能改绑。'
  return writing
    ? '关联结果尚未确认，请先刷新核对，再决定是否重试。'
    : '本人档案读取失败，请刷新重试。'
}

/** 关联与可用性均回读服务端；家庭详情只保留本人来源的展示信息。 */
async function reload() {
  const ticket = ++sequence
  const memberId = props.member?.id
  clearState()
  loading.value = true
  if (!canRead.value || !user.isLoggedIn) {
    loading.value = false
    return null
  }
  try {
    const currentLink = await api.familyProfileLink(memberId)
    if (!active(ticket)) return null
    link.value = currentLink
    if (currentLink.source_member_id) {
      const family = await familyApi.get(currentLink.family_id)
      if (!active(ticket)) return null
      const member = family.members.find(
        (item) => item.id === currentLink.source_member_id && item.is_self
      )
      if (!member) throw { status: 404 }
      source.value = {
        name: member.name,
        familyName: family.name,
        version: member.version,
        missingFields: member.missing_fields
      }
    }
    const currentProfile = await api.familyProfile(memberId)
    if (!active(ticket)) return null
    profile.value = {
      status: currentProfile.status,
      code: currentProfile.code,
      profile_available: currentProfile.profile_available,
      confirmed_version: currentProfile.confirmed_version,
      missing_fields: currentProfile.missing_fields,
      unknown_fields: currentProfile.unknown_fields,
      nutrition_safety_ready: currentProfile.nutrition_safety_ready
    }
    if (!currentLink.source_member_id && canEdit.value) {
      const families = await familyApi.list()
      if (!active(ticket)) return null
      const details = await Promise.all(families.map((item) => familyApi.get(item.id)))
      if (!active(ticket)) return null
      candidates.value = details.flatMap((family) =>
        family.members
          .filter((member) => member.is_self)
          .map((member) => ({
            key: `${family.id}:${member.id}`,
            familyId: family.id,
            sourceId: member.id,
            name: member.name,
            familyName: family.name,
            status: profileStatus(member)
          }))
      )
    }
    return ticket
  } catch (cause) {
    if (active(ticket)) {
      profile.value = null
      source.value = null
      candidates.value = []
      error.value = errorText(cause)
    }
    return null
  } finally {
    if (active(ticket)) loading.value = false
  }
}

/** 只有用户选定并明确确认同一身份后提交；成功提示须等待事实回读。 */
async function associate() {
  if (!canEdit.value || linked.value || busy.value || !selected.value || !confirmedIdentity.value)
    return
  const ticket = sequence
  const memberId = props.member.id
  const candidate = selected.value
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    await api.linkFamilyProfile(memberId, {
      family_id: candidate.familyId,
      source_member_id: candidate.sourceId,
      confirmed_identity: true
    })
    if (!active(ticket)) return
    const refreshed = await reload()
    if (refreshed !== null && active(refreshed) && linked.value)
      success.value = '本人档案已关联，当前状态已重新核对。'
  } catch (cause) {
    if (active(ticket)) error.value = errorText(cause, true)
  } finally {
    if (active(ticket)) saving.value = false
  }
}

function openArchives() {
  if (!disposed && !busy.value) router.push({ name: 'family', query: { tab: 'profiles' } })
}

function consult() {
  if (!disposed && ready.value && !busy.value && props.member.scopes?.includes('ai_use'))
    emit('consult')
}

watch(
  selectedKey,
  () => {
    confirmedIdentity.value = false
  },
  { flush: 'sync' }
)
watch(
  () => [
    user.uid,
    user.token,
    props.member?.id,
    props.member?.is_owner,
    props.member?.relationship_label,
    props.member?.scopes?.join(',')
  ],
  () => reload(),
  { flush: 'sync' }
)
onMounted(() => reload())
onBeforeUnmount(() => {
  disposed = true
  sequence++
  clearState()
})
</script>

<template>
  <section class="family-profile">
    <div class="heading">
      <div>
        <h2>本人档案</h2>
        <p class="muted">关联家庭档案中由你认领的本人信息，供营养咨询参考。</p>
      </div>
      <a-button v-if="canRead" :loading="loading" :disabled="saving || disabled" @click="reload"
        >刷新档案</a-button
      >
    </div>
    <a-alert
      v-if="!isSelf"
      type="info"
      show-icon
      message="请选择自己的本人健康对象，再关联本人家庭档案。"
    />
    <a-alert
      v-else-if="!canRead"
      type="info"
      show-icon
      message="查看本人档案需要档案查看授权，请核对当前成员权限。"
    />
    <template v-else>
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <a-alert v-if="success" type="success" show-icon :message="success" />
      <a-spin :spinning="loading">
        <div v-if="!loading && !error" class="content">
          <p class="status"><strong>{{ statusLabel }}</strong></p>
          <template v-if="linked">
            <p v-if="source" class="source">来源：{{ source.familyName }} · {{ source.name }}</p>
            <p v-if="ready" class="muted">确认版本 {{ profile.confirmed_version }}</p>
            <p v-else-if="source" class="muted">当前档案版本 {{ source.version }}</p>
            <a-alert
              v-if="profile?.code === 'profile_unconfirmed'"
              type="warning"
              show-icon
              message="档案已保存或修改，请前往家庭档案核对并确认当前版本，再刷新。"
            />
            <a-alert
              v-if="missing.length"
              type="warning"
              show-icon
              :message="'待补充：' + fieldNames(missing)"
            />
            <p v-if="ready && profile.unknown_fields?.length" class="muted">
              仍未填写或未知：{{ fieldNames(profile.unknown_fields) }}。未填写不代表“无”。
            </p>
            <p class="muted">已有来源不能改绑。修改档案后，请由本人重新确认并刷新当前状态。</p>
          </template>
          <template v-else>
            <p class="muted">请选择属于当前账号的本人家庭档案，并明确确认与当前健康对象是同一人。</p>
            <a-alert
              v-if="!canEdit"
              type="info"
              show-icon
              message="关联本人档案还需要档案编辑授权。"
            />
            <a-empty
              v-else-if="!candidates.length"
              description="尚无已认领的本人家庭档案。请前往家庭档案创建家庭，或加入家庭并认领本人档案。"
            />
            <a-form v-else layout="vertical" class="link-form">
              <a-form-item label="本人家庭档案">
                <a-select
                  v-model:value="selectedKey"
                  aria-label="选择本人家庭档案"
                  placeholder="请主动选择本人档案"
                  :disabled="busy"
                  :options="
                    candidates.map((item) => ({
                      value: item.key,
                      label: `${item.familyName} · ${item.name} · ${item.status}`
                    }))
                  "
                />
              </a-form-item>
              <a-checkbox v-model:checked="confirmedIdentity" :disabled="!selected || busy">
                我确认所选家庭档案与当前本人健康对象是同一人
              </a-checkbox>
              <div class="actions">
                <a-button
                  type="primary"
                  :loading="saving"
                  :disabled="!selected || !confirmedIdentity || loading || disabled"
                  @click="associate"
                  >确认并关联</a-button
                >
              </div>
            </a-form>
          </template>
          <a-alert
            type="info"
            show-icon
            message="关联与本人确认不代表完整营养安全评估已完成。"
            description="现阶段可将已确认档案用于本人描述性咨询。完整营养目标、专业安全规则与独立测量仍需补充和校验。"
          />
          <p class="muted">关联档案不会自动同意模型处理；进入咨询时需另行确认用途、处理方和政策。</p>
        </div>
      </a-spin>
      <div class="actions footer">
        <a-button :disabled="busy" @click="openArchives">前往家庭档案</a-button>
        <a-button
          v-if="ready && !error"
          :disabled="busy || !member.scopes?.includes('ai_use')"
          @click="consult"
          >使用当前档案新建咨询</a-button
        >
      </div>
    </template>
  </section>
</template>

<style scoped lang="less">
.family-profile {
  padding: 24px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-0);
  color: var(--color-text);
}
.heading,
.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.heading {
  margin-bottom: 16px;
  h2 {
    margin: 0;
    font-size: 18px;
  }
  p {
    margin: 6px 0 0;
  }
}
.content > *,
.family-profile > :deep(.ant-alert) {
  margin-bottom: 12px;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.source,
.muted,
.status {
  overflow-wrap: anywhere;
}
.link-form {
  max-width: 640px;
  margin: 16px 0;
  .actions {
    margin-top: 16px;
  }
}
.actions {
  justify-content: flex-start;
}
.footer {
  margin-top: 16px;
}
@media (max-width: 600px) {
  .family-profile {
    padding: 16px;
  }
}
</style>
