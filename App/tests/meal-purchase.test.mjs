import test from 'node:test';
import assert from 'node:assert/strict';
import { createMealPurchaseFlow } from '../src/services/meal-purchase-flow.js';

function fixture({ configured = true, adopted = true } = {}) {
  let state, scope = 'A', late;
  const calls = [];
  const send = async o => {
    calls.push(o);
    if (o.path.endsWith('/members')) return { data: [{ id: 'member-A', name: '测试成员' }] };
    if (o.path.endsWith('/configuration')) return { data: { missing_configuration: configured ? [] : ['mapping'] } };
    if (o.path.includes('/adopted-plan')) return { data: { status: adopted ? 'ready' : 'not_adopted',
      plan: adopted ? { current: true, adoption_id: 'adopted-A', version: 2, plan_version: 3 } : null } };
    if (o.path.endsWith('/purchase-requirements')) return { data: { items: [{ food_id: 'food-A', cooking_state: 'raw' }] } };
    if (late) return late();
    return { data: { source: 'approved_adopted_plan', ai_generation_performed: false, package: { package_sn: 'pkg-A', package_version: 4, status: 'available' } } };
  };
  const commerce = {
    confirmRecommendation: async (...args) => { calls.push(args); return { purchase_list_sn: 'list-A', version: 5, status: 'ready' }; },
    addPurchaseList: async (...args) => { calls.push(args); return { items: [] }; },
  };
  const flow = createMealPurchaseFlow({ send, commerce, context: () => scope, onChange: s => { state = s; } });
  return { flow, calls, state: () => state, switch: () => { scope = 'B'; flow.reset(); }, defer: fn => { late = fn; } };
}

test('approved adoption uses explicit inventory, server package version and saved list to add to cart', async () => {
  const f = fixture(); await f.flow.open('2026-10-19');
  await f.flow.prepare([]); await f.flow.confirm(); await f.flow.add();
  const body = f.calls.find(o => o.path?.endsWith('/commerce-recommendations')).data;
  assert.deepEqual(body, { adoption_id: 'adopted-A', adoption_version: 2, plan_version: 3, inventory_confirmed: true, inventory: [] });
  assert.deepEqual(f.calls.slice(-2), [['pkg-A', 4], ['list-A', 5]]);
  assert.equal(f.state().cartAdded, true);
  assert.equal('nutrition_validation' in body, false);
});
test('missing configuration or adopted plan never generates a substitute menu', async () => {
  for (const options of [{ configured: false }, { adopted: false }]) {
    const f = fixture(options); await f.flow.open('2026-10-19'); await f.flow.prepare();
    assert.equal(f.calls.some(o => o.path?.endsWith('/commerce-recommendations')), false);
    assert.equal(f.state().package, null);
  }
});
test('late export response cannot appear under another account or family', async () => {
  const f = fixture(); await f.flow.open('2026-10-19'); let release;
  f.defer(() => new Promise(resolve => { release = resolve; }));
  const pending = f.flow.prepare(); await Promise.resolve(); f.switch();
  release({ data: { source: 'approved_adopted_plan', package: { package_sn: 'old-A', status: 'available' } } });
  await pending; assert.equal(f.state().package, null); assert.equal(f.state().plan, null);
});
test('revoked source clears health projections and blocks adding old lists', async () => {
  for (const fields of [{ code: 410 }, { code: 40944, status: 409 }]) {
    const f = fixture(); await f.flow.open('2026-10-19');
    f.defer(() => Promise.reject(Object.assign(new Error('source revoked'), fields)));
    await f.flow.prepare(); await f.flow.add();
    assert.equal(f.state().plan, null); assert.equal(f.state().requirements, null);
    assert.equal(f.calls.some(Array.isArray), false);
  }
});
