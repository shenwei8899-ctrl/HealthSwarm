<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { useUserStore } from '@/stores/user'
const user = useUserStore(), status = ref(null), recipes = ref([]), selected = ref(null), source = ref(null)
const busy = ref(false), error = ref(''), notice = ref('')
const draft = reactive({ source_ref: '', steps: '', ingredient_codes: {}, dish_type_code: '', allowed_meal_types: [] })
const ruleReasons = {
  not_configured: '尚未指定日常配餐规则',
  not_delivered: '指定规则尚未登记',
  revoked: '指定规则已撤回',
  expired: '指定规则已过期',
  future_attestation: '指定规则尚未生效',
  integrity_mismatch: '指定规则来源或内容需重新核验',
  knowledge_source_changed: '指定规则引用的原文已变化'
}
let revision = 0

async function load() {
  const ticket = ++revision
  try {
    const [readiness, values] = await Promise.all([api.dailySetupReadiness(), api.recipes('')])
    if (ticket !== revision) return
    status.value = readiness; recipes.value = values
  } catch (exc) { if (ticket === revision) error.value = exc.message }
}

async function readSource() {
  const ticket = ++revision
  source.value = null; notice.value = ''; error.value = ''
  if (!selected.value) return
  busy.value = true
  try {
    const value = await api.recipeCommerceSource(selected.value)
    if (ticket !== revision) return
    source.value = value
    Object.assign(draft, { source_ref: value.source_ref, steps: value.steps.join('\n'),
      ingredient_codes: { ...value.ingredient_codes }, dish_type_code: value.dish_type_code || '',
      allowed_meal_types: [...value.allowed_meal_types] })
  } catch (exc) { if (ticket === revision) error.value = exc.message }
  finally { if (ticket === revision) busy.value = false }
}

async function publish() {
  if (!source.value || busy.value) return
  const ticket = revision
  busy.value = true; error.value = ''
  try {
    await api.publishRecipeCommerceSource(source.value.recipe_version_id, {
      recipe_hash: source.value.recipe_hash, source_ref: draft.source_ref.trim(),
      steps: draft.steps.split('\n').map(value => value.trim()).filter(Boolean),
      ingredient_codes: { ...draft.ingredient_codes }, dish_type_code: draft.dish_type_code || null,
      allowed_meal_types: [...draft.allowed_meal_types]
    })
    if (ticket !== revision) return
    notice.value = '做法、标准食材映射和配方分类已保存。变更配方使用新版本。'
    source.value.published = true
    const readiness = await api.dailySetupReadiness()
    if (ticket === revision) status.value = readiness
  } catch (exc) { if (ticket === revision) error.value = exc.message }
  finally { if (ticket === revision) busy.value = false }
}
onMounted(load)
watch(() => user.uid, () => { revision++; status.value = null; source.value = null; selected.value = null; recipes.value = []; busy.value = false; error.value = ''; notice.value = '' })
</script>
<template>
  <section class="daily-setup">
    <h3>今日安排资料准备</h3>
    <template v-if="status">
      <p>食材营养 {{ status.counts.foods }} 个版本 · 菜谱 {{ status.counts.recipes }} 个版本 · 做法和采购映射 {{ status.counts.recipe_sources }} 个版本。</p>
      <p>配餐模型：{{ status.meal_plan.available ? '配置可用' : '尚未配置完成' }}；规则：{{ status.rules_ready ? '当前版本可用' : '待发布或指定' }}；商城签名调用：{{ status.commerce_configured ? '已配置，需核验调用' : '待配置' }}。</p>
      <p>配置状态与资料数量不代表已完成真实三餐验收。</p>
      <p v-if="status.rules">
        规则历史 {{ status.counts.rule_versions }} 个版本；{{
          status.rules_ready
            ? `当前指定规则 ${status.rules.code} · 第 ${status.rules.version} 版有效`
            : ruleReasons[status.rules.reason] || '指定规则尚未就绪'
        }}。历史版本数不代表当前有效版本数。
      </p>
      <p v-if="status.knowledge_bindings">
        食品整理来源：{{
          status.knowledge_bindings.food.available
            ? '家庭营养库绑定正常'
            : status.knowledge_bindings.food.configured
              ? '绑定的资料库不可用'
              : '尚未配置资料库'
        }}；菜谱整理来源：{{
          status.knowledge_bindings.recipe.available
            ? '菜谱库绑定正常'
            : status.knowledge_bindings.recipe.configured
              ? '绑定的资料库不可用'
              : '尚未配置菜谱库'
        }}。
      </p>
      <template v-if="status.candidate_batches">
        <p>
          本账号保存的食品候选 {{ status.candidate_batches.food.rows }} 行（{{
            status.candidate_batches.food.invalid
          }}
          行需修正，{{ status.candidate_batches.food.pending_review }} 行待审）；菜谱候选
          {{ status.candidate_batches.recipe.rows }} 行（{{
            status.candidate_batches.recipe.invalid
          }}
          行需修正，{{ status.candidate_batches.recipe.pending_review }} 行待审）。
        </p>
        <p>
          候选行数包含不同批次的重复资料，尚未计入正式目录。资料整理、专业签发、正式发布和方案采用分别执行。
        </p>
      </template>

    </template>
    <a-button :disabled="busy" @click="load">重新读取准备状态</a-button>
    <a-select v-model:value="selected" :disabled="busy" placeholder="选择已发布的菜谱版本" :options="recipes.map(recipe => ({ value: recipe.id, label: `${recipe.name} · ${recipe.dataset_version}` }))" @change="readSource" />
    <template v-if="source">
      <p>{{ source.name }} · 配方版本 {{ source.recipe_version_id }}</p>
      <label>做法与映射来源<a-input v-model:value="draft.source_ref" :disabled="busy || source.published" :maxlength="500" /></label>
      <label>制作步骤（每行一步）<a-textarea v-model:value="draft.steps" :disabled="busy || source.published" :rows="4" /></label>
      <label v-for="food in source.ingredients" :key="food.food_id">{{ food.name }}对应的商城标准食材编码<a-input v-model:value="draft.ingredient_codes[food.food_id]" :disabled="busy || source.published" :maxlength="100" /></label>
      <label>批准的菜品类型编码<a-input v-model:value="draft.dish_type_code" :disabled="busy || source.published" :maxlength="80" /></label>
      <a-checkbox-group v-model:value="draft.allowed_meal_types" :disabled="busy || source.published" :options="[{ label: '早餐', value: 'breakfast' }, { label: '午餐', value: 'lunch' }, { label: '晚餐', value: 'dinner' }]" />
      <a-button :disabled="busy || source.published" :loading="busy" @click="publish">核对后发布此版本做法与映射</a-button>
    </template>
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <p v-if="notice">{{ notice }}</p>
  </section>
</template>
<style scoped>
.daily-setup{display:flex;flex-direction:column;gap:12px;padding:20px 0;border-top:1px solid var(--gray-200)}
.daily-setup p{color:var(--gray-600);overflow-wrap:anywhere}.daily-setup label{display:flex;flex-direction:column;gap:6px}
</style>
