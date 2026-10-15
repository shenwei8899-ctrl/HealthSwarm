import { reactive, computed, watch } from 'vue'
import { onUnload } from '@dcloudio/uni-app'
import { commerce, commerceContext, commerceSessionEpoch } from './commerce.js'
import { commerceMealView, newMealCommerceState, createMealCommerceController } from './meal-commerce-state.js'

export function useMealCommercePage(context) {
  const state = reactive(newMealCommerceState())
  const controller = createMealCommerceController({ state, api: commerce, scope: commerceContext, context })
  const plan = computed(() => commerceMealView(state.menu, { ...context(), quantities: state.quantities, contextIssue: state.contextIssue }))
  watch(commerceSessionEpoch, controller.sync, { flush: 'sync' })
  onUnload(controller.dispose)
  return { state, plan, ...controller }
}
