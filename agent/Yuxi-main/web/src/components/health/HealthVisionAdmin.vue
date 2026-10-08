<script setup>
import { reactive, ref, watch, inject } from 'vue'
import { message } from 'ant-design-vue'
import { healthVisionApi } from '@/apis/health_vision_api'
import { nutrientLabels } from '@/utils/healthVision'
import RecipePortionAdmin from './RecipePortionAdmin.vue'
const props = defineProps({ configuration: { type: Object, required: true } })
const emit = defineEmits(['saved'])
const openSettings = inject('settingsModal', null)?.openSettingsModal
const busy = ref(false)
const settings = reactive({
  report_model: '',
  meal_model: '',
  consultation_model: '',
  meal_plan_model: '',
  diet_analysis_model: '',
  quality_review_model: '',
  policy_version: '',
  cloud_processing_reviewed: false
})
const food = reactive({
  record_code: '',
  name: '',
  cooking_state: '',
  source: '',
  license: '',
  edition: '',
  dataset_version: '',
  nutrients: Object.fromEntries(Object.keys(nutrientLabels).map((key) => [key, null])),
  recipe_estimated: false
})
watch(
  () => props.configuration,
  (value) => {
    settings.report_model = value.report.model
    settings.meal_model = value.meal.model
    settings.consultation_model = value.consultation?.model || ''
    settings.meal_plan_model = value.meal_plan?.model || ''
    settings.diet_analysis_model = value.diet_analysis?.model || ''
    settings.quality_review_model = value.quality_review?.model || ''
    settings.policy_version = value.policy_version
    settings.cloud_processing_reviewed = false
  },
  { immediate: true }
)

/** 仅保存管理员明确批准的配置，不触发探测性收费调用。 */
async function saveConfiguration() {
  busy.value = true
  try {
    await healthVisionApi.configure(settings)
    emit('saved')
    message.success('配置已保存，未调用云识别')
  } catch (error) {
    message.error(error.message)
  } finally {
    busy.value = false
  }
}

/** 食品数据必须注明来源、许可和版本，发布后不覆盖历史版本。 */
async function publishFood() {
  if (
    [
      'record_code',
      'name',
      'cooking_state',
      'source',
      'license',
      'edition',
      'dataset_version'
    ].some((key) => !food[key].trim())
  )
    return message.warning('请补齐食品来源、许可及版本字段')
  busy.value = true
  try {
    await healthVisionApi.publishFood(food)
    emit('saved')
    message.success('食品版本已发布')
    food.record_code = ''
    food.name = ''
  } catch (error) {
    message.error(error.message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="admin-section">
    <h2>健康服务配置</h2>
    <p>
      先在系统设置中配置模型供应商及 PaddleOCR 凭据，再选择验证过的固定模型版本。饮食模型限定
      qwen3-vl-flash-2026-01-22。此页面不显示密钥。
    </p>
    <a-button v-if="openSettings" @click="openSettings('ocr')">打开 OCR 与模型设置</a-button>
    <div class="grid">
      <label
        >报告字段提取模型<a-select
          v-model:value="settings.report_model"
          allow-clear
          placeholder="未启用"
          @change="settings.report_model ||= ''"
          ><a-select-option
            v-for="model in configuration.model_options"
            :key="model.spec"
            :value="model.spec"
            >{{ model.name }} · {{ model.spec }}</a-select-option
          ></a-select
        ></label
      >
      <label
        >饮食视觉模型<a-select
          v-model:value="settings.meal_model"
          allow-clear
          placeholder="未启用"
          @change="settings.meal_model ||= ''"
          ><a-select-option
            v-for="model in configuration.model_options.filter((item) =>
              item.spec.includes('qwen3-vl-flash-2026-01-22')
            )"
            :key="model.spec"
            :value="model.spec"
            >{{ model.name }}</a-select-option
          ></a-select
        ></label
      >
      <label
        >健康咨询模型<a-select
          v-model:value="settings.consultation_model"
          allow-clear
          placeholder="未启用"
          @change="settings.consultation_model ||= ''"
        >
          <a-select-option
            v-for="model in configuration.model_options"
            :key="model.spec"
            :value="model.spec"
          >
            {{ model.name }} · {{ model.spec }}
          </a-select-option>
        </a-select></label
      >
      <label
        v-for="(label, key) in {
          meal_plan_model: '配餐师模型',
          diet_analysis_model: '饮食分析模型',
          quality_review_model: '质量复核模型'
        }"
        :key="key"
        >{{ label
        }}<a-select
          v-model:value="settings[key]"
          allow-clear
          placeholder="未启用"
          @change="settings[key] ||= ''"
        >
          <a-select-option
            v-for="model in configuration.model_options"
            :key="model.spec"
            :value="model.spec"
          >
            {{ model.name }} · {{ model.spec }}
          </a-select-option>
        </a-select></label
      >
      <label
        >处理政策版本<a-input
          v-model:value="settings.policy_version"
          :maxlength="80"
          placeholder="填写实际审批的政策版本"
      /></label>
    </div>
    <a-checkbox v-model:checked="settings.cloud_processing_reviewed"
      >已审批敏感数据云处理、供应商及任务限额（每账号每日 10 次，全平台每日 100 次）</a-checkbox
    >
    <div class="actions">
      <a-button type="primary" :loading="busy" @click="saveConfiguration">保存服务配置</a-button>
    </div>
  </section>
  <section class="admin-section">
    <h2>发布食品营养数据</h2>
    <a-alert
      message="系统不内置未经许可的食物数据。以下营养值均按每 100g 可食部计，留空表示未知；已发布版本不可覆盖。复合菜肴需说明配方及用油依据。"
      type="info"
      show-icon
    />
    <div class="grid">
      <label
        v-for="(label, key) in {
          record_code: '食品编码',
          name: '食品名称',
          cooking_state: '生熟 / 加工状态',
          source: '来源（可追溯）',
          license: '使用许可 / 授权依据',
          edition: '原始数据版本',
          dataset_version: '本次数据集版本'
        }"
        :key="key"
        >{{ label
        }}<a-input
          v-model:value="food[key]"
          :maxlength="key === 'source' || key === 'license' ? 300 : 80"
      /></label>
      <label v-for="([label, unit], key) in nutrientLabels" :key="key"
        >{{ label }}（{{ unit }}/100g）<a-input-number
          v-model:value="food.nutrients[key]"
          :min="0"
          :max="100000"
          :precision="4"
          placeholder="未知"
      /></label>
    </div>
    <a-checkbox v-model:checked="food.recipe_estimated"
      >此记录为配方估算（计算结果标记为估算）</a-checkbox
    >
    <div class="actions">
      <a-button :loading="busy" @click="publishFood">发布不可变食品版本</a-button>
    </div>
    <p>当前已发布 {{ configuration.food_count }} 条食品数据。不会根据商品宣传自动生成营养属性。</p>
  </section>
  <RecipePortionAdmin :food-count="configuration.food_count" @saved="emit('saved')" />
</template>

<style scoped lang="less">
.admin-section {
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 18px;
  background: var(--gray-0);
  h2 {
    margin: 0 0 10px;
    font-size: 17px;
    color: var(--gray-1000);
  }
  p {
    color: var(--gray-600);
    line-height: 1.8;
  }
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
.actions {
  margin-top: 16px;
}
@media (max-width: 700px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
