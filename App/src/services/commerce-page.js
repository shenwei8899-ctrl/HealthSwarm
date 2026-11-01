import { ref } from "vue";
import { onShow, onUnload } from "@dcloudio/uni-app";
import { commerceContext as storageContext } from "./commerce.js";

export function useCommercePage(clear) {
  const busy = ref(false),
    error = ref("");
  let generation = 0,
    pageScope = storageContext();
  const invalidate = () => {
    generation++;
    busy.value = false;
    clear?.();
  };
  // Native payment and photo pickers temporarily hide the page; keep their operation alive.
  onShow(() => {
    const scope = storageContext();
    if (scope !== pageScope) {
      invalidate();
      pageScope = scope;
    }
  });
  onUnload(invalidate);
  async function run(work) {
    if (busy.value) return;
    const ticket = generation,
      scope = storageContext();
    const active = () => ticket === generation && scope === storageContext();
    busy.value = true;
    error.value = "";
    try {
      await work(active);
    } catch (e) {
      if (active()) error.value = e.message || "操作未完成，请重试";
    } finally {
      // A login refresh can change the commerce revision while work is pending.
      // The operation still owns its loading flag unless a newer generation
      // replaced it; stale data must remain hidden, but loading must always end.
      if (ticket === generation) {
        if (scope !== storageContext()) {
          clear?.();
          pageScope = storageContext();
          error.value = "登录状态已更新，请重新读取";
        }
        busy.value = false;
      }
    }
  }
  return { busy, error, run };
}
