import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ref, computed } from "vue";

function fixture() {
  let scope = "A",
    show,
    unload,
    mounted;
  const deps = {
    ref,
    computed,
    storageContext: () => scope,
    onShow: (cb) => {
      show = cb;
    },
    onUnload: (cb) => {
      unload = cb;
    },
    onMounted: (cb) => {
      mounted = cb;
    },
  };
  const code = readFileSync(
    new URL("../src/services/commerce-page.js", import.meta.url),
    "utf8",
  )
    .replace(/^import .*$/gm, "")
    .replace("export function", "function");
  deps.useCommercePage = new Function(
    "deps",
    `const {${Object.keys(deps)}}=deps;${code};return useCommercePage`,
  )(deps);
  return {
    deps,
    show: () => show?.(),
    unload: () => unload?.(),
    mount: () => mounted?.(),
    switch: () => {
      scope = "B";
    },
  };
}

function detail(h, commerce) {
  const deps = {
    ...h.deps,
    commerce,
    defineProps: () => ({ id: "REAL-ORDER" }),
  };
  const code = readFileSync(
    new URL("../src/components/CommerceOrderDetail.vue", import.meta.url),
    "utf8",
  )
    .match(/<script setup>([\s\S]*?)<\/script>/)[1]
    .replace(/^import .*$/gm, "");
  return new Function(
    "deps",
    `const {${Object.keys(deps)}}=deps;${code};return {orderId,order,form,busy,error,afterSale,photo,pay}`,
  )(deps);
}

test("page scope rejects late results and clears private state on account change", async () => {
  const h = fixture(),
    data = ref("A private"),
    { run } = h.deps.useCommercePage(() => {
      data.value = "";
    });
  let resolve;
  const pending = run(async (active) => {
    await new Promise((r) => {
      resolve = r;
    });
    if (active()) data.value = "late A";
  });
  h.switch();
  h.show();
  resolve();
  await pending;
  assert.equal(data.value, "");
});

test("real detail mounts with page-owned order ID and photo picker preserves the form", async () => {
  const h = fixture(),
    calls = [];
  const commerce = {
    order: async (id) => {
      calls.push(id);
      return { id, type: "normal", allowedActions: ["afterSale"] };
    },
    afterSales: async () => [],
    pendingAfterSale: () => null,
    eligibility: async () => ({
      allowed_reason_codes: ["other"],
      items: [{ id: 1, nums: 2, eligible: true, title: "Real product" }],
    }),
    upload: async () => "https://shop.example.test/uploads/photo.jpg",
  };
  const page = detail(h, commerce);
  await h.mount();
  assert.equal(page.orderId.value, "REAL-ORDER");
  assert.deepEqual(calls, ["REAL-ORDER"]);
  await page.afterSale();
  globalThis.uni = {
    chooseImage(options) {
      h.show();
      options.success({ tempFilePaths: ["/tmp/photo.jpg"] });
    },
  };
  await page.photo();
  assert.deepEqual(page.form.value.evidence_urls, [
    "https://shop.example.test/uploads/photo.jpg",
  ]);
  assert.equal(page.error.value, "");
  assert.equal(page.busy.value, false);
});

test("return from native payment preserves its work and rereads the server order", async () => {
  const h = fixture();
  let paid = false;
  const commerce = {
    order: async (id) => ({
      id,
      status: paid ? "paid" : "pending",
      allowedActions: ["pay"],
    }),
    afterSales: async () => [],
    pendingAfterSale: () => null,
    payOrder: async () => {
      h.show();
      paid = true;
      return { status: "paid" };
    },
  };
  const page = detail(h, commerce);
  await h.mount();
  await page.pay();
  assert.equal(page.order.value.status, "paid");
  assert.equal(page.busy.value, false);
  h.unload();
  assert.equal(page.order.value, null);
});


test("expired commerce credentials remove the protected view immediately", async () => {
  let session = { token: "valid" }, changed, mounted;
  const deps = {ref, defineProps:()=>({entry:false}), defineEmits:()=>()=>{}, usesCommerceIdentity:false, onMounted: cb => {mounted=cb}, onShow: () => {},
    watch: (_, cb) => {changed=cb}, commerceSessionEpoch: ref(0),
    commerceContext: () => session?.token || "guest",
    commerce: {session:()=>session,restore:async()=>session},
  };
  const code=readFileSync(new URL("../src/components/CommerceAccess.vue",import.meta.url),"utf8")
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,"");
  const page=new Function("deps",`const {${Object.keys(deps)}}=deps;${code};return {ready,error}`)(deps);
  await mounted(); assert.equal(page.ready.value,true);
  session=null; changed();
  assert.equal(page.ready.value,false); assert.match(page.error.value,/重新登录/);
});

function shop(delivery) {
  const h = fixture();
  let quoteCalls = 0;
  const commerce = {
    products: async () => ({ items: [{ sku_id: 'EXCEL-SKU', product_name: 'Excel imported product' }], next_cursor: '', has_more: false }),
    cart: async () => ({ items: [{ selected: true, valid: true }] }),
    addresses: async () => [{ id: 'ADDRESS', isDefault: true }],
    pendingOrder: () => null,
    slots: () => delivery(),
    quote: async () => { quoteCalls++; return { checkout_token: 'quote' }; },
  };
  const deps = { ...h.deps, commerce, defineProps: () => ({ route: {} }) };
  const code = readFileSync(new URL('../src/components/CommerceShop.vue', import.meta.url), 'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '');
  const page = new Function('deps', `const {${Object.keys(deps)}}=deps;${code};return {products,cart,ready,error,deliveryState,deliveryMessage,quote,load,preview,retryDelivery}`)(deps);
  return { page, quotes: () => quoteCalls };
}

test('unsupported address preserves Excel products and cart while blocking checkout', async () => {
  const { page, quotes } = shop(async () => ({ supported: false, reason_code: 'area_disabled', message: '该地区暂停配送', items: [] }));
  await page.load();
  assert.equal(page.products.value[0].sku_id, 'EXCEL-SKU');
  assert.equal(page.cart.value.length, 1);
  assert.equal(page.ready.value, true);
  assert.equal(page.error.value, '');
  assert.equal(page.deliveryState.value, 'unsupported');
  assert.equal(page.deliveryMessage.value, '该地区暂停配送');
  await page.preview();
  assert.equal(quotes(), 0);
});

test('delivery network failure stays distinct from out of range and can be retried', async () => {
  let available = false;
  const { page, quotes } = shop(async () => {
    if (!available) throw Object.assign(new Error('Network offline'), { code: 'NETWORK_ERROR' });
    return { supported: true, items: [] };
  });
  await page.load();
  assert.equal(page.products.value.length, 1);
  assert.equal(page.error.value, '');
  assert.equal(page.deliveryState.value, 'error');
  await page.preview();
  assert.equal(quotes(), 0);
  available = true;
  await page.retryDelivery();
  assert.equal(page.deliveryState.value, 'supported');
  await page.preview();
  assert.equal(quotes(), 1);
});

test('legacy backend coverage rejection is shown only beside the address', async () => {
  const { page } = shop(async () => { throw Object.assign(new Error('当前地址不在配送范围'), { code: 40914 }); });
  await page.load();
  assert.equal(page.deliveryState.value, 'unsupported');
  assert.equal(page.products.value.length, 1);
  assert.equal(page.error.value, '');
});
