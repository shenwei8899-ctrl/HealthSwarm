<script setup>
import { ref } from 'vue'
import HealthDietAnalysis from './HealthDietAnalysis.vue'

defineProps({
  memberId: { type: String, required: true },
  scopes: { type: Array, required: true },
  configuration: { type: Object, required: true },
  record: { type: Object, required: true },
  disabled: { type: Boolean, default: false }
})
const open = ref(false)
const working = ref(false)
</script>

<template>
  <div class="feedback-conversation-entry">
    <a-button size="small" :disabled="disabled" @click="open = true">这餐反馈对话</a-button>
    <a-modal
      v-model:open="open"
      title="这餐反馈对话"
      :footer="null"
      :destroy-on-close="true"
      :mask-closable="!working"
      :closable="!working"
    >
      <HealthDietAnalysis
        v-if="open"
        :member-id="memberId"
        :scopes="scopes"
        :configuration="configuration"
        :record="record"
        :disabled="disabled"
        @busy="working = $event"
        feedback
      />
    </a-modal>
  </div>
</template>

<style scoped lang="less">
.feedback-conversation-entry {
  margin-top: 8px;
}
</style>
