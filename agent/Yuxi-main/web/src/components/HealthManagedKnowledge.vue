<template>
  <section class="managed-knowledge" aria-label="后台管理的知识库">
    <div class="managed-heading">
      <a-tag>由后台管理</a-tag>
      <span>此处只读，修改绑定请联系后台管理员。</span>
    </div>
    <p class="managed-description">{{ binding.description }}</p>
    <a-alert
      v-if="['unconfigured', 'unavailable'].includes(binding.status)"
      type="warning"
      message="知识库绑定需要检查"
      show-icon
    />
    <ul v-if="binding.items.length" class="managed-list">
      <li v-for="(item, index) in binding.items" :key="item.id || index">
        <span class="managed-name">{{ item.name }}</span>
        <span class="managed-state">{{ labels[item.status] }}</span>
      </li>
    </ul>
    <p v-else-if="binding.status === 'business_data'" class="managed-empty">当前使用业务数据服务</p>
  </section>
</template>

<script setup>
defineProps({ binding: { type: Object, required: true } })
const labels = {
  configured: '已绑定',
  restricted: '详情受限',
  unavailable: '不可用',
  unsupported: '类型不支持'
}
</script>

<style scoped>
.managed-knowledge {
  padding: 14px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-25);
}
.managed-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
  font-size: 12px;
}
.managed-description {
  margin: 10px 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}
.managed-list {
  list-style: none;
  padding: 0;
  margin: 12px 0 0;
}
.managed-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 12px;
  padding: 8px 0;
  border-top: 1px solid var(--gray-150);
}
.managed-name {
  flex: 1;
  min-width: 150px;
  overflow-wrap: anywhere;
  color: var(--color-text);
}
.managed-state,
.managed-empty {
  color: var(--color-text-secondary);
  font-size: 12px;
}
.managed-empty {
  margin-bottom: 0;
}
</style>
