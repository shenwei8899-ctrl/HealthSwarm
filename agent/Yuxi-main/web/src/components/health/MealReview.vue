<script setup>
import { healthVisionApi } from '@/apis/health_vision_api'
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { message } from 'ant-design-vue'
const props = defineProps({ payload: { type: Object, required: true }, readonly: Boolean })
const emit = defineEmits(['changed', 'add'])
const foods = ref([])
const recipes = ref([])
const kinds = ref({})
const references = ref({})
const pendingReferences = new Set()
let searchSequence = 0
const preview = ref('')
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewError = ref('')
const selectedLocation = ref(null)
let previewRequest = 0

/** 模型序号只解析服务器绑定来源，预览仍由后端鉴权。 */
async function showLocation(location) {
  const photo = (props.payload.photos || []).find(
    (entry) => entry.image_index === location.image_index
  )
  if (!photo) return message.error('该位置没有可定位的照片')
  closePreview()
  const request = ++previewRequest
  selectedLocation.value = location
  previewOpen.value = true
  previewLoading.value = true
  try {
    const blob = await healthVisionApi.preview(photo.upload_id, photo.upload_page_index)
    if (request !== previewRequest) return
    preview.value = URL.createObjectURL(blob)
  } catch (error) {
    if (request === previewRequest) previewError.value = error.message
  } finally {
    if (request === previewRequest) previewLoading.value = false
  }
}

/** 关闭与卸载都作废迟到响应并回收私有图片 Blob。 */
function closePreview() {
  previewRequest++
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = ''
  previewOpen.value = false
  previewLoading.value = false
  previewError.value = ''
  selectedLocation.value = null
}
onBeforeUnmount(closePreview)

/** 候选只供参考，食品或食谱必须由用户显式映射到发布版本。 */
async function searchFood(query = '') {
  const sequence = ++searchSequence
  try {
    const [foodResult, recipeResult] = await Promise.all([
      healthVisionApi.foods(query),
      healthVisionApi.recipes(query)
    ])
    if (sequence === searchSequence) {
      foods.value = foodResult
      recipes.value = recipeResult
    }
  } catch (error) {
    message.error(error.message)
  }
}
onMounted(() => searchFood())

/** 规格缓存绑定数据版本，不把旧请求结果应用到另一个食物。 */
watch(
  () => props.payload.items.map(mappingKey).join(','),
  async () => {
    for (const item of props.payload.items) {
      const key = mappingKey(item)
      if (!key || references.value[key] || pendingReferences.has(key)) continue
      pendingReferences.add(key)
      try {
        references.value[key] = await healthVisionApi.portions(
          item.recipe_version_id
            ? { recipe_version_id: item.recipe_version_id }
            : { food_id: item.food_id }
        )
      } catch (error) {
        message.error(error.message)
      } finally {
        pendingReferences.delete(key)
      }
    }
  },
  { immediate: true }
)

function mappingKey(item) {
  return item.recipe_version_id || item.food_id || ''
}
function mappingKind(item) {
  return item.recipe_version_id ? 'recipe' : kinds.value[item.item_id] || 'food'
}
function changeKind(item, value) {
  kinds.value[item.item_id] = value
  item.food_id = null
  item.recipe_version_id = null
  item.adjustments = []
  clearPortion(item)
}
function selectMapping(item) {
  item.food_id ||= null
  item.recipe_version_id ||= null
  clearPortion(item)
}
function clearPortion(item) {
  item.portion_reference_id = null
  item.portion_count = null
  emit('changed')
}
function selectPortion(item) {
  item.portion_reference_id ||= null
  item.portion_count = null
  if (item.portion_reference_id) {
    item.grams = null
    item.portion_source = 'estimated'
  }
  emit('changed')
}
function addAdjustment(item, role) {
  item.adjustments ||= []
  item.adjustments.push({ role, mode: 'append', food_id: null, grams: null })
  emit('changed')
}
function removeAdjustment(item, index) {
  item.adjustments.splice(index, 1)
  emit('changed')
}
</script>

<template>
  <a-alert
    message="照片只产生候选。选择已发布食品或食谱版本，确认最终可食净重与本人分食比例。碗勺换算和配方均标记估算；油糖调整已包含在最终净重内，不要再另建同一油糖食物项。"
    type="info"
    show-icon
  />
  <p class="observation-note">
    可见食材与位置框是照片观察，仍需核实；未看见不代表不存在，不能据此排除隐藏配料或过敏原。
  </p>
  <div v-for="(item, index) in payload.items" :key="item.item_id" class="meal-card">
    <div class="heading">
      <strong>食物 {{ index + 1 }}</strong>
      <a-checkbox v-model:checked="item.excluded" :disabled="readonly" @change="emit('changed')"
        >排除此项</a-checkbox
      >
    </div>
    <div class="grid">
      <label
        >食物名称<a-input
          v-model:value="item.name"
          :disabled="readonly"
          :maxlength="120"
          placeholder="按实际食物修正"
          @change="emit('changed')"
      /></label>
      <label
        >数据类型<a-select
          :value="mappingKind(item)"
          :disabled="readonly"
          @change="changeKind(item, $event)"
          ><a-select-option value="food">单一食品 / 已有营养标签</a-select-option
          ><a-select-option value="recipe">食谱成品（配方估算）</a-select-option></a-select
        ></label
      >
      <label
        >匹配数据版本
        <a-select
          v-if="mappingKind(item) === 'food'"
          v-model:value="item.food_id"
          :disabled="readonly"
          show-search
          allow-clear
          :filter-option="false"
          placeholder="搜索并确认食品版本"
          @search="searchFood"
          @change="selectMapping(item)"
        >
          <a-select-option v-for="food in foods" :key="food.id" :value="food.id"
            >{{ food.name }} · {{ food.cooking_state }} ·
            {{ food.dataset_version }}</a-select-option
          >
        </a-select>
        <a-select
          v-else
          v-model:value="item.recipe_version_id"
          :disabled="readonly"
          show-search
          allow-clear
          :filter-option="false"
          placeholder="搜索并确认食谱版本"
          @search="searchFood"
          @change="selectMapping(item)"
        >
          <a-select-option v-for="recipe in recipes" :key="recipe.id" :value="recipe.id"
            >{{ recipe.name }} · {{ recipe.cooking_state }} ·
            {{ recipe.dataset_version }}</a-select-option
          >
        </a-select>
      </label>
      <label
        >烹饪方式<a-input
          v-model:value="item.cooking_method"
          :disabled="readonly"
          :maxlength="100"
          @change="emit('changed')"
      /></label>
      <label class="ingredients"
        >可见食材 / 人工补充（待核实）<a-select
          v-model:value="item.visible_ingredients"
          mode="tags"
          :disabled="readonly"
          :token-separators="['、', '，', ',']"
          placeholder="回车分项；未知时留空"
          @change="emit('changed')"
        /><small>至多 20 项，每项 80 字；不自动用于营养或过敏判断。</small></label
      >
      <label
        >最终可食净重（g，含调整油糖）<a-input-number
          v-model:value="item.grams"
          :disabled="readonly || !!item.portion_reference_id"
          :min="0.1"
          :max="10000"
          :precision="1"
          placeholder="未知时留空"
          @change="emit('changed')"
      /></label>
      <label
        >本人分食比例（0—1）<a-input-number
          v-model:value="item.share_ratio"
          :disabled="readonly"
          :min="0"
          :max="1"
          :step="0.1"
          :precision="3"
          placeholder="如一半填写 0.5"
          @change="emit('changed')"
      /></label>
      <label
        >碗勺参考（可选）<a-select
          v-model:value="item.portion_reference_id"
          :disabled="readonly || !mappingKey(item)"
          allow-clear
          placeholder="无适用规格时手填克数"
          @change="selectPortion(item)"
          ><a-select-option
            v-for="portion in references[mappingKey(item)] || []"
            :key="portion.id"
            :value="portion.id"
            >{{ portion.unit_label }} · {{ portion.grams_per_unit }}g ·
            {{ portion.dataset_version }}</a-select-option
          ></a-select
        ></label
      >
      <label v-if="item.portion_reference_id"
        >份量数量<a-input-number
          v-model:value="item.portion_count"
          :disabled="readonly"
          :min="0.001"
          :max="1000"
          :precision="3"
          placeholder="请填写实际数量"
          @change="emit('changed')"
      /></label>
      <label
        >重量来源<a-select
          v-model:value="item.portion_source"
          :disabled="readonly || !!item.portion_reference_id"
          @change="emit('changed')"
          ><a-select-option value="unknown">未知</a-select-option
          ><a-select-option value="estimated">人工 / 参考估算</a-select-option
          ><a-select-option value="weighed">实际称重</a-select-option
          ><a-select-option value="manual">人工填写</a-select-option></a-select
        ></label
      >
    </div>
    <p
      v-for="portion in (references[mappingKey(item)] || []).filter(
        (entry) => entry.id === item.portion_reference_id
      )"
      :key="portion.id"
    >
      份量依据：{{ portion.source }} · {{ portion.edition }} · {{ portion.license }}；适用范围：{{
        portion.applicable_scope
      }}。换算属于估算，不是本人称重。
    </p>
    <div
      v-for="(adjustment, adjustmentIndex) in item.adjustments || []"
      :key="adjustment.role"
      class="adjustment grid"
    >
      <label
        >{{ adjustment.role === 'oil' ? '油' : '糖' }}的处理方式<a-select
          v-model:value="adjustment.mode"
          :disabled="readonly"
          @change="emit('changed')"
          ><a-select-option value="append">额外追加（不扣原配方）</a-select-option
          ><a-select-option v-if="item.recipe_version_id" value="replace"
            >替换原配方对应油糖</a-select-option
          ></a-select
        ></label
      >
      <label
        >调整食品版本<a-select
          v-model:value="adjustment.food_id"
          :disabled="readonly"
          show-search
          :filter-option="false"
          placeholder="选择实际油或糖"
          @search="searchFood"
          @change="emit('changed')"
          ><a-select-option v-for="food in foods" :key="food.id" :value="food.id"
            >{{ food.name }} · {{ food.dataset_version }}</a-select-option
          ></a-select
        ></label
      >
      <label
        >调整重量（g）<a-input-number
          v-model:value="adjustment.grams"
          :disabled="readonly"
          :min="0.1"
          :max="10000"
          :precision="1"
          placeholder="必须明确填写"
          @change="emit('changed')"
      /></label>
      <a-button v-if="!readonly" @click="removeAdjustment(item, adjustmentIndex)"
        >移除该调整</a-button
      >
    </div>
    <div v-if="!readonly" class="actions">
      <a-button
        v-for="role in ['oil', 'sugar'].filter(
          (role) => !(item.adjustments || []).some((entry) => entry.role === role)
        )"
        :key="role"
        @click="addAdjustment(item, role)"
        >明确{{ role === 'oil' ? '油' : '糖' }}调整</a-button
      >
    </div>
    <p v-if="item.recipe_version_id">
      配方原本包含的油糖已计入；只有明确追加或替换时才填调整，隐含调味料和过敏原仍需人工核实。
    </p>
    <p v-if="item.candidates.length">模型候选：{{ item.candidates.join('、') }}</p>
    <p v-if="item.uncertainties.length">待确认：{{ item.uncertainties.join('；') }}</p>
    <div v-if="(item.locations || []).length" class="locations">
      <span>照片位置（模型标记，待核实）</span>
      <a-button
        v-for="location in item.locations"
        :key="location.image_index"
        size="small"
        @click="showLocation(location)"
        >查看照片 {{ location.image_index + 1 }} 的位置</a-button
      >
    </div>
    <p v-else>照片位置未知，请按实物核对。</p>
  </div>
  <a-button v-if="!readonly && payload.items.length < 30" @click="emit('add')">补充食物</a-button>
  <a-empty v-if="!payload.items.length" description="暂无食物，请手工补充" />
  <a-modal
    :open="previewOpen"
    :title="`照片 ${(selectedLocation?.image_index ?? 0) + 1} · 模型位置待核实`"
    :footer="null"
    width="850px"
    @cancel="closePreview"
  >
    <a-spin v-if="previewLoading" tip="正在加载私有照片" />
    <a-alert v-if="previewError" :message="previewError" type="error" show-icon />
    <a-button v-if="previewError" @click="showLocation(selectedLocation)">重试加载照片</a-button>
    <div v-if="preview" class="photo-preview">
      <img :src="preview" alt="鉴权后的饮食处理图" />
      <div
        class="bbox"
        :style="{
          left: `${selectedLocation.bbox[0] * 100}%`,
          top: `${selectedLocation.bbox[1] * 100}%`,
          width: `${(selectedLocation.bbox[2] - selectedLocation.bbox[0]) * 100}%`,
          height: `${(selectedLocation.bbox[3] - selectedLocation.bbox[1]) * 100}%`
        }"
      />
    </div>
  </a-modal>
</template>

<style scoped lang="less">
.meal-card {
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  padding: 16px;
  margin: 14px 0;
}
.heading,
.actions,
.locations {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}
.locations {
  margin-top: 12px;
  align-items: center;
  color: var(--gray-600);
  font-size: 12px;
}
.observation-note {
  margin-top: 8px;
}
.ingredients {
  grid-column: 1 / -1;
  small {
    color: var(--gray-600);
  }
}
.photo-preview {
  position: relative;
  line-height: 0;
  img {
    display: block;
    width: 100%;
    height: auto;
  }
  .bbox {
    position: absolute;
    border: 2px solid var(--main-color);
    pointer-events: none;
  }
}
.actions {
  margin-top: 12px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    color: var(--gray-700);
  }
  .ant-input-number {
    width: 100%;
  }
}
.adjustment {
  margin: 12px 0;
  padding: 12px;
  background: var(--gray-50);
  border-radius: 8px;
}
p {
  margin-bottom: 0;
  color: var(--gray-600);
  font-size: 12px;
  line-height: 1.7;
}
@media (max-width: 700px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
