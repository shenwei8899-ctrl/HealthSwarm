<template>
  <section class="guardian-panel">
    <h3>儿童监护关系</h3>
    <p class="muted">
      成年家庭成员可申请，独立管理员核对监护资料后审核。申请人不能审核自己的申请。
    </p>
    <div v-for="member in wards" :key="member.id" class="guardian-row">
      <span
        >{{ member.name }} · {{ statusLabels[member.guardian?.status] || '未申请'
        }}<span v-if="member.is_guardian"> · 可代维护并确认</span></span
      >
      <a-button
        v-if="!['pending', 'approved'].includes(member.guardian?.status)"
        type="link"
        @click="open(member)"
        >申请监护</a-button
      >
      <a-popconfirm
        v-if="
          ['pending', 'approved'].includes(member.guardian?.status) &&
          (member.guardian?.is_applicant || member.is_self)
        "
        title="撤销后立即失去监护权限，确认？"
        @confirm="revoke(member)"
      >
        <a-button type="link" danger>撤销监护</a-button>
      </a-popconfirm>
    </div>
    <a-empty
      v-if="!wards.length"
      description="暂无儿童成员。添加成员后可申请监护。"
      :image="false"
    />
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <template v-if="isAdmin">
      <h3>待审核的监护申请</h3>
      <a-button @click="loadReviews">刷新审核队列</a-button>
      <div v-for="request in requests" :key="request.member_id" class="guardian-row">
        <span
          >{{ request.family_name }} · {{ request.member_name }} · 申请人：{{
            request.applicant_name
          }}（{{ request.applicant_uid }}） · 申请关系：{{ request.relationship }} · 出生日期：{{
            request.birth_date
          }}</span
        >
        <a-button type="link" :disabled="!request.can_review" @click="openReview(request)"
          >核对申请</a-button
        >
        <span v-if="!request.can_review" class="muted">需其他管理员审核</span>
      </div>
    </template>
    <a-modal v-model:open="requestOpen" title="申请儿童监护" :confirm-loading="saving" @ok="submit">
      <a-form layout="vertical">
        <a-form-item label="监护关系"
          ><a-select
            v-model:value="relationship"
            aria-label="监护关系"
            :options="['父亲', '母亲', '法定监护人'].map((value) => ({ value, label: value }))"
        /></a-form-item>
        <a-form-item label="儿童出生日期" required
          ><a-input v-model:value="birth" type="date" aria-label="儿童出生日期"
        /></a-form-item>
        <a-form-item label="申请有效期至（最长一年）"
          ><a-input v-model:value="expires" type="date" aria-label="监护有效期至"
        /></a-form-item>
        <a-checkbox v-model:checked="attested"
          >我确认拥有该成员的监护资格，并提供资料供独立审核。</a-checkbox
        > </a-form
      ><a-alert v-if="error" type="error" :message="error" />
    </a-modal>
    <a-modal
      :open="!!reviewTarget"
      title="核对监护申请"
      :footer="null"
      @cancel="reviewTarget = null"
    >
      <template v-if="reviewTarget"
        ><p>
          {{ reviewTarget.family_name }} · {{ reviewTarget.member_name }} ·
          {{ reviewTarget.relationship }}
        </p>
        <p>申请人账号：{{ reviewTarget.applicant_name }}（{{ reviewTarget.applicant_uid }}）</p>
        <p>请核对申请人身份、监护证明和儿童身份；审核通过后将开放资料代维护与确认权限。</p>
        <a-checkbox v-model:checked="verified">已核对监护资料和成员身份</a-checkbox>
        <div class="review-actions">
          <a-button type="primary" :disabled="!verified" :loading="saving" @click="review(true)"
            >审核通过</a-button
          >
          <a-button danger :disabled="!verified" :loading="saving" @click="review(false)"
            >审核不通过</a-button
          >
        </div>
        <a-alert v-if="error" type="error" :message="error"
      /></template>
    </a-modal>
  </section>
</template>
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { familyApi } from '@/apis/family_api'
import { memberAge } from '@/utils/familyArchives'
const props = defineProps({ family: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const user = useUserStore(),
  isAdmin = computed(() => user.isAdmin)
const wards = computed(() =>
  props.family.members.filter(
    (m) =>
      m.guardian?.status ||
      ['女儿', '儿子', '儿童'].includes(m.relationship) ||
      (memberAge(m) !== null && memberAge(m) < 18)
  )
)
const statusLabels = {
  pending: '待独立审核',
  approved: '已审核通过',
  rejected: '审核未通过',
  revoked: '已撤销'
}
const requests = ref([]),
  error = ref(''),
  saving = ref(false),
  selected = ref(null),
  requestOpen = ref(false),
  relationship = ref('父亲'),
  birth = ref(''),
  expires = ref(''),
  attested = ref(false),
  reviewTarget = ref(null),
  verified = ref(false)
defineExpose({ hasDraft: computed(() => requestOpen.value || !!reviewTarget.value) })
let generation = 0
function clear() {
  generation++
  requests.value = []
  selected.value = null
  requestOpen.value = false
  reviewTarget.value = null
  saving.value = false
  birth.value = ''
  expires.value = ''
  attested.value = false
  verified.value = false
  error.value = ''
}
watch(
  [() => props.family.id, () => user.uid, () => user.isAdmin],
  () => {
    clear()
    loadReviews()
  },
  { immediate: true }
)
onBeforeUnmount(clear)
function open(member) {
  selected.value = member
  birth.value = member.profile?.birth_date || ''
  expires.value = new Date(Date.now() + 180 * 86400000).toISOString().slice(0, 10)
  attested.value = false
  error.value = ''
  requestOpen.value = true
}
function openReview(request) {
  reviewTarget.value = request
  verified.value = false
  error.value = ''
}
async function submit() {
  if (!birth.value || !attested.value || !expires.value) {
    error.value = '请填写日期并确认监护声明'
    return
  }
  const current = generation
  saving.value = true
  try {
    await familyApi.requestGuardian(props.family.id, selected.value.id, {
      expected_version: selected.value.guardian?.version || 1,
      relationship: relationship.value,
      birth_date: birth.value,
      attested: true,
      expires_at: expires.value + 'T23:59:59+08:00'
    })
    if (current === generation) {
      requestOpen.value = false
      emit('changed')
      loadReviews()
    }
  } catch (cause) {
    if (current === generation) error.value = cause.message
  } finally {
    if (current === generation) saving.value = false
  }
}
async function revoke(member) {
  const current = generation
  try {
    await familyApi.revokeGuardian(props.family.id, member.id, member.guardian.version)
    if (current === generation) {
      emit('changed')
      loadReviews()
    }
  } catch (cause) {
    if (current === generation) error.value = cause.message
  }
}
async function loadReviews() {
  if (!isAdmin.value) return
  const current = generation
  try {
    const rows = await familyApi.guardianRequests()
    if (current === generation) requests.value = rows
  } catch (cause) {
    if (current === generation) error.value = cause.message
  }
}
async function review(approved) {
  if (!verified.value || !reviewTarget.value) return
  const target = reviewTarget.value,
    current = generation
  saving.value = true
  error.value = ''
  try {
    await familyApi.reviewGuardian(target.family_id, target.member_id, {
      expected_version: target.version,
      approved,
      verified: true
    })
    if (current === generation) {
      reviewTarget.value = null
      emit('changed')
      loadReviews()
    }
  } catch (cause) {
    if (current === generation) error.value = cause.message
  } finally {
    if (current === generation) saving.value = false
  }
}
</script>
<style scoped>
.guardian-panel {
  margin-top: 28px;
  border-top: 1px solid var(--gray-200);
  padding-top: 20px;
}
.guardian-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 12px 0;
}
.review-actions {
  display: flex;
  gap: 12px;
  margin: 16px 0;
}
</style>
