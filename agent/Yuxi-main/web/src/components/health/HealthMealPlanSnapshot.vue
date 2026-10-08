<script setup>
import { mealLabels, nutrientLabels, nutrientText } from '@/utils/healthVision'

defineProps({
  snapshot: { type: Object, required: true },
  editable: { type: Boolean, default: false }
})
defineEmits(['swap'])

/** 服务端克数用普通十进制展示，保留未知份量。 */
function gramsText(value) {
  return value === null || value === undefined
    ? '未知'
    : `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 6 })} g`
}
</script>

<template>
  <section class="plan-snapshot">
    <div class="status">
      <a-tag>草稿</a-tag><a-tag color="orange">未个体适配</a-tag
      ><a-tag color="orange">未专业审核</a-tag>
    </div>
    <p class="muted">{{ snapshot.notice }} 保存草稿后仍需核对，不计入实际饮食记录。</p>
    <div class="totals">
      <div v-for="([label, unit], key) in nutrientLabels" :key="key" class="nutrient">
        <span>{{ label }} · 全天</span
        ><strong>{{ nutrientText(snapshot.nutrition?.totals?.[key], unit) }}</strong>
      </div>
    </div>
    <p v-if="!snapshot.nutrition?.complete" class="muted">营养或份量数据不完整，未知值保留为空。</p>
    <div class="meals">
      <article v-for="meal in snapshot.meals" :key="meal.meal_type" class="meal-card">
        <h3>{{ mealLabels[meal.meal_type] }}</h3>
        <div v-for="dish in meal.dishes" :key="dish.dish_index" class="dish">
          <div class="dish-heading">
            <strong>{{ dish.name }}</strong
            ><a-button v-if="editable" size="small" @click="$emit('swap', meal.meal_type, dish)"
              >换菜</a-button
            >
          </div>
          <p class="muted">
            计划份量：{{ gramsText(dish.planned_grams) }} · {{ dish.cooking_state }}
          </p>
          <p class="ingredients">
            {{
              dish.ingredients
                .map((item) => `${item.name} ${gramsText(item.planned_grams)}`)
                .join('、')
            }}
          </p>
          <p class="muted">来源：{{ dish.source }} · 数据版本 {{ dish.dataset_version }}</p>
        </div>
        <dl>
          <template v-for="([label, unit], key) in nutrientLabels" :key="key"
            ><dt>{{ label }}</dt>
            <dd>{{ nutrientText(meal.nutrition?.totals?.[key], unit) }}</dd></template
          >
        </dl>
      </article>
    </div>
  </section>
</template>

<style scoped>
.status,
.dish-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.status {
  justify-content: flex-start;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
}
.totals {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin: 18px 0;
}
.nutrient {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--gray-50);
  padding: 14px;
  border-radius: 8px;
}
.nutrient span {
  color: var(--color-text-secondary);
  font-size: 12px;
}
.meals {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.meal-card {
  padding: 18px;
  background: var(--bg-container);
  border: 1px solid var(--gray-150);
  border-radius: 10px;
  min-width: 0;
}
h3 {
  margin: 0 0 14px;
}
.dish {
  padding: 12px 0;
  border-top: 1px solid var(--gray-100);
  overflow-wrap: anywhere;
}
.ingredients {
  font-size: 13px;
}
dl {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 7px;
  font-size: 13px;
  border-top: 1px solid var(--gray-150);
  padding-top: 14px;
}
dt {
  color: var(--color-text-secondary);
}
dd {
  margin: 0;
}
@media (max-width: 900px) {
  .meals {
    grid-template-columns: 1fr;
  }
  .totals {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
