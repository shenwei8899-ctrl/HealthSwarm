<script setup>
import { mealLabels, nutrientLabels, nutrientText } from '@/utils/healthVision'

const props = defineProps({
  snapshot: { type: Object, required: true },
  members: { type: Array, default: () => [] },
  ruleChecked: { type: Boolean, default: false }
})

/** 显示已授权成员名称，未知身份不从营养或份量推断。 */
function memberName(id) {
  return props.members.find((member) => member.id === id)?.display_name || '所选成员'
}
/** 服务端计划克数保留未知值，绝不默认均分。 */
function gramsText(value) {
  return value === null || value === undefined
    ? '未知'
    : `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 6 })} g`
}
</script>

<template>
  <section class="family-snapshot" aria-label="家庭餐单快照">
    <div class="status">
      <a-tag>草稿</a-tag>
      <a-tag color="orange">{{ ruleChecked ? '按批准规则逐人检查' : '未个体适配' }}</a-tag>
      <a-tag color="orange">未专业审核</a-tag>
    </div>
    <p class="muted">
      按各成员明确的计划份量计算。家庭合计包含多人，个人只统计列明的参加餐次；保存后仍需专业审核，不计入实际饮食。
    </p>
    <h4>家庭计划合计（多人）</h4>
    <dl class="nutrition">
      <template v-for="([label, unit], code) in nutrientLabels" :key="code">
        <dt>{{ label }}</dt>
        <dd>{{ nutrientText(snapshot.nutrition?.totals?.[code], unit) }}</dd>
      </template>
    </dl>
    <article v-for="(person, id) in snapshot.members" :key="id" class="person">
      <h4>{{ memberName(id) }}</h4>
      <p class="muted">
        参加餐次：{{ (person.covered_meals || []).map((meal) => mealLabels[meal]).join('、') }} ·
        {{ person.full_day_covered ? '已覆盖三餐' : '未覆盖三餐，不能作为个人全天结论' }}
      </p>
      <h5>所列餐次计划合计</h5>
      <dl class="nutrition">
        <template v-for="([label, unit], code) in nutrientLabels" :key="code">
          <dt>{{ label }}</dt>
          <dd>{{ nutrientText(person.nutrition?.totals?.[code], unit) }}</dd>
        </template>
      </dl>
      <p v-if="!person.nutrition?.complete" class="muted">营养或份量数据不完整，未知值保留为空。</p>
      <div class="meals">
        <section v-for="meal in person.meals" :key="meal.meal_type" class="meal">
          <h5>{{ mealLabels[meal.meal_type] }}</h5>
          <div v-for="dish in meal.dishes" :key="dish.family_dish_index" class="dish">
            <strong>{{ dish.name }}</strong>
            <p class="muted">
              个人计划份量：{{ gramsText(dish.planned_grams) }} · {{ dish.cooking_state }}
            </p>
            <p class="muted">
              {{
                (dish.ingredients || [])
                  .map((item) => `${item.name} ${gramsText(item.planned_grams)}`)
                  .join('、')
              }}
            </p>
            <p class="muted">来源：{{ dish.source }} · 数据版本 {{ dish.dataset_version }}</p>
          </div>
          <dl class="nutrition">
            <template v-for="([label, unit], code) in nutrientLabels" :key="code">
              <dt>{{ label }}</dt>
              <dd>{{ nutrientText(meal.nutrition?.totals?.[code], unit) }}</dd>
            </template>
          </dl>
        </section>
      </div>
    </article>
  </section>
</template>

<style scoped>
.family-snapshot,
.person {
  display: grid;
  gap: 12px;
  min-width: 0;
}
h4,
h5,
p {
  margin: 0;
}
h4 {
  overflow-wrap: anywhere;
}
.status {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
  overflow-wrap: anywhere;
}
.person {
  border-top: 1px solid var(--gray-150);
  padding-top: 16px;
}
.nutrition {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 7px 12px;
  margin: 0;
  font-size: 13px;
}
dt {
  color: var(--color-text-secondary);
}
dd {
  margin: 0;
}
.meals {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.meal {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  min-width: 0;
}
.dish {
  display: grid;
  gap: 6px;
  overflow-wrap: anywhere;
}
@media (max-width: 900px) {
  .meals {
    grid-template-columns: 1fr;
  }
}
</style>
