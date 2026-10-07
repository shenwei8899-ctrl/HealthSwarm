<template>
  <section>
    <div class="section-heading">
      <div>
        <h2>成员授权管理</h2>
        <p class="muted">家庭营养管理用途 · 查看与代维护所选字段</p>
      </div>
    </div>
    <a-alert
      type="info"
      show-icon
      message="成员本人认领后决定开放范围，家庭管理员身份不自动授予健康详情权限。"
    />
    <div class="table-scroll">
      <table class="family-table">
        <thead>
          <tr>
            <th>成员</th>
            <th>状态与访问范围</th>
            <th>有效期</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="member in family.members" :key="member.id">
            <td>
              {{ member.name }}<span class="muted"> · {{ member.relationship }}</span>
            </td>
            <td>
              {{
                member.is_self
                  ? '本人数据'
                  : !member.claimed
                    ? '等待本人认领'
                    : member.allowed_fields.length
                      ? member.allowed_fields.map(label).join('、')
                      : '待授权或已失效'
              }}
            </td>
            <td>
              {{
                member.authorization?.expires_at ? formatTime(member.authorization.expires_at) : '—'
              }}
            </td>
            <td>
              <a-button v-if="member.is_self && !family.is_owner" type="link" @click="edit(member)"
                >管理我的授权</a-button
              >
              <span v-else-if="member.is_self" class="muted">本人可管理自身数据</span>
              <a-button
                v-else-if="family.is_owner && !member.claimed"
                type="link"
                :loading="inviting"
                :disabled="inviting"
                @click="invite(member)"
                >生成邀请</a-button
              >
              <span v-else class="muted">由成员本人管理</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <a-modal
      v-model:open="editing"
      title="管理向家庭管理员开放的字段"
      :confirm-loading="saving"
      @ok="save"
    >
      <p class="form-note">
        用途：家庭营养管理。请先在成员档案填写本人出生日期；一期仅支持成年成员向管理员授权。管理员可查看和代维护所选字段，授权可随时撤回。
      </p>
      <a-checkbox-group v-model:value="fields" class="permission-fields" :options="allFields" />
      <a-form layout="vertical"
        ><a-form-item label="有效期至（北京时间，最长一年）"
          ><a-input v-model:value="expires" type="date" /></a-form-item
      ></a-form>
      <a-button danger :loading="saving" @click="revoke">撤回全部授权</a-button>
      <a-alert v-if="error" type="error" :message="error" show-icon class="form-note" />
    </a-modal>
    <a-modal v-model:open="inviteOpen" title="邀请成员本人认领" :footer="null">
      <p>
        请将代码通过你选择的渠道发给成员，由成员登录平台后在“家庭档案 →
        加入家庭”输入。认领后仍需本人设置授权。
      </p>
      <a-input :value="invitation?.code" readonly aria-label="家庭邀请代码" />
      <p class="muted form-note">
        有效期至
        {{
          formatTime(invitation?.expires_at)
        }}；有效期内重复获取返回同一代码，认领后其他账户不能使用。
      </p>
    </a-modal>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { familyApi } from '@/apis/family_api'
import { profileLabels, metricDefinitions, formatTime } from '@/utils/familyArchives'
const props = defineProps({ family: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const editing = ref(false),
  saving = ref(false),
  fields = ref([]),
  expires = ref(''),
  error = ref(''),
  selected = ref(null)
const inviteOpen = ref(false),
  invitation = ref(null)
const inviting = ref(false)
const allFields = computed(() =>
  Object.entries(profileLabels)
    .map(([value, label]) => ({ value, label }))
    .concat(
      Object.entries(metricDefinitions).map(([value, item]) => ({ value, label: item.label }))
    )
)
const label = (key) => profileLabels[key] || metricDefinitions[key]?.label || key
let generation = 0
watch(
  () => props.family,
  () => {
    generation++
    editing.value = false
    inviteOpen.value = false
    invitation.value = null
    fields.value = []
    selected.value = null
  }
)
onBeforeUnmount(() => {
  generation++
  fields.value = []
  selected.value = null
  invitation.value = null
})
function edit(member) {
  selected.value = member
  fields.value = [...(member.authorization?.fields || [])]
  expires.value =
    member.authorization?.expires_at && Date.parse(member.authorization.expires_at) > Date.now()
      ? member.authorization.expires_at.slice(0, 10)
      : new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10)
  error.value = ''
  editing.value = true
}
async function save() {
  if (fields.value.length) {
    const born = selected.value?.profile.birth_date
    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date())
    const cutoff = String(Number(today.slice(0, 4)) - 18) + today.slice(4)
    if (!born || born > cutoff) {
      error.value = '请先在成员档案填写本人出生日期；一期仅支持成年成员授权'
      return
    }
  }
  if (!expires.value) {
    error.value = '请选择有效期'
    return
  }
  saving.value = true
  try {
    await familyApi.authorize(props.family.id, selected.value.id, {
      fields: fields.value,
      purpose: 'family_nutrition',
      expires_at: new Date(expires.value + 'T23:59:00+08:00').toISOString()
    })
    editing.value = false
    emit('changed')
    message.success(fields.value.length ? '授权已保存' : '授权已撤回')
  } catch (cause) {
    error.value = cause.message
  } finally {
    saving.value = false
  }
}
async function revoke() {
  fields.value = []
  expires.value = new Date(Date.now() + 86400000).toISOString().slice(0, 10)
  await save()
}
async function invite(member) {
  if (inviting.value) return
  inviting.value = true
  const current = ++generation
  try {
    const result = await familyApi.invite(props.family.id, member.id)
    if (current === generation) {
      invitation.value = result
      inviteOpen.value = true
    }
  } catch (cause) {
    if (current === generation) message.error(cause.message)
  } finally {
    inviting.value = false
  }
}
</script>

<style scoped lang="less">
.permission-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 24px 0;
}
.form-note {
  margin: 16px 0;
}
</style>
