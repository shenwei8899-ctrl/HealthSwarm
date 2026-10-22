const failure = (message, code, extra = {}) =>
  Object.assign(new Error(message), { code, ...extra });
const id = (value) => encodeURIComponent(String(value));

export function createCommerceClient({
  baseUrl,
  transport,
  uploadTransport,
  parent,
  storage,
  randomKey,
  getWechatCode,
  appId,
  pay,
  activateIdentity,
  deactivateIdentity,
  allowProxy = false,
  authMode = 'member',
}) {
  const url = (baseUrl || "").replace(/\/$/, "");
  const prefix = "/api/v1/commerce";
  const key = () =>
    "fn-commerce-v1:" + encodeURIComponent(url) + ":" + (parent.storageScope?.() || parent.scope());
  let loginGeneration = 0;
  let connecting = null;
  function current(scope) {
    if (scope !== parent.scope())
      throw failure("账号或家庭已切换，请重新操作", "SESSION_CHANGED");
  }
  function read() {
    return storage.get(key()) || {};
  }
  function save(value) {
    storage.set(key(), value);
  }
  // A direct member login authenticates commerce only; it never creates an Agent identity.
  const isAgentMode = () => authMode === 'agent';
  function configured() {
    if (allowProxy && url === "/commerce-api") return;
    if (
      !/^https:\/\/[^/]+/.test(url) &&
      !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(url)
    )
      throw failure("商城服务尚未配置", "COMMERCE_NOT_CONFIGURED");
  }
  function unwrap(response, scope, expectedToken) {
    current(scope);
    const status = Number(response.statusCode);
    let body;
    try {
      body =
        typeof response.data === "string"
          ? JSON.parse(response.data)
          : response.data;
    } catch {
      if (status !== 401)
        throw failure("商城返回异常，请稍后重试", "INVALID_RESPONSE");
    }
    if (status === 401 || [401, 40100].includes(body?.code)) {
      if (!expectedToken) throw failure(body?.message || "商城登录失败，请检查账号和密码", body?.code || status, { status });
      if (expectedToken && read().session?.token === expectedToken)
        save({ ...read(), session: null });
      throw failure("商城登录已过期，请重新进入", 401);
    }
    if (status < 200 || status >= 300 || body?.code !== 0)
      throw failure(
        body?.message || body?.msg || "请求未完成，请重试",
        body?.code || status,
        { status, traceId: body?.request_id, details: body?.data },
      );
    return body.data;
  }
  async function send(path, options = {}, header = {}) {
    configured();
    const scope = parent.scope(), revision = read().session?.revision;
    let response;
    try {
      response = await transport({
        url: url + prefix + path,
        method: options.method || "GET",
        data: options.data,
        timeout: 15000,
        header: {
          "Content-Type": "application/json",
          ...header,
          ...(options.key ? { "Idempotency-Key": options.key } : {}),
        },
      });
    } catch {
      current(scope);
      throw failure(
        "网络暂不可用，操作结果尚未确认，请重试原操作",
        "NETWORK_ERROR",
      );
    }
    if (revision !== read().session?.revision) throw failure("商城账号已切换，请重新操作", "SESSION_CHANGED");
    return unwrap(response, scope, header.token);
  }
  async function connect() {
    const scope = parent.scope(), session = read().session;
    if (session?.token && session.scope === scope && (!isAgentMode() || session.agentAccountId === String(parent.read()?.accountId))) return session;
    if (isAgentMode()) {
      if (!connecting || connecting.scope !== scope) {
        const pending = exchangeAgent();
        const entry = { scope, pending };
        connecting = entry;
        pending.finally(() => { if (connecting === entry) connecting = null; }).catch(() => {});
      }
      return connecting.pending;
    }
    throw failure("请先登录商城账号", 401);
  }
  async function request(path, options = {}) {
    const scope = parent.scope();
    const session = options.auth === false ? null : await connect();
    current(scope);
    return send(path, options, session ? { token: session.token } : {});
  }
  async function mutate(path, method = "POST", data = {}) {
    const scope = parent.scope(),
      signature = JSON.stringify([path, method, data]);
    const state = read(),
      intents = state.intents || {};
    const intent = intents[signature] || randomKey();
    save({ ...state, intents: { ...intents, [signature]: intent } });
    try {
      const result = await request(path, { method, data, key: intent });
      current(scope);
      const next = { ...(read().intents || {}) };
      delete next[signature];
      save({ ...read(), intents: next });
      return result;
    } catch (error) {
      if (
        scope === parent.scope() &&
        Number(error.status) >= 400 &&
        Number(error.status) < 500 &&
        !error.details?.retryable &&
        Number(error.code) !== 40902 &&
        ![401, 40100].includes(Number(error.code))
      ) {
        const next = { ...(read().intents || {}) };
        delete next[signature];
        save({ ...read(), intents: next });
      }
      throw error;
    }
  }
  async function upload(filePath) {
    const scope = parent.scope(),
      session = await connect();
    current(scope);
    configured();
    let response;
    try {
      response = await uploadTransport({
        url: url + prefix + "/media/evidence",
        filePath,
        name: "file",
        header: { token: session.token },
        timeout: 30000,
      });
    } catch {
      current(scope);
      throw failure("照片上传未完成，请重试", "NETWORK_ERROR");
    }
    const result = unwrap(response, scope, session.token);
    if (!/^https?:\/\//.test(result?.url || ""))
      throw failure("照片上传返回异常", "INVALID_MEDIA");
    return result.url;
  }
  async function payOrder(orderId) {
    const scope = parent.scope();
    if (!getWechatCode || !pay || !/^wx[0-9a-f]{16}$/i.test(appId || ""))
      throw failure("请在已配置的小程序中支付", "WECHAT_PLATFORM_REQUIRED");
    if (isAgentMode()) {
      const account = parent.read(), session = await connect();
      current(scope);
      if (!account?.token || account.isDemo) throw failure('请先登录小程序账号', 401);
      const code = await getWechatCode();
      current(scope);
      if (session.revision !== read().session?.revision) throw failure('商城账号已切换，请重新操作', 'SESSION_CHANGED');
      if (typeof code !== 'string' || !code || code.length > 256) throw failure('微信未返回有效凭证，请重试', 'INVALID_WECHAT_CODE');
      // A fresh code must never enter the persisted mutation-intent queue.
      const identity = await send('/session/wechat-payment-identity', { method: 'POST', data: { code } },
        { token: session.token, Authorization: 'Bearer ' + account.token });
      if (identity?.linked !== true || identity.app_id !== appId) throw failure('微信支付身份验证返回异常', 'INVALID_WECHAT_IDENTITY');
    }
    const payment = await mutate("/orders/" + id(orderId) + "/payments/wechat");
    current(scope);
    if (!payment?.payment_params)
      throw failure("支付参数返回异常", "INVALID_PAYMENT");
    let interrupted = false;
    try {
      await pay(payment.payment_params);
    } catch {
      interrupted = true;
    }
    current(scope);
    const result = await request("/orders/" + id(orderId) + "/payment-status");
    return { ...result, interrupted };
  }
  const query = (object) =>
    "?" +
    Object.entries(object)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => id(k) + "=" + id(v))
      .join("&");
  async function login(credentials) {
    if (isAgentMode()) return exchangeAgent(credentials);
    return loginWithMember(credentials);
  }
  async function loginMember(credentials) {
    if (isAgentMode()) throw failure('请使用微信登录后继续采购', 'STANDALONE_LOGIN_DISABLED');
    if (!credentials?.account?.trim() || !credentials?.password) throw failure('请填写商城会员账号和密码', 'INVALID_CREDENTIALS');
    return loginWithMember({ account: credentials.account.trim(), password: credentials.password });
  }
  async function loginWithMember(credentials) {
    const generation = ++loginGeneration, scope = parent.scope();
    const wechat = !credentials;
    if (wechat && (!getWechatCode || !/^wx[0-9a-f]{16}$/i.test(appId || "")))
      throw failure("微信登录尚未配置，请先配置真实 AppID", "WECHAT_NOT_CONFIGURED");
    const data = wechat ? { code: await getWechatCode() } : credentials;
    if (generation !== loginGeneration) throw failure("登录已取消", "SESSION_CHANGED");
    current(scope);
    const result = await send(wechat ? "/session/wechat" : "/session/login", { method: "POST", data });
    if (generation !== loginGeneration) throw failure("登录已取消", "SESSION_CHANGED");
    current(scope);
    return acceptLogin(result, 'member');
  }
  function acceptLogin(result, loginMode) {
    if (!result?.user?.token || !Number.isSafeInteger(Number(result.user.id)) || Number(result.user.id) <= 0) throw failure("商城登录返回异常", "INVALID_RESPONSE");
    const userId = String(result.user.id), previous = read();
    if (previous.userId) storage.set(key() + ":member:" + previous.userId, { intents: previous.intents || {} });
    // The identity hook runs only after the server has authenticated this member.
    activateIdentity?.({ ...result, userId });
    const memberState = read();
    const retained = memberState.userId === userId ? memberState : storage.get(key() + ":member:" + userId) || {};
    const session = { token: result.user.token, userId, scope: parent.scope(), revision: randomKey(), identityNamespace: result.identity_namespace, localTestPayment: result.local_test_payment === true,
      ...(loginMode === 'agent' ? { agentAccountId: String(result.agent_account_id) } : {}) };
    save({ ...retained, loginMode, userId, session });
    return session;
  }
  async function exchangeAgent(payload = {}) {
    if (Object.keys(payload).length) throw failure('商城会员由当前微信身份自动衔接', 'AUTOMATIC_IDENTITY_REQUIRED');
    const generation = ++loginGeneration, scope = parent.scope(), account = parent.read();
    if (!account?.token || !account.accountId || account.isDemo || account.authSource === 'commerce') throw failure('请先登录小程序账号', 401);
    const result = await send('/session/exchange', { method: 'POST', data: payload }, { Authorization: 'Bearer ' + account.token });
    if (generation !== loginGeneration) throw failure('登录已取消', 'SESSION_CHANGED');
    current(scope);
    if (parent.read()?.token !== account.token || parent.read()?.accountId !== account.accountId) throw failure('登录状态已变更，请重新操作', 'SESSION_CHANGED');
    if (String(result?.agent_account_id) !== String(account.accountId)) throw failure('商城返回的关联身份不一致', 'INVALID_IDENTITY');
    return acceptLogin(result, 'agent');
  }
  async function logout() {
    ++loginGeneration;
    const scope = parent.scope(), state = read();
    try { if (state.session?.token) await send("/session", { method: "DELETE" }, { token: state.session.token }); }
    finally { current(scope); if (read().session?.token === state.session?.token) { save({ ...read(), session: null }); deactivateIdentity?.(state.session); } }
  }
  return {
    login, loginMember, logout, exchange: exchangeAgent,
    isMemberLogin: () => read().loginMode === 'member',
    cancelLogin: () => { ++loginGeneration; },
    session: () => { const session = read().session; return session?.scope === parent.scope() && (!isAgentMode() || read().loginMode === 'agent' && session.agentAccountId === String(parent.read()?.accountId)) ? session : null; },
    sessionRevision: () => read().session?.revision || read().session?.token || "guest",
    restore: async () => {
      let session = await connect(), result;
      try { result = await request('/session'); }
      catch (error) {
        // Refresh only the read-only session check. Never retry a cart/order write here.
        if (!isAgentMode() || Number(error.code) !== 401) throw error;
        session = await connect();
        result = await request('/session');
      }
      if (!result.user?.id) throw failure("商城身份返回异常，请重试", "INVALID_RESPONSE");
      if (result.user && String(result.user.id) !== session.userId || session.identityNamespace && result.identity_namespace !== session.identityNamespace) {
        save({ ...read(), session: null }); throw failure("商城身份已变化，请重新登录", 401);
      }
      const previous = read();
      activateIdentity?.({ ...result, userId: session.userId });
      const refreshed = { ...session, scope: parent.scope(), identityNamespace: result.identity_namespace || session.identityNamespace, localTestPayment: result.local_test_payment === true };
      const state = read().userId === session.userId ? read() : previous;
      save({ ...state, session: refreshed }); return refreshed;
    },
    areas: async () => (await request("/areas?tree=1")).items,
    connect,
    request,
    mutate,
    upload,
    payOrder,
    pendingOrder: () =>
      Object.keys(read().intents || {})
        .map((signature) => JSON.parse(signature))
        .find(
          ([path, method]) => path === "/orders" && method === "POST",
        )?.[2] || null,
    retryOrder: async () => {
      const pending = Object.keys(read().intents || {})
        .map((signature) => JSON.parse(signature))
        .find(([path, method]) => path === "/orders" && method === "POST");
      if (!pending)
        throw failure("没有待确认的下单操作，请刷新订单", "NO_PENDING_ORDER");
      return mutate("/orders", "POST", pending[2]);
    },
    products: (cursor) =>
      request("/products" + query({ limit: 30, cursor }), { auth: false }),
    meal: (meal = "dinner", date) => request("/meals/current" + query({ meal, date })),
    mealPackage: (sn, version) => request("/meals/packages/" + id(sn) + query({ version })),
    addMeal: (menu) => mutate("/meals/cart", "POST", { package_sn: menu.package_sn, package_version: menu.package_version }),
    cooking: (orderId) => request("/orders/" + id(orderId) + "/cooking"),
    localTestPay: async (orderId) => {
      if (!read().session?.localTestPayment) throw failure("本地测试支付未启用", "LOCAL_PAYMENT_DISABLED");
      return mutate("/local-test/orders/" + id(orderId) + "/pay");
    },
    cart: () => request("/cart"),
    recommendation: (sn) => request('/recommendation-packages/' + id(sn)),
    confirmRecommendation: (sn, version) => mutate('/recommendation-packages/' + id(sn) + '/purchase-list', 'POST', { package_version: version }),
    purchaseLists: () => request('/purchase-lists'),
    purchaseList: (sn) => request('/purchase-lists/' + id(sn)),
    addPurchaseList: (sn, version) => mutate('/purchase-lists/' + id(sn) + '/cart', 'POST', { version }),
    add: (sku, quantity = 1) =>
      mutate("/cart/items", "POST", { sku_id: sku, quantity }),
    quantity: (line, quantity) =>
      mutate("/cart/items/" + id(line.cart_item_id), "PUT", {
        quantity,
        version: line.version,
      }),
    select: (line, selected) =>
      mutate("/cart/items/" + id(line.cart_item_id) + "/selection", "PUT", {
        selected,
        version: line.version,
      }),
    remove: (line) =>
      mutate("/cart/items/" + id(line.cart_item_id), "DELETE", {
        version: line.version,
      }),
    addresses: async () => (await request("/addresses")).items,
    saveAddress: (address) =>
      mutate(
        "/addresses" + (address.id ? "/" + id(address.id) : ""),
        address.id ? "PUT" : "POST",
        address,
      ),
    selectAddress: (addressId) =>
      mutate("/addresses/" + id(addressId) + "/default", "PUT"),
    slots: (addressId) =>
      request("/delivery/slots" + query({ address_id: addressId })),
    quote: async (lines, addressId, slotId = 0, menu = null) => {
      const session = await connect();
      return mutate("/checkout/preview", "POST", {
        ...(menu ? { meal_package_sn: menu.package_sn, meal_package_version: menu.package_version } : {}),
        source_type: "cart",
        source_ref: session.userId,
        source_version: 1,
        address_id: addressId,
        delivery_slot_id: slotId,
        cart_items: lines
          .filter((line) => line.selected)
          .map((line) => ({
            cart_item_id: line.cart_item_id,
            version: line.version,
          })),
      });
    },
    quoteRecommendation: (sn, version, addressId, slotId) => mutate('/checkout/preview', 'POST', {
      source_type:'recommendation_package', source_ref:sn, source_version:version,
      address_id:addressId, delivery_slot_id:slotId,
    }),
    createOrder: (token) =>
      mutate("/orders", "POST", { checkout_token: token }),
    orders: async (page = 1) => {
      const r = await request("/orders" + query({ page, page_size: 20 }));
      return { ...r, items: r.items.map(orderView) };
    },
    order: async (orderId) =>
      orderView(await request("/orders/" + id(orderId))),
    paymentStatus: (orderId) =>
      request("/orders/" + id(orderId) + "/payment-status"),
    action: async (orderId, action) => {
      if (!["cancel", "receipt"].includes(action))
        throw failure("订单操作无效", "INVALID_ACTION");
      await mutate("/orders/" + id(orderId) + "/" + action);
      return orderView(await request("/orders/" + id(orderId)));
    },
    repurchase: (orderId) => mutate("/orders/" + id(orderId) + "/repurchase"),
    logistics: (orderId) => request("/orders/" + id(orderId) + "/fulfillment"),
    eligibility: (orderId) =>
      request("/orders/" + id(orderId) + "/aftersales/eligibility"),
    pendingAfterSale: (orderId) =>
      Object.keys(read().intents || {})
        .map((signature) => JSON.parse(signature))
        .find(
          ([path, method, data]) =>
            path === "/aftersales" &&
            method === "POST" &&
            data.order_sn === orderId,
        )?.[2] || null,
    retryAfterSale: (orderId) => {
      const pending = Object.keys(read().intents || {})
        .map((signature) => JSON.parse(signature))
        .find(
          ([path, method, data]) =>
            path === "/aftersales" &&
            method === "POST" &&
            data.order_sn === orderId,
        );
      if (!pending)
        throw failure("没有待确认的售后申请", "NO_PENDING_AFTERSALE");
      return mutate("/aftersales", "POST", pending[2]).then(result => ({ items: [result] }));
    },
    submitAfterSale: async (payload) => {
      if (payload.items.length !== 1) throw failure("请每次选择一件商品申请售后", "INVALID_AFTERSALE");
      const { items, ...common } = payload;
      const result = await mutate("/aftersales", "POST", { ...common, ...items[0] });
      return { items: [result] };
    },
    afterSales: async (orderId) =>
      (await request("/orders/" + id(orderId) + "/aftersales")).items,
  };
}

export function orderView(result) {
  const order = result.order || result,
    ext = result.extension || order;
  const paymentStatus =
    ext.payment_status || (Number(order.paystate) === 1 ? "paid" : "unpaid");
  let status = "pending",
    label = "待支付";
  if (Number(order.orderstate) === 1 || ext.business_status === "cancelled") {
    status = "cancelled";
    label = "已取消";
  } else if (
    Number(order.orderstate) === 2 ||
    ext.business_status === "closed"
  ) {
    status = "cancelled";
    label = "已关闭";
  } else if (
    Number(order.orderstate) === 4 ||
    ["refunding", "refund_pending"].includes(paymentStatus)
  ) {
    status = "refund_pending";
    label = "售后处理中";
  } else if (
    Number(order.orderstate) === 3 ||
    Number(order.shippingstate) === 2
  ) {
    status = "delivered";
    label = "已完成";
  } else if (paymentStatus === "paid" || Number(order.paystate) === 1) {
    status = Number(order.shippingstate) === 1 ? "shipping" : "paid";
    label = status === "shipping" ? "配送中" : "待配送";
  } else if (paymentStatus === "paying") label = "支付结果待确认";
  return {
    id: String(order.order_sn),
    type: order.order_type,
    status,
    label,
    paymentStatus,
    isDemo: false,
    localTestPayment: result.local_test_payment === true,
    mealSnapshot: ext.pricing_snapshot?.meal_snapshot || null,
    totalCents: Math.round(Number(order.saleamount || 0) * 100),
    createdAt: Number(order.createtime || 0) * 1000,
    allowedActions: result.allowed_actions || order.allowed_actions || [],
    address: ext.address_snapshot || null,
    items: (result.items || order.items || []).map((line) => ({
      ...line,
      name: line.sku_snapshot?.product_name || line.title || "",
      image: line.sku_snapshot?.image_url || "",
      id: String(line.order_goods_id || line.id),
      quantity: Number(line.quantity || line.nums),
      priceCents: Number(line.unit_price_cent || 0),
    })),
    batches: result.delivery_batches || [],
    plan: result.plan_order || null,
    raw: result,
  };
}
