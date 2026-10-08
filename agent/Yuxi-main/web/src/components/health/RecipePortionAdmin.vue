<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { healthVisionApi } from '@/apis/health_vision_api'
const props = defineProps({ foodCount: { type: Number, default: 0 } })
const emit = defineEmits(['saved'])
const busy = ref(false)
const foods = ref([])
const recipes = ref([])
const publishedRecipe = ref(null)
let versionSequence = 0
const sourceLabels = {
  source: '来源（可追溯）',
  license: '使用许可 / 授权依据',
  edition: '原始版本',
  dataset_version: '本次数据集版本'
}
const sourceFields = () => Object.fromEntries(Object.keys(sourceLabels).map((key) => [key, '']))
const recipe = reactive({
  record_code: '',
  name: '',
  cooking_state: '',
  ...sourceFields(),
  yield_grams: null,
  ingredients: []
})
const portionKind = ref('food')
const portion = reactive({
  food_id: null,
  recipe_version_id: null,
  unit_label: '',
  grams_per_unit: null,
  applicable_scope: '',
  ...sourceFields()
})
watch(portionKind, () => {
  portion.food_id = null
  portion.recipe_version_id = null
})

/** 原料与规格只绑定已发布版本，不添加演示食物数据。 */
async function loadVersions(query = '') {
  const sequence = ++versionSequence
  try {
    const [foodResult, recipeResult] = await Promise.all([
      healthVisionApi.foods(query),
      healthVisionApi.recipes(query)
    ])
    if (sequence === versionSequence) {
      foods.value = foodResult
      recipes.value = recipeResult
    }
  } catch (error) {
    message.error(error.message)
  }
}
onMounted(loadVersions)
watch(
  () => props.foodCount,
  () => loadVersions()
)

function addIngredient() {
  recipe.ingredients.push({ food_id: null, grams: null, role: 'food' })
}

/** 原料与净成品重提交后，营养只由服务端确定性计算。 */
async function publishRecipe() {
  if (
    !recipe.ingredients.length ||
    recipe.ingredients.some((entry) => !entry.food_id || !entry.grams) ||
    !recipe.yield_grams ||
    ['record_code', 'name', 'cooking_state', ...Object.keys(sourceLabels)].some(
      (key) => !recipe[key].trim()
    )
  )
    return message.warning('请补齐原料、净成品重、来源及版本')
  busy.value = true
  try {
    publishedRecipe.value = await healthVisionApi.publishRecipe(recipe)
    await loadVersions()
    emit('saved')
    message.success('食谱版本已发布，配方营养标记为估算')
    recipe.record_code = ''
    recipe.name = ''
  } catch (error) {
    message.error(error.message)
  } finally {
    busy.value = false
  }
}

/** 碗勺重量须具备实测依据和明确适用范围。 */
async function publishPortion() {
  if (
    !(portion.food_id || portion.recipe_version_id) ||
    !portion.grams_per_unit ||
    ['unit_label', 'applicable_scope', ...Object.keys(sourceLabels)].some(
      (key) => !portion[key].trim()
    )
  )
    return message.warning('请补齐目标版本、实测规格、来源及适用范围')
  busy.value = true
  try {
    await healthVisionApi.publishPortion(portion)
    emit('saved')
    message.success('份量参考版本已发布，用户应用时仍标记为估算')
    portion.unit_label = ''
  } catch (error) {
    message.error(error.message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="section">
    <h2>发布食谱配方版本</h2>
    <a-alert
      message="食品原料克数与净成品重量分别填写，不用原料总重代替煮熟后的净重。原配方油糖须标明角色；成品营养由服务端计算，留空营养仍为未知。发布只追加新版本。"
      type="info"
      show-icon
    />
    <div class="grid">
      <label
        v-for="(label, key) in {
          record_code: '食谱编码',
          name: '食谱名称',
          cooking_state: '生熟 / 加工状态',
          ...sourceLabels
        }"
        :key="key"
        >{{ label
        }}<a-input
          v-model:value="recipe[key]"
          :disabled="busy"
          :maxlength="key === 'source' || key === 'license' ? 300 : 80"
      /></label>
      <label
        >净成品重量（g）<a-input-number
          v-model:value="recipe.yield_grams"
          :disabled="busy"
          :min="0.1"
          :max="100000"
          :precision="1"
          placeholder="实际测量烹饪后的可食净重"
      /></label>
    </div>
    <div v-for="(ingredient, index) in recipe.ingredients" :key="index" class="ingredient grid">
      <label
        >原料版本<a-select
          v-model:value="ingredient.food_id"
          :disabled="busy"
          show-search
          :options="
            foods.map((food) => ({
              value: food.id,
              label: `${food.name} · ${food.cooking_state} · ${food.dataset_version}`
            }))
          "
          :filter-option="false"
          @search="loadVersions"
      /></label>
      <label
        >原料可食克数<a-input-number
          v-model:value="ingredient.grams"
          :disabled="busy"
          :min="0.1"
          :max="100000"
          :precision="1"
      /></label>
      <label
        >配方角色<a-select v-model:value="ingredient.role" :disabled="busy"
          ><a-select-option value="food">普通原料</a-select-option
          ><a-select-option value="oil">原配方油</a-select-option
          ><a-select-option value="sugar">原配方糖</a-select-option></a-select
        ></label
      >
      <a-button :disabled="busy" @click="recipe.ingredients.splice(index, 1)">移除此原料</a-button>
    </div>
    <div class="actions">
      <a-button :disabled="busy || recipe.ingredients.length >= 50" @click="addIngredient"
        >添加原料</a-button
      ><a-button :loading="busy" @click="publishRecipe">发布不可变食谱版本</a-button>
    </div>
    <p v-if="publishedRecipe">
      已发布：{{ publishedRecipe.name }} · {{ publishedRecipe.dataset_version }}，净成品
      {{ publishedRecipe.yield_grams }}g，原料 {{ publishedRecipe.ingredients.length }} 项。每 100g
      能量：{{ publishedRecipe.nutrients.energy_kcal ?? '未知' }} kcal（配方估算）。
    </p>
  </section>
  <section class="section">
    <h2>发布碗勺份量参考</h2>
    <a-alert
      message="规格严格绑定食品或食谱版本；注明容器、装量及实测条件。用户选择此规格后按数量换算，不能标记为实际称重。"
      type="info"
      show-icon
    />
    <div class="grid">
      <label
        >目标数据类型<a-select v-model:value="portionKind" :disabled="busy"
          ><a-select-option value="food">食品版本</a-select-option
          ><a-select-option value="recipe">食谱版本</a-select-option></a-select
        ></label
      >
      <label
        >目标版本<a-select
          v-if="portionKind === 'food'"
          v-model:value="portion.food_id"
          :disabled="busy"
          show-search
          :options="
            foods.map((food) => ({
              value: food.id,
              label: `${food.name} · ${food.dataset_version}`
            }))
          "
          :filter-option="false"
          @search="loadVersions" /><a-select
          v-else
          v-model:value="portion.recipe_version_id"
          :disabled="busy"
          show-search
          :options="
            recipes.map((recipe) => ({
              value: recipe.id,
              label: `${recipe.name} · ${recipe.dataset_version}`
            }))
          "
          :filter-option="false"
          @search="loadVersions"
      /></label>
      <label
        >容器与装量名称<a-input
          v-model:value="portion.unit_label"
          :disabled="busy"
          :maxlength="80"
          placeholder="如指定 200ml 碗平装"
      /></label>
      <label
        >每单位可食重量（g）<a-input-number
          v-model:value="portion.grams_per_unit"
          :disabled="busy"
          :min="0.1"
          :max="10000"
          :precision="1"
      /></label>
      <label
        >适用范围与实测条件<a-input
          v-model:value="portion.applicable_scope"
          :disabled="busy"
          :maxlength="300"
      /></label>
      <label v-for="(label, key) in sourceLabels" :key="key"
        >{{ label
        }}<a-input
          v-model:value="portion[key]"
          :disabled="busy"
          :maxlength="key === 'source' || key === 'license' ? 300 : 80"
      /></label>
    </div>
    <a-button :loading="busy" @click="publishPortion">发布不可变份量参考</a-button>
  </section>
</template>

<style scoped lang="less">
.section {
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 18px;
  background: var(--gray-0);
}
h2 {
  margin: 0 0 10px;
  font-size: 17px;
  color: var(--gray-1000);
}
p {
  color: var(--gray-600);
  line-height: 1.8;
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 18px 0;
  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .ant-input-number {
    width: 100%;
  }
}
.ingredient {
  padding: 12px;
  background: var(--gray-50);
  border-radius: 8px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
}
@media (max-width: 700px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
