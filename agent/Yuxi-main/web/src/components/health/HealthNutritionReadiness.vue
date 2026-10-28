<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { healthVisionApi } from '@/apis/health_vision_api'
const props = defineProps({
  memberId: { type: String, required: true },
  ruleCode: { type: String, default: '' },
  disabled: Boolean
})
const result = ref(null)
const busy = ref(false)
const error = ref('')
let sequence = 0
let disposed = false
const reasons = {
  confirmed_profile_or_approved_rules_required: '需要当前有效的专业档案与批准规则',
  complete_supported_profile_required: '请补充档案缺项或核对适用范围',
  initial_catalog_not_approved: '规则中尚无批准的初始配餐目录',
  profile_menu_not_approved: '没有匹配该人群及疾病组合的批准菜单',
  eligible_recipe_missing: '部分餐次缺少来源有效且适用的菜谱',
  knowledge_source_changed: '知识库原件已变化或不可用，请重新核对',
  not_delivered: '尚未登记专业确认版本',
  personal_target_formula_not_approved: '该规则尚无匹配的批准目标公式',
  confirmed_population_age_and_sex_required: '人群、年龄或性别专业确认信息不完整',
  unsupported_population: '当前人群不在批准规则适用范围内',
  confirmed_conditions_and_requirements_required: '疾病及医嘱信息需要明确专业确认',
  confirmed_approved_activity_required: '活动编码未确认或不在批准公式内',
  selected_weight_measurement_required: '目标计算需要明确选定的本人实测体重版本',
  confirmed_formula_input_required: '批准公式所需的专业确认参数不完整',
  formula_result_outside_supported_range: '公式结果超出支持范围，需要专业复核',
  doctor_requirement_rule_not_approved: '医嘱未匹配批准规则，需要专业复核',
  approved_target_ranges_conflict: '批准目标或医嘱范围存在冲突，需要专业复核',
  revoked: '版本已撤回',
  expired: '版本已过期'
}
/** 每次主动检查当前来源；它不保存餐单，也不替代专业审核。 */
async function check() {
  if (props.disabled || !props.ruleCode.trim()) return
  const ticket = ++sequence
  result.value = null
  error.value = ''
  busy.value = true
  try {
    const value = await healthVisionApi.nutritionReadiness(props.memberId, props.ruleCode.trim())
    if (!disposed && ticket === sequence) result.value = value
  } catch {
    if (!disposed && ticket === sequence) error.value = '依赖检查失败，请核对成员授权后重试。'
  } finally {
    if (!disposed && ticket === sequence) busy.value = false
  }
}
watch(
  () => [props.memberId, props.ruleCode, props.disabled],
  () => {
    sequence++
    result.value = null
    error.value = ''
    busy.value = false
  }
)
onBeforeUnmount(() => {
  disposed = true
  sequence++
})
</script>

<template>
  <section class="readiness">
    <h3>营养业务准备情况</h3>
    <p>
      按上方规则代码检查当前成员的来源、档案和候选菜谱。组合是否满足全天目标仍需实际生成与计算。
    </p>
    <a-button :disabled="disabled || !ruleCode.trim()" :loading="busy" @click="check"
      >检查当前依赖</a-button
    >
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <template v-if="result">
      <ul>
        <li v-for="(source, name) in result.sources" :key="name">
          {{ name === 'profile' ? '专业档案' : '批准规则' }}：{{
            source.status === 'ready'
              ? `版本 ${source.version} 当前有效`
              : reasons[source.reason] || source.reason
          }}
        </li>
        <li>
          个体目标：{{
            result.personal_targets.status === 'ready'
              ? '具备计算条件'
              : reasons[result.personal_targets.reason] || result.personal_targets.reason
          }}
        </li>
        <li>
          配餐预览：{{
            result.meal_preview.status === 'can_attempt_preview'
              ? '具备候选菜谱，可尝试生成预览'
              : reasons[result.meal_preview.reason] || result.meal_preview.reason
          }}
        </li>
      </ul>
      <ul v-if="result.missing.length || result.conflicts.length">
        <li v-for="(item, i) in [...result.missing, ...result.conflicts]" :key="i">
          {{ item.path }}：{{ item.reason }}
        </li>
      </ul>
      <p v-if="result.meal_preview.missing_slots?.length">
        缺少菜位：{{
          result.meal_preview.missing_slots
            .map((slot) => `${slot.meal_type} / ${slot.dish_type_code}`)
            .join('、')
        }}
      </p>
      <p>本次检查未保存方案，也未作出专业批准。</p>
    </template>
  </section>
</template>

<style scoped>
.readiness {
  margin-top: 20px;
  border-top: 1px solid var(--gray-200);
  padding-top: 16px;
}
p {
  color: var(--color-text-secondary);
}
li {
  margin: 8px 0;
  overflow-wrap: anywhere;
}
</style>
