<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { agentApi } from '@/apis/agent_api'
import { mealLabels } from '@/utils/healthVision'
import HealthMealPlanSnapshot from './HealthMealPlanSnapshot.vue'

const props = defineProps({
  memberId: { type: String, default: '' },
  scopes: { type: Array, default: () => [] },
  configuration: { type: Object, required: true }
})
const router = useRouter()
const canRead = computed(() => !!props.memberId && props.scopes.includes('diet_edit'))
const canGenerate = computed(
  () =>
    canRead.value &&
    props.scopes.includes('ai_use') &&
    props.scopes.includes('report_view') &&
    !!props.configuration.meal_plan?.available
)
const date = ref(
  new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(new Date())
)
const notes = ref('')
const consent = ref(false)
const recipes = ref([])
const recipeQuery = ref('')
const recipesLoading = ref(false)
const recipesError = ref('')
const plans = ref([])
const truncated = ref(false)
const loading = ref(false)
const working = ref(false)
const error = ref('')
const preview = ref(null)
const current = ref(null)
const historyVersion = ref(null)
const saveAttempt = ref(null)
const swap = ref(null)
const swapAttempt = ref(null)
const generation = ref(null)
const generationStatus = ref('')
const polling = ref(false)
const questions = ref([])
const manual = ref(false)
const meals = ref(newMeals())
const selectedId = ref('')
let epoch = 0
let listSequence = 0
let detailSequence = 0
let recipeSequence = 0
let timer
let disposed = false
const displayed = computed(() => historyVersion.value?.snapshot || current.value || preview.value)
const canPreview = computed(
  () =>
    canRead.value &&
    !!date.value &&
    meals.value.every((meal) => meal.dishes.every((dish) => !!dish.recipe_version_id))
)
const recipeOptions = computed(() =>
  recipes.value.map((r) => ({ value: r.id, label: `${r.name} · ${r.dataset_version}` }))
)
const locked = computed(
  () => working.value || polling.value || !!saveAttempt.value || !!generation.value
)

function newDish() {
  return { recipe_version_id: null, grams: null }
}
function newMeals() {
  return ['breakfast', 'lunch', 'dinner'].map((meal_type) => ({ meal_type, dishes: [newDish()] }))
}
function toggleManual() {
  manual.value = !manual.value
  if (manual.value) void loadRecipes()
}
function active(ticket) {
  return !disposed && ticket === epoch && canRead.value
}
function failure(exc) {
  return exc.status === 409
    ? '版本或处理政策已变化，请刷新核对后重新操作。'
    : exc.status === 403
      ? '成员授权或处理同意已变化，请重新确认授权。'
      : '操作结果未确认，请重试原请求或刷新核对。'
}

/** 成员列表与选中详情各有读取代次，迟到响应不能覆盖新选择。 */
async function reload() {
  const ticket = epoch,
    sequence = ++listSequence
  plans.value = []
  loading.value = true
  error.value = ''
  if (!canRead.value) {
    loading.value = false
    return
  }
  try {
    const result = await api.mealPlans(props.memberId)
    if (!active(ticket) || sequence !== listSequence) return
    plans.value = result.plans
    truncated.value = result.truncated
  } catch (exc) {
    if (active(ticket) && sequence === listSequence) {
      error.value = failure(exc)
      if (exc.status === 403) {
        current.value = null
        historyVersion.value = null
        preview.value = null
        swap.value = null
      }
    }
  } finally {
    if (active(ticket) && sequence === listSequence) loading.value = false
  }
}
async function loadRecipes() {
  const ticket = epoch,
    sequence = ++recipeSequence
  recipesLoading.value = true
  recipesError.value = ''
  try {
    const result = await api.recipes(recipeQuery.value)
    if (active(ticket) && sequence === recipeSequence) recipes.value = result
  } catch {
    if (active(ticket) && sequence === recipeSequence)
      recipesError.value = '菜谱读取失败，请重新搜索。'
  } finally {
    if (active(ticket) && sequence === recipeSequence) recipesLoading.value = false
  }
}
async function selectPlan(id) {
  if (working.value || saveAttempt.value || polling.value || generation.value) return
  const ticket = epoch,
    sequence = ++detailSequence
  selectedId.value = id
  current.value = null
  preview.value = null
  historyVersion.value = null
  error.value = ''
  working.value = true
  try {
    const result = await api.mealPlan(id)
    if (active(ticket) && sequence === detailSequence) {
      if (result.member_id !== props.memberId) throw Error('member mismatch')
      current.value = result
    }
  } catch (exc) {
    if (active(ticket) && sequence === detailSequence) error.value = failure(exc)
  } finally {
    if (active(ticket) && sequence === detailSequence) working.value = false
  }
}
/** 手动预览只提交菜谱与计划份量，显示服务端营养快照。 */
async function makePreview() {
  if (!canPreview.value || locked.value) return
  const ticket = epoch
  working.value = true
  error.value = ''
  preview.value = null
  current.value = null
  historyVersion.value = null
  try {
    const result = await api.previewMealPlan(props.memberId, {
      plan_date: date.value,
      meals: JSON.parse(JSON.stringify(meals.value))
    })
    if (active(ticket)) {
      if (result.member_id !== props.memberId) throw Error('member mismatch')
      preview.value = result
      selectedId.value = ''
    }
  } catch (exc) {
    if (active(ticket)) error.value = failure(exc)
  } finally {
    if (active(ticket)) working.value = false
  }
}
/** 未知保存响应重试原回执与原幂等键，不从页面重建快照。 */
async function save() {
  if (!canRead.value || !preview.value || working.value) return
  const ticket = epoch
  saveAttempt.value ||= {
    client_request_id: crypto.randomUUID(),
    preview_id: preview.value.preview_id
  }
  working.value = true
  error.value = ''
  try {
    const result = await api.saveMealPlan(props.memberId, saveAttempt.value)
    if (!active(ticket)) return
    if (result.member_id !== props.memberId) throw Error('member mismatch')
    saveAttempt.value = null
    preview.value = null
    current.value = result
    selectedId.value = result.plan_id
    working.value = false
    await selectPlan(result.plan_id)
    await reload()
  } catch (exc) {
    if (active(ticket)) error.value = failure(exc)
  } finally {
    if (active(ticket)) working.value = false
  }
}
function openSwap(meal_type, dish) {
  if (locked.value || !current.value || historyVersion.value) return
  swap.value = {
    meal_type,
    dish_index: dish.dish_index,
    name: dish.name,
    replacement: newDish(),
    reason: ''
  }
  swapAttempt.value = null
  void loadRecipes()
}
async function closeSwap() {
  if (working.value) return
  swap.value = null
  swapAttempt.value = null
  if (current.value) await selectPlan(current.value.plan_id)
}
/** 换菜冻结当前版本；冲突时旧餐单不可继续操作。 */
async function submitSwap() {
  if (
    !canRead.value ||
    !current.value ||
    !swap.value?.replacement.recipe_version_id ||
    !swap.value.reason.trim() ||
    working.value
  )
    return
  const ticket = epoch,
    id = current.value.plan_id
  if (!swapAttempt.value) {
    const { meal_type, dish_index, replacement, reason } = swap.value
    const data = { meal_type, dish_index, replacement, reason }
    swapAttempt.value = {
      ...JSON.parse(JSON.stringify(data)),
      version: current.value.version,
      client_request_id: crypto.randomUUID()
    }
  }
  working.value = true
  error.value = ''
  try {
    const result = await api.swapMealPlan(id, swapAttempt.value)
    if (!active(ticket)) return
    if (result.member_id !== props.memberId) throw Error('member mismatch')
    current.value = result
    swap.value = null
    swapAttempt.value = null
    working.value = false
    await selectPlan(id)
    await reload()
  } catch (exc) {
    if (active(ticket)) {
      error.value = failure(exc)
      if (exc.status === 409) {
        swap.value = null
        swapAttempt.value = null
        current.value = null
      }
    }
  } finally {
    if (active(ticket)) working.value = false
  }
}

/** 只读取同一请求、线程和 Run 的完成结果，非终态不展示正文。 */
async function checkGeneration() {
  if (!generation.value || polling.value || !canGenerate.value) return
  const ticket = epoch,
    attempt = generation.value
  polling.value = true
  error.value = ''
  clearTimeout(timer)
  try {
    const { request } = await agentApi.getRequest(attempt.request_id)
    if (!active(ticket) || generation.value !== attempt) return
    if (request.thread_id !== attempt.thread_id || request.request_id !== attempt.request_id)
      throw Error('request mismatch')
    if (!request.dispatched_run_id) {
      if (['failed', 'cancelled', 'rejected'].includes(request.status)) {
        generation.value = null
        throw Error('request failed')
      }
      generationStatus.value = '等待配餐师处理'
    } else {
      const result = await agentApi.getAgentRunResult(request.dispatched_run_id)
      if (!active(ticket) || generation.value !== attempt) return
      if (
        result.agent_run_id !== request.dispatched_run_id ||
        result.request_id !== attempt.request_id ||
        result.thread_id !== attempt.thread_id ||
        result.agent_slug !== 'health-meal-planner'
      )
        throw Error('run mismatch')
      if (result.status === 'completed') {
        const output = JSON.parse(result.output)
        if (output.status === 'needs_input' && Array.isArray(output.questions))
          questions.value = output.questions
        else if (
          output.preview_id &&
          output.member_id === props.memberId &&
          output.status === 'draft' &&
          Array.isArray(output.meals)
        )
          preview.value = output
        else throw Error('invalid result')
        generationStatus.value =
          output.status === 'needs_input' ? '请补充信息后重新生成' : '草稿已生成，请核对后保存'
        generation.value = null
        return
      }
      if (['failed', 'cancelled', 'interrupted'].includes(result.status)) {
        generation.value = null
        generationStatus.value = '生成未完成，可调整要求后重新生成'
        throw Error('run failed')
      }
      generationStatus.value = '配餐师正在生成三餐草稿'
    }
    timer = setTimeout(checkGeneration, 2000)
  } catch (exc) {
    if (active(ticket)) error.value = `${failure(exc)} 可点击“恢复生成状态”重新读取。`
  } finally {
    if (active(ticket)) polling.value = false
  }
}
/** 模型用途同意独立提交，重试冻结线程键与请求正文。 */
async function generate() {
  if (
    !canGenerate.value ||
    !consent.value ||
    !date.value ||
    working.value ||
    polling.value ||
    saveAttempt.value
  )
    return
  const ticket = epoch
  if (!generation.value)
    generation.value = {
      binding_key: crypto.randomUUID(),
      request_id: crypto.randomUUID(),
      thread_id: null,
      query: `请生成${date.value}的早餐、午餐和晚餐草稿。${notes.value.trim()}`,
      processor: props.configuration.meal_plan.processor,
      policy_version: props.configuration.policy_version
    }
  const attempt = generation.value
  working.value = true
  preview.value = null
  current.value = null
  historyVersion.value = null
  questions.value = []
  error.value = ''
  try {
    await api.consent(props.memberId, {
      purpose: 'meal_plan',
      accepted: true,
      processor: attempt.processor,
      policy_version: attempt.policy_version
    })
    if (!active(ticket)) return
    if (!attempt.thread_id) {
      const binding = await api.createMealPlanner(props.memberId, {
        client_request_id: attempt.binding_key
      })
      if (!active(ticket)) return
      if (binding.member_id !== props.memberId || binding.agent_slug !== 'health-meal-planner')
        throw Error('binding mismatch')
      attempt.thread_id = binding.thread_id
    }
    await agentApi.createAgentRun({
      agent_slug: 'health-meal-planner',
      thread_id: attempt.thread_id,
      query: attempt.query,
      meta: { request_id: attempt.request_id }
    })
    if (active(ticket)) {
      working.value = false
      await checkGeneration()
    }
  } catch (exc) {
    if (active(ticket)) error.value = failure(exc)
  } finally {
    if (active(ticket)) working.value = false
  }
}
function openConversation() {
  if (generation.value?.thread_id)
    router.push({
      name: 'AgentCompWithThreadId',
      params: { thread_id: generation.value.thread_id }
    })
}
/** 停止操作以服务器取消结果为准，网络失败仍保留恢复入口。 */
async function stopGeneration() {
  if (!generation.value || working.value || polling.value) return
  const ticket = epoch
  working.value = true
  try {
    try {
      await agentApi.cancelRequest(generation.value.request_id)
    } catch (exc) {
      if (exc.status === 409) {
        const { request } = await agentApi.getRequest(generation.value.request_id)
        if (!active(ticket)) return
        if (!request.dispatched_run_id || request.thread_id !== generation.value.thread_id)
          throw exc
        await agentApi.cancelAgentRun(request.dispatched_run_id)
      } else if (exc.status !== 404 || generation.value.thread_id) throw exc
    }
    if (active(ticket)) {
      clearTimeout(timer)
      generation.value = null
      generationStatus.value = '已提交取消请求，可重新生成；取消与完成竞争时以对话最终状态为准。'
    }
  } catch (exc) {
    if (active(ticket)) error.value = failure(exc)
  } finally {
    if (active(ticket)) working.value = false
  }
}
watch(
  () => [date.value, JSON.stringify(meals.value)],
  () => {
    if (!saveAttempt.value) preview.value = null
  }
)
watch(
  () => [props.memberId, props.scopes.join(',')],
  () => {
    epoch++
    clearTimeout(timer)
    preview.value = null
    current.value = null
    historyVersion.value = null
    saveAttempt.value = null
    swap.value = null
    swapAttempt.value = null
    generation.value = null
    consent.value = false
    polling.value = false
    working.value = false
    questions.value = []
    generationStatus.value = ''
    selectedId.value = ''
    meals.value = newMeals()
    notes.value = ''
    recipes.value = []
    recipesError.value = ''
    recipesLoading.value = false
    recipeQuery.value = ''
    manual.value = false
    void reload()
  }
)
onMounted(() => reload())
onBeforeUnmount(() => {
  disposed = true
  epoch++
  clearTimeout(timer)
})
</script>

<template>
  <section class="meal-plans">
    <a-alert v-if="!canRead" type="info" show-icon message="请选择具备饮食维护授权的健康成员。" />
    <template v-else>
      <a-alert
        type="warning"
        show-icon
        message="完整健康档案与专业配餐规则尚未接入。餐单为未个体适配、未专业审核的单成员三餐草稿。"
      />
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <section class="panel">
        <div class="heading">
          <h2>生成三餐草稿</h2>
          <a-tag>单成员 · 单日</a-tag>
        </div>
        <p class="muted">核对菜品和计划份量后显式保存。离开页面前请保存需要保留的草稿。</p>
        <div class="form-row">
          <label>餐单日期<input v-model="date" type="date" :disabled="locked" /></label
          ><a-button :disabled="locked" @click="toggleManual">{{
            manual ? '收起手动选择' : '手动选择菜谱'
          }}</a-button>
        </div>
        <a-alert
          v-if="!canGenerate"
          type="info"
          :message="
            configuration.meal_plan?.reason ||
            'AI 生成需要已启用的配餐服务、AI 使用和报告查看授权。可先手动选择菜谱。'
          "
        />
        <a-textarea
          v-model:value="notes"
          :disabled="locked || !canGenerate"
          :maxlength="1500"
          :rows="2"
          placeholder="补充用餐要求；份量只作为计划量，不能替代个人营养目标"
        />
        <p v-if="canGenerate" class="muted">
          处理方：{{ configuration.meal_plan.processor }} · 处理政策：{{
            configuration.policy_version
          }}
        </p>
        <a-checkbox v-if="canGenerate" v-model:checked="consent" :disabled="locked"
          >同意将本次用餐要求交由上述配餐服务处理</a-checkbox
        >
        <div class="actions">
          <a-button
            type="primary"
            :loading="working && !!generation"
            :disabled="!canGenerate || !consent || !date || locked"
            @click="generate"
            >配餐师生成</a-button
          ><template v-if="generation"
            ><a-button :disabled="working || polling" @click="generate">重试原生成请求</a-button
            ><a-button
              :loading="polling"
              :disabled="working || !generation.thread_id"
              @click="checkGeneration"
              >恢复生成状态</a-button
            ><a-button :disabled="working" @click="openConversation">查看生成对话</a-button
            ><a-button :disabled="working || polling" @click="stopGeneration"
              >停止等待</a-button
            ></template
          ><span class="muted" role="status">{{ generationStatus }}</span>
        </div>
        <ul v-if="questions.length">
          <li v-for="question in questions" :key="question">{{ question }}</li>
        </ul>
        <template v-if="manual">
          <div class="actions">
            <a-input-search
              v-model:value="recipeQuery"
              placeholder="搜索已发布菜谱"
              :loading="recipesLoading"
              style="max-width: 340px"
              @search="loadRecipes"
            /><a-button :loading="recipesLoading" @click="loadRecipes">刷新菜谱</a-button>
          </div>
          <a-alert v-if="recipesError" type="error" :message="recipesError" />
          <a-empty
            v-if="!recipes.length && !recipesLoading"
            description="暂无匹配的已发布菜谱。请搜索或在服务与食品数据中发布菜谱。"
          />
          <div class="manual-meals">
            <section v-for="meal in meals" :key="meal.meal_type" class="manual-meal">
              <h3>{{ mealLabels[meal.meal_type] }}</h3>
              <div v-for="(dish, index) in meal.dishes" :key="index" class="dish-form">
                <label :for="`plan-recipe-${meal.meal_type}-${index}`"
                  >{{ mealLabels[meal.meal_type] }}菜谱{{ index + 1 }}</label
                >
                <a-select
                  :id="`plan-recipe-${meal.meal_type}-${index}`"
                  v-model:value="dish.recipe_version_id"
                  :options="recipeOptions"
                  :disabled="locked"
                  placeholder="选择已发布菜谱"
                  :aria-label="`${mealLabels[meal.meal_type]}菜谱${index + 1}`"
                /><a-input-number
                  v-model:value="dish.grams"
                  :min="0.000001"
                  :max="10000"
                  :precision="6"
                  :disabled="locked"
                  placeholder="计划克数（可留空）"
                  :aria-label="`${mealLabels[meal.meal_type]}计划克数${index + 1}`"
                /><a-button
                  v-if="meal.dishes.length > 1"
                  :disabled="locked"
                  @click="meal.dishes.splice(index, 1)"
                  >移除</a-button
                >
              </div>
              <a-button
                :disabled="locked || meal.dishes.length >= 10"
                @click="meal.dishes.push(newDish())"
                >添加菜品</a-button
              >
            </section>
          </div>
          <p class="muted">没有份量依据时可留空，营养显示未知。预览依据当前填写的计划克数计算。</p>
          <a-button
            :loading="working && !generation"
            :disabled="!canPreview || locked"
            @click="makePreview"
            >计算三餐预览</a-button
          >
        </template>
      </section>
      <section class="panel">
        <div class="heading">
          <h2>已保存的餐单草稿</h2>
          <a-button :loading="loading" :disabled="working" @click="reload">刷新餐单</a-button>
        </div>
        <a-select
          :value="selectedId || undefined"
          :options="
            plans.map((p) => ({
              value: p.plan_id,
              label: `${p.plan_date} · 草稿 · 版本 ${p.version}`
            }))
          "
          :disabled="locked"
          placeholder="选择餐单查看详情"
          style="width: 100%"
          @change="selectPlan"
        /><a-empty
          v-if="!plans.length && !loading && !error"
          description="暂无已保存餐单。生成或手动预览后可保存。"
        />
        <p v-if="truncated" class="muted">当前展示最近 50 份餐单。</p>
      </section>
      <section v-if="displayed" class="panel">
        <div class="heading">
          <h2>
            {{ displayed.plan_date }} ·
            {{
              historyVersion
                ? `历史版本 ${historyVersion.version}`
                : current
                  ? `当前版本 ${current.version}`
                  : '待保存预览'
            }}
          </h2>
          <a-button v-if="preview && !current" type="primary" :loading="working" @click="save">{{
            saveAttempt ? '重试原保存请求' : '保存草稿'
          }}</a-button>
        </div>
        <HealthMealPlanSnapshot
          :snapshot="displayed"
          :editable="!!current && !historyVersion && !locked"
          @swap="openSwap"
        /><template v-if="current?.revisions"
          ><div class="heading">
            <h3>版本历史</h3>
            <a-button v-if="historyVersion" @click="historyVersion = null">返回当前版本</a-button>
          </div>
          <div v-for="revision in current.revisions" :key="revision.version" class="revision">
            <span>版本 {{ revision.version }} · {{ revision.reason }}</span
            ><span class="muted">{{ revision.created_at }}</span
            ><a-button size="small" :disabled="working" @click="historyVersion = revision"
              >查看快照</a-button
            >
          </div></template
        >
      </section>
    </template>
    <a-modal
      :open="!!swap"
      title="替换菜品并重新计算"
      :confirm-loading="working"
      :ok-button-props="{ disabled: !swap?.replacement.recipe_version_id || !swap?.reason.trim() }"
      @ok="submitSwap"
      @cancel="closeSwap"
      ><template v-if="swap"
        ><p>{{ mealLabels[swap.meal_type] }} · {{ swap.name }} · 当前版本 {{ current?.version }}</p>
        <a-alert v-if="error" type="error" :message="error" /><a-input-search
          v-model:value="recipeQuery"
          placeholder="搜索已发布菜谱"
          @search="loadRecipes"
        /><a-alert v-if="recipesError" type="error" :message="recipesError" />
        <label for="plan-swap-recipe">替换菜谱</label
        ><a-select
          id="plan-swap-recipe"
          v-model:value="swap.replacement.recipe_version_id"
          :options="recipeOptions"
          :loading="recipesLoading"
          :disabled="working || !!swapAttempt"
          placeholder="替换为哪个菜谱"
          aria-label="替换菜谱"
          style="width: 100%"
        /><a-input-number
          v-model:value="swap.replacement.grams"
          :min="0.000001"
          :max="10000"
          :precision="6"
          :disabled="working || !!swapAttempt"
          placeholder="计划克数（可留空）"
          aria-label="替换计划克数"
          style="width: 100%"
        /><a-textarea
          v-model:value="swap.reason"
          :maxlength="500"
          :disabled="working || !!swapAttempt"
          placeholder="填写换菜原因"
        />
        <p class="muted">
          换菜后保存新版本，旧版本保留。未确认响应可重试原请求；关闭后重新读取餐单状态。
        </p></template
      ></a-modal
    >
  </section>
</template>

<style scoped>
.meal-plans {
  display: grid;
  gap: 16px;
  color: var(--color-text);
}
.panel {
  background: var(--bg-container);
  border: 1px solid var(--gray-150);
  padding: 22px;
  border-radius: 12px;
  min-width: 0;
}
.heading,
.actions,
.form-row,
.revision {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.heading {
  justify-content: space-between;
  margin-bottom: 16px;
}
h2,
h3 {
  margin: 0;
}
.actions,
.form-row {
  margin: 14px 0;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
}
label {
  display: flex;
  align-items: center;
  gap: 12px;
}
input[type='date'] {
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  color-scheme: light dark;
  color: var(--color-text);
  background: var(--bg-container);
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  padding: 6px 10px;
}
.manual-meals {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.manual-meal {
  display: grid;
  gap: 12px;
  align-content: start;
  background: var(--gray-50);
  padding: 16px;
  border-radius: 8px;
}
.dish-form {
  display: grid;
  gap: 8px;
}
.dish-form :deep(.ant-input-number) {
  width: 100%;
}
.revision {
  padding: 12px 0;
  border-top: 1px solid var(--gray-150);
  overflow-wrap: anywhere;
}
:deep(.ant-modal-body > *) {
  margin-bottom: 12px;
}
@media (max-width: 900px) {
  .manual-meals {
    grid-template-columns: 1fr;
  }
  .panel {
    padding: 16px;
  }
}
@media (max-width: 600px) {
  .form-row label {
    flex-direction: column;
    align-items: flex-start;
    width: 100%;
  }
  h2 {
    font-size: 20px;
  }
}
</style>
