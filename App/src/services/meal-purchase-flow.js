// Only authoritative adopted plans can become purchases. No mock fallback or local menu upload.
export function createMealPurchaseFlow({ send, commerce, context, onChange = () => {} }) {
  let epoch = 0;
  const blank = () => ({ busy: false, error: '', notice: '', members: [], memberId: '', date: '',
    missing: [], plan: null, requirements: null, package: null, list: null, cartAdded: false });
  let state = blank();
  const emit = () => onChange({ ...state });
  const current = t => t.epoch === epoch && t.context === context();
  const ticket = () => ({ epoch, context: context() });
  function reset() { epoch++; state = blank(); emit(); }
  async function run(work) {
    if (state.busy) return;
    const t = ticket(); state.busy = true; state.error = ''; emit();
    try { await work(t); }
    catch (error) { if (current(t)) {
      state.error = error.message || '采购请求未完成';
      if ([401, 403, 404, 409, 410].includes(Number(error.status ?? error.code))) {
        state.plan = null; state.requirements = null; state.package = null; state.list = null; state.cartAdded = false;
      }
    } }
    finally { if (current(t)) { state.busy = false; emit(); } }
  }
  async function choose(memberId, date, t) {
    state.memberId = memberId; state.date = date; state.plan = null; state.requirements = null;
    state.package = null; state.list = null; state.cartAdded = false; state.notice = '';
    if (!memberId) { state.notice = '请先建立并授权健康成员，再生成、复核和采用餐单。'; return; }
    const result = (await send({ path: `/api/health/v1/members/${encodeURIComponent(memberId)}/adopted-plan?plan_date=${encodeURIComponent(date)}` })).data;
    if (!current(t)) return;
    if (result.status !== 'ready' || !result.plan?.current) {
      state.notice = '当天没有有效采用的餐单。请先完成真实配餐、专业复核和采用；此处不会使用演示餐单。'; return;
    }
    state.plan = result.plan;
    const requirements = (await send({ path: `/api/health/v1/members/${encodeURIComponent(memberId)}/purchase-requirements`,
      method: 'POST', data: selection(false, []) })).data;
    if (!current(t)) return;
    state.requirements = requirements;
    state.notice = '来源为服务器已批准并采用的餐单。采购操作不会调用 AI；AI 生成来源以餐单自身记录为准。';
  }
  function selection(confirmed, inventory) {
    return { adoption_id: state.plan.adoption_id, adoption_version: state.plan.version,
      plan_version: state.plan.plan_version, inventory_confirmed: confirmed, inventory };
  }
  return {
    reset,
    open: (date) => { reset(); return run(async t => {
      const [members, config] = await Promise.all([send({ path: '/api/health/v1/members' }), send({ path: '/api/health/v1/commerce/configuration' })]);
      if (!current(t)) return;
      state.members = members.data; state.missing = config.data.missing_configuration || [];
      await choose(state.members[0]?.id || '', date, t);
    }); },
    choose: (memberId, date) => { epoch++; state.busy = false; return run(t => choose(memberId, date, t)); },
    prepare: (inventory = []) => run(async t => {
      if (!state.plan || state.missing.length) throw new Error('有效餐单或采购服务配置尚未就绪');
      state.package = null; state.list = null; state.cartAdded = false;
      const result = (await send({ path: `/api/health/v1/members/${encodeURIComponent(state.memberId)}/commerce-recommendations`,
        method: 'POST', data: selection(true, inventory), timeout: 30000 })).data;
      if (!current(t)) return;
      if (result.source !== 'approved_adopted_plan' || !result.package?.package_sn) throw new Error('采购来源返回异常');
      state.package = result.package;
      if (!['available', 'confirmed'].includes(result.package.status)) { state.package = null; throw new Error('采购商品尚未匹配完成，请核对食材、库存和上架状态'); }
    }),
    confirm: () => run(async t => {
      if (!state.package) throw new Error('请先生成采购预览');
      const list = await commerce.confirmRecommendation(state.package.package_sn, state.package.package_version);
      if (current(t)) state.list = list;
    }),
    add: () => run(async t => {
      if (!state.list || !['ready', 'confirmed'].includes(state.list.status)) throw new Error('采购清单尚未就绪');
      await commerce.addPurchaseList(state.list.purchase_list_sn, state.list.version);
      if (current(t)) state.cartAdded = true;
    }),
  };
}
