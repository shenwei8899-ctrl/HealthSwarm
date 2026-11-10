const KEY = "today-menu:snapshot-v1";
const TYPES = ["breakfast", "lunch", "dinner"];

// 展示快照不代表服务器已重新确认；详情和采购继续使用各自的校验。
function profileKey(profile) {
  return JSON.stringify([
    profile.householdId, profile.selfMemberId, profile.familyVersion,
    profile.usageMode, [...(profile.defaultDiners || [])].sort(),
    (profile.members || []).map(member => [
      member.id, member.version, member.relationshipVersion,
      member.healthMemberId, member.confirmed,
    ]).sort((a, b) => String(a[0]).localeCompare(String(b[0]))),
  ]);
}

function validPlan(plan, date) {
  if (!plan || plan.date !== date || plan.status !== "ready" ||
      !Number.isInteger(plan.version) || plan.version < 0 ||
      !Array.isArray(plan.meals) || !plan.meals.length || plan.meals.length > 3) return false;
  const types = plan.meals.map(meal => meal && meal.meal_type);
  return new Set(types).size === types.length && types.every(type => TYPES.includes(type)) &&
    plan.meals.every(meal => meal.source && typeof meal.source.id === "string" && meal.source.id &&
      ["formal", "reference", "selection"].includes(meal.source.kind) &&
      (meal.source.kind !== "formal" || Number.isInteger(meal.source.version) && meal.source.version > 0) &&
      meal.meal && Array.isArray(meal.meal.dishes)) &&
    plan.meals.some(meal => meal.meal.dishes.length > 0) &&
    (plan.needs_regeneration == null || Array.isArray(plan.needs_regeneration) &&
      plan.needs_regeneration.every(type => TYPES.includes(type)));
}

function createTodayMenuCache(storage) {
  // 缓存空间不足或快照损坏不能中断正常配餐。
  function clear() { try { storage.setStorageSync(KEY, null); } catch (_) {} }
  function read(owner, profile, date) {
    try {
      const saved = storage.getStorageSync(KEY);
      if (!saved) return null;
      if (saved.owner === owner && saved.profileKey === profileKey(profile) && validPlan(saved.plan, date)) {
        return JSON.parse(JSON.stringify(saved.plan));
      }
      clear();
    } catch (_) { clear(); }
    return null;
  }
  function write(owner, profile, date, plan) {
    if (!validPlan(plan, date)) { clear(); return; }
    try { storage.setStorageSync(KEY, { owner, profileKey: profileKey(profile), plan }); } catch (_) {}
  }
  return { read, write, clear };
}

export { profileKey, createTodayMenuCache };
