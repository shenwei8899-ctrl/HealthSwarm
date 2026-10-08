(global["webpackJsonp"] = global["webpackJsonp"] || []).push([["common/vendor"],{

/***/ 1:
/*!*********************************************************!*\
  !*** ./node_modules/@dcloudio/uni-mp-weixin/dist/wx.js ***!
  \*********************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
const objectKeys = ['qy', 'env', 'error', 'version', 'lanDebug', 'cloud', 'serviceMarket', 'router', 'worklet', '__webpack_require_UNI_MP_PLUGIN__'];
const singlePageDisableKey = ['lanDebug', 'router', 'worklet'];
const target = typeof globalThis !== 'undefined' ? globalThis : function () {
  return this;
}();
const key = ['w', 'x'].join('');
const oldWx = target[key];
const launchOption = oldWx.getLaunchOptionsSync ? oldWx.getLaunchOptionsSync() : null;
function isWxKey(key) {
  if (launchOption && launchOption.scene === 1154 && singlePageDisableKey.includes(key)) {
    return false;
  }
  return objectKeys.indexOf(key) > -1 || typeof oldWx[key] === 'function';
}
function initWx() {
  const newWx = {};
  for (const key in oldWx) {
    if (isWxKey(key)) {
      // TODO wrapper function
      newWx[key] = oldWx[key];
    }
  }
  return newWx;
}
target[key] = initWx();
if (!target[key].canIUse('getAppBaseInfo')) {
  target[key].getAppBaseInfo = target[key].getSystemInfoSync;
}
if (!target[key].canIUse('getWindowInfo')) {
  target[key].getWindowInfo = target[key].getSystemInfoSync;
}
if (!target[key].canIUse('getDeviceInfo')) {
  target[key].getDeviceInfo = target[key].getSystemInfoSync;
}
/* harmony default export */ __webpack_exports__["default"] = (target[key]);

/***/ }),

/***/ 10:
/*!********************!*\
  !*** ./pages.json ***!
  \********************/
/*! no static exports found */
/***/ (function(module, exports) {



/***/ }),

/***/ 11:
/*!********************************************************************!*\
  !*** ./node_modules/@dcloudio/uni-stat/dist/uni-stat-public.es.js ***!
  \********************************************************************/
/*! exports provided: __resetInstall, __resetStatApp, getStatApp, installPublicStat */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni, global) {/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "__resetInstall", function() { return __resetInstall; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "__resetStatApp", function() { return __resetStatApp; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "getStatApp", function() { return getStatApp; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "installPublicStat", function() { return installPublicStat; });
/**
 * 事件类型与会话创建类型常量。
 *
 * 与私有版 / 文档 `uni统计上报参数.md` 的兼容关系：
 *   - 上行参数文档明确：`lt` 仅取 `1 / 3 / 11 / 21 / 31 / 41`，**没有** `lt=0`。
 *   - 历史架构文档（03-公有版架构设计.md §3.2）曾设计 `lt=0` 作为"客户端 session 边界"事件，
 *     但与服务端入库口径不一致（会话日志 = lt=1），已**整体移除**：
 *     新会话直接发一条 lt=1，会话字段（`sid / cst / fvts / lvts / tvc`）随 lt=1 上行。
 *   - 因此 `LT` 不再包含 `Session`；删除 lt=0 不影响老接收端。
 */
/**
 * Log Type（事件类型）。统一在此声明，禁止其他模块裸写字符串。
 *
 * 注：`lt=41`（uni-app x 原生崩溃日志）暂未在公有版实现，详见 `docs/暂未实现字段说明.md`。
 */
const LT = {
  Launch: '1',
  Hide: '3',
  Page: '11',
  Event: '21',
  Error: '31',
  Push: '101'
};
/**
 * Create Session Type / Session Create Type（同义）。
 *
 * - `1` 冷启动：进程刚起，第一次创建会话。
 * - `2` 后台超时：从后台返回前台，间隔 >= `backgroundTimeoutSec`（秒）。
 * - `3` 前台无操作超时：在前台一段时间无任何 page/event 触达。
 *
 * 公有版预留 `0` 给"未触发新会话"的零值；不要用 0 覆写 storage，仅作为内部哨兵。
 */
const CST = {
  ColdLaunch: 1,
  BackgroundTimeout: 2,
  PageInactiveTimeout: 3
};
/**
 * 入口页标记。
 *
 * `iey` / `ppiey` 上行字段以 `0/1` 形式表达布尔，与私有版数字风格保持一致。
 */
const IEY = {
  No: 0,
  Yes: 1
};
/**
 * 把任意输入归一化为 `IEYValue`。
 *
 * 用于 `domain/entry` 在拼装字段时统一布尔→0/1。`true / 1 / '1'` 均视为 Yes。
 */
function toIey(input) {
  if (input === true || input === 1 || input === '1') return IEY.Yes;
  return IEY.No;
}

/******************************************************************************
Copyright (c) Microsoft Corporation.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
***************************************************************************** */
/* global Reflect, Promise, SuppressedError, Symbol, Iterator */

function __awaiter(thisArg, _arguments, P, generator) {
  function adopt(value) {
    return value instanceof P ? value : new P(function (resolve) {
      resolve(value);
    });
  }
  return new (P || (P = Promise))(function (resolve, reject) {
    function fulfilled(value) {
      try {
        step(generator.next(value));
      } catch (e) {
        reject(e);
      }
    }
    function rejected(value) {
      try {
        step(generator["throw"](value));
      } catch (e) {
        reject(e);
      }
    }
    function step(result) {
      result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected);
    }
    step((generator = generator.apply(thisArg, _arguments || [])).next());
  });
}
typeof SuppressedError === "function" ? SuppressedError : function (error, suppressed, message) {
  var e = new Error(message);
  return e.name = "SuppressedError", e.error = error, e.suppressed = suppressed, e;
};

/**
 * 安全工具集：序列化、try 包裹、指数退避重试。
 *
 * 修复缺陷：
 *   - #1 `_retry` 未初始化导致重试链路 NaN（公有版直接以参数显式传 `times`）。
 *   - #7 取值反向（私有版 `if (data.length > MAX_LENGTH)` 误判）。
 *   - #8 循环引用导致 `JSON.stringify` 抛错（用 WeakSet replacer 兜底）。
 */
const DEFAULT_MAX_LENGTH = 4096;
const TRUNCATED_SUFFIX = '…[truncated]';
/**
 * 序列化任意值为字符串：支持循环引用与最大长度截断。
 *
 * @param value 待序列化的值。`undefined` 返回 ''；string 直接返回（仍参与截断）。
 * @param max   字符串最大长度，默认 4096；超长会截断并附 `…[truncated]`。
 */
function safeStringify(value, max = DEFAULT_MAX_LENGTH) {
  var _a;
  if (value === undefined) return '';
  let raw;
  if (typeof value === 'string') {
    raw = value;
  } else {
    const seen = new WeakSet();
    try {
      raw = (_a = JSON.stringify(value, (_key, val) => {
        if (typeof val === 'object' && val !== null) {
          if (seen.has(val)) return '[Circular]';
          seen.add(val);
        }
        if (typeof val === 'bigint') return val.toString();
        if (typeof val === 'function') return `[Function ${val.name || 'anonymous'}]`;
        return val;
      })) !== null && _a !== void 0 ? _a : '';
    } catch (e) {
      raw = `[Unserializable: ${e.message}]`;
    }
  }
  if (raw.length > max) {
    return raw.slice(0, Math.max(0, max - TRUNCATED_SUFFIX.length)) + TRUNCATED_SUFFIX;
  }
  return raw;
}
/**
 * 包裹同步函数，捕获任何抛出，返回 fallback。
 *
 * 不打印 console（由调用方按需 `logger.warn`）；保持纯函数风格便于热路径使用。
 */
function tryRun(fn, fallback) {
  try {
    return fn();
  } catch (_a) {
    return fallback;
  }
}
/**
 * 指数退避重试：失败时按 `baseDelayMs * 2^(n-1)` 等待后重试，全部失败抛出最后一个错误。
 *
 * @example
 *   await withRetry(() => fetch(url), { times: 3, baseDelayMs: 200 })
 *   // 第 1 次失败 → wait 200ms；第 2 次失败 → wait 400ms；第 3 次失败 → throw
 */
function withRetry(fn, opts) {
  return __awaiter(this, void 0, void 0, function* () {
    var _a;
    const total = Math.max(1, Math.floor(opts.times));
    const sleep = (_a = opts.sleep) !== null && _a !== void 0 ? _a : defaultSleep;
    let lastErr;
    for (let attempt = 1; attempt <= total; attempt++) {
      try {
        return yield fn();
      } catch (e) {
        lastErr = e;
        if (attempt >= total) break;
        yield sleep(opts.baseDelayMs * Math.pow(2, attempt - 1));
      }
    }
    throw lastErr;
  });
}
function defaultSleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 解析 uni-app 运行时根对象 `uni`。
 *
 * - H5 / App：常见为 `globalThis.uni`。
 * - 微信小程序等：多为 Vite/rollup 向**当前模块**注入的标识符 `uni`，
 *   **未必**同步挂到 `globalThis`；仅读 `globalThis.uni` 会导致
 *   `bindLifecycle` / `uni.request` / storage 等全部静默失败。
 * - 支付宝等旧版小程序：**无 `globalThis` 标识符**，须用 `getGlobalObject()` 兜底。
 * - H5 发行摇树：`pages.json.js` 会先把 `window.uni = {}` 占位；若仍按「有 object 即用」
 *   会误把空桩当真 uni。须用 `isUsableUniRuntime` 过滤后再择源。
 *
 * 第二路依赖宿主构建对 `uni` 的注入（与业务页面同一套解析规则），
 * 类型兜底见 `packages/uni-stat/src/uni-global.d.ts`。
 */
/**
 * 判断候选 `uni` 是否具备统计 SDK 可用的最小 API 集合（排除 H5 摇树空桩 `{}`）。
 *
 * 任一核心 API 存在即视为可用；与具体平台无关，微信/QQ/抖音/支付宝/百度等
 * 完整 runtime 均满足，仅「占位空对象」会被过滤。
 */
function isUsableUniRuntime(candidate) {
  if (candidate == null || typeof candidate !== 'object') return false;
  const u = candidate;
  return typeof u.getStorageSync === 'function' || typeof u.onCreateVueApp === 'function' || typeof u.request === 'function' || typeof u.onAppShow === 'function';
}
/**
 * 读取宿主向当前模块注入的 `uni`（小程序等）；不可用时返回 `undefined`。
 */
function getModuleUniCandidate() {
  if (typeof uni === 'undefined' || uni == null || typeof uni !== 'object') {
    return undefined;
  }
  return uni;
}
/**
 * H5 兜底：在 `globalThis` / `self` 不可用时尝试读取 `window`。
 *
 * 通过 `Function` 间接访问，避免 ESLint `no-restricted-globals` 对 `window` 标识符的限制；
 * 小程序等环境执行失败时返回 `undefined`。
 */
function getWindowObject() {
  try {
    const w = Function('return typeof window !== "undefined" ? window : undefined')();
    return w != null ? w : undefined;
  } catch (_a) {
    return undefined;
  }
}
/**
 * 安全获取全局对象。
 *
 * 支付宝 / 部分旧版小程序运行时未提供 `globalThis`，直接写 `globalThis` 会
 * `ReferenceError: globalThis is not defined`，导致 install 阶段整包崩溃。
 */
function getGlobalObject() {
  if (typeof globalThis !== 'undefined' && globalThis != null) {
    return globalThis;
  }
  if (typeof global !== 'undefined' && global != null) {
    return global;
  }
  if (typeof self !== 'undefined' && self != null) {
    return self;
  }
  const win = getWindowObject();
  if (win) return win;
  return {};
}
/**
 * 用字面量 `uni.方法` 引用拼出一个可用的 `uni` facade。
 *
 * uni-app 各端构建的 API 注入器仅识别字面量成员表达式 `uni.方法`（H5 → `@dcloudio/uni-h5`，
 * 小程序 / App 同理），动态 `u.方法` 不会被注入。这里对所需 API 逐个写字面量 `uni.方法`，
 * 使其被注入后收敛为一个对象供下游适配器使用。
 *
 * 仅在 `globalThis.uni` 与模块 `uni` 均不可用时作为兜底（典型：H5 发行摇树后 `window.uni`
 * 为 `{}` 空桩）。未经注入的环境下 `uni.方法` 读到空桩 / 未声明，拼不出方法时返回 undefined。
 */
function buildInjectedUniRuntime() {
  try {
    const out = {};
    const pick = (name, fn) => {
      if (typeof fn === 'function') out[name] = fn;
    };
    // 必须逐个写字面量 `(uni as ...).方法`（emit 后为 `uni.方法`），不可别名 / 循环，否则不会被注入。
    pick('getStorageSync', uni.getStorageSync);
    pick('setStorageSync', uni.setStorageSync);
    pick('removeStorageSync', uni.removeStorageSync);
    pick('getSystemInfoSync', uni.getSystemInfoSync);
    pick('getDeviceInfo', uni.getDeviceInfo);
    pick('getAppBaseInfo', uni.getAppBaseInfo);
    pick('getWindowInfo', uni.getWindowInfo);
    pick('getNetworkType', uni.getNetworkType);
    pick('request', uni.request);
    pick('onAppShow', uni.onAppShow);
    pick('offAppShow', uni.offAppShow);
    pick('onAppHide', uni.onAppHide);
    pick('offAppHide', uni.offAppHide);
    pick('onAppLaunch', uni.onAppLaunch);
    pick('offAppLaunch', uni.offAppLaunch);
    pick('getLaunchOptionsSync', uni.getLaunchOptionsSync);
    pick('addInterceptor', uni.addInterceptor);
    pick('removeInterceptor', uni.removeInterceptor);
    pick('getPushClientId', uni.getPushClientId);
    pick('getAccountInfoSync', uni.getAccountInfoSync);
    pick('onCreateVueApp', uni.onCreateVueApp);
    return Object.keys(out).length > 0 ? out : undefined;
  } catch (_e) {
    // 未注入且 `uni` 未声明（单测 / 极端环境）→ ReferenceError，兜底返回 undefined。
    return undefined;
  }
}
/**
 * 探测 `uni` 解析路径（不改变 `resolveUniRuntime` 行为，仅用于 debug 诊断）。
 */
function probeUniRuntime() {
  const globalThisAvailable = typeof globalThis !== 'undefined';
  const g = getGlobalObject();
  const globalUni = g.uni;
  const globalThisHasUni = globalUni != null && typeof globalUni === 'object';
  const globalThisUniStub = globalThisHasUni && !isUsableUniRuntime(globalUni);
  const moduleUni = getModuleUniCandidate();
  const moduleUniDefined = moduleUni != null;
  if (isUsableUniRuntime(globalUni)) {
    return {
      resolved: true,
      source: 'globalThis',
      globalThisHasUni: true,
      globalThisUniStub: false,
      moduleUniDefined,
      globalThisAvailable,
      uni: globalUni
    };
  }
  if (isUsableUniRuntime(moduleUni)) {
    return {
      resolved: true,
      source: 'module',
      globalThisHasUni,
      globalThisUniStub,
      moduleUniDefined: true,
      globalThisAvailable,
      uni: moduleUni
    };
  }
  // globalThis / 模块 uni 均不可用（典型 H5 发行空桩）时，用注入 facade 兜底。
  const injectedUni = buildInjectedUniRuntime();
  if (isUsableUniRuntime(injectedUni)) {
    return {
      resolved: true,
      source: 'injected',
      globalThisHasUni,
      globalThisUniStub,
      moduleUniDefined,
      globalThisAvailable,
      uni: injectedUni
    };
  }
  return {
    resolved: false,
    source: 'none',
    globalThisHasUni,
    globalThisUniStub,
    moduleUniDefined,
    globalThisAvailable,
    uni: undefined
  };
}
/**
 * 返回与业务侧一致的 `uni` 运行时根对象；均不可用时返回 `undefined`。
 */
function resolveUniRuntime() {
  const probe = probeUniRuntime();
  return probe.resolved ? probe.uni : undefined;
}

/**
 * 公有版统一日志出口。
 *
 * 修复的私有版缺陷：
 *   - #19 `!!process.env.UNI_STAT_DEBUG` 在构建时若被替换为字符串 `"false"` 仍是 truthy。
 *     公有版严格使用 `=== 'true'` 判定，并允许在运行时通过 `setDebug()` 临时打开
 *     （供调试 / 灰度小流量验证）。
 *
 * 行为约定：
 *   - `debug` 受调试开关控制；其他 level 始终输出到对应的 `console.*`。
 *   - **Android / iOS 真机**：`TAG` 与正文拼成单条字符串，避免桥接丢弃第二参起。
 *   - **其它平台**：`console.*(TAG, ...args)`，对象保持原生传递。
 *
 * 兼容性：
 *   - 历史版本插件 define 误把 `process.env.UNI_STAT_DEBUG` 替换成布尔字面量
 *     （未 `JSON.stringify`），导致 dist 运行时该值为 `true`/`false` 而非 `'true'`/`'false'`。
 *     `isDebug()` 同时接受字符串 `'true'` 与布尔字面量 `true`，避免历史构建产物完全失效。
 */
const TAG = '[uni统计 2.0]';
let runtimeDebug;
/**
 * 是否屏蔽 info / warn / error。
 * `undefined`：自动——`NODE_ENV === 'test'` 时默认屏蔽，避免 Jest 用例预期失败路径刷屏。
 */
let muteNonDebug;
/**
 * 是否将日志合并为单行（Android / iOS 真机侧）。
 */
function preferSingleLineConsole() {
  return isAndroidOrIosRuntime();
}
/**
 * 是否为 App 或小程序运行在 **Android / iOS** 上（仅此类环境对对象参数做字符串化）。
 */
function isAndroidOrIosRuntime() {
  var _a, _b, _c, _d, _e, _f, _g, _h;
  const raw = (_a = "mp-weixin") !== null && _a !== void 0 ? _a : '';
  const g = getGlobalObject();
  if (raw === 'app' || raw === 'app-plus' || raw === 'app-harmony') {
    const n = (_d = (_c = (_b = g.plus) === null || _b === void 0 ? void 0 : _b.os) === null || _c === void 0 ? void 0 : _c.name) === null || _d === void 0 ? void 0 : _d.toLowerCase();
    if (!n) return false;
    if (n.includes('android')) return true;
    if (n === 'ios' || n.includes('iphone')) return true;
    return false;
  }
  if (raw.startsWith('mp-')) {
    try {
      const p = (_h = (_g = (_f = (_e = g.uni) === null || _e === void 0 ? void 0 : _e.getSystemInfoSync) === null || _f === void 0 ? void 0 : _f.call(_e)) === null || _g === void 0 ? void 0 : _g.platform) === null || _h === void 0 ? void 0 : _h.toLowerCase();
      return p === 'android' || p === 'ios';
    } catch (_j) {
      return false;
    }
  }
  return false;
}
/**
 * 在 Android/iOS 上将「对象类」参数转为可打印字符串；其余类型原样返回。
 */
function stringifyObjectArgForNative(value) {
  if (value === null || value === undefined) return value;
  if (typeof value !== 'object') return value;
  if (value instanceof Error) return `${value.name}: ${value.message}`;
  return safeStringify(value);
}
/**
 * 将单段日志参数格式化为可拼进一行文本的片段（Android/iOS 单参输出用）。
 */
function formatLogArgForNativeConsole(value) {
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (typeof value === 'bigint') return String(value);
  if (typeof value === 'symbol') {
    try {
      return value.toString();
    } catch (_a) {
      return '?';
    }
  }
  if (typeof value === 'function') {
    const fn = value;
    return `[Function ${fn.name || 'anonymous'}]`;
  }
  if (typeof value === 'object') {
    if (value instanceof Error) return `${value.name}: ${value.message}`;
    return safeStringify(value);
  }
  return String(value);
}
/**
 * 当前是否应屏蔽 info / warn / error（debug 仍由 `isDebug()` 单独控制）。
 */
function isNonDebugMuted() {
  if (muteNonDebug !== undefined) return muteNonDebug;
  return "development" === 'test';
}
/**
 * 测试 / CI 下临时恢复 warn 等输出（如断言 install 告警文案）。
 *
 * @param value `true` 屏蔽；`false` 允许；`undefined` 恢复为按 NODE_ENV 自动判定。
 */
function setMuteNonDebug(value) {
  muteNonDebug = value;
}
/**
 * 输出到 console：Android/iOS 真机整行单参；其余平台 `TAG` + 多参。
 */
function emitConsole(method, args) {
  if (method !== 'log' && isNonDebugMuted()) return;
  const fn = console[method];
  if (!preferSingleLineConsole()) {
    fn.call(console, TAG, ...args);
    return;
  }
  const mapped = isAndroidOrIosRuntime() ? args.map(stringifyObjectArgForNative) : args;
  if (mapped.length === 0) {
    fn.call(console, TAG);
    return;
  }
  const body = mapped.map(formatLogArgForNativeConsole).join(' ');
  fn.call(console, `${TAG} ${body}`);
}
/**
 * 当前是否启用 debug 输出。优先级：
 *   1. `setDebug(value)` 显式设置过 → 直接返回。
 *   2. `process.env.UNI_STAT_DEBUG === 'true'` 或被构建期替换为布尔字面量 `true`
 *      （历史插件兼容路径）。
 */
function isDebug() {
  if (runtimeDebug !== undefined) return runtimeDebug;
  const v = false;
  return v === 'true' || v === true;
}
/**
 * 运行时切换 debug 开关；传 `undefined` 恢复为「按 process.env 判断」。
 */
function setDebug(value) {
  runtimeDebug = value;
}
const logger = {
  debug(...args) {
    if (!isDebug()) return;
    // eslint-disable-next-line no-console
    emitConsole('log', args);
  },
  info(...args) {
    // eslint-disable-next-line no-console
    emitConsole('info', args);
  },
  warn(...args) {
    // eslint-disable-next-line no-console
    emitConsole('warn', args);
  },
  error(...args) {
    // eslint-disable-next-line no-console
    emitConsole('error', args);
  },
  setDebug,
  isDebug,
  setMuteNonDebug
};

/**
 * 公有版本地存储抽象（重写自私有版 `utils/db.js`）。
 *
 * 修复的私有版缺陷：
 *   - #14 `dbRemove` 第二段 `data = uni.getStorageSync(...)` 无 `|| {}` 兜底导致 NPE。
 *   - #18 每次 get/set/remove 都做 2~3 次 storage IO（read-modify-write），
 *         公有版改为「按 key 独立存储 + 内存缓存」，每次操作只 1 次同步 IO。
 *
 * 关键能力（供 Phase 4 缺陷 #5 修复使用）：
 *   - `safeRead`：读取失败时返回 `{ ok: false }` 而不是 `undefined`，调用方据此区分
 *     "key 不存在 / storage 异常"，避免老用户被 lvts=0 误判为新用户。
 *
 * 命名空间：所有 key 自动加前缀 `UNI_STAT_DATA:<appid>:`；`<appid>` 取
 * `process.env.UNI_APP_ID`，缺失时退化为 `default`。
 *
 * 注意：本模块依赖 `uni.{getStorageSync,setStorageSync,removeStorageSync}`，
 * 解析规则见 `infra/uniRuntime.ts`（含小程序注入路径）。
 * 测试中通过 `helpers/mockUni` 注入。
 */
/**
 * 公有版命名空间前缀，遵循公司内部统一规范 `UNI_STAT_DATA:<appid>:<key>`。
 *
 * 私有版（旧）使用 `$$STAT__DBDATA:<appid>` 作为单一聚合 key；这里**不再**使用旧前缀，
 * 仅在 Phase 4 `domain/migration` 中通过显式只读 API 读取一次老聚合数据并拆解到新前缀，
 * 保证平滑迁移；除迁移路径外，新代码全部写入 `UNI_STAT_DATA:` 命名空间。
 */
const NAMESPACE_ROOT = 'UNI_STAT_DATA';
/** 仅供迁移层读取老数据用：私有版聚合 key 的前缀。 */
const LEGACY_NAMESPACE_ROOT = '$$STAT__DBDATA';
/**
 * 内存缓存。值语义：
 *   - 命中且非 undefined → cache 中的真实值
 *   - 命中且 undefined   → 已经主动 `remove` 或确认 storage 中不存在
 *   - 未命中              → 还没读过 storage
 */
const cache = new Map();
/** 已知存在过的全部完整 key（用于 `clearNamespace`）。 */
const knownKeys = new Set();
/**
 * 拼装命名空间下的完整 key。
 */
function fullKey(key) {
  const appid =  false || 'default';
  return `${NAMESPACE_ROOT}:${appid}:${key}`;
}
/**
 * 取真实 uni 对象。剥离到函数里，便于测试用 mockUni 替换后立即生效。
 */
function getUni$a() {
  const raw = resolveUniRuntime();
  const u = raw != null && typeof raw === 'object' ? raw : undefined;
  if (!u || typeof u.getStorageSync !== 'function') {
    throw new Error('[uni统计 2.0] uni storage API is not available');
  }
  return u;
}
/**
 * 获取一个 key 的值。
 *
 * @returns 命中返回值；未命中或 storage 异常返回 `undefined`（无法区分两种情况，
 *          需要区分时请使用 `safeRead`）。
 */
function get(key) {
  const fk = fullKey(key);
  if (cache.has(fk)) return cache.get(fk);
  try {
    const raw = getUni$a().getStorageSync(fk);
    // uni 规范：未命中返回空字符串
    if (raw === '' || raw === null || raw === undefined) {
      cache.set(fk, undefined);
      return undefined;
    }
    cache.set(fk, raw);
    knownKeys.add(fk);
    return raw;
  } catch (_a) {
    return undefined;
  }
}
/**
 * 安全读取：明确区分「未命中 / 读异常」。
 *
 * @returns
 *   - `{ ok: true, value }`：成功读取（value 可能为 undefined 表示 key 不存在）。
 *   - `{ ok: false, value: undefined }`：storage 抛错；调用方应使用上次内存值兜底，
 *     **绝不**直接退化为 0 / null（否则会复现缺陷 #5：老用户被误判为新用户）。
 */
function safeRead(key) {
  const fk = fullKey(key);
  if (cache.has(fk)) return {
    ok: true,
    value: cache.get(fk)
  };
  try {
    const raw = getUni$a().getStorageSync(fk);
    if (raw === '' || raw === null || raw === undefined) {
      cache.set(fk, undefined);
      return {
        ok: true,
        value: undefined
      };
    }
    cache.set(fk, raw);
    knownKeys.add(fk);
    return {
      ok: true,
      value: raw
    };
  } catch (_a) {
    return {
      ok: false,
      value: undefined
    };
  }
}
/**
 * 写入一个 key。`undefined` 视为删除（与私有版语义对齐）。
 *
 * 失败策略：先更新缓存，再写 storage；storage 抛错时不回滚缓存，
 * 由调用方决定是否补偿（视调用方场景而定，热路径不应阻塞）。
 */
function set(key, value) {
  const fk = fullKey(key);
  if (value === undefined) {
    remove(key);
    return;
  }
  cache.set(fk, value);
  knownKeys.add(fk);
  try {
    getUni$a().setStorageSync(fk, value);
  } catch (_a) {
    // 缓存已更新，吞掉异常；调用方如需感知请使用 try/catch 显式包裹。
  }
}
/**
 * 删除一个 key。
 */
function remove(key) {
  const fk = fullKey(key);
  cache.set(fk, undefined);
  try {
    getUni$a().removeStorageSync(fk);
  } catch (_a) {
    // 同 set：忽略 storage 异常，缓存已置空。
  }
}
/**
 * 批量读：返回 `Record<key, value>`，未命中 / 异常的 key 取值为 `undefined`。
 */
function batchGet(keys) {
  const out = {};
  for (const k of keys) out[k] = get(k);
  return out;
}
/**
 * 批量写：逐个 `set`，等价于循环调用，便于调用侧聚合。
 */
function batchSet(entries) {
  for (const k of Object.keys(entries)) set(k, entries[k]);
}
/**
 * 清除当前 appid 命名空间下、自模块加载以来访问过的所有 key。
 *
 * 注意：受限于 uni storage 不一定支持 `getStorageInfoSync`，本函数只清理
 * 「本模块写入或读取过的 key」；未触达过的历史脏数据需要调用方显式处理。
 */
function clearNamespace() {
  let uni;
  try {
    uni = getUni$a();
  } catch (_a) {
    // uni 不可用：仅清缓存，无法清持久化
  }
  for (const fk of Array.from(knownKeys)) {
    try {
      uni === null || uni === void 0 ? void 0 : uni.removeStorageSync(fk);
    } catch (_b) {
      // 单 key 失败不影响其他 key 的清理
    }
    cache.set(fk, undefined);
  }
  knownKeys.clear();
}
/**
 * 仅供单测使用：清空内部缓存与 knownKeys 索引，让模块"像刚加载"一样。
 *
 * 单测必须在每个用例之间调用，否则会跨用例泄漏缓存状态。
 */
function __resetCache() {
  cache.clear();
  knownKeys.clear();
}
const storage = {
  get,
  set,
  remove,
  safeRead,
  batchGet,
  batchSet,
  clearNamespace,
  __resetCache
};

/**
 * 访问字段 `fvts / lvts / tvc` 状态机。**专项修复缺陷 #5：lvts=0 老用户被误判为新用户。**
 *
 * 私有版（`utils/pageTime.js`）的副作用链：
 *   1. `get_first_visit_time` 在写 fvts 时主动 `dbRemove(LAST_VISIT_TIME_KEY)`
 *      → 第 1 次启动结束 storage 中 lvts 为空。
 *   2. `get_last_visit_time` 在读时立即 `dbSet(LAST_VISIT_TIME_KEY, get_time())`
 *      → 把 "上一次" 当成 "本次"，下次启动读出来已是当前时间。
 *   3. 写入早于上报，上报失败时无法回滚，下次启动状态错乱。
 *
 * 公有版严格契约：
 *   1. 老用户三段拆分：`loadVisitSnapshot()` 纯读、`buildVisitFields()` 仅生成本次待写、
 *      `commitVisitOnAck()` 在上报 ack 后才落 storage（仅推进 lvts，永不主动清 lvts）。
 *   2. **新用户首条 lt=1 例外（保证"一生只计一次新增"）**：本条仍上报 `lvts=0`，但
 *      `buildVisitFields` 会**立即**把基线 `fvts/lvts/tvc=now/now/1` 落库（对齐私有版
 *      `get_last_visit_time` 的"读即写"）。这样本进程后续续会话、以及下次冷启动都会读到
 *      `lvts=now`（非 0），不再被重复计为新增；首条即便上报失败也已由 retry 暂存重试，
 *      不会丢失这唯一一次新增信号。**唯有卸载应用 / 清空缓存**清掉基线后才会重新计一次。
 *   3. `loadVisitSnapshot` 区分 "key 不存在" 与 "storage 异常"：
 *      - 不存在 → `lvts=0`，按新用户路径走（Yes new user）。
 *      - 异常   → 内存有上次 snapshot 时复用之；首次启动且异常 → fallback `lvts=0`，
 *        但**记录** `degraded=true`，上层可决定是否仍上报（Phase 5 collector 用）。
 *   4. 同一进程内只允许一次 `buildVisitFields`；后续 cst=2/3 触发的新会话 lt=1
 *      调用 `buildVisitFieldsForSessionRenewal`，复用 committed / lastBuilt 推进 tvc，
 *      并保证 lvts 仍随 lt=1 上行（缺失会被服务端误判为新用户）。
 *
 * 与 `pipeline/collector.ts` 的契约见 `05-公有版重构开发计划.md` §4.1.5。
 */
const KEY_FVTS = 'visit:fvts';
const KEY_LVTS = 'visit:lvts';
const KEY_TVC = 'visit:tvc';
const EMPTY_SNAPSHOT = {
  fvts: 0,
  lvts: 0,
  tvc: 0,
  isNewUser: true,
  degraded: false
};
/** 启动后通过 `loadVisitSnapshot` 写入；后续 build/commit 均基于此推进。 */
let loaded = null;
/** `buildVisitFields` 生成；`commitVisitOnAck` 落库后清空。 */
let pending = null;
/** cst=2/3 新会话 lt=1 生成；`commitVisitOnAck` 落库后清空。 */
let pendingRenewal = null;
/** `commitVisitOnAck` 落库后写入；同进程内 cst=2/3 后续事件复用此 snapshot。 */
let committed = null;
/**
 * 本进程内最近一次 `buildVisitFields` 的产出。即使 pending 已被 commit / rollback 清空，
 * 仍保留这份，用于：
 *   - cst=2/3 复用同一份字段（参见 T5/T6）。
 *   - 拦截同进程二次 `buildVisitFields` 误调（warn 后返回此值，不再生成新值）。
 */
let lastBuilt = null;
/** 同进程内 `buildVisitFields` 只允许调用一次（缺陷 #5 修复点之一）。 */
let buildCalledInProcess = false;
/**
 * 转 number（兼容历史 storage 中 string 形式的时间戳）。
 *
 * 异常 / NaN / 负数一律视为 0；
 * 这里保守不抛错，因为读流程要保证不让"脏数据"中断采集链路。
 */
function toNum(v) {
  if (typeof v === 'number' && Number.isFinite(v) && v >= 0) return v;
  if (typeof v === 'string' && v.length > 0) {
    const n = Number(v);
    if (Number.isFinite(n) && n >= 0) return n;
  }
  return 0;
}
/**
 * snapshot 是否「确实是一台全新设备」：三字段全 0。
 *
 * 用于消费 `degraded`：storage 读取异常时 `lvts` 会退化为 0 而误判 `isNewUser=true`。
 * 若此时 `fvts/tvc` 仍读到非 0（说明是老用户、只是 lvts 这一项读失败），就**不能**当新增，
 * 也不能落库覆盖真实持久值；只有三字段都为 0 才是可信的全新设备。
 */
function isLikelyFreshDevice(snap) {
  return snap.fvts === 0 && snap.lvts === 0 && snap.tvc === 0;
}
/**
 * 是否为「可信的新用户」：非 degraded 直接信任 `isNewUser`；degraded 时仅当三字段全 0
 * （`isLikelyFreshDevice`）才信任，否则视为「读失败的老用户」，走老用户兜底路径。
 */
function isTrustworthyNewUser(snap) {
  if (!snap.isNewUser) return false;
  return !snap.degraded || isLikelyFreshDevice(snap);
}
/**
 * 从 storage 读取 snapshot。**纯读，无副作用**（spy `storage.set` 必须 not.toHaveBeenCalled）。
 *
 * 异常处理：
 *   - 三个 key 任意一个 `safeRead.ok=false` → degraded=true。
 *   - 后续读到值仍写 snapshot；调用方应根据 `degraded` 决策是否上报。
 */
function loadVisitSnapshot() {
  const fvtsR = storage.safeRead(KEY_FVTS);
  const lvtsR = storage.safeRead(KEY_LVTS);
  const tvcR = storage.safeRead(KEY_TVC);
  const degraded = !fvtsR.ok || !lvtsR.ok || !tvcR.ok;
  const fvts = toNum(fvtsR.value);
  const lvts = toNum(lvtsR.value);
  const tvc = toNum(tvcR.value);
  const snapshot = {
    fvts,
    lvts,
    tvc,
    isNewUser: lvts === 0,
    degraded
  };
  if (degraded) {
    const likelyFresh = fvts === 0 && lvts === 0 && tvc === 0 && snapshot.isNewUser;
    if (!likelyFresh) {
      logger.warn('[uni统计 2.0] visit snapshot degraded; some storage keys read failed');
    }
  }
  loaded = snapshot;
  return snapshot;
}
/**
 * 取已加载的 snapshot；未调用过 `loadVisitSnapshot` 时返回 EMPTY。
 *
 * 这里不主动调 `loadVisitSnapshot`，避免在错误时机产生隐式 IO；
 * collector 必须在启动时显式 load 一次。
 */
function ensureLoaded() {
  if (!loaded) loaded = EMPTY_SNAPSHOT;
  return loaded;
}
/**
 * 新用户首条 lt=1 的**乐观落库**：立即把基线 `fvts/lvts/tvc=now/now/1` 写入 storage，
 * 并把内存 `loaded`/`committed` 刷新为"非新用户"基线。
 *
 * 目的：保证一台设备一生只上报一次 `lvts=0`（=只计一次新增）。对齐私有版
 * `get_first_visit_time`/`get_last_visit_time` 的"读即写"语义。
 *
 * 与 ack-commit 的关系：
 *   - 首条 lt=1 仍按 `lvts=0` 上报（在 `buildVisitFields` 里单独构造 pending 返回）；
 *     即便该条上报失败，也已由 `pipeline/retry` 暂存重试，唯一一次新增信号不丢。
 *   - 本进程后续续会话（`buildVisitFieldsForSessionRenewal`）命中 `committed` → lvts=now（非 0）；
 *     下次冷启动 `loadVisitSnapshot` 读到 storage 里的 lvts=now → `isNewUser=false`。
 *   - 唯有卸载应用 / 清空缓存清掉基线后，才会重新计一次新增。
 */
function persistNewUserBaseline(now) {
  storage.set(KEY_FVTS, now);
  storage.set(KEY_LVTS, now);
  storage.set(KEY_TVC, 1);
  const baseline = {
    fvts: now,
    lvts: now,
    tvc: 1,
    isNewUser: false,
    degraded: false
  };
  loaded = baseline;
  committed = baseline;
}
/**
 * 生成本次启动要上报的 fvts/lvts/tvc 三元组。
 *
 * 推进规则：
 *   - 新用户（loaded.isNewUser）：本次上报 fvts=now, lvts=0（0 表示新增），tvc=1；
 *     **同时立即落库基线**（见 `persistNewUserBaseline`），确保后续不再重复计新增。
 *   - 老用户：**不写 storage**；fvts 维持 loaded.fvts；lvts 上报 loaded.lvts（"上一次"，
 *     不是 now）；tvc=loaded.tvc+1；真正落库由 `commitVisitOnAck` 在 ack 后推进。
 *
 * 注意：同一进程内只允许调用一次（参考 `domain/session` 设计）；cst=2/3 新会话应走
 * `buildVisitFieldsForSessionRenewal`。这里通过 `buildCalledInProcess` 哨兵防止误用，
 * 二次调用返回与首次相同的结果但发出 warn，便于排查上层 collector bug。
 */
function buildVisitFields(now) {
  const snap = ensureLoaded();
  if (buildCalledInProcess && lastBuilt) {
    logger.warn('[uni统计 2.0] buildVisitFields() called twice in same process; returning cached fields');
    return Object.assign({}, lastBuilt);
  }
  buildCalledInProcess = true;
  if (isTrustworthyNewUser(snap)) {
    pending = {
      fvts: now,
      lvts: 0,
      tvc: 1,
      now
    };
    persistNewUserBaseline(now);
  } else if (snap.isNewUser) {
    // degraded 且非全新设备：lvts 读失败被误当 0。按老用户兜底，**不**上报 lvts=0、
    // **不**落库基线（storage 不可靠），避免新增虚高与覆盖真实持久值。
    logger.warn('[uni统计 2.0] visit degraded: lvts 读取失败但检测到历史数据，按老用户处理以避免新增虚高');
    const fvts = snap.fvts > 0 ? snap.fvts : now;
    pending = {
      fvts,
      lvts: fvts,
      tvc: snap.tvc + 1,
      now
    };
  } else {
    pending = {
      fvts: snap.fvts,
      lvts: snap.lvts,
      tvc: snap.tvc + 1,
      now
    };
  }
  lastBuilt = {
    fvts: pending.fvts,
    lvts: pending.lvts,
    tvc: pending.tvc
  };
  return Object.assign({}, lastBuilt);
}
/**
 * 为 cst=2/3 新会话 lt=1 生成本次要上报的 visit 字段（**不写 storage**）。
 *
 * 与私有版 `sendReportRequest` 对齐：后台/前台超时触发的新会话仍携带 fvts/lvts/tvc，
 * 避免 lvts 缺失被服务端按新用户入库。
 *
 * 推进规则：
 *   - 已有 committed：fvts 不变，lvts 上报 committed.lvts，tvc=committed.tvc+1。
 *   - 冷启动 lt=1 尚未 ack：复用 lastBuilt，不重复递增 tvc。
 *   - 兜底读 loaded snapshot，逻辑同 buildVisitFields 的老用户路径。
 */
function buildVisitFieldsForSessionRenewal(now) {
  let fvts;
  let lvts;
  let tvc;
  if (committed) {
    fvts = committed.fvts;
    lvts = committed.lvts;
    tvc = committed.tvc + 1;
  } else if (lastBuilt) {
    fvts = lastBuilt.fvts;
    // 防御：新用户冷启首条 lt=1（lvts=0）尚未 ack 时，本进程后续续会话不能再上报 lvts=0，
    // 否则同一新设备被重复计新增。此时用"本次启动时间"(=fvts) 作为上一次访问时间。
    // 正常路径下 buildVisitFields 已落库基线并置 committed，会走上面的 committed 分支。
    lvts = lastBuilt.lvts !== 0 ? lastBuilt.lvts : lastBuilt.fvts;
    tvc = lastBuilt.tvc;
  } else {
    const snap = ensureLoaded();
    if (isTrustworthyNewUser(snap)) {
      // 续会话成为本进程首条 lt=1 且命中新用户（罕见：未走过冷启 build）：本条仍按
      // lvts=0 计一次新增，并立即落库基线，保证只计一次。
      fvts = now;
      lvts = 0;
      tvc = 1;
      persistNewUserBaseline(now);
    } else if (snap.isNewUser) {
      // degraded 且非全新设备：按老用户兜底，不上报 lvts=0、不落库基线。
      fvts = snap.fvts > 0 ? snap.fvts : now;
      lvts = fvts;
      tvc = snap.tvc + 1;
    } else {
      fvts = snap.fvts;
      lvts = snap.lvts;
      tvc = snap.tvc + 1;
    }
  }
  pendingRenewal = {
    fvts,
    lvts,
    tvc,
    now
  };
  return {
    fvts,
    lvts,
    tvc
  };
}
/**
 * 上报 ack 成功后落库。
 *
 * 实际写入：
 *   - 新用户：`fvts=now, lvts=now, tvc=1`（本次启动既是首装也是上一次）。
 *   - 老用户：`fvts` 不变，`lvts=now`（注意：不是 pending.lvts，是 commit 时的 now），`tvc=pending.tvc`。
 *
 * pending 为空 / commit 重复调用一律 noop（保持幂等，便于 collector 重试逻辑）。
 */
function commitVisitOnAck(now) {
  if (pending) {
    const snap = ensureLoaded();
    const newFvts = snap.fvts === 0 ? now : snap.fvts;
    const newLvts = now;
    const newTvc = pending.tvc;
    storage.set(KEY_FVTS, newFvts);
    storage.set(KEY_LVTS, newLvts);
    storage.set(KEY_TVC, newTvc);
    committed = {
      fvts: newFvts,
      lvts: newLvts,
      tvc: newTvc,
      isNewUser: false,
      degraded: false
    };
    loaded = committed;
    pending = null;
    return;
  }
  if (!pendingRenewal) return;
  const newFvts = pendingRenewal.fvts;
  const newLvts = now;
  const newTvc = pendingRenewal.tvc;
  storage.set(KEY_FVTS, newFvts);
  storage.set(KEY_LVTS, newLvts);
  storage.set(KEY_TVC, newTvc);
  committed = {
    fvts: newFvts,
    lvts: newLvts,
    tvc: newTvc,
    isNewUser: false,
    degraded: false
  };
  loaded = committed;
  pendingRenewal = null;
}
/**
 * 上报失败回滚：清掉 pending，下次再 build 仍基于 loaded snapshot 推进。
 *
 * **不**重置 `buildCalledInProcess`：同一进程内即使首批失败，也不允许"重新"再造一份
 * fvts/lvts 上报，避免污染。失败的批次应由 `pipeline/retry` 负责持久化重试。
 */
function rollbackPendingVisit() {
  pending = null;
  pendingRenewal = null;
}

/**
 * 入口页（entry page）记忆与 `iey / ppiey` 计算。
 *
 * 设计文档：`03-公有版架构设计.md` §4 与 `04-字段字典与平台获取矩阵.md`。
 *
 * 上行出口：
 *   - **仅 `lt=11` 携带 `iey` / `ppiey`（0/1）**；`lt=1` / `lt=3` 等事件不含入口字段。
 * 字段含义（`lt=11` 在**下一页 onShow** 采集，描述**刚离开的上一页**）：
 *   - `iey`：离开页是否为本会话**首次离开的入口页**（会话内仅第一次离开入口路由为 1）。
 *   - `ppiey`：`urlref` 指向页是否仍为**有效入口**（同上，循环回到入口后再离开不算）。
 *
 * 写入时机（`markEntryPage` 仅维护「本会话入口 path」，供 `isEntry` 与 `lt=11` 使用）：
 *   - 新会话：`clearEntry()` 后立刻 `markEntryPage(route)`（launch / app_show / 首个 page_show），
 *     使首屏/恢复后当前页成为本会话登记入口。
 *   - 同一会话内仅首个 route 生效（一会话一 entry）；后续 `markEntryPage` noop。
 *
 * 模块**不持有** lastRoute；ppiey 由调用方传入"上一页"，避免和 `adapter/route` 的
 * 当前路由职责耦合。
 */
const KEY_ENTRY = 'session:entryRoute';
let cached$3;
/** 本会话是否已离开过登记入口（离开后循环回入口不再计 iey/ppiey）。 */
let entryDeparted = false;
/**
 * 标记当前页为入口页。
 *
 * 行为：
 *   - 已存在 entry 时直接 noop（保证一会话一 entry）。
 *   - route 为空字符串 / undefined 时 noop（不污染 storage）。
 */
function markEntryPage(route) {
  if (!route) return;
  const existing = getEntryRoute();
  if (existing) return;
  storage.set(KEY_ENTRY, route);
  cached$3 = route;
}
/**
 * 当前会话的入口路径；从内存优先取，未命中读 storage。
 */
function getEntryRoute() {
  if (cached$3 !== undefined) return cached$3 || undefined;
  const r = storage.safeRead(KEY_ENTRY);
  if (!r.ok) return undefined;
  if (typeof r.value === 'string' && r.value.length > 0) {
    cached$3 = r.value;
    return r.value;
  }
  // 标注已查过，避免下次再 IO
  cached$3 = '';
  return undefined;
}
/**
 * 当前路径是否为入口页。
 *
 * route 为空时返回 false；尚未 mark 时返回 false（不会把"未知"误判为入口）。
 */
function isEntry(route) {
  if (!route) return false;
  const entry = getEntryRoute();
  return entry === route;
}
/**
 * 当前路径是否仍按入口参与 `iey` / `ppiey` 计算。
 *
 * 与 `isEntry` 区别：用户首次离开登记入口后，即使再次导航回同一路由也不再视为入口。
 */
function isEntryForIey(route) {
  if (entryDeparted) return false;
  return isEntry(route);
}
/**
 * 标记本会话已离开登记入口；后续同路由访问不再产生 `iey=1` / `ppiey=1`。
 */
function markEntryDeparted() {
  entryDeparted = true;
}
/**
 * session 切换时调用：清掉 entry，等待新会话第一次 pageShow 重新登记。
 */
function clearEntry() {
  cached$3 = '';
  entryDeparted = false;
  storage.remove(KEY_ENTRY);
}

/**
 * pages.json 导航栏标题解析（ttpj 数据源）。
 *
 * 与私有版 `utils/pageInfo.js` 对齐，按 Vue 版本分两套构建期数据源：
 *   - VUE3：`uni:stat` 插件注入 `process.env.UNI_STAT_TITLE_JSON`（JSON 字符串）；
 *   - VUE2：`require('uni-pages?{"type":"style"}')` 在应用打包阶段解析 pages.json（公有版 dist
 *     拷贝进 Vue2 工程后无法依赖 define 注入，须与私有版同路径）。
 *
 * 运行时 `getPagesJsonNavigationTitle` 等价私有版 `get_page_name`。
 */
/** VUE3 懒加载缓存；`undefined` 表示尚未解析。 */
let titleMapCache;
/**
 * VUE2 构建期：由 `uni-pages` 虚拟模块解析出的 path → title 表（模块加载时即确定）。
 */

function buildVue2TitleMapFromUniPages() {
  const titleMap = {};
  try {
    // eslint-disable-next-line no-restricted-globals
    const pagesTitle = __webpack_require__(/*! uni-pages?{"type":"style"} */ 12).default;
    const pagesData = pagesTitle === null || pagesTitle === void 0 ? void 0 : pagesTitle.pages;
    if (!pagesData || typeof pagesData !== 'object') return titleMap;
    for (const path in pagesData) {
      const style = pagesData[path];
      const navigationBar = style.navigationBar;
      const titleText = style.navigationBarTitleText || style.defaultTitle || (navigationBar === null || navigationBar === void 0 ? void 0 : navigationBar.titleText) || '';
      if (titleText) {
        titleMap[path] = titleText;
      }
    }
  } catch (_a) {
    // uni-pages 不可用时（单测、非 uni 打包上下文）保持空表
  }
  return titleMap;
}
const vue2TitleMap = buildVue2TitleMapFromUniPages();

/**
 * VUE3：解析并缓存 `UNI_STAT_TITLE_JSON`；解析失败或缺失时得到空表，避免重复 JSON.parse。
 */

/**
 * 取当前编译目标下的标题映射表。
 */
function getTitleMap() {
  let map = {};
  map = vue2TitleMap;
  return map;
}
/**
 * 按当前页路由取 pages.json 中的导航栏标题，供 `setConfigTitle` → 上行 `ttpj`。
 *
 * @param routePath `getCurrentRoute()` 的典型返回值（一般无前导 `/`）；允许含 query。
 * @returns 未配置或查找不到时返回空串（与私有版 `get_page_name` 一致）。
 */
function getPagesJsonNavigationTitle(routePath) {
  if (!routePath || typeof routePath !== 'string') return '';
  const pathOnly = routePath.split('?')[0].trim();
  if (!pathOnly) return '';
  const map = getTitleMap();
  let result = '';
  const direct = map[pathOnly];
  result = typeof direct === 'string' && direct.length > 0 ? direct : '';
  return result;
}

/**
 * 导航栏标题内存状态。
 *
 * 私有版 `Stat._navigationBarTitle = { page, config, report }` 三段被分散维护：
 *   - `page`：拦截 `uni.setNavigationBarTitle` → `ttn`；
 *   - `config`：构建期注入的 pages.json 映射，运行时由 `getPagesJsonNavigationTitle(route)`（等价私有版 `get_page_name`）在每次 `onShow` 写入 → `ttpj`；
 *   - `report`：`uni.report('title', value)` / `StatApp.report('title')` → `ttc`。
 *
 * 公有版集中到 `domain/title.ts`，对外仅暴露 setter / getter / clearForRoute；
 * statData 拼装时通过 `getCurrentTitle()` 一次性读出，**不再**和拦截器/路由耦合。
 */
const state$2 = {
  page: '',
  config: '',
  report: ''
};
/**
 * 由拦截器在 `setNavigationBarTitle.invoke` 时调用。
 *
 * @param title 用户设置的标题；非字符串视为空串，避免污染上行 ttn。
 */
function setPageTitle(title) {
  state$2.page = typeof title === 'string' ? title : '';
}
/**
 * 由 collector / runtime 在 onPageShow 时写入 pages.json 配置标题。
 */
function setConfigTitle(title) {
  state$2.config = typeof title === 'string' ? title : '';
}
/**
 * 业务通过 `uni.report('title', value)` 写入；与私有版 `sendEvent('title')` 行为一致。
 */
function setReportTitle(title) {
  state$2.report = typeof title === 'string' ? title : '';
}
/**
 * 取当前 title 三元组的浅拷贝；statData.builder 在拼装 ttn/ttpj/ttc 时调用。
 */
function getCurrentTitle() {
  return {
    ttn: state$2.page,
    ttpj: state$2.config,
    ttc: state$2.report
  };
}
/**
 * 切换页面时清掉 page 维度的 title（config / report 由各自 setter 控制）。
 */
function clearPageTitle() {
  state$2.page = '';
}

/**
 * 时间相关基础设施。
 *
 * 设计要点：
 *   1. 单元统一：`Sec` 后缀代表秒级；`Ms` 后缀代表毫秒级。任何函数签名都禁止"参数与
 *      返回值单元不一致"，避免私有版长期存在的"秒/毫秒混用"问题。
 *   2. 全部走 `Date.now()`，不走 `new Date().getTime()`，便于 jest fake timers / mock。
 */
/**
 * 当前毫秒级时间戳。用于上报 jitter / 节流定时器等内部计算。
 */
function nowMs() {
  return Date.now();
}
/**
 * 当前秒级时间戳。用于 statData 上行字段（`t / fvts / lvts / sst` 等）。
 */
function nowSec() {
  return Math.floor(Date.now() / 1000);
}
/**
 * 将「离开页 / 后台前当前页」停留时长（秒）钳到与私有版 `get_residence_time` 一致：
 * 差值小于 1 秒时按 1 秒上报（`residenceTime &lt; 1 ? 1 : residenceTime`）。
 *
 * @param deltaSec 非负停留秒数优先；传入负数时视为 0 再钳制。
 */
function clampUrlrefStaySec(deltaSec) {
  const d = deltaSec > 0 ? deltaSec : 0;
  return d < 1 ? 1 : d;
}

/**
 * 平台标识适配。
 *
 * 私有版 `pageInfo.js#get_platform_name` 的能力等价物，但做了三点改进：
 *   1. 类型化：返回受控 `Platform` 联合，禁止把陌生平台直接透传出去。
 *   2. 拆出 `getRawPlatform()`：返回 `process.env.UNI_PLATFORM` 原值，便于 adapter 内部
 *      做"小程序基础库分支"判断，而无需重复读 env。
 *   3. `isApp / isMp / isH5 / isNvue` 一次实现，调用方不再四处 `if (platform === 'n')`。
 *
 * 上行字段约定：
 *   - `ut` = `getPlatform()`（宿主类型：wx / h5 / n …）。
 *   - `p` = 运行设备操作系统（与私有版 `report.js` 中 `sys.platform` 语义一致），由
 *     `normalizeStatOsP()` 从 `getSystemInfo` 合并结果解析，**不得**再用仅读 `plus` 的
 *     `getClientOs()` 填小程序（否则恒为 `unknown` → 空串）。
 *   - `getClientOs()`：保留为 App 端粗分字母 'a' / 'i' / 'h'（历史逻辑），与 `p` 无强绑定。
 *
 * 注意：本模块严禁缓存平台判定结果到模块级常量。`process.env.UNI_PLATFORM` 在 SSR 与
 * 单测中可能被运行时切换；缓存会让多端测试串味。
 */
/**
 * 将 uni 系统信息中的 `platform` / `osName` / `system` 归一为上行 `p`。
 *
 * 与私有版 `report.js`（`sys.platform` → `a|i|h`）数据源一致，但输出采用完整单词，
 * 并覆盖 H5 桌面端（windows / macos / linux）。小程序依赖 `getDeviceInfo` 等合并后的
 * `platform`（如 `ios` / `android`）；`devtools` 无有效机型时再退 `system` / `osName`。
 *
 * @param info 来自 `mergedSystemInfo()` 的字段子集；均可缺省。
 * @returns 小写 OS 名；无法判断时返回空串。
 */
function normalizeStatOsP(info) {
  var _a, _b, _c, _d, _e;
  const fromToken = raw => {
    const s = raw.toLowerCase().trim();
    if (!s) return '';
    if (s === 'devtools') return '';
    if (s === 'android') return 'android';
    if (s === 'ios' || s === 'iphone') return 'ios';
    if (s.includes('android')) return 'android';
    if (s.includes('iphone') || s === 'iphone os' || /\bios\b/.test(s)) return 'ios';
    if (s.includes('harmony') || s === 'ohos' || s === 'openharmony') return 'harmonyos';
    if (s.includes('windows') || s === 'windows_nt') return 'windows';
    if (s === 'mac' || s === 'darwin' || s.includes('mac os') || s === 'macos') return 'macos';
    if (s.includes('linux') && !s.includes('android')) return 'linux';
    return '';
  };
  const p0 = fromToken((_a = info.platform) !== null && _a !== void 0 ? _a : '');
  if (p0) return p0;
  const p1 = fromToken((_b = info.osName) !== null && _b !== void 0 ? _b : '');
  if (p1) return p1;
  const sys = ((_c = info.system) !== null && _c !== void 0 ? _c : '').toLowerCase();
  if (sys.includes('android')) return 'android';
  if (sys.includes('iphone') || /\bios\b/.test(sys)) return 'ios';
  if (sys.includes('harmony') || sys.includes('ohos')) return 'harmonyos';
  if (sys.includes('windows')) return 'windows';
  if (sys.includes('mac os') || sys.includes('darwin')) return 'macos';
  if (sys.includes('linux')) return 'linux';
  const plus = getGlobalObject().plus;
  const p2 = fromToken((_e = (_d = plus === null || plus === void 0 ? void 0 : plus.os) === null || _d === void 0 ? void 0 : _d.name) !== null && _e !== void 0 ? _e : '');
  if (p2) return p2;
  return '';
}
/**
 * 与私有版 `pageInfo.js#get_platform_name` 中 `aliArr.reverse().join('')` 等价：
 * 得到 uni-app 注入的「阿里系小程序」`UNI_PLATFORM` 原始键。
 *
 * 苹果审核会扫描源码中的敏感品牌连续词，故**禁止**在字面量中直接写出完整键名；
 * 仅通过片段拼接构造（`mp-` + `ali` + `p` + `a` + `y` 逆序拼接）。
 */
function uniPlatformMpAliRaw() {
  const parts = ['y', 'a', 'p', 'mp-ali'];
  return [...parts].reverse().join('');
}
/** 私有版兼容映射：UNI_PLATFORM → 短码。 */
const PLATFORM_MAP = {
  app: 'n',
  'app-plus': 'n',
  'app-harmony': 'n',
  'mp-harmony': 'mhm',
  h5: 'h5',
  'mp-weixin': 'wx',
  [uniPlatformMpAliRaw()]: 'ali',
  'mp-baidu': 'bd',
  'mp-toutiao': 'tt',
  'mp-qq': 'qq',
  'mp-kuaishou': 'ks',
  'mp-lark': 'lark',
  'mp-xhs': 'xhs',
  'mp-jd': 'jd',
  'quickapp-native': 'qn',
  'quickapp-webview': 'qw'
};
/**
 * 取 `process.env.UNI_PLATFORM` 原值，未设置返回空字符串。
 *
 * 单独抽出是为了：
 *   - 单测可以专门校验"未注入 UNI_PLATFORM"路径，不被 PLATFORM_MAP 遮蔽。
 *   - 调用方做小程序差异判断（如阿里系再细分 ali/dt）时无需再 `process.env.*`。
 */
function getRawPlatform() {
  var _a;
  return (_a = "mp-weixin") !== null && _a !== void 0 ? _a : '';
}
/**
 * 取标准化后的平台短码。
 *
 * 阿里系细分逻辑：
 *   - 命中 `uniPlatformMpAliRaw()` 对应宿主时，若 `globalThis.my.env.clientName === 'dingtalk'` → `dt`。
 *   - 其他阿里系（小程序、H5 中嵌入支付宝端等）继续返回 `'ali'`。
 *
 * 未识别平台返回 `'unknown'`，禁止把陌生 raw 值直接当作 Platform 透传，
 * 避免上行字段污染（私有版的 `return … || process.env.VUE_APP_PLATFORM` 是潜在风险点）。
 */
function getPlatform() {
  var _a;
  const raw = getRawPlatform();
  const mapped = PLATFORM_MAP[raw];
  if (!mapped) return 'unknown';
  if (mapped === 'ali') {
    const my = getGlobalObject().my;
    if (((_a = my === null || my === void 0 ? void 0 : my.env) === null || _a === void 0 ? void 0 : _a.clientName) === 'dingtalk') return 'dt';
    return 'ali';
  }
  return mapped;
}
/** 当前是否运行在 App / nvue / HarmonyOS App 端。 */
function isApp() {
  const raw = getRawPlatform();
  return raw === 'app' || raw === 'app-plus' || raw === 'app-harmony';
}
/** 当前是否运行在小程序端（含各平台）。 */
function isMp() {
  return getRawPlatform().startsWith('mp-');
}
/** 当前是否运行在 H5 端。 */
function isH5() {
  return getRawPlatform() === 'h5';
}
/**
 * 当前页面/上下文是否为 nvue。
 *
 * uni-app nvue 页面的 `__UNI_FEATURE_NVUE__` 编译期常量为 true；
 * 运行时无可靠 API，统一通过编译期 define 注入的 `globalThis.__NVUE__` 判断。
 * 没有注入则保守返回 false。
 */
function isNvue() {
  return Boolean(getGlobalObject().__NVUE__);
}

/**
 * 设备 ID 适配。
 *
 * 私有版痛点（参考 `pageInfo.js#getUuid` / `get_uuid` / `get_odid`）：
 *   - `get_uuid` 优先用 `sys.deviceId`，但 `sys` 是模块加载期 `uni.getSystemInfoSync()`
 *     的快照，SSR/早期阶段可能不存在 `deviceId` 字段，导致退化路径被频繁走到。
 *   - 退化路径里 `uni.setStorageSync(UUID_KEY, UUID_VALUE)` —— 这里 `UUID_VALUE` 是
 *     字面量字符串 `'__DC_UUID_VALUE'`，会让所有"写入失败"的设备共享同一个 uuid，
 *     直接污染统计漏斗（缺陷 #28）。
 *
 * 公有版职责：
 *   1. `getUuid()`（上行 `did`）：稳定 + 持久化。
 *      - **App / H5 / 微信小程序（`mp-weixin`）**：优先 `uni.getDeviceInfo().deviceId`，
 *        再退 `getSystemInfoSync().deviceId`、storage、本地 anon。
 *      - **其余宿主**：不走 `getDeviceInfo` 首取，直接 `getSystemInfoSync().deviceId` →
 *        storage → anon（与历史兜底一致）。
 *   2. 任何 storage / uni 调用全部走 `tryRun` 兜底，绝不抛出。
 *   3. 内存级缓存：避免每次构建 statData 都触发一次同步 storage IO。
 *   4. `__resetCache()` 仅供测试。
 *
 * 说明：老版 `odid`（`plus.device.uuid`）已移除，不再参与装配与导出。
 */
const STORAGE_KEY_UUID = 'device:uuid';
/**
 * uni-h5 `getDeviceInfo().deviceId` 的底层 localStorage 键（见 `packages/uni-h5/src/helpers/uuid.ts`）。
 *
 * H5 端直接复用同一个键读写 deviceId：绕开 uni 运行时，保证 `did` 与页面
 * `uni.getDeviceInfo().deviceId` 同源一致，且跨刷新稳定。
 */
const WEB_UUID_KEY = '__DC_STAT_UUID';
let cachedUuid = null;
/**
 * App、H5、微信小程序上优先用拆分 API `getDeviceInfo().deviceId`；其它平台保持原兜底顺序。
 */
function preferGetDeviceInfoDeviceIdFirst() {
  if (isApp() || isH5()) return true;
  return getRawPlatform() === 'mp-weixin';
}
/**
 * 读取 `uni.getSystemInfoSync().deviceId`；任何异常 / 缺失返回空串。
 *
 * 不复用 `adapter/system.getSystemInfo`：deviceId 在 uni-app 字段表里属于"敏感字段"，
 * 公有版默认不暴露在 `SystemInfoStatic` 中，仅在本 adapter 内部使用。
 */
function readSysDeviceId() {
  const root = resolveUniRuntime();
  const u = root != null && typeof root === 'object' ? root : undefined;
  if (!u || typeof u.getSystemInfoSync !== 'function') return '';
  return tryRun(() => {
    var _a;
    return (_a = u.getSystemInfoSync().deviceId) !== null && _a !== void 0 ? _a : '';
  }, '');
}
/**
 * 读取 `uni.getDeviceInfo().deviceId`（官方推荐的设备标识来源之一）。
 *
 * API 不存在或抛错时返回空串，由 `getUuid` 继续走 `getSystemInfoSync` / storage 兜底。
 */
function readGetDeviceInfoDeviceId() {
  const root = resolveUniRuntime();
  const u = root != null && typeof root === 'object' ? root : undefined;
  if (!u || typeof u.getDeviceInfo !== 'function') return '';
  return tryRun(() => {
    var _a;
    return (_a = u.getDeviceInfo().deviceId) !== null && _a !== void 0 ? _a : '';
  }, '');
}
/**
 * 生成兜底设备 id（did）：**纯数字串**，与常见线上形态一致（毫秒时间戳 + 6 位随机数，约 19 位）。
 *
 * 与 `infra/sid.genSid` 区别：uuid 设备级持久化；sid 每会话新生且带 `-xxxx-xxxx` 形后缀。
 */
function generateAnonUuid() {
  const ms = nowMs();
  const rnd = Math.floor(Math.random() * 1000000).toString().padStart(6, '0');
  return `${ms}${rnd}`;
}
/**
 * 把设备 id 写回统计命名空间（`UNI_STAT_DATA:<appid>:device:uuid`），供后续启动读回锁定。
 * 写入失败静默吞掉，不影响本次返回。
 */
function persistUuid(uuid) {
  tryRun(() => storage.set(STORAGE_KEY_UUID, uuid), undefined);
}
/**
 * 取浏览器 `localStorage`（cookie 被禁用 / 无 localStorage 时返回 undefined）。
 *
 * 直接走 `getGlobalObject()`（globalThis / window），**绕开可能不可用的 `uni` 运行时**；
 * 与 `adapter/web.getWebInfo` 直读 `location` 同思路。
 */
function getWebLocalStorage() {
  return tryRun(() => {
    const g = getGlobalObject();
    if (g.navigator && g.navigator.cookieEnabled === false) return undefined;
    const ls = g.localStorage;
    if (ls && typeof ls.getItem === 'function' && typeof ls.setItem === 'function') {
      return ls;
    }
    return undefined;
  }, undefined);
}
/**
 * H5：直接从浏览器 `localStorage` 读取 uni-h5 写入的稳定 deviceId（`__DC_STAT_UUID`）。
 * 取不到返回空串。
 */
function readWebDeviceId() {
  const ls = getWebLocalStorage();
  if (!ls) return '';
  return tryRun(() => {
    const v = ls.getItem(WEB_UUID_KEY);
    return typeof v === 'string' ? v : '';
  }, '');
}
/**
 * H5：把 did 直接写入浏览器 `localStorage`（与 uni-h5 同键 `__DC_STAT_UUID`）。
 * 使下次刷新读回同一值，并与页面 `uni.getDeviceInfo().deviceId` 对齐。
 */
function writeWebDeviceId(uuid) {
  const ls = getWebLocalStorage();
  if (!ls) return;
  tryRun(() => ls.setItem(WEB_UUID_KEY, uuid), undefined);
}
/**
 * 从 uni 运行时解析设备 id。
 *
 * - App / H5 / 微信小程序：优先 `getDeviceInfo().deviceId`，再退 `getSystemInfoSync().deviceId`；
 *   H5 上 `getDeviceInfo().deviceId` 取自 uni-h5 持久化的 `__DC_STAT_UUID`，跨刷新稳定。
 * - 其余宿主：直接 `getSystemInfoSync().deviceId`。
 *
 * 取不到时返回空串，由 `getUuid` 继续走 storage / anon 兜底。
 */
function resolveDeviceIdFromUni() {
  if (preferGetDeviceInfoDeviceIdFirst()) {
    const fromDeviceInfo = readGetDeviceInfoDeviceId();
    if (fromDeviceInfo) return fromDeviceInfo;
  }
  return readSysDeviceId();
}
/**
 * 取设备 uuid（上行映射为 `did`）。
 *
 * 解析顺序：
 *   1. 内存缓存（同进程内恒定，保证同次启动 `did` 与 `sid` 前半段一致）。
 *   2. H5：直接读浏览器 `localStorage['__DC_STAT_UUID']`（uni-h5 写入的 deviceId）。
 *   3. uni 设备源（getDeviceInfo / getSystemInfoSync），取到即写回 storage 锁定。
 *   4. uni storage 已持久化的 did。
 *   5. uni storage 正常且无历史值 → 生成 anon 并落库。
 *   6. uni storage 读取异常：H5 直接写浏览器 localStorage 并缓存；其它端返回不缓存、不落库的临时 did。
 *
 * 任何环节失败都不抛错，最差返回新生成的临时 uuid，保证上行字段非空。
 */
function getUuid() {
  if (cachedUuid) return cachedUuid;
  // H5：直读浏览器 localStorage 的 deviceId，与页面 uni.getDeviceInfo().deviceId 同源。
  if (isH5()) {
    const fromWeb = readWebDeviceId();
    if (fromWeb) {
      cachedUuid = fromWeb;
      return cachedUuid;
    }
  }
  // uni 设备源；取到后写回 storage 锁定。
  const fromDevice = resolveDeviceIdFromUni();
  if (fromDevice) {
    persistUuid(fromDevice);
    if (isH5()) writeWebDeviceId(fromDevice);
    cachedUuid = fromDevice;
    return cachedUuid;
  }
  // 设备源不可用：回落到 uni storage 已持久化的 did。
  // safeRead 区分「确无历史值」与「storage 读取异常」，后者不落库以免覆盖真实值。
  const storedRead = storage.safeRead(STORAGE_KEY_UUID);
  if (storedRead.ok) {
    const stored = storedRead.value;
    if (typeof stored === 'string' && stored.length > 0) {
      if (stored.startsWith('device-anon-')) {
        const upgraded = generateAnonUuid();
        persistUuid(upgraded);
        if (isH5()) writeWebDeviceId(upgraded);
        cachedUuid = upgraded;
        return cachedUuid;
      }
      cachedUuid = stored;
      return cachedUuid;
    }
    // 无历史值 → 首次生成并落库。
    const generated = generateAnonUuid();
    persistUuid(generated);
    if (isH5()) writeWebDeviceId(generated);
    cachedUuid = generated;
    return cachedUuid;
  }
  // uni storage 读取异常。
  const ephemeral = generateAnonUuid();
  if (isH5()) {
    // H5 写浏览器 localStorage 并缓存，下次刷新读回同一值。
    writeWebDeviceId(ephemeral);
    cachedUuid = ephemeral;
    return cachedUuid;
  }
  // 其它端：临时 did，不缓存、不落库，避免覆盖磁盘上可能仍存在的真实 did。
  return ephemeral;
}

/**
 * 会话 ID 生成器。
 *
 * 形如（与典型调试示例一致）：
 *   - 有 did（uuid）：`${did}-${8位base36}-${4位base36}`，例如 `1777261806777339018-moih1mhr-40gn`
 *   - 无 did：先生成与兜底 did 同形的数字主体，再拼同样后缀（避免 `anon-` 前缀）。
 *
 * 设计要点：
 *   1. 长度可控，避免上报字段超限。
 *   2. 仅依赖 `Math.random` 与 `Date.now`，不引入 crypto。
 */
const SUFFIX_HEAD_LEN = 8;
const SUFFIX_TAIL_LEN = 4;
/**
 * 生成 base36 随机串。
 *
 * @param len 期望长度；不足时用 '0' **末尾填充**（`padEnd`）补齐，保证长度稳定。
 */
function randomPart(len) {
  const r = Math.random().toString(36).slice(2, 2 + len);
  return r.length >= len ? r : r.padEnd(len, '0');
}
/**
 * 会话实例后缀：`xxxxxxxx-xxxx`（与常见上报示例形态一致）。
 */
function sessionInstanceSuffix() {
  return `${randomPart(SUFFIX_HEAD_LEN)}-${randomPart(SUFFIX_TAIL_LEN)}`;
}
/**
 * 无设备 id 时的数字主体（与 device 兜底 did 生成规则对齐，避免引入循环依赖故略重复）。
 */
function anonNumericBody() {
  const ms = nowMs();
  const rnd = Math.floor(Math.random() * 1000000).toString().padStart(6, '0');
  return `${ms}${rnd}`;
}
/**
 * 生成会话 ID。`uuid` 为空字符串 / undefined 时退化为「数字主体 + 后缀」。
 */
function genSid(uuid) {
  if (uuid && uuid.length > 0) {
    return `${uuid}-${sessionInstanceSuffix()}`;
  }
  return `${anonNumericBody()}-${sessionInstanceSuffix()}`;
}

/**
 * 客户端会话状态机（公有版核心新增）。
 *
 * 设计文档：`03-公有版架构设计.md` §3。
 *
 * 状态：
 *   - `None`：未生成过 session（首次启动 / clearStorage 后）。
 *   - `Active`：前台有有效 session，可继续 touch 推进 lastActive。
 *   - `Background`：应用进入后台，等待返回前台时判定是否超时。
 *
 * 触发器 → cst 映射：
 *   - `cold_launch`：进程冷启动 → cst=1。
 *   - `app_show` (从后台返回)：
 *       - now - bgTs >= backgroundTimeoutSec → 新 session, cst=2（与私有版 pageTime
 *         可读性对齐：配置为 10 秒时，隐藏端与显示端秒戳相差 10 即视为超时）。
 *       - 否则复用旧 session, cst=0。
 *   - `wx_scene_changed`：scene 与上次不同 → 新 session, cst=2。
 *   - `page_show` (前台已有 session)：
 *       - now - lastActive >= pageInactiveTimeoutSec → 新 session, cst=3。
 *       - 否则 touch & 复用, cst=0。
 *
 * 关键设计：所有 storage 操作都带 try / safeRead 兜底；任何路径都不抛异常，
 * 失败 → 退化生成新 session，避免阻塞采集链路。
 */
const KEY_SID = 'session:id';
const KEY_SST = 'session:start';
const KEY_SCT = 'session:sct';
const KEY_SEQ = 'session:seq';
const KEY_LAST_ACTIVE = 'session:lastActive';
const KEY_BG_TS = 'session:bgTs';
const KEY_LAST_SCENE = 'session:lastScene';
const DEFAULT_CONFIG = {
  backgroundTimeoutSec: 300,
  pageInactiveTimeoutSec: 1800
};
let config$1 = Object.assign({}, DEFAULT_CONFIG);
let cached$2 = null;
/** 配置注入（runtime/install.ts 在启动时调一次）。 */
function configure$1(c) {
  config$1 = Object.assign({}, DEFAULT_CONFIG, c);
}
/**
 * 工具：把 storage 读取到的值转 number；非法值返回 0。
 */
function readNum(key) {
  const r = storage.safeRead(key);
  if (!r.ok) return 0;
  const v = r.value;
  if (typeof v === 'number' && Number.isFinite(v) && v >= 0) return v;
  if (typeof v === 'string' && v.length > 0) {
    const n = Number(v);
    if (Number.isFinite(n) && n >= 0) return n;
  }
  return 0;
}
function readStr(key) {
  const r = storage.safeRead(key);
  if (!r.ok) return '';
  return typeof r.value === 'string' ? r.value : '';
}
/**
 * 计算 `now - from` 的非负秒差，防止设备时钟回拨（NTP 校时 / 用户手动改时间）导致
 * `elapsed < 0` 使后台 / 无操作超时判定**永不触发**、会话被异常拉长。
 *
 * 与 `infra/time.elapsedSec` 同语义（负值钳零），此处因状态机入参 `now` 由调用方注入、
 * 不直接走 `nowSec()`，故就地实现保持纯函数可测。
 */
function elapsedNonNeg(now, from) {
  const diff = now - from;
  return diff > 0 ? diff : 0;
}
/**
 * 从 storage 重建 snapshot；任意字段缺失返回 null。
 */
function loadFromStorage() {
  const sid = readStr(KEY_SID);
  if (!sid) return null;
  return {
    sid,
    sst: readNum(KEY_SST),
    sct: readNum(KEY_SCT) || CST.ColdLaunch,
    seq: readNum(KEY_SEQ),
    lastActive: readNum(KEY_LAST_ACTIVE),
    bgTs: readNum(KEY_BG_TS),
    lastScene: readStr(KEY_LAST_SCENE)
  };
}
function ensureCache() {
  if (cached$2 !== null) return cached$2;
  cached$2 = loadFromStorage();
  return cached$2;
}
/**
 * 创建一个新 session，写入 storage 并返回新的 snapshot。
 *
 * 内部职责：
 *   - 重置 seq=0、lastActive=now、bgTs=0。
 *
 * 注：原"上一会话 sid（pid）"机制已移除——参数文档无 pid 字段，后端无入库口径，
 *     新会话的字段仅随当次 lt=1 携带。
 */
function createNew(now, sct, scene) {
  const sid = genSid(getUuid());
  const next = {
    sid,
    sst: now,
    sct,
    seq: 0,
    lastActive: now,
    bgTs: 0,
    lastScene: scene
  };
  storage.set(KEY_SID, sid);
  storage.set(KEY_SST, now);
  storage.set(KEY_SCT, sct);
  storage.set(KEY_SEQ, 0);
  storage.set(KEY_LAST_ACTIVE, now);
  storage.set(KEY_BG_TS, 0);
  storage.set(KEY_LAST_SCENE, scene);
  cached$2 = next;
  return next;
}
/**
 * 主入口：根据 trigger 与上下文，确保 session 处于正确状态。
 *
 * 结果包含 isNew / cst，供 lifecycleHooks 决定本次 lt=1 是否携带 fvts/lvts/tvc。
 */
function ensureSession(t, ctx) {
  const {
    now,
    scene = ''
  } = ctx;
  const snap = ensureCache();
  if (t === 'cold_launch') {
    const created = createNew(now, CST.ColdLaunch, scene);
    return {
      snapshot: created,
      isNew: true,
      cst: CST.ColdLaunch
    };
  }
  if (!snap) {
    // 没有现存 session（罕见：app_show 但 storage 被清）→ 视为冷启动
    const created = createNew(now, CST.ColdLaunch, scene);
    return {
      snapshot: created,
      isNew: true,
      cst: CST.ColdLaunch
    };
  }
  if (t === 'app_show') {
    const enterCandidates = [];
    if (ctx.backgroundEnteredAt && ctx.backgroundEnteredAt > 0) {
      enterCandidates.push(ctx.backgroundEnteredAt);
    }
    if (snap.bgTs > 0) {
      enterCandidates.push(snap.bgTs);
    }
    const enterTs = enterCandidates.length > 0 ? Math.min(...enterCandidates) : 0;
    const elapsed = enterTs > 0 ? elapsedNonNeg(now, enterTs) : elapsedNonNeg(now, snap.lastActive);
    const sceneChanged = !!scene && !!snap.lastScene && scene !== snap.lastScene;
    const fromBackground = enterTs > 0;
    if (sceneChanged || fromBackground && elapsed >= config$1.backgroundTimeoutSec) {
      const created = createNew(now, CST.BackgroundTimeout, scene);
      return {
        snapshot: created,
        isNew: true,
        cst: CST.BackgroundTimeout
      };
    }
    // 未超时：清 bgTs，更新 lastActive
    touch(now);
    storage.set(KEY_BG_TS, 0);
    if (cached$2) cached$2.bgTs = 0;
    return {
      snapshot: cached$2,
      isNew: false,
      cst: 0
    };
  }
  if (t === 'wx_scene_changed') {
    if (scene && scene !== snap.lastScene) {
      const created = createNew(now, CST.BackgroundTimeout, scene);
      return {
        snapshot: created,
        isNew: true,
        cst: CST.BackgroundTimeout
      };
    }
    return {
      snapshot: snap,
      isNew: false,
      cst: 0
    };
  }
  // page_show：判定前台无操作超时
  const elapsed = elapsedNonNeg(now, snap.lastActive);
  if (elapsed >= config$1.pageInactiveTimeoutSec) {
    const created = createNew(now, CST.PageInactiveTimeout, scene || snap.lastScene);
    return {
      snapshot: created,
      isNew: true,
      cst: CST.PageInactiveTimeout
    };
  }
  touch(now);
  return {
    snapshot: cached$2,
    isNew: false,
    cst: 0
  };
}
/**
 * 标记应用进入后台。写入 bgTs，供下次 app_show 判定超时。
 */
function markBackground(now) {
  if (!cached$2) cached$2 = loadFromStorage();
  if (!cached$2) return;
  storage.set(KEY_BG_TS, now);
  cached$2.bgTs = now;
}
/**
 * 更新 lastActive；page_show 与**用户主动行为事件**（collector 在收到 lt=21 自定义/
 * 拦截器事件时调用）触发。这样「前台无操作超时（cst=3）」与文档「无任何 page/event
 * 触达」语义一致：用户持续点按但不翻页时不会被误判为无操作而开新会话。
 */
function touch(now) {
  if (!cached$2) cached$2 = loadFromStorage();
  if (!cached$2) return;
  storage.set(KEY_LAST_ACTIVE, now);
  cached$2.lastActive = now;
}
/**
 * 取下一个 seq；先递增 storage 中的 seq，再返回新值。
 *
 * 失败兜底：若 storage 异常，仍以内存 cached.seq 自增；保证序号单调，但跨进程可能跳号。
 */
function nextSeq() {
  if (!cached$2) cached$2 = loadFromStorage();
  if (!cached$2) return 0;
  const next = cached$2.seq + 1;
  cached$2.seq = next;
  storage.set(KEY_SEQ, next);
  return next;
}
/** 取当前 snapshot；未初始化时尝试从 storage 加载，仍为空返回 null。 */
function getSnapshot() {
  return ensureCache();
}
/**
 * 同步更新 session 的 lastScene，不触发新会话。
 *
 * 用于同一次回前台多 hook 携带不同 scene 时，避免重复 lt=1 后补写正确 scene。
 */
function syncLastScene(scene) {
  if (!scene) return;
  if (!cached$2) cached$2 = loadFromStorage();
  if (!cached$2) return;
  storage.set(KEY_LAST_SCENE, scene);
  cached$2.lastScene = scene;
}

/**
 * 页面路由适配。
 *
 * 私有版痛点（参考 `pageInfo.js#get_route / get_page_route / get_page_vm`）：
 *   - `get_page_route` 失败兜底用 `uni.getStorageSync('_STAT_LAST_PAGE_ROUTE')`，
 *     但这个 key 写入位置散落在 `report.js` 多处，时序复杂、容易脏。
 *   - 百度小程序 `_self.$mp.page.is` 取页面路由，逻辑硬编码在 `get_route` 里，
 *     新平台进来必须改这一处主流程。
 *   - `get_page_vm` 直接调 `getCurrentPages()`：在 `onHide` 之后窗口栈可能为空。
 *
 * 公有版职责：
 *   1. `getCurrentRoute()`：稳定获取当前页 path，支持显式传入 pageVm 与多端兜底。
 *   2. `getCurrentRouteWithQuery()`：取带 query 的完整 fullPath。
 *   3. `parseQuery()`：解析 query string 为对象（不依赖 url-search-params，nvue 兼容）。
 *   4. 全部 try/catch，永远返回 `string` / `object`，不返回 undefined。
 *
 * 与私有版兼容：上行字段 `url`（不含 query）/ `urlref`（前页 url）等仍由
 * `domain/statData` 拼装，本层只提供原料。
 */
/**
 * 判定当前 vm 是页面还是应用（对齐私有版 `pageInfo.js#get_page_types`）。
 *
 * Vue2 下应用前后台走 mixin 的 App `onShow` / `onHide`，不能仅靠 `uni.onAppShow`。
 */
function getPageVmType(vm) {
  var _a, _b, _c, _d, _e, _f, _g, _h;
  if (!vm) return null;
  const internalMpType = (_c = (_b = (_a = vm.$) === null || _a === void 0 ? void 0 : _a.type) === null || _b === void 0 ? void 0 : _b.mpType) !== null && _c !== void 0 ? _c : (_d = vm.type) === null || _d === void 0 ? void 0 : _d.mpType;
  if (vm.mpType === 'page' || vm.$mpType === 'page' || ((_e = vm.$mp) === null || _e === void 0 ? void 0 : _e.mpType) === 'page' || ((_f = vm.$options) === null || _f === void 0 ? void 0 : _f.mpType) === 'page' || internalMpType === 'page') {
    return 'page';
  }
  if (vm.mpType === 'app' || vm.$mpType === 'app' || ((_g = vm.$mp) === null || _g === void 0 ? void 0 : _g.mpType) === 'app' || ((_h = vm.$options) === null || _h === void 0 ? void 0 : _h.mpType) === 'app' || internalMpType === 'app') {
    return 'app';
  }
  return null;
}
/**
 * 取栈顶页面实例（vm）。
 *
 * 优先 `getCurrentPages()`；若不可用或栈为空返回 `undefined`。
 */
function getTopPageVm() {
  var _a;
  const fn = getGlobalObject().getCurrentPages;
  if (typeof fn !== 'function') return undefined;
  const pages = tryRun(() => fn(), []) || [];
  if (!Array.isArray(pages) || pages.length === 0) return undefined;
  const top = pages[pages.length - 1];
  return (_a = top === null || top === void 0 ? void 0 : top.$vm) !== null && _a !== void 0 ? _a : top;
}
/**
 * 取当前页面路径（不含 query）。
 *
 * 取值顺序：
 *   1. 显式 pageVm 优先（mixin 收到的 self/this）。
 *   2. 百度小程序：`vm.$mp.page.is` / `vm.$scope.is`。
 *   3. 通用：`vm.route` → `vm.$scope.route` → `vm.$mp.page.route`。
 *   4. 取栈顶 page 兜底。
 *   5. 全失败返回 ''。
 */
function getCurrentRoute(pageVm) {
  var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l;
  const vm = pageVm !== null && pageVm !== void 0 ? pageVm : getTopPageVm();
  if (!vm) return '';
  if (getPlatform() === 'bd') {
    const r = (_e = (_c = (_b = (_a = vm.$mp) === null || _a === void 0 ? void 0 : _a.page) === null || _b === void 0 ? void 0 : _b.is) !== null && _c !== void 0 ? _c : (_d = vm.$scope) === null || _d === void 0 ? void 0 : _d.is) !== null && _e !== void 0 ? _e : '';
    if (r) return r;
  }
  return (_l = (_h = (_f = vm.route) !== null && _f !== void 0 ? _f : (_g = vm.$scope) === null || _g === void 0 ? void 0 : _g.route) !== null && _h !== void 0 ? _h : (_k = (_j = vm.$mp) === null || _j === void 0 ? void 0 : _j.page) === null || _k === void 0 ? void 0 : _k.route) !== null && _l !== void 0 ? _l : '';
}
/**
 * 取当前页 fullPath（含 query）；无 query 返回与 `getCurrentRoute` 一致。
 *
 * 取值顺序：vm.$page.fullPath → vm.$scope.$page.fullPath → 退化 route。
 * 与私有版一致：fullPath === '/' 时退到 route，避免根路径 query 丢失。
 */
function getCurrentRouteWithQuery(pageVm) {
  var _a, _b;
  const vm = pageVm !== null && pageVm !== void 0 ? pageVm : getTopPageVm();
  if (!vm) return '';
  const page = (_a = vm.$page) !== null && _a !== void 0 ? _a : (_b = vm.$scope) === null || _b === void 0 ? void 0 : _b.$page;
  if (page) {
    if (page.fullPath && page.fullPath !== '/') return page.fullPath;
    if (page.route) return page.route;
  }
  return getCurrentRoute(vm);
}

/**
 * 应用生命周期 + 场景值适配。
 *
 * 公有版职责：
 *   1. 把 `uni.onAppShow / onAppHide / onLaunch` 这一组事件抽象成"订阅 + 解绑"形式，
 *      供 `domain/session` 与 `pipeline/collector` 复用，避免业务层直接吃 uni API。
 *   2. 兜底所有调用：uni 缺失时 unsubscribe 为 noop，订阅失败不抛。
 *   3. `getLaunchScene()`：私有版 `get_scene` 仅限 wx，公有版补全 mp-qq / mp-toutiao /
 *      mp-baidu / 阿里系小程序宿主 / mp-lark / mp-kuaishou，并允许覆写（页面自带 scene）。
 *
 * 注意：本模块不维护订阅注册表（去重逻辑由 `infra/interceptor` 与 `runtime/install`
 * 处理），保持单一职责。
 */
function getUni$9() {
  const u = resolveUniRuntime();
  return u != null && typeof u === 'object' ? u : undefined;
}
/**
 * 启动时取场景值。优先级：
 *   1. 调用方显式传入 `override`（如页面 onLoad 收到的 options.scene）。
 *   2. `uni.getLaunchOptionsSync().scene`（多端通用）。
 *   3. 不识别的平台返回空字符串。
 *
 * 公有版扩展：所有小程序宿主（`mp-*`，含 wx/qq/tt/bd/阿里系/lark/ks/xhs/jd/harmony 等）
 * 均支持 `getLaunchOptionsSync().scene`，故统一以 `isMp()` 判定，避免逐个平台维护白名单时
 * 漏掉新增小程序端导致 scene 恒为空（H5 / App / 快应用无场景值，返回空串）。
 */
function getLaunchScene(override) {
  if (override !== undefined && override !== null && override !== '') {
    return String(override);
  }
  const u = getUni$9();
  if (typeof (u === null || u === void 0 ? void 0 : u.getLaunchOptionsSync) !== 'function') return '';
  // 仅小程序宿主有有意义的 scene；其它端即便存在 getLaunchOptionsSync 也无场景值。
  if (!isMp()) return '';
  return tryRun(() => {
    const opts = u.getLaunchOptionsSync();
    const scene = opts === null || opts === void 0 ? void 0 : opts.scene;
    return scene === undefined || scene === null ? '' : String(scene);
  }, '');
}

/**
 * uniPush ClientID 适配。
 *
 * 私有版（`core/stat.js#pushEvent`）逻辑：
 *   - 调 `uni.getPushClientId({ success(res){ cid = res.cid } })`，无 cid 直接丢弃。
 *   - 没有超时；某些机型 push 服务异常时，回调永远不来，导致这次 launch 的 push 上报丢失。
 *   - 返回值包在 success 回调里，无法 await，不便 pipeline 串接。
 *
 * 公有版职责：
 *   1. `getPushClientId({ enabled, timeoutMs })` 返回 `Promise<PushClientResult>`，
 *      永不 reject；超时 / 失败 / 关闭统一返回 `{ ok: false, cid: '' }`。
 *   2. `enabled` 默认 false（合规要求显式开启）；调用方应从 `config.uniPushClientID`
 *      透传。
 *   3. 不缓存：业务方需要会话维度复用时在 `domain/push.ts` 中缓存（待 Phase 5 接入）。
 */
function getUni$8() {
  const u = resolveUniRuntime();
  return u != null && typeof u === 'object' ? u : undefined;
}
/**
 * 异步取 push clientId。
 *
 * 任意异常路径都 resolve（永不 reject），调用方只需根据 `ok` 字段判断是否上报。
 */
function getPushClientId(opts = {}) {
  const {
    enabled = false,
    timeoutMs = 3000
  } = opts;
  return new Promise(resolve => {
    if (!enabled) {
      resolve({
        ok: false,
        cid: '',
        reason: 'disabled'
      });
      return;
    }
    const u = getUni$8();
    if (!u || typeof u.getPushClientId !== 'function') {
      resolve({
        ok: false,
        cid: '',
        reason: 'unsupported'
      });
      return;
    }
    let settled = false;
    const finish = r => {
      if (settled) return;
      settled = true;
      resolve(r);
    };
    const timer = setTimeout(() => finish({
      ok: false,
      cid: '',
      reason: 'timeout'
    }), timeoutMs);
    tryRun(() => u.getPushClientId({
      success: res => {
        clearTimeout(timer);
        const cid = typeof (res === null || res === void 0 ? void 0 : res.cid) === 'string' ? res.cid : '';
        if (!cid) {
          finish({
            ok: false,
            cid: '',
            reason: 'fail'
          });
          return;
        }
        finish({
          ok: true,
          cid
        });
      },
      fail: () => {
        clearTimeout(timer);
        finish({
          ok: false,
          cid: '',
          reason: 'fail'
        });
      }
    }), undefined);
  });
}

/**
 * 生命周期 → collector 调度桥。
 *
 * 把 vue mixin / `uni.onAppShow|onAppHide` / push clientId 这些"运行时事件源"
 * 翻译成 collector 的 `report({lt, ...})` 调用，统一处理：
 *   - 会话状态机（ensureSession / markBackground）。
 *   - 入口页登记（entryPage）。
 *   - lastRoute / urlref / urlref_ts 维护。
 *   - 新会话首报：仅发一条 `lt=1`（Launch），新会话字段（sid/cst/fvts/lvts/tvc）随之上行；
 *     `app_show` 新 sid 后立即 **flush(true)**；`page_show`（cst=3）新 sid 在本轮 lt=11
 *     入队后 **flush(true)**（同批内 `LT_ORDER` 保证 lt=1 先于 lt=11）。与 `app_hide` 的
 *     lt=3+flush 一并降低「锚点未送达、后续已用新 sid」的丢失风险（与参数文档对齐；
 *     不再发已废弃的 `lt=0`）。
 *   - push CID 异步抓取后再发 `lt=101`，超时 / 失败静默丢弃。
 *
 * 暴露：
 *   - `bindLifecycle(app, opts?)`：返回 mixin / onAppShow / onAppHide 句柄与
 *     unbind 函数，runtime/install.ts 据此装到 vue & uni 上。
 *   - 内部句柄（`onLaunch / onAppShow / onAppHide / onPageShow / onPageHide / onError`）
 *     单独导出便于单测精准触发。
 *
 * 注意：本模块**不直接**依赖任何 adapter（除 `getCurrentRoute*` 与 `getLaunchScene`），
 * adapter 调用全部走 `tryRun` 兜底，单端缺失不影响调度。
 */
const EMPTY_TITLE_SNAP = {
  ttn: '',
  ttpj: '',
  ttc: ''
};
/** 模块级状态。`bindLifecycle` 返回的 unbind 仅断订阅，不重置 state。 */
const state$1 = {
  lastRoute: '',
  lastRouteFull: '',
  beforeLastRoute: '',
  beforeLastRouteFull: '',
  lastRouteEnterTime: 0,
  lastPageTitleSnap: Object.assign({}, EMPTY_TITLE_SNAP),
  lastIey: false,
  prevIey: false,
  isHide: false,
  wasBackgrounded: false,
  pendingBackgroundResume: false,
  backgroundEnteredAt: 0,
  suppressNextPageLogAfterResume: false,
  backgroundResumeLt1At: 0
};
/** Vue2 H5 hide 过程中偶发 page onShow（间隔≈0s），低于此阈值不消费 pending。 */
const BACKGROUND_RESUME_DEBOUNCE_SEC = 1;
/** 同一次回前台多 hook 重复 lt=1 的去重窗口（秒）。 */
const BACKGROUND_RESUME_LT1_DEDUP_SEC = 3;
/** 小程序等：page onHide 延迟判定「真进后台」；切页会在短时内 onShow 并取消。 */
const PAGE_APP_HIDE_DEFER_MS = 120;
let pageAppHideDeferTimer;
/**
 * Vue3 小程序等已绑定 `uni.onAppShow` 时，后台恢复应仅由 `handleAppShow` 消费。
 *
 * mixin / page onShow 过早消费会在 QQ 等端与 uni 回调形成双 hook，且 scene 不一致
 * （如 2001 vs 1011）导致重复 lt=1。Vue2 / H5 仍走 mixin 提前消费以适配 Page 先于 App onShow。
 */
function shouldEarlyConsumeBackgroundResumeInMixin() {
  return !shouldBindUniAppLifecycle();
}
/**
 * 记录本进程内最近一次后台恢复 lt=1 上报时刻。
 */
function markBackgroundResumeLt1Emitted(now) {
  state$1.backgroundResumeLt1At = now;
}
/**
 * 同一次回前台是否已在去重窗口内上报过后台恢复 lt=1。
 */
function shouldSkipDuplicateBackgroundResumeLt1(now) {
  return state$1.backgroundResumeLt1At > 0 && now - state$1.backgroundResumeLt1At <= BACKGROUND_RESUME_LT1_DEDUP_SEC;
}
/**
 * 取消 page onHide 触发的延迟进后台判定（Vue2/Vue3 共用）。
 */
function cancelPageAppHideDefer() {
  if (pageAppHideDeferTimer !== undefined) {
    clearTimeout(pageAppHideDeferTimer);
    pageAppHideDeferTimer = undefined;
  }
}
/**
 * H5 进后台时部分工程只触发 page onHide（Vue2/Vue3 均可能出现），
 * 需在 visibility 已为 hidden 时补记 lt=3；普通切页不会满足 hidden。
 */
function tryAppHideFromPageOnHideWhenH5Hidden(app, opts) {
  var _a;
  if (!isH5()) return;
  if (state$1.pendingBackgroundResume) return;
  const vis = (_a = globalThis.document) === null || _a === void 0 ? void 0 : _a.visibilityState;
  if (vis === 'hidden') {
    handleAppHide(app, opts);
  }
}
/**
 * 小程序等非 H5：page onHide 后短时延迟补记 lt=3；若随后 page onShow 则取消（切页）。
 */
function tryAppHideFromPageOnHideWhenMpDefer(app, opts) {
  if (isH5()) return;
  if (state$1.pendingBackgroundResume) return;
  cancelPageAppHideDefer();
  pageAppHideDeferTimer = setTimeout(() => {
    pageAppHideDeferTimer = undefined;
    if (state$1.pendingBackgroundResume) return;
    handleAppHide(app, opts);
  }, PAGE_APP_HIDE_DEFER_MS);
}

/**
 * Vue2 部分端进后台只触发 page onHide，须在此时补 `handleAppHide`。
 *
 * 普通切页也会触发 page onHide，**不能**无条件补记（否则多报 lt=3）。
 * 对齐私有版 `pageHide`：仅当 `__licationHide` 为真时不再发页面离开；此处等价于：
 *   - H5：`document.visibilityState === 'hidden'` 才补记；
 *   - 其它端：短时延迟，若下一页 onShow 则取消（切页），否则视为进后台。
 */
function tryVue2AppHideFromPageOnHide(app, opts) {
  if (state$1.pendingBackgroundResume) return;
  if (isH5()) {
    tryAppHideFromPageOnHideWhenH5Hidden(app, opts);
    return;
  }
  tryAppHideFromPageOnHideWhenMpDefer(app, opts);
}

/**
 * 取 collector；未 install 时返回 undefined（调用方需负责 noop）。
 */
function safeCollector(app) {
  return app.getCollector();
}
/**
 * 将 onLaunch / onShow 透传的 path 归一为 `markEntryPage` 使用的 route（去 query、去前导 `/`）。
 *
 * 与 `getCurrentRoute()` 常见返回值对齐，避免入口登记与实际页面 path 不一致。
 */
function normalizePathForEntryMark(raw) {
  var _a;
  if (!raw || typeof raw !== 'string') return '';
  const noQuery = (_a = raw.split('?')[0]) !== null && _a !== void 0 ? _a : '';
  return noQuery.startsWith('/') ? noQuery.slice(1) : noQuery;
}
/**
 * 新会话首报：仅发一条 `lt=1`（Launch），新会话字段随之上行。
 *
 * 重要约束（修复 lvts=0 / lvts 缺失缺陷）：
 *   - 进程内首次 lt=1（cold_launch）调用 `buildVisitFields`；
 *   - cst=2/3 新会话 lt=1 调用 `buildVisitFieldsForSessionRenewal`，仍携带 fvts/lvts/tvc，
 *     避免 lvts 缺失被服务端误判为新用户。
 *   - 通过 `firstVisitEmittedInProcess` 哨兵区分上述两条路径。
 *   - `cst` 入参仅用于将来可能的本地侧打印 / 监控；上行字段已由 statData 从 session
 *     snapshot 中读取（出口字段名为 `cst`）。
 *   - `url` 参数：参数文档要求 `lt=1` 携带当前启动页的完整 url；冷启动 / app_show
 *     可从 launch options.path 兜底；page_show 触发的 cst=3 由调用方直接传当前页路径。
 */
function reportNewSession(c, _cst, scene, now, attachVisit, url = '') {
  let visit;
  if (attachVisit && !firstVisitEmittedInProcess) {
    firstVisitEmittedInProcess = true;
    visit = tryRun(() => buildVisitFields(now), undefined);
  } else {
    // 续会话（attachVisit=false），或同进程内冷启 lt=1 已发过又被二次触发
    // （attachVisit=true 但 firstVisitEmittedInProcess 已 true）：都复用 renewal 字段，
    // 确保 lt=1 始终携带 fvts/lvts/tvc，杜绝"裸 lt=1 缺 lvts 被服务端按新增计入"。
    visit = tryRun(() => buildVisitFieldsForSessionRenewal(now), undefined);
  }
  const payload = {
    lt: LT.Launch,
    t: now,
    sc: scene,
    visit
  };
  // url 仅当非空时携带；避免 lt=1 上行体出现 url=""（参数文档要求 url 至多 255 字符，但允许缺省）。
  if (url) payload.url = url;
  c.report(payload);
}
/** 进程内是否已发过首批访问字段（fvts/lvts/tvc）。 */
let firstVisitEmittedInProcess = false;
/**
 * 标题三元组快照代数：hide 优先写入快照并 ++；show 尾部 microtask 携带快照时的代数，
 * 若已被 hide 抢先递增则丢弃 microtask，避免「新页刚灌的 ttpj」顶替「离开页」应有的 ttn/ttc。
 */
let titleSnapGeneration = 0;
/** 在同步栈清空后再采样标题，确保晚于页面自己的 onShow / setNavigationBarTitle。 */
function scheduleDeferredTitleSnapshot() {
  const gen = titleSnapGeneration;
  const run = typeof queueMicrotask === 'function' ? queueMicrotask : fn => {
    void Promise.resolve().then(fn);
  };
  run(() => {
    tryRun(() => {
      if (gen !== titleSnapGeneration) return;
      state$1.lastPageTitleSnap = Object.assign({}, getCurrentTitle());
    }, undefined);
  });
}
/**
 * App.onLaunch：冷启动入口。
 *
 * 流程：
 *   1. ensureSession('cold_launch') → cst=1，必产新 session。
 *   2. 发一条 lt=1（携带 sid/cst/fvts/lvts/tvc/sc/url）。
 *   3. 异步抓 push CID，成功后发 lt=101。
 *   4. 兜底 onLaunch options 可能携带 scene / path（小程序）；path 透传成 lt=1 的 url。
 */
function handleLaunch(app, options = {}, opts = {}) {
  const c = safeCollector(app);
  if (!c) return;
  const now = nowSec();
  const scene = tryRun(() => getLaunchScene(options.scene), '');
  const result = tryRun(() => ensureSession('cold_launch', {
    now,
    scene
  }), null);
  if (!result) return;
  // 冷启动同样视为新会话：清旧入口登记，再按 launch path 登记入口，最后发 lt=1（不含 iey，入口仅 lt=11）。
  tryRun(() => clearEntry(), undefined);
  const url = options.path || '';
  const entryKey = normalizePathForEntryMark(url);
  if (entryKey) {
    tryRun(() => markEntryPage(entryKey), undefined);
  }
  reportNewSession(c, result.cst || CST.ColdLaunch, scene, now, true, url);
  if (opts.enablePush) {
    void getPushClientId({
      enabled: true,
      timeoutMs: opts.pushTimeoutMs
    }).then(r => {
      if (!r.ok || !r.cid) return;
      const c2 = safeCollector(app);
      if (!c2) return;
      c2.report({
        lt: LT.Push,
        cid: r.cid,
        t: nowSec()
      });
    }).catch(e => logger.warn('[uni统计 2.0] push cid fetch failed', e));
  }
}
/**
 * 消费「从后台回前台」会话判定（cst=2）；返回 true 表示已处理（含防抖跳过但仍保留 pending）。
 *
 * Vue2：Page onShow 常早于 App onShow，且 hide 过程中可能误触发一次 page onShow，
 * 若在那时清空 pending/wasBackgrounded，App onShow 将看不到后台标记（用户截图现象）。
 */
function tryConsumeBackgroundResume(app, options = {}, _opts = {}, _from = 'unknown') {
  if (!state$1.pendingBackgroundResume) {
    return false;
  }
  const bgEnterAt = state$1.backgroundEnteredAt;
  if (bgEnterAt <= 0) {
    return false;
  }
  const c = safeCollector(app);
  if (!c) {
    return false;
  }
  const now = nowSec();
  const elapsed = now - bgEnterAt;
  if (elapsed < BACKGROUND_RESUME_DEBOUNCE_SEC) {
    state$1.suppressNextPageLogAfterResume = true;
    return true;
  }
  state$1.wasBackgrounded = false;
  state$1.suppressNextPageLogAfterResume = true;
  state$1.lastRouteEnterTime = now;
  const scene = tryRun(() => getLaunchScene(options.scene), '');
  const result = tryRun(() => ensureSession('app_show', {
    now,
    scene,
    backgroundEnteredAt: bgEnterAt
  }), null);
  state$1.pendingBackgroundResume = false;
  state$1.backgroundEnteredAt = 0;
  if (!result || !result.isNew) {
    return true;
  }
  tryRun(() => clearEntry(), undefined);
  const url = options.path || state$1.lastRoute || '';
  const entryKey = normalizePathForEntryMark(url);
  if (entryKey) {
    tryRun(() => markEntryPage(entryKey), undefined);
  }
  reportNewSession(c, result.cst || CST.BackgroundTimeout, scene, now, false, url);
  markBackgroundResumeLt1Emitted(now);
  void c.flush(true).catch(e => logger.warn('[uni统计 2.0] flush after new session (app_show) failed', e));
  return true;
}
/**
 * 应用从后台进入前台。
 *
 * 流程：
 *   1. `tryConsumeBackgroundResume`（pending）→ ensureSession('app_show') / cst=2。
 *   2. isNew=true 时发一条 lt=1，并 **flush(true)**。
 *   3. 无 pending 时仅处理 scene 变化等（少见）。
 */
function handleAppShow(app, options = {}, opts = {}) {
  if (tryConsumeBackgroundResume(app, options, opts, 'handleAppShow')) return;
  const c = safeCollector(app);
  if (!c) return;
  const now = nowSec();
  const scene = tryRun(() => getLaunchScene(options.scene), '');
  if (shouldSkipDuplicateBackgroundResumeLt1(now)) {
    tryRun(() => syncLastScene(scene), undefined);
    return;
  }
  const result = tryRun(() => ensureSession('app_show', {
    now,
    scene
  }), null);
  if (!result || !result.isNew) {
    return;
  }
  tryRun(() => clearEntry(), undefined);
  const url = options.path || state$1.lastRoute || '';
  const entryKey = normalizePathForEntryMark(url);
  if (entryKey) {
    tryRun(() => markEntryPage(entryKey), undefined);
  }
  reportNewSession(c, result.cst || CST.BackgroundTimeout, scene, now, false, url);
  markBackgroundResumeLt1Emitted(now);
  void c.flush(true).catch(e => logger.warn('[uni统计 2.0] flush after new session (app_show) failed', e));
}
/**
 * 应用进入后台。
 *
 * 流程：
 *   1. markBackground(now)：写 bgTs，让下次 app_show 能算超时。
 *   2. 若存在当前页且启用页面日志：先发一条 lt=11，闭合"离开当前页"语义（含 url/urlref/urlref_ts/iey/ppiey/title）。
 *   3. 再发 lt=3：保留"应用进入后台"语义（urlref=urlref_ts 指向后台前最后可见页）。
 *   4. 进入后台后强制 flush（force=true），尽量在被 kill 前送出。
 */
function handleAppHide(app, opts = {}) {
  if (state$1.pendingBackgroundResume) return;
  const c = safeCollector(app);
  if (!c) return;
  const now = nowSec();
  state$1.wasBackgrounded = true;
  state$1.pendingBackgroundResume = true;
  state$1.backgroundEnteredAt = now;
  tryRun(() => markBackground(now), undefined);
  const deltaStay = state$1.lastRouteEnterTime > 0 ? now - state$1.lastRouteEnterTime : 0;
  const stayed = clampUrlrefStaySec(deltaStay);
  if (state$1.lastRoute && opts.enablePageLog !== false) {
    const exitedUrl = state$1.lastRouteFull || state$1.lastRoute;
    const ref = state$1.beforeLastRouteFull || state$1.beforeLastRoute || '';
    const snap = state$1.lastPageTitleSnap;
    const payload = {
      lt: LT.Page,
      t: now,
      url: exitedUrl,
      urlref_ts: stayed,
      iey: state$1.lastIey,
      ppiey: state$1.prevIey,
      ttn: snap.ttn,
      ttpj: snap.ttpj,
      ttc: snap.ttc
    };
    if (ref) payload.urlref = ref;
    c.report(payload);
    if (state$1.lastIey) {
      tryRun(() => markEntryDeparted(), undefined);
      state$1.lastIey = false;
    }
  }
  c.report({
    lt: LT.Hide,
    t: now,
    urlref: state$1.lastRoute,
    urlref_ts: stayed
  });
  void c.flush(true).catch(e => logger.warn('[uni统计 2.0] flush on hide failed', e));
}
/**
 * Page.onShow：页面前台展示。
 *
 * `lt=11`（页面日志）在**进入新页**的 `onShow` 触发，但语义描述的是**刚刚离开的页面**
 *（只有离开后才能闭合停留时长、导航栏标题等）：
 *
 *   - `url`：离开页的完整路径（含 query），来自上一次 onShow 结束时登记的 `lastRouteFull`。
 *   - `urlref`：再上一层的来源页（「上上个页面」），来自 `beforeLastRouteFull`；
 *     首次从启动页外跳（只有一层来源）时不带 `urlref`。
 *   - `urlref_ts`：离开页停留秒数（`now - lastRouteEnterTime`，不足 1 秒按 1 秒，对齐私有版）。
 *   - `iey` / `ppiey`：分别对应**离开页**是否仍为有效入口、`urlref` 指向页是否仍为有效入口
 *     （会话内仅**首次离开**登记入口为 1；循环回到入口后再离开不算）。
 *   - `ttn` / `ttpj` / `ttc`：三维独立内存（API 导航栏 / pages.json / uni.report('title')），
 *     **同一事件可同时非空**。离开页快照优先在 **`onHide` 且 `clearPageTitle` 之前**落盘；
 *     无 hide 场景依赖 **microtask**（晚于业务 `onShow`）— 由 `titleSnapGeneration` 防止被下一页 show 尾部误覆盖。
 *
 * 首次应用内 onShow（无前序页面）不发 `lt=11`。`enablePageLog=false` 时跳过整段 `lt=11`。
 */
function handlePageShow(app, vm, opts = {}) {
  const c = safeCollector(app);
  if (!c) return;
  if (state$1.pendingBackgroundResume && shouldEarlyConsumeBackgroundResumeInMixin()) {
    tryConsumeBackgroundResume(app, {}, opts, 'handlePageShow');
  }
  const now = nowSec();
  const route = tryRun(() => getCurrentRoute(vm), '');
  const url = tryRun(() => getCurrentRouteWithQuery(vm), '') || route;
  /**
   * H5/部分端存在"App.onShow 也会打到 mixin onShow"的情况，此时 this 并非页面 vm，
   * route/fullPath 为空。该事件应由 `handleAppShow` 处理，不能当 page_show。
   */
  if (!route && !url) return;
  const result = tryRun(() => ensureSession('page_show', {
    now
  }), null);
  if (!result) return;
  // 每页重置「自定义上报标题」维（ttc）；注入 pages.json 导航标题 → `ttpj`。
  //
  // **禁止**在此处调用 `clearPageTitle()`：uni-app 页面 `onLoad` 早于统计 mixin 的 `onShow`，
  // 业务常在 `onLoad` 里 `uni.setNavigationBarTitle`，拦截器已写入 `ttn`；若此处再清 page，
  // 会把刚设好的 ttn 抹掉。**跨页**时由 `handlePageHide` 在快照后 `clearPageTitle` 即可。
  tryRun(() => setReportTitle(''), undefined);
  tryRun(() => setConfigTitle(getPagesJsonNavigationTitle(route)), undefined);
  if (result.isNew) {
    // 新会话：清 entry → 先登记当前页为会话入口（与 lt=1「落地即入口」一致）→ 再发 lt=1。
    tryRun(() => clearEntry(), undefined);
  }
  if (route) {
    tryRun(() => markEntryPage(route), undefined);
  }
  if (result.isNew) {
    // cst=3：复用 committed visit 字段，与私有版 sendReportRequest 对齐。
    // 注意：lt=1（新会话首报）**不受** enablePageLog 控制 —— 与私有版语义一致，
    // is_page_report 仅拦截 pageShow/pageHide，不影响 launch/appShow/appHide。
    reportNewSession(c, result.cst || CST.PageInactiveTimeout, '', now, false, url);
  }
  // 存在上一页 → 发 lt=11：描述「离开的上一页」，而非当前 vm 所在页。
  const shouldSuppressPageLog = state$1.suppressNextPageLogAfterResume;
  if (state$1.lastRoute && opts.enablePageLog !== false && !shouldSuppressPageLog) {
    const deltaStay = state$1.lastRouteEnterTime > 0 ? now - state$1.lastRouteEnterTime : 0;
    const stayed = clampUrlrefStaySec(deltaStay);
    const exitedUrl = state$1.lastRouteFull || state$1.lastRoute;
    const ref = state$1.beforeLastRouteFull || state$1.beforeLastRoute || '';
    const snap = state$1.lastPageTitleSnap;
    const payload = {
      lt: LT.Page,
      t: now,
      url: exitedUrl,
      urlref_ts: stayed,
      // 离开页是否入口页 / urlref 指向页是否入口页（进入新页前状态尚未被本轮覆盖）。
      iey: state$1.lastIey,
      ppiey: state$1.prevIey
    };
    if (ref) payload.urlref = ref;
    // 三维并列上行，不因其一存在而省略其它；空串由 builder/omit 统一处理
    payload.ttn = snap.ttn;
    payload.ttpj = snap.ttpj;
    payload.ttc = snap.ttc;
    c.report(payload);
    if (state$1.lastIey) {
      tryRun(() => markEntryDeparted(), undefined);
    }
  }
  // 轮换路由链：当前页在下一轮成为「上一页」。
  state$1.beforeLastRoute = state$1.lastRoute;
  state$1.beforeLastRouteFull = state$1.lastRouteFull;
  state$1.prevIey = state$1.lastIey;
  state$1.lastIey = !!route && tryRun(() => isEntryForIey(route), false);
  state$1.lastRoute = route;
  state$1.lastRouteFull = url;
  state$1.lastRouteEnterTime = now;
  state$1.suppressNextPageLogAfterResume = false;
  // 不在此处同步快照：此时 lastRoute 已指向新页，getCurrentTitle 会是新页 ttpj+空 ttn，造成顶替。
  // 离开页快照见 handlePageHide（优先）；否则见 scheduleDeferredTitleSnapshot。
  scheduleDeferredTitleSnapshot();
  state$1.isHide = false;
  // cst=3 新会话：本 tick 内可能已入队 lt=1 与（若有上一页）lt=11；serializer 按 LT_ORDER
  // 保证同批内 lt=1 先于 lt=11。此处强制 flush，避免仍等 reportInterval 才被杀死丢锚点。
  if (result.isNew) {
    void c.flush(true).catch(e => logger.warn('[uni统计 2.0] flush after new session (page_show) failed', e));
  }
}
/**
 * Page.onHide / Page.onUnload：页面隐藏 / 卸载。
 *
 * 私有版用 `isHide` 区分 onUnload 是隐藏还是真离开；本模块同样兼容。
 *
 * 公有版调整（与 `docs/uni统计上报参数.md` 对齐）：
 *   - `lt=11` 不在 onHide 上报；页面离开闭环由「下一次 `handlePageShow` 或 `handleAppHide`」触发。
 *   - onHide 仅做收尾：标记 isHide、清掉自定义 title，避免下次新页空标题。
 *   - lastRoute / lastRouteEnterTime / lastIey 保持不变，由 `handlePageShow` 统一切换。
 */
function handlePageHide(app, _vm) {
  const c = safeCollector(app);
  if (!c) return;
  state$1.isHide = true;
  // 离开前快照：此时仍保留「本页」ttpj/ttn/ttc；清空 page 维后仅丢 ttn，故必须先快照
  titleSnapGeneration++;
  state$1.lastPageTitleSnap = Object.assign({}, getCurrentTitle());
  tryRun(() => clearPageTitle(), undefined);
}
/**
 * 已经被本模块"异步重抛"过的错误实例，用于阻断 `onError → 重抛 → onError` 死循环。
 *
 * ## 选 WeakSet 的原因
 *   - 弱引用语义：业务方在外部 catch 这些 error 后，error 仍可被 GC，不内存泄漏。
 *   - uni-app 全端原生支持（H5 / 微信/支付宝/百度/字节 等小程序 / App-iOS/Android /
 *     nvue / uvue / 鸿蒙）—— vue runtime 自身大量使用 WeakSet/WeakMap 做响应式，
 *     任何不支持 WeakSet 的环境，vue 本身就起不来。
 *
 * ## 为什么仍然加 typeof 守卫
 *   作为 SDK 必须 defensive。万一极端环境（自定义沙箱阉割、业务代码 `delete
 *   globalThis.WeakSet`、SSR mock 等）导致 `new WeakSet()` 抛错，会让整个统计模块
 *   在初始化期 `ReferenceError` 加载失败 —— 过激的失败模式。
 *
 *   降级策略：退化为 has=false / add=noop 的 stub。后果是失去防重入保护，但 SDK
 *   仍可正常工作；最坏情况（小程序端 setTimeout 重抛被 mixin 二次接住）会触发
 *   一次额外的 setTimeout（仍是异步、不会同步阻塞），第二次 setTimeout 抛出后会
 *   到达全局 onError，仍然不会无限循环 —— 影响完全可控。
 *
 * ## 仅处理 object 类型
 *   非 object 错误（极少见的 `throw 'string'` / `throw 42` 等）无法进 WeakSet；
 *   且重抛非 object 在多数端的全局 onError 不会再次触发 vue mixin 的 onError，
 *   无重入风险，无需特殊处理。
 */
const rethrownErrors = typeof WeakSet === 'function' ? new WeakSet() :
// 极端环境降级：has=false 永不命中，add=noop；本模块只用 has/add 两个方法，
// 其它方法（delete / [Symbol.toStringTag]）调用方不依赖，类型断言即可。
{
  has: () => false,
  add: () => rethrownErrors
};
/**
 * onError：上报错误（lt=31）+ 异步重抛，让错误回归原生 "Uncaught Error" 通路。
 *
 * ## 设计目标：统计是**旁路监听**，绝不侵入业务方的报错体验
 *
 * ### 私有版（含早期公有版）的两种错误做法都不达标
 *
 * 1. **私有版 `src/index.js#onError`**：仅 `stat.error(e)`，**完全吞掉错误**。
 *    一旦 mixin 注册了 onError，uni-app/Vue 视为业务已处理 → Vue 不再 console.error
 *    → 业务方在 H5 端排错时控制台一片空白，看不到任何 stack。
 *
 * 2. **早期公有版 `console.error(e)` 兜底**：能看到 stack，但 devtools 会把
 *    `console.error` 的**调用文件**（即 SDK 路径 `uni-stat-public.es.js:行号`）
 *    显示在控制台日志右侧的"来源"列。业务方误以为统计 SDK 出现在他们的错误栈里，
 *    与"旁路监听"承诺相悖。
 *
 * ### 当前方案：`setTimeout(() => { throw e }, 0)` 异步重抛（**仅非小程序**）
 *
 * - **H5 / App 等**：错误进入浏览器 / 原生 "Uncaught Exception" 通路（同 `window.onerror`），
 *   与**完全没接入统计**时的默认行为一致，且控制台「来源」指向用户任务而非 SDK。
 *
 * - **各小程序（`mp-*`）**：**不重抛**。运行时已在首次异常路径打印 `MiniProgramError` 等；
 *   若再 `setTimeout(throw)`，会二次进入全局 `onError`，且微信往往传入**新的包装对象**，
 *   `WeakSet` 无法按引用去重 → 多条 `lt=31`、控制台刷屏。统计在此只做旁路上报。
 *
 * ### 防重入（主要针对仍走重抛的环境）
 *
 * 重抛后可能被二次回调；用 `rethrownErrors`(WeakSet) 标记已处理的 error 实例。
 *
 * ### 顺序
 *
 * 1. **先标记重入防护** —— 防止极端竞态下 setTimeout 在同步上报完成前已 fire。
 * 2. **再上报** —— 同步执行，确保 lt=31 一定入队。
 * 3. **非小程序**：**最后**异步重抛 —— `setTimeout 0` 排到下一 task；小程序端跳过此步。
 *
 * 外层 `try/catch` 仅兜底 `reportError` 自身抛错（与私有版一致）；`tryRun` 兜底
 * `setTimeout` 在极端环境（如 SSR / 被 mock 的 timer）下不可用的情况。
 */
function handleError(app, e) {
  const isObj = typeof e === 'object' && e !== null;
  if (isObj && rethrownErrors.has(e)) return;
  if (isObj) rethrownErrors.add(e);
  try {
    app.reportError(e);
  } catch (err) {
    logger.warn('[uni统计 2.0] handleError failed', err);
  }
  if (isMp()) {
    return;
  }
  tryRun(() => {
    setTimeout(() => {
      throw e;
    }, 0);
  }, undefined);
}
function getUni$7() {
  const u = resolveUniRuntime();
  return u != null && typeof u === 'object' ? u : undefined;
}
/**
 * 是否由 mixin 分发 App 级 onShow/onHide（对齐私有版 `stat.show` / `stat.hide`）。
 *
 * - Vue2：始终走 mixin（`load_stat` 不注册 uni.onAppShow/Hide）。
 * - Vue3：仅 H5 / nvue 走 mixin；小程序等走 `uni.onAppShow` / `onAppHide`。
 *
 * 使用赋值而非连续 `return`：公有版 dist 经 Rollup 打包时，连续 return 会导致
 * `#ifdef VUE3` 分支被 tree-shake；应用构建再剥离 `#ifndef VUE3` 后函数体为空 → undefined。
 */
function shouldMixinDispatchAppLifecycle() {
  let result = isH5() || getPlatform() === 'n' || isNvue();
  result = true;
  return result;
}
/**
 * 是否注册 `uni.onAppShow` / `onAppHide`（对齐私有版 `index.js#load_stat` VUE3 分支）。
 *
 * 仅 Vue3 且非 H5、非 nvue（即小程序等）为 true；Vue2 必须为 false。
 */
function shouldBindUniAppLifecycle() {
  let result = !isH5() && getPlatform() !== 'n' && !isNvue();
  result = false;
  return result;
}
const uniAppHookRegistry = {
  showBound: false,
  hideBound: false,
  appShowCb: undefined,
  appHideCb: undefined
};
/**
 * 订阅应用级 `uni.onAppShow` / `onAppHide`；`uni` 或 API 未就绪时返回 false，可稍后重试。
 *
 * show/hide 分别绑定：避免 `onAppShow` 晚就绪时连 `onAppHide` 也无法注册（lt=3 缺失）。
 */
function tryBindUniAppLifecycle(app, opts = {}) {
  if (!shouldBindUniAppLifecycle()) return false;
  const u = getUni$7();
  if (!u) return false;
  if (!uniAppHookRegistry.showBound && typeof u.onAppShow === 'function') {
    uniAppHookRegistry.appShowCb = e => handleAppShow(app, e !== null && e !== void 0 ? e : {}, opts);
    tryRun(() => u.onAppShow(uniAppHookRegistry.appShowCb), undefined);
    uniAppHookRegistry.showBound = true;
  }
  if (!uniAppHookRegistry.hideBound && typeof u.onAppHide === 'function') {
    uniAppHookRegistry.appHideCb = () => handleAppHide(app, opts);
    tryRun(() => u.onAppHide(uniAppHookRegistry.appHideCb), undefined);
    uniAppHookRegistry.hideBound = true;
  }
  return uniAppHookRegistry.showBound && uniAppHookRegistry.hideBound;
}
/** 解绑 `tryBindUniAppLifecycle` 注册的回调。 */
function unbindUniAppLifecycle() {
  if (!uniAppHookRegistry.showBound && !uniAppHookRegistry.hideBound) return;
  const cur = getUni$7();
  if (uniAppHookRegistry.showBound && uniAppHookRegistry.appShowCb && (cur === null || cur === void 0 ? void 0 : cur.offAppShow)) {
    tryRun(() => cur.offAppShow(uniAppHookRegistry.appShowCb), undefined);
  }
  if (uniAppHookRegistry.hideBound && uniAppHookRegistry.appHideCb && (cur === null || cur === void 0 ? void 0 : cur.offAppHide)) {
    tryRun(() => cur.offAppHide(uniAppHookRegistry.appHideCb), undefined);
  }
  uniAppHookRegistry.showBound = false;
  uniAppHookRegistry.hideBound = false;
  uniAppHookRegistry.appShowCb = undefined;
  uniAppHookRegistry.appHideCb = undefined;
}
/**
 * 装配 vue mixin；Vue3 小程序等另由 `tryBindUniAppLifecycle` 订阅 uni 应用前后台。
 *
 * 与私有版 `src/index.js` + `core/stat.js#show|hide` 对齐：
 *   - Vue2：仅 `Vue.mixin`，App/Page 均在 mixin 的 onShow/onHide 内分支。
 *   - Vue3：H5/nvue 的 App 前后台在 mixin；其它端用 uni.onAppShow/onAppHide。
 */
function bindLifecycle(app, opts = {}) {
  let bound = true;
  const mixin = {
    onLaunch(options = {}) {
      handleLaunch(app, options, opts);
    },
    onLoad() {
      // 保留钩子位，用于未来扩展（query 收集等）；当前 noop。
    },
    onShow() {
      const vmType = getPageVmType(this);
      cancelPageAppHideDefer();
      if (state$1.pendingBackgroundResume && shouldEarlyConsumeBackgroundResumeInMixin()) {
        tryConsumeBackgroundResume(app, {}, opts, 'mixin.onShow');
      }
      state$1.isHide = false;
      if (vmType === 'page') {
        handlePageShow(app, this, opts);
      }
      if (shouldMixinDispatchAppLifecycle() && vmType === 'app') {
        handleAppShow(app, {}, opts);
      }
    },
    onHide() {
      state$1.isHide = true;
      if (getPageVmType(this) === 'page') {
        handlePageHide(app);
        tryVue2AppHideFromPageOnHide(app, opts);
      }
      if (shouldMixinDispatchAppLifecycle() && getPageVmType(this) === 'app' && !state$1.pendingBackgroundResume) {
        handleAppHide(app, opts);
      }
    },
    onUnload() {
      if (state$1.isHide) {
        state$1.isHide = false;
        return;
      }
      handlePageHide(app);
    },
    onError(e) {
      handleError(app, e);
    }
  };
  if (shouldBindUniAppLifecycle()) {
    tryBindUniAppLifecycle(app, opts);
  }
  return {
    mixin,
    tryBindUniAppHooks: () => shouldBindUniAppLifecycle() && tryBindUniAppLifecycle(app, opts),
    unbind() {
      if (!bound) return;
      bound = false;
      unbindUniAppLifecycle();
    }
  };
}

/**
 * 公有版常量与可配置项的集中定义（版本号、URL、超时阈值等）。
 *
 * 该模块只导出**编译期常量**与**默认值**；运行时可变配置走 `runtime/StatApp` 注入。
 */
/**
 * 上行字段 `usv` 取值：**uni-app 编译器版本号**（与权威参数文档
 * `docs/uni统计上报参数.md` 中 `usv: "4.24"` 示例对齐）。
 *
 * 与私有版 `src/config.ts` 保持同源做法：直接读 `process.env.UNI_COMPILER_VERSION`，
 * 由 uni-cli 在用户应用打包阶段通过 vite `define` 替换成字面量字符串；
 * 运行时取不到时回退为空串，避免拼到 URL 时变成 `undefined`。
 *
 * 注意：这里**不再**硬编码统计实现版本。统计入口由 `src/plugin/index.ts`
 * 的统计类型（`public` / `private`）控制；
 * 与 `usv` 字段无关。
 */
const STAT_VERSION_PUBLIC = "5.26" || false;
/** 1.0 通道（HTTP）默认上报地址。 */
const STAT_URL = 'https://tongji.dcloud.io/uni/stat';
/** H5 image 兜底通道（绕过跨域）。 */
const STAT_H5_URL = 'https://tongji.dcloud.io/uni/stat.gif';
/** 默认上报间隔（秒）。queue 节流阈值。 */
const REPORT_INTERVAL_SEC = 10;
/** HTTP 协议层最大重试次数（含首次）。 */
const HTTP_MAX_RETRIES = 3;
/** Cloud 协议层最大重试次数（含首次）。 */
const CLOUD_MAX_RETRIES = 2;
/** Image 协议层最大重试次数（含首次）。 */
const IMAGE_MAX_RETRIES = 2;
/** 重试基础延迟（指数退避）。 */
const RETRY_BASE_DELAY_MS = 1000;
/**
 * 微信小程序是否用 `wx.preloadAssets` + `WebTrack.gif` GET 上报。
 *
 * - `true`（默认）：`mp-weixin` 走 preload 信标；无 API 时回退 `uni.request` GET。
 * - `false`：微信与其它宿主一样走 `uni.request` GET（query 与 H5 一致）。
 *
 * 可在 `createImageChannel({ mpWeixinPreloadReport: false })` 覆盖。
 */
const MP_WEIXIN_USE_PRELOAD_ASSETS_REPORT = true;
/**
 * 微信 `wx.preloadAssets` 单次等待上限（ms）。
 *
 * 冷启动首包常慢于 10s（DNS/TLS/首连），而 image 通道默认 `timeoutMs=10000` 会先于
 * `success` 触发 SDK 超时；Network 里请求可能已是 200。默认放宽到 30s，`uni.request` GET 仍用 10s。
 */
const MP_WEIXIN_PRELOAD_TIMEOUT_MS = 30000;
/**
 * 微信小程序 preload 冷启动首包 flush 延迟（ms）。
 *
 * `onLaunch` 入队 lt=1 后，`queue.shouldFlush()` 会因 `lastFlushAt=0` 立即为 true；
 * 若在 App 尚未完成启动时调用 `wx.preloadAssets`，易出现 30s 无 success。延迟后再 flush，
 * 用于验证「启动时机」是否为根因（方案 C）。设为 `0` 则关闭延迟。
 */
const MP_WEIXIN_PRELOAD_FIRST_FLUSH_DELAY_MS = 2000;
/**
 * App 渠道首包 flush 延迟（ms）。
 *
 * App 自定义渠道来自原生 `plus.runtime.channel`。极少数设备/基座上，统计 install
 * 或首个 lt=1 入队时该值可能还未就绪；给首个自动 flush 一个很短的窗口，发送前
 * `collector.resolveUploadFields` 会再次读取并补齐 `ch`。设为 `0` 可关闭。
 */
const APP_CHANNEL_FIRST_FLUSH_DELAY_MS = 300;
/**
 * 单条事件序列化后允许的最大字节数。
 *
 * 阈值取舍：
 *   - GET 上报（`/WebTrack` / `/WebTrack.gif`）URL 上限约 6KB（见 `docs/image-url-too-long-修复说明.md`）；
 *     扣掉 host / ProjectId / TopicId / Source / Time 等固定 query 后，留给
 *     `Logs=encodeURIComponent(payload.requests)` 约 5.8KB 量级。
 *   - `encodeURIComponent` 对纯 ASCII 膨胀 ~1.05x，对中英混排 ~1.5–2x，对纯中文最坏 3x。
 *   - 取 **4KB 作为单条事件上限**：保证 ASCII 场景（含大段 Error stack）能放进单批；
 *     纯中文极端场景下，由 `chunkEvents` 单条独占一片 + image preflight 在 URL 编码后
 *     再做一次 6144 字节硬截断兜底。
 *   - 业务错误 stack 通常 ~1–3KB，4KB 足够；超 4KB 的单条多半是 base64 图片 / 大段 JSON
 *     这类**应该被业务自身收敛**的场景，直接丢弃并 warn 比静默卡死管道更安全。
 *
 * 超过本阈值的单条事件直接在 `queue.enqueue()` 内丢弃并 warn —— 不入桶、不持久化、
 * 不进入重试队列，避免 81KB 这种"任何 batch 切多细都过不了"的死信卡死管道。
 *
 * 参考排错文档：`docs/image-url-too-long-修复说明.md`。
 */
const SINGLE_EVENT_MAX_BYTES = 4 * 1024;
/**
 * 单批 `requests`（已 `JSON.stringify(events)`）允许的最大字节数。
 *
 * 与 GET URL 长度上限相关：`encodeURIComponent` 保守按 3x 估，
 * 本常量与 `createImageChannel.maxRequestBytes()` 取 min 后由 collector 切片。
 */
const BATCH_REQUESTS_MAX_BYTES = 4 * 1024;
/** 单批最多容纳的事件数；与字节阈值取 min 作为切片边界。 */
const BATCH_MAX_EVENTS = 30;
/**
 * 内存上报桶（主队列）允许容纳的事件总数上限。
 *
 * 设置原因：通道长期不可用时，失败批次会反复 `rollback` 回桶，且每次 `enqueue`/`rollback`
 * 都会 `persistBucket` 落盘。若无上限，内存与 storage 会随离线时长无界增长，最终可能触发
 * 小程序 storage 配额异常甚至 OOM。超过本上限时，`enqueue` 按 FIFO 丢弃**最旧**事件
 * （优先从当前最大的桶丢，尽量保住体量小但关键的 lt=1/lt=3），并 warn。
 *
 * 取值 1000：以单条均值约 0.5–1KB 估算，约占 0.5–1MB，远低于各端 storage 配额；
 * 正常在线（10s flush）场景永远触不到，仅在长时间离线积压时生效。
 */
const QUEUE_MAX_EVENTS = 1000;
/**
 * 单条 retry 队列条目允许的最大重放次数。
 *
 * 设置原因：`recoverRetry` 每次冷启串行重放历史 payload，对永久错误（例如曾经误塞入
 * 队列的超长 payload、协议早期版本的脏数据）只会反复 fail，永远卡在队列前部把后续
 * 健康 payload 也拖死。超过本阈值后由 `markAttempt` 自动 ack 删除（死信清理）。
 */
const RETRY_MAX_ATTEMPTS = 5;
const IMAGE_REPORT_DEFAULTS = {
  host: 'https://tongji-collector.dcloud.net.cn',
  /** 正式环境 */
  projectId: '964f0397-af5d-45bf-99d6-8fb3500d7849',
  topicId: '8563e231-f4cd-4ab0-8870-917e4b04e810'
  // 以下为历史测试环境（已停用，勿删便于回切排查）
  // projectId: '9fad19a2-b7f1-47f5-87ff-8621f545ab61',
  // topicId: '99b55c91-ed80-406e-b205-e9d18aca744d',
};
/**
 * uni-app appid。优先取构建期 `process.env.UNI_APP_ID`；未注入时返回 `''`，
 * 由调用方决定是否上报为 `'default'`。
 */
function getAppId$1() {
  var _a;
  return (_a = "") !== null && _a !== void 0 ? _a : '';
}

/**
 * 2.0 通道：uniCloud importObject 上报。
 *
 * 与私有版协议 1:1：
 *   `uni.__stat_uniCloud_space.importObject('uni-stat-receiver', { customUI: true }).report(payload)`
 *
 * 与私有版差异（修复点）：
 *   - 私有版 `sendRequest` 仅在 1.0 通道有 `_retry` 重试，2.0 通道**完全没有重试**，
 *     云函数偶发抖动会直接丢数据。本实现统一接入 `withRetry`（指数退避）。
 *   - 私有版直接读全局 `uni.__stat_uniCloud_space`，无法测试。本实现支持依赖注入
 *     `uniCloudSpace`（测试） / `getUniCloudSpace()`（运行时）。
 *   - `available()` 在 `space.importObject` 不可用时返回 false，调用方据此决定是否
 *     回退到 1.0 通道（由 selector 决策，本通道自身不做回退）。
 */
/**
 * 解析当前可用的 uniCloud space。
 *
 * 优先级：opts.uniCloudSpace > uni.__stat_uniCloud_space（`uni` 解析见 `infra/uniRuntime`）。
 * 都不可用返回 undefined，由 `available()` / `send()` 自行处理。
 */
/**
 * 校验云对象返回值是否表示业务失败。**只识别 uniCloud 标准失败约定，默认成功**，
 * 以避免把成功返回误判为失败而触发无谓重试：
 *   - `success === false`（显式布尔失败）
 *   - `errCode` 为非 0 的 number（uniCloud 云对象错误码约定；0 / 缺省 = 成功）
 *
 * **刻意不判断通用 `code` 字段**：部分接口用 `code: 200` 表示成功，若按「非 0 即失败」
 * 处理会把成功误判为失败、误入重试队列。未知返回形态一律视为成功（保守）。
 *
 * 命中失败约定时抛错，交由 `withRetry` / collector 走重试链路。
 */
function assertCloudResultOk(res) {
  if (!res || typeof res !== 'object') return;
  const r = res;
  if (r.success === false) {
    throw new Error('cloud receiver reported success=false');
  }
  if (typeof r.errCode === 'number' && r.errCode !== 0) {
    throw new Error('cloud receiver reported errCode=' + String(r.errCode));
  }
}
function resolveSpace(injected) {
  if (injected) return injected;
  const raw = resolveUniRuntime();
  const u = raw != null && typeof raw === 'object' ? raw : undefined;
  return u === null || u === void 0 ? void 0 : u.__stat_uniCloud_space;
}
function createCloudChannel(opts = {}) {
  var _a, _b;
  const receiverName = (_a = opts.receiverName) !== null && _a !== void 0 ? _a : 'uni-stat-receiver';
  const maxRetries = (_b = opts.maxRetries) !== null && _b !== void 0 ? _b : CLOUD_MAX_RETRIES;
  function getReceiver() {
    const space = resolveSpace(opts.uniCloudSpace);
    if (!space || typeof space.importObject !== 'function') return undefined;
    try {
      return space.importObject(receiverName, {
        customUI: true
      });
    } catch (e) {
      logger.warn('[uni统计 2.0] cloud importObject threw', e);
      return undefined;
    }
  }
  function once(payload) {
    const receiver = getReceiver();
    if (!receiver || typeof receiver.report !== 'function') {
      return Promise.reject(new Error('uniCloud space unavailable'));
    }
    return Promise.resolve(receiver.report(payload)).then(res => {
      // 云对象未 throw 但**业务结果显式失败**时，仍按失败处理以触发重试，
      // 避免"resolve 即成功"漏掉服务端拒收。仅识别明确的失败约定，默认视为成功，
      // 防止把未知返回形态误判为失败（保守）。
      assertCloudResultOk(res);
    });
  }
  return {
    name: '2.0',
    available() {
      const space = resolveSpace(opts.uniCloudSpace);
      return !!(space && typeof space.importObject === 'function');
    },
    send(payload) {
      return __awaiter(this, void 0, void 0, function* () {
        try {
          yield withRetry(() => once(payload), {
            times: maxRetries,
            baseDelayMs: RETRY_BASE_DELAY_MS,
            sleep: opts.sleep
          });
        } catch (e) {
          logger.warn('[uni统计 2.0] 统计上报失败（云函数已重试）', e);
          throw e;
        }
      });
    }
  };
}

/**
 * 公有版调试日志：面向业务方的"采集 / 上报"过程日志封装。
 *
 * 与 `logger.debug` 的差异：
 *   - `logger.debug` 是底层 console.log + 闸门；调用点散落，文案随意。
 *   - 本模块提供**统一文案 / 统一格式**的高层包装，覆盖：
 *       1. 采集动作：每个 lt 都有中文动作名 +「采集 → 数据」标记。
 *       2. 上报生命周期：开始 / 成功 / 失败 / 冷启续传。
 *       3. 启动摘要：通道版本、上报间隔、ak 是否就位等。
 *   - 所有 helper 都内嵌 `logger.isDebug()` 判断；非 debug 模式下零开销，
 *     调用方无需再写 `if (logger.isDebug()) ...`。
 *
 * 文案风格参考私有版 `utils/pageInfo.js#log`：直接面向业务调试，**中文**为主，
 * 关键字段（lt / 通道 / 用时 / 错误原因）一目了然。
 *
 * 注意：不在此处吞错；任意 console.log 异常仍会冒泡。运行时调用方需要 `tryRun` 兜底
 * 时自行处理（一般 console.log 不会抛错，故未做包装）。
 */
/**
 * `lt` → 用户友好的中文动作名映射。
 *
 * 与私有版 `pageInfo.js#log` 的 msg_type 对齐。
 * 注：`lt=0` 已废弃（详见 `domain/eventTypes.ts` 头注释），新会话信息直接随 lt=1 上行。
 *
 * 未知 lt 走默认 "未知事件 (lt=X)"，便于排查异常上行。
 */
function getActionLabel(lt) {
  switch (lt) {
    case LT.Launch:
      return '应用启动';
    case LT.Hide:
      return '应用进入后台';
    case LT.Page:
      return '页面切换';
    case LT.Event:
      return '事件触发';
    case LT.Error:
      return '应用错误';
    case LT.Push:
      return 'PUSH 设备标识';
    default:
      return `未知事件 (lt=${String(lt !== null && lt !== void 0 ? lt : '?')})`;
  }
}
/**
 * 计算 bucket（`Record<lt, StatData[]>`）内的事件总数。
 *
 * 仅在 debug 路径需要，单独抽出避免与 queue.size() 模块循环依赖。
 */
function bucketSize(bucket) {
  let n = 0;
  for (const lt of Object.keys(bucket)) {
    const arr = bucket[lt];
    if (Array.isArray(arr)) n += arr.length;
  }
  return n;
}
/**
 * 把 bucket 摘要成 "lt=1×1, lt=11×3, lt=21×2" 形式，方便控制台扫读。
 */
function bucketSummary(bucket) {
  const parts = [];
  for (const lt of Object.keys(bucket)) {
    const arr = bucket[lt];
    if (Array.isArray(arr) && arr.length > 0) {
      parts.push(`lt=${lt}×${arr.length}`);
    }
  }
  return parts.join(', ') || '<空>';
}
/**
 * 单次事件采集日志。
 *
 * 文案示意：
 *   ```text
 *   [uni统计 2.0] === 统计数据采集：应用启动 (lt=1) ===
 *   [uni统计 2.0] {lt: '1', t: 1714123456, ut: 'h5', ...}
 *   [uni统计 2.0] === 采集结束 ===
 *   ```
 */
function logCollect(data) {
  if (!logger.isDebug()) return;
  const lt = data.lt;
  const label = getActionLabel(lt);
  logger.debug(`=== 统计数据采集：${label} (lt=${String(lt !== null && lt !== void 0 ? lt : '?')}) ===`);
  logger.debug(data);
  logger.debug('=== 采集结束 ===');
}
/**
 * 启动 / 配置摘要。`installPublicStat` 装配完毕后调用一次，方便业务方一眼确认接入状态。
 */
function logBoot(info) {
  if (!logger.isDebug()) return;
  const timeoutParts = [];
  if (info.backgroundTimeoutSec != null) {
    timeoutParts.push(`后台超时(新会话): ${info.backgroundTimeoutSec}s`);
  }
  if (info.pageInactiveTimeoutSec != null) {
    timeoutParts.push(`前台无操作超时: ${info.pageInactiveTimeoutSec}s`);
  }
  const timeoutSeg = timeoutParts.length > 0 ? ` | ${timeoutParts.join(' | ')}` : '';
  const lines = ['=== uni统计 2.0 已启用 ===', `上报间隔: ${info.reportIntervalSec}s${timeoutSeg} | 应用APPID: ${info.ak || '<未注入>'}${info.appName ? ` | 应用名: ${info.appName}` : ''}${info.vueMode ? ` | ${info.vueMode}` : ''}`];
  if (info.debugFromManifest) {
    lines.push('调试模式：已从 manifest.uniStatistics.debug 自动开启');
  }
  lines.push('=== 后续将在每次采集 / 上报时输出过程日志 ===');
  logger.debug(lines.join('\n'));
}
/**
 * 即将上报：取出 batch、选定 channel 后调用。
 *
 * 文案示意：
 *   ```text
 *   // 通道=${info.channel}
 *   [uni统计 2.0] === 准备上报： 共 4 条事件 (lt=1×1, lt=11×2, lt=21×1) [_id=p-xxxx] ===
 *   ```
 */
function logReportStart(info) {
  if (!logger.isDebug()) return;
  const total = bucketSize(info.bucket);
  const summary = bucketSummary(info.bucket);
  logger.debug(`=== 准备上报：共 ${total} 条事件 (${summary}) ===`);
}
/**
 * 仅输出失败的"原因 / 重试落盘"细节，不输出 `=== 上报失败 ===` headline。
 *
 * 用于 collector 在切片化发送时**每次失败 send 后立即给出可观察性**：业务方能看到
 * 是哪一批因什么失败、是否进入了重试队列；而最终的"上报失败 / 上报完成（部分失败）"
 * 总览由 `logReportSummary` 统一输出，避免一次失败被打两次 headline。
 */
function logReportFailureReason(info) {
  if (!logger.isDebug()) return;
  logger.debug(`原因: ${describeError(info.error)}`);
  if (info.persistedId) {
    logger.debug(`已暂存重试队列 [retryId=${info.persistedId}]，下次启动自动续传`);
  } else {
    logger.debug('未能写入重试队列：本批数据已丢弃');
  }
}
/**
 * 单批次上报的最终汇总。
 *
 * 设计原则：**对外只暴露"成功 / 失败"两种结果，不暴露"切片"等内部实现细节**。
 *
 * 切片是 collector 为了适配 image 通道 URL 长度上限 / 全局 batch 字节阈值而做的
 * 内部分批发送策略；业务方关心的只是"这一批数据有没有送达、送达多少、丢失多少"。
 * 因此本汇总以**事件数**（而非片数）为统计维度，文案与单批 `logReportSuccess` /
 * `logReportFailure` 完全对齐——业务方感知不到内部走了几次 send。
 *
 * 三种状态文案：
 *   - 全成功：`=== 上报成功： N 条事件已送达, 用时 Tms ===`（与 logReportSuccess 同）
 *   - 全失败：`=== 上报失败： N 条事件未送达, 用时 Tms ===`（与 logReportFailure 同）
 *   - 部分失败：`=== 上报完成：成功 X 条，失败 Y 条，用时 Tms ===`
 *
 * 失败原因 / 重试落盘 id 等细节由 collector 在每次失败 send 后通过 logReportFailure
 * 输出，本汇总不再重复，避免噪音。
 */
function logReportSummary(info) {
  if (!logger.isDebug()) return;
  if (info.failedCount === 0) {
    logger.debug(`=== 上报成功： ${info.okCount} 条事件已送达, 用时 ${info.elapsedMs}ms ===`);
  } else if (info.okCount === 0) {
    logger.debug(`=== 上报失败： ${info.failedCount} 条事件未送达, 用时 ${info.elapsedMs}ms ===`);
  } else {
    logger.debug(`=== 上报完成：成功 ${info.okCount} 条，失败 ${info.failedCount} 条，用时 ${info.elapsedMs}ms ===`);
  }
}
/**
 * 无可用通道：通常是 channelVersion=2 但 uniCloud space 未关联，或 image 配置缺失。
 */
function logNoChannel(info) {
  if (!logger.isDebug()) return;
  logger.debug(`=== 上报跳过：当前无可用通道，已回滚 ${bucketSize(info.bucket)} 条事件入队 ===`);
}
/**
 * 冷启续传：进入 recoverRetry 时调用。
 */
function logRecoverStart(count) {
  if (!logger.isDebug()) return;
  logger.debug(`=== 冷启续传：发现 ${count} 条历史 payload，开始逐条重发 ===`);
}
/**
 * 冷启续传 - 单条结果。
 */
function logRecoverItem(info) {
  if (!logger.isDebug()) return;
  // const idTag = info.payloadId ? ` [_id=${info.payloadId}]` : ''
  if (info.ok) {
    logger.debug(`续传成功 (${info.index}/${info.total})`);
  } else {
    logger.debug(`续传失败 (${info.index}/${info.total})：${describeError(info.error)}`);
  }
}
/**
 * 把 unknown 错误压成可读字符串；保留 message + name，避免业务方在控制台只看到 `[object Object]`。
 */
function describeError(e) {
  if (!e) return '<无错误对象>';
  if (e instanceof Error) {
    return `${e.name}: ${e.message}`;
  }
  if (typeof e === 'string') return e;
  return safeStringify(e) || String(e);
}

/**
 * 上行体瘦身：去掉值为空字符串 `''` 的字段。
 *
 * - **调试日志**：`collector.report` 在瘦身前把完整 `StatData` 交给 `logCollect`，空串字段仍会打印，
 *   便于对照「是真的没采集到」还是「协议口径为空」。
 * - **入队 / 发送**：经本函数后再 `queue.enqueue`，缩短 image GET URL（encode 后的 Logs），
 *   仅减少体积，不改变非空字段语义。
 *
 * 注意：
 *   - 只处理**顶层**键；`StatData` 事件对象为单层 KV。
 *   - 仅剔除 `v === ''`，保留 `0`、`false`、`null`（若上游传入）；当前 builder 不会主动写入 null。
 */
/**
 * 返回浅拷贝：值为 `''` 的键不拷贝到结果对象。
 */
function omitEmptyStringFieldsForUpload(data) {
  const out = {};
  for (const key of Object.keys(data)) {
    const v = data[key];
    if (v === '') continue;
    out[key] = v;
  }
  return out;
}

/**
 * 上报体序列化（重写私有版 `utils/pageInfo.js#handle_data`）。
 *
 * 修复缺陷 #4：私有版用 `for...in` 拿到的 key 永远是字符串，写成 `i === 0` 与 `i === 3`
 * 导致两条边界分支从未命中：`lt=3`（应用进入后台）应排最后用于服务端 session 闭合——被混入中间。
 *
 * 公有版严格契约：
 *   1. 输出顺序固定：`1 → 11 → 21 → 31 → 101 → 3`（可在 `LT_ORDER` 中扩展）。
 *      `lt=0` 已废弃（参考 `domain/eventTypes.ts` 头注释），不再参与排序。
 *   2. 同一 lt 内事件按 push 顺序保留（稳定排序）。
 *   3. 纯函数：不读 storage、不调 console、不依赖 `'3'`。
 *   4. 输入桶为空 → 返回 `'[]'`，调用方应在外层判空。
 *
 * 数据形状（公有版只支持 v2 协议，元素为 JSON 对象；不再走 v1 的 `key=val&...` 字符串）：
 *   `JSON.stringify([{...stat1}, {...stat2}])`
 */
/**
 * 上报顺序权重表。值越小越靠前；未知 lt 落到最末（靠近 lt=3 之前），同时打 warn。
 *
 * 顺序设计依据：
 *   - lt=1：会话日志（含 sid/cst/fvts/lvts/tvc），最先；
 *   - lt=11/21/31/101：按事件类型轻重排开；
 *   - lt=3：应用进入后台，永远最后，用于服务端归一会话停留时长。
 */
const LT_ORDER = {
  '1': 1,
  '11': 2,
  '21': 3,
  '31': 4,
  '101': 5,
  '3': 100
};
const UNKNOWN_LT_WEIGHT = 50;
/**
 * 拉平 + 排序 + 序列化。
 *
 * @param buckets 按 lt 分组的事件桶。
 * @returns 上行 `requests` 字段的 JSON 字符串（`'[{...}]'`）。
 */
function handleData(buckets) {
  return JSON.stringify(flatten(buckets));
}
/**
 * 仅做拉平 + 排序，便于 collector 在不需要 stringify 的场景下做断言或二次处理（如分片）。
 *
 * 排序规则：
 *   - 主键：`LT_ORDER[lt] ?? UNKNOWN_LT_WEIGHT`。
 *   - 次键：原始 push 顺序（依靠 Array.prototype.sort 在 Node 11+ 已稳定）。
 *
 * 修复缺陷 #4 关键断言：`lt='3'` 必落最后；`lt='1'` 必落最前。
 */
function flatten(buckets) {
  const ltKeys = Object.keys(buckets);
  ltKeys.sort((a, b) => weightOf(a) - weightOf(b));
  const out = [];
  for (let i = 0; i < ltKeys.length; i++) {
    const lt = ltKeys[i];
    const list = buckets[lt];
    if (!list || list.length === 0) continue;
    for (let j = 0; j < list.length; j++) out.push(list[j]);
  }
  return out;
}
function weightOf(lt) {
  const w = LT_ORDER[lt];
  return typeof w === 'number' ? w : UNKNOWN_LT_WEIGHT;
}
/**
 * 把已 flatten 的事件数组按"事件数 + 字节数"双阈值贪婪切片。
 *
 * 用于 collector flush 阶段：把一次 flush 出来的整桶切成多个 ReportPayload，
 * 避免单批拼成 GET URL 后超过网关 / CDN / 浏览器 URL 上限（典型 8KB）。
 *
 * 行为：
 *   - **不丢任何事件**：单条事件即便已超 maxBytes 也独占一片（由 queue.enqueue 的
 *     `SINGLE_EVENT_MAX_BYTES` 兜底，正常路径走不到这里）。
 *   - **保持顺序**：贪婪累加，不打乱 flatten 排序结果，保证 lt=1 在最前 / lt=3 在最后的契约。
 *   - **空数组返回 []**：调用方据此跳过本次发送。
 */
function chunkEvents(events, opts = {}) {
  var _a, _b;
  const maxEvents = (_a = opts.maxEvents) !== null && _a !== void 0 ? _a : Infinity;
  const maxBytes = (_b = opts.maxBytes) !== null && _b !== void 0 ? _b : Infinity;
  const out = [];
  if (!Array.isArray(events) || events.length === 0) return out;
  const safeMaxEvents = maxEvents > 0 ? maxEvents : Infinity;
  const safeMaxBytes = maxBytes > 0 ? maxBytes : Infinity;
  let cur = [];
  let curBytes = 2; // 头尾 '[]'
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    let s = '';
    try {
      s = JSON.stringify(e);
    } catch (_c) {
      // 单条不可序列化交给 collector 丢弃（serializer 不打 console，由外层日志代理）
      continue;
    }
    // 加入后会占用：当前是空片 → s.length；否则 +1（逗号分隔）
    const inc = cur.length === 0 ? s.length : s.length + 1;
    const wouldExceed = cur.length >= safeMaxEvents || cur.length > 0 && curBytes + inc > safeMaxBytes;
    if (wouldExceed) {
      out.push(cur);
      cur = [];
      curBytes = 2;
    }
    cur.push(e);
    curBytes += cur.length === 1 ? s.length : s.length + 1;
  }
  if (cur.length > 0) out.push(cur);
  return out;
}
/**
 * 切片版 handleData：返回多个 `requests` 字符串，对应多个 ReportPayload。
 *
 * `chunkEvents` 已保证排序与边界，本函数只做 stringify。
 */
function handleDataChunked(buckets, opts = {}) {
  const events = flatten(buckets);
  if (events.length === 0) return [];
  const chunks = chunkEvents(events, opts);
  const out = [];
  for (let i = 0; i < chunks.length; i++) {
    out.push(JSON.stringify(chunks[i]));
  }
  return out;
}

/**
 * Pipeline 层共享类型。
 *
 * 单独抽出避免 channel / queue / retry 之间循环 import。
 */
/**
 * 永久性通道错误：本次 payload 自身有问题（与网络无关），重试同一份 payload 永远不会过。
 *
 * 典型场景：
 *   - H5 GET URL 超过 `maxUrlLength`，重发同一份必定再次超长；
 *   - TLS host / projectId / topicId 未配置，换网络也救不了；
 *   - 浏览器内既无 `Image` 全局也没有 `uni.request`：环境本身缺失，重试无意义。
 *
 * 设计意图：
 *   - **不进 channel 内部 `withRetry`**：永久错误一抛立刻冒泡到 collector，避免协议层空转 N 次。
 *   - **不进 retry 队列**：collector 的 `report()` 捕获到 permanent 时跳过 `retry.persist`，
 *     避免下次冷启 `recoverRetry` 反复读出 → 反复失败 → 反复落盘的死循环
 *     （这是 `image url too long` 卡死队列的根因）。
 *   - **死信清理**：`recoverRetry` 重放历史 payload 时若再次拿到 permanent 错误，
 *     直接 `retry.ack(_id)` 删除，不再写回。
 *
 * 错误识别：用 `instanceof PermanentChannelError`。为兼容跨 bundle / 跨上下文（少见但
 * 防御性写法），同时设置 `permanent = true` 标志位，`isPermanentChannelError` 双重判定。
 */
class PermanentChannelError extends Error {
  constructor(message) {
    super(message);
    /** 兼容跨 bundle 的标志位；与 `instanceof` 任一为真即视为永久错误。 */
    this.permanent = true;
    this.name = 'PermanentChannelError';
    // 修复 ts/babel 转译后 prototype 链丢失，导致 instanceof 失效
    Object.setPrototypeOf(this, PermanentChannelError.prototype);
  }
}
/**
 * 类型守卫：判定一个 unknown 错误是否为永久性通道错误。
 *
 * 兼容三种来源：
 *   1. `instanceof PermanentChannelError`（同一 bundle）；
 *   2. `err.name === 'PermanentChannelError'`（跨 bundle 但同名）；
 *   3. `err.permanent === true`（任意错误显式标记）。
 */
function isPermanentChannelError(err) {
  if (!err || typeof err !== 'object') return false;
  if (err instanceof PermanentChannelError) return true;
  const e = err;
  if (e.name === 'PermanentChannelError') return true;
  if (e.permanent === true) return true;
  return false;
}

/**
 * Collector：domain 与 pipeline 的编排层。
 *
 * 职责（与 runtime/lifecycleHooks 配合）：
 *   1. `report(input)`：把外部输入（lt + 事件上下文）转成 statData 并入队；
 *      自动填充 session 快照、seq（仅本地状态使用，不再上行）。
 *   2. `flush(force?)`：从 queue 取快照 → serializer → 选 channel → 发送；
 *      成功调用 `visit.commit(now)`；失败 `queue.rollback` + `retry.persist`。
 *   3. `recoverRetry()`：冷启动时由 runtime 触发，把上次未送达的 payload 重试。
 *
 * 设计原则：
 *   - 依赖全部注入；本模块不直接 import 任何 adapter，便于测试与多端切换。
 *   - 不持有业务字段；所有 statData 字段由 `domain/statData.builder` 拼装。
 *   - 错误吞掉 + 日志：collector 层异常**不应**抛回到生命周期回调，避免污染业务页面。
 */
/**
 * 默认 payload id 生成；与 retry.ts 的 genId 风格一致但前缀不同，便于日志区分。
 */
function defaultGenPayloadId(nowMs) {
  return 'p-' + nowMs.toString(36) + '-' + Math.random().toString(36).slice(2, 6);
}
function createCollector(deps) {
  /** 是否已完成进程内首次 flush（含延迟触发的那一次）。 */
  let firstFlushDone = false;
  /** 已安排的延迟 flush 定时器，避免重复 schedule。 */
  let deferredFlushTimer = null;
  /** 取消已安排的延迟首 flush（`flush(true)` 等显式调用前使用）。 */
  function cancelDeferredFlush() {
    if (deferredFlushTimer == null) return;
    clearTimeout(deferredFlushTimer);
    deferredFlushTimer = null;
  }
  /**
   * `report` 达到阈值后的自动 flush 入口；仅此处做冷启动延迟（方案 C）。
   */
  function triggerAutoFlush() {
    var _a;
    const deferMs = Math.max(0, Math.floor((_a = deps.firstFlushDeferMs) !== null && _a !== void 0 ? _a : 0));
    if (!firstFlushDone && deferMs > 0) {
      if (deferredFlushTimer != null) return;
      deferredFlushTimer = setTimeout(() => {
        deferredFlushTimer = null;
        firstFlushDone = true;
        void flushImpl(false).catch(e => logger.warn('[uni统计 2.0] auto-flush failed', e));
      }, deferMs);
      return;
    }
    firstFlushDone = true;
    void flushImpl(false).catch(e => logger.warn('[uni统计 2.0] auto-flush failed', e));
  }
  /**
   * 构造 EventContext 并入队。
   *
   * 不再附加 pid（上一会话 sid）：参数文档无该字段，新会话信息由 lt=1 自身的
   * `sid / cst / fvts / lvts / tvc` 表达。
   */
  function report(input) {
    tryRun(() => {
      const t = typeof input.t === 'number' ? input.t : deps.nowSec();
      const snap = deps.session.getSnapshot();
      let sessionForCtx;
      if (snap) {
        const seq = deps.session.nextSeq();
        sessionForCtx = Object.assign({}, snap, {
          seq
        });
      }
      // 用户主动行为事件（lt=21：自定义事件 / login / pay / share 拦截器）刷新
      // 前台无操作计时器，避免用户持续操作却无翻页时被误判「无操作超时」开新会话（cst=3）。
      // 仅 lt=21 视为「用户触达」；lt=1/3/11/31/101 由会话状态机自身管理。
      if (snap && input.lt === LT.Event && deps.session.touch) {
        deps.session.touch(t);
      }
      const ctx = Object.assign({}, input, {
        t,
        session: sessionForCtx
      });
      const data = deps.builder.build(ctx);
      // 调试日志打印完整对象（含空串）；入队发送侧去掉 '' 键以缩短 image URL
      logCollect(data);
      deps.queue.enqueue(omitEmptyStringFieldsForUpload(data));
      if (deps.queue.shouldFlush()) {
        triggerAutoFlush();
      }
    }, undefined);
  }
  /**
   * flush 前补运行时字段。
   *
   * 典型场景：App 端首个 Launch 事件入队时 `plus.runtime.channel` 暂不可读，
   * 但真正发送前已经就绪；此时应以发送前的原生运行时值覆盖本批事件的 `ch`。
   */
  function applyUploadFields(bucket) {
    const fields = deps.resolveUploadFields ? deps.resolveUploadFields() : {};
    const keys = Object.keys(fields).filter(key => {
      const v = fields[key];
      return v !== '' && v !== undefined && v !== null;
    });
    if (keys.length === 0) return;
    for (const lt of Object.keys(bucket)) {
      const list = bucket[lt];
      if (!Array.isArray(list)) continue;
      for (let i = 0; i < list.length; i++) {
        const item = list[i];
        for (let j = 0; j < keys.length; j++) {
          const key = keys[j];
          item[key] = fields[key];
        }
      }
    }
  }
  function applyUploadFieldsToRequests(requests) {
    const fields = deps.resolveUploadFields ? deps.resolveUploadFields() : {};
    const keys = Object.keys(fields).filter(key => {
      const v = fields[key];
      return v !== '' && v !== undefined && v !== null;
    });
    if (keys.length === 0) return requests;
    try {
      const events = JSON.parse(requests);
      if (!Array.isArray(events)) return requests;
      for (let i = 0; i < events.length; i++) {
        const item = events[i];
        if (!item || typeof item !== 'object') continue;
        for (let j = 0; j < keys.length; j++) {
          const key = keys[j];
          item[key] = fields[key];
        }
      }
      return JSON.stringify(events);
    } catch (_a) {
      return requests;
    }
  }
  function applyUploadFieldsToPayload(payload) {
    const requests = applyUploadFieldsToRequests(payload.requests);
    if (requests === payload.requests) return payload;
    return Object.assign({}, payload, {
      requests
    });
  }
  /**
   * 真正发送：取快照、序列化、挑通道、按双阈值切片、串行发送，根据结果 commit/persist。
   *
   * 切片策略（修复 image url too long 死循环）：
   *   - 用 `handleDataChunked(snapshot, { maxEvents, maxBytes })` 把整桶切成 N 份；
   *   - 单片失败：永久错（`PermanentChannelError`）→ 直接丢弃，不 persist、不影响其他片；
   *     非永久错 → 调用 `retry.persist`，下次冷启 `recoverRetry` 重放该片。
   *   - **任意片失败** → 不 commit visit；**全部片成功** → commit 一次。
   *     切片场景下 `lt=1` 必定落在第一片（serializer 已按 `LT_ORDER` 排序），
   *     若需要更精细的"首批成功就 commit"，下一步迭代再做。
   *   - 通道不可用：依旧整桶 rollback 回 queue（与切片前行为一致）。
   *
   * @param force 强制 flush（忽略节流阈值）。
   */
  function flushImpl() {
    return __awaiter(this, arguments, void 0, function* (force = false) {
      var _a, _b, _c, _d, _e;
      if (!deps.queue.shouldFlush(force)) return;
      // 无网：不摘队列，等网络恢复后再 flush（公有版门闸）
      if (deps.isNetworkOffline) {
        let offline = false;
        try {
          offline = yield deps.isNetworkOffline();
        } catch (_f) {
          offline = false;
        }
        if (offline) {
          logger.warn('[uni统计 2.0] 当前无网络，延后 flush');
          return;
        }
      }
      const snapshot = deps.queue.flush();
      if (!snapshot) return;
      applyUploadFields(snapshot);
      const channel = deps.selectChannel();
      if (!channel) {
        logger.warn('[uni统计 2.0] 无可用上报线路，本批已回滚队列');
        logNoChannel({
          bucket: snapshot
        });
        deps.queue.rollback(snapshot);
        return;
      }
      // 切片阈值 = min(全局配置, 通道物理上限)
      //   - 全局：BATCH_REQUESTS_MAX_BYTES（业务可调）
      //   - 通道：image GET URL 经 encodeURIComponent 膨胀，原文不能按 URL 上限直接用
      //     → 由 image 通道 maxRequestBytes() 反推（见 image.ts）
      // 这样 100 条事件在 image 通道下不会再切出"原文 4KB / encoded 7.5KB"超长片。
      const globalMaxBytes = (_b = (_a = deps.batchLimits) === null || _a === void 0 ? void 0 : _a.maxBytes) !== null && _b !== void 0 ? _b : BATCH_REQUESTS_MAX_BYTES;
      const channelMaxBytes = typeof channel.maxRequestBytes === 'function' ? channel.maxRequestBytes() : Number.POSITIVE_INFINITY;
      const limits = {
        maxEvents: (_d = (_c = deps.batchLimits) === null || _c === void 0 ? void 0 : _c.maxEvents) !== null && _d !== void 0 ? _d : BATCH_MAX_EVENTS,
        maxBytes: Math.min(globalMaxBytes, channelMaxBytes)
      };
      const chunks = handleDataChunked(snapshot, limits);
      if (chunks.length === 0) {
        // 快照已被 flush() 从队列摘除，但切片结果为空（极端：桶内全是空数组 key，
        // 或所有事件 JSON.stringify 失败）。若直接 return 会**静默丢数**，故回滚回队列等待下次。
        logger.warn('[uni统计 2.0] flush 切片结果为空，已回滚队列', snapshot);
        deps.queue.rollback(snapshot);
        return;
      }
      const startMs = deps.nowMs();
      let totalCount = 0;
      for (const lt of Object.keys(snapshot)) {
        const arr = snapshot[lt];
        if (Array.isArray(arr)) totalCount += arr.length;
      }
      logReportStart({
        channel: channel.name,
        bucket: snapshot
      });
      // 切片是适配 image URL 长度限制 / 全局 batch 字节阈值的内部分批策略，业务方
      // 不应感知。统计维度统一为**事件数**：成功片累计 okEvents、失败片累计 failedEvents
      // + per-slice logReportFailure（保留原因）；末尾由 logReportSummary 输出统一汇总。
      // visit 字段（fvts/lvts/tvc）只随 lt=1 上行，而 serializer 已按 LT_ORDER 把 lt=1
      // 排到最前 → 必定落在第一片（chunks[0]）。因此「访问是否被服务端接收」只取决于
      // 第一片是否成功，与后续 lt=21/31 等切片成败无关。
      //   - 桶内有 lt=1：以 chunks[0] 成功与否决定 commit / rollback（部分成功也可 commit，
      //     避免后续片失败把已被接收的访问回滚，造成本地与服务端口径偏差）。
      //   - 桶内无 lt=1：visit pending 本就为空，commit/rollback 均为 noop；沿用「全部成功才 commit」
      //     的旧语义，保持既有行为与测试稳定。
      const hasLaunch = Array.isArray(snapshot['1']) && snapshot['1'].length > 0;
      let okEvents = 0;
      let failedEvents = 0;
      let allOk = true;
      let firstChunkOk = true;
      for (let i = 0; i < chunks.length; i++) {
        const requests = chunks[i];
        const payload = {
          usv: deps.config.usv,
          t: deps.nowSec(),
          requests,
          _id: ((_e = deps.genPayloadId) !== null && _e !== void 0 ? _e : () => defaultGenPayloadId(deps.nowMs()))()
        };
        const sliceEvents = countEvents(requests);
        try {
          yield channel.send(payload);
          okEvents += sliceEvents;
        } catch (e) {
          allOk = false;
          if (i === 0) firstChunkOk = false;
          failedEvents += sliceEvents;
          if (isPermanentChannelError(e)) {
            // 永久错：丢弃本片，不 persist、不污染下次冷启
            logger.warn('[uni统计 2.0] 统计上报失败（本批已丢弃，不可重试）', e, 'sliceBytes=' + requests.length);
            logReportFailureReason({
              error: e,
              persistedId: undefined
            });
            continue;
          }
          logger.warn('[uni统计 2.0] 统计上报失败（已暂存，下次启动自动重试）', e);
          const id = deps.retry.persist(payload);
          if (!id) {
            logger.warn('[uni统计 2.0] 统计暂存重试失败（无 retryId），本批已丢弃');
          }
          logReportFailureReason({
            error: e,
            persistedId: id
          });
        }
      }
      const visitAccepted = hasLaunch ? firstChunkOk : allOk;
      if (visitAccepted) {
        tryRun(() => deps.visit.commitVisitOnAck(deps.nowSec()), undefined);
      } else {
        tryRun(() => deps.visit.rollbackPendingVisit(), undefined);
      }
      // 单批最终汇总：业务方视角只看到"成功/失败/部分失败"，不暴露切片实现。
      // 文案见 debugLog.ts#logReportSummary。
      logReportSummary({
        channel: channel.name,
        okCount: okEvents,
        failedCount: failedEvents,
        elapsedMs: deps.nowMs() - startMs
      });
    });
  }
  /** 估算一片的事件数（容错：解析失败按 0 计）。仅供日志展示。 */
  function countEvents(requests) {
    try {
      const arr = JSON.parse(requests);
      return Array.isArray(arr) ? arr.length : 0;
    } catch (_a) {
      return 0;
    }
  }
  /**
   * 把上次进程留在 storage 中的 retry 队列依次重放。
   *
   * 串行执行，失败的条目保留在队列里（不动 _id），调用方会在下次冷启再次重放。
   */
  function recoverRetry() {
    return __awaiter(this, void 0, void 0, function* () {
      if (deps.isNetworkOffline) {
        let offline = false;
        try {
          offline = yield deps.isNetworkOffline();
        } catch (_a) {
          offline = false;
        }
        if (offline) {
          logger.warn('[uni统计 2.0] 当前无网络，延后续传重试');
          return;
        }
      }
      const items = deps.retry.loadAll();
      if (items.length === 0) return;
      const channel = deps.selectChannel();
      if (!channel) {
        logger.warn('[uni统计 2.0] 续传重试跳过：当前无可用上报线路');
        return;
      }
      logRecoverStart(items.length);
      let i = 0;
      for (const payload of items) {
        i++;
        const uploadPayload = applyUploadFieldsToPayload(payload);
        try {
          yield channel.send(uploadPayload);
          if (payload._id) deps.retry.ack(payload._id);
          logRecoverItem({
            index: i,
            total: items.length,
            payloadId: payload._id,
            ok: true
          });
        } catch (e) {
          // 永久错：直接 ack 删除死信，避免下次冷启再次重放再次失败
          if (isPermanentChannelError(e)) {
            if (payload._id) deps.retry.ack(payload._id);
            logger.warn('[uni统计 2.0] 续传重试失败（不可重试，已从队列移除）', e, 'id=' + payload._id);
            logRecoverItem({
              index: i,
              total: items.length,
              payloadId: payload._id,
              ok: false,
              error: e
            });
            continue;
          }
          if (payload._id && deps.retry.markAttempt) {
            // markAttempt 内部超过 maxAttempts 会自动 ack 兜底（参见 retry.ts）
            deps.retry.markAttempt(payload._id);
          }
          logger.warn('[uni统计 2.0] 续传重试失败（保留队列，下次启动再试）', e);
          logRecoverItem({
            index: i,
            total: items.length,
            payloadId: payload._id,
            ok: false,
            error: e
          });
        }
      }
    });
  }
  /**
   * 对外 flush：显式调用（含 `flush(true)`）立即发送，并取消尚未触发的延迟首 flush。
   */
  function flush() {
    return __awaiter(this, arguments, void 0, function* (force = false) {
      cancelDeferredFlush();
      firstFlushDone = true;
      return flushImpl(force);
    });
  }
  /** 取消延迟首 flush 定时器，防止 collector 被弃后仍触发幽灵 flush。 */
  function destroy() {
    cancelDeferredFlush();
    // 置为「已完成首 flush」，即便有残留闭包再次调用 triggerAutoFlush 也不会重排定时器。
    firstFlushDone = true;
  }
  return {
    report,
    flush,
    recoverRetry,
    destroy
  };
}

/**
 * 1.0 通道：HTTP POST 上报。
 *
 * 兼容私有版同协议（`uni.request(POST STAT_URL)`），并修复其历史缺陷：
 *   - #1 `_retry` 未初始化导致 NaN：本实现以 `withRetry({times})` 显式控制。
 *   - #16 H5 在 nvue/部分小程序无 `Image`：本实现以 `uni.request` 为主；TLS 公有版 image
 *     通道的 H5 路径亦优先 `uni.request` GET 以读取 HTTP 状态，避免误报成功。
 *
 * 接口契约：
 *   - `available()`：在任何 uni 平台都返回 true（HTTP 是兜底通道）。
 *   - `send(payload)`：成功 resolve；3 次重试全失败抛错（供 retry.persist 落盘）。
 *   - 不缓存任何状态；每次 `send` 是无状态的。
 */
function getUni$6() {
  const u = resolveUniRuntime();
  return u != null && typeof u === 'object' ? u : undefined;
}
/**
 * 把 payload 拼成 query string，供 H5 image fallback 使用。
 *
 * 私有版用 `get_sgin(get_encodeURIComponent_options(data))` 还会算签名；公有版去掉签名
 * （服务端历史阶段仅 1.0 走签名，2.0 已弃用），保持 query 简单可读：
 *   `?usv=3&t=...&requests=URL_ENCODED_JSON`
 */
function toQuery(payload) {
  const out = [];
  out.push('usv=' + encodeURIComponent(String(payload.usv)));
  out.push('t=' + encodeURIComponent(String(payload.t)));
  out.push('requests=' + encodeURIComponent(payload.requests));
  return out.join('&');
}
/**
 * H5 image 通道。仅在 `Image` 全局存在时调用；否则返回 false 让外层退回 `uni.request`。
 *
 * 不等待 onload/onerror（image 兜底语义即"发出去就算"），同步 resolve。
 * 若 `new Image()` 本身抛错也吞掉，转给 fallback。
 */
function tryImageRequest(payload, h5Url = STAT_H5_URL) {
  const ImageCtor = getGlobalObject().Image;
  if (typeof ImageCtor !== 'function') return false;
  return tryRun(() => {
    const img = new ImageCtor();
    img.src = h5Url + '?' + toQuery(payload);
    return true;
  }, false);
}
function createHttpChannel(opts = {}) {
  var _a, _b, _c, _d, _e;
  const url = (_a = opts.url) !== null && _a !== void 0 ? _a : STAT_URL;
  const h5Url = (_b = opts.h5Url) !== null && _b !== void 0 ? _b : STAT_H5_URL;
  const ut = (_c = opts.ut) !== null && _c !== void 0 ? _c : '';
  const timeoutMs = (_d = opts.timeoutMs) !== null && _d !== void 0 ? _d : 10000;
  const maxRetries = (_e = opts.maxRetries) !== null && _e !== void 0 ? _e : HTTP_MAX_RETRIES;
  function once(payload) {
    if (ut === 'h5' && opts.preferImageOnH5 !== false) {
      if (tryImageRequest(payload, h5Url)) return Promise.resolve();
    }
    const u = getUni$6();
    if (!u || typeof u.request !== 'function') {
      return Promise.reject(new Error('uni.request unavailable'));
    }
    return new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(new Error('http timeout'));
      }, timeoutMs);
      u.request({
        url,
        method: 'POST',
        data: payload,
        timeout: timeoutMs,
        success: res => {
          var _a;
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          const code = (_a = res === null || res === void 0 ? void 0 : res.statusCode) !== null && _a !== void 0 ? _a : 0;
          if (code >= 200 && code < 300) resolve();else reject(new Error('http status ' + code));
        },
        fail: e => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          reject(e instanceof Error ? e : new Error(String(e)));
        }
      });
    });
  }
  return {
    name: '1.0',
    available() {
      const u = getUni$6();
      return !!(u && typeof u.request === 'function');
    },
    send(payload) {
      return __awaiter(this, void 0, void 0, function* () {
        try {
          yield withRetry(() => once(payload), {
            times: maxRetries,
            baseDelayMs: RETRY_BASE_DELAY_MS,
            sleep: opts.sleep
          });
        } catch (e) {
          logger.warn('[uni统计 2.0] 统计上报失败（HTTP 已重试）', e);
          throw e;
        }
      });
    }
  };
}

/**
 * 公有版默认通道：火山 TLS Web 采集。
 *
 * **官方 GET**（`uni.request`，App / 小程序 / H5·微信回退）：
 *   `GET ${host}/WebTrack?ProjectId&TopicId&Logs&Source&Time&…`
 *   与文档 `curl GET 'http://${host}/WebTrack?ProjectId=…&TopicId=…&key=val'` 一致。
 *
 * **信标 GET**（H5 `fetch`/`Image`、微信 `preloadAssets`）：
 *   `GET ${host}/WebTrack.gif?…`（query 与 `/WebTrack` 相同，路径为 1×1 像素接口）。
 *   H5 优先 `fetch(keepalive)` 读真实状态码；采集端返回 `200 application/json` 且带
 *   `Access-Control-Allow-Origin: *`，故可跨域判定成败（旧 `<img>` 信标无法读状态，降级兜底）。
 *
 * **已废弃 POST**：`POST ${host}/WebTracks?ProjectId&TopicId` + JSON body。
 */
/** 官方 GET 接口路径（`uni.request`）。 */
const WEBTRACK_API_PATH = '/WebTrack';
/** 浏览器 / 微信 preload 信标路径。 */
const WEBTRACK_BEACON_PATH = '/WebTrack.gif';
/**
 * 解析运行时 `uni.request` API。
 */
function getUni$5() {
  const u = resolveUniRuntime();
  return u != null && typeof u === 'object' ? u : undefined;
}
/** URL 中除 `Logs` 外的固定 query 字节预算（保守值）。 */
const REPORT_URL_BASE_OVERHEAD = 256;
/** `encodeURIComponent` 字节膨胀比上界（用于 collector 切片反推）。 */
const REPORT_ENCODE_RATIO = 3.0;
/**
 * 拼装统计上报 query（ProjectId / TopicId / Logs / Source / Time）。
 *
 * @param payload 上报 payload；`requests` 为 `JSON.stringify(events)`。
 * @param opts    host / projectId / topicId / path / nowMs。
 */
function buildStatReportUrl(payload, opts) {
  var _a;
  const t = ((_a = opts.nowMs) !== null && _a !== void 0 ? _a : () => Date.now())();
  const logs = encodeURIComponent(payload.requests);
  const host = opts.host.replace(/\/+$/, '');
  return host + opts.path + '?ProjectId=' + encodeURIComponent(opts.projectId) + '&TopicId=' + encodeURIComponent(opts.topicId) + '&Logs=' + logs + '&Source=webImg' + '&Time=' + t;
}
/**
 * 将 `uni.request` 返回的 `data` 压成短串，便于在 Error.message 中展示。
 *
 * @param data   success 回调中的 `res.data`
 * @param maxLen 最大字符数
 */
function summarizeHttpErrorBody(data, maxLen = 320) {
  if (data == null) return '';
  if (typeof data === 'string') {
    return data.length <= maxLen ? data : data.slice(0, maxLen) + '…';
  }
  try {
    const s = JSON.stringify(data);
    return s.length <= maxLen ? s : s.slice(0, maxLen) + '…';
  } catch (_a) {
    return String(data).slice(0, maxLen);
  }
}
/**
 * H5 最后兜底：`Image` 触发 `/WebTrack.gif`；`onload` / `onerror` 均 resolve，仅超时 reject。
 *
 * ## 为什么 onload/onerror 都判成功（且为何不再作为首选）
 *
 * 采集端 `/WebTrack.gif` 成功时返回 `200 application/json`（空体），**并非合法图片**，
 * 浏览器无法把响应解码为图片 → 即便上报成功也会触发 `onerror`。因此 `<img>` 信标
 * 物理上**无法区分**「成功（JSON 响应）」与「真实失败（DNS/网络/拦截/4xx/5xx）」，
 * 只能一律 resolve，否则每次成功都会被误判失败并重试。
 *
 * 这是一个有损降级：仅在**既无 `fetch` 又无 `uni.request`** 的极旧 H5 环境才会走到。
 * 正常环境优先 `fetchBeaconAwait`（读真实状态码），次选 `uni.request` GET（读 statusCode）。
 *
 * @param url 完整信标 URL
 * @param ms  超时毫秒
 */
function imageBeaconAwait(url, ms) {
  const ImageCtor = getGlobalObject().Image;
  if (typeof ImageCtor !== 'function') {
    return Promise.reject(new PermanentChannelError('当前环境无法完成统计上报'));
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new Error('统计上报超时'));
    }, ms);
    const img = new ImageCtor();
    img.onload = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve();
    };
    img.onerror = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve();
    };
    img.src = url;
  });
}
/**
 * H5 首选：`fetch` 触发 `/WebTrack.gif`，读取真实 HTTP 状态码判定成败。
 *
 * ## 为什么用 fetch 替代 `<img>` 信标
 *
 * 采集端 `/WebTrack.gif` 成功返回 `200 application/json`（空体），且响应头带
 * `Access-Control-Allow-Origin: *`，因此 H5 可**跨域读取** `res.ok`：
 *   - 2xx → 送达成功，resolve；
 *   - 其余状态码 / 网络异常（DNS、断网、CSP/拦截、4xx/5xx）→ reject，交由
 *     `withRetry` 重试，最终失败落盘 retry，**不再被静默 ACK**。
 *
 * `keepalive: true` 保证页面卸载（如 `lt=3` hide 期）请求仍能发出，等价于
 * `<img>` 信标的「卸载存活」能力，因此可安全取代旧的 onerror=成功 兜底。
 *
 * `credentials: 'omit'`：仅需读状态码，无需携带 cookie；同时规避
 * `Allow-Origin:*` 与 `include` 凭证模式在浏览器侧的冲突。
 *
 * @param url 完整信标 URL
 * @param ms  超时毫秒
 */
function fetchBeaconAwait(url, ms) {
  const g = getGlobalObject();
  const fetchFn = g.fetch;
  if (typeof fetchFn !== 'function') {
    return Promise.reject(new Error('fetch unavailable'));
  }
  const controller = typeof g.AbortController === 'function' ? new g.AbortController() : undefined;
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      if (controller) tryRun(() => controller.abort(), undefined);
      reject(new Error('统计上报超时'));
    }, ms);
    fetchFn(url, {
      method: 'GET',
      keepalive: true,
      credentials: 'omit',
      signal: controller ? controller.signal : undefined
    }).then(res => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (res && res.ok) {
        resolve();
        return;
      }
      reject(new Error('统计上报 HTTP ' + (res ? res.status : 0)));
    }, e => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(e instanceof Error ? e : new Error(String(e)));
    });
  });
}
/**
 * 读取微信 `wx.preloadAssets`（仅 mp-weixin 信标使用）。
 */
function getWxPreloadAssets() {
  const wx = getGlobalObject().wx;
  return typeof (wx === null || wx === void 0 ? void 0 : wx.preloadAssets) === 'function' ? wx.preloadAssets : undefined;
}
/**
 * 规范化 `wx.preloadAssets` 的 fail 入参。
 */
function formatWxPreloadFail(err) {
  if (err instanceof Error) return err;
  if (err != null && typeof err === 'object' && 'errMsg' in err) {
    const msg = err.errMsg;
    if (typeof msg === 'string' && msg.length > 0) return new Error(msg);
  }
  if (err == null) return new Error('preloadAssets fail (empty err)');
  return new Error(String(err));
}
/**
 * 微信：`wx.preloadAssets` 拉取 `/WebTrack.gif`；仅 `success` 视为送达。
 *
 * @param url     完整信标 URL
 * @param ms      超时毫秒
 * @param preload 已校验存在的 `wx.preloadAssets`
 */
function mpWeixinPreloadAssetsBeaconAwait(url, ms, preload) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new Error('统计上报超时(preloadAssets)'));
    }, ms);
    try {
      preload({
        data: [{
          type: 'image',
          src: url
        }],
        success: () => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          resolve();
        },
        fail: err => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          reject(formatWxPreloadFail(err));
        }
      });
    } catch (e) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(e instanceof Error ? e : new Error(String(e)));
    }
  });
}
/**
 * 微信小程序是否启用 preload 信标（开关开且宿主为 mp-weixin）。
 */
function isMpWeixinPreloadEnabled(opts) {
  var _a, _b;
  const enabled = (_a = opts.mpWeixinPreloadReport) !== null && _a !== void 0 ? _a : MP_WEIXIN_USE_PRELOAD_ASSETS_REPORT;
  if (!enabled) return false;
  const raw = (_b = opts.rawPlatform) !== null && _b !== void 0 ? _b : getRawPlatform();
  return raw === 'mp-weixin';
}
function createImageChannel(opts = {}) {
  var _a, _b, _c, _d, _e, _f, _g;
  const host = (_a = opts.host) !== null && _a !== void 0 ? _a : IMAGE_REPORT_DEFAULTS.host;
  const projectId = (_b = opts.projectId) !== null && _b !== void 0 ? _b : IMAGE_REPORT_DEFAULTS.projectId;
  const topicId = (_c = opts.topicId) !== null && _c !== void 0 ? _c : IMAGE_REPORT_DEFAULTS.topicId;
  const timeoutMs = (_d = opts.timeoutMs) !== null && _d !== void 0 ? _d : 10000;
  const maxRetries = (_e = opts.maxRetries) !== null && _e !== void 0 ? _e : IMAGE_MAX_RETRIES;
  const maxUrlLength = (_f = opts.maxUrlLength) !== null && _f !== void 0 ? _f : 6 * 1024;
  const preferBeacon = opts.preferImageBeacon !== false;
  const nowMs = opts.nowMs;
  const ut = (_g = opts.ut) !== null && _g !== void 0 ? _g : '';
  const isH5 = ut === 'h5';
  const mpWeixinPreload = isMpWeixinPreloadEnabled(opts);
  function configured() {
    return !!(host && projectId && topicId);
  }
  const reportOpts = {
    host,
    projectId,
    topicId,
    nowMs
  };
  /**
   * 校验配置并拼装 URL；超长抛 `PermanentChannelError`。
   *
   * @param payload 批次数据
   * @param path    `WEBTRACK_API_PATH` 或 `WEBTRACK_BEACON_PATH`
   */
  function preflightUrl(payload, path) {
    if (!configured()) {
      throw new PermanentChannelError('统计上报未配置：请设置 TLS host、projectId、topicId');
    }
    const url = buildStatReportUrl(payload, {
      host: reportOpts.host,
      projectId: reportOpts.projectId,
      topicId: reportOpts.topicId,
      nowMs: reportOpts.nowMs,
      path
    });
    if (url.length > maxUrlLength) {
      throw new PermanentChannelError('统计上报 URL 过长: ' + url.length + ' > ' + maxUrlLength);
    }
    return url;
  }
  /**
   * `uni.request` GET `/WebTrack`（官方普通 GET，非信标）。
   */
  function webTrackGetViaRequest(url) {
    const u = getUni$5();
    if (!u || typeof u.request !== 'function') {
      return Promise.reject(new PermanentChannelError('当前环境无法完成统计上报'));
    }
    return new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(new Error('统计上报超时'));
      }, timeoutMs);
      u.request({
        url,
        method: 'GET',
        timeout: timeoutMs,
        success: res => {
          var _a;
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          const code = (_a = res === null || res === void 0 ? void 0 : res.statusCode) !== null && _a !== void 0 ? _a : 0;
          if (code >= 200 && code < 300) {
            resolve();
            return;
          }
          const hint = summarizeHttpErrorBody(res === null || res === void 0 ? void 0 : res.data);
          reject(new Error(hint ? `统计上报 HTTP ${code}: ${hint}` : `统计上报 HTTP ${code}`));
        },
        fail: e => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          reject(e instanceof Error ? e : new Error(String(e)));
        }
      });
    });
  }
  /**
   * H5 发送方式选择（均能判定真实成败，失败进 retry）：
   *   1. 首选 `fetch` 信标 `/WebTrack.gif`：跨域读 `res.ok`，`keepalive` 保证卸载期送达；
   *   2. 次选 `uni.request` GET `/WebTrack`：读 `statusCode`；
   *   3. 末选 `Image` 信标 `/WebTrack.gif`：仅极旧环境（无 fetch、无 uni.request）兜底，
   *      无法读状态，发出即视为送达（有损）。
   *
   * `preferImageBeacon: false` 时跳过信标，强制走 `uni.request` GET（测试/特殊场景）。
   */
  function onceH5(payload) {
    const g = getGlobalObject();
    const u = getUni$5();
    const hasRequest = !!(u && typeof u.request === 'function');
    if (preferBeacon && typeof g.fetch === 'function') {
      return fetchBeaconAwait(preflightUrl(payload, WEBTRACK_BEACON_PATH), timeoutMs);
    }
    if (hasRequest) {
      return webTrackGetViaRequest(preflightUrl(payload, WEBTRACK_API_PATH));
    }
    if (preferBeacon && typeof g.Image === 'function') {
      return imageBeaconAwait(preflightUrl(payload, WEBTRACK_BEACON_PATH), timeoutMs);
    }
    return Promise.reject(new PermanentChannelError('当前环境无法完成统计上报'));
  }
  /**
   * 微信：优先 `/WebTrack.gif` preload；否则 `uni.request` GET `/WebTrack`。
   */
  function onceMpWeixin(payload) {
    const preloadFn = getWxPreloadAssets();
    if (preloadFn) {
      return mpWeixinPreloadAssetsBeaconAwait(preflightUrl(payload, WEBTRACK_BEACON_PATH), MP_WEIXIN_PRELOAD_TIMEOUT_MS, preloadFn);
    }
    logger.warn('[uni统计 2.0] wx.preloadAssets 不可用，回退 uni.request GET /WebTrack');
    return webTrackGetViaRequest(preflightUrl(payload, WEBTRACK_API_PATH));
  }
  /**
   * 按宿主选择发送方式。
   */
  function dispatchReport(payload) {
    if (isH5) return onceH5(payload);
    if (mpWeixinPreload) return onceMpWeixin(payload);
    return webTrackGetViaRequest(preflightUrl(payload, WEBTRACK_API_PATH));
  }
  return {
    name: 'image',
    available() {
      return configured();
    },
    maxRequestBytes() {
      const raw = (maxUrlLength - REPORT_URL_BASE_OVERHEAD) / REPORT_ENCODE_RATIO;
      return Math.max(512, Math.floor(raw));
    },
    send(payload) {
      return __awaiter(this, void 0, void 0, function* () {
        try {
          yield withRetry(() => dispatchReport(payload), {
            times: maxRetries,
            baseDelayMs: RETRY_BASE_DELAY_MS,
            sleep: opts.sleep
          });
        } catch (e) {
          if (isPermanentChannelError(e)) {
            logger.warn('[uni统计 2.0] 统计上报失败（不可重试）', e);
          } else {
            logger.warn('[uni统计 2.0] 统计上报失败（已重试）', e);
          }
          throw e;
        }
      });
    }
  };
}

/**
 * 上行字段集中拼装。
 *
 * 私有版痛点：`sendXxxRequest` 系列函数中各自 `Object.assign(getStatData(), ...)`，
 * 字段散落、重复、字段名硬编码、新增字段需改多处。公有版集中到本模块，按事件类型
 * 决定字段子集。
 *
 * 设计要点：
 *   - 通过依赖注入（`createStatDataBuilder(deps)`）解耦 adapter / domain，便于单测。
 *   - 字段全部经过 `s/n` 兜底转换，禁止 undefined 出现在最终上行体（统一用空串 / 0）。
 *   - 事件类型驱动：仅 lt=1 携带 fvts/lvts/tvc / sc 等启动字段；其他事件不携带。
 *   - 仅做拼装，不做副作用：不写 storage、不调 ensureSession（这些由 collector 编排）。
 *   - 严守 ES2015 baseline：禁用 `ObjectExpression > SpreadElement`，统一用 `Object.assign`。
 *
 * 与 `docs/uni统计上报参数.md` 对齐说明：
 *   - 设备 ID 使用文档字段名 `did`（内部 SessionSnapshot/Adapter 仍以 uuid 命名，仅出口处映射）。
 *   - `on`：优先 **`romName`**（厂商 ROM，如 HyperOS）及 **`romVersion`**，否则 **`osName`**。
 *   - 会话创建类型使用文档字段名 `cst`（内部 storage 仍以 sct 命名，仅出口处映射）。
 *   - 不再上行 `sst / seq / pid`（及历史 `odid`）：
 *       * sst/seq 仅本地用于会话状态机，不参与服务端入库；
 *       * pid（上一会话 sid）当前后端无入库口径。
 *     这些字段在 SessionSnapshot 里仍保留，确保会话过期判断、调试日志可继续使用。
 */
/** 字段值兜底：把 undefined / null / NaN 转为类型默认值，避免污染上行 JSON。 */
function s(v, def = '') {
  if (typeof v === 'string') return v;
  if (typeof v === 'number' && Number.isFinite(v)) return String(v);
  return def;
}
function n(v, def = 0) {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.length > 0) {
    const x = Number(v);
    if (Number.isFinite(x)) return x;
  }
  return def;
}
/**
 * 创建 statData 构建器。
 *
 * 调用方典型用法：
 * ```ts
 * const builder = createStatDataBuilder(deps)
 * const data = builder.build({ lt: LT.Page, t: nowSec(), route: '...' })
 * ```
 */
function createStatDataBuilder(deps) {
  /**
   * 复用频率高的"基础字段"——每条事件都带。
   *
   * 字段映射（参考 `docs/uni统计上报参数.md`）：
   *   - `did` ← 内部 `device.uuid`（出口字段重命名为文档口径）
   *   - `p` ← `platform.p` 或 `system.osP`（仅操作系统 slug：`ios` / `android` …）
   *   - `on` ← `system.on`（ROM 展示名优先，否则 `osName`）
   *   - `mpsdk` ← `system.sdkVersion`
   *   - `mpv` ← `system.mpvHostVersion`（宿主客户端版本，与私有版 `sys.version` 同源）
   *   - `domain` ← `web.domain`（H5 含协议域名，如 `https://www.example.com`，非 H5 为空串）
   *   - `pr/ww/wh/sw/sh/lang` 来自 `locale`（实时取，修复缺陷 #18）
   *   - `lat/lng` 当前 LocationResult 仅含字符串经纬度，cn/pn/ct 留空待 adapter 扩展
   *
   * 不再装配 `odid`（老 App 兼容字段已移除）。
   */
  function baseFields() {
    var _a, _b, _c;
    const {
      config,
      platform,
      system,
      locale,
      device,
      net,
      location,
      pkg,
      legacy,
      web
    } = deps;
    return {
      ak: s(config.ak),
      usv: s(config.usv),
      v: s((_a = config.v) !== null && _a !== void 0 ? _a : system.appVersion),
      ch: s(config.ch),
      ut: s(platform.ut),
      p: s((_b = platform.p) !== null && _b !== void 0 ? _b : system.osP),
      on: s(system.on),
      did: s(device.uuid),
      brand: s(system.brand),
      md: s(system.md),
      sv: s(system.sv),
      mpsdk: s(system.sdkVersion),
      mpv: s(system.mpvHostVersion),
      pr: n(locale.pr, 1),
      ww: n(locale.ww),
      wh: n(locale.wh),
      sw: n(locale.sw),
      sh: n(locale.sh),
      lang: s(locale.lang),
      net: s(net.net, 'unknown'),
      lat: s(location.lat),
      lng: s(location.lng),
      mpn: s((_c = legacy === null || legacy === void 0 ? void 0 : legacy.mpn) !== null && _c !== void 0 ? _c : pkg.mpn),
      tdaid: s(pkg.tdaid),
      pkn: s(pkg.pkn),
      an: s(pkg.an),
      domain: s(web.domain)
    };
  }
  /**
   * 会话字段：所有 lt 都要带。
   *
   * 与文档对齐：仅上行 `sid` 与 `cst`；
   * 内部状态字段 `sst / seq` 不再随上行体发出，仅保留在 SessionSnapshot 中。
   */
  function sessionFields(ctx) {
    if (!ctx.session) return {};
    return {
      sid: ctx.session.sid,
      cst: ctx.session.sct
    };
  }
  /** 页面字段：lt=11/3 / 普通页面事件携带。 */
  function pageFields(ctx) {
    const out = {};
    if (ctx.url !== undefined) out.url = s(ctx.url);
    if (ctx.urlref !== undefined) out.urlref = s(ctx.urlref);
    if (ctx.urlref_ts !== undefined) out.urlref_ts = n(ctx.urlref_ts);
    if (ctx.ttn !== undefined) out.ttn = s(ctx.ttn);
    if (ctx.ttpj !== undefined) out.ttpj = s(ctx.ttpj);
    if (ctx.ttc !== undefined) out.ttc = s(ctx.ttc);
    return out;
  }
  /**
   * 入口标记：**仅 lt=11** 携带 iey + ppiey（缺省按 0）；lt=1 / lt=3 等不参与入口字段。
   */
  function entryFields(ctx) {
    if (ctx.lt === '11') {
      return {
        iey: toIey(ctx.iey !== undefined ? ctx.iey : false),
        ppiey: toIey(ctx.ppiey !== undefined ? ctx.ppiey : false)
      };
    }
    return {};
  }
  /** 访问字段：仅 lt=1（应用启动 / 新会话）且 collector 显式传入 visit 时携带。 */
  function visitFields(ctx) {
    if (ctx.lt !== '1') return {};
    if (!ctx.visit) return {};
    return {
      fvts: ctx.visit.fvts,
      lvts: ctx.visit.lvts,
      tvc: ctx.visit.tvc
    };
  }
  /** 启动场景：仅 lt=1 携带。 */
  function launchFields(ctx) {
    if (ctx.lt !== '1') return {};
    if (ctx.sc === undefined) return {};
    return {
      sc: s(ctx.sc)
    };
  }
  /**
   * 错误事件特化字段：lt=31 时把 `errMsg`（含 stack）截断后写入 `em`。
   *
   * 截断动机：长 Error stack（尤其是 jest / Node 调用栈）轻易超过 3KB，会让单条事件
   * 触发 `SINGLE_EVENT_MAX_BYTES` 被 enqueue 丢弃；这里在 builder 阶段先做一次软截断，
   * 既能保留头部关键定位信息（错误类型、消息、第一层 stack），又能保证事件可达。
   *
   * 阈值：3KB（保留 1KB buffer 给其他字段，整体仍在 SINGLE_EVENT_MAX_BYTES = 4KB 内）。
   */
  function errorFields(ctx) {
    if (ctx.lt !== '31' || !ctx.errMsg) return {};
    const ERR_MSG_MAX = 3 * 1024;
    const TRUNC_SUFFIX = '…[truncated]';
    let em = s(ctx.errMsg);
    if (em.length > ERR_MSG_MAX) {
      em = em.slice(0, ERR_MSG_MAX - TRUNC_SUFFIX.length) + TRUNC_SUFFIX;
    }
    return {
      em
    };
  }
  /** Push 事件特化字段。 */
  function pushFields(ctx) {
    if (ctx.lt !== '101' || !ctx.cid) return {};
    return {
      cid: s(ctx.cid)
    };
  }
  /**
   * 拼装最终上行体。
   *
   * 合并顺序（**后者覆盖前者**）：
   *   base → session → page → entry → visit → launch → error → push → custom
   * custom 放最后，业务可控扩展，但**不允许**覆盖 lt/t/sid 等关键字段（在此过滤）。
   */
  function build(ctx) {
    const safeCustom = {};
    if (ctx.custom) {
      const reserved = new Set(['lt', 't', 'sid', 'cst', 'did', 'p', 'on', 'mpv', 'domain', 'fvts', 'lvts', 'tvc', 'sc']);
      for (const k of Object.keys(ctx.custom)) {
        if (!reserved.has(k)) safeCustom[k] = ctx.custom[k];
      }
    }
    const out = {
      lt: ctx.lt,
      t: n(ctx.t)
    };
    Object.assign(out, baseFields(), sessionFields(ctx), pageFields(ctx), entryFields(ctx), visitFields(ctx), launchFields(ctx), errorFields(ctx), pushFields(ctx), safeCustom);
    return out;
  }
  return {
    build
  };
}

/**
 * App 渠道包标识适配（对齐私有版 `utils/pageInfo.js#get_channel`）。
 *
 * HBuilderX 云打包会为每个渠道包写入 `plus.runtime.channel`（如 huawei、oppo），
 * 统计上行字段 `ch` 应优先读取该运行时值，而非 manifest 静态配置。
 *
 * 职责：
 *   - App 端（`isApp()`）尝试读取 `plus.runtime.channel`。
 *   - 若构建期平台变量缺失但运行时已存在 `plus.runtime`，也信任原生运行时作为 App 信号。
 *   - 任意 API 缺失 / 抛错 → 降级 `''`，不阻断 install。
 *   - 返回值统一为 `string`（原生偶发返回数字时转为字符串）。
 */
/**
 * 将原生渠道值规范为上行用的字符串。
 *
 * @param value `plus.runtime.channel` 原值。
 * @returns 非空字符串；无法识别时返回 `''`。
 */
function normalizeChannelValue(value) {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}
/**
 * 读取 App 渠道包标识（`plus.runtime.channel`）。
 *
 * 与私有版 `get_channel()` 对齐：仅原生 App 有意义；小程序 / H5 恒为 `''`。
 *
 * @returns 渠道字符串；未配置或读取失败时为 `''`。
 */
function getAppChannel() {
  const plus = getGlobalObject().plus;
  if (!isApp() && !(plus === null || plus === void 0 ? void 0 : plus.runtime)) return '';
  const raw = tryRun(() => {
    var _a;
    return (_a = plus === null || plus === void 0 ? void 0 : plus.runtime) === null || _a === void 0 ? void 0 : _a.channel;
  }, undefined);
  return normalizeChannelValue(raw);
}

/**
 * 系统信息适配。
 *
 * 私有版的痛点（参考缺陷清单 #14、#18）：
 *   - `utils/util.js` 顶层 `export const sys = uni.getSystemInfoSync()`：模块加载即执行
 *     `uni.getSystemInfoSync`，SSR / 单测 / nvue 早期阶段会直接抛错。
 *   - `lang / ww / wh` 等"可变"字段被一同缓存，用户切换系统语言或旋转屏幕后字段失真。
 *
 * 公有版职责：
 *   1. `getSystemInfo()` 懒加载 + 缓存（不可变字段：brand/md/sv/v/ut/on …）。
 *   2. `getLocaleAndScreen()` 实时取（lang + ww/wh + sw/sh + pr）—— 修复缺陷 #18。
 *   3. SSR/单测：任一 API 不存在或抛错时，返回安全空对象，绝不抛。
 *   4. `__resetCache()`：仅供测试，重置缓存。
 *
 * 小程序新基础库对 `getSystemInfoSync` 做了能力拆分，部分字段为空或恒为 0。
 * 因此优先通过 `uni.getDeviceInfo / getAppBaseInfo / getWindowInfo` 取对应信息，
 * 再以 `uni.getSystemInfoSync` 合并兜底（与 uni-app 运行时、uni-api 侧实践一致）。
 *
 * **小程序注意**：`uni` 常由构建注入在模块作用域，仅读 `globalThis.uni` 会取不到
 * 任何 API；必须通过 `resolveUniRuntime()` 与 `package.ts` 等 adapter 对齐。
 * 微信系再叠一层 `wx.getDeviceInfo / getAppBaseInfo / getWindowInfo`（与 `uni-api`
 * `upx2px` 一致），避免 `uni` 代理未就绪时宽高全 0。
 */
let cachedStatic = null;
/**
 * 解析 `uni` 根对象：优先 `globalThis.uni`，再回退宿主注入的模块级 `uni`。
 *
 * @see `infra/uniRuntime.ts` 说明（小程序上仅读 globalThis 会静默失败）。
 */
function getUni$4() {
  const u = resolveUniRuntime();
  return u != null && typeof u === 'object' ? u : undefined;
}
/**
 * 微信系宿主上再取一层原生拆分 API，与 `uni` 合并结果再叠加以补全字段。
 *
 * @returns 已按 sync→device→app→window 合并过的一条快照；非微信系返回 `null`。
 */
function mergeWxHostSnapshots() {
  const raw = getRawPlatform();
  if (raw !== 'mp-weixin' && raw !== 'mp-qq') return null;
  const wxHost = getGlobalObject().wx;
  if (!wxHost) return null;
  const sync = typeof wxHost.getSystemInfoSync === 'function' ? tryRun(() => wxHost.getSystemInfoSync(), null) : null;
  const device = typeof wxHost.getDeviceInfo === 'function' ? tryRun(() => wxHost.getDeviceInfo(), null) : null;
  const appBase = typeof wxHost.getAppBaseInfo === 'function' ? tryRun(() => wxHost.getAppBaseInfo(), null) : null;
  const windowInfo = typeof wxHost.getWindowInfo === 'function' ? tryRun(() => wxHost.getWindowInfo(), null) : null;
  return mergeSystemSnapshots(sync, device, appBase, windowInfo);
}
/**
 * 从左到右浅合并多个快照：后者非 `undefined` / `null` 的键覆盖前者。
 *
 * 合并顺序为「sync → device → appBase → window」，使拆分 API 覆盖宿主裁剪后的
 * `getSystemInfoSync` 残缺字段。
 */
function mergeSystemSnapshots(...parts) {
  const out = {};
  for (const p of parts) {
    if (!p) continue;
    for (const k of Object.keys(p)) {
      const v = p[k];
      if (v !== undefined && v !== null) out[k] = v;
    }
  }
  return out;
}
/**
 * 聚合当前运行时的系统信息：先 `getSystemInfoSync` 打底，再叠拆分 API。
 *
 * 各 API 均经 `tryRun` 包裹，任一失败不影响其余来源。
 */
function mergedSystemInfo() {
  const u = getUni$4();
  const sync = u && typeof u.getSystemInfoSync === 'function' ? tryRun(() => u.getSystemInfoSync(), null) : null;
  const device = u && typeof u.getDeviceInfo === 'function' ? tryRun(() => u.getDeviceInfo(), null) : null;
  const appBase = u && typeof u.getAppBaseInfo === 'function' ? tryRun(() => u.getAppBaseInfo(), null) : null;
  const windowInfo = u && typeof u.getWindowInfo === 'function' ? tryRun(() => u.getWindowInfo(), null) : null;
  const fromUni = mergeSystemSnapshots(sync, device, appBase, windowInfo);
  const fromWx = mergeWxHostSnapshots();
  const merged = fromWx ? mergeSystemSnapshots(fromUni, fromWx) : fromUni;
  return merged;
}
/**
 * 读取 H5 运行时 `__uniConfig.appVersion`（manifest.versionName）。
 *
 * H5 发行摇树时模块加载期 `window.uni` 可能仍是 `{}` 空桩，`resolveUniRuntime`
 * 无法调用 `getAppBaseInfo`；此时 `__uniConfig` 仍已由构建注入，可作为应用版本兜底。
 */
function resolveUniConfigAppVersion() {
  return tryRun(() => {
    const cfg = getGlobalObject().__uniConfig;
    return typeof (cfg === null || cfg === void 0 ? void 0 : cfg.appVersion) === 'string' ? cfg.appVersion : '';
  }, '');
}
/**
 * 读取构建期注入的 `UNI_APP_VERSION_NAME`（manifest.versionName）。
 *
 * 须**直接**访问 `process.env.UNI_APP_VERSION_NAME`，以便 Vite define 静态替换；
 * 经中间变量读取会导致发行包内始终为空（与 `install.ts#parseInjectedUniStatistics` 同理）。
 */
function resolveBuildTimeAppVersion() {
  const raw = "1.2.7";
  return typeof raw === 'string' ? raw : '';
}
/**
 * 解析上行用的应用版本 `appVersion`（对应 statData 字段 `v` 的主要回退来源）。
 *
 * 优先级：App 原生 `plus.runtime.version` → uni 拆分 API → H5 `__uniConfig` → 构建期 env。
 */
function resolveAppVersionForStat(plus, sys) {
  var _a;
  const fromPlus = (_a = plus === null || plus === void 0 ? void 0 : plus.runtime) === null || _a === void 0 ? void 0 : _a.version;
  if (typeof fromPlus === 'string' && fromPlus) return fromPlus;
  const fromSys = sys.appVersion;
  if (typeof fromSys === 'string' && fromSys) return fromSys;
  const fromUniConfig = resolveUniConfigAppVersion();
  if (fromUniConfig) return fromUniConfig;
  return resolveBuildTimeAppVersion();
}
/**
 * 组装上行 `on`：优先厂商定制系统名（ROM），否则退回操作系统名 `osName`。
 *
 * App 端 `uni.getDeviceInfo` 会带出 `romName`/`romVersion`（见 uni-app-plus 原生 systemInfo）；
 * 微信等小程序沙箱通常无 ROM 字段，此时与仅 `osName` 一致。
 *
 * @param sys `mergedSystemInfo()` 合并结果
 * @returns 去首尾空白后的展示串；均无则空串
 */
function buildOnForStat(sys) {
  const rom = typeof sys.romName === 'string' ? sys.romName.trim() : '';
  if (rom) {
    const romVer = typeof sys.romVersion === 'string' ? sys.romVersion.trim() : '';
    return romVer ? `${rom} ${romVer}`.trim() : rom;
  }
  return typeof sys.osName === 'string' ? sys.osName.trim() : '';
}
/**
 * 取静态系统信息（懒加载 + 缓存）。
 *
 * 字段映射策略：
 *   - `brand / md`：优先 `deviceBrand`/`deviceModel`（拆分 API），再退化 `brand`/`model`。
 *   - `sv / v / sdkVersion`：优先 `osVersion`、`hostVersion`、`hostSDKVersion`，兼容旧字段。
 *   - `osP`：由 `platform` / `osName` / `system` 经 `normalizeStatOsP` 得到，供上行 `p`。
 *   - `mpvHostVersion`：`hostVersion ?? version`，与私有版 `sys.version` 同源。
 *   - `on`：`buildOnForStat`（优先 `romName`/`romVersion`，否则 `osName`），供上行 `on`。
 *   - `appVersion`：见 `resolveAppVersionForStat`（H5 发行空桩时回退 `__uniConfig` / 构建 env）。
 *   - 缺失统一空字符串或 0，避免上行 JSON 丢字段语义。
 */
function getSystemInfo() {
  var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p, _q, _r, _s, _t;
  if (cachedStatic) return cachedStatic;
  const sys = mergedSystemInfo();
  const plus = getGlobalObject().plus;
  const appVersion = resolveAppVersionForStat(plus, sys);
  cachedStatic = {
    brand: (_b = (_a = sys.deviceBrand) !== null && _a !== void 0 ? _a : sys.brand) !== null && _b !== void 0 ? _b : '',
    md: (_d = (_c = sys.deviceModel) !== null && _c !== void 0 ? _c : sys.model) !== null && _d !== void 0 ? _d : '',
    sv: (_f = (_e = sys.osVersion) !== null && _e !== void 0 ? _e : sys.system) !== null && _f !== void 0 ? _f : '',
    v: (_h = (_g = sys.hostVersion) !== null && _g !== void 0 ? _g : sys.version) !== null && _h !== void 0 ? _h : '',
    ut: (_j = sys.deviceType) !== null && _j !== void 0 ? _j : 'unknown',
    appVersion,
    appWgtVersion: (_p = (_o = (_l = (_k = plus === null || plus === void 0 ? void 0 : plus.runtime) === null || _k === void 0 ? void 0 : _k.appWgtVersion) !== null && _l !== void 0 ? _l : (_m = plus === null || plus === void 0 ? void 0 : plus.runtime) === null || _m === void 0 ? void 0 : _m.appWgtRevision) !== null && _o !== void 0 ? _o : sys.appWgtVersion) !== null && _p !== void 0 ? _p : '',
    mpvHostVersion: ((_r = (_q = sys.hostVersion) !== null && _q !== void 0 ? _q : sys.version) !== null && _r !== void 0 ? _r : '').trim(),
    on: buildOnForStat(sys),
    sdkVersion: (_t = (_s = sys.hostSDKVersion) !== null && _s !== void 0 ? _s : sys.SDKVersion) !== null && _t !== void 0 ? _t : '',
    statusBarHeight: typeof sys.statusBarHeight === 'number' ? sys.statusBarHeight : 0,
    osP: normalizeStatOsP({
      platform: sys.platform,
      osName: sys.osName,
      system: sys.system
    })
  };
  return cachedStatic;
}
/**
 * 取实时字段（lang / 窗口尺寸 / 屏幕尺寸 / dpr）。
 *
 * 每次调用重新走拆分 API + sync 合并，不复用缓存，避免旋转屏、改语言后失真。
 */
function getLocaleAndScreen() {
  var _a, _b;
  const sys = mergedSystemInfo();
  const prRaw = typeof sys.pixelRatio === 'number' ? sys.pixelRatio : typeof sys.devicePixelRatio === 'number' ? sys.devicePixelRatio : 1;
  return {
    lang: ((_b = (_a = sys.hostLanguage) !== null && _a !== void 0 ? _a : sys.language) !== null && _b !== void 0 ? _b : '').replace(/_/g, '-'),
    ww: typeof sys.windowWidth === 'number' ? sys.windowWidth : 0,
    wh: typeof sys.windowHeight === 'number' ? sys.windowHeight : 0,
    sw: typeof sys.screenWidth === 'number' ? sys.screenWidth : 0,
    sh: typeof sys.screenHeight === 'number' ? sys.screenHeight : 0,
    pr: prRaw > 0 ? prRaw : 1
  };
}

/**
 * 包信息适配（公有版新增字段 `tdaid / pkn / an`）。
 *
 * 详细矩阵参考 `04-字段字典与平台获取矩阵.md` §3。本模块职责：
 *   - 启动时调用一次 `getPackageInfo()`，结果常驻内存；不入 storage。
 *   - 每端分支独立函数，便于单测精准 mock。
 *   - 任意端、任意 API 抛错 → 一律降级为 `''`，**绝不**抛出。
 *
 * 字段语义提示：
 *   - `mpn`：兼容字段；各端「原生包名或小程序 appid」的统一口径（与文档 `mpn` 对齐）。
 *   - `tdaid`：第三方平台 appid（如微信小程序 appid）。
 *   - `pkn`：原生包名 / bundleId（App）；小程序无独立包名时为空串，**不与** tdaid 混填。
 *   - `an`：应用展示名（App = plus.runtime.appname；小程序/H5 = `process.env.UNI_APP_NAME` 等）。
 */
let cached$1 = null;
function getUni$3() {
  const u = resolveUniRuntime();
  return u != null && typeof u === 'object' ? u : undefined;
}
function getPlus() {
  return getGlobalObject().plus;
}
/**
 * 取小程序系列的 tdaid。各端 API 不同：
 *   - 微信/QQ：`uni.getAccountInfoSync().miniProgram.appId`（基础库 ≥ 1.10.0）。
 *   - 支付宝：`my.getAppIdSync()`（部分版本可用）。
 *   - 头条/飞书：`tt.getEnvInfoSync().microapp.appId`。
 *   - 百度：`swan.getEnvInfoSync().common.appKey` 兜底。
 *   - 其他端：暂时返回 ''；后续真机探测后再补。
 *
 * 任何分支抛错都返回 ''。
 */
function getMpTdaid(platform) {
  const u = getUni$3();
  switch (platform) {
    case 'wx':
    case 'qq':
      {
        if (typeof (u === null || u === void 0 ? void 0 : u.getAccountInfoSync) === 'function') {
          const id = tryRun(() => {
            var _a, _b;
            return (_b = (_a = u.getAccountInfoSync().miniProgram) === null || _a === void 0 ? void 0 : _a.appId) !== null && _b !== void 0 ? _b : '';
          }, '');
          if (id) return id;
        }
        const wxHost = getGlobalObject().wx;
        if (typeof (wxHost === null || wxHost === void 0 ? void 0 : wxHost.getAccountInfoSync) === 'function') {
          const id2 = tryRun(() => {
            var _a, _b;
            return (_b = (_a = wxHost.getAccountInfoSync().miniProgram) === null || _a === void 0 ? void 0 : _a.appId) !== null && _b !== void 0 ? _b : '';
          }, '');
          if (id2) return id2;
        }
        const envId = "";
        return typeof envId === 'string' ? envId : '';
      }
    case 'ali':
    case 'dt':
      {
        const my = getGlobalObject().my;
        if (!my) return '';
        const v1 = tryRun(() => {
          var _a, _b;
          return (_b = (_a = my.getAppIdSync) === null || _a === void 0 ? void 0 : _a.call(my)) !== null && _b !== void 0 ? _b : '';
        }, '');
        if (v1) return v1;
        return tryRun(() => {
          var _a, _b, _c;
          return (_c = (_b = (_a = my.getAccountInfoSync) === null || _a === void 0 ? void 0 : _a.call(my).miniProgram) === null || _b === void 0 ? void 0 : _b.appId) !== null && _c !== void 0 ? _c : '';
        }, '');
      }
    case 'tt':
    case 'lark':
      {
        const tt = getGlobalObject().tt;
        return tryRun(() => {
          var _a, _b, _c;
          return (_c = (_b = (_a = tt === null || tt === void 0 ? void 0 : tt.getEnvInfoSync) === null || _a === void 0 ? void 0 : _a.call(tt).microapp) === null || _b === void 0 ? void 0 : _b.appId) !== null && _c !== void 0 ? _c : '';
        }, '');
      }
    case 'bd':
      {
        const swan = getGlobalObject().swan;
        return tryRun(() => {
          var _a, _b, _c;
          return (_c = (_b = (_a = swan === null || swan === void 0 ? void 0 : swan.getEnvInfoSync) === null || _a === void 0 ? void 0 : _a.call(swan).common) === null || _b === void 0 ? void 0 : _b.appKey) !== null && _c !== void 0 ? _c : '';
        }, '');
      }
    default:
      return '';
  }
}
/**
 * App 端 packageName / bundleId。
 *
 * Android 走 `plus.android.runtimeMainActivity().getPackageName()`；
 * iOS 走 `plus.ios.bundleId`，缺失时退化 `plus.runtime.appid`；
 * HarmonyOS 暂时取 `plus.runtime.appid` 兜底（待 OS API 稳定后扩展）。
 */
function getAppPkn() {
  var _a, _b, _c;
  const plus = getPlus();
  if (!plus) return '';
  const osName = (_c = (_b = (_a = plus.os) === null || _a === void 0 ? void 0 : _a.name) === null || _b === void 0 ? void 0 : _b.toLowerCase()) !== null && _c !== void 0 ? _c : '';
  if (osName.includes('android')) {
    return tryRun(() => {
      var _a, _b, _c, _d, _e;
      return (_e = (_d = (_c = (_b = (_a = plus.android) === null || _a === void 0 ? void 0 : _a.runtimeMainActivity) === null || _b === void 0 ? void 0 : _b.call(_a)) === null || _c === void 0 ? void 0 : _c.getPackageName) === null || _d === void 0 ? void 0 : _d.call(_c)) !== null && _e !== void 0 ? _e : '';
    }, '');
  }
  if (osName === 'ios' || osName === 'iphone os') {
    const v = tryRun(() => {
      var _a, _b;
      return (_b = (_a = plus.ios) === null || _a === void 0 ? void 0 : _a.bundleId) !== null && _b !== void 0 ? _b : '';
    }, '');
    return v || tryRun(() => {
      var _a, _b;
      return (_b = (_a = plus.runtime) === null || _a === void 0 ? void 0 : _a.appid) !== null && _b !== void 0 ? _b : '';
    }, '');
  }
  return tryRun(() => {
    var _a, _b;
    return (_b = (_a = plus.runtime) === null || _a === void 0 ? void 0 : _a.appid) !== null && _b !== void 0 ? _b : '';
  }, '');
}
/**
 * 取 plus.runtime.appname / plus.runtime.name。
 *
 * 旧版本 plus 上字段名不一致，两个都试一次。
 */
function getAppName() {
  const plus = getPlus();
  if (!plus) return '';
  return tryRun(() => {
    var _a, _b;
    return (_b = (_a = plus.runtime) === null || _a === void 0 ? void 0 : _a.appname) !== null && _b !== void 0 ? _b : '';
  }, '') || tryRun(() => {
    var _a, _b;
    return (_b = (_a = plus.runtime) === null || _a === void 0 ? void 0 : _a.name) !== null && _b !== void 0 ? _b : '';
  }, '');
}
/**
 * 取编译期注入的 UNI_APP_NAME。
 *
 * `plugin/index.ts` 后续会读取 `manifest.json#name` 注入此字段；当前若未注入返回 ''。
 */
function getEnvAppName() {
  var _a;
  return (_a = "商城") !== null && _a !== void 0 ? _a : '';
}
/**
 * 取 H5 端应用名：优先编译期注入，回退 `document.title`。
 */
function getH5AppName() {
  const env = getEnvAppName();
  if (env) return env;
  return tryRun(() => {
    var _a, _b;
    return (_b = (_a = getGlobalObject().document) === null || _a === void 0 ? void 0 : _a.title) !== null && _b !== void 0 ? _b : '';
  }, '');
}
/**
 * 启动时获取一次包信息；结果缓存于内存。
 *
 * 所有字段保证返回 `string`；缺失统一为 `''`，符合 `domain/statData.ts` 的字段处理约定。
 */
function getPackageInfo() {
  if (cached$1) return cached$1;
  const platform = getPlatform();
  let mpn = '';
  let tdaid = '';
  let pkn = '';
  let an = '';
  if (isApp()) {
    tdaid = tryRun(() => {
      var _a, _b, _c;
      return (_c = (_b = (_a = getPlus()) === null || _a === void 0 ? void 0 : _a.runtime) === null || _b === void 0 ? void 0 : _b.appid) !== null && _c !== void 0 ? _c : '';
    }, '');
    pkn = getAppPkn() || tdaid;
    an = getAppName() || getEnvAppName();
    mpn = pkn || tdaid;
  } else if (isMp()) {
    tdaid = getMpTdaid(platform);
    pkn = '';
    an = getEnvAppName();
    mpn = tdaid || ( true ? "" : undefined);
  } else if (isH5()) {
    tdaid = '';
    pkn = '';
    an = getH5AppName();
    mpn = '';
  } else {
    // unknown / 快应用等：尝试 env 注入即可
    tdaid = '';
    pkn = '';
    an = getEnvAppName();
    mpn = '';
  }
  cached$1 = {
    mpn,
    tdaid,
    pkn,
    an
  };
  return cached$1;
}

/**
 * H5 / Web 平台适配。
 *
 * 职责：采集仅 Web 端有意义的上行字段原料（如含协议的页面域名 `domain`）。
 * 非 H5 或运行时无 `window.location` 时一律返回空串，不抛错。
 */
const EMPTY_WEB_INFO = {
  domain: ''
};
let cached = null;
/**
 * 从 `location` 解析上行 `domain`（`https://host` / `http://host` 形式）。
 *
 * 仅 `http:` / `https:` 协议有效；`file:` 等返回空串。
 */
function readWebDomainFromLocation(loc) {
  const protocol = typeof loc.protocol === 'string' ? loc.protocol.toLowerCase() : '';
  if (protocol !== 'http:' && protocol !== 'https:') return '';
  if (typeof loc.origin === 'string' && loc.origin.trim()) {
    return loc.origin.trim();
  }
  const host = typeof loc.host === 'string' && loc.host.trim() ? loc.host.trim() : typeof loc.hostname === 'string' ? loc.hostname.trim() : '';
  if (!host) return '';
  return `${protocol}//${host}`;
}
/**
 * 读取 H5 页面 Web 信息。
 *
 * 非 H5、SSR 或无 `location` 时 `domain` 为空串。
 * 结果在进程内缓存（SPA 内 origin 通常不变）。
 */
function getWebInfo() {
  if (!isH5()) return EMPTY_WEB_INFO;
  if (cached !== null) return cached;
  cached = tryRun(() => {
    const win = getGlobalObject();
    const loc = win.location;
    if (!loc) return EMPTY_WEB_INFO;
    return {
      domain: readWebDomainFromLocation(loc)
    };
  }, EMPTY_WEB_INFO);
  return cached;
}
const registry = new Map();
/**
 * 本模块每个 api 最近一次装入 uni 的 fanout 引用。
 * 用于重装 / 解绑时按引用精准 `removeInterceptor(api, prevFanout)`，不波及第三方拦截器。
 */
const installedFanout = new Map();
/**
 * 注册一个拦截器。同一 api 重复注册会去重，并自动按当前注册集合重装到 uni。
 *
 * @returns 解绑函数。调用后从集合中移除本次的 handlers，并按剩余集合重新装配。
 */
function add(api, handlers) {
  var _a;
  const set = (_a = registry.get(api)) !== null && _a !== void 0 ? _a : new Set();
  set.add(handlers);
  registry.set(api, set);
  reinstall(api);
  return () => {
    const cur = registry.get(api);
    if (!cur) return;
    cur.delete(handlers);
    if (cur.size === 0) {
      registry.delete(api);
      const prev = installedFanout.get(api);
      installedFanout.delete(api);
      if (prev) {
        try {
          // 精准移除本模块的 fanout，保留第三方在同一 api 上的拦截器。
          getUni$2().removeInterceptor(api, prev);
        } catch (_a) {
          // 即使解绑失败也应保证下次重装时不带本次 handlers
        }
      }
    } else {
      reinstall(api);
    }
  };
}
/**
 * 把某个 api 的全部 handlers 合并成单个 fanout 拦截器。
 *
 * 闭包持有 `set` 引用（registry 内的同一 Set），故 fanout 会实时反映集合的增删。
 */
function buildFanout(set) {
  return {
    invoke(args) {
      let blocked = false;
      for (const h of set) {
        if (!h.invoke) continue;
        const r = h.invoke(args);
        if (r === false) blocked = true;
      }
      return blocked ? false : undefined;
    },
    success(res) {
      var _a;
      for (const h of set) (_a = h.success) === null || _a === void 0 ? void 0 : _a.call(h, res);
    },
    fail(err) {
      var _a;
      for (const h of set) (_a = h.fail) === null || _a === void 0 ? void 0 : _a.call(h, err);
    },
    complete(res) {
      var _a;
      for (const h of set) (_a = h.complete) === null || _a === void 0 ? void 0 : _a.call(h, res);
    },
    returnValue(res) {
      let v = res;
      for (const h of set) {
        if (!h.returnValue) continue;
        v = h.returnValue(v);
      }
      return v;
    }
  };
}
/**
 * 把 registry 中某个 api 的全部 handlers 合并成一个 fanout 拦截器，重新挂到 uni。
 *
 * 精准重装：先按引用移除本模块**上一次**装入的 fanout（若有），再装入新 fanout；
 * 全程不调用「不带第二参数」的 blanket remove，故业务方 / 其它插件在同一 api 上的
 * 拦截器不会被波及。
 */
function reinstall(api) {
  const set = registry.get(api);
  if (!set || set.size === 0) return;
  const fanout = buildFanout(set);
  try {
    const uni = getUni$2();
    const prev = installedFanout.get(api);
    if (prev) {
      try {
        uni.removeInterceptor(api, prev);
      } catch (_a) {
        /* ignore：旧 fanout 移除失败不阻断新 fanout 装入 */
      }
    }
    uni.addInterceptor(api, fanout);
    installedFanout.set(api, fanout);
  } catch (_b) {
    // uni 不可用（例如 nvue 早期阶段）：保留 registry 与 installedFanout，等下次 reinstall 再试
  }
}
function getUni$2() {
  const raw = resolveUniRuntime();
  const u = raw != null && typeof raw === 'object' ? raw : undefined;
  if (!u) throw new Error('[uni统计 2.0] uni interceptor API is not available');
  return u;
}
/**
 * 仅供单测使用：清空 registry，让本模块「像刚加载」一样。
 */
function __reset() {
  registry.clear();
  installedFanout.clear();
}
const interceptor = {
  add,
  __reset
};

/**
 * 拦截 `uni.login` 调用，complete 时上报一条 `lt=21, e_n=login` 自定义事件。
 *
 * 与私有版差异：
 *   - 走 `infra/interceptor.add`，多次 register 不会覆盖回调（修复缺陷 #26）。
 *   - 通过 `reporter` 注入，便于单测断言。
 */
/**
 * 注册 login 拦截器。
 *
 * @returns 解绑函数。同一 reporter 多次 register 视为多次回调（fanout）；卸载时只摘当次。
 */
function registerLoginInterceptor(reporter) {
  return interceptor.add('login', {
    complete() {
      reporter.report({
        lt: LT.Event,
        custom: {
          e_n: 'login'
        }
      });
    }
  });
}

/**
 * 拦截 `uni.setNavigationBarTitle`，把用户设置的标题写入 `domain/title` 内存。
 *
 * **不**直接 reporter.report；title 是字段维度的状态，由 statData.builder 在拼装
 * 页面事件时一次性读出。这样保证 ttn 与 lt=11 / lt=3 事件强相关，避免私有版"标题在
 * 全局对象、上报时机散落"的问题。
 */
/**
 * 注册 setNavigationBarTitle 拦截器；不依赖 reporter。
 *
 * @returns 解绑函数。
 */
function registerNavigationBarInterceptor() {
  return interceptor.add('setNavigationBarTitle', {
    invoke(args) {
      const a = args;
      if (a && 'title' in a) setPageTitle(a.title);
    }
  });
}

/**
 * 拦截 `uni.requestPayment`：
 *   - success → `lt=21, e_n=pay_success`
 *   - fail    → `lt=21, e_n=pay_fail`
 *
 * 与私有版差异：经由 `infra/interceptor.add` 去重；多 reporter 注册都会触发（fanout）。
 */
function registerPaymentInterceptor(reporter) {
  return interceptor.add('requestPayment', {
    success() {
      reporter.report({
        lt: LT.Event,
        custom: {
          e_n: 'pay_success'
        }
      });
    },
    fail() {
      reporter.report({
        lt: LT.Event,
        custom: {
          e_n: 'pay_fail'
        }
      });
    }
  });
}

/**
 * 拦截 `uni.share` 调用，success / fail 都上报一条 `lt=21, e_n=share` 自定义事件。
 *
 * 与私有版差异（修复缺陷 #26）：
 *   - 私有版 `interceptShare(true)` 在 `onLoad` 内重复 wrap `onShareAppMessage`，
 *     连续打开同一页面会导致 share 事件被多次上报。
 *   - 公有版通过 `infra/interceptor` 单次 fanout 注册；onLoad 不再重复包装。
 */
function registerShareInterceptor(reporter) {
  const fire = () => reporter.report({
    lt: LT.Event,
    custom: {
      e_n: 'share'
    }
  });
  return interceptor.add('share', {
    success() {
      fire();
    },
    fail() {
      fire();
    }
  });
}

/**
 * 拦截器统一装配入口。
 *
 * 使用：
 *   ```ts
 *   import { installAllInterceptors } from './interceptors'
 *   const uninstall = installAllInterceptors(collector)  // collector 实现 InterceptorReporter
 *   // 卸载（hot reload / unit test）：
 *   uninstall()
 *   ```
 *
 * 重复 install 安全：每次 install 都会返回独立的 unbinder；多次 install 触发的 fanout
 * 由 `infra/interceptor` 统一去重 + 解绑。
 */
/**
 * 一次性装配全部拦截器。
 *
 * @returns 解绑函数（顺序解绑全部已注册的拦截器）。
 */
function installAllInterceptors(reporter) {
  const unbinders = [registerLoginInterceptor(reporter), registerShareInterceptor(reporter), registerPaymentInterceptor(reporter), registerNavigationBarInterceptor()];
  return () => {
    for (const u of unbinders) {
      try {
        u();
      } catch (_a) {
        // 单个解绑失败不影响其余
      }
    }
  };
}

/**
 * 老版本（私有版 1.0/2.0）→ 公有版数据迁移。
 *
 * 老版本通过 `utils/db.js` 把所有字段写到一个聚合 key：
 *   `$$STAT__DBDATA:<appid>` → `{ '__first__visit__time': T, '__last__visit__time': T, ... }`
 *
 * 公有版改为按字段拆 key（`UNI_STAT_DATA:<appid>:<key>`）。
 *
 * 本模块职责（只读老数据，不删）：
 *   1. **一次性**把已知字段从老聚合 key 拆解写入新命名空间。
 *   2. 保留老 key（不 remove），让私有版同库共存场景仍能正常运行。
 *   3. 通过新命名空间下的 `migration:done` 哨兵避免重复执行。
 *   4. 任何步骤异常 → 静默吞掉，不影响采集主链路。
 *
 * 不做的事：
 *   - 不在迁移中写"今天本次启动"的 fvts/lvts；那是 `domain/visit/firstVisit` 的职责。
 *   - 不抛错；调用方无需 try/catch。
 *
 * 调用时机：
 *   - 由 `runtime/install.ts` 在公有版启动早期调用一次（在 `loadVisitSnapshot` 之前），
 *     保证 firstVisit 读到的是已迁移的新前缀数据。
 */
/** 已迁移哨兵 key（写到新命名空间）。值固定为 1。 */
const KEY_DONE = 'migration:done';
/**
 * 老聚合 key 内字段 → 新拆分 key 的映射表。
 *
 * 仅迁移**对公有版有用**的字段；其它（如 `__page__residence__time`）保留老 key，
 * 由 Phase 5 的对应 domain 模块按需读取。
 */
const KEY_MAP = [['__first__visit__time', 'visit:fvts'], ['__last__visit__time', 'visit:lvts'], ['__total__visit__count', 'visit:tvc']];
/** 取 UNI_APP_ID（与 storage 内部保持一致的回退）。 */
function getAppId() {
  const id = "";
  if (typeof id === 'string' && id.length > 0) return id;
  return 'default';
}
/**
 * 从底层 uni 读取老聚合 key（不走 `infra/storage`，避免命名空间被改写）。
 *
 * 任何异常一律返回 `null`，由调用方决定 noop。
 */
function readLegacyAggregate() {
  const u = resolveUniRuntime();
  if (!u || typeof u.getStorageSync !== 'function') return null;
  const key = `${LEGACY_NAMESPACE_ROOT}:${getAppId()}`;
  const raw = tryRun(() => u.getStorageSync(key), null);
  if (raw && typeof raw === 'object') return raw;
  return null;
}
/** 哨兵：本进程内不重复 run。 */
let ran = false;
/**
 * 执行迁移；幂等：
 *   - 进程内已 run → 直接 return false。
 *   - 新命名空间已有 `migration:done` → 直接 return false。
 *   - 老聚合 key 不存在 / 为空 → 写 `migration:done`，return false。
 *   - 真正发生迁移 → return true。
 */
function migrateLegacyData() {
  if (ran) return false;
  ran = true;
  const doneR = storage.safeRead(KEY_DONE);
  if (doneR.ok && doneR.value) return false;
  const legacy = readLegacyAggregate();
  if (!legacy) {
    storage.set(KEY_DONE, 1);
    return false;
  }
  let migrated = 0;
  for (let i = 0; i < KEY_MAP.length; i++) {
    const [oldKey, newKey] = KEY_MAP[i];
    if (!(oldKey in legacy)) continue;
    const value = legacy[oldKey];
    // 已经存在新值就不覆盖（避免覆盖公有版自身已写入的更新值）
    const existing = storage.safeRead(newKey);
    if (existing.ok && existing.value !== undefined) continue;
    storage.set(newKey, value);
    migrated++;
  }
  storage.set(KEY_DONE, 1);
  if (migrated > 0) {
    logger.info('[uni统计 2.0] migrated legacy keys', migrated);
  }
  return migrated > 0;
}

/**
 * 通道选择器：根据**统计版本**与**运行环境**返回最合适的 Channel。
 *
 * 选择规则（公有版默认 image）：
 *   - `version === 'image'`（默认）：优先 image；image 不可用时按 fallback 决策走 http；
 *     image 通道未注入 → 静默走 http（公有版默认场景）。
 *   - `version === '2'`：优先 cloud；cloud 不可用时按 fallback 决策走 http（私有版兼容）。
 *   - `version === '1'`：始终 http。
 *
 * 注意：
 *   - 公有版**不会**主动构造 cloud channel（StatApp 仅在 version='2' 才创建），
 *     因此默认运行路径不会再触发"cloud channel unavailable"警告。
 *   - 选择是**幂等无副作用**的：调用方每次发送前调用 `selectChannel()` 即可，
 *     channel 自身不缓存可用性。
 */
/**
 * 根据策略挑选当前应使用的 channel。
 *
 * @returns 选中的 channel；若没有可用通道返回 `undefined`。
 */
function selectChannel(opts) {
  var _a;
  const version = (_a = opts.version) !== null && _a !== void 0 ? _a : 'image';
  const fallback = opts.fallbackToHttp !== false;
  if (version === '1') {
    if (opts.http && opts.http.available()) return opts.http;
    return undefined;
  }
  if (version === '2') {
    if (opts.cloud && opts.cloud.available()) return opts.cloud;
    if (!fallback) {
      logger.warn('[uni统计 2.0] 云函数上报不可用且已关闭 HTTP 兜底，本批已丢弃');
      return undefined;
    }
    if (opts.http && opts.http.available()) {
      logger.warn('[uni统计 2.0] 云函数上报不可用，已降级为 HTTP 上报');
      return opts.http;
    }
    logger.warn('[uni统计 2.0] 无可用上报线路');
    return undefined;
  }
  // image（默认）：image > http
  if (opts.image && opts.image.available()) return opts.image;
  if (!fallback) {
    if (opts.image) {
      // 仅在 image 已构造但失效时给出警告，便于排查；未构造视为正常的"未启用"
      logger.warn('[uni统计 2.0] 统计上报线路不可用且已关闭 HTTP 兜底，本批已丢弃');
    }
    return undefined;
  }
  if (opts.http && opts.http.available()) {
    if (opts.image) {
      // 同上，仅在 image 已构造但失效时打印降级日志
      logger.warn('[uni统计 2.0] 统计上报线路不可用，已降级为 HTTP 上报');
    }
    return opts.http;
  }
  logger.warn('[uni统计 2.0] 无可用上报线路');
  return undefined;
}

/**
 * 网络类型适配。
 *
 * 公有版要求（`03-公有版架构设计.md` §5.9）：
 *   - 返回 `Promise<NetResult>`，失败一律给默认值，**绝不**中断上报链路（修复缺陷 #10）。
 *   - 提供 `onChange` 订阅，便于会话上下文里"网络切换 → 触发一次 sessionDirty"。
 *
 * 字段映射：上行字段 `net`，与私有版字段保持一致；可选值：
 *   `wifi | 2g | 3g | 4g | 5g | ethernet | unknown | none`。
 */
const DEFAULT_RESULT = {
  net: 'unknown',
  raw: ''
};
/** 已知映射；命中外的统一归 unknown。 */
const NET_MAP = {
  wifi: 'wifi',
  '2g': '2g',
  '3g': '3g',
  '4g': '4g',
  '5g': '5g',
  ethernet: 'ethernet',
  none: 'none',
  unknown: 'unknown'
};
function getUni$1() {
  const u = resolveUniRuntime();
  return u != null && typeof u === 'object' ? u : undefined;
}
/**
 * 把 uni 原始 networkType 字符串归一化为 `NetType`。
 *
 * 抽出独立函数，便于上层直接复用（例如 `onChange` 回调里也要做归一）。
 */
function normalizeNet(raw) {
  var _a;
  if (typeof raw !== 'string' || raw.length === 0) return 'unknown';
  return (_a = NET_MAP[raw.toLowerCase()]) !== null && _a !== void 0 ? _a : 'unknown';
}
/**
 * 异步取当前网络类型。
 *
 * 一律 resolve（永不 reject）：
 *   - uni 缺失 / 调用抛错 / fail 回调 / 超时 → resolve(`{ net: 'unknown', raw: '' }`）。
 *   - 默认 1500ms 超时；防止 H5 端 navigator.connection 卡住采集链路。
 */
function getNet(timeoutMs = 1500) {
  return new Promise(resolve => {
    const u = getUni$1();
    if (!u || typeof u.getNetworkType !== 'function') {
      resolve(DEFAULT_RESULT);
      return;
    }
    let settled = false;
    const finish = r => {
      if (settled) return;
      settled = true;
      resolve(r);
    };
    const timer = setTimeout(() => finish(DEFAULT_RESULT), timeoutMs);
    tryRun(() => u.getNetworkType({
      success: res => {
        var _a;
        clearTimeout(timer);
        const raw = (_a = res === null || res === void 0 ? void 0 : res.networkType) !== null && _a !== void 0 ? _a : '';
        finish({
          net: normalizeNet(raw),
          raw
        });
      },
      fail: () => {
        clearTimeout(timer);
        finish(DEFAULT_RESULT);
      }
    }), undefined);
  });
}
/**
 * 订阅网络变化。返回 unsubscribe 函数，方便测试与运行时解绑。
 *
 * 注意：私有版直接调 `uni.onNetworkStatusChange` 但没有解绑，导致 nvue 多次 install 时
 * 会注册多个回调（缺陷 #16）。公有版返回 unsubscribe 强制调用方持有；
 * `runtime/install.ts` 会保证 install 多次时复用单实例。
 */
function onChange(cb) {
  const u = getUni$1();
  if (!u || typeof u.onNetworkStatusChange !== 'function') {
    return () => {
      /* noop */
    };
  }
  const wrapped = res => {
    var _a;
    const raw = (_a = res === null || res === void 0 ? void 0 : res.networkType) !== null && _a !== void 0 ? _a : '';
    const net = (res === null || res === void 0 ? void 0 : res.isConnected) === false ? 'none' : normalizeNet(raw);
    tryRun(() => cb({
      net,
      raw
    }), undefined);
  };
  // 注册本身也兜底：个别端 onNetworkStatusChange 同步抛错不应冒泡到调用方（与解绑对称）。
  tryRun(() => u.onNetworkStatusChange(wrapped), undefined);
  return () => {
    if (typeof u.offNetworkStatusChange === 'function') {
      tryRun(() => u.offNetworkStatusChange(wrapped), undefined);
    }
  };
}

/**
 * 公有版网络门闸（仅 `src/public` 使用，不与私有版 core 共用）。
 *
 * 能力：
 *   1. `isNetworkOffline()`：基于 `uni.getNetworkType` 判断当前是否无网；
 *   2. `onNetworkOnline(cb)`：基于 `uni.onNetworkStatusChange`，在恢复有网时回调。
 *
 * 判定：`net === 'none'` 为无网；`unknown` **不**当无网（避免误挂起）。
 */
/**
 * 根据 NetResult 判断是否无网。
 */
function isOfflineNetResult(r) {
  return r.net === 'none';
}
/**
 * 先检查当前网络是否不可用。
 */
function isNetworkOffline() {
  return __awaiter(this, void 0, void 0, function* () {
    const r = yield getNet();
    return isOfflineNetResult(r);
  });
}
/**
 * 监听网络恢复为可用。返回 unsubscribe。
 *
 * @param cb 变为有网时触发（wifi/4g/...）；无网变化不触发。
 */
function onNetworkOnline(cb) {
  return onChange(r => {
    if (isOfflineNetResult(r)) return;
    cb();
  });
}

/**
 * 事件入队 + 批量 flush，修复私有版缺陷 #3。
 *
 * 私有版 `report.js#request` 的入队逻辑：
 *   ```
 *   uniStatData = dbGet(KEY) || {}
 *   uniStatData[lt].push(data)
 *   dbSet(KEY, uniStatData)         // <-- 写
 *   ...
 *   const stat_data = handle_data(uniStatData)
 *   dbRemove(KEY)                   // <-- 删，但不是原子的
 *   sendRequest(...)
 *   ```
 *
 * 缺陷 #3：在 `dbSet` 与 `dbRemove` 之间，若有并发的 `request()` 调用执行
 * `dbGet → push → dbSet`，最后的 `dbRemove` 会**误删**这一批新数据。
 *
 * 公有版修复策略：
 *   - 入队全部走"内存桶 + 持久化镜像"双写；持久化只为冷启续传准备。
 *   - flush() 走一次"原子 swap"：把当前桶交换给空对象，立刻清持久化镜像；
 *     在 swap 之后插入的新事件落到新桶，绝不被 flush 误删。
 *   - flush() 仅返回快照，**不直接发送**：发送由 collector 负责，便于解耦
 *     单测与运行时（collector 不需要 mock 通道）。
 *
 * 数据形态：
 *   - bucket: `Record<lt, StatData[]>`，与私有版 `uniStatData` 兼容。
 *   - 持久化 key：`UNI_STAT_DATA:<appid>:queue`。
 */
const STORAGE_KEY$1 = 'queue';
const DEFAULT_SINGLE_EVENT_MAX_BYTES = SINGLE_EVENT_MAX_BYTES;
const state = {
  bucket: {},
  lastFlushAt: 0
};
let intervalSec = REPORT_INTERVAL_SEC;
let singleEventMaxBytes = DEFAULT_SINGLE_EVENT_MAX_BYTES;
let maxEvents = QUEUE_MAX_EVENTS;
let restored = false;
/** 容量超限 warn 节流：持续离线积压时仅首次告警，回落到上限内后复位。 */
let capacityWarned = false;
/**
 * 配置上报间隔；运行时可在 runtime/StatApp 初始化时注入。
 */
function configure(opts) {
  if (typeof opts.intervalSec === 'number' && opts.intervalSec >= 0) {
    intervalSec = Math.floor(opts.intervalSec);
  }
  if (typeof opts.singleEventMaxBytes === 'number' && opts.singleEventMaxBytes > 0) {
    singleEventMaxBytes = Math.floor(opts.singleEventMaxBytes);
  }
  if (typeof opts.maxEvents === 'number' && opts.maxEvents > 0) {
    maxEvents = Math.floor(opts.maxEvents);
  }
}
/**
 * 强制把内存桶事件总数压到 `maxEvents` 以内（FIFO 丢弃最旧）。
 *
 * 丢弃策略：每轮从**当前事件数最多的桶**头部移除一条（最旧），直到总数达标。
 * 这样长期离线时疯涨的 lt=21/lt=31 会先被裁剪，体量通常很小的 lt=1（会话锚点）/
 * lt=3（后台闭合）更可能被保留。仅在超限时打一次 warn，避免刷屏。
 */
function enforceCapacity() {
  let total = size();
  if (total <= maxEvents) {
    // 回落到上限内 → 复位告警节流，下次再超限时可再次提示。
    capacityWarned = false;
    return;
  }
  const dropped = total - maxEvents;
  while (total > maxEvents) {
    let largestLt = '';
    let largestLen = 0;
    for (const lt of Object.keys(state.bucket)) {
      const len = state.bucket[lt].length;
      if (len > largestLen) {
        largestLen = len;
        largestLt = lt;
      }
    }
    if (!largestLt || largestLen === 0) break;
    state.bucket[largestLt].shift();
    if (state.bucket[largestLt].length === 0) delete state.bucket[largestLt];
    total--;
  }
  // 节流：持续离线积压时每次 enqueue 都会触发裁剪，但仅首次告警，避免刷屏。
  if (!capacityWarned) {
    capacityWarned = true;
    logger.warn('[uni统计 2.0] 上报队列超过容量上限，已丢弃最旧事件', 'dropped=' + dropped, 'limit=' + maxEvents);
  }
}
/**
 * 持久化当前内存桶。失败仅打日志，不影响主流程。
 */
function persistBucket() {
  if (Object.keys(state.bucket).length === 0) {
    storage.remove(STORAGE_KEY$1);
    return;
  }
  try {
    storage.set(STORAGE_KEY$1, state.bucket);
  } catch (e) {
    logger.warn('[uni统计 2.0] queue persist failed', e);
  }
}
/**
 * 冷启时尝试从 storage 恢复上一次进程未上报的桶；只在第一次入队前执行一次。
 *
 * 若 storage 中存在合法的桶数据，与当前内存桶**合并**而不是覆盖（合并语义防止极端
 * 边界场景下丢失冷启已入队的事件）。
 */
function restoreOnce() {
  if (restored) return;
  restored = true;
  const raw = storage.safeRead(STORAGE_KEY$1);
  if (!raw.ok || !raw.value || typeof raw.value !== 'object') return;
  const persisted = raw.value;
  for (const lt of Object.keys(persisted)) {
    const arr = persisted[lt];
    if (!Array.isArray(arr) || arr.length === 0) continue;
    if (!state.bucket[lt]) state.bucket[lt] = [];
    state.bucket[lt].push(...arr);
  }
}
/**
 * 把一条事件入队到对应 lt 的桶。
 *
 * 不抛错；data.lt 必填，缺失/类型异常时打日志丢弃。
 *
 * 单条体积保护：序列化后超过 `singleEventMaxBytes`（默认 2KB）的事件直接丢弃 ——
 * 进了桶最终一定打不出去（无论怎么切片都会顶满 GET URL），还会污染 retry 队列。
 * 典型源头：业务方在 `key/value` 里塞了 base64 图片 / 大段 JSON / 长 stack 等。
 */
function enqueue(data) {
  var _a;
  if (!data || typeof data !== 'object') return;
  const lt = String((_a = data.lt) !== null && _a !== void 0 ? _a : '');
  if (!lt) {
    logger.warn('[uni统计 2.0] enqueue dropped: missing lt', data);
    return;
  }
  let serialized = '';
  try {
    serialized = JSON.stringify(data);
  } catch (e) {
    logger.warn('[uni统计 2.0] enqueue dropped: stringify failed', e);
    return;
  }
  if (serialized.length > singleEventMaxBytes) {
    logger.warn('[uni统计 2.0] enqueue dropped: single event too large', 'lt=' + lt, 'bytes=' + serialized.length, 'limit=' + singleEventMaxBytes);
    return;
  }
  restoreOnce();
  if (!state.bucket[lt]) state.bucket[lt] = [];
  state.bucket[lt].push(data);
  enforceCapacity();
  persistBucket();
}
/**
 * 是否到达 flush 阈值。
 *
 * @param force 如为 true 直接返回 true（用于 onAppHide / 错误兜底等场景）。
 */
function shouldFlush(force = false) {
  if (force) return true;
  if (intervalSec <= 0) return true;
  const elapsedSec = (nowMs() - state.lastFlushAt) / 1000;
  return elapsedSec >= intervalSec;
}
/**
 * 原子取出当前桶并清空（修复缺陷 #3）。
 *
 * 调用时机：由 collector 决定（间隔触发 / app hide / 强制刷新）。
 *
 * @returns 取出的桶；若空桶返回 undefined（调用方据此跳过本次发送）。
 */
function flush() {
  restoreOnce();
  const lts = Object.keys(state.bucket);
  if (lts.length === 0) return undefined;
  const snapshot = state.bucket;
  state.bucket = {};
  state.lastFlushAt = nowMs();
  storage.remove(STORAGE_KEY$1);
  return snapshot;
}
/**
 * 发送失败回滚：把 flush 取出的快照重新合并回当前桶，等待下一次 flush。
 *
 * 注意：合并时插入到桶的"前面"，保留 FIFO 语义。
 */
function rollback(snapshot) {
  if (!snapshot) return;
  for (const lt of Object.keys(snapshot)) {
    const arr = snapshot[lt];
    if (!Array.isArray(arr) || arr.length === 0) continue;
    if (!state.bucket[lt]) state.bucket[lt] = [];
    state.bucket[lt] = arr.concat(state.bucket[lt]);
  }
  enforceCapacity();
  persistBucket();
}
/**
 * 当前桶内事件总数（按 lt 加总）。
 */
function size() {
  let n = 0;
  for (const lt of Object.keys(state.bucket)) {
    n += state.bucket[lt].length;
  }
  return n;
}

/**
 * 失败重试落盘队列。
 *
 * 设计动机：
 *   - 私有版仅在 1.0 通道内做了 3 次内存级重试；进程被杀（应用退出 / kill）后所有
 *     未上报数据**直接丢失**，且 2.0 通道根本没有重试。
 *   - 公有版引入"内存重试 + 失败落盘 + 下次冷启重放"双层兜底：
 *       通道层：`channel.send` 内部已用 `withRetry` 做协议层重试。
 *       本模块：协议层最终失败后调用 `persist(payload)` 写入 storage；
 *               冷启时调 `loadAll()` 取出，逐条尝试重放，成功后 `ack(_id)` 删除。
 *
 * 数据结构：
 *   `UNI_STAT_DATA:<appid>:retry:queue`：`Array<RetryItem>`，最多 `maxItems` 条；
 *   超容时按 FIFO 丢弃最旧条目。每条带创建时间戳，超过 `maxAgeMs` 的过期清理。
 *
 * 与 retry 队列只存"已序列化的 ReportPayload"——不再依赖 collector / domain，
 * 由调用方负责重组业务字段（如重试时不需要再次重算 visit/session）。
 */
const STORAGE_KEY = 'retry:queue';
const DEFAULT_MAX_ITEMS = 50;
const DEFAULT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const DEFAULT_MAX_ATTEMPTS = RETRY_MAX_ATTEMPTS;
const config = {
  maxItems: DEFAULT_MAX_ITEMS,
  maxAgeMs: DEFAULT_MAX_AGE_MS,
  maxAttempts: DEFAULT_MAX_ATTEMPTS
};
/**
 * 读取队列。出现异常或非数组时返回空数组（不影响主流程）。
 */
function readQueue() {
  const raw = storage.safeRead(STORAGE_KEY);
  if (!raw.ok || !Array.isArray(raw.value)) return [];
  return raw.value.filter(it => it && typeof it.id === 'string' && it.payload && typeof it.payload === 'object');
}
/**
 * 写回队列。空数组时直接 remove，避免存储垃圾。
 */
function writeQueue(items) {
  if (items.length === 0) {
    storage.remove(STORAGE_KEY);
    return;
  }
  storage.set(STORAGE_KEY, items);
}
/**
 * 生成 retry item id。优先复用 payload._id（来自 queue 出栈时分配的批次 id）。
 */
function genId(payload) {
  if (payload._id) return payload._id;
  return 'r-' + nowMs().toString(36) + '-' + Math.random().toString(36).slice(2, 6);
}
/**
 * 持久化一条失败 payload。
 *
 * @param payload 协议层最终失败的 payload。
 * @returns 实际写入的 retry id；若被丢弃返回 undefined。
 */
function persist(payload) {
  if (!payload) return undefined;
  const id = genId(payload);
  const items = readQueue();
  if (items.some(it => it.id === id)) {
    return id;
  }
  const item = {
    id,
    payload: Object.assign({}, payload, {
      _id: id
    }),
    createdAt: nowMs(),
    attempts: 0
  };
  items.push(item);
  while (items.length > config.maxItems) {
    const dropped = items.shift();
    logger.warn('[uni统计 2.0] retry queue overflow, drop oldest', dropped === null || dropped === void 0 ? void 0 : dropped.id);
  }
  writeQueue(items);
  return id;
}
/**
 * 取出全部待重试条目（同时清理过期项），按入队顺序返回。
 *
 * 调用方应自行决定是否串行重放；本模块**不**自动触发任何网络。
 */
function loadAll() {
  const items = readQueue();
  if (items.length === 0) return [];
  const cutoff = nowMs() - config.maxAgeMs;
  const alive = [];
  for (const it of items) {
    if (it.createdAt < cutoff) {
      logger.warn('[uni统计 2.0] retry item expired, drop', it.id);
      continue;
    }
    alive.push(it);
  }
  if (alive.length !== items.length) writeQueue(alive);
  return alive.map(it => it.payload);
}
/**
 * 重放成功后删除指定 id；id 不存在视为 no-op。
 */
function ack(id) {
  if (!id) return;
  const items = readQueue();
  const next = items.filter(it => it.id !== id);
  if (next.length === items.length) return;
  writeQueue(next);
}
/**
 * 标记一次重放失败：累加 `attempts`，超过 `config.maxAttempts` 自动死信清理。
 *
 * 死信清理动机：`recoverRetry` 串行重放，永久错误（脏 payload / 历史协议数据）若不
 * 主动丢弃，会反复占据队列前部，把后续健康 payload 也拖到失败 —— 这是 image url too
 * long 看似"重试无穷大"的次因。本兜底与"过期清理（maxAgeMs）+ 容量裁剪（maxItems）"
 * 形成三道防线。
 */
function markAttempt(id) {
  if (!id) return;
  const items = readQueue();
  let nextItems = null;
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    if (it.id !== id) continue;
    it.attempts++;
    if (it.attempts >= config.maxAttempts) {
      logger.warn('[uni统计 2.0] retry item exceeded maxAttempts, drop as dead letter', id, 'attempts=' + it.attempts);
      nextItems = items.slice(0, i).concat(items.slice(i + 1));
    } else {
      nextItems = items;
    }
    break;
  }
  if (nextItems) writeQueue(nextItems);
}

/**
 * 公有版统计运行时门面（单例）。
 *
 * 职责：
 *   1. `install(config?, overrides?)`：一次性装配 collector / channel / 拦截器；
 *      启动时 `migrateLegacyData` → `loadVisitSnapshot` → `recoverRetry`。
 *      重复 install 幂等。
 *   2. `report(type, value)`：业务侧 `uni.report(type, value)` 的承接入口。
 *   3. `reportError(e)`：错误兜底事件（lt=31）。
 *   4. `getCollector()` / `getDeps()`：测试与 lifecycleHooks 复用。
 *
 * 设计原则：
 *   - 所有 adapter 调用都包了 `tryRun`，单端缺失 API 不影响 install。
 *   - 所有依赖通过 `defaults + overrides` 构造；测试可注入替换。
 *   - install 不抛错；任何子步骤失败都吞掉并 logger.warn。
 *   - 单例：`StatApp.getInstance()` 全局唯一；`__resetStatApp()` 仅供测试。
 */
let instance = null;
class StatApp {
  constructor() {
    /** install 幂等哨兵。 */
    this.installed = false;
    /** 已生效的协议版本（'1' / '2' / 'image'）。 */
    this.statVersion = 'image';
  }
  static getInstance() {
    if (!instance) instance = new StatApp();
    return instance;
  }
  /**
   * 一次性装配。重复调用直接返回。
   *
   * @param config 业务配置；缺省值兼容私有版默认行为。
   * @param overrides 测试钩子。
   */
  install(config = {}, overrides = {}) {
    var _a, _b, _c, _d, _e;
    if (this.installed) return;
    const cfg = this.normalizeConfig(config);
    this.config = cfg;
    this.statVersion = cfg.version;
    tryRun(() => configure$1({
      backgroundTimeoutSec: cfg.backgroundTimeoutSec,
      pageInactiveTimeoutSec: cfg.pageInactiveTimeoutSec
    }), undefined);
    tryRun(() => configure({
      intervalSec: cfg.reportIntervalSec
    }), undefined);
    if (!overrides.skipMigration) {
      tryRun(() => migrateLegacyData(), false);
    }
    tryRun(() => loadVisitSnapshot(), undefined);
    this.httpChannel = (_b = (_a = overrides.channels) === null || _a === void 0 ? void 0 : _a.http) !== null && _b !== void 0 ? _b : createHttpChannel({
      ut: getPlatform(),
      maxRetries: HTTP_MAX_RETRIES
    });
    // cloud：仅在用户明确选择 channelVersion=2 或测试 override 时构造，
    // 公有版默认路径不会创建 cloud，避免触发"cloud channel unavailable"误降级警告。
    if (overrides.channels && 'cloud' in overrides.channels) {
      this.cloudChannel = (_c = overrides.channels.cloud) !== null && _c !== void 0 ? _c : undefined;
    } else if (this.statVersion === '2') {
      this.cloudChannel = createCloudChannel({
        maxRetries: CLOUD_MAX_RETRIES
      });
    } else {
      this.cloudChannel = undefined;
    }
    // image：公有版默认通道。host/projectId/topicId 来自 config.IMAGE_REPORT_DEFAULTS，
    // 由 SDK 维护者直接在源码中调整，**不暴露**到 manifest / runtime API；
    // 测试场景仍可通过 overrides.channels.image 注入伪通道做断言。
    if (overrides.channels && 'image' in overrides.channels) {
      this.imageChannel = (_d = overrides.channels.image) !== null && _d !== void 0 ? _d : undefined;
    } else if (this.statVersion === 'image') {
      this.imageChannel = createImageChannel({
        host: IMAGE_REPORT_DEFAULTS.host,
        projectId: IMAGE_REPORT_DEFAULTS.projectId,
        topicId: IMAGE_REPORT_DEFAULTS.topicId,
        maxRetries: IMAGE_MAX_RETRIES,
        ut: getPlatform(),
        rawPlatform: getRawPlatform()
      });
    } else {
      this.imageChannel = undefined;
    }
    this.collectorDeps = this.buildCollectorDeps(cfg, (_e = overrides.collectorDepsPatch) !== null && _e !== void 0 ? _e : {});
    this.collector = createCollector(this.collectorDeps);
    if (!overrides.skipInterceptors) {
      const c = this.collector;
      this.uninstallInterceptors = tryRun(() => installAllInterceptors({
        report: i => c.report(i)
      }), undefined);
    }
    if (!overrides.skipRecoverRetry) {
      void this.collector.recoverRetry().catch(e => logger.warn('[uni统计 2.0] recoverRetry failed', e));
    }
    // 公有版：监听网络恢复，立即续传 + 强制 flush（与私有版 core 实现分离）
    this.uninstallNetworkWatch = tryRun(() => onNetworkOnline(() => {
      const c = this.collector;
      if (!c) return;
      void c.recoverRetry().catch(e => logger.warn('[uni统计 2.0] recoverRetry on online failed', e));
      void c.flush(true).catch(e => logger.warn('[uni统计 2.0] flush on online failed', e));
    }), undefined);
    // 仅在 collector 与拦截器等就绪后再标记，避免中途抛错导致「已 install 却无 collector」。
    this.installed = true;
  }
  /**
   * 业务侧 `uni.report(type, value)` 入口。
   *
   * 兼容私有版语义：
   *   - `type === 'title'` → 写 reportTitle，不发事件；下次 lt=11 / lt=3 携带 `ttc`。
   *   - 其他 type → 自定义事件 lt=21，custom `{ e_n: type, e_v: value }`。
   */
  report(type, value) {
    if (!this.installed || !this.collector) return;
    if (type === 'title') {
      setReportTitle(value);
      return;
    }
    const ev = typeof value === 'object' && value !== null ? tryRun(() => JSON.stringify(value), '') : value === undefined ? '' : String(value);
    this.collector.report({
      lt: LT.Event,
      custom: {
        e_n: type,
        e_v: ev
      }
    });
  }
  /** 上报 onError 捕获的错误。 */
  reportError(err) {
    var _a;
    if (!this.installed || !this.collector) return;
    const errMsg = err instanceof Error ? `${err.name}: ${err.message}\n${(_a = err.stack) !== null && _a !== void 0 ? _a : ''}` : typeof err === 'string' ? err : tryRun(() => JSON.stringify(err), '');
    this.collector.report({
      lt: LT.Error,
      errMsg
    });
  }
  /** 取 collector，供 lifecycleHooks 调度生命周期事件。 */
  getCollector() {
    return this.collector;
  }
  /** 取 deps（测试用）。 */
  getDeps() {
    return this.collectorDeps;
  }
  /** 是否已 install。 */
  isInstalled() {
    return this.installed;
  }
  /** 当前协议版本。 */
  getStatVersion() {
    return this.statVersion;
  }
  /** 当前生效配置（含默认值合并），测试用。 */
  getConfig() {
    return this.config;
  }
  /**
   * 卸载（测试 / hot reload）。
   *
   * 解绑全部拦截器、清空内部句柄。**不**清外部模块（queue/visit/session）状态，
   * 那些由各自的 `__reset*` 在测试 setup 中处理。
   */
  uninstall() {
    if (this.uninstallInterceptors) {
      tryRun(() => this.uninstallInterceptors(), undefined);
    }
    this.uninstallInterceptors = undefined;
    if (this.uninstallNetworkWatch) {
      tryRun(() => this.uninstallNetworkWatch(), undefined);
    }
    this.uninstallNetworkWatch = undefined;
    // 先释放 collector 内部定时器（取消延迟首 flush），再丢弃引用，避免幽灵 flush。
    if (this.collector) {
      tryRun(() => this.collector.destroy(), undefined);
    }
    this.collector = undefined;
    this.collectorDeps = undefined;
    this.httpChannel = undefined;
    this.cloudChannel = undefined;
    this.imageChannel = undefined;
    this.config = undefined;
    this.installed = false;
  }
  /**
   * 解析上行渠道字段 `ch`。
   *
   * App 渠道包标识只能以原生运行时为准：`plus.runtime.channel`。
   * `manifest.uniStatistics.ch` 是静态配置，不能区分同一项目打出的多渠道包。
   * 非 App 端没有 `plus.runtime.channel` 语义，保留手动 install 传入 `ch` 的能力。
   */
  resolveChannel(explicit) {
    if (isApp()) {
      return getAppChannel();
    }
    if (typeof explicit === 'string' && explicit.length > 0) {
      return explicit;
    }
    return '';
  }
  resolveFirstFlushDeferMs() {
    if (getRawPlatform() === 'mp-weixin' && MP_WEIXIN_USE_PRELOAD_ASSETS_REPORT) {
      return MP_WEIXIN_PRELOAD_FIRST_FLUSH_DELAY_MS;
    }
    if (isApp() && !getAppChannel()) {
      return APP_CHANNEL_FIRST_FLUSH_DELAY_MS;
    }
    return 0;
  }
  normalizeConfig(c) {
    var _a, _b, _c, _d;
    return {
      ak: (_a = c.ak) !== null && _a !== void 0 ? _a : getAppId$1(),
      v: c.v,
      ch: this.resolveChannel(c.ch),
      version: (_b = c.version) !== null && _b !== void 0 ? _b : 'image',
      backgroundTimeoutSec: (_c = c.backgroundTimeoutSec) !== null && _c !== void 0 ? _c : 300,
      pageInactiveTimeoutSec: (_d = c.pageInactiveTimeoutSec) !== null && _d !== void 0 ? _d : 1800,
      reportIntervalSec: typeof c.reportIntervalSec === 'number' ? c.reportIntervalSec : REPORT_INTERVAL_SEC,
      // collectItems 默认值与私有版严格对齐：push 默认关闭、页面日志默认开启
      enablePush: c.enablePush === true,
      enablePageLog: c.enablePageLog !== false
    };
  }
  /**
   * 构建 collector 依赖。所有 adapter 调用都包了 `tryRun`，避免单端缺失 API 导致
   * install 失败。
   */
  buildCollectorDeps(cfg, patch) {
    const platformShort = getPlatform();
    const builder = createStatDataBuilder({
      config: {
        ak: cfg.ak,
        usv: STAT_VERSION_PUBLIC,
        v: cfg.v,
        get ch() {
          return isApp() ? getAppChannel() : cfg.ch;
        }
      },
      platform: {
        ut: platformShort
      },
      system: tryRun(() => getSystemInfo(), {
        brand: '',
        md: '',
        sv: '',
        v: '',
        ut: 'unknown',
        appVersion: '',
        appWgtVersion: '',
        mpvHostVersion: '',
        on: '',
        sdkVersion: '',
        statusBarHeight: 0,
        osP: ''
      }),
      locale: tryRun(() => getLocaleAndScreen(), {
        lang: '',
        ww: 0,
        wh: 0,
        sw: 0,
        sh: 0,
        pr: 1
      }),
      device: {
        // 惰性解析：每次 build 时再调 getUuid()，避免 install 过早（uni 运行时未就绪）冻结临时值。
        get uuid() {
          return tryRun(() => getUuid(), '');
        }
      },
      net: {
        net: 'unknown',
        raw: ''
      },
      location: {
        lat: '',
        lng: '',
        ok: false
      },
      pkg: tryRun(() => getPackageInfo(), {
        mpn: '',
        tdaid: '',
        pkn: '',
        an: ''
      }),
      web: tryRun(() => getWebInfo(), {
        domain: ''
      })
    });
    const base = {
      builder,
      queue: {
        enqueue: enqueue,
        flush: flush,
        rollback: rollback,
        shouldFlush: shouldFlush
      },
      serializer: {
        handleData
      },
      selectChannel: () => selectChannel({
        version: this.statVersion,
        http: this.httpChannel,
        cloud: this.cloudChannel,
        image: this.imageChannel
      }),
      retry: {
        persist: persist,
        loadAll: loadAll,
        ack: ack,
        markAttempt: markAttempt
      },
      visit: {
        commitVisitOnAck: commitVisitOnAck,
        rollbackPendingVisit: rollbackPendingVisit
      },
      session: {
        getSnapshot: getSnapshot,
        nextSeq: nextSeq,
        touch: touch
      },
      config: {
        usv: STAT_VERSION_PUBLIC
      },
      resolveUploadFields: () => {
        const ch = getAppChannel();
        return ch ? {
          ch
        } : {};
      },
      nowMs,
      nowSec,
      firstFlushDeferMs: this.resolveFirstFlushDeferMs(),
      isNetworkOffline
    };
    return Object.assign(base, patch);
  }
}
/**
 * 便捷 API：获取或创建当前应用 collector，供拦截器 / lifecycleHooks 使用。
 *
 * 上层若希望直接拿 lt 入参，可先 `getStatApp().install(cfg)`，再
 * `getStatApp().getCollector()?.report({ lt, ... })`。
 */
function getStatApp() {
  return StatApp.getInstance();
}
/** 仅供测试：销毁全局单例与 install 状态（不会重置 queue/visit/session）。 */
function __resetStatApp() {
  if (instance) {
    instance.uninstall();
    instance = null;
  }
}

/**
 * 公有版统计运行时安装入口。
 *
 * 与私有版 `src/index.js#load_stat` 等价：
 *   - VUE3 走 `uni.onCreateVueApp(app => app.mixin(lifecycle))`。
 *   - VUE2 走 `Vue.mixin(lifecycle)`（require('vue')）。
 *   - 同时把 `uni.report = (type, value) => StatApp.report(type, value)` 暴露给业务。
 *
 * 与私有版差异：
 *   - 模块加载即调 `installPublicStat()`，但内部用 install 哨兵保证幂等；
 *     测试可调 `__resetStatApp()` 重置。
 *   - `is_debug / NODE_ENV === 'development'` 的开关由调用方在 build 阶段做（
 *     `plugin/index.ts` 已注入），运行时不再分支。
 *
 * 暴露：
 *   - `installPublicStat(config?, opts?)`：手动触发；幂等。
 *   - `getMixin()`：返回 vue mixin 对象，供宿主自行 `app.mixin(...)`。
 */
/**
 * 从 `process.env.UNI_STATISTICS_CONFIG`（plugin 注入的 manifest.uniStatistics 序列化串）
 * 读取业务配置，把已知行为字段映射为 StatApp.install 的 partial config。
 *
 * ## 字段命名严格对齐私有版
 *
 * uni-app 私有版（`src/utils/pageInfo.js`）历史已对外暴露的 manifest 字段：
 *
 *   | manifest 字段                          | 类型     | 默认值 | 私有版语义                       |
 *   | -------------------------------------- | -------- | ------ | -------------------------------- |
 *   | `enable`                               | Boolean  | false  | 总开关，由 plugin 处理           |
 *   | `version`                              | String   | "1"    | "1" / "2" / "3"（公有版新增）    |
 *   | `debug`                                | Boolean  | false  | logger.debug 开关                |
 *   | `reportInterval`                       | Number   | 10     | 上报间隔秒数；0 = 立即上报       |
 *   | `collectItems.uniPushClientID`         | Boolean  | false  | 是否采集 push ClientID（lt=101） |
 *   | `collectItems.uniStatPageLog`          | Boolean  | true   | 是否上报页面日志（lt=11）        |
 *
 * 公有版**新增**字段（私有版不支持）：
 *
 *   | manifest 字段             | 类型    | 默认值 | 说明                                                   |
 *   | ------------------------- | ------- | ------ | ------------------------------------------------------ |
 *   | `backgroundTimeout`       | Number  | 300    | 后台返回前台超过此秒数视为新会话（cst=2）              |
 *   | `pageInactiveTimeout`     | Number  | 1800   | 前台连续无操作超过此秒数视为新会话（cst=3）            |
 *   | `channelVersion`          | String  | image  | 内部调试：`image` / `1` / `2`，业务方一般不需要设置   |
 *
 * ## 别名兼容
 *
 * 公有版早期内部测试用了带 `Sec` 后缀的命名（`reportIntervalSec / backgroundTimeoutSec /
 * pageInactiveTimeoutSec`），未对外发布但已在示例中出现过；本函数同时接受这两套写法，
 * **优先取私有版命名**（无后缀），别名仅作向后兼容。
 *
 * ## 上行身份字段不从 manifest 读取
 *
 * `ak / v / ch` 均有更可信的数据源：`ak` 取构建期应用 AppID，`v` 取运行时版本，
 * App 端 `ch` 取 `plus.runtime.channel`。这些字段不应由
 * `manifest.uniStatistics` 静态覆盖，尤其多渠道包会因此被固定到默认渠道。
 *
 * ## 内部接入参数不可自定义
 *
 * image 通道的 `host / projectId / topicId` 是 SDK 内部接入参数，由维护者直接在
 * `public/config.ts#IMAGE_REPORT_DEFAULTS` 中维护，**不**通过 manifest 暴露给业务方。
 *
 * 任意 JSON 解析 / 字段类型异常都吞掉，回到默认值；此处**不能**抛错，否则会阻塞自动 install。
 *
 * ## 必须直接写 `process.env.UNI_STATISTICS_CONFIG`
 *
 * `uni:stat` 插件通过 Vite `define` 在**构建阶段**把字面量 `process.env.UNI_STATISTICS_CONFIG`
 * 替换为 JSON 字符串。若写成 `const env = process.env; env.UNI_STATISTICS_CONFIG`，
 * 打包器无法静态替换，小程序/H5 运行时读到的一直是 `undefined`，manifest 超时等字段全部丢失。
 *
 * ## 禁止 `typeof process !== 'undefined' ? process.env.XXX : …`
 *
 * 微信小程序等运行时**往往没有全局 `process`**。替换后源码等价于
 * `typeof process !== 'undefined' ? "{\"enable\":…}" : undefined`，条件为假时会**整段丢弃**
 * 已内联的 JSON 字符串，表现为 `UNI_STATISTICS_CONFIG_len=0`、会话阈值永远默认。
 * 因此必须**直接**书写 `process.env.UNI_STATISTICS_CONFIG`（无任何 `typeof process` 包裹）。
 */
/**
 * 解析构建期注入的 `UNI_STATISTICS_CONFIG`。
 * 正常为 JSON 字符串；少数打包配置会误注入为对象字面量，此处一并兼容。
 */
function parseInjectedUniStatistics() {
  const raw = {};
  if (raw == null) return undefined;
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    return raw;
  }
  if (typeof raw !== 'string') return undefined;
  const trimmed = raw.trim();
  if (!trimmed || trimmed === 'undefined') return undefined;
  try {
    const obj = JSON.parse(trimmed);
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return undefined;
    return obj;
  } catch (_e) {
    return undefined;
  }
}
function readManifestStatConfig() {
  try {
    const obj = parseInjectedUniStatistics();
    if (!obj) return undefined;
    const cfg = {};
    if (obj.channelVersion != null) {
      const v = String(obj.channelVersion);
      if (v === '1' || v === '2' || v === 'image') cfg.version = v;
    }
    // === 公有版扩展：backgroundTimeout / pageInactiveTimeout（私有版无此字段）===
    // 同时兼容早期内部用的带 Sec 后缀别名；优先无后缀（与官方风格一致）。
    const bg = pickPositiveNumber(obj.backgroundTimeout, obj.backgroundTimeoutSec);
    if (bg !== undefined) cfg.backgroundTimeoutSec = bg;
    const pi = pickPositiveNumber(obj.pageInactiveTimeout, obj.pageInactiveTimeoutSec);
    if (pi !== undefined) cfg.pageInactiveTimeoutSec = pi;
    // === 私有版同名字段：reportInterval（私有版默认 10）===
    // 兼容旧公有版别名 reportIntervalSec；允许 0（私有版语义"立即上报"）。
    const ri = pickNonNegativeNumber(obj.reportInterval, obj.reportIntervalSec);
    if (ri !== undefined) cfg.reportIntervalSec = ri;
    // === 私有版同名字段：collectItems.{uniPushClientID, uniStatPageLog} ===
    if (obj.collectItems && typeof obj.collectItems === 'object') {
      const items = obj.collectItems;
      if (typeof items.uniPushClientID === 'boolean') {
        cfg.enablePush = items.uniPushClientID;
      }
      if (typeof items.uniStatPageLog === 'boolean') {
        cfg.enablePageLog = items.uniStatPageLog;
      }
    }
    return Object.keys(cfg).length > 0 ? cfg : undefined;
  } catch (e) {
    logger.warn('[uni统计 2.0] readManifestStatConfig failed', e);
    return undefined;
  }
}
/**
 * 将 manifest / JSON 中的数值候选标准化为正数（> 0）。
 * 兼容部分工具或手工编辑 manifest 时写成**字符串数字**（如 `"60"`）的情况。
 */
function normalizePositiveNumber(value) {
  if (typeof value === 'number') {
    return value > 0 ? value : undefined;
  }
  if (typeof value === 'string') {
    const t = value.trim();
    if (t === '') return undefined;
    const n = Number(t);
    if (Number.isFinite(n) && n > 0) return n;
  }
  return undefined;
}
/**
 * 将候选标准化为非负数（>= 0），用于 `reportInterval`。
 */
function normalizeNonNegativeNumber(value) {
  if (typeof value === 'number') {
    return value >= 0 ? value : undefined;
  }
  if (typeof value === 'string') {
    const t = value.trim();
    if (t === '') return undefined;
    const n = Number(t);
    if (Number.isFinite(n) && n >= 0) return n;
  }
  return undefined;
}
/**
 * 在多个候选值中按顺序取**第一个有效的正数**（> 0），其余忽略。
 * 用于 manifest 字段的"主名 / 别名"二选一解析（如 `backgroundTimeout` / `backgroundTimeoutSec`）。
 *
 * 注意：私有版历史允许 `0` 表示"立即上报"，但仅 `reportInterval` 一项有此语义；
 * timeout 类字段 0 表示"立即超时"，不合理，本函数统一过滤为 undefined。
 */
function pickPositiveNumber(...candidates) {
  for (const c of candidates) {
    const n = normalizePositiveNumber(c);
    if (n !== undefined) return n;
  }
  return undefined;
}
/**
 * 同 `pickPositiveNumber`，但允许 `0`（用于 `reportInterval` 表达"立即上报"语义）。
 */
function pickNonNegativeNumber(...candidates) {
  for (const c of candidates) {
    const n = normalizeNonNegativeNumber(c);
    if (n !== undefined) return n;
  }
  return undefined;
}
function getUni() {
  const u = resolveUniRuntime();
  return u != null && typeof u === 'object' ? u : undefined;
}
/** Vue3 下晚就绪 API 重试次数（50ms 间隔，约 1s）。 */
const UNI_HOOK_RETRY_MAX = 20;
const UNI_HOOK_RETRY_MS = 50;
/** 已排队或已执行的 vue mixin 注入，避免重复。 */
let vueMixinMounted = false;
let vueMixinRetryTimer;
/** install 是否已经触发过（不论成功失败）。 */
let bootstrapped = false;
/** 已注册到全局的 unbind，便于 __reset。 */
let lastUnbind;
/** 晚就绪时重试 `uni.onAppShow` 的定时器。 */
let uniHookRetryTimer;
/**
 * 入口装配。重复调用时立即返回。
 *
 * 失败任意子步骤都吞掉日志，不抛回。
 */
function installPublicStat(opts = {}) {
  if (bootstrapped) return;
  bootstrapped = true;
  // 优先级：opts.config（手动覆盖） > manifest.uniStatistics（plugin 注入） > 默认值。
  // 这样业务/灰度同学既能在 manifest 里改超时阈值（生产路径），
  // 也能用 installPublicStat({ config: {...} }) 在测试环境强行覆盖（接入调试）。
  // 注意：manifest 仅解析行为配置，不解析 ak/v/ch；App 渠道始终由 plus.runtime.channel 决定。
  const fromManifest = readManifestStatConfig();
  const finalConfig = Object.assign({}, fromManifest, opts.config);
  const app = getStatApp();
  tryRun(() => app.install(finalConfig, opts.overrides), undefined);
  // 启动摘要：与生命周期解耦，保证 StatApp.install 完成后立刻可打印（不依赖 uni 是否已挂载）。
  tryRun(() => {
    var _a, _b, _c;
    const cfgBoot = app.getConfig();
    const appName = "商城" || false;
    const injected = parseInjectedUniStatistics();
    const bootBase = {
      channel: (_a = cfgBoot === null || cfgBoot === void 0 ? void 0 : cfgBoot.version) !== null && _a !== void 0 ? _a : 'image',
      reportIntervalSec: (_b = cfgBoot === null || cfgBoot === void 0 ? void 0 : cfgBoot.reportIntervalSec) !== null && _b !== void 0 ? _b : 0,
      ak: (_c = cfgBoot === null || cfgBoot === void 0 ? void 0 : cfgBoot.ak) !== null && _c !== void 0 ? _c : '',
      appName,
      debugFromManifest: false === 'true' || false === true
    };
    // 仅当 manifest 显式配置了超时项时才在 debug 启动摘要中展示（默认值 300/1800 不刷屏）。
    if (injected != null) {
      if (injected.backgroundTimeout != null || injected.backgroundTimeoutSec != null) {
        bootBase.backgroundTimeoutSec = cfgBoot === null || cfgBoot === void 0 ? void 0 : cfgBoot.backgroundTimeoutSec;
      }
      if (injected.pageInactiveTimeout != null || injected.pageInactiveTimeoutSec != null) {
        bootBase.pageInactiveTimeoutSec = cfgBoot === null || cfgBoot === void 0 ? void 0 : cfgBoot.pageInactiveTimeoutSec;
      }
    }
    logBoot(Object.assign({}, bootBase, {
      vueMode: 'Vue2'
    }));
  }, undefined);
  /**
   * 装配 vue mixin 与 uni 生命周期；与 logBoot 解耦，便于在 uni 晚就绪时延后执行。
   */
  const finishLifecycleInstall = () => {
    var _a, _b;
    // 把 collectItems 的开关透传给 lifecycleHooks：
    //   - uniPushClientID → enablePush（决定是否抓取 push CID 上报 lt=101）
    //   - uniStatPageLog  → enablePageLog（决定是否上报 lt=11 页面切换事件）
    // 调用方通过 opts.lifecycle 显式传入的值优先级最高，未指定时用 manifest 默认。
    const cfg = app.getConfig();
    const lifecycleOpts = Object.assign({}, {
      enablePush: (_a = cfg === null || cfg === void 0 ? void 0 : cfg.enablePush) !== null && _a !== void 0 ? _a : false,
      enablePageLog: (_b = cfg === null || cfg === void 0 ? void 0 : cfg.enablePageLog) !== null && _b !== void 0 ? _b : true
    }, opts.lifecycle);
    const {
      mixin,
      unbind
    } = bindLifecycle(app, lifecycleOpts);
    lastUnbind = unbind;
    // 与私有版 load_stat 一致：同步注入 mixin，不等待 uni.onAppShow（Vue2 根本不注册该项）。
    if (!opts.skipVueMixin) {
      tryRun(() => mountVueMixin(mixin), undefined);
    }
    if (!opts.skipUniReport) {
      tryRun(() => mountUniReport(app), undefined);
    }
    // 私有版：仅 Vue3 且非 H5/nvue 注册 uni 应用前后台。
    if (shouldBindUniAppLifecycle() && !tryBindUniAppLifecycle(app, lifecycleOpts)) {
      scheduleUniAppHookRetry(() => tryBindUniAppLifecycle(app, lifecycleOpts));
    }
  };
  finishLifecycleInstall();
}
/**
 * 仅 Vue3 小程序等重试 `uni.onAppShow` / `onAppHide`；Vue2 不调用。
 */
function scheduleUniAppHookRetry(tryBind) {
  if (uniHookRetryTimer) {
    clearTimeout(uniHookRetryTimer);
    uniHookRetryTimer = undefined;
  }
  let attempts = 0;
  const tick = () => {
    if (tryBind()) return;
    if (++attempts >= UNI_HOOK_RETRY_MAX) {
      logger.warn('[uni统计 2.0] Vue3 小程序：uni.onAppShow 暂不可用，应用前后台统计可能缺失');
      return;
    }
    uniHookRetryTimer = setTimeout(tick, UNI_HOOK_RETRY_MS);
  };
  uniHookRetryTimer = setTimeout(tick, UNI_HOOK_RETRY_MS);
}
/**
 * 把 mixin 装到 vue 实例上。
 *
 * 与私有版 `src/index.js#load_stat` 一致，必须用条件编译区分：
 *   - VUE3：`uni.onCreateVueApp` → `app.mixin`（与私有版相同，不引 `@dcloudio/uni-shared`）。
 *   - VUE2：`require('vue').mixin`（由应用打包器静态解析，勿用 `globalThis.require`）。
 *
 * `#ifdef` 保留到 dist，由宿主 `uni:pre` 在打包阶段剔除分支（同私有版 dist）。
 */

function mountVueMixin(mixin) {
  if (vueMixinMounted) return;
  if (mountVue2GlobalMixin(mixin)) {
    vueMixinMounted = true;
  }
}

/**
 * Vue2 全局 mixin（与私有版 `index.js` 中 `require('vue').mixin` 一致）。
 *
 * @returns 是否注入成功
 */
function mountVue2GlobalMixin(mixin) {
  var _a;
  // eslint-disable-next-line no-restricted-globals
  const Vue = __webpack_require__(/*! vue */ 5);
  const target = (_a = Vue.default) !== null && _a !== void 0 ? _a : Vue;
  if (target && typeof target.mixin === 'function') {
    tryRun(() => target.mixin(mixin), undefined);
    return true;
  }
  logger.warn('[uni统计 2.0] Vue2: vue.mixin 不可用，请检查是否已安装 vue 依赖');
  return false;
}
/**
 * 把 `uni.report` 桥到 StatApp.report。
 *
 * H5 发行摇树时 `resolveUniRuntime` 会跳过 `{}` 空桩，但业务仍可能通过
 * `window.uni.report` 调用；故在可用 runtime 缺失时回退 `getGlobalObject().uni`。
 */
function mountUniReport(app) {
  var _a;
  const g = getGlobalObject();
  const u = (_a = getUni()) !== null && _a !== void 0 ? _a : g.uni;
  if (!u || typeof u !== 'object') return;
  u.report = (type, value) => {
    app.report(type, value);
  };
}
/** 仅供测试：重置 install 哨兵；调用方应同时调 `__resetStatApp()`。 */
function __resetInstall() {
  if (uniHookRetryTimer) {
    clearTimeout(uniHookRetryTimer);
    uniHookRetryTimer = undefined;
  }
  if (vueMixinRetryTimer) {
    clearTimeout(vueMixinRetryTimer);
    vueMixinRetryTimer = undefined;
  }
  vueMixinMounted = false;
  if (lastUnbind) tryRun(() => lastUnbind(), undefined);
  lastUnbind = undefined;
  bootstrapped = false;
}

/**
 * 公有版统计入口。
 *
 * 与私有版 `src/index.js#main()` 等价：模块加载即触发安装。宿主无需手动调用，
 * 只需 `import '@dcloudio/uni-stat-public'`（或对应 dist 路径）即可。
 *
 * 也对外导出 `installPublicStat / getStatApp` 以便调试或自定义场景手动重装。
 */
// 自动安装：与私有版行为一致，加载即触发。
installPublicStat();

/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"], __webpack_require__(/*! ./../../../webpack/buildin/global.js */ 3)))

/***/ }),

/***/ 12:
/*!*************************************!*\
  !*** ./pages.json?{"type":"style"} ***!
  \*************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony default export */ __webpack_exports__["default"] = ({
  "easycom": {
    "autoscan": true,
    "custom": {
      "^u-(.*)": "@/uview-ui/components/u-$1/u-$1.vue"
    }
  },
  "pages": [{
    "path": "pages/index/index",
    "style": {
      "navigationBarTitleText": "首页",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/my/my",
    "style": {
      "navigationBarTitleText": "个人中心",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/my/profile",
    "style": {
      "navigationBarTitleText": "个人资料",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "uview-ui/components/u-avatar-cropper/u-avatar-cropper",
    "style": {
      "navigationBarTitleText": "头像裁剪",
      "navigationBarBackgroundColor": "#000000"
    }
  }, {
    "path": "pages/login/auth",
    "style": {
      "navigationBarTitleText": "微信授权",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/login/openid",
    "style": {
      "navigationBarTitleText": "获取授权",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/login/login",
    "style": {
      "navigationBarTitleText": "登录",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/login/register",
    "style": {
      "navigationBarTitleText": "注册",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/login/forgetpwd",
    "style": {
      "navigationBarTitleText": "忘记密码",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/login/mobilelogin",
    "style": {
      "navigationBarTitleText": "验证码登录",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/signin/signin",
    "style": {
      "navigationBarTitleText": "签到",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/signin/logs",
    "style": {
      "navigationBarTitleText": "签到日志",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/signin/ranking",
    "style": {
      "navigationBarTitleText": "排行榜",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white"
    }
  }, {
    "path": "pages/webview/webview",
    "style": {
      "navigationBarTitleText": "webview",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/order/payment",
    "style": {
      "navigationBarTitleText": "立即支付",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/remark/remark",
    "style": {
      "navigationBarTitleText": "添加评论",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/remark/lists",
    "style": {
      "navigationBarTitleText": "评论列表",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/remark/comment",
    "style": {
      "navigationBarTitleText": "我的评论",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/my/collect",
    "style": {
      "navigationBarTitleText": "我的收藏",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/goods/goods",
    "style": {
      "navigationBarTitleText": "商品列表",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/category/index",
    "style": {
      "navigationBarTitleText": "商品分类",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/goods/detail",
    "style": {
      "navigationBarTitleText": "商品详情",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/cart/cart",
    "style": {
      "navigationBarTitleText": "购物车",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/goods/order",
    "style": {
      "navigationBarTitleText": "提交订单",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/order/list",
    "style": {
      "navigationBarTitleText": "商品订单",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/order/detail",
    "style": {
      "navigationBarTitleText": "订单详情",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": true
    }
  }, {
    "path": "pages/order/apply",
    "style": {
      "navigationBarTitleText": "申请售后",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/order/aftersale",
    "style": {
      "navigationBarTitleText": "查看售后",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": true
    }
  }, {
    "path": "pages/order/logistics",
    "style": {
      "navigationBarTitleText": "查看物流",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/address/address",
    "style": {
      "navigationBarTitleText": "地址管理",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/address/addedit",
    "style": {
      "navigationBarTitleText": "添加地址",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/score/score",
    "style": {
      "navigationBarTitleText": "我的积分",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/score/logs",
    "style": {
      "navigationBarTitleText": "积分日志",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/score/exchange",
    "style": {
      "navigationBarTitleText": "积分兑换",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/score/order",
    "style": {
      "navigationBarTitleText": "兑换订单",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/coupon/coupon",
    "style": {
      "navigationBarTitleText": "优惠券",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/coupon/user",
    "style": {
      "navigationBarTitleText": "我的优惠券",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/coupon/detail",
    "style": {
      "navigationBarTitleText": "优惠券详情",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/page/page",
    "style": {
      "navigationBarTitleText": "单页",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/search/search",
    "style": {
      "navigationBarTitleText": "搜索",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }, {
    "path": "pages/help/index",
    "style": {
      "navigationBarTitleText": "帮助中心",
      "navigationStyle": "custom",
      "navigationBarTextStyle": "white",
      "enablePullDownRefresh": false
    }
  }],
  "preloadRule": {},
  "globalStyle": {
    "navigationBarTextStyle": "black",
    "navigationBarTitleText": "简单商城",
    "navigationBarBackgroundColor": "#F8F8F8",
    "backgroundColor": "#F8F8F8",
    "pageOrientation": "portrait"
  },
  "usingComponts": true
});

/***/ }),

/***/ 16:
/*!***************************************!*\
  !*** ./uview-ui/libs/function/md5.js ***!
  \***************************************/
/*! no static exports found */
/***/ (function(module, exports) {

/*
 * A JavaScript implementation of the RSA Data Security, Inc. MD5 Message
 * Digest Algorithm, as defined in RFC 1321.
 * Version 2.2 Copyright (C) Paul Johnston 1999 - 2009
 * Other contributors: Greg Holt, Andrew Kepert, Ydnar, Lostinet
 * Distributed under the BSD License
 * See http://pajhome.org.uk/crypt/md5 for more info.
 */

/*
 * Configurable variables. You may need to tweak these to be compatible with
 * the server-side, but the defaults work in most cases.
 */
var hexcase = 0; /* hex output format. 0 - lowercase; 1 - uppercase        */
var b64pad = ""; /* base-64 pad character. "=" for strict RFC compliance   */

/*
 * These are the functions you'll usually want to call
 * They take string arguments and return either hex or base-64 encoded strings
 */
function hex_md5(s) {
  return rstr2hex(rstr_md5(str2rstr_utf8(s)));
}
function b64_md5(s) {
  return rstr2b64(rstr_md5(str2rstr_utf8(s)));
}
function any_md5(s, e) {
  return rstr2any(rstr_md5(str2rstr_utf8(s)), e);
}
function hex_hmac_md5(k, d) {
  return rstr2hex(rstr_hmac_md5(str2rstr_utf8(k), str2rstr_utf8(d)));
}
function b64_hmac_md5(k, d) {
  return rstr2b64(rstr_hmac_md5(str2rstr_utf8(k), str2rstr_utf8(d)));
}
function any_hmac_md5(k, d, e) {
  return rstr2any(rstr_hmac_md5(str2rstr_utf8(k), str2rstr_utf8(d)), e);
}

/*
 * Perform a simple self-test to see if the VM is working
 */
function md5_vm_test() {
  return hex_md5("abc").toLowerCase() == "900150983cd24fb0d6963f7d28e17f72";
}

/*
 * Calculate the MD5 of a raw string
 */
function rstr_md5(s) {
  return binl2rstr(binl_md5(rstr2binl(s), s.length * 8));
}

/*
 * Calculate the HMAC-MD5, of a key and some data (raw strings)
 */
function rstr_hmac_md5(key, data) {
  var bkey = rstr2binl(key);
  if (bkey.length > 16) bkey = binl_md5(bkey, key.length * 8);
  var ipad = Array(16),
    opad = Array(16);
  for (var i = 0; i < 16; i++) {
    ipad[i] = bkey[i] ^ 0x36363636;
    opad[i] = bkey[i] ^ 0x5C5C5C5C;
  }
  var hash = binl_md5(ipad.concat(rstr2binl(data)), 512 + data.length * 8);
  return binl2rstr(binl_md5(opad.concat(hash), 512 + 128));
}

/*
 * Convert a raw string to a hex string
 */
function rstr2hex(input) {
  try {
    hexcase;
  } catch (e) {
    hexcase = 0;
  }
  var hex_tab = hexcase ? "0123456789ABCDEF" : "0123456789abcdef";
  var output = "";
  var x;
  for (var i = 0; i < input.length; i++) {
    x = input.charCodeAt(i);
    output += hex_tab.charAt(x >>> 4 & 0x0F) + hex_tab.charAt(x & 0x0F);
  }
  return output;
}

/*
 * Convert a raw string to a base-64 string
 */
function rstr2b64(input) {
  try {
    b64pad;
  } catch (e) {
    b64pad = '';
  }
  var tab = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  var output = "";
  var len = input.length;
  for (var i = 0; i < len; i += 3) {
    var triplet = input.charCodeAt(i) << 16 | (i + 1 < len ? input.charCodeAt(i + 1) << 8 : 0) | (i + 2 < len ? input.charCodeAt(i + 2) : 0);
    for (var j = 0; j < 4; j++) {
      if (i * 8 + j * 6 > input.length * 8) output += b64pad;else output += tab.charAt(triplet >>> 6 * (3 - j) & 0x3F);
    }
  }
  return output;
}

/*
 * Convert a raw string to an arbitrary string encoding
 */
function rstr2any(input, encoding) {
  var divisor = encoding.length;
  var i, j, q, x, quotient;

  /* Convert to an array of 16-bit big-endian values, forming the dividend */
  var dividend = Array(Math.ceil(input.length / 2));
  for (i = 0; i < dividend.length; i++) {
    dividend[i] = input.charCodeAt(i * 2) << 8 | input.charCodeAt(i * 2 + 1);
  }

  /*
   * Repeatedly perform a long division. The binary array forms the dividend,
   * the length of the encoding is the divisor. Once computed, the quotient
   * forms the dividend for the next step. All remainders are stored for later
   * use.
   */
  var full_length = Math.ceil(input.length * 8 / (Math.log(encoding.length) / Math.log(2)));
  var remainders = Array(full_length);
  for (j = 0; j < full_length; j++) {
    quotient = Array();
    x = 0;
    for (i = 0; i < dividend.length; i++) {
      x = (x << 16) + dividend[i];
      q = Math.floor(x / divisor);
      x -= q * divisor;
      if (quotient.length > 0 || q > 0) quotient[quotient.length] = q;
    }
    remainders[j] = x;
    dividend = quotient;
  }

  /* Convert the remainders to the output string */
  var output = "";
  for (i = remainders.length - 1; i >= 0; i--) output += encoding.charAt(remainders[i]);
  return output;
}

/*
 * Encode a string as utf-8.
 * For efficiency, this assumes the input is valid utf-16.
 */
function str2rstr_utf8(input) {
  var output = "";
  var i = -1;
  var x, y;
  while (++i < input.length) {
    /* Decode utf-16 surrogate pairs */
    x = input.charCodeAt(i);
    y = i + 1 < input.length ? input.charCodeAt(i + 1) : 0;
    if (0xD800 <= x && x <= 0xDBFF && 0xDC00 <= y && y <= 0xDFFF) {
      x = 0x10000 + ((x & 0x03FF) << 10) + (y & 0x03FF);
      i++;
    }

    /* Encode output as utf-8 */
    if (x <= 0x7F) output += String.fromCharCode(x);else if (x <= 0x7FF) output += String.fromCharCode(0xC0 | x >>> 6 & 0x1F, 0x80 | x & 0x3F);else if (x <= 0xFFFF) output += String.fromCharCode(0xE0 | x >>> 12 & 0x0F, 0x80 | x >>> 6 & 0x3F, 0x80 | x & 0x3F);else if (x <= 0x1FFFFF) output += String.fromCharCode(0xF0 | x >>> 18 & 0x07, 0x80 | x >>> 12 & 0x3F, 0x80 | x >>> 6 & 0x3F, 0x80 | x & 0x3F);
  }
  return output;
}

/*
 * Encode a string as utf-16
 */
function str2rstr_utf16le(input) {
  var output = "";
  for (var i = 0; i < input.length; i++) output += String.fromCharCode(input.charCodeAt(i) & 0xFF, input.charCodeAt(i) >>> 8 & 0xFF);
  return output;
}
function str2rstr_utf16be(input) {
  var output = "";
  for (var i = 0; i < input.length; i++) output += String.fromCharCode(input.charCodeAt(i) >>> 8 & 0xFF, input.charCodeAt(i) & 0xFF);
  return output;
}

/*
 * Convert a raw string to an array of little-endian words
 * Characters >255 have their high-byte silently ignored.
 */
function rstr2binl(input) {
  var output = Array(input.length >> 2);
  for (var i = 0; i < output.length; i++) output[i] = 0;
  for (var i = 0; i < input.length * 8; i += 8) output[i >> 5] |= (input.charCodeAt(i / 8) & 0xFF) << i % 32;
  return output;
}

/*
 * Convert an array of little-endian words to a string
 */
function binl2rstr(input) {
  var output = "";
  for (var i = 0; i < input.length * 32; i += 8) output += String.fromCharCode(input[i >> 5] >>> i % 32 & 0xFF);
  return output;
}

/*
 * Calculate the MD5 of an array of little-endian words, and a bit length.
 */
function binl_md5(x, len) {
  /* append padding */
  x[len >> 5] |= 0x80 << len % 32;
  x[(len + 64 >>> 9 << 4) + 14] = len;
  var a = 1732584193;
  var b = -271733879;
  var c = -1732584194;
  var d = 271733878;
  for (var i = 0; i < x.length; i += 16) {
    var olda = a;
    var oldb = b;
    var oldc = c;
    var oldd = d;
    a = md5_ff(a, b, c, d, x[i + 0], 7, -680876936);
    d = md5_ff(d, a, b, c, x[i + 1], 12, -389564586);
    c = md5_ff(c, d, a, b, x[i + 2], 17, 606105819);
    b = md5_ff(b, c, d, a, x[i + 3], 22, -1044525330);
    a = md5_ff(a, b, c, d, x[i + 4], 7, -176418897);
    d = md5_ff(d, a, b, c, x[i + 5], 12, 1200080426);
    c = md5_ff(c, d, a, b, x[i + 6], 17, -1473231341);
    b = md5_ff(b, c, d, a, x[i + 7], 22, -45705983);
    a = md5_ff(a, b, c, d, x[i + 8], 7, 1770035416);
    d = md5_ff(d, a, b, c, x[i + 9], 12, -1958414417);
    c = md5_ff(c, d, a, b, x[i + 10], 17, -42063);
    b = md5_ff(b, c, d, a, x[i + 11], 22, -1990404162);
    a = md5_ff(a, b, c, d, x[i + 12], 7, 1804603682);
    d = md5_ff(d, a, b, c, x[i + 13], 12, -40341101);
    c = md5_ff(c, d, a, b, x[i + 14], 17, -1502002290);
    b = md5_ff(b, c, d, a, x[i + 15], 22, 1236535329);
    a = md5_gg(a, b, c, d, x[i + 1], 5, -165796510);
    d = md5_gg(d, a, b, c, x[i + 6], 9, -1069501632);
    c = md5_gg(c, d, a, b, x[i + 11], 14, 643717713);
    b = md5_gg(b, c, d, a, x[i + 0], 20, -373897302);
    a = md5_gg(a, b, c, d, x[i + 5], 5, -701558691);
    d = md5_gg(d, a, b, c, x[i + 10], 9, 38016083);
    c = md5_gg(c, d, a, b, x[i + 15], 14, -660478335);
    b = md5_gg(b, c, d, a, x[i + 4], 20, -405537848);
    a = md5_gg(a, b, c, d, x[i + 9], 5, 568446438);
    d = md5_gg(d, a, b, c, x[i + 14], 9, -1019803690);
    c = md5_gg(c, d, a, b, x[i + 3], 14, -187363961);
    b = md5_gg(b, c, d, a, x[i + 8], 20, 1163531501);
    a = md5_gg(a, b, c, d, x[i + 13], 5, -1444681467);
    d = md5_gg(d, a, b, c, x[i + 2], 9, -51403784);
    c = md5_gg(c, d, a, b, x[i + 7], 14, 1735328473);
    b = md5_gg(b, c, d, a, x[i + 12], 20, -1926607734);
    a = md5_hh(a, b, c, d, x[i + 5], 4, -378558);
    d = md5_hh(d, a, b, c, x[i + 8], 11, -2022574463);
    c = md5_hh(c, d, a, b, x[i + 11], 16, 1839030562);
    b = md5_hh(b, c, d, a, x[i + 14], 23, -35309556);
    a = md5_hh(a, b, c, d, x[i + 1], 4, -1530992060);
    d = md5_hh(d, a, b, c, x[i + 4], 11, 1272893353);
    c = md5_hh(c, d, a, b, x[i + 7], 16, -155497632);
    b = md5_hh(b, c, d, a, x[i + 10], 23, -1094730640);
    a = md5_hh(a, b, c, d, x[i + 13], 4, 681279174);
    d = md5_hh(d, a, b, c, x[i + 0], 11, -358537222);
    c = md5_hh(c, d, a, b, x[i + 3], 16, -722521979);
    b = md5_hh(b, c, d, a, x[i + 6], 23, 76029189);
    a = md5_hh(a, b, c, d, x[i + 9], 4, -640364487);
    d = md5_hh(d, a, b, c, x[i + 12], 11, -421815835);
    c = md5_hh(c, d, a, b, x[i + 15], 16, 530742520);
    b = md5_hh(b, c, d, a, x[i + 2], 23, -995338651);
    a = md5_ii(a, b, c, d, x[i + 0], 6, -198630844);
    d = md5_ii(d, a, b, c, x[i + 7], 10, 1126891415);
    c = md5_ii(c, d, a, b, x[i + 14], 15, -1416354905);
    b = md5_ii(b, c, d, a, x[i + 5], 21, -57434055);
    a = md5_ii(a, b, c, d, x[i + 12], 6, 1700485571);
    d = md5_ii(d, a, b, c, x[i + 3], 10, -1894986606);
    c = md5_ii(c, d, a, b, x[i + 10], 15, -1051523);
    b = md5_ii(b, c, d, a, x[i + 1], 21, -2054922799);
    a = md5_ii(a, b, c, d, x[i + 8], 6, 1873313359);
    d = md5_ii(d, a, b, c, x[i + 15], 10, -30611744);
    c = md5_ii(c, d, a, b, x[i + 6], 15, -1560198380);
    b = md5_ii(b, c, d, a, x[i + 13], 21, 1309151649);
    a = md5_ii(a, b, c, d, x[i + 4], 6, -145523070);
    d = md5_ii(d, a, b, c, x[i + 11], 10, -1120210379);
    c = md5_ii(c, d, a, b, x[i + 2], 15, 718787259);
    b = md5_ii(b, c, d, a, x[i + 9], 21, -343485551);
    a = safe_add(a, olda);
    b = safe_add(b, oldb);
    c = safe_add(c, oldc);
    d = safe_add(d, oldd);
  }
  return Array(a, b, c, d);
}

/*
 * These functions implement the four basic operations the algorithm uses.
 */
function md5_cmn(q, a, b, x, s, t) {
  return safe_add(bit_rol(safe_add(safe_add(a, q), safe_add(x, t)), s), b);
}
function md5_ff(a, b, c, d, x, s, t) {
  return md5_cmn(b & c | ~b & d, a, b, x, s, t);
}
function md5_gg(a, b, c, d, x, s, t) {
  return md5_cmn(b & d | c & ~d, a, b, x, s, t);
}
function md5_hh(a, b, c, d, x, s, t) {
  return md5_cmn(b ^ c ^ d, a, b, x, s, t);
}
function md5_ii(a, b, c, d, x, s, t) {
  return md5_cmn(c ^ (b | ~d), a, b, x, s, t);
}

/*
 * Add integers, wrapping at 2^32. This uses 16-bit operations internally
 * to work around bugs in some JS interpreters.
 */
function safe_add(x, y) {
  var lsw = (x & 0xFFFF) + (y & 0xFFFF);
  var msw = (x >> 16) + (y >> 16) + (lsw >> 16);
  return msw << 16 | lsw & 0xFFFF;
}

/*
 * Bitwise rotate a 32-bit number to the left.
 */
function bit_rol(num, cnt) {
  return num << cnt | num >>> 32 - cnt;
}
module.exports = {
  md5: function (str) {
    return hex_md5(str);
  }
};

/***/ }),

/***/ 19:
/*!**********************************************************************************************************!*\
  !*** ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/runtime/componentNormalizer.js ***!
  \**********************************************************************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "default", function() { return normalizeComponent; });
/* globals __VUE_SSR_CONTEXT__ */

// IMPORTANT: Do NOT use ES2015 features in this file (except for modules).
// This module is a runtime utility for cleaner component module output and will
// be included in the final webpack user bundle.

function normalizeComponent (
  scriptExports,
  render,
  staticRenderFns,
  functionalTemplate,
  injectStyles,
  scopeId,
  moduleIdentifier, /* server only */
  shadowMode, /* vue-cli only */
  components, // fixed by xxxxxx auto components
  renderjs // fixed by xxxxxx renderjs
) {
  // Vue.extend constructor export interop
  var options = typeof scriptExports === 'function'
    ? scriptExports.options
    : scriptExports

  // fixed by xxxxxx auto components
  if (components) {
    if (!options.components) {
      options.components = {}
    }
    var hasOwn = Object.prototype.hasOwnProperty
    for (var name in components) {
      if (hasOwn.call(components, name) && !hasOwn.call(options.components, name)) {
        options.components[name] = components[name]
      }
    }
  }
  // fixed by xxxxxx renderjs
  if (renderjs) {
    if(typeof renderjs.beforeCreate === 'function'){
			renderjs.beforeCreate = [renderjs.beforeCreate]
		}
    (renderjs.beforeCreate || (renderjs.beforeCreate = [])).unshift(function() {
      this[renderjs.__module] = this
    });
    (options.mixins || (options.mixins = [])).push(renderjs)
  }

  // render functions
  if (render) {
    options.render = render
    options.staticRenderFns = staticRenderFns
    options._compiled = true
  }

  // functional template
  if (functionalTemplate) {
    options.functional = true
  }

  // scopedId
  if (scopeId) {
    options._scopeId = 'data-v-' + scopeId
  }

  var hook
  if (moduleIdentifier) { // server build
    hook = function (context) {
      // 2.3 injection
      context =
        context || // cached call
        (this.$vnode && this.$vnode.ssrContext) || // stateful
        (this.parent && this.parent.$vnode && this.parent.$vnode.ssrContext) // functional
      // 2.2 with runInNewContext: true
      if (!context && typeof __VUE_SSR_CONTEXT__ !== 'undefined') {
        context = __VUE_SSR_CONTEXT__
      }
      // inject component styles
      if (injectStyles) {
        injectStyles.call(this, context)
      }
      // register component module identifier for async chunk inferrence
      if (context && context._registeredComponents) {
        context._registeredComponents.add(moduleIdentifier)
      }
    }
    // used by ssr in case component is cached and beforeCreate
    // never gets called
    options._ssrRegister = hook
  } else if (injectStyles) {
    hook = shadowMode
      ? function () { injectStyles.call(this, this.$root.$options.shadowRoot) }
      : injectStyles
  }

  if (hook) {
    if (options.functional) {
      // for template-only hot-reload because in that case the render fn doesn't
      // go through the normalizer
      options._injectStyles = hook
      // register for functioal component in vue file
      var originalRender = options.render
      options.render = function renderWithStyleInjection (h, context) {
        hook.call(context)
        return originalRender(h, context)
      }
    } else {
      // inject component registration as beforeCreate hook
      var existing = options.beforeCreate
      options.beforeCreate = existing
        ? [].concat(existing, hook)
        : [hook]
    }
  }

  return {
    exports: scriptExports,
    options: options
  }
}


/***/ }),

/***/ 2:
/*!************************************************************!*\
  !*** ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js ***!
  \************************************************************/
/*! exports provided: default, createApp, createComponent, createPage, createPlugin, createSubpackageApp */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(wx, global) {/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "createApp", function() { return createApp; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "createComponent", function() { return createComponent; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "createPage", function() { return createPage; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "createPlugin", function() { return createPlugin; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "createSubpackageApp", function() { return createSubpackageApp; });
/* harmony import */ var _dcloudio_uni_i18n__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @dcloudio/uni-i18n */ 4);
/* harmony import */ var vue__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! vue */ 5);


let realAtob;
const b64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';
const b64re = /^(?:[A-Za-z\d+/]{4})*?(?:[A-Za-z\d+/]{2}(?:==)?|[A-Za-z\d+/]{3}=?)?$/;
if (typeof atob !== 'function') {
  realAtob = function (str) {
    str = String(str).replace(/[\t\n\f\r ]+/g, '');
    if (!b64re.test(str)) {
      throw new Error("Failed to execute 'atob' on 'Window': The string to be decoded is not correctly encoded.");
    }

    // Adding the padding if missing, for semplicity
    str += '=='.slice(2 - (str.length & 3));
    var bitmap;
    var result = '';
    var r1;
    var r2;
    var i = 0;
    for (; i < str.length;) {
      bitmap = b64.indexOf(str.charAt(i++)) << 18 | b64.indexOf(str.charAt(i++)) << 12 | (r1 = b64.indexOf(str.charAt(i++))) << 6 | (r2 = b64.indexOf(str.charAt(i++)));
      result += r1 === 64 ? String.fromCharCode(bitmap >> 16 & 255) : r2 === 64 ? String.fromCharCode(bitmap >> 16 & 255, bitmap >> 8 & 255) : String.fromCharCode(bitmap >> 16 & 255, bitmap >> 8 & 255, bitmap & 255);
    }
    return result;
  };
} else {
  // 注意atob只能在全局对象上调用，例如：`const Base64 = {atob};Base64.atob('xxxx')`是错误的用法
  realAtob = atob;
}
function b64DecodeUnicode(str) {
  return decodeURIComponent(realAtob(str).split('').map(function (c) {
    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
  }).join(''));
}
function getCurrentUserInfo() {
  const token = wx.getStorageSync('uni_id_token') || '';
  const tokenArr = token.split('.');
  if (!token || tokenArr.length !== 3) {
    return {
      uid: null,
      role: [],
      permission: [],
      tokenExpired: 0
    };
  }
  let userInfo;
  try {
    userInfo = JSON.parse(b64DecodeUnicode(tokenArr[1]));
  } catch (error) {
    throw new Error('获取当前用户信息出错，详细错误信息为：' + error.message);
  }
  userInfo.tokenExpired = userInfo.exp * 1000;
  delete userInfo.exp;
  delete userInfo.iat;
  return userInfo;
}
function uniIdMixin(Vue) {
  Vue.prototype.uniIDHasRole = function (roleId) {
    const {
      role
    } = getCurrentUserInfo();
    return role.indexOf(roleId) > -1;
  };
  Vue.prototype.uniIDHasPermission = function (permissionId) {
    const {
      permission
    } = getCurrentUserInfo();
    return this.uniIDHasRole('admin') || permission.indexOf(permissionId) > -1;
  };
  Vue.prototype.uniIDTokenValid = function () {
    const {
      tokenExpired
    } = getCurrentUserInfo();
    return tokenExpired > Date.now();
  };
}
const _toString = Object.prototype.toString;
const hasOwnProperty = Object.prototype.hasOwnProperty;
function isFn(fn) {
  return typeof fn === 'function';
}
function isStr(str) {
  return typeof str === 'string';
}
function isObject(obj) {
  return obj !== null && typeof obj === 'object';
}
function isPlainObject(obj) {
  return _toString.call(obj) === '[object Object]';
}
function hasOwn(obj, key) {
  return hasOwnProperty.call(obj, key);
}
function noop() {}

/**
 * Create a cached version of a pure function.
 */
function cached(fn) {
  const cache = Object.create(null);
  return function cachedFn(str) {
    const hit = cache[str];
    return hit || (cache[str] = fn(str));
  };
}

/**
 * Camelize a hyphen-delimited string.
 */
const camelizeRE = /-(\w)/g;
const camelize = cached(str => {
  return str.replace(camelizeRE, (_, c) => c ? c.toUpperCase() : '');
});
const HOOKS = ['invoke', 'success', 'fail', 'complete', 'returnValue'];
const globalInterceptors = {};
const scopedInterceptors = {};
function mergeHook(parentVal, childVal) {
  const res = childVal ? parentVal ? parentVal.concat(childVal) : Array.isArray(childVal) ? childVal : [childVal] : parentVal;
  return res ? dedupeHooks(res) : res;
}
function dedupeHooks(hooks) {
  const res = [];
  for (let i = 0; i < hooks.length; i++) {
    if (res.indexOf(hooks[i]) === -1) {
      res.push(hooks[i]);
    }
  }
  return res;
}
function removeHook(hooks, hook) {
  const index = hooks.indexOf(hook);
  if (index !== -1) {
    hooks.splice(index, 1);
  }
}
function mergeInterceptorHook(interceptor, option) {
  Object.keys(option).forEach(hook => {
    if (HOOKS.indexOf(hook) !== -1 && isFn(option[hook])) {
      interceptor[hook] = mergeHook(interceptor[hook], option[hook]);
    }
  });
}
function removeInterceptorHook(interceptor, option) {
  if (!interceptor || !option) {
    return;
  }
  Object.keys(option).forEach(hook => {
    if (HOOKS.indexOf(hook) !== -1 && isFn(option[hook])) {
      removeHook(interceptor[hook], option[hook]);
    }
  });
}
function addInterceptor(method, option) {
  if (typeof method === 'string' && isPlainObject(option)) {
    mergeInterceptorHook(scopedInterceptors[method] || (scopedInterceptors[method] = {}), option);
  } else if (isPlainObject(method)) {
    mergeInterceptorHook(globalInterceptors, method);
  }
}
function removeInterceptor(method, option) {
  if (typeof method === 'string') {
    if (isPlainObject(option)) {
      removeInterceptorHook(scopedInterceptors[method], option);
    } else {
      delete scopedInterceptors[method];
    }
  } else if (isPlainObject(method)) {
    removeInterceptorHook(globalInterceptors, method);
  }
}
function wrapperHook(hook, params) {
  return function (data) {
    return hook(data, params) || data;
  };
}
function isPromise(obj) {
  return !!obj && (typeof obj === 'object' || typeof obj === 'function') && typeof obj.then === 'function';
}
function queue(hooks, data, params) {
  let promise = false;
  for (let i = 0; i < hooks.length; i++) {
    const hook = hooks[i];
    if (promise) {
      promise = Promise.resolve(wrapperHook(hook, params));
    } else {
      const res = hook(data, params);
      if (isPromise(res)) {
        promise = Promise.resolve(res);
      }
      if (res === false) {
        return {
          then() {}
        };
      }
    }
  }
  return promise || {
    then(callback) {
      return callback(data);
    }
  };
}
function wrapperOptions(interceptor, options = {}) {
  ['success', 'fail', 'complete'].forEach(name => {
    if (Array.isArray(interceptor[name])) {
      const oldCallback = options[name];
      options[name] = function callbackInterceptor(res) {
        queue(interceptor[name], res, options).then(res => {
          /* eslint-disable no-mixed-operators */
          return isFn(oldCallback) && oldCallback(res) || res;
        });
      };
    }
  });
  return options;
}
function wrapperReturnValue(method, returnValue) {
  const returnValueHooks = [];
  if (Array.isArray(globalInterceptors.returnValue)) {
    returnValueHooks.push(...globalInterceptors.returnValue);
  }
  const interceptor = scopedInterceptors[method];
  if (interceptor && Array.isArray(interceptor.returnValue)) {
    returnValueHooks.push(...interceptor.returnValue);
  }
  returnValueHooks.forEach(hook => {
    returnValue = hook(returnValue) || returnValue;
  });
  return returnValue;
}
function getApiInterceptorHooks(method) {
  const interceptor = Object.create(null);
  Object.keys(globalInterceptors).forEach(hook => {
    if (hook !== 'returnValue') {
      interceptor[hook] = globalInterceptors[hook].slice();
    }
  });
  const scopedInterceptor = scopedInterceptors[method];
  if (scopedInterceptor) {
    Object.keys(scopedInterceptor).forEach(hook => {
      if (hook !== 'returnValue') {
        interceptor[hook] = (interceptor[hook] || []).concat(scopedInterceptor[hook]);
      }
    });
  }
  return interceptor;
}
function invokeApi(method, api, options, ...params) {
  const interceptor = getApiInterceptorHooks(method);
  if (interceptor && Object.keys(interceptor).length) {
    if (Array.isArray(interceptor.invoke)) {
      const res = queue(interceptor.invoke, options);
      return res.then(options => {
        // 重新访问 getApiInterceptorHooks, 允许 invoke 中再次调用 addInterceptor,removeInterceptor
        return api(wrapperOptions(getApiInterceptorHooks(method), options), ...params);
      });
    } else {
      return api(wrapperOptions(interceptor, options), ...params);
    }
  }
  return api(options, ...params);
}
const promiseInterceptor = {
  returnValue(res) {
    if (!isPromise(res)) {
      return res;
    }
    return new Promise((resolve, reject) => {
      res.then(res => {
        if (!res) {
          resolve(res);
          return;
        }
        if (res[0]) {
          reject(res[0]);
        } else {
          resolve(res[1]);
        }
      });
    });
  }
};
const SYNC_API_RE = /^\$|__f__|Window$|WindowStyle$|sendHostEvent|sendNativeEvent|restoreGlobal|requireGlobal|getCurrentSubNVue|getMenuButtonBoundingClientRect|^report|interceptors|Interceptor$|getSubNVueById|requireNativePlugin|rpx2px|upx2px|hideKeyboard|canIUse|^create|Sync$|Manager$|base64ToArrayBuffer|arrayBufferToBase64|getLocale|setLocale|invokePushCallback|getWindowInfo|getDeviceInfo|getAppBaseInfo|getSystemSetting|getAppAuthorizeSetting|initUTS|requireUTS|registerUTS|getFacialRecognitionMetaInfo/;
const CONTEXT_API_RE = /^create|Manager$/;

// Context例外情况
const CONTEXT_API_RE_EXC = ['createBLEConnection'];

// 同步例外情况
const ASYNC_API = ['createBLEConnection', 'createPushMessage'];
const CALLBACK_API_RE = /^on|^off/;
function isContextApi(name) {
  return CONTEXT_API_RE.test(name) && CONTEXT_API_RE_EXC.indexOf(name) === -1;
}
function isSyncApi(name) {
  return SYNC_API_RE.test(name) && ASYNC_API.indexOf(name) === -1;
}
function isCallbackApi(name) {
  return CALLBACK_API_RE.test(name) && name !== 'onPush';
}
function handlePromise(promise) {
  return promise.then(data => {
    return [null, data];
  }).catch(err => [err]);
}
function shouldPromise(name) {
  if (isContextApi(name) || isSyncApi(name) || isCallbackApi(name)) {
    return false;
  }
  return true;
}

/* eslint-disable no-extend-native */
if (!Promise.prototype.finally) {
  Promise.prototype.finally = function (callback) {
    const promise = this.constructor;
    return this.then(value => promise.resolve(callback()).then(() => value), reason => promise.resolve(callback()).then(() => {
      throw reason;
    }));
  };
}
function promisify(name, api) {
  if (!shouldPromise(name) || !isFn(api)) {
    return api;
  }
  return function promiseApi(options = {}, ...params) {
    if (isFn(options.success) || isFn(options.fail) || isFn(options.complete)) {
      return wrapperReturnValue(name, invokeApi(name, api, Object.assign({}, options), ...params));
    }
    return wrapperReturnValue(name, handlePromise(new Promise((resolve, reject) => {
      invokeApi(name, api, Object.assign({}, options, {
        success: resolve,
        fail: reject
      }), ...params);
    })));
  };
}
const EPS = 1e-4;
const BASE_DEVICE_WIDTH = 750;
let isIOS = false;
let deviceWidth = 0;
let deviceDPR = 0;
function checkDeviceWidth() {
  let windowWidth, pixelRatio, platform;
  {
    const windowInfo = typeof wx.getWindowInfo === 'function' && wx.getWindowInfo() ? wx.getWindowInfo() : wx.getSystemInfoSync();
    const deviceInfo = typeof wx.getDeviceInfo === 'function' && wx.getDeviceInfo() ? wx.getDeviceInfo() : wx.getSystemInfoSync();
    windowWidth = windowInfo.windowWidth;
    pixelRatio = windowInfo.pixelRatio;
    platform = deviceInfo.platform;
  }
  deviceWidth = windowWidth;
  deviceDPR = pixelRatio;
  isIOS = platform === 'ios';
}
function upx2px(number, newDeviceWidth) {
  if (deviceWidth === 0) {
    checkDeviceWidth();
  }
  number = Number(number);
  if (number === 0) {
    return 0;
  }
  let result = number / BASE_DEVICE_WIDTH * (newDeviceWidth || deviceWidth);
  if (result < 0) {
    result = -result;
  }
  result = Math.floor(result + EPS);
  if (result === 0) {
    if (deviceDPR === 1 || !isIOS) {
      result = 1;
    } else {
      result = 0.5;
    }
  }
  return number < 0 ? -result : result;
}
const LOCALE_ZH_HANS = 'zh-Hans';
const LOCALE_ZH_HANT = 'zh-Hant';
const LOCALE_EN = 'en';
const LOCALE_FR = 'fr';
const LOCALE_ES = 'es';
const messages = {};
function getLocaleLanguage() {
  let localeLanguage = '';
  {
    const appBaseInfo = typeof wx.getAppBaseInfo === 'function' && wx.getAppBaseInfo() ? wx.getAppBaseInfo() : wx.getSystemInfoSync();
    const language = appBaseInfo && appBaseInfo.language ? appBaseInfo.language : LOCALE_EN;
    localeLanguage = normalizeLocale(language) || LOCALE_EN;
  }
  return localeLanguage;
}
let locale;
{
  locale = getLocaleLanguage();
}
function initI18nMessages() {
  if (!isEnableLocale()) {
    return;
  }
  const localeKeys = Object.keys(__uniConfig.locales);
  if (localeKeys.length) {
    localeKeys.forEach(locale => {
      const curMessages = messages[locale];
      const userMessages = __uniConfig.locales[locale];
      if (curMessages) {
        Object.assign(curMessages, userMessages);
      } else {
        messages[locale] = userMessages;
      }
    });
  }
}
initI18nMessages();
const i18n = Object(_dcloudio_uni_i18n__WEBPACK_IMPORTED_MODULE_0__["initVueI18n"])(locale, {});
const t = i18n.t;
const i18nMixin = i18n.mixin = {
  beforeCreate() {
    const unwatch = i18n.i18n.watchLocale(() => {
      this.$forceUpdate();
    });
    this.$once('hook:beforeDestroy', function () {
      unwatch();
    });
  },
  methods: {
    $$t(key, values) {
      return t(key, values);
    }
  }
};
const setLocale = i18n.setLocale;
const getLocale = i18n.getLocale;
function initAppLocale(Vue, appVm, locale) {
  const state = Vue.observable({
    locale: locale || i18n.getLocale()
  });
  const localeWatchers = [];
  appVm.$watchLocale = fn => {
    localeWatchers.push(fn);
  };
  Object.defineProperty(appVm, '$locale', {
    get() {
      return state.locale;
    },
    set(v) {
      state.locale = v;
      localeWatchers.forEach(watch => watch(v));
    }
  });
}
function isEnableLocale() {
  return typeof __uniConfig !== 'undefined' && __uniConfig.locales && !!Object.keys(__uniConfig.locales).length;
}
function include(str, parts) {
  return !!parts.find(part => str.indexOf(part) !== -1);
}
function startsWith(str, parts) {
  return parts.find(part => str.indexOf(part) === 0);
}
function normalizeLocale(locale, messages) {
  if (!locale) {
    return;
  }
  locale = locale.trim().replace(/_/g, '-');
  if (messages && messages[locale]) {
    return locale;
  }
  locale = locale.toLowerCase();
  if (locale === 'chinese') {
    // 支付宝
    return LOCALE_ZH_HANS;
  }
  if (locale.indexOf('zh') === 0) {
    if (locale.indexOf('-hans') > -1) {
      return LOCALE_ZH_HANS;
    }
    if (locale.indexOf('-hant') > -1) {
      return LOCALE_ZH_HANT;
    }
    if (include(locale, ['-tw', '-hk', '-mo', '-cht'])) {
      return LOCALE_ZH_HANT;
    }
    return LOCALE_ZH_HANS;
  }
  const lang = startsWith(locale, [LOCALE_EN, LOCALE_FR, LOCALE_ES]);
  if (lang) {
    return lang;
  }
}
// export function initI18n() {
//   const localeKeys = Object.keys(__uniConfig.locales || {})
//   if (localeKeys.length) {
//     localeKeys.forEach((locale) =>
//       i18n.add(locale, __uniConfig.locales[locale])
//     )
//   }
// }

function getLocale$1() {
  // 优先使用 $locale
  if (isFn(getApp)) {
    const app = getApp({
      allowDefault: true
    });
    if (app && app.$vm) {
      return app.$vm.$locale;
    }
  }
  return getLocaleLanguage();
}
function setLocale$1(locale) {
  const app = isFn(getApp) ? getApp() : false;
  if (!app) {
    return false;
  }
  const oldLocale = app.$vm.$locale;
  if (oldLocale !== locale) {
    app.$vm.$locale = locale;
    onLocaleChangeCallbacks.forEach(fn => fn({
      locale
    }));
    return true;
  }
  return false;
}
const onLocaleChangeCallbacks = [];
function onLocaleChange(fn) {
  if (onLocaleChangeCallbacks.indexOf(fn) === -1) {
    onLocaleChangeCallbacks.push(fn);
  }
}
if (typeof global !== 'undefined') {
  global.getLocale = getLocale$1;
}
const interceptors = {
  promiseInterceptor
};
var baseApi = /*#__PURE__*/Object.freeze({
  __proto__: null,
  upx2px: upx2px,
  rpx2px: upx2px,
  getLocale: getLocale$1,
  setLocale: setLocale$1,
  onLocaleChange: onLocaleChange,
  addInterceptor: addInterceptor,
  removeInterceptor: removeInterceptor,
  interceptors: interceptors
});
function findExistsPageIndex(url) {
  const pages = getCurrentPages();
  let len = pages.length;
  while (len--) {
    const page = pages[len];
    if (page.$page && page.$page.fullPath === url) {
      return len;
    }
  }
  return -1;
}
var redirectTo = {
  name(fromArgs) {
    if (fromArgs.exists === 'back' && fromArgs.delta) {
      return 'navigateBack';
    }
    return 'redirectTo';
  },
  args(fromArgs) {
    if (fromArgs.exists === 'back' && fromArgs.url) {
      const existsPageIndex = findExistsPageIndex(fromArgs.url);
      if (existsPageIndex !== -1) {
        const delta = getCurrentPages().length - 1 - existsPageIndex;
        if (delta > 0) {
          fromArgs.delta = delta;
        }
      }
    }
  }
};
var previewImage = {
  args(fromArgs) {
    let currentIndex = parseInt(fromArgs.current);
    if (isNaN(currentIndex)) {
      return;
    }
    const urls = fromArgs.urls;
    if (!Array.isArray(urls)) {
      return;
    }
    const len = urls.length;
    if (!len) {
      return;
    }
    if (currentIndex < 0) {
      currentIndex = 0;
    } else if (currentIndex >= len) {
      currentIndex = len - 1;
    }
    if (currentIndex > 0) {
      fromArgs.current = urls[currentIndex];
      fromArgs.urls = urls.filter((item, index) => index < currentIndex ? item !== urls[currentIndex] : true);
    } else {
      fromArgs.current = urls[0];
    }
    return {
      indicator: false,
      loop: false
    };
  }
};
const UUID_KEY = '__DC_STAT_UUID';
let deviceId;
function useDeviceId(result) {
  deviceId = deviceId || wx.getStorageSync(UUID_KEY);
  if (!deviceId) {
    deviceId = Date.now() + '' + Math.floor(Math.random() * 1e7);
    wx.setStorage({
      key: UUID_KEY,
      data: deviceId
    });
  }
  result.deviceId = deviceId;
}
function addSafeAreaInsets(result) {
  if (result.safeArea) {
    const safeArea = result.safeArea;
    result.safeAreaInsets = {
      top: safeArea.top,
      left: safeArea.left,
      right: result.windowWidth - safeArea.right,
      bottom: result.screenHeight - safeArea.bottom
    };
  }
}
function getOSInfo(system, platform) {
  /**
   * system 枚举值说明：
   *
   * weixin: 操作系统及版本
   * qq: 操作系统及版本
   * kuaishou: 操作系统及版本
   *
   * alipay、dingding: 系统版本
   * baidu: 操作系统版本
   * toutiao/douyin: 操作系统版本
   * jd: 操作系统版本
   * harmony: 操作系统版本
   *
   * lark: 文档无此字段
   */
  let osName = '';
  let osVersion = '';
  if (platform && "mp-weixin" === 'mp-harmony') {
    osName = platform;
    osVersion = system;
    system = `${osName} ${osVersion}`;
  } else {
    {
      osName = platform;
    }
    osVersion = system.split(' ')[1] || '';
  }
  osName = osName.toLocaleLowerCase();
  switch (osName) {
    case 'harmony': // alipay
    case 'ohos': // weixin harmony
    case 'openharmonyos': // weixin 由 HarmonyOS 改为了 OpenHarmonyOS
    case 'openharmony':
      // feishu
      osName = 'harmonyos';
      break;
    case 'iphone os':
      // alipay
      osName = 'ios';
      break;
    case 'mac': // weixin qq
    case 'darwin':
      // feishu
      osName = 'macos';
      break;
    case 'windows_nt':
      // feishu
      osName = 'windows';
      break;
  }
  return {
    osName,
    osVersion,
    system
  };
}
function getPlatform(platform) {
  /**
   * platform 枚举值说明：
   *
   * weixin：ios、android、windows、mac、ohos、ohos_pc、devtools
   * alipay、dingding：Android，iOS / iPhone OS，Harmony
   * harmony: 固定 ohos
   *
   * toutiao: Android，iOS 无 harmony 平台，暂不处理
   * lark: 'pc' | 'mobile' | 'android' | 'ios', 无 harmony 平台，暂不处理
   *
   * baidu：无相关描述
   * qq: 无相关描述
   * kuaishou: 无相关描述
   * jd: 无相关描述
   */
  platform = platform.toLowerCase();
  {
    if (platform === 'ohos') {
      platform = 'harmonyos';
    }
  }
  return platform;
}
function populateParameters(result) {
  const {
    brand = '',
    model = '',
    system = '',
    language = '',
    theme,
    version,
    platform,
    fontSizeSetting,
    SDKVersion,
    pixelRatio,
    deviceOrientation
  } = result;
  // const isQuickApp = "mp-weixin".indexOf('quickapp-webview') !== -1

  const extraParam = {};

  // osName osVersion
  const {
    osName,
    osVersion,
    system: updatedSystem
  } = getOSInfo(system, platform);
  let hostVersion = version;

  // deviceType
  const deviceType = getGetDeviceType(result, model);

  // deviceModel
  const deviceBrand = getDeviceBrand(brand);

  // hostName
  const _hostName = getHostName(result);

  // deviceOrientation
  let _deviceOrientation = deviceOrientation; // 仅 微信 百度 支持

  // devicePixelRatio
  let _devicePixelRatio = pixelRatio;

  // SDKVersion
  let _SDKVersion = SDKVersion;

  // hostLanguage
  const hostLanguage = (language || '').replace(/_/g, '-');

  // wx.getAccountInfoSync

  const parameters = {
    appId: "",
    appName: "商城",
    appVersion: "1.2.7",
    appVersionCode: "127",
    appLanguage: getAppLanguage(hostLanguage),
    uniCompileVersion: "5.26",
    uniCompilerVersion: "5.26",
    uniRuntimeVersion: "5.26",
    uniPlatform: undefined || "mp-weixin",
    deviceBrand,
    deviceModel: model,
    deviceType,
    devicePixelRatio: _devicePixelRatio,
    deviceOrientation: _deviceOrientation,
    osName: osName.toLocaleLowerCase(),
    osVersion,
    hostTheme: theme,
    hostVersion,
    hostLanguage,
    hostName: _hostName,
    hostSDKVersion: _SDKVersion,
    hostFontSizeSetting: fontSizeSetting,
    windowTop: 0,
    windowBottom: 0,
    platform: getPlatform(platform),
    system: updatedSystem,
    // TODO
    osLanguage: undefined,
    osTheme: undefined,
    ua: undefined,
    hostPackageName: undefined,
    browserName: undefined,
    browserVersion: undefined,
    isUniAppX: false
  };
  Object.assign(result, parameters, extraParam);
}
function getGetDeviceType(result, model) {
  const platform = result.platform || '';
  let deviceType = result.deviceType || 'phone';
  {
    const deviceTypeMaps = {
      ipad: 'pad',
      windows: 'pc',
      mac: 'pc',
      linux: 'pc',
      pc: 'pc'
    };
    const deviceTypeMapsKeys = Object.keys(deviceTypeMaps);
    const _model = model.toLocaleLowerCase();
    for (let index = 0; index < deviceTypeMapsKeys.length; index++) {
      const _m = deviceTypeMapsKeys[index];
      if (_model.indexOf(_m) !== -1) {
        deviceType = deviceTypeMaps[_m];
        break;
      }
    }
  }
  {
    if (platform === 'ohos_pc') {
      deviceType = 'pc';
    }
  }
  return deviceType;
}
function getDeviceBrand(brand) {
  let deviceBrand = brand;
  if (deviceBrand) {
    deviceBrand = brand.toLocaleLowerCase();
  }
  return deviceBrand;
}
function getAppLanguage(defaultLanguage) {
  return getLocale$1 ? getLocale$1() : defaultLanguage;
}
function getHostName(result) {
  const _platform = 'WeChat';
  let _hostName = result.hostName || _platform; // mp-jd
  {
    if (result.environment) {
      _hostName = result.environment;
    } else if (result.host && result.host.env) {
      _hostName = result.host.env;
    }
  }
  return _hostName;
}
var getSystemInfo = {
  returnValue: function (result) {
    useDeviceId(result);
    addSafeAreaInsets(result);
    populateParameters(result);
  }
};
var showActionSheet = {
  args(fromArgs) {
    if (typeof fromArgs === 'object') {
      fromArgs.alertText = fromArgs.title;
    }
  }
};
var getAppBaseInfo = {
  returnValue: function (result) {
    const {
      version,
      language,
      SDKVersion,
      theme
    } = result;
    const _hostName = getHostName(result);
    const hostLanguage = (language || '').replace('_', '-');
    const parameters = {
      appId: "",
      appName: "商城",
      appVersion: "1.2.7",
      appVersionCode: "127",
      appLanguage: getAppLanguage(hostLanguage),
      hostVersion: version,
      hostLanguage,
      hostName: _hostName,
      hostSDKVersion: SDKVersion,
      hostTheme: theme,
      isUniAppX: false,
      uniPlatform: undefined || "mp-weixin",
      uniCompileVersion: "5.26",
      uniCompilerVersion: "5.26",
      uniRuntimeVersion: "5.26"
    };
    try {
      if (typeof wx.getAccountInfoSync === 'function') {
        parameters.packagename = wx.getAccountInfoSync().miniProgram.appId;
      }
    } catch (e) {}
    result = Object.assign(result, parameters);
  }
};

/**
 * 目前仅 weixin、toutiao/douyin 支持 deviceInfo。
 * system: 操作系统及版本
 */
var getDeviceInfo = {
  returnValue: function (result) {
    const {
      brand,
      model,
      system = '',
      platform = ''
    } = result;
    const deviceType = getGetDeviceType(result, model);
    const deviceBrand = getDeviceBrand(brand);
    useDeviceId(result);
    const {
      osName,
      osVersion
    } = getOSInfo(system, platform);
    result = Object.assign(result, {
      deviceType,
      deviceBrand,
      deviceModel: model,
      osName,
      osVersion,
      platform: getPlatform(platform)
    });
  }
};
var getWindowInfo = {
  returnValue: function (result) {
    addSafeAreaInsets(result);
    result = Object.assign(result, {
      windowTop: 0,
      windowBottom: 0
    });
  }
};
var getAppAuthorizeSetting = {
  returnValue: function (result) {
    const {
      locationReducedAccuracy
    } = result;
    result.locationAccuracy = 'unsupported';
    if (locationReducedAccuracy === true) {
      result.locationAccuracy = 'reduced';
    } else if (locationReducedAccuracy === false) {
      result.locationAccuracy = 'full';
    }
  }
};

// import navigateTo from 'uni-helpers/navigate-to'

const compressImage = {
  args(fromArgs) {
    // https://developers.weixin.qq.com/community/develop/doc/000c08940c865011298e0a43256800?highLine=compressHeight
    if (fromArgs.compressedHeight && !fromArgs.compressHeight) {
      fromArgs.compressHeight = fromArgs.compressedHeight;
    }
    if (fromArgs.compressedWidth && !fromArgs.compressWidth) {
      fromArgs.compressWidth = fromArgs.compressedWidth;
    }
  }
};
const protocols = {
  redirectTo,
  // navigateTo,  // 由于在微信开发者工具的页面参数，会显示__id__参数，因此暂时关闭mp-weixin对于navigateTo的AOP
  previewImage,
  getSystemInfo,
  getSystemInfoSync: getSystemInfo,
  showActionSheet,
  getAppBaseInfo,
  getDeviceInfo,
  getWindowInfo,
  getAppAuthorizeSetting,
  compressImage
};
const todos = ['vibrate', 'preloadPage', 'unPreloadPage', 'loadSubPackage'];
const canIUses = [];
const CALLBACKS = ['success', 'fail', 'cancel', 'complete'];
function processCallback(methodName, method, returnValue) {
  return function (res) {
    return method(processReturnValue(methodName, res, returnValue));
  };
}
function processArgs(methodName, fromArgs, argsOption = {}, returnValue = {}, keepFromArgs = false) {
  if (isPlainObject(fromArgs)) {
    // 一般 api 的参数解析
    const toArgs = keepFromArgs === true ? fromArgs : {}; // returnValue 为 false 时，说明是格式化返回值，直接在返回值对象上修改赋值
    if (isFn(argsOption)) {
      argsOption = argsOption(fromArgs, toArgs) || {};
    }
    for (const key in fromArgs) {
      if (hasOwn(argsOption, key)) {
        let keyOption = argsOption[key];
        if (isFn(keyOption)) {
          keyOption = keyOption(fromArgs[key], fromArgs, toArgs);
        }
        if (!keyOption) {
          // 不支持的参数
          console.warn(`The '${methodName}' method of platform '微信小程序' does not support option '${key}'`);
        } else if (isStr(keyOption)) {
          // 重写参数 key
          toArgs[keyOption] = fromArgs[key];
        } else if (isPlainObject(keyOption)) {
          // {name:newName,value:value}可重新指定参数 key:value
          toArgs[keyOption.name ? keyOption.name : key] = keyOption.value;
        }
      } else if (CALLBACKS.indexOf(key) !== -1) {
        if (isFn(fromArgs[key])) {
          toArgs[key] = processCallback(methodName, fromArgs[key], returnValue);
        }
      } else {
        if (!keepFromArgs) {
          toArgs[key] = fromArgs[key];
        }
      }
    }
    return toArgs;
  } else if (isFn(fromArgs)) {
    fromArgs = processCallback(methodName, fromArgs, returnValue);
  }
  return fromArgs;
}
function processReturnValue(methodName, res, returnValue, keepReturnValue = false) {
  if (isFn(protocols.returnValue)) {
    // 处理通用 returnValue
    res = protocols.returnValue(methodName, res);
  }
  return processArgs(methodName, res, returnValue, {}, keepReturnValue);
}
function wrapper(methodName, method) {
  if (hasOwn(protocols, methodName)) {
    const protocol = protocols[methodName];
    if (!protocol) {
      // 暂不支持的 api
      return function () {
        console.error(`Platform '微信小程序' does not support '${methodName}'.`);
      };
    }
    return function (arg1, arg2) {
      // 目前 api 最多两个参数
      let options = protocol;
      if (isFn(protocol)) {
        options = protocol(arg1);
      }
      arg1 = processArgs(methodName, arg1, options.args, options.returnValue);
      const args = [arg1];
      if (typeof arg2 !== 'undefined') {
        args.push(arg2);
      }
      if (isFn(options.name)) {
        methodName = options.name(arg1);
      } else if (isStr(options.name)) {
        methodName = options.name;
      }
      const returnValue = wx[methodName].apply(wx, args);
      if (isSyncApi(methodName)) {
        // 同步 api
        return processReturnValue(methodName, returnValue, options.returnValue, isContextApi(methodName));
      }
      return returnValue;
    };
  }
  return method;
}
const todoApis = Object.create(null);
const TODOS = ['onTabBarMidButtonTap', 'subscribePush', 'unsubscribePush', 'onPush', 'offPush', 'share'];
function createTodoApi(name) {
  return function todoApi({
    fail,
    complete
  }) {
    const res = {
      errMsg: `${name}:fail method '${name}' not supported`
    };
    isFn(fail) && fail(res);
    isFn(complete) && complete(res);
  };
}
TODOS.forEach(function (name) {
  todoApis[name] = createTodoApi(name);
});
var providers = {
  oauth: ['weixin'],
  share: ['weixin'],
  payment: ['wxpay'],
  push: ['weixin']
};
function getProvider({
  service,
  success,
  fail,
  complete
}) {
  let res = false;
  if (providers[service]) {
    res = {
      errMsg: 'getProvider:ok',
      service,
      provider: providers[service]
    };
    isFn(success) && success(res);
  } else {
    res = {
      errMsg: 'getProvider:fail service not found'
    };
    isFn(fail) && fail(res);
  }
  isFn(complete) && complete(res);
}
var extraApi = /*#__PURE__*/Object.freeze({
  __proto__: null,
  getProvider: getProvider
});
const getEmitter = function () {
  let Emitter;
  return function getUniEmitter() {
    if (!Emitter) {
      Emitter = new vue__WEBPACK_IMPORTED_MODULE_1__["default"]();
    }
    return Emitter;
  };
}();
function apply(ctx, method, args) {
  return ctx[method].apply(ctx, args);
}
function $on() {
  return apply(getEmitter(), '$on', [...arguments]);
}
function $off() {
  return apply(getEmitter(), '$off', [...arguments]);
}
function $once() {
  return apply(getEmitter(), '$once', [...arguments]);
}
function $emit() {
  return apply(getEmitter(), '$emit', [...arguments]);
}
var eventApi = /*#__PURE__*/Object.freeze({
  __proto__: null,
  $on: $on,
  $off: $off,
  $once: $once,
  $emit: $emit
});

/**
 * 框架内 try-catch
 */
/**
 * 开发者 try-catch
 */
function tryCatch(fn) {
  return function () {
    try {
      return fn.apply(fn, arguments);
    } catch (e) {
      // TODO
      console.error(e);
    }
  };
}
function getApiCallbacks(params) {
  const apiCallbacks = {};
  for (const name in params) {
    const param = params[name];
    if (isFn(param)) {
      apiCallbacks[name] = tryCatch(param);
      delete params[name];
    }
  }
  return apiCallbacks;
}
let cid;
let cidErrMsg;
let enabled;
function normalizePushMessage(message) {
  try {
    return JSON.parse(message);
  } catch (e) {}
  return message;
}
function invokePushCallback(args) {
  if (args.type === 'enabled') {
    enabled = true;
  } else if (args.type === 'clientId') {
    cid = args.cid;
    cidErrMsg = args.errMsg;
    invokeGetPushCidCallbacks(cid, args.errMsg);
  } else if (args.type === 'pushMsg') {
    const message = {
      type: 'receive',
      data: normalizePushMessage(args.message)
    };
    for (let i = 0; i < onPushMessageCallbacks.length; i++) {
      const callback = onPushMessageCallbacks[i];
      callback(message);
      // 该消息已被阻止
      if (message.stopped) {
        break;
      }
    }
  } else if (args.type === 'click') {
    onPushMessageCallbacks.forEach(callback => {
      callback({
        type: 'click',
        data: normalizePushMessage(args.message)
      });
    });
  }
}
const getPushCidCallbacks = [];
function invokeGetPushCidCallbacks(cid, errMsg) {
  getPushCidCallbacks.forEach(callback => {
    callback(cid, errMsg);
  });
  getPushCidCallbacks.length = 0;
}
function getPushClientId(args) {
  if (!isPlainObject(args)) {
    args = {};
  }
  const {
    success,
    fail,
    complete
  } = getApiCallbacks(args);
  const hasSuccess = isFn(success);
  const hasFail = isFn(fail);
  const hasComplete = isFn(complete);
  Promise.resolve().then(() => {
    if (typeof enabled === 'undefined') {
      enabled = false;
      cid = '';
      cidErrMsg = 'uniPush is not enabled';
    }
    getPushCidCallbacks.push((cid, errMsg) => {
      let res;
      if (cid) {
        res = {
          errMsg: 'getPushClientId:ok',
          cid
        };
        hasSuccess && success(res);
      } else {
        res = {
          errMsg: 'getPushClientId:fail' + (errMsg ? ' ' + errMsg : '')
        };
        hasFail && fail(res);
      }
      hasComplete && complete(res);
    });
    if (typeof cid !== 'undefined') {
      invokeGetPushCidCallbacks(cid, cidErrMsg);
    }
  });
}
const onPushMessageCallbacks = [];
// 不使用 defineOnApi 实现，是因为 defineOnApi 依赖 UniServiceJSBridge ，该对象目前在小程序上未提供，故简单实现
const onPushMessage = fn => {
  if (onPushMessageCallbacks.indexOf(fn) === -1) {
    onPushMessageCallbacks.push(fn);
  }
};
const offPushMessage = fn => {
  if (!fn) {
    onPushMessageCallbacks.length = 0;
  } else {
    const index = onPushMessageCallbacks.indexOf(fn);
    if (index > -1) {
      onPushMessageCallbacks.splice(index, 1);
    }
  }
};
function __f__(type, ...args) {
  console[type].apply(console, args);
}
let baseInfo = wx.getAppBaseInfo && wx.getAppBaseInfo();
if (!baseInfo) {
  baseInfo = wx.getSystemInfoSync();
}
const host = baseInfo ? baseInfo.host : null;
const shareVideoMessage = host && host.env === 'SAAASDK' ? wx.miniapp.shareVideoMessage : wx.shareVideoMessage;
var api = /*#__PURE__*/Object.freeze({
  __proto__: null,
  shareVideoMessage: shareVideoMessage,
  getPushClientId: getPushClientId,
  onPushMessage: onPushMessage,
  offPushMessage: offPushMessage,
  invokePushCallback: invokePushCallback,
  __f__: __f__
});
const mocks = ['__route__', '__wxExparserNodeId__', '__wxWebviewId__'];
function findVmByVueId(vm, vuePid) {
  const $children = vm.$children;
  // 优先查找直属(反向查找:https://github.com/dcloudio/uni-app/issues/1200)
  for (let i = $children.length - 1; i >= 0; i--) {
    const childVm = $children[i];
    if (childVm.$scope._$vueId === vuePid) {
      return childVm;
    }
  }
  // 反向递归查找
  let parentVm;
  for (let i = $children.length - 1; i >= 0; i--) {
    parentVm = findVmByVueId($children[i], vuePid);
    if (parentVm) {
      return parentVm;
    }
  }
}
function initBehavior(options) {
  return Behavior(options);
}
function isPage() {
  return !!this.route;
}
function initRelation(detail) {
  this.triggerEvent('__l', detail);
}
function selectAllComponents(mpInstance, selector, $refs) {
  const components = mpInstance.selectAllComponents(selector) || [];
  components.forEach(component => {
    const ref = component.dataset.ref;
    $refs[ref] = component.$vm || toSkip(component);
    {
      if (component.dataset.vueGeneric === 'scoped') {
        component.selectAllComponents('.scoped-ref').forEach(scopedComponent => {
          selectAllComponents(scopedComponent, selector, $refs);
        });
      }
    }
  });
}
function syncRefs(refs, newRefs) {
  const oldKeys = new Set(...Object.keys(refs));
  const newKeys = Object.keys(newRefs);
  newKeys.forEach(key => {
    const oldValue = refs[key];
    const newValue = newRefs[key];
    if (Array.isArray(oldValue) && Array.isArray(newValue) && oldValue.length === newValue.length && newValue.every(value => oldValue.includes(value))) {
      return;
    }
    refs[key] = newValue;
    oldKeys.delete(key);
  });
  oldKeys.forEach(key => {
    delete refs[key];
  });
  return refs;
}
function initRefs(vm) {
  const mpInstance = vm.$scope;
  const refs = {};
  Object.defineProperty(vm, '$refs', {
    get() {
      const $refs = {};
      selectAllComponents(mpInstance, '.vue-ref', $refs);
      // TODO 暂不考虑 for 中的 scoped
      const forComponents = mpInstance.selectAllComponents('.vue-ref-in-for') || [];
      forComponents.forEach(component => {
        const ref = component.dataset.ref;
        if (!$refs[ref]) {
          $refs[ref] = [];
        }
        $refs[ref].push(component.$vm || toSkip(component));
      });
      return syncRefs(refs, $refs);
    }
  });
}
function handleLink(event) {
  const {
    vuePid,
    vueOptions
  } = event.detail || event.value; // detail 是微信,value 是百度(dipatch)

  let parentVm;
  if (vuePid) {
    parentVm = findVmByVueId(this.$vm, vuePid);
  }
  if (!parentVm) {
    parentVm = this.$vm;
  }
  vueOptions.parent = parentVm;
}
function markMPComponent(component) {
  // 在 Vue 中标记为小程序组件
  const IS_MP = '__v_isMPComponent';
  Object.defineProperty(component, IS_MP, {
    configurable: true,
    enumerable: false,
    value: true
  });
  return component;
}
function toSkip(obj) {
  const OB = '__ob__';
  const SKIP = '__v_skip';
  if (isObject(obj) && Object.isExtensible(obj)) {
    // 避免被 @vue/composition-api 观测
    Object.defineProperty(obj, OB, {
      configurable: true,
      enumerable: false,
      value: {
        [SKIP]: true
      }
    });
  }
  return obj;
}
const WORKLET_RE = /_(.*)_worklet_factory_/;
function initWorkletMethods(mpMethods, vueMethods) {
  if (vueMethods) {
    Object.keys(vueMethods).forEach(name => {
      const matches = name.match(WORKLET_RE);
      if (matches) {
        const workletName = matches[1];
        mpMethods[name] = vueMethods[name];
        mpMethods[workletName] = vueMethods[workletName];
      }
    });
  }
}
const MPPage = Page;
const MPComponent = Component;
const customizeRE = /:/g;
const customize = cached(str => {
  return camelize(str.replace(customizeRE, '-'));
});
function initTriggerEvent(mpInstance) {
  const oldTriggerEvent = mpInstance.triggerEvent;
  const newTriggerEvent = function (event, ...args) {
    // 事件名统一转驼峰格式，仅处理：当前组件为 vue 组件、当前组件为 vue 组件子组件
    if (this.$vm || this.dataset && this.dataset.comType) {
      event = customize(event);
    } else {
      // 针对微信/QQ小程序单独补充驼峰格式事件，以兼容历史项目
      const newEvent = customize(event);
      if (newEvent !== event) {
        oldTriggerEvent.apply(this, [newEvent, ...args]);
      }
    }
    return oldTriggerEvent.apply(this, [event, ...args]);
  };
  try {
    // 京东小程序 triggerEvent 为只读
    mpInstance.triggerEvent = newTriggerEvent;
  } catch (error) {
    mpInstance._triggerEvent = newTriggerEvent;
  }
}
function initHook(name, options, isComponent) {
  const oldHook = options[name];
  options[name] = function (...args) {
    markMPComponent(this);
    initTriggerEvent(this);
    if (oldHook) {
      return oldHook.apply(this, args);
    }
  };
}
if (!MPPage.__$wrappered) {
  MPPage.__$wrappered = true;
  Page = function (options = {}) {
    initHook('onLoad', options);
    return MPPage(options);
  };
  Page.after = MPPage.after;
  Component = function (options = {}) {
    initHook('created', options);
    return MPComponent(options);
  };
}
const PAGE_EVENT_HOOKS = ['onPullDownRefresh', 'onReachBottom', 'onAddToFavorites', 'onShareTimeline', 'onShareAppMessage', 'onPageScroll', 'onResize', 'onTabItemTap'];
function initMocks(vm, mocks) {
  const mpInstance = vm.$mp[vm.mpType];
  mocks.forEach(mock => {
    if (hasOwn(mpInstance, mock)) {
      vm[mock] = mpInstance[mock];
    }
  });
}
function hasHook(hook, vueOptions) {
  if (!vueOptions) {
    return true;
  }
  if (vue__WEBPACK_IMPORTED_MODULE_1__["default"].options && Array.isArray(vue__WEBPACK_IMPORTED_MODULE_1__["default"].options[hook])) {
    return true;
  }
  vueOptions = vueOptions.default || vueOptions;
  if (isFn(vueOptions)) {
    if (isFn(vueOptions.extendOptions[hook])) {
      return true;
    }
    if (vueOptions.super && vueOptions.super.options && Array.isArray(vueOptions.super.options[hook])) {
      return true;
    }
    return false;
  }
  if (isFn(vueOptions[hook]) || Array.isArray(vueOptions[hook])) {
    return true;
  }
  const mixins = vueOptions.mixins;
  if (Array.isArray(mixins)) {
    return !!mixins.find(mixin => hasHook(hook, mixin));
  }
}
function initHooks(mpOptions, hooks, vueOptions) {
  hooks.forEach(hook => {
    if (hasHook(hook, vueOptions)) {
      mpOptions[hook] = function (args) {
        return this.$vm && this.$vm.__call_hook(hook, args);
      };
    }
  });
}
function initUnknownHooks(mpOptions, vueOptions, excludes = []) {
  findHooks(vueOptions).forEach(hook => initHook$1(mpOptions, hook, excludes));
}
function findHooks(vueOptions, hooks = []) {
  if (vueOptions) {
    Object.keys(vueOptions).forEach(name => {
      if (name.indexOf('on') === 0 && isFn(vueOptions[name])) {
        hooks.push(name);
      }
    });
  }
  return hooks;
}
function initHook$1(mpOptions, hook, excludes) {
  if (excludes.indexOf(hook) === -1 && !hasOwn(mpOptions, hook)) {
    mpOptions[hook] = function (args) {
      return this.$vm && this.$vm.__call_hook(hook, args);
    };
  }
}
function initVueComponent(Vue, vueOptions) {
  vueOptions = vueOptions.default || vueOptions;
  let VueComponent;
  if (isFn(vueOptions)) {
    VueComponent = vueOptions;
  } else {
    VueComponent = Vue.extend(vueOptions);
  }
  vueOptions = VueComponent.options;
  return [VueComponent, vueOptions];
}
function initSlots(vm, vueSlots) {
  if (Array.isArray(vueSlots) && vueSlots.length) {
    const $slots = Object.create(null);
    vueSlots.forEach(slotName => {
      $slots[slotName] = true;
    });
    vm.$scopedSlots = vm.$slots = $slots;
  }
}
function initVueIds(vueIds, mpInstance) {
  vueIds = (vueIds || '').split(',');
  const len = vueIds.length;
  if (len === 1) {
    mpInstance._$vueId = vueIds[0];
  } else if (len === 2) {
    mpInstance._$vueId = vueIds[0];
    mpInstance._$vuePid = vueIds[1];
  }
}
function initData(vueOptions, context) {
  let data = vueOptions.data || {};
  const methods = vueOptions.methods || {};
  if (typeof data === 'function') {
    try {
      data = data.call(context); // 支持 Vue.prototype 上挂的数据
    } catch (e) {
      if (Object({"NODE_ENV":"development","VUE_APP_DARK_MODE":"false","VUE_APP_NAME":"商城","VUE_APP_PLATFORM":"mp-weixin","BASE_URL":"/"}).VUE_APP_DEBUG) {
        console.warn('根据 Vue 的 data 函数初始化小程序 data 失败，请尽量确保 data 函数中不访问 vm 对象，否则可能影响首次数据渲染速度。', data);
      }
    }
  } else {
    try {
      // 对 data 格式化
      data = JSON.parse(JSON.stringify(data));
    } catch (e) {}
  }
  if (!isPlainObject(data)) {
    data = {};
  }
  Object.keys(methods).forEach(methodName => {
    if (context.__lifecycle_hooks__.indexOf(methodName) === -1 && !hasOwn(data, methodName)) {
      data[methodName] = methods[methodName];
    }
  });
  return data;
}
const PROP_TYPES = [String, Number, Boolean, Object, Array, null];
function createObserver(name) {
  return function observer(newVal, oldVal) {
    if (this.$vm) {
      this.$vm[name] = newVal; // 为了触发其他非 render watcher
    }
  };
}
function initBehaviors(vueOptions, initBehavior) {
  const vueBehaviors = vueOptions.behaviors;
  const vueExtends = vueOptions.extends;
  const vueMixins = vueOptions.mixins;
  let vueProps = vueOptions.props;
  if (!vueProps) {
    vueOptions.props = vueProps = [];
  }
  const behaviors = [];
  if (Array.isArray(vueBehaviors)) {
    vueBehaviors.forEach(behavior => {
      behaviors.push(behavior.replace('uni://', `${"wx"}://`));
      if (behavior === 'uni://form-field') {
        if (Array.isArray(vueProps)) {
          vueProps.push('name');
          vueProps.push('value');
        } else {
          vueProps.name = {
            type: String,
            default: ''
          };
          vueProps.value = {
            type: [String, Number, Boolean, Array, Object, Date],
            default: ''
          };
        }
      }
    });
  }
  if (isPlainObject(vueExtends) && vueExtends.props) {
    behaviors.push(initBehavior({
      properties: initProperties(vueExtends.props, true)
    }));
  }
  if (Array.isArray(vueMixins)) {
    vueMixins.forEach(vueMixin => {
      if (isPlainObject(vueMixin) && vueMixin.props) {
        behaviors.push(initBehavior({
          properties: initProperties(vueMixin.props, true)
        }));
      }
    });
  }
  return behaviors;
}
function parsePropType(key, type, defaultValue, file) {
  // [String]=>String
  if (Array.isArray(type) && type.length === 1) {
    return type[0];
  }
  return type;
}
function initProperties(props, isBehavior = false, file = '', options) {
  const properties = {};
  if (!isBehavior) {
    properties.vueId = {
      type: String,
      value: ''
    };
    {
      if (options.virtualHost) {
        properties.virtualHostStyle = {
          type: null,
          value: ''
        };
        properties.virtualHostClass = {
          type: null,
          value: ''
        };
      }
    }
    // scopedSlotsCompiler auto
    properties.scopedSlotsCompiler = {
      type: String,
      value: ''
    };
    properties.vueSlots = {
      // 小程序不能直接定义 $slots 的 props，所以通过 vueSlots 转换到 $slots
      type: null,
      value: [],
      observer: function (newVal, oldVal) {
        const $slots = Object.create(null);
        newVal.forEach(slotName => {
          $slots[slotName] = true;
        });
        this.setData({
          $slots
        });
      }
    };
  }
  if (Array.isArray(props)) {
    // ['title']
    props.forEach(key => {
      properties[key] = {
        type: null,
        observer: createObserver(key)
      };
    });
  } else if (isPlainObject(props)) {
    // {title:{type:String,default:''},content:String}
    Object.keys(props).forEach(key => {
      const opts = props[key];
      if (isPlainObject(opts)) {
        // title:{type:String,default:''}
        let value = opts.default;
        if (isFn(value)) {
          value = value();
        }
        opts.type = parsePropType(key, opts.type);
        properties[key] = {
          type: PROP_TYPES.indexOf(opts.type) !== -1 ? opts.type : null,
          value,
          observer: createObserver(key)
        };
      } else {
        // content:String
        const type = parsePropType(key, opts);
        properties[key] = {
          type: PROP_TYPES.indexOf(type) !== -1 ? type : null,
          observer: createObserver(key)
        };
      }
    });
  }
  return properties;
}
function wrapper$1(event) {
  // TODO 又得兼容 mpvue 的 mp 对象
  try {
    event.mp = JSON.parse(JSON.stringify(event));
  } catch (e) {}
  event.stopPropagation = noop;
  event.preventDefault = noop;
  event.target = event.target || {};
  if (!hasOwn(event, 'detail')) {
    event.detail = {};
  }
  if (hasOwn(event, 'markerId')) {
    event.detail = typeof event.detail === 'object' ? event.detail : {};
    event.detail.markerId = event.markerId;
  }
  if (isPlainObject(event.detail)) {
    event.target = Object.assign({}, event.target, event.detail);
  }
  return event;
}
function getExtraValue(vm, dataPathsArray) {
  let context = vm;
  dataPathsArray.forEach(dataPathArray => {
    const dataPath = dataPathArray[0];
    const value = dataPathArray[2];
    if (dataPath || typeof value !== 'undefined') {
      // ['','',index,'disable']
      const propPath = dataPathArray[1];
      const valuePath = dataPathArray[3];
      let vFor;
      if (Number.isInteger(dataPath)) {
        vFor = dataPath;
      } else if (!dataPath) {
        vFor = context;
      } else if (typeof dataPath === 'string' && dataPath) {
        if (dataPath.indexOf('#s#') === 0) {
          vFor = dataPath.substr(3);
        } else {
          vFor = vm.__get_value(dataPath, context);
        }
      }
      if (Number.isInteger(vFor)) {
        context = value;
      } else if (!propPath) {
        context = vFor[value];
      } else {
        if (Array.isArray(vFor)) {
          context = vFor.find(vForItem => {
            return vm.__get_value(propPath, vForItem) === value;
          });
        } else if (isPlainObject(vFor)) {
          context = Object.keys(vFor).find(vForKey => {
            return vm.__get_value(propPath, vFor[vForKey]) === value;
          });
        } else {
          console.error('v-for 暂不支持循环数据：', vFor);
        }
      }
      if (valuePath) {
        context = vm.__get_value(valuePath, context);
      }
    }
  });
  return context;
}
function processEventExtra(vm, extra, event, __args__) {
  const extraObj = {};
  if (Array.isArray(extra) && extra.length) {
    /**
     *[
     *    ['data.items', 'data.id', item.data.id],
     *    ['metas', 'id', meta.id]
     *],
     *[
     *    ['data.items', 'data.id', item.data.id],
     *    ['metas', 'id', meta.id]
     *],
     *'test'
     */
    extra.forEach((dataPath, index) => {
      if (typeof dataPath === 'string') {
        if (!dataPath) {
          // model,prop.sync
          extraObj['$' + index] = vm;
        } else {
          if (dataPath === '$event') {
            // $event
            extraObj['$' + index] = event;
          } else if (dataPath === 'arguments') {
            extraObj['$' + index] = event.detail ? event.detail.__args__ || __args__ : __args__;
          } else if (dataPath.indexOf('$event.') === 0) {
            // $event.target.value
            extraObj['$' + index] = vm.__get_value(dataPath.replace('$event.', ''), event);
          } else {
            extraObj['$' + index] = vm.__get_value(dataPath);
          }
        }
      } else {
        extraObj['$' + index] = getExtraValue(vm, dataPath);
      }
    });
  }
  return extraObj;
}
function getObjByArray(arr) {
  const obj = {};
  for (let i = 1; i < arr.length; i++) {
    const element = arr[i];
    obj[element[0]] = element[1];
  }
  return obj;
}
function processEventArgs(vm, event, args = [], extra = [], isCustom, methodName) {
  let isCustomMPEvent = false; // wxcomponent 组件，传递原始 event 对象

  // fixed 用户直接触发 mpInstance.triggerEvent
  const __args__ = isPlainObject(event.detail) ? event.detail.__args__ || [event.detail] : [event.detail];
  if (isCustom) {
    // 自定义事件
    isCustomMPEvent = event.currentTarget && event.currentTarget.dataset && event.currentTarget.dataset.comType === 'wx';
    if (!args.length) {
      // 无参数，直接传入 event 或 detail 数组
      if (isCustomMPEvent) {
        return [event];
      }
      return __args__;
    }
  }
  const extraObj = processEventExtra(vm, extra, event, __args__);
  const ret = [];
  args.forEach(arg => {
    if (arg === '$event') {
      if (methodName === '__set_model' && !isCustom) {
        // input v-model value
        ret.push(event.target.value);
      } else {
        if (isCustom && !isCustomMPEvent) {
          ret.push(__args__[0]);
        } else {
          // wxcomponent 组件或内置组件
          ret.push(event);
        }
      }
    } else {
      if (Array.isArray(arg) && arg[0] === 'o') {
        ret.push(getObjByArray(arg));
      } else if (typeof arg === 'string' && hasOwn(extraObj, arg)) {
        ret.push(extraObj[arg]);
      } else {
        ret.push(arg);
      }
    }
  });
  return ret;
}
const ONCE = '~';
const CUSTOM = '^';
function isMatchEventType(eventType, optType) {
  return eventType === optType || optType === 'regionchange' && (eventType === 'begin' || eventType === 'end');
}
function getContextVm(vm) {
  let $parent = vm.$parent;
  // 父组件是 scoped slots 或者其他自定义组件时继续查找
  while ($parent && $parent.$parent && ($parent.$options.generic || $parent.$parent.$options.generic || $parent.$scope._$vuePid)) {
    $parent = $parent.$parent;
  }
  return $parent && $parent.$parent;
}
function handleEvent(event) {
  event = wrapper$1(event);

  // [['tap',[['handle',[1,2,a]],['handle1',[1,2,a]]]]]
  const dataset = (event.currentTarget || event.target).dataset;
  if (!dataset) {
    return console.warn('事件信息不存在');
  }
  const eventOpts = dataset.eventOpts || dataset['event-opts']; // 支付宝 web-view 组件 dataset 非驼峰
  if (!eventOpts) {
    return console.warn('事件信息不存在');
  }

  // [['handle',[1,2,a]],['handle1',[1,2,a]]]
  const eventType = event.type;
  const ret = [];
  eventOpts.forEach(eventOpt => {
    let type = eventOpt[0];
    const eventsArray = eventOpt[1];
    const isCustom = type.charAt(0) === CUSTOM;
    type = isCustom ? type.slice(1) : type;
    const isOnce = type.charAt(0) === ONCE;
    type = isOnce ? type.slice(1) : type;
    if (eventsArray && isMatchEventType(eventType, type)) {
      eventsArray.forEach(eventArray => {
        const methodName = eventArray[0];
        if (methodName) {
          let handlerCtx = this.$vm;
          if (handlerCtx.$options.generic) {
            // mp-weixin,mp-toutiao 抽象节点模拟 scoped slots
            handlerCtx = getContextVm(handlerCtx) || handlerCtx;
          }
          if (methodName === '$emit') {
            handlerCtx.$emit.apply(handlerCtx, processEventArgs(this.$vm, event, eventArray[1], eventArray[2], isCustom, methodName));
            return;
          }
          const handler = handlerCtx[methodName];
          if (!isFn(handler)) {
            const type = this.$vm.mpType === 'page' ? 'Page' : 'Component';
            const path = this.route || this.is;
            throw new Error(`${type} "${path}" does not have a method "${methodName}"`);
          }
          if (isOnce) {
            if (handler.once) {
              return;
            }
            handler.once = true;
          }
          let params = processEventArgs(this.$vm, event, eventArray[1], eventArray[2], isCustom, methodName);
          params = Array.isArray(params) ? params : [];
          // 参数尾部增加原始事件对象用于复杂表达式内获取额外数据
          if (/=\s*\S+\.eventParams\s*\|\|\s*\S+\[['"]event-params['"]\]/.test(handler.toString())) {
            // eslint-disable-next-line no-sparse-arrays
            params = params.concat([,,,,,,,,,, event]);
          }
          ret.push(handler.apply(handlerCtx, params));
        }
      });
    }
  });
  if (eventType === 'input' && ret.length === 1 && typeof ret[0] !== 'undefined') {
    return ret[0];
  }
}
const eventChannels = {};
function getEventChannel(id) {
  const eventChannel = eventChannels[id];
  delete eventChannels[id];
  return eventChannel;
}
const hooks = ['onShow', 'onHide', 'onError', 'onPageNotFound', 'onThemeChange', 'onUnhandledRejection'];
function initEventChannel() {
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.getOpenerEventChannel = function () {
    // 微信小程序使用自身getOpenerEventChannel
    {
      return this.$scope.getOpenerEventChannel();
    }
  };
  const callHook = vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.__call_hook;
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.__call_hook = function (hook, args) {
    if (hook === 'onLoad' && args && args.__id__) {
      this.__eventChannel__ = getEventChannel(args.__id__);
      delete args.__id__;
    }
    return callHook.call(this, hook, args);
  };
}
function initScopedSlotsParams() {
  const center = {};
  const parents = {};
  function currentId(fn) {
    const vueIds = this.$options.propsData.vueId;
    if (vueIds) {
      const vueId = vueIds.split(',')[0];
      fn(vueId);
    }
  }
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.$hasSSP = function (vueId) {
    const slot = center[vueId];
    if (!slot) {
      parents[vueId] = this;
      this.$on('hook:destroyed', () => {
        delete parents[vueId];
      });
    }
    return slot;
  };
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.$getSSP = function (vueId, name, needAll) {
    const slot = center[vueId];
    if (slot) {
      const params = slot[name] || [];
      if (needAll) {
        return params;
      }
      return params[0];
    }
  };
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.$setSSP = function (name, value) {
    let index = 0;
    currentId.call(this, vueId => {
      const slot = center[vueId];
      const params = slot[name] = slot[name] || [];
      params.push(value);
      index = params.length - 1;
    });
    return index;
  };
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.$initSSP = function () {
    currentId.call(this, vueId => {
      center[vueId] = {};
    });
  };
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.$callSSP = function () {
    currentId.call(this, vueId => {
      if (parents[vueId]) {
        parents[vueId].$forceUpdate();
      }
    });
  };
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].mixin({
    destroyed() {
      const propsData = this.$options.propsData;
      const vueId = propsData && propsData.vueId;
      if (vueId) {
        delete center[vueId];
        delete parents[vueId];
      }
    }
  });
}
function parseBaseApp(vm, {
  mocks,
  initRefs
}) {
  initEventChannel();
  {
    initScopedSlotsParams();
  }
  if (vm.$options.store) {
    vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.$store = vm.$options.store;
  }
  uniIdMixin(vue__WEBPACK_IMPORTED_MODULE_1__["default"]);
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype.mpHost = "mp-weixin";
  vue__WEBPACK_IMPORTED_MODULE_1__["default"].mixin({
    beforeCreate() {
      if (!this.$options.mpType) {
        return;
      }
      this.mpType = this.$options.mpType;
      this.$mp = {
        data: {},
        [this.mpType]: this.$options.mpInstance
      };
      this.$scope = this.$options.mpInstance;
      delete this.$options.mpType;
      delete this.$options.mpInstance;
      if (this.mpType === 'page' && typeof getApp === 'function') {
        // hack vue-i18n
        const app = getApp();
        if (app.$vm && app.$vm.$i18n) {
          this._i18n = app.$vm.$i18n;
        }
      }
      if (this.mpType !== 'app') {
        initRefs(this);
        initMocks(this, mocks);
      }
    }
  });
  const appOptions = {
    onLaunch(args) {
      if (this.$vm) {
        // 已经初始化过了，主要是为了百度，百度 onShow 在 onLaunch 之前
        return;
      }
      {
        if (wx.canIUse && !wx.canIUse('nextTick')) {
          // 事实 上2.2.3 即可，简单使用 2.3.0 的 nextTick 判断
          console.error('当前微信基础库版本过低，请将 微信开发者工具-详情-项目设置-调试基础库版本 更换为`2.3.0`以上');
        }
      }
      this.$vm = vm;
      this.$vm.$mp = {
        app: this
      };
      this.$vm.$scope = this;
      // vm 上也挂载 globalData
      this.$vm.globalData = this.globalData;
      this.$vm._isMounted = true;
      this.$vm.__call_hook('mounted', args);
      this.$vm.__call_hook('onLaunch', args);
    }
  };

  // 兼容旧版本 globalData
  appOptions.globalData = vm.$options.globalData || {};
  // 将 methods 中的方法挂在 getApp() 中
  const methods = vm.$options.methods;
  if (methods) {
    Object.keys(methods).forEach(name => {
      appOptions[name] = methods[name];
    });
  }
  initAppLocale(vue__WEBPACK_IMPORTED_MODULE_1__["default"], vm, getLocaleLanguage$1());
  initHooks(appOptions, hooks);
  initUnknownHooks(appOptions, vm.$options);
  return appOptions;
}
function getLocaleLanguage$1() {
  let localeLanguage = '';
  {
    const appBaseInfo = wx.getAppBaseInfo();
    const language = appBaseInfo && appBaseInfo.language ? appBaseInfo.language : LOCALE_EN;
    localeLanguage = normalizeLocale(language) || LOCALE_EN;
  }
  return localeLanguage;
}
function parseApp(vm) {
  return parseBaseApp(vm, {
    mocks,
    initRefs
  });
}
function createApp(vm) {
  App(parseApp(vm));
  return vm;
}
const encodeReserveRE = /[!'()*]/g;
const encodeReserveReplacer = c => '%' + c.charCodeAt(0).toString(16);
const commaRE = /%2C/g;

// fixed encodeURIComponent which is more conformant to RFC3986:
// - escapes [!'()*]
// - preserve commas
const encode = str => encodeURIComponent(str).replace(encodeReserveRE, encodeReserveReplacer).replace(commaRE, ',');
function stringifyQuery(obj, encodeStr = encode) {
  const res = obj ? Object.keys(obj).map(key => {
    const val = obj[key];
    if (val === undefined) {
      return '';
    }
    if (val === null) {
      return encodeStr(key);
    }
    if (Array.isArray(val)) {
      const result = [];
      val.forEach(val2 => {
        if (val2 === undefined) {
          return;
        }
        if (val2 === null) {
          result.push(encodeStr(key));
        } else {
          result.push(encodeStr(key) + '=' + encodeStr(val2));
        }
      });
      return result.join('&');
    }
    return encodeStr(key) + '=' + encodeStr(val);
  }).filter(x => x.length > 0).join('&') : null;
  return res ? `?${res}` : '';
}
function parseBaseComponent(vueComponentOptions, {
  isPage,
  initRelation
} = {}, needVueOptions) {
  const [VueComponent, vueOptions] = initVueComponent(vue__WEBPACK_IMPORTED_MODULE_1__["default"], vueComponentOptions);
  const options = {
    multipleSlots: true,
    // styleIsolation: 'apply-shared',
    addGlobalClass: true,
    ...(vueOptions.options || {})
  };
  {
    // 微信 multipleSlots 部分情况有 bug，导致内容顺序错乱 如 u-list，提供覆盖选项
    if (vueOptions['mp-weixin'] && vueOptions['mp-weixin'].options) {
      Object.assign(options, vueOptions['mp-weixin'].options);
    }
  }
  const componentOptions = {
    options,
    data: initData(vueOptions, vue__WEBPACK_IMPORTED_MODULE_1__["default"].prototype),
    behaviors: initBehaviors(vueOptions, initBehavior),
    properties: initProperties(vueOptions.props, false, vueOptions.__file, options),
    lifetimes: {
      attached() {
        const properties = this.properties;
        const options = {
          mpType: isPage.call(this) ? 'page' : 'component',
          mpInstance: this,
          propsData: properties
        };
        initVueIds(properties.vueId, this);

        // 处理父子关系
        initRelation.call(this, {
          vuePid: this._$vuePid,
          vueOptions: options
        });

        // 初始化 vue 实例
        this.$vm = new VueComponent(options);

        // 处理$slots,$scopedSlots（暂不支持动态变化$slots）
        initSlots(this.$vm, properties.vueSlots);

        // 触发首次 setData
        this.$vm.$mount();
      },
      ready() {
        // 当组件 props 默认值为 true，初始化时传入 false 会导致 created,ready 触发, 但 attached 不触发
        // https://developers.weixin.qq.com/community/develop/doc/00066ae2844cc0f8eb883e2a557800
        if (this.$vm) {
          this.$vm._isMounted = true;
          this.$vm.__call_hook('mounted');
          this.$vm.__call_hook('onReady');
        }
      },
      detached() {
        this.$vm && this.$vm.$destroy();
      }
    },
    pageLifetimes: {
      show(args) {
        this.$vm && this.$vm.__call_hook('onPageShow', args);
      },
      hide() {
        this.$vm && this.$vm.__call_hook('onPageHide');
      },
      resize(size) {
        this.$vm && this.$vm.__call_hook('onPageResize', size);
      }
    },
    methods: {
      __l: handleLink,
      __e: handleEvent
    }
  };
  // externalClasses
  if (vueOptions.externalClasses) {
    componentOptions.externalClasses = vueOptions.externalClasses;
  }
  if (Array.isArray(vueOptions.wxsCallMethods)) {
    vueOptions.wxsCallMethods.forEach(callMethod => {
      componentOptions.methods[callMethod] = function (args) {
        return this.$vm[callMethod](args);
      };
    });
  }
  if (needVueOptions) {
    return [componentOptions, vueOptions, VueComponent];
  }
  if (isPage) {
    return componentOptions;
  }
  return [componentOptions, VueComponent];
}
function parseComponent(vueComponentOptions, needVueOptions) {
  return parseBaseComponent(vueComponentOptions, {
    isPage,
    initRelation
  }, needVueOptions);
}
const hooks$1 = ['onShow', 'onHide', 'onUnload'];
hooks$1.push(...PAGE_EVENT_HOOKS);
function parseBasePage(vuePageOptions) {
  const [pageOptions, vueOptions] = parseComponent(vuePageOptions, true);
  initHooks(pageOptions.methods, hooks$1, vueOptions);
  pageOptions.methods.onLoad = function (query) {
    this.options = query;
    const copyQuery = Object.assign({}, query);
    delete copyQuery.__id__;
    this.$page = {
      fullPath: '/' + (this.route || this.is) + stringifyQuery(copyQuery)
    };
    // 微信基础库 3.x 中页面 onLoad 可能早于 uni-app 初始化 $mp。
    // 先补齐兼容对象，避免 Cannot set property query of undefined。
    if (!this.$vm.$mp) {
      this.$vm.$mp = {
        data: {},
        page: this
      };
    }
    this.$vm.$mp.query = query; // 兼容 mpvue
    this.$vm.__call_hook('onLoad', query);
  };
  {
    initUnknownHooks(pageOptions.methods, vuePageOptions, ['onReady']);
  }
  {
    initWorkletMethods(pageOptions.methods, vueOptions.methods);
  }
  return pageOptions;
}
function parsePage(vuePageOptions) {
  return parseBasePage(vuePageOptions);
}
function createPage(vuePageOptions) {
  {
    return Component(parsePage(vuePageOptions));
  }
}
function createComponent(vueOptions) {
  {
    return Component(parseComponent(vueOptions));
  }
}
function createSubpackageApp(vm) {
  const appOptions = parseApp(vm);
  const app = getApp({
    allowDefault: true
  });
  vm.$scope = app;
  const globalData = app.globalData;
  if (globalData) {
    Object.keys(appOptions.globalData).forEach(name => {
      if (!hasOwn(globalData, name)) {
        globalData[name] = appOptions.globalData[name];
      }
    });
  }
  Object.keys(appOptions).forEach(name => {
    if (!hasOwn(app, name)) {
      app[name] = appOptions[name];
    }
  });
  if (isFn(appOptions.onShow) && wx.onAppShow) {
    wx.onAppShow((...args) => {
      vm.__call_hook('onShow', args);
    });
  }
  if (isFn(appOptions.onHide) && wx.onAppHide) {
    wx.onAppHide((...args) => {
      vm.__call_hook('onHide', args);
    });
  }
  if (isFn(appOptions.onLaunch)) {
    const args = wx.getLaunchOptionsSync && wx.getLaunchOptionsSync();
    vm.__call_hook('onLaunch', args);
  }
  return vm;
}
function createPlugin(vm) {
  const appOptions = parseApp(vm);
  if (isFn(appOptions.onShow) && wx.onAppShow) {
    wx.onAppShow((...args) => {
      vm.__call_hook('onShow', args);
    });
  }
  if (isFn(appOptions.onHide) && wx.onAppHide) {
    wx.onAppHide((...args) => {
      vm.__call_hook('onHide', args);
    });
  }
  if (isFn(appOptions.onLaunch)) {
    const args = wx.getLaunchOptionsSync && wx.getLaunchOptionsSync();
    vm.__call_hook('onLaunch', args);
  }
  return vm;
}
todos.forEach(todoApi => {
  protocols[todoApi] = false;
});
canIUses.forEach(canIUseApi => {
  const apiName = protocols[canIUseApi] && protocols[canIUseApi].name ? protocols[canIUseApi].name : canIUseApi;
  if (!wx.canIUse(apiName)) {
    protocols[canIUseApi] = false;
  }
});
let uni = {};
if (typeof Proxy !== 'undefined' && "mp-weixin" !== 'app-plus') {
  uni = new Proxy({}, {
    get(target, name) {
      if (hasOwn(target, name)) {
        return target[name];
      }
      if (baseApi[name]) {
        return baseApi[name];
      }
      if (api[name]) {
        return promisify(name, api[name]);
      }
      {
        if (extraApi[name]) {
          return promisify(name, extraApi[name]);
        }
        if (todoApis[name]) {
          return promisify(name, todoApis[name]);
        }
      }
      if (eventApi[name]) {
        return eventApi[name];
      }
      return promisify(name, wrapper(name, wx[name]));
    },
    set(target, name, value) {
      target[name] = value;
      return true;
    }
  });
} else {
  Object.keys(baseApi).forEach(name => {
    uni[name] = baseApi[name];
  });
  {
    Object.keys(todoApis).forEach(name => {
      uni[name] = promisify(name, todoApis[name]);
    });
    Object.keys(extraApi).forEach(name => {
      uni[name] = promisify(name, extraApi[name]);
    });
  }
  Object.keys(eventApi).forEach(name => {
    uni[name] = eventApi[name];
  });
  Object.keys(api).forEach(name => {
    uni[name] = promisify(name, api[name]);
  });
  Object.keys(wx).forEach(name => {
    if (hasOwn(wx, name) || hasOwn(protocols, name)) {
      uni[name] = promisify(name, wrapper(name, wx[name]));
    }
  });
}
wx.createApp = createApp;
wx.createPage = createPage;
wx.createComponent = createComponent;
wx.createSubpackageApp = createSubpackageApp;
wx.createPlugin = createPlugin;
var uni$1 = uni;
/* harmony default export */ __webpack_exports__["default"] = (uni$1);

/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/wx.js */ 1)["default"], __webpack_require__(/*! ./../../../webpack/buildin/global.js */ 3)))

/***/ }),

/***/ 20:
/*!************************!*\
  !*** ./common/util.js ***!
  \************************/
/*! exports provided: strlen, isWeiXinBrowser, getQueryString, getPath, uniCopy, setDb, getDb, getCachedImage, setTabbar, getByteSize */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "strlen", function() { return strlen; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "isWeiXinBrowser", function() { return isWeiXinBrowser; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "getQueryString", function() { return getQueryString; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "getPath", function() { return getPath; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "uniCopy", function() { return uniCopy; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "setDb", function() { return setDb; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "getDb", function() { return getDb; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "getCachedImage", function() { return getCachedImage; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "setTabbar", function() { return setTabbar; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "getByteSize", function() { return getByteSize; });
function strlen(value) {
  //中文、中文标点、全角字符按1长度，英文、英文符号、数字按0.5长度计算
  let cnReg = /([\u4e00-\u9fa5]|[\u3000-\u303F]|[\uFF00-\uFF60])/g;
  let mat = value.match(cnReg);
  let length = 0;
  if (mat) {
    return length = mat.length + (value.length - mat.length) * 0.5;
  } else {
    return length = value.length * 0.5;
  }
}

/**
 * 获取字节大小
 * @param {string} value
 * @return int
 */
function getByteSize(value) {
  let reg = new RegExp("^([0-9\.]+)([a-zA-Z]+)$", "g");
  let ret = reg.exec(value);
  if (ret) {
    let type = ret[2].toLowerCase();
    let typeDict = {
      'b': 0,
      'k': 1,
      'kb': 1,
      'm': 2,
      'mb': 2,
      'gb': 3,
      'g': 3
    };
    let size = parseInt(parseInt(ret[1]) * Math.pow(1024, typeDict[type] || 0));
    return size;
  } else {
    return parseInt(value);
  }
}

/**
 *
 *  判断是否在微信浏览器 true是
 */
function isWeiXinBrowser() {
  return false;
}

/**
 * 获取url参数
 * @param {*} name
 * @param {*} url
 * @returns
 */
function getQueryString(name, url) {
  var url = url || window.location.href;
  var regex = new RegExp("[?&/]" + name + "([=/]([^&#/?]*)|&|#|$)", "i"),
    results = regex.exec(url);
  if (!results) return null;
  return results[2] || '';
}

//路径转化
function getPath(path) {
  return path ? path.split('?').shift() : path;
}

//复制内容
function uniCopy({
  content,
  success,
  error
}) {
  content = typeof content === 'string' ? content : content.toString(); // 复制内容，必须字符串，数字需要转换为字符串

  /**
   * 小程序端 和 app端的复制逻辑
   */

  uni.setClipboardData({
    data: content,
    success: function () {
      success("复制成功~");
    },
    fail: function () {
      error("复制失败~");
    }
  });

  /**
   * H5端的复制逻辑
   */
}

//设置缓存
function setDb(name, value, db_time = 7200) {
  let time = new Date().getTime();
  let data = {
    value: value,
    time: time,
    db_time: db_time
  };
  uni.setStorageSync(name, data);
}
//获取缓存
function getDb(name) {
  try {
    let res = uni.getStorageSync(name);
    if (!res) {
      return '';
    }
    let time = new Date().getTime();
    if ((time - res.time) / 1000 >= res.db_time) {
      uni.removeStorageSync(name);
      return '';
    }
    return res.value;
  } catch (e) {
    //TODO handle the exception
    return '';
  }
}

/**
 * 下载图片
 */
function getCachedImage(image_url) {
  return new Promise((resolve, reject) => {
    let arr = image_url.split('/');
    let image_name = arr[arr.length - 1];
    var u = getDb('shop' + image_name);
    if (u) {
      resolve(u);
    } else {
      // 本地没有缓存 需要下载
      uni.downloadFile({
        url: image_url,
        success: res => {
          if (res.statusCode === 200) {
            uni.saveFile({
              tempFilePath: res.tempFilePath,
              success: function (res) {
                setDb('shop' + image_name, res.savedFilePath);
                resolve(res.savedFilePath);
              }
            });
          } else {
            reject('下载失败');
          }
        },
        fail: function () {
          reject('下载失败');
        }
      });
    }
  });
}
/**
 * 重设tabbar
 * @param {Object} tablist
 */
function setTabbar(tablist) {
  tablist.list.forEach((item, index) => {
    uni.setTabBarItem({
      index: index,
      text: item.text,
      iconPath: item.image,
      selectedIconPath: item.selectedImage,
      pagePath: item.path
    });
  });
  uni.setTabBarStyle({
    color: tablist.color,
    selectedColor: tablist.selectColor,
    backgroundColor: tablist.bgColor,
    borderStyle: 'black'
  });
}

/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 21:
/*!***************************!*\
  !*** ./uview-ui/index.js ***!
  \***************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {/* harmony import */ var _libs_mixin_mixin_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./libs/mixin/mixin.js */ 22);
/* harmony import */ var _libs_mixin_mixin_js__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_libs_mixin_mixin_js__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _libs_request__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./libs/request */ 23);
/* harmony import */ var _libs_function_queryParams_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ./libs/function/queryParams.js */ 27);
/* harmony import */ var _libs_function_route_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./libs/function/route.js */ 28);
/* harmony import */ var _libs_function_timeFormat_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! ./libs/function/timeFormat.js */ 29);
/* harmony import */ var _libs_function_timeFrom_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./libs/function/timeFrom.js */ 30);
/* harmony import */ var _libs_function_colorGradient_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! ./libs/function/colorGradient.js */ 31);
/* harmony import */ var _libs_function_guid_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! ./libs/function/guid.js */ 32);
/* harmony import */ var _libs_function_color_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(/*! ./libs/function/color.js */ 33);
/* harmony import */ var _libs_function_type2icon_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(/*! ./libs/function/type2icon.js */ 34);
/* harmony import */ var _libs_function_randomArray_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(/*! ./libs/function/randomArray.js */ 35);
/* harmony import */ var _libs_function_deepClone_js__WEBPACK_IMPORTED_MODULE_11__ = __webpack_require__(/*! ./libs/function/deepClone.js */ 25);
/* harmony import */ var _libs_function_deepMerge_js__WEBPACK_IMPORTED_MODULE_12__ = __webpack_require__(/*! ./libs/function/deepMerge.js */ 24);
/* harmony import */ var _libs_function_addUnit_js__WEBPACK_IMPORTED_MODULE_13__ = __webpack_require__(/*! ./libs/function/addUnit.js */ 36);
/* harmony import */ var _libs_function_test_js__WEBPACK_IMPORTED_MODULE_14__ = __webpack_require__(/*! ./libs/function/test.js */ 26);
/* harmony import */ var _libs_function_random_js__WEBPACK_IMPORTED_MODULE_15__ = __webpack_require__(/*! ./libs/function/random.js */ 37);
/* harmony import */ var _libs_function_trim_js__WEBPACK_IMPORTED_MODULE_16__ = __webpack_require__(/*! ./libs/function/trim.js */ 38);
/* harmony import */ var _libs_function_toast_js__WEBPACK_IMPORTED_MODULE_17__ = __webpack_require__(/*! ./libs/function/toast.js */ 39);
/* harmony import */ var _libs_function_getParent_js__WEBPACK_IMPORTED_MODULE_18__ = __webpack_require__(/*! ./libs/function/getParent.js */ 40);
/* harmony import */ var _libs_function_$parent_js__WEBPACK_IMPORTED_MODULE_19__ = __webpack_require__(/*! ./libs/function/$parent.js */ 41);
/* harmony import */ var _libs_function_sys_js__WEBPACK_IMPORTED_MODULE_20__ = __webpack_require__(/*! ./libs/function/sys.js */ 42);
/* harmony import */ var _libs_function_debounce_js__WEBPACK_IMPORTED_MODULE_21__ = __webpack_require__(/*! ./libs/function/debounce.js */ 43);
/* harmony import */ var _libs_function_throttle_js__WEBPACK_IMPORTED_MODULE_22__ = __webpack_require__(/*! ./libs/function/throttle.js */ 44);
/* harmony import */ var _libs_config_config_js__WEBPACK_IMPORTED_MODULE_23__ = __webpack_require__(/*! ./libs/config/config.js */ 45);
/* harmony import */ var _libs_config_zIndex_js__WEBPACK_IMPORTED_MODULE_24__ = __webpack_require__(/*! ./libs/config/zIndex.js */ 46);
// 引入全局mixin

// 引入关于是否mixin集成小程序分享的配置
// import wxshare from './libs/mixin/mpShare.js'
// 全局挂载引入http相关请求拦截插件

function wranning(str) {
  // 开发环境进行信息输出,主要是一些报错信息
  // 这个环境的来由是在程序编写时候,点击hx编辑器运行调试代码的时候,详见:
  // 	https://uniapp.dcloud.io/frame?id=%e5%bc%80%e5%8f%91%e7%8e%af%e5%a2%83%e5%92%8c%e7%94%9f%e4%ba%a7%e7%8e%af%e5%a2%83
  if (true) {
    console.warn(str);
  }
}

// 尝试判断在根目录的/store中是否有$u.mixin.js，此文件uView默认为需要挂在到全局的vuex的state变量
// HX2.6.11版本,放到try中,控制台依然会警告,暂时不用此方式，
// let vuexStore = {};
// try {
// 	vuexStore = require("@/store/$u.mixin.js");
// } catch (e) {
// 	//TODO handle the exception
// }

// post类型对象参数转为get类型url参数

// 路由封装

// 时间格式化

// 时间戳格式化,返回多久之前

// 颜色渐变相关,colorGradient-颜色渐变,hexToRgb-十六进制颜色转rgb颜色,rgbToHex-rgb转十六进制

// 生成全局唯一guid字符串

// 主题相关颜色,info|success|warning|primary|default|error,此颜色已在uview.scss中定义,但是为js中也能使用,故也定义一份

// 根据type获取图标名称

// 打乱数组的顺序

// 对象和数组的深度克隆

// 对象深度拷贝

// 添加单位


// 规则检验

// 随机数

// 去除空格

// toast提示，对uni.showToast的封装

// 获取父组件参数

// 获取整个父组件

// 获取sys()和os()工具方法
// 获取设备信息，挂载到$u的sys()(system的缩写)属性中，
// 同时把安卓和ios平台的名称"ios"和"android"挂到$u.os()中，方便取用

// 防抖方法

// 节流方法


// 配置信息

// 各个需要fixed的地方的z-index配置文件

const $u = {
  queryParams: _libs_function_queryParams_js__WEBPACK_IMPORTED_MODULE_2__["default"],
  route: _libs_function_route_js__WEBPACK_IMPORTED_MODULE_3__["default"],
  timeFormat: _libs_function_timeFormat_js__WEBPACK_IMPORTED_MODULE_4__["default"],
  date: _libs_function_timeFormat_js__WEBPACK_IMPORTED_MODULE_4__["default"],
  // 另名date
  timeFrom: _libs_function_timeFrom_js__WEBPACK_IMPORTED_MODULE_5__["default"],
  colorGradient: _libs_function_colorGradient_js__WEBPACK_IMPORTED_MODULE_6__["default"].colorGradient,
  colorToRgba: _libs_function_colorGradient_js__WEBPACK_IMPORTED_MODULE_6__["default"].colorToRgba,
  guid: _libs_function_guid_js__WEBPACK_IMPORTED_MODULE_7__["default"],
  color: _libs_function_color_js__WEBPACK_IMPORTED_MODULE_8__["default"],
  sys: _libs_function_sys_js__WEBPACK_IMPORTED_MODULE_20__["sys"],
  os: _libs_function_sys_js__WEBPACK_IMPORTED_MODULE_20__["os"],
  type2icon: _libs_function_type2icon_js__WEBPACK_IMPORTED_MODULE_9__["default"],
  randomArray: _libs_function_randomArray_js__WEBPACK_IMPORTED_MODULE_10__["default"],
  wranning,
  get: _libs_request__WEBPACK_IMPORTED_MODULE_1__["default"].get,
  post: _libs_request__WEBPACK_IMPORTED_MODULE_1__["default"].post,
  put: _libs_request__WEBPACK_IMPORTED_MODULE_1__["default"].put,
  'delete': _libs_request__WEBPACK_IMPORTED_MODULE_1__["default"].delete,
  hexToRgb: _libs_function_colorGradient_js__WEBPACK_IMPORTED_MODULE_6__["default"].hexToRgb,
  rgbToHex: _libs_function_colorGradient_js__WEBPACK_IMPORTED_MODULE_6__["default"].rgbToHex,
  test: _libs_function_test_js__WEBPACK_IMPORTED_MODULE_14__["default"],
  random: _libs_function_random_js__WEBPACK_IMPORTED_MODULE_15__["default"],
  deepClone: _libs_function_deepClone_js__WEBPACK_IMPORTED_MODULE_11__["default"],
  deepMerge: _libs_function_deepMerge_js__WEBPACK_IMPORTED_MODULE_12__["default"],
  getParent: _libs_function_getParent_js__WEBPACK_IMPORTED_MODULE_18__["default"],
  $parent: _libs_function_$parent_js__WEBPACK_IMPORTED_MODULE_19__["default"],
  addUnit: _libs_function_addUnit_js__WEBPACK_IMPORTED_MODULE_13__["default"],
  trim: _libs_function_trim_js__WEBPACK_IMPORTED_MODULE_16__["default"],
  type: ['primary', 'success', 'error', 'warning', 'info'],
  http: _libs_request__WEBPACK_IMPORTED_MODULE_1__["default"],
  toast: _libs_function_toast_js__WEBPACK_IMPORTED_MODULE_17__["default"],
  config: _libs_config_config_js__WEBPACK_IMPORTED_MODULE_23__["default"],
  // uView配置信息相关，比如版本号
  zIndex: _libs_config_zIndex_js__WEBPACK_IMPORTED_MODULE_24__["default"],
  debounce: _libs_function_debounce_js__WEBPACK_IMPORTED_MODULE_21__["default"],
  throttle: _libs_function_throttle_js__WEBPACK_IMPORTED_MODULE_22__["default"]
};

// $u挂载到uni对象上
uni.$u = $u;
const install = Vue => {
  Vue.mixin(_libs_mixin_mixin_js__WEBPACK_IMPORTED_MODULE_0___default.a);
  if (Vue.prototype.openShare) {
    Vue.mixin(mpShare);
  }
  // Vue.mixin(vuexStore);
  // 时间格式化，同时两个名称，date和timeFormat
  Vue.filter('timeFormat', (timestamp, format) => {
    return Object(_libs_function_timeFormat_js__WEBPACK_IMPORTED_MODULE_4__["default"])(timestamp, format);
  });
  Vue.filter('date', (timestamp, format) => {
    return Object(_libs_function_timeFormat_js__WEBPACK_IMPORTED_MODULE_4__["default"])(timestamp, format);
  });
  // 将多久以前的方法，注入到全局过滤器
  Vue.filter('timeFrom', (timestamp, format) => {
    return Object(_libs_function_timeFrom_js__WEBPACK_IMPORTED_MODULE_5__["default"])(timestamp, format);
  });
  Vue.prototype.$u = $u;
};
/* harmony default export */ __webpack_exports__["default"] = ({
  install
});
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 22:
/*!**************************************!*\
  !*** ./uview-ui/libs/mixin/mixin.js ***!
  \**************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

/* WEBPACK VAR INJECTION */(function(uni) {module.exports = {
  data() {
    return {};
  },
  onLoad() {
    // getRect挂载到$u上，因为这方法需要使用in(this)，所以无法把它独立成一个单独的文件导出
    this.$u.getRect = this.$uGetRect;
  },
  methods: {
    // 查询节点信息
    // 目前此方法在支付宝小程序中无法获取组件跟接点的尺寸，为支付宝的bug(2020-07-21)
    // 解决办法为在组件根部再套一个没有任何作用的view元素
    $uGetRect(selector, all) {
      return new Promise(resolve => {
        uni.createSelectorQuery().in(this)[all ? 'selectAll' : 'select'](selector).boundingClientRect(rect => {
          if (all && Array.isArray(rect) && rect.length) {
            resolve(rect);
          }
          if (!all && rect) {
            resolve(rect);
          }
        }).exec();
      });
    },
    getParentData(parentName = '') {
      // 避免在created中去定义parent变量
      if (!this.parent) this.parent = false;
      // 这里的本质原理是，通过获取父组件实例(也即u-radio-group的this)
      // 将父组件this中对应的参数，赋值给本组件(u-radio的this)的parentData对象中对应的属性
      // 之所以需要这么做，是因为所有端中，头条小程序不支持通过this.parent.xxx去监听父组件参数的变化
      this.parent = this.$u.$parent.call(this, parentName);
      if (this.parent) {
        // 历遍parentData中的属性，将parent中的同名属性赋值给parentData
        Object.keys(this.parentData).map(key => {
          this.parentData[key] = this.parent[key];
        });
      }
    },
    // 阻止事件冒泡
    preventEvent(e) {
      e && e.stopPropagation && e.stopPropagation();
    }
  },
  onReachBottom() {
    uni.$emit('uOnReachBottom');
  },
  beforeDestroy() {
    // 判断当前页面是否存在parent和chldren，一般在checkbox和checkbox-group父子联动的场景会有此情况
    // 组件销毁时，移除子组件在父组件children数组中的实例，释放资源，避免数据混乱
    if (this.parent && uni.$u.test.array(this.parent.children)) {
      // 组件销毁时，移除父组件中的children数组中对应的实例
      const childrenList = this.parent.children;
      childrenList.map((child, index) => {
        // 如果相等，则移除
        if (child === this) {
          childrenList.splice(index, 1);
        }
      });
    }
  }
};
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 23:
/*!****************************************!*\
  !*** ./uview-ui/libs/request/index.js ***!
  \****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {/* harmony import */ var _function_deepMerge__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../function/deepMerge */ 24);
/* harmony import */ var _function_test__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ../function/test */ 26);


class Request {
  // 设置全局默认配置
  setConfig(customConfig) {
    // 深度合并对象，否则会造成对象深层属性丢失
    this.config = Object(_function_deepMerge__WEBPACK_IMPORTED_MODULE_0__["default"])(this.config, customConfig);
  }

  // 主要请求部分
  request(options = {}) {
    // 检查请求拦截
    if (this.interceptor.request && typeof this.interceptor.request === 'function') {
      let tmpConfig = {};
      let interceptorRequest = this.interceptor.request(options);
      if (interceptorRequest === false) {
        // 返回一个处于pending状态中的Promise，来取消原promise，避免进入then()回调
        return new Promise(() => {});
      }
      this.options = interceptorRequest;
    }
    options.dataType = options.dataType || this.config.dataType;
    options.responseType = options.responseType || this.config.responseType;
    options.url = options.url || '';
    options.params = options.params || {};
    options.header = Object.assign({}, this.config.header, options.header);
    options.method = options.method || this.config.method;
    return new Promise((resolve, reject) => {
      let loadingTimer = null;
      let loadingShown = false;
      options.complete = response => {
        // Only hide a loading indicator that this request actually displayed.
        // Calling hideLoading without a matching showLoading triggers a warning
        // in recent WeChat base libraries.
        if (loadingTimer) {
          clearTimeout(loadingTimer);
          loadingTimer = null;
        }
        if (loadingShown) {
          uni.hideLoading();
          loadingShown = false;
        }
        // 判断用户对拦截返回数据的要求，如果originalData为true，返回所有的数据(response)到拦截器，否则只返回response.data
        if (this.config.originalData) {
          // 判断是否存在拦截器
          if (this.interceptor.response && typeof this.interceptor.response === 'function') {
            let resInterceptors = this.interceptor.response(response);
            // 如果拦截器不返回false，就将拦截器返回的内容给this.$u.post的then回调
            if (resInterceptors !== false) {
              resolve(resInterceptors);
            } else {
              // 如果拦截器返回false，意味着拦截器定义者认为返回有问题，直接接入catch回调
              reject(response);
            }
          } else {
            // 如果要求返回原始数据，就算没有拦截器，也返回最原始的数据
            resolve(response);
          }
        } else {
          if (response.statusCode == 200) {
            if (this.interceptor.response && typeof this.interceptor.response === 'function') {
              let resInterceptors = this.interceptor.response(response.data);
              if (resInterceptors !== false) {
                resolve(resInterceptors);
              } else {
                reject(response.data);
              }
            } else {
              // 如果不是返回原始数据(originalData=false)，且没有拦截器的情况下，返回纯数据给then回调
              resolve(response.data);
            }
          } else {
            // 不返回原始数据的情况下，服务器状态码不为200，modal弹框提示
            // if(response.errMsg) {
            // 	uni.showModal({
            // 		title: response.errMsg
            // 	});
            // }
            reject(response);
          }
        }
      };

      // 判断用户传递的URL是否/开头,如果不是,加上/，这里使用了uView的test.js验证库的url()方法
      options.url = _function_test__WEBPACK_IMPORTED_MODULE_1__["default"].url(options.url) ? options.url : this.config.baseUrl + (options.url.indexOf('/') == 0 ? options.url : '/' + options.url);

      // 是否显示loading
      // 加一个是否已有timer定时器的判断，否则有两个同时请求的时候，后者会清除前者的定时器id
      // 而没有清除前者的定时器，导致前者超时，一直显示loading
      if (this.config.showLoading) {
        loadingTimer = setTimeout(() => {
          uni.showLoading({
            title: this.config.loadingText,
            mask: this.config.loadingMask
          });
          loadingShown = true;
          loadingTimer = null;
        }, this.config.loadingTime);
      }
      uni.request(options);
    });
    // .catch(res => {
    // 	// 如果返回reject()，不让其进入this.$u.post().then().catch()后面的catct()
    // 	// 因为很多人都会忘了写后面的catch()，导致报错捕获不到catch
    // 	return new Promise(()=>{});
    // })
  }
  constructor() {
    this.config = {
      baseUrl: '',
      // 请求的根域名
      // 默认的请求头
      header: {},
      method: 'POST',
      // 设置为json，返回后uni.request会对数据进行一次JSON.parse
      dataType: 'json',
      // 此参数无需处理，因为5+和支付宝小程序不支持，默认为text即可
      responseType: 'text',
      showLoading: true,
      // 是否显示请求中的loading
      loadingText: '请求中...',
      loadingTime: 800,
      // 在此时间内，请求还没回来的话，就显示加载中动画，单位ms
      timer: null,
      // 定时器
      originalData: false,
      // 是否在拦截器中返回服务端的原始数据，见文档说明
      loadingMask: true // 展示loading的时候，是否给一个透明的蒙层，防止触摸穿透
    };

    // 拦截器
    this.interceptor = {
      // 请求前的拦截
      request: null,
      // 请求后的拦截
      response: null
    };

    // get请求
    this.get = (url, data = {}, header = {}) => {
      return this.request({
        method: 'GET',
        url,
        header,
        data
      });
    };

    // post请求
    this.post = (url, data = {}, header = {}) => {
      return this.request({
        url,
        method: 'POST',
        header,
        data
      });
    };

    // put请求，不支持支付宝小程序(HX2.6.15)
    this.put = (url, data = {}, header = {}) => {
      return this.request({
        url,
        method: 'PUT',
        header,
        data
      });
    };

    // delete请求，不支持支付宝和头条小程序(HX2.6.15)
    this.delete = (url, data = {}, header = {}) => {
      return this.request({
        url,
        method: 'DELETE',
        header,
        data
      });
    };
  }
}
/* harmony default export */ __webpack_exports__["default"] = (new Request());
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 24:
/*!*********************************************!*\
  !*** ./uview-ui/libs/function/deepMerge.js ***!
  \*********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _deepClone__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./deepClone */ 25);


// JS对象深度合并
function deepMerge(target = {}, source = {}) {
  target = Object(_deepClone__WEBPACK_IMPORTED_MODULE_0__["default"])(target);
  if (typeof target !== 'object' || typeof source !== 'object') return false;
  for (var prop in source) {
    if (!source.hasOwnProperty(prop)) continue;
    if (prop in target) {
      if (typeof target[prop] !== 'object') {
        target[prop] = source[prop];
      } else {
        if (typeof source[prop] !== 'object') {
          target[prop] = source[prop];
        } else {
          if (target[prop].concat && source[prop].concat) {
            target[prop] = target[prop].concat(source[prop]);
          } else {
            target[prop] = deepMerge(target[prop], source[prop]);
          }
        }
      }
    } else {
      target[prop] = source[prop];
    }
  }
  return target;
}
/* harmony default export */ __webpack_exports__["default"] = (deepMerge);

/***/ }),

/***/ 25:
/*!*********************************************!*\
  !*** ./uview-ui/libs/function/deepClone.js ***!
  \*********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
// 判断arr是否为一个数组，返回一个bool值
function isArray(arr) {
  return Object.prototype.toString.call(arr) === '[object Array]';
}

// 深度克隆
function deepClone(obj) {
  // 对常见的“非”值，直接返回原来值
  if ([null, undefined, NaN, false].includes(obj)) return obj;
  if (typeof obj !== "object" && typeof obj !== 'function') {
    //原始类型直接返回
    return obj;
  }
  var o = isArray(obj) ? [] : {};
  for (let i in obj) {
    if (obj.hasOwnProperty(i)) {
      o[i] = typeof obj[i] === "object" ? deepClone(obj[i]) : obj[i];
    }
  }
  return o;
}
/* harmony default export */ __webpack_exports__["default"] = (deepClone);

/***/ }),

/***/ 26:
/*!****************************************!*\
  !*** ./uview-ui/libs/function/test.js ***!
  \****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/**
 * 验证电子邮箱格式
 */
function email(value) {
  return /^\w+((-\w+)|(\.\w+))*\@[A-Za-z0-9]+((\.|-)[A-Za-z0-9]+)*\.[A-Za-z0-9]+$/.test(value);
}

/**
 * 验证手机格式
 */
function mobile(value) {
  return /^1[3-9]\d{9}$/.test(value);
}

/**
 * 验证URL格式
 */
function url(value) {
  return /http(s)?:\/\/([\w-]+\.)+[\w-]+(\/[\w-.\/?%&=]*)?/.test(value);
}

/**
 * 验证日期格式
 */
function date(value) {
  return !/Invalid|NaN/.test(new Date(value).toString());
}

/**
 * 验证ISO类型的日期格式
 */
function dateISO(value) {
  return /^\d{4}[\/\-](0?[1-9]|1[012])[\/\-](0?[1-9]|[12][0-9]|3[01])$/.test(value);
}

/**
 * 验证十进制数字
 */
function number(value) {
  return /^(?:-?\d+|-?\d{1,3}(?:,\d{3})+)?(?:\.\d+)?$/.test(value);
}

/**
 * 验证整数
 */
function digits(value) {
  return /^\d+$/.test(value);
}

/**
 * 验证身份证号码
 */
function idCard(value) {
  return /^[1-9]\d{5}[1-9]\d{3}((0\d)|(1[0-2]))(([0|1|2]\d)|3[0-1])\d{3}([0-9]|X)$/.test(value);
}

/**
 * 是否车牌号
 */
function carNo(value) {
  // 新能源车牌
  const xreg = /^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领A-Z]{1}[A-Z]{1}(([0-9]{5}[DF]$)|([DF][A-HJ-NP-Z0-9][0-9]{4}$))/;
  // 旧车牌
  const creg = /^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领A-Z]{1}[A-Z]{1}[A-HJ-NP-Z0-9]{4}[A-HJ-NP-Z0-9挂学警港澳]{1}$/;
  if (value.length === 7) {
    return creg.test(value);
  } else if (value.length === 8) {
    return xreg.test(value);
  } else {
    return false;
  }
}

/**
 * 金额,只允许2位小数
 */
function amount(value) {
  //金额，只允许保留两位小数
  return /^[1-9]\d*(,\d{3})*(\.\d{1,2})?$|^0\.\d{1,2}$/.test(value);
}

/**
 * 中文
 */
function chinese(value) {
  let reg = /^[\u4e00-\u9fa5]+$/gi;
  return reg.test(value);
}

/**
 * 只能输入字母
 */
function letter(value) {
  return /^[a-zA-Z]*$/.test(value);
}

/**
 * 只能是字母或者数字
 */
function enOrNum(value) {
  //英文或者数字
  let reg = /^[0-9a-zA-Z]*$/g;
  return reg.test(value);
}

/**
 * 验证是否包含某个值
 */
function contains(value, param) {
  return value.indexOf(param) >= 0;
}

/**
 * 验证一个值范围[min, max]
 */
function range(value, param) {
  return value >= param[0] && value <= param[1];
}

/**
 * 验证一个长度范围[min, max]
 */
function rangeLength(value, param) {
  return value.length >= param[0] && value.length <= param[1];
}

/**
 * 是否固定电话
 */
function landline(value) {
  let reg = /^\d{3,4}-\d{7,8}(-\d{3,4})?$/;
  return reg.test(value);
}

/**
 * 判断是否为空
 */
function empty(value) {
  switch (typeof value) {
    case 'undefined':
      return true;
    case 'string':
      if (value.replace(/(^[ \t\n\r]*)|([ \t\n\r]*$)/g, '').length == 0) return true;
      break;
    case 'boolean':
      if (!value) return true;
      break;
    case 'number':
      if (0 === value || isNaN(value)) return true;
      break;
    case 'object':
      if (null === value || value.length === 0) return true;
      for (var i in value) {
        return false;
      }
      return true;
  }
  return false;
}

/**
 * 是否json字符串
 */
function jsonString(value) {
  if (typeof value == 'string') {
    try {
      var obj = JSON.parse(value);
      if (typeof obj == 'object' && obj) {
        return true;
      } else {
        return false;
      }
    } catch (e) {
      return false;
    }
  }
  return false;
}

/**
 * 是否数组
 */
function array(value) {
  if (typeof Array.isArray === "function") {
    return Array.isArray(value);
  } else {
    return Object.prototype.toString.call(value) === "[object Array]";
  }
}

/**
 * 是否对象
 */
function object(value) {
  return Object.prototype.toString.call(value) === '[object Object]';
}

/**
 * 是否短信验证码
 */
function code(value, len = 6) {
  return new RegExp(`^\\d{${len}}$`).test(value);
}
/* harmony default export */ __webpack_exports__["default"] = ({
  email,
  mobile,
  url,
  date,
  dateISO,
  number,
  digits,
  idCard,
  carNo,
  amount,
  chinese,
  letter,
  enOrNum,
  contains,
  range,
  rangeLength,
  empty,
  isEmpty: empty,
  jsonString,
  landline,
  object,
  array,
  code
});

/***/ }),

/***/ 27:
/*!***********************************************!*\
  !*** ./uview-ui/libs/function/queryParams.js ***!
  \***********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/**
 * 对象转url参数
 * @param {*} data,对象
 * @param {*} isPrefix,是否自动加上"?"
 */
function queryParams(data = {}, isPrefix = true, arrayFormat = 'brackets') {
  let prefix = isPrefix ? '?' : '';
  let _result = [];
  if (['indices', 'brackets', 'repeat', 'comma'].indexOf(arrayFormat) == -1) arrayFormat = 'brackets';
  for (let key in data) {
    let value = data[key];
    // 去掉为空的参数
    if (['', undefined, null].indexOf(value) >= 0) {
      continue;
    }
    // 如果值为数组，另行处理
    if (value.constructor === Array) {
      // e.g. {ids: [1, 2, 3]}
      switch (arrayFormat) {
        case 'indices':
          // 结果: ids[0]=1&ids[1]=2&ids[2]=3
          for (let i = 0; i < value.length; i++) {
            _result.push(key + '[' + i + ']=' + value[i]);
          }
          break;
        case 'brackets':
          // 结果: ids[]=1&ids[]=2&ids[]=3
          value.forEach(_value => {
            _result.push(key + '[]=' + _value);
          });
          break;
        case 'repeat':
          // 结果: ids=1&ids=2&ids=3
          value.forEach(_value => {
            _result.push(key + '=' + _value);
          });
          break;
        case 'comma':
          // 结果: ids=1,2,3
          let commaStr = "";
          value.forEach(_value => {
            commaStr += (commaStr ? "," : "") + _value;
          });
          _result.push(key + '=' + commaStr);
          break;
        default:
          value.forEach(_value => {
            _result.push(key + '[]=' + _value);
          });
      }
    } else {
      _result.push(key + '=' + value);
    }
  }
  return _result.length ? prefix + _result.join('&') : '';
}
/* harmony default export */ __webpack_exports__["default"] = (queryParams);

/***/ }),

/***/ 28:
/*!*****************************************!*\
  !*** ./uview-ui/libs/function/route.js ***!
  \*****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {/**
 * 路由跳转方法，该方法相对于直接使用uni.xxx的好处是使用更加简单快捷
 * 并且带有路由拦截功能
 */

class Router {
  constructor() {
    // 原始属性定义
    this.config = {
      type: 'navigateTo',
      url: '',
      delta: 1,
      // navigateBack页面后退时,回退的层数
      params: {},
      // 传递的参数
      animationType: 'pop-in',
      // 窗口动画,只在APP有效
      animationDuration: 300,
      // 窗口动画持续时间,单位毫秒,只在APP有效
      intercept: false // 是否需要拦截
    };
    // 因为route方法是需要对外赋值给另外的对象使用，同时route内部有使用this，会导致route失去上下文
    // 这里在构造函数中进行this绑定
    this.route = this.route.bind(this);
  }

  // 判断url前面是否有"/"，如果没有则加上，否则无法跳转
  addRootPath(url) {
    return url[0] === '/' ? url : `/${url}`;
  }

  // 整合路由参数
  mixinParam(url, params) {
    url = url && this.addRootPath(url);

    // 使用正则匹配，主要依据是判断是否有"/","?","="等，如“/page/index/index?name=mary"
    // 如果有url中有get参数，转换后无需带上"?"
    let query = '';
    if (/.*\/.*\?.*=.*/.test(url)) {
      // object对象转为get类型的参数
      query = uni.$u.queryParams(params, false);
      if (query === '') {
        return url;
      }
      // 因为已有get参数,所以后面拼接的参数需要带上"&"隔开
      return url += "&" + query;
    } else {
      // 直接拼接参数，因为此处url中没有后面的query参数，也就没有"?/&"之类的符号
      query = uni.$u.queryParams(params);
      return url += query;
    }
  }

  // 对外的方法名称
  async route(options = {}, params = {}) {
    // 合并用户的配置和内部的默认配置
    let mergeConfig = {};
    if (typeof options === 'string') {
      // 如果options为字符串，则为route(url, params)的形式
      mergeConfig.url = this.mixinParam(options, params);
      mergeConfig.type = 'navigateTo';
    } else {
      mergeConfig = uni.$u.deepClone(options, this.config);
      // 否则正常使用mergeConfig中的url和params进行拼接
      mergeConfig.url = this.mixinParam(options.url, options.params);
    }
    if (params.intercept) {
      this.config.intercept = params.intercept;
    }
    // params参数也带给拦截器
    mergeConfig.params = params;
    // 合并内外部参数
    mergeConfig = uni.$u.deepMerge(this.config, mergeConfig);
    // 判断用户是否定义了拦截器
    if (typeof uni.$u.routeIntercept === 'function') {
      // 定一个promise，根据用户执行resolve(true)或者resolve(false)来决定是否进行路由跳转
      const isNext = await new Promise((resolve, reject) => {
        uni.$u.routeIntercept(mergeConfig, resolve);
      });
      // 如果isNext为true，则执行路由跳转
      isNext && this.openPage(mergeConfig);
    } else {
      this.openPage(mergeConfig);
    }
  }

  // 执行路由跳转
  openPage(config) {
    // 解构参数
    const {
      url,
      type,
      delta,
      animationType,
      animationDuration
    } = config;
    if (config.type == 'navigateTo' || config.type == 'to') {
      uni.navigateTo({
        url,
        animationType,
        animationDuration
      });
    }
    if (config.type == 'redirectTo' || config.type == 'redirect') {
      uni.redirectTo({
        url
      });
    }
    if (config.type == 'switchTab' || config.type == 'tab') {
      uni.switchTab({
        url
      });
    }
    if (config.type == 'reLaunch' || config.type == 'launch') {
      uni.reLaunch({
        url
      });
    }
    if (config.type == 'navigateBack' || config.type == 'back') {
      uni.navigateBack({
        delta
      });
    }
  }
}
/* harmony default export */ __webpack_exports__["default"] = (new Router().route);
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 29:
/*!**********************************************!*\
  !*** ./uview-ui/libs/function/timeFormat.js ***!
  \**********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
// padStart 的 polyfill，因为某些机型或情况，还无法支持es7的padStart，比如电脑版的微信小程序
// 所以这里做一个兼容polyfill的兼容处理
if (!String.prototype.padStart) {
  // 为了方便表示这里 fillString 用了ES6 的默认参数，不影响理解
  String.prototype.padStart = function (maxLength, fillString = ' ') {
    if (Object.prototype.toString.call(fillString) !== "[object String]") throw new TypeError('fillString must be String');
    let str = this;
    // 返回 String(str) 这里是为了使返回的值是字符串字面量，在控制台中更符合直觉
    if (str.length >= maxLength) return String(str);
    let fillLength = maxLength - str.length,
      times = Math.ceil(fillLength / fillString.length);
    while (times >>= 1) {
      fillString += fillString;
      if (times === 1) {
        fillString += fillString;
      }
    }
    return fillString.slice(0, fillLength) + str;
  };
}

// 其他更多是格式化有如下:
// yyyy:mm:dd|yyyy:mm|yyyy年mm月dd日|yyyy年mm月dd日 hh时MM分等,可自定义组合
function timeFormat(dateTime = null, fmt = 'yyyy-mm-dd') {
  // 如果为null,则格式化当前时间
  if (!dateTime) dateTime = Number(new Date());
  // 如果dateTime长度为10或者13，则为秒和毫秒的时间戳，如果超过13位，则为其他的时间格式
  if (dateTime.toString().length == 10) dateTime *= 1000;
  let date = new Date(dateTime);
  let ret;
  let opt = {
    "y+": date.getFullYear().toString(),
    // 年
    "m+": (date.getMonth() + 1).toString(),
    // 月
    "d+": date.getDate().toString(),
    // 日
    "h+": date.getHours().toString(),
    // 时
    "M+": date.getMinutes().toString(),
    // 分
    "s+": date.getSeconds().toString() // 秒
    // 有其他格式化字符需求可以继续添加，必须转化成字符串
  };
  for (let k in opt) {
    ret = new RegExp("(" + k + ")").exec(fmt);
    if (ret) {
      fmt = fmt.replace(ret[1], ret[1].length == 1 ? opt[k] : opt[k].padStart(ret[1].length, "0"));
    }
    ;
  }
  ;
  return fmt;
}
/* harmony default export */ __webpack_exports__["default"] = (timeFormat);

/***/ }),

/***/ 3:
/*!***********************************!*\
  !*** (webpack)/buildin/global.js ***!
  \***********************************/
/*! no static exports found */
/***/ (function(module, exports) {

var g;

// This works in non-strict mode
g = function () {
  return this;
}();
try {
  // This works if eval is allowed (see CSP)
  g = g || new Function("return this")();
} catch (e) {
  // This works if the window reference is available
  if (typeof window === "object") g = window;
}

// g can still be undefined, but nothing to do about it...
// We return undefined, instead of nothing here, so it's
// easier to handle this case. if(!global) { ...}

module.exports = g;

/***/ }),

/***/ 30:
/*!********************************************!*\
  !*** ./uview-ui/libs/function/timeFrom.js ***!
  \********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _libs_function_timeFormat_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../../libs/function/timeFormat.js */ 29);


/**
 * 时间戳转为多久之前
 * @param String timestamp 时间戳
 * @param String | Boolean format 如果为时间格式字符串，超出一定时间范围，返回固定的时间格式；
 * 如果为布尔值false，无论什么时间，都返回多久以前的格式
 */
function timeFrom(dateTime = null, format = 'yyyy-mm-dd') {
  // 如果为null,则格式化当前时间
  if (!dateTime) dateTime = Number(new Date());
  // 如果dateTime长度为10或者13，则为秒和毫秒的时间戳，如果超过13位，则为其他的时间格式
  if (dateTime.toString().length == 10) dateTime *= 1000;
  let timestamp = +new Date(Number(dateTime));
  let timer = (Number(new Date()) - timestamp) / 1000;
  // 如果小于5分钟,则返回"刚刚",其他以此类推
  let tips = '';
  switch (true) {
    case timer < 300:
      tips = '刚刚';
      break;
    case timer >= 300 && timer < 3600:
      tips = parseInt(timer / 60) + '分钟前';
      break;
    case timer >= 3600 && timer < 86400:
      tips = parseInt(timer / 3600) + '小时前';
      break;
    case timer >= 86400 && timer < 2592000:
      tips = parseInt(timer / 86400) + '天前';
      break;
    default:
      // 如果format为false，则无论什么时间戳，都显示xx之前
      if (format === false) {
        if (timer >= 2592000 && timer < 365 * 86400) {
          tips = parseInt(timer / (86400 * 30)) + '个月前';
        } else {
          tips = parseInt(timer / (86400 * 365)) + '年前';
        }
      } else {
        tips = Object(_libs_function_timeFormat_js__WEBPACK_IMPORTED_MODULE_0__["default"])(timestamp, format);
      }
  }
  return tips;
}
/* harmony default export */ __webpack_exports__["default"] = (timeFrom);

/***/ }),

/***/ 31:
/*!*************************************************!*\
  !*** ./uview-ui/libs/function/colorGradient.js ***!
  \*************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/**
 * 求两个颜色之间的渐变值
 * @param {string} startColor 开始的颜色
 * @param {string} endColor 结束的颜色
 * @param {number} step 颜色等分的份额
 * */
function colorGradient(startColor = 'rgb(0, 0, 0)', endColor = 'rgb(255, 255, 255)', step = 10) {
  let startRGB = hexToRgb(startColor, false); //转换为rgb数组模式
  let startR = startRGB[0];
  let startG = startRGB[1];
  let startB = startRGB[2];
  let endRGB = hexToRgb(endColor, false);
  let endR = endRGB[0];
  let endG = endRGB[1];
  let endB = endRGB[2];
  let sR = (endR - startR) / step; //总差值
  let sG = (endG - startG) / step;
  let sB = (endB - startB) / step;
  let colorArr = [];
  for (let i = 0; i < step; i++) {
    //计算每一步的hex值 
    let hex = rgbToHex('rgb(' + Math.round(sR * i + startR) + ',' + Math.round(sG * i + startG) + ',' + Math.round(sB * i + startB) + ')');
    colorArr.push(hex);
  }
  return colorArr;
}

// 将hex表示方式转换为rgb表示方式(这里返回rgb数组模式)
function hexToRgb(sColor, str = true) {
  let reg = /^#([0-9a-fA-f]{3}|[0-9a-fA-f]{6})$/;
  sColor = sColor.toLowerCase();
  if (sColor && reg.test(sColor)) {
    if (sColor.length === 4) {
      let sColorNew = "#";
      for (let i = 1; i < 4; i += 1) {
        sColorNew += sColor.slice(i, i + 1).concat(sColor.slice(i, i + 1));
      }
      sColor = sColorNew;
    }
    //处理六位的颜色值
    let sColorChange = [];
    for (let i = 1; i < 7; i += 2) {
      sColorChange.push(parseInt("0x" + sColor.slice(i, i + 2)));
    }
    if (!str) {
      return sColorChange;
    } else {
      return `rgb(${sColorChange[0]},${sColorChange[1]},${sColorChange[2]})`;
    }
  } else if (/^(rgb|RGB)/.test(sColor)) {
    let arr = sColor.replace(/(?:\(|\)|rgb|RGB)*/g, "").split(",");
    return arr.map(val => Number(val));
  } else {
    return sColor;
  }
}
;

// 将rgb表示方式转换为hex表示方式
function rgbToHex(rgb) {
  let _this = rgb;
  let reg = /^#([0-9a-fA-f]{3}|[0-9a-fA-f]{6})$/;
  if (/^(rgb|RGB)/.test(_this)) {
    let aColor = _this.replace(/(?:\(|\)|rgb|RGB)*/g, "").split(",");
    let strHex = "#";
    for (let i = 0; i < aColor.length; i++) {
      let hex = Number(aColor[i]).toString(16);
      hex = String(hex).length == 1 ? 0 + '' + hex : hex; // 保证每个rgb的值为2位
      if (hex === "0") {
        hex += hex;
      }
      strHex += hex;
    }
    if (strHex.length !== 7) {
      strHex = _this;
    }
    return strHex;
  } else if (reg.test(_this)) {
    let aNum = _this.replace(/#/, "").split("");
    if (aNum.length === 6) {
      return _this;
    } else if (aNum.length === 3) {
      let numHex = "#";
      for (let i = 0; i < aNum.length; i += 1) {
        numHex += aNum[i] + aNum[i];
      }
      return numHex;
    }
  } else {
    return _this;
  }
}

/**
* JS颜色十六进制转换为rgb或rgba,返回的格式为 rgba（255，255，255，0.5）字符串
* sHex为传入的十六进制的色值
* alpha为rgba的透明度
*/
function colorToRgba(color, alpha = 0.3) {
  color = rgbToHex(color);
  // 十六进制颜色值的正则表达式
  var reg = /^#([0-9a-fA-f]{3}|[0-9a-fA-f]{6})$/;
  /* 16进制颜色转为RGB格式 */
  let sColor = color.toLowerCase();
  if (sColor && reg.test(sColor)) {
    if (sColor.length === 4) {
      var sColorNew = '#';
      for (let i = 1; i < 4; i += 1) {
        sColorNew += sColor.slice(i, i + 1).concat(sColor.slice(i, i + 1));
      }
      sColor = sColorNew;
    }
    // 处理六位的颜色值
    var sColorChange = [];
    for (let i = 1; i < 7; i += 2) {
      sColorChange.push(parseInt('0x' + sColor.slice(i, i + 2)));
    }
    // return sColorChange.join(',')
    return 'rgba(' + sColorChange.join(',') + ',' + alpha + ')';
  } else {
    return sColor;
  }
}
/* harmony default export */ __webpack_exports__["default"] = ({
  colorGradient,
  hexToRgb,
  rgbToHex,
  colorToRgba
});

/***/ }),

/***/ 32:
/*!****************************************!*\
  !*** ./uview-ui/libs/function/guid.js ***!
  \****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/**
 * 本算法来源于简书开源代码，详见：https://www.jianshu.com/p/fdbf293d0a85
 * 全局唯一标识符（uuid，Globally Unique Identifier）,也称作 uuid(Universally Unique IDentifier) 
 * 一般用于多个组件之间,给它一个唯一的标识符,或者v-for循环的时候,如果使用数组的index可能会导致更新列表出现问题
 * 最可能的情况是左滑删除item或者对某条信息流"不喜欢"并去掉它的时候,会导致组件内的数据可能出现错乱
 * v-for的时候,推荐使用后端返回的id而不是循环的index
 * @param {Number} len uuid的长度
 * @param {Boolean} firstU 将返回的首字母置为"u"
 * @param {Nubmer} radix 生成uuid的基数(意味着返回的字符串都是这个基数),2-二进制,8-八进制,10-十进制,16-十六进制
 */
function guid(len = 32, firstU = true, radix = null) {
  let chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'.split('');
  let uuid = [];
  radix = radix || chars.length;
  if (len) {
    // 如果指定uuid长度,只是取随机的字符,0|x为位运算,能去掉x的小数位,返回整数位
    for (let i = 0; i < len; i++) uuid[i] = chars[0 | Math.random() * radix];
  } else {
    let r;
    // rfc4122标准要求返回的uuid中,某些位为固定的字符
    uuid[8] = uuid[13] = uuid[18] = uuid[23] = '-';
    uuid[14] = '4';
    for (let i = 0; i < 36; i++) {
      if (!uuid[i]) {
        r = 0 | Math.random() * 16;
        uuid[i] = chars[i == 19 ? r & 0x3 | 0x8 : r];
      }
    }
  }
  // 移除第一个字符,并用u替代,因为第一个字符为数值时,该guuid不能用作id或者class
  if (firstU) {
    uuid.shift();
    return 'u' + uuid.join('');
  } else {
    return uuid.join('');
  }
}
/* harmony default export */ __webpack_exports__["default"] = (guid);

/***/ }),

/***/ 33:
/*!*****************************************!*\
  !*** ./uview-ui/libs/function/color.js ***!
  \*****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
// 为了让用户能够自定义主题，会逐步弃用此文件，各颜色通过css提供
// 为了给某些特殊场景使用和向后兼容，无需删除此文件(2020-06-20)
let color = {
  primary: "#2979ff",
  primaryDark: "#2b85e4",
  primaryDisabled: "#a0cfff",
  primaryLight: "#ecf5ff",
  bgColor: "#f3f4f6",
  info: "#909399",
  infoDark: "#82848a",
  infoDisabled: "#c8c9cc",
  infoLight: "#f4f4f5",
  warning: "#ff9900",
  warningDark: "#f29100",
  warningDisabled: "#fcbd71",
  warningLight: "#fdf6ec",
  error: "#fa3534",
  errorDark: "#dd6161",
  errorDisabled: "#fab6b6",
  errorLight: "#fef0f0",
  success: "#19be6b",
  successDark: "#18b566",
  successDisabled: "#71d5a1",
  successLight: "#dbf1e1",
  mainColor: "#303133",
  contentColor: "#606266",
  tipsColor: "#909399",
  lightColor: "#c0c4cc",
  borderColor: "#e4e7ed"
};
/* harmony default export */ __webpack_exports__["default"] = (color);

/***/ }),

/***/ 34:
/*!*********************************************!*\
  !*** ./uview-ui/libs/function/type2icon.js ***!
  \*********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/**
 * 根据主题type值,获取对应的图标
 * @param String type 主题名称,primary|info|error|warning|success
 * @param String fill 是否使用fill填充实体的图标  
 */
function type2icon(type = 'success', fill = false) {
  // 如果非预置值,默认为success
  if (['primary', 'info', 'error', 'warning', 'success'].indexOf(type) == -1) type = 'success';
  let iconName = '';
  // 目前(2019-12-12),info和primary使用同一个图标
  switch (type) {
    case 'primary':
      iconName = 'info-circle';
      break;
    case 'info':
      iconName = 'info-circle';
      break;
    case 'error':
      iconName = 'close-circle';
      break;
    case 'warning':
      iconName = 'error-circle';
      break;
    case 'success':
      iconName = 'checkmark-circle';
      break;
    default:
      iconName = 'checkmark-circle';
  }
  // 是否是实体类型,加上-fill,在icon组件库中,实体的类名是后面加-fill的
  if (fill) iconName += '-fill';
  return iconName;
}
/* harmony default export */ __webpack_exports__["default"] = (type2icon);

/***/ }),

/***/ 35:
/*!***********************************************!*\
  !*** ./uview-ui/libs/function/randomArray.js ***!
  \***********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
// 打乱数组
function randomArray(array = []) {
  // 原理是sort排序,Math.random()产生0<= x < 1之间的数,会导致x-0.05大于或者小于0
  return array.sort(() => Math.random() - 0.5);
}
/* harmony default export */ __webpack_exports__["default"] = (randomArray);

/***/ }),

/***/ 36:
/*!*******************************************!*\
  !*** ./uview-ui/libs/function/addUnit.js ***!
  \*******************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "default", function() { return addUnit; });
/* harmony import */ var _test_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./test.js */ 26);


// 添加单位，如果有rpx，%，px等单位结尾或者值为auto，直接返回，否则加上rpx单位结尾
function addUnit(value = 'auto', unit = 'rpx') {
  value = String(value);
  // 用uView内置验证规则中的number判断是否为数值
  return _test_js__WEBPACK_IMPORTED_MODULE_0__["default"].number(value) ? `${value}${unit}` : value;
}

/***/ }),

/***/ 37:
/*!******************************************!*\
  !*** ./uview-ui/libs/function/random.js ***!
  \******************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
function random(min, max) {
  if (min >= 0 && max > 0 && max >= min) {
    let gab = max - min + 1;
    return Math.floor(Math.random() * gab + min);
  } else {
    return 0;
  }
}
/* harmony default export */ __webpack_exports__["default"] = (random);

/***/ }),

/***/ 38:
/*!****************************************!*\
  !*** ./uview-ui/libs/function/trim.js ***!
  \****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
function trim(str, pos = 'both') {
  if (pos == 'both') {
    return str.replace(/^\s+|\s+$/g, "");
  } else if (pos == "left") {
    return str.replace(/^\s*/, '');
  } else if (pos == 'right') {
    return str.replace(/(\s*$)/g, "");
  } else if (pos == 'all') {
    return str.replace(/\s+/g, "");
  } else {
    return str;
  }
}
/* harmony default export */ __webpack_exports__["default"] = (trim);

/***/ }),

/***/ 39:
/*!*****************************************!*\
  !*** ./uview-ui/libs/function/toast.js ***!
  \*****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {function toast(title, duration = 1500) {
  uni.showToast({
    title: title,
    icon: 'none',
    duration: duration
  });
}
/* harmony default export */ __webpack_exports__["default"] = (toast);
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 4:
/*!*************************************************************!*\
  !*** ./node_modules/@dcloudio/uni-i18n/dist/uni-i18n.es.js ***!
  \*************************************************************/
/*! exports provided: Formatter, I18n, LOCALE_EN, LOCALE_ES, LOCALE_FR, LOCALE_ZH_HANS, LOCALE_ZH_HANT, compileI18nJsonStr, hasI18nJson, initVueI18n, isI18nStr, isString, normalizeLocale, parseI18nJson, resolveLocale */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni, global) {/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "Formatter", function() { return BaseFormatter; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "I18n", function() { return I18n; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "LOCALE_EN", function() { return LOCALE_EN; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "LOCALE_ES", function() { return LOCALE_ES; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "LOCALE_FR", function() { return LOCALE_FR; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "LOCALE_ZH_HANS", function() { return LOCALE_ZH_HANS; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "LOCALE_ZH_HANT", function() { return LOCALE_ZH_HANT; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "compileI18nJsonStr", function() { return compileI18nJsonStr; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "hasI18nJson", function() { return hasI18nJson; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "initVueI18n", function() { return initVueI18n; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "isI18nStr", function() { return isI18nStr; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "isString", function() { return isString; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "normalizeLocale", function() { return normalizeLocale; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "parseI18nJson", function() { return parseI18nJson; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "resolveLocale", function() { return resolveLocale; });
const isObject = val => val !== null && typeof val === 'object';
const defaultDelimiters = ['{', '}'];
class BaseFormatter {
  constructor() {
    this._caches = Object.create(null);
  }
  interpolate(message, values, delimiters = defaultDelimiters) {
    if (!values) {
      return [message];
    }
    let tokens = this._caches[message];
    if (!tokens) {
      tokens = parse(message, delimiters);
      this._caches[message] = tokens;
    }
    return compile(tokens, values);
  }
}
const RE_TOKEN_LIST_VALUE = /^(?:\d)+/;
const RE_TOKEN_NAMED_VALUE = /^(?:\w)+/;
function parse(format, [startDelimiter, endDelimiter]) {
  const tokens = [];
  let position = 0;
  let text = '';
  while (position < format.length) {
    let char = format[position++];
    if (char === startDelimiter) {
      if (text) {
        tokens.push({
          type: 'text',
          value: text
        });
      }
      text = '';
      let sub = '';
      char = format[position++];
      while (char !== undefined && char !== endDelimiter) {
        sub += char;
        char = format[position++];
      }
      const isClosed = char === endDelimiter;
      const type = RE_TOKEN_LIST_VALUE.test(sub) ? 'list' : isClosed && RE_TOKEN_NAMED_VALUE.test(sub) ? 'named' : 'unknown';
      tokens.push({
        value: sub,
        type
      });
    }
    //  else if (char === '%') {
    //   // when found rails i18n syntax, skip text capture
    //   if (format[position] !== '{') {
    //     text += char
    //   }
    // }
    else {
      text += char;
    }
  }
  text && tokens.push({
    type: 'text',
    value: text
  });
  return tokens;
}
function compile(tokens, values) {
  const compiled = [];
  let index = 0;
  const mode = Array.isArray(values) ? 'list' : isObject(values) ? 'named' : 'unknown';
  if (mode === 'unknown') {
    return compiled;
  }
  while (index < tokens.length) {
    const token = tokens[index];
    switch (token.type) {
      case 'text':
        compiled.push(token.value);
        break;
      case 'list':
        compiled.push(values[parseInt(token.value, 10)]);
        break;
      case 'named':
        if (mode === 'named') {
          compiled.push(values[token.value]);
        } else {
          if (true) {
            console.warn(`Type of token '${token.type}' and format of value '${mode}' don't match!`);
          }
        }
        break;
      case 'unknown':
        if (true) {
          console.warn(`Detect 'unknown' type of token!`);
        }
        break;
    }
    index++;
  }
  return compiled;
}
const LOCALE_ZH_HANS = 'zh-Hans';
const LOCALE_ZH_HANT = 'zh-Hant';
const LOCALE_EN = 'en';
const LOCALE_FR = 'fr';
const LOCALE_ES = 'es';
const hasOwnProperty = Object.prototype.hasOwnProperty;
const hasOwn = (val, key) => hasOwnProperty.call(val, key);
const defaultFormatter = new BaseFormatter();
function include(str, parts) {
  return !!parts.find(part => str.indexOf(part) !== -1);
}
function startsWith(str, parts) {
  return parts.find(part => str.indexOf(part) === 0);
}
function normalizeLocale(locale, messages) {
  if (!locale) {
    return;
  }
  locale = locale.trim().replace(/_/g, '-');
  if (messages && messages[locale]) {
    return locale;
  }
  locale = locale.toLowerCase();
  if (locale === 'chinese') {
    // 支付宝
    return LOCALE_ZH_HANS;
  }
  if (locale.indexOf('zh') === 0) {
    if (locale.indexOf('-hans') > -1) {
      return LOCALE_ZH_HANS;
    }
    if (locale.indexOf('-hant') > -1) {
      return LOCALE_ZH_HANT;
    }
    if (include(locale, ['-tw', '-hk', '-mo', '-cht'])) {
      return LOCALE_ZH_HANT;
    }
    return LOCALE_ZH_HANS;
  }
  let locales = [LOCALE_EN, LOCALE_FR, LOCALE_ES];
  if (messages && Object.keys(messages).length > 0) {
    locales = Object.keys(messages);
  }
  const lang = startsWith(locale, locales);
  if (lang) {
    return lang;
  }
}
class I18n {
  constructor({
    locale,
    fallbackLocale,
    messages,
    watcher,
    formater
  }) {
    this.locale = LOCALE_EN;
    this.fallbackLocale = LOCALE_EN;
    this.message = {};
    this.messages = {};
    this.watchers = [];
    if (fallbackLocale) {
      this.fallbackLocale = fallbackLocale;
    }
    this.formater = formater || defaultFormatter;
    this.messages = messages || {};
    this.setLocale(locale || LOCALE_EN);
    if (watcher) {
      this.watchLocale(watcher);
    }
  }
  setLocale(locale) {
    const oldLocale = this.locale;
    this.locale = normalizeLocale(locale, this.messages) || this.fallbackLocale;
    if (!this.messages[this.locale]) {
      // 可能初始化时不存在
      this.messages[this.locale] = {};
    }
    this.message = this.messages[this.locale];
    // 仅发生变化时，通知
    if (oldLocale !== this.locale) {
      this.watchers.forEach(watcher => {
        watcher(this.locale, oldLocale);
      });
    }
  }
  getLocale() {
    return this.locale;
  }
  watchLocale(fn) {
    const index = this.watchers.push(fn) - 1;
    return () => {
      this.watchers.splice(index, 1);
    };
  }
  add(locale, message, override = true) {
    const curMessages = this.messages[locale];
    if (curMessages) {
      if (override) {
        Object.assign(curMessages, message);
      } else {
        Object.keys(message).forEach(key => {
          if (!hasOwn(curMessages, key)) {
            curMessages[key] = message[key];
          }
        });
      }
    } else {
      this.messages[locale] = message;
    }
  }
  f(message, values, delimiters) {
    return this.formater.interpolate(message, values, delimiters).join('');
  }
  t(key, locale, values) {
    let message = this.message;
    if (typeof locale === 'string') {
      locale = normalizeLocale(locale, this.messages);
      locale && (message = this.messages[locale]);
    } else {
      values = locale;
    }
    if (!hasOwn(message, key)) {
      console.warn(`Cannot translate the value of keypath ${key}. Use the value of keypath as default.`);
      return key;
    }
    return this.formater.interpolate(message[key], values).join('');
  }
}
function watchAppLocale(appVm, i18n) {
  // 需要保证 watch 的触发在组件渲染之前
  if (appVm.$watchLocale) {
    // vue2
    appVm.$watchLocale(newLocale => {
      i18n.setLocale(newLocale);
    });
  } else {
    appVm.$watch(() => appVm.$locale, newLocale => {
      i18n.setLocale(newLocale);
    });
  }
}
function getDefaultLocale() {
  if (typeof uni !== 'undefined' && uni.getLocale) {
    return uni.getLocale();
  }
  // 小程序平台，uni 和 uni-i18n 互相引用，导致访问不到 uni，故在 global 上挂了 getLocale
  if (typeof global !== 'undefined' && global.getLocale) {
    return global.getLocale();
  }
  return LOCALE_EN;
}
function initVueI18n(locale, messages = {}, fallbackLocale, watcher) {
  // 兼容旧版本入参
  if (typeof locale !== 'string') {
    [locale, messages] = [messages, locale];
  }
  if (typeof locale !== 'string') {
    // 因为小程序平台，uni-i18n 和 uni 互相引用，导致此时访问 uni 时，为 undefined
    locale = getDefaultLocale();
  }
  if (typeof fallbackLocale !== 'string') {
    fallbackLocale = typeof __uniConfig !== 'undefined' && __uniConfig.fallbackLocale || LOCALE_EN;
  }
  const i18n = new I18n({
    locale,
    fallbackLocale,
    messages,
    watcher
  });
  let t = (key, values) => {
    if (typeof getApp !== 'function') {
      // app view
      /* eslint-disable no-func-assign */
      t = function (key, values) {
        return i18n.t(key, values);
      };
    } else {
      let isWatchedAppLocale = false;
      t = function (key, values) {
        const appVm = getApp().$vm;
        // 可能$vm还不存在，比如在支付宝小程序中，组件定义较早，在props的default里使用了t()函数（如uni-goods-nav），此时app还未初始化
        // options: {
        // 	type: Array,
        // 	default () {
        // 		return [{
        // 			icon: 'shop',
        // 			text: t("uni-goods-nav.options.shop"),
        // 		}, {
        // 			icon: 'cart',
        // 			text: t("uni-goods-nav.options.cart")
        // 		}]
        // 	}
        // },
        if (appVm) {
          // 触发响应式
          appVm.$locale;
          if (!isWatchedAppLocale) {
            isWatchedAppLocale = true;
            watchAppLocale(appVm, i18n);
          }
        }
        return i18n.t(key, values);
      };
    }
    return t(key, values);
  };
  return {
    i18n,
    f(message, values, delimiters) {
      return i18n.f(message, values, delimiters);
    },
    t(key, values) {
      return t(key, values);
    },
    add(locale, message, override = true) {
      return i18n.add(locale, message, override);
    },
    watch(fn) {
      return i18n.watchLocale(fn);
    },
    getLocale() {
      return i18n.getLocale();
    },
    setLocale(newLocale) {
      return i18n.setLocale(newLocale);
    }
  };
}
const isString = val => typeof val === 'string';
let formater;
function hasI18nJson(jsonObj, delimiters) {
  if (!formater) {
    formater = new BaseFormatter();
  }
  return walkJsonObj(jsonObj, (jsonObj, key) => {
    const value = jsonObj[key];
    if (isString(value)) {
      if (isI18nStr(value, delimiters)) {
        return true;
      }
    } else {
      return hasI18nJson(value, delimiters);
    }
  });
}
function parseI18nJson(jsonObj, values, delimiters) {
  if (!formater) {
    formater = new BaseFormatter();
  }
  walkJsonObj(jsonObj, (jsonObj, key) => {
    const value = jsonObj[key];
    if (isString(value)) {
      if (isI18nStr(value, delimiters)) {
        jsonObj[key] = compileStr(value, values, delimiters);
      }
    } else {
      parseI18nJson(value, values, delimiters);
    }
  });
  return jsonObj;
}
function compileI18nJsonStr(jsonStr, {
  locale,
  locales,
  delimiters
}) {
  if (!isI18nStr(jsonStr, delimiters)) {
    return jsonStr;
  }
  if (!formater) {
    formater = new BaseFormatter();
  }
  const localeValues = [];
  Object.keys(locales).forEach(name => {
    if (name !== locale) {
      localeValues.push({
        locale: name,
        values: locales[name]
      });
    }
  });
  localeValues.unshift({
    locale,
    values: locales[locale]
  });
  try {
    return JSON.stringify(compileJsonObj(JSON.parse(jsonStr), localeValues, delimiters), null, 2);
  } catch (e) {}
  return jsonStr;
}
function isI18nStr(value, delimiters) {
  return value.indexOf(delimiters[0]) > -1;
}
function compileStr(value, values, delimiters) {
  return formater.interpolate(value, values, delimiters).join('');
}
function compileValue(jsonObj, key, localeValues, delimiters) {
  const value = jsonObj[key];
  if (isString(value)) {
    // 存在国际化
    if (isI18nStr(value, delimiters)) {
      jsonObj[key] = compileStr(value, localeValues[0].values, delimiters);
      if (localeValues.length > 1) {
        // 格式化国际化语言
        const valueLocales = jsonObj[key + 'Locales'] = {};
        localeValues.forEach(localValue => {
          valueLocales[localValue.locale] = compileStr(value, localValue.values, delimiters);
        });
      }
    }
  } else {
    compileJsonObj(value, localeValues, delimiters);
  }
}
function compileJsonObj(jsonObj, localeValues, delimiters) {
  walkJsonObj(jsonObj, (jsonObj, key) => {
    compileValue(jsonObj, key, localeValues, delimiters);
  });
  return jsonObj;
}
function walkJsonObj(jsonObj, walk) {
  if (Array.isArray(jsonObj)) {
    for (let i = 0; i < jsonObj.length; i++) {
      if (walk(jsonObj, i)) {
        return true;
      }
    }
  } else if (isObject(jsonObj)) {
    for (const key in jsonObj) {
      if (walk(jsonObj, key)) {
        return true;
      }
    }
  }
  return false;
}
function resolveLocale(locales) {
  return locale => {
    if (!locale) {
      return locale;
    }
    locale = normalizeLocale(locale) || locale;
    return resolveLocaleChain(locale).find(locale => locales.indexOf(locale) > -1);
  };
}
function resolveLocaleChain(locale) {
  const chain = [];
  const tokens = locale.split('-');
  while (tokens.length) {
    chain.push(tokens.join('-'));
    tokens.pop();
  }
  return chain;
}

/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"], __webpack_require__(/*! ./../../../webpack/buildin/global.js */ 3)))

/***/ }),

/***/ 40:
/*!*********************************************!*\
  !*** ./uview-ui/libs/function/getParent.js ***!
  \*********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "default", function() { return getParent; });
// 获取父组件的参数，因为支付宝小程序不支持provide/inject的写法
// this.$parent在非H5中，可以准确获取到父组件，但是在H5中，需要多次this.$parent.$parent.xxx
function getParent(name, keys) {
  let parent = this.$parent;
  // 通过while历遍，这里主要是为了H5需要多层解析的问题
  while (parent) {
    // 父组件
    if (parent.$options.name !== name) {
      // 如果组件的name不相等，继续上一级寻找
      parent = parent.$parent;
    } else {
      let data = {};
      // 判断keys是否数组，如果传过来的是一个数组，那么直接使用数组元素值当做键值去父组件寻找
      if (Array.isArray(keys)) {
        keys.map(val => {
          data[val] = parent[val] ? parent[val] : '';
        });
      } else {
        // 历遍传过来的对象参数
        for (let i in keys) {
          // 如果子组件有此值则用，无此值则用父组件的值
          // 判断是否空数组，如果是，则用父组件的值，否则用子组件的值
          if (Array.isArray(keys[i])) {
            if (keys[i].length) {
              data[i] = keys[i];
            } else {
              data[i] = parent[i];
            }
          } else if (keys[i].constructor === Object) {
            // 判断是否对象，如果是对象，且有属性，那么使用子组件的值，否则使用父组件的值
            if (Object.keys(keys[i]).length) {
              data[i] = keys[i];
            } else {
              data[i] = parent[i];
            }
          } else {
            // 只要子组件有传值，即使是false值，也是“传值”了，也需要覆盖父组件的同名参数
            data[i] = keys[i] || keys[i] === false ? keys[i] : parent[i];
          }
        }
      }
      return data;
    }
  }
  return {};
}

/***/ }),

/***/ 41:
/*!*******************************************!*\
  !*** ./uview-ui/libs/function/$parent.js ***!
  \*******************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "default", function() { return $parent; });
// 获取父组件的参数，因为支付宝小程序不支持provide/inject的写法
// this.$parent在非H5中，可以准确获取到父组件，但是在H5中，需要多次this.$parent.$parent.xxx
// 这里默认值等于undefined有它的含义，因为最顶层元素(组件)的$parent就是undefined，意味着不传name
// 值(默认为undefined)，就是查找最顶层的$parent
function $parent(name = undefined) {
  let parent = this.$parent;
  // 通过while历遍，这里主要是为了H5需要多层解析的问题
  while (parent) {
    // 父组件
    if (parent.$options && parent.$options.name !== name) {
      // 如果组件的name不相等，继续上一级寻找
      parent = parent.$parent;
    } else {
      return parent;
    }
  }
  return false;
}

/***/ }),

/***/ 42:
/*!***************************************!*\
  !*** ./uview-ui/libs/function/sys.js ***!
  \***************************************/
/*! exports provided: os, sys */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "os", function() { return os; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "sys", function() { return sys; });
function os() {
  return uni.getSystemInfoSync().platform;
}
;
function sys() {
  return uni.getSystemInfoSync();
}
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 43:
/*!********************************************!*\
  !*** ./uview-ui/libs/function/debounce.js ***!
  \********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
let timeout = null;

/**
 * 防抖原理：一定时间内，只有最后一次操作，再过wait毫秒后才执行函数
 * 
 * @param {Function} func 要执行的回调函数 
 * @param {Number} wait 延时的时间
 * @param {Boolean} immediate 是否立即执行 
 * @return null
 */
function debounce(func, wait = 500, immediate = false) {
  // 清除定时器
  if (timeout !== null) clearTimeout(timeout);
  // 立即执行，此类情况一般用不到
  if (immediate) {
    var callNow = !timeout;
    timeout = setTimeout(function () {
      timeout = null;
    }, wait);
    if (callNow) typeof func === 'function' && func();
  } else {
    // 设置定时器，当最后一次操作后，timeout不会再被清除，所以在延时wait毫秒后执行func回调方法
    timeout = setTimeout(function () {
      typeof func === 'function' && func();
    }, wait);
  }
}
/* harmony default export */ __webpack_exports__["default"] = (debounce);

/***/ }),

/***/ 44:
/*!********************************************!*\
  !*** ./uview-ui/libs/function/throttle.js ***!
  \********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
let timer, flag;
/**
 * 节流原理：在一定时间内，只能触发一次
 * 
 * @param {Function} func 要执行的回调函数 
 * @param {Number} wait 延时的时间
 * @param {Boolean} immediate 是否立即执行
 * @return null
 */
function throttle(func, wait = 500, immediate = true) {
  if (immediate) {
    if (!flag) {
      flag = true;
      // 如果是立即执行，则在wait毫秒内开始时执行
      typeof func === 'function' && func();
      timer = setTimeout(() => {
        flag = false;
      }, wait);
    }
  } else {
    if (!flag) {
      flag = true;
      // 如果是非立即执行，则在wait毫秒内的结束处执行
      timer = setTimeout(() => {
        flag = false;
        typeof func === 'function' && func();
      }, wait);
    }
  }
}
;
/* harmony default export */ __webpack_exports__["default"] = (throttle);

/***/ }),

/***/ 45:
/*!****************************************!*\
  !*** ./uview-ui/libs/config/config.js ***!
  \****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
// 此版本发布于2020-03-17
let version = '1.8.4';
/* harmony default export */ __webpack_exports__["default"] = ({
  v: version,
  version: version,
  // 主题名称
  type: ['primary', 'success', 'info', 'error', 'warning']
});

/***/ }),

/***/ 46:
/*!****************************************!*\
  !*** ./uview-ui/libs/config/zIndex.js ***!
  \****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
// uniapp在H5中各API的z-index值如下：
/**
 * actionsheet: 999
 * modal: 999
 * navigate: 998
 * tabbar: 998
 * toast: 999
 */

/* harmony default export */ __webpack_exports__["default"] = ({
  toast: 10090,
  noNetwork: 10080,
  // popup包含popup，actionsheet，keyboard，picker的值
  popup: 10075,
  mask: 10070,
  navbar: 980,
  topTips: 975,
  sticky: 970,
  indexListSticky: 965
});

/***/ }),

/***/ 47:
/*!****************************!*\
  !*** ./common/fa.mixin.js ***!
  \****************************/
/*! exports provided: tools, avatar, loginfunc */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni, wx) {/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "tools", function() { return tools; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "avatar", function() { return avatar; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "loginfunc", function() { return loginfunc; });
const tools = {
  filters: {},
  computed: {},
  methods: {
    //富文本的回调
    navigate(e) {
      if (e.href && e.href.indexOf('http') == -1) {
        //不完整的链接					

        this.$util.uniCopy({
          content: this.vuex_config.upload.cdnurl + e.href,
          success: () => {
            this.$u.toast('链接已复制,请在浏览器中打开');
          }
        });
      }
    },
    //卡片跳转
    diylinkpress(e) {
      e.ignore();
      this.goPage(e.href);
      return false;
    },
    //预览图片
    lookImage(index) {
      uni.previewImage({
        current: index,
        urls: this.imagesList,
        longPressActions: {
          itemList: ['发送给朋友', '保存图片', '收藏'],
          success: function (data) {
            console.log(data);
          },
          fail: function (err) {
            console.log(err.errMsg);
          }
        }
      });
    },
    //复制url
    copyUrl(url = '') {
      this.$util.uniCopy({
        content: url || window.location.href,
        success: () => {
          this.$u.toast('复制成功，请去粘贴发送给好友吧');
        },
        error: () => {
          console.log('复制失败！');
        }
      });
    },
    //cdnurl
    cdnurl(url) {
      if (!/^((?:[a-z]+:)?\/\/|data:image\/)(.*)/.test(url)) {
        return this.vuex_config.upload.cdnurl + url;
      }
      return url;
    },
    //页面跳转
    goPage(path, auth) {
      if (path == 'out') {
        this.$u.vuex('vuex_token', '');
        this.$u.vuex('vuex_user', {});
        this.$u.vuex('vuex_openid', '');
        return;
      }
      if (auth && !this.vuex_token) {
        let pages = getCurrentPages();
        // 页面栈中的最后一个即为项为当前页面，route属性为页面路径
        let lastPageUrl = pages[pages.length - 1].$page.fullPath;
        this.$u.vuex('vuex_lasturl', lastPageUrl);
        this.$u.route('/pages/login/mobilelogin');
        return;
      }
      uni.$u.route({
        url: path,
        complete(e) {
          console.log(e, path);
        }
      });
    },
    logistics(res) {
      if (this.vuex_config.logisticstype == 'kd100') {
        wx.navigateToMiniProgram({
          appId: 'wx6885acbedba59c14',
          path: `pages/result/result?nu=${res.expressno}&com=&querysource=third_xcx`,
          //备注：nu为快递单号，com为快递公司编码，com没有可不传
          extraData: {
            foo: 'bar'
          },
          success: res => {
            // 打开成功
          }
        });
      } else {
        this.goPage(`/pages/order/logistics?nu=${res.expressno}&coname=${res.expressname}&order_sn=${res.order_sn}`);
      }
    }
  }
};
//修改头像的事件
const avatar = {
  methods: {
    chooseAvatar() {
      uni.$on('uAvatarCropper', this.upload);
      this.$u.route({
        // 关于此路径，请见下方"注意事项"
        url: '/uview-ui/components/u-avatar-cropper/u-avatar-cropper',
        // 内部已设置以下默认参数值，可不传这些参数
        params: {
          // 输出图片宽度，高等于宽，单位px
          destWidth: 300,
          // 裁剪框宽度，高等于宽，单位px
          rectWidth: 300,
          // 输出的图片类型，如果'png'类型发现裁剪的图片太大，改成"jpg"即可
          fileType: 'jpg'
        }
      });
    },
    upload: async function (path) {
      uni.$off('uAvatarCropper', this.upload);
      // 可以在此上传到服务端
      try {
        let res = await this.$api.goUpload({
          filePath: path
        });
        if (!res.code) {
          this.$u.toast(res.msg);
        }
        this.form.avatar = res.data.url;
        this.url = res.data.fullurl;
        if (typeof this.editAvatar == 'function') {
          this.editAvatar();
        }
      } catch (e) {
        console.error(e);
        this.$u.toast('图片上传失败！');
      }
    }
  }
};

// 登录方法
const loginfunc = {
  methods: {
    // 登录成功
    async success(delta) {
      //重置用户信息
      let apptype = '';
      let platform = '';
      let logincode = '';
      platform = 'wechat';
      apptype = 'miniapp';
      logincode = await this.getMpCode();
      this.$api.getUserIndex({
        apptype,
        platform,
        logincode
      }).then(res => {
        if (res.code) {
          this.$u.vuex('vuex_user', res.data.userInfo);
          if (res.data.openid) {
            this.$u.vuex('vuex_openid', res.data.openid);
          }
        }
        console.log(delta);
        var pages = getCurrentPages();
        if (!delta) {
          delta = 0;
          for (let i = pages.length; i > 0; i--) {
            console.log(pages[i - 1].route);
            if (pages[i - 1].route.indexOf("pages/login/") == -1) {
              break;
            } else {
              delta++;
            }
          }
          //根据pages自动计算出的delta
          console.log(delta);
        }
        let url = this.vuex_lasturl || '/pages/index/index';
        //清空最后页面
        this.$u.vuex('vuex_lasturl', '');

        //不在H5

        if (typeof pages[delta] !== 'undefined') {
          uni.navigateBack({
            delta: delta
          });
        } else {
          uni.reLaunch({
            url: url
          });
        }

        // 在H5 刷新导致路由丢失
      });
    },
    // 获取手机号回调
    async getPhoneNumber(e) {
      if (e.detail.errMsg === "privacy permission is not authorized") {
        this.$refs.uToast.show({
          title: '授权失败，失败原因：未同意隐私协议',
          type: 'error'
        });
        return;
      }
      if (e.detail.errMsg === "privacy permission is not authorized in gap") {
        this.$refs.uToast.show({
          title: '授权失败，原因：未同意隐私协议，请稍后重试',
          type: 'error'
        });
        return;
      }
      if (e.detail.errMsg === "getPhoneNumber:fail user deny") {
        this.$refs.uToast.show({
          title: '授权失败，原因：用户拒绝',
          type: 'error'
        });
        return;
      }
      if (e.detail.errMsg !== "getPhoneNumber:ok") {
        this.$refs.uToast.show({
          title: '授权失败，原因：' + e.detail.errMsg,
          type: 'error'
        });
        return;
      }
      if (typeof this.agreeChecked !== 'undefined' && !this.agreeChecked) {
        this.$refs.uToast.show({
          title: '请阅读并同意遵守《用户协议》',
          type: 'error'
        });
        return;
      }
      let logincode = await this.getMpCode();
      this.$api.goWechatMobileLogin({
        code: e.detail.code,
        logincode: logincode,
        bind: this.is_bind || ''
      }).then(res => {
        if (res.code == 1) {
          this.$u.vuex('vuex_token', res.data.token);
          this.$u.vuex('vuex_openid', res.data.openid);
          this.success();
        } else {
          this.$u.toast(res.msg);
        }
      });
    },
    // 获取微信小程序用户openid
    async getWechatOpenid() {
      let logincode = await this.getMpCode();
      let res = await this.$api.getWechatOpenid({
        logincode: logincode
      });
      if (res.code && res.data.openid) {
        this.$u.vuex('vuex_openid', res.data.openid);
        return res.data.openid;
      }
      return '';
    },
    // 获取登录Code
    async getMpCode() {
      return new Promise((resolve, reject) => {
        uni.login({
          success: function (res) {
            if (res.code) {
              resolve(res.code);
            } else {
              //login成功，但是没有取到code
              reject('未取得code');
            }
          },
          fail: function (res) {
            reject('用户授权失败wx.login');
          }
        });
      });
    },
    // 微信授权登录
    async goMpLogin() {
      uni.showLoading({
        title: '登录中...'
      });
      let that = this;
      try {
        let code = await that.getMpCode();
        let data = {
          code: code,
          __token__: that.vuex__token__
        };
        //有推荐码的话带上
        if (that.vuex_invitecode) {
          data.invitecode = that.vuex_invitecode;
        }
        let res = await this.$api.gowxLogin(data);
        uni.hideLoading();
        if (!res.code) {
          this.$u.toast(res.msg);
          return;
        }
        if (res.data.user) {
          this.$u.vuex('vuex_token', res.data.user.token);
          this.success();
          return;
        }
        this.$u.vuex('vuex_third', res.data.third);

        //授权成功到登录或绑定页面
        this.$u.route('/pages/login/register?bind=bind');
      } catch (e) {
        uni.hideLoading();
        that.$u.toast(e);
      }
    },
    // 判断是否允许对应的登录方式
    checkLogintype(type) {
      return this.vuex_config.logintypearr && this.vuex_config.logintypearr.indexOf(type) > -1;
    }
  }
};
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"], __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/wx.js */ 1)["default"]))

/***/ }),

/***/ 48:
/*!****************************************!*\
  !*** ./uview-ui/libs/mixin/mpShare.js ***!
  \****************************************/
/*! no static exports found */
/***/ (function(module, exports) {

module.exports = {
  onLoad() {
    // 设置默认的转发参数
    this.$u.mpShare = {
      title: '',
      // 默认为小程序名称
      path: '',
      // 默认为当前页面路径
      imageUrl: '' // 默认为当前页面的截图
    };
  },
  onShareAppMessage() {
    return this.$u.mpShare;
  },
  onShareTimeline() {
    return this.$u.mpShare;
  }
};

/***/ }),

/***/ 49:
/*!**********************************!*\
  !*** ./common/fa.style.mixin.js ***!
  \**********************************/
/*! no static exports found */
/***/ (function(module, exports) {

module.exports = {
  computed: {
    theme() {
      let style = {};
      if (this.vuex_theme.value) {
        let theme = this.vuex_theme.value;
        let ladder = theme.ladder || 10;
        let number = theme.number || 9;
        let border = theme.border || 5;
        let colorArr = this.$u.colorGradient(theme.bgColor, theme.color, ladder);
        style = Object.assign({
          lightColor: colorArr[number] || '#f5f5f5',
          faBorderColor: colorArr[border] || '#f5f5f5'
        }, theme);
      } else {
        style = {
          bgColor: "#0301c5",
          color: "#ffffff",
          lightColor: '#f5f5f5',
          faBorderColor: '#f5f5f5'
        };
      }
      return style;
    },
    btnBgColor(param, type) {
      return (param, type) => {
        if (typeof type == 'undefined') {
          return param ? this.theme.bgColor : this.theme.lightColor;
        }
        return param == type ? this.theme.bgColor : this.theme.lightColor;
      };
    },
    btnColor(param, type) {
      return (param, type) => {
        if (typeof type == 'undefined') {
          return param ? this.theme.color : this.theme.bgColor;
        }
        return param == type ? this.theme.color : this.theme.bgColor;
      };
    }
  }
};

/***/ }),

/***/ 498:
/*!***************************************!*\
  !*** ./uview-ui/libs/util/emitter.js ***!
  \***************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/**
 * 递归使用 call 方式this指向
 * @param componentName // 需要找的组件的名称
 * @param eventName // 事件名称
 * @param params // 需要传递的参数
 */
function broadcast(componentName, eventName, params) {
  // 循环子节点找到名称一样的子节点 否则 递归 当前子节点
  this.$children.map(child => {
    if (componentName === child.$options.name) {
      child.$emit.apply(child, [eventName].concat(params));
    } else {
      broadcast.apply(child, [componentName, eventName].concat(params));
    }
  });
}
/* harmony default export */ __webpack_exports__["default"] = ({
  methods: {
    /**
     * 派发 (向上查找) (一个)
     * @param componentName // 需要找的组件的名称
     * @param eventName // 事件名称
     * @param params // 需要传递的参数
     */
    dispatch(componentName, eventName, params) {
      let parent = this.$parent || this.$root; //$parent 找到最近的父节点 $root 根节点
      let name = parent.$options.name; // 获取当前组件实例的name
      // 如果当前有节点 && 当前没名称 且 当前名称等于需要传进来的名称的时候就去查找当前的节点
      // 循环出当前名称的一样的组件实例
      while (parent && (!name || name !== componentName)) {
        parent = parent.$parent;
        if (parent) {
          name = parent.$options.name;
        }
      }
      // 有节点表示当前找到了name一样的实例
      if (parent) {
        parent.$emit.apply(parent, [eventName].concat(params));
      }
    },
    /**
     * 广播 (向下查找) (广播多个)
     * @param componentName // 需要找的组件的名称
     * @param eventName // 事件名称
     * @param params // 需要传递的参数
     */
    broadcast(componentName, eventName, params) {
      broadcast.call(this, componentName, eventName, params);
    }
  }
});

/***/ }),

/***/ 5:
/*!******************************************************************************************!*\
  !*** ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/mp-vue/dist/mp.runtime.esm.js ***!
  \******************************************************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(global, Buffer) {/*!
 * Vue.js v2.6.11
 * (c) 2014-2026 Evan You
 * Released under the MIT License.
 */
/*  */

var emptyObject = Object.freeze({});

// These helpers produce better VM code in JS engines due to their
// explicitness and function inlining.
function isUndef(v) {
  return v === undefined || v === null;
}
function isDef(v) {
  return v !== undefined && v !== null;
}
function isTrue(v) {
  return v === true;
}
function isFalse(v) {
  return v === false;
}

/**
 * Check if value is primitive.
 */
function isPrimitive(value) {
  return typeof value === 'string' || typeof value === 'number' ||
  // $flow-disable-line
  typeof value === 'symbol' || typeof value === 'boolean';
}

/**
 * Quick object check - this is primarily used to tell
 * Objects from primitive values when we know the value
 * is a JSON-compliant type.
 */
function isObject(obj) {
  return obj !== null && typeof obj === 'object';
}

/**
 * Get the raw type string of a value, e.g., [object Object].
 */
var _toString = Object.prototype.toString;
function toRawType(value) {
  return _toString.call(value).slice(8, -1);
}

/**
 * Strict object type check. Only returns true
 * for plain JavaScript objects.
 */
function isPlainObject(obj) {
  return _toString.call(obj) === '[object Object]';
}
function isRegExp(v) {
  return _toString.call(v) === '[object RegExp]';
}

/**
 * Check if val is a valid array index.
 */
function isValidArrayIndex(val) {
  var n = parseFloat(String(val));
  return n >= 0 && Math.floor(n) === n && isFinite(val);
}
function isPromise(val) {
  return isDef(val) && typeof val.then === 'function' && typeof val.catch === 'function';
}

/**
 * Convert a value to a string that is actually rendered.
 */
function toString(val) {
  return val == null ? '' : Array.isArray(val) || isPlainObject(val) && val.toString === _toString ? JSON.stringify(val, null, 2) : String(val);
}

/**
 * Convert an input value to a number for persistence.
 * If the conversion fails, return original string.
 */
function toNumber(val) {
  var n = parseFloat(val);
  return isNaN(n) ? val : n;
}

/**
 * Make a map and return a function for checking if a key
 * is in that map.
 */
function makeMap(str, expectsLowerCase) {
  var map = Object.create(null);
  var list = str.split(',');
  for (var i = 0; i < list.length; i++) {
    map[list[i]] = true;
  }
  return expectsLowerCase ? function (val) {
    return map[val.toLowerCase()];
  } : function (val) {
    return map[val];
  };
}

/**
 * Check if a tag is a built-in tag.
 */
var isBuiltInTag = makeMap('slot,component', true);

/**
 * Check if an attribute is a reserved attribute.
 */
var isReservedAttribute = makeMap('key,ref,slot,slot-scope,is');

/**
 * Remove an item from an array.
 */
function remove(arr, item) {
  if (arr.length) {
    var index = arr.indexOf(item);
    if (index > -1) {
      return arr.splice(index, 1);
    }
  }
}

/**
 * Check whether an object has the property.
 */
var hasOwnProperty = Object.prototype.hasOwnProperty;
function hasOwn(obj, key) {
  return hasOwnProperty.call(obj, key);
}

/**
 * Create a cached version of a pure function.
 */
function cached(fn) {
  var cache = Object.create(null);
  return function cachedFn(str) {
    var hit = cache[str];
    return hit || (cache[str] = fn(str));
  };
}

/**
 * Camelize a hyphen-delimited string.
 */
var camelizeRE = /-(\w)/g;
var camelize = cached(function (str) {
  return str.replace(camelizeRE, function (_, c) {
    return c ? c.toUpperCase() : '';
  });
});

/**
 * Capitalize a string.
 */
var capitalize = cached(function (str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
});

/**
 * Hyphenate a camelCase string.
 */
var hyphenateRE = /\B([A-Z])/g;
var hyphenate = cached(function (str) {
  return str.replace(hyphenateRE, '-$1').toLowerCase();
});

/**
 * Simple bind polyfill for environments that do not support it,
 * e.g., PhantomJS 1.x. Technically, we don't need this anymore
 * since native bind is now performant enough in most browsers.
 * But removing it would mean breaking code that was able to run in
 * PhantomJS 1.x, so this must be kept for backward compatibility.
 */

/* istanbul ignore next */
function polyfillBind(fn, ctx) {
  function boundFn(a) {
    var l = arguments.length;
    return l ? l > 1 ? fn.apply(ctx, arguments) : fn.call(ctx, a) : fn.call(ctx);
  }
  boundFn._length = fn.length;
  return boundFn;
}
function nativeBind(fn, ctx) {
  return fn.bind(ctx);
}
var bind = Function.prototype.bind ? nativeBind : polyfillBind;

/**
 * Convert an Array-like object to a real Array.
 */
function toArray(list, start) {
  start = start || 0;
  var i = list.length - start;
  var ret = new Array(i);
  while (i--) {
    ret[i] = list[i + start];
  }
  return ret;
}

/**
 * Mix properties into target object.
 */
function extend(to, _from) {
  for (var key in _from) {
    to[key] = _from[key];
  }
  return to;
}

/**
 * Merge an Array of Objects into a single Object.
 */
function toObject(arr) {
  var res = {};
  for (var i = 0; i < arr.length; i++) {
    if (arr[i]) {
      extend(res, arr[i]);
    }
  }
  return res;
}

/* eslint-disable no-unused-vars */

/**
 * Perform no operation.
 * Stubbing args to make Flow happy without leaving useless transpiled code
 * with ...rest (https://flow.org/blog/2017/05/07/Strict-Function-Call-Arity/).
 */
function noop(a, b, c) {}

/**
 * Always return false.
 */
var no = function (a, b, c) {
  return false;
};

/* eslint-enable no-unused-vars */

/**
 * Return the same value.
 */
var identity = function (_) {
  return _;
};

/**
 * Check if two values are loosely equal - that is,
 * if they are plain objects, do they have the same shape?
 */
function looseEqual(a, b) {
  if (a === b) {
    return true;
  }
  var isObjectA = isObject(a);
  var isObjectB = isObject(b);
  if (isObjectA && isObjectB) {
    try {
      var isArrayA = Array.isArray(a);
      var isArrayB = Array.isArray(b);
      if (isArrayA && isArrayB) {
        return a.length === b.length && a.every(function (e, i) {
          return looseEqual(e, b[i]);
        });
      } else if (a instanceof Date && b instanceof Date) {
        return a.getTime() === b.getTime();
      } else if (!isArrayA && !isArrayB) {
        var keysA = Object.keys(a);
        var keysB = Object.keys(b);
        return keysA.length === keysB.length && keysA.every(function (key) {
          return looseEqual(a[key], b[key]);
        });
      } else {
        /* istanbul ignore next */
        return false;
      }
    } catch (e) {
      /* istanbul ignore next */
      return false;
    }
  } else if (!isObjectA && !isObjectB) {
    return String(a) === String(b);
  } else {
    return false;
  }
}

/**
 * Return the first index at which a loosely equal value can be
 * found in the array (if value is a plain object, the array must
 * contain an object of the same shape), or -1 if it is not present.
 */
function looseIndexOf(arr, val) {
  for (var i = 0; i < arr.length; i++) {
    if (looseEqual(arr[i], val)) {
      return i;
    }
  }
  return -1;
}

/**
 * Ensure a function is called only once.
 */
function once(fn) {
  var called = false;
  return function () {
    if (!called) {
      called = true;
      fn.apply(this, arguments);
    }
  };
}
var ASSET_TYPES = ['component', 'directive', 'filter'];
var LIFECYCLE_HOOKS = ['beforeCreate', 'created', 'beforeMount', 'mounted', 'beforeUpdate', 'updated', 'beforeDestroy', 'destroyed', 'activated', 'deactivated', 'errorCaptured', 'serverPrefetch'];

/*  */

var config = {
  /**
   * Option merge strategies (used in core/util/options)
   */
  // $flow-disable-line
  optionMergeStrategies: Object.create(null),
  /**
   * Whether to suppress warnings.
   */
  silent: false,
  /**
   * Show production mode tip message on boot?
   */
  productionTip: "development" !== 'production',
  /**
   * Whether to enable devtools
   */
  devtools: "development" !== 'production',
  /**
   * Whether to record perf
   */
  performance: false,
  /**
   * Error handler for watcher errors
   */
  errorHandler: null,
  /**
   * Warn handler for watcher warns
   */
  warnHandler: null,
  /**
   * Ignore certain custom elements
   */
  ignoredElements: [],
  /**
   * Custom user key aliases for v-on
   */
  // $flow-disable-line
  keyCodes: Object.create(null),
  /**
   * Check if a tag is reserved so that it cannot be registered as a
   * component. This is platform-dependent and may be overwritten.
   */
  isReservedTag: no,
  /**
   * Check if an attribute is reserved so that it cannot be used as a component
   * prop. This is platform-dependent and may be overwritten.
   */
  isReservedAttr: no,
  /**
   * Check if a tag is an unknown element.
   * Platform-dependent.
   */
  isUnknownElement: no,
  /**
   * Get the namespace of an element
   */
  getTagNamespace: noop,
  /**
   * Parse the real tag name for the specific platform.
   */
  parsePlatformTagName: identity,
  /**
   * Check if an attribute must be bound using property, e.g. value
   * Platform-dependent.
   */
  mustUseProp: no,
  /**
   * Perform updates asynchronously. Intended to be used by Vue Test Utils
   * This will significantly reduce performance if set to false.
   */
  async: true,
  /**
   * Exposed for legacy reasons
   */
  _lifecycleHooks: LIFECYCLE_HOOKS
};

/*  */

/**
 * unicode letters used for parsing html tags, component names and property paths.
 * using https://www.w3.org/TR/html53/semantics-scripting.html#potentialcustomelementname
 * skipping \u10000-\uEFFFF due to it freezing up PhantomJS
 */
var unicodeRegExp = /a-zA-Z\u00B7\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u037D\u037F-\u1FFF\u200C-\u200D\u203F-\u2040\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD/;

/**
 * Check if a string starts with $ or _
 */
function isReserved(str) {
  var c = (str + '').charCodeAt(0);
  return c === 0x24 || c === 0x5F;
}

/**
 * Define a property.
 */
function def(obj, key, val, enumerable) {
  Object.defineProperty(obj, key, {
    value: val,
    enumerable: !!enumerable,
    writable: true,
    configurable: true
  });
}

/**
 * Parse simple path.
 */
var bailRE = new RegExp("[^" + unicodeRegExp.source + ".$_\\d]");
function parsePath(path) {
  if (bailRE.test(path)) {
    return;
  }
  var segments = path.split('.');
  return function (obj) {
    for (var i = 0; i < segments.length; i++) {
      if (!obj) {
        return;
      }
      obj = obj[segments[i]];
    }
    return obj;
  };
}

/*  */

// can we use __proto__?
var hasProto = '__proto__' in {};

// Browser environment sniffing
var inBrowser = typeof window !== 'undefined';
var inWeex = typeof WXEnvironment !== 'undefined' && !!WXEnvironment.platform;
var weexPlatform = inWeex && WXEnvironment.platform.toLowerCase();
var UA = inBrowser && window.navigator && window.navigator.userAgent && window.navigator.userAgent.toLowerCase();
var isIE = UA && /msie|trident/.test(UA);
var isIE9 = UA && UA.indexOf('msie 9.0') > 0;
var isEdge = UA && UA.indexOf('edge/') > 0;
var isAndroid = UA && UA.indexOf('android') > 0 || weexPlatform === 'android';
var isIOS = UA && /iphone|ipad|ipod|ios/.test(UA) || weexPlatform === 'ios';
var isChrome = UA && /chrome\/\d+/.test(UA) && !isEdge;
var isPhantomJS = UA && /phantomjs/.test(UA);
var isFF = UA && UA.match(/firefox\/(\d+)/);

// Firefox has a "watch" function on Object.prototype...
var nativeWatch = {}.watch;
if (inBrowser) {
  try {
    var opts = {};
    Object.defineProperty(opts, 'passive', {
      get: function get() {}
    }); // https://github.com/facebook/flow/issues/285
    window.addEventListener('test-passive', null, opts);
  } catch (e) {}
}

// this needs to be lazy-evaled because vue may be required before
// vue-server-renderer can set VUE_ENV
var _isServer;
var isServerRendering = function () {
  if (_isServer === undefined) {
    /* istanbul ignore if */
    if (!inBrowser && !inWeex && typeof global !== 'undefined') {
      // detect presence of vue-server-renderer and avoid
      // Webpack shimming the process
      _isServer = global['process'] && global['process'].env.VUE_ENV === 'server';
    } else {
      _isServer = false;
    }
  }
  return _isServer;
};

// detect devtools
var devtools = inBrowser && window.__VUE_DEVTOOLS_GLOBAL_HOOK__;

/* istanbul ignore next */
function isNative(Ctor) {
  return typeof Ctor === 'function' && /native code/.test(Ctor.toString());
}
var hasSymbol = typeof Symbol !== 'undefined' && isNative(Symbol) && typeof Reflect !== 'undefined' && isNative(Reflect.ownKeys);
var _Set;
/* istanbul ignore if */ // $flow-disable-line
if (typeof Set !== 'undefined' && isNative(Set)) {
  // use native Set when available.
  _Set = Set;
} else {
  // a non-standard Set polyfill that only works with primitive keys.
  _Set = /*@__PURE__*/function () {
    function Set() {
      this.set = Object.create(null);
    }
    Set.prototype.has = function has(key) {
      return this.set[key] === true;
    };
    Set.prototype.add = function add(key) {
      this.set[key] = true;
    };
    Set.prototype.clear = function clear() {
      this.set = Object.create(null);
    };
    return Set;
  }();
}

/*  */

var warn = noop;
var tip = noop;
var generateComponentTrace = noop; // work around flow check
var formatComponentName = noop;
if (true) {
  var hasConsole = typeof console !== 'undefined';
  var classifyRE = /(?:^|[-_])(\w)/g;
  var classify = function (str) {
    return str.replace(classifyRE, function (c) {
      return c.toUpperCase();
    }).replace(/[-_]/g, '');
  };
  warn = function (msg, vm) {
    var trace = vm ? generateComponentTrace(vm) : '';
    if (config.warnHandler) {
      config.warnHandler.call(null, msg, vm, trace);
    } else if (hasConsole && !config.silent) {
      console.error("[Vue warn]: " + msg + trace);
    }
  };
  tip = function (msg, vm) {
    if (hasConsole && !config.silent) {
      console.warn("[Vue tip]: " + msg + (vm ? generateComponentTrace(vm) : ''));
    }
  };
  formatComponentName = function (vm, includeFile) {
    if (vm.$root === vm) {
      if (vm.$options && vm.$options.__file) {
        // fixed by xxxxxx
        return '' + vm.$options.__file;
      }
      return '<Root>';
    }
    var options = typeof vm === 'function' && vm.cid != null ? vm.options : vm._isVue ? vm.$options || vm.constructor.options : vm;
    var name = options.name || options._componentTag;
    var file = options.__file;
    if (!name && file) {
      var match = file.match(/([^/\\]+)\.vue$/);
      name = match && match[1];
    }
    return (name ? "<" + classify(name) + ">" : "<Anonymous>") + (file && includeFile !== false ? " at " + file : '');
  };
  var repeat = function (str, n) {
    var res = '';
    while (n) {
      if (n % 2 === 1) {
        res += str;
      }
      if (n > 1) {
        str += str;
      }
      n >>= 1;
    }
    return res;
  };
  generateComponentTrace = function (vm) {
    if (vm._isVue && vm.$parent) {
      var tree = [];
      var currentRecursiveSequence = 0;
      while (vm && vm.$options.name !== 'PageBody') {
        if (tree.length > 0) {
          var last = tree[tree.length - 1];
          if (last.constructor === vm.constructor) {
            currentRecursiveSequence++;
            vm = vm.$parent;
            continue;
          } else if (currentRecursiveSequence > 0) {
            tree[tree.length - 1] = [last, currentRecursiveSequence];
            currentRecursiveSequence = 0;
          }
        }
        !vm.$options.isReserved && tree.push(vm);
        vm = vm.$parent;
      }
      return '\n\nfound in\n\n' + tree.map(function (vm, i) {
        return "" + (i === 0 ? '---> ' : repeat(' ', 5 + i * 2)) + (Array.isArray(vm) ? formatComponentName(vm[0]) + "... (" + vm[1] + " recursive calls)" : formatComponentName(vm));
      }).join('\n');
    } else {
      return "\n\n(found in " + formatComponentName(vm) + ")";
    }
  };
}

/*  */

var uid = 0;

/**
 * A dep is an observable that can have multiple
 * directives subscribing to it.
 */
var Dep = function Dep() {
  this.id = uid++;
  this.subs = [];
};
Dep.prototype.addSub = function addSub(sub) {
  this.subs.push(sub);
};
Dep.prototype.removeSub = function removeSub(sub) {
  remove(this.subs, sub);
};
Dep.prototype.depend = function depend() {
  if (Dep.SharedObject.target) {
    Dep.SharedObject.target.addDep(this);
  }
};
Dep.prototype.notify = function notify() {
  // stabilize the subscriber list first
  var subs = this.subs.slice();
  if ( true && !config.async) {
    // subs aren't sorted in scheduler if not running async
    // we need to sort them now to make sure they fire in correct
    // order
    subs.sort(function (a, b) {
      return a.id - b.id;
    });
  }
  for (var i = 0, l = subs.length; i < l; i++) {
    subs[i].update();
  }
};

// The current target watcher being evaluated.
// This is globally unique because only one watcher
// can be evaluated at a time.
// fixed by xxxxxx (nvue shared vuex)
/* eslint-disable no-undef */
Dep.SharedObject = {};
Dep.SharedObject.target = null;
Dep.SharedObject.targetStack = [];
function pushTarget(target) {
  Dep.SharedObject.targetStack.push(target);
  Dep.SharedObject.target = target;
  Dep.target = target;
}
function popTarget() {
  Dep.SharedObject.targetStack.pop();
  Dep.SharedObject.target = Dep.SharedObject.targetStack[Dep.SharedObject.targetStack.length - 1];
  Dep.target = Dep.SharedObject.target;
}

/*  */

var VNode = function VNode(tag, data, children, text, elm, context, componentOptions, asyncFactory) {
  this.tag = tag;
  this.data = data;
  this.children = children;
  this.text = text;
  this.elm = elm;
  this.ns = undefined;
  this.context = context;
  this.fnContext = undefined;
  this.fnOptions = undefined;
  this.fnScopeId = undefined;
  this.key = data && data.key;
  this.componentOptions = componentOptions;
  this.componentInstance = undefined;
  this.parent = undefined;
  this.raw = false;
  this.isStatic = false;
  this.isRootInsert = true;
  this.isComment = false;
  this.isCloned = false;
  this.isOnce = false;
  this.asyncFactory = asyncFactory;
  this.asyncMeta = undefined;
  this.isAsyncPlaceholder = false;
};
var prototypeAccessors = {
  child: {
    configurable: true
  }
};

// DEPRECATED: alias for componentInstance for backwards compat.
/* istanbul ignore next */
prototypeAccessors.child.get = function () {
  return this.componentInstance;
};
Object.defineProperties(VNode.prototype, prototypeAccessors);
var createEmptyVNode = function (text) {
  if (text === void 0) text = '';
  var node = new VNode();
  node.text = text;
  node.isComment = true;
  return node;
};
function createTextVNode(val) {
  return new VNode(undefined, undefined, undefined, String(val));
}

// optimized shallow clone
// used for static nodes and slot nodes because they may be reused across
// multiple renders, cloning them avoids errors when DOM manipulations rely
// on their elm reference.
function cloneVNode(vnode) {
  var cloned = new VNode(vnode.tag, vnode.data,
  // #7975
  // clone children array to avoid mutating original in case of cloning
  // a child.
  vnode.children && vnode.children.slice(), vnode.text, vnode.elm, vnode.context, vnode.componentOptions, vnode.asyncFactory);
  cloned.ns = vnode.ns;
  cloned.isStatic = vnode.isStatic;
  cloned.key = vnode.key;
  cloned.isComment = vnode.isComment;
  cloned.fnContext = vnode.fnContext;
  cloned.fnOptions = vnode.fnOptions;
  cloned.fnScopeId = vnode.fnScopeId;
  cloned.asyncMeta = vnode.asyncMeta;
  cloned.isCloned = true;
  return cloned;
}

/*
 * not type checking this file because flow doesn't play well with
 * dynamically accessing methods on Array prototype
 */

var arrayProto = Array.prototype;
var arrayMethods = Object.create(arrayProto);
var methodsToPatch = ['push', 'pop', 'shift', 'unshift', 'splice', 'sort', 'reverse'];

/**
 * Intercept mutating methods and emit events
 */
methodsToPatch.forEach(function (method) {
  // cache original method
  var original = arrayProto[method];
  def(arrayMethods, method, function mutator() {
    var args = [],
      len = arguments.length;
    while (len--) args[len] = arguments[len];
    var result = original.apply(this, args);
    var ob = this.__ob__;
    var inserted;
    switch (method) {
      case 'push':
      case 'unshift':
        inserted = args;
        break;
      case 'splice':
        inserted = args.slice(2);
        break;
    }
    if (inserted) {
      ob.observeArray(inserted);
    }
    // notify change
    ob.dep.notify();
    return result;
  });
});

/*  */

var arrayKeys = Object.getOwnPropertyNames(arrayMethods);

/**
 * In some cases we may want to disable observation inside a component's
 * update computation.
 */
var shouldObserve = true;
function toggleObserving(value) {
  shouldObserve = value;
}

/**
 * Observer class that is attached to each observed
 * object. Once attached, the observer converts the target
 * object's property keys into getter/setters that
 * collect dependencies and dispatch updates.
 */
var Observer = function Observer(value) {
  this.value = value;
  this.dep = new Dep();
  this.vmCount = 0;
  def(value, '__ob__', this);
  if (Array.isArray(value)) {
    if (hasProto) {
      {
        // fixed by xxxxxx 微信小程序使用 plugins 之后，数组方法被直接挂载到了数组对象上，需要执行 copyAugment 逻辑
        if (value.push !== value.__proto__.push) {
          copyAugment(value, arrayMethods, arrayKeys);
        } else {
          protoAugment(value, arrayMethods);
        }
      }
    } else {
      copyAugment(value, arrayMethods, arrayKeys);
    }
    this.observeArray(value);
  } else {
    this.walk(value);
  }
};

/**
 * Walk through all properties and convert them into
 * getter/setters. This method should only be called when
 * value type is Object.
 */
Observer.prototype.walk = function walk(obj) {
  var keys = Object.keys(obj);
  for (var i = 0; i < keys.length; i++) {
    defineReactive$$1(obj, keys[i]);
  }
};

/**
 * Observe a list of Array items.
 */
Observer.prototype.observeArray = function observeArray(items) {
  for (var i = 0, l = items.length; i < l; i++) {
    observe(items[i]);
  }
};

// helpers

/**
 * Augment a target Object or Array by intercepting
 * the prototype chain using __proto__
 */
function protoAugment(target, src) {
  /* eslint-disable no-proto */
  target.__proto__ = src;
  /* eslint-enable no-proto */
}

/**
 * Augment a target Object or Array by defining
 * hidden properties.
 */
/* istanbul ignore next */
function copyAugment(target, src, keys) {
  for (var i = 0, l = keys.length; i < l; i++) {
    var key = keys[i];
    def(target, key, src[key]);
  }
}

/**
 * Attempt to create an observer instance for a value,
 * returns the new observer if successfully observed,
 * or the existing observer if the value already has one.
 */
function observe(value, asRootData) {
  if (!isObject(value) || value instanceof VNode) {
    return;
  }
  var ob;
  if (hasOwn(value, '__ob__') && value.__ob__ instanceof Observer) {
    ob = value.__ob__;
  } else if (shouldObserve && !isServerRendering() && (Array.isArray(value) || isPlainObject(value)) && Object.isExtensible(value) && !value._isVue && !value.__v_isMPComponent) {
    ob = new Observer(value);
  }
  if (asRootData && ob) {
    ob.vmCount++;
  }
  return ob;
}

/**
 * Define a reactive property on an Object.
 */
function defineReactive$$1(obj, key, val, customSetter, shallow) {
  var dep = new Dep();
  var property = Object.getOwnPropertyDescriptor(obj, key);
  if (property && property.configurable === false) {
    return;
  }

  // cater for pre-defined getter/setters
  var getter = property && property.get;
  var setter = property && property.set;
  if ((!getter || setter) && arguments.length === 2) {
    val = obj[key];
  }
  var childOb = !shallow && observe(val);
  Object.defineProperty(obj, key, {
    enumerable: true,
    configurable: true,
    get: function reactiveGetter() {
      var value = getter ? getter.call(obj) : val;
      if (Dep.SharedObject.target) {
        // fixed by xxxxxx
        dep.depend();
        if (childOb) {
          childOb.dep.depend();
          if (Array.isArray(value)) {
            dependArray(value);
          }
        }
      }
      return value;
    },
    set: function reactiveSetter(newVal) {
      var value = getter ? getter.call(obj) : val;
      /* eslint-disable no-self-compare */
      if (newVal === value || newVal !== newVal && value !== value) {
        return;
      }
      /* eslint-enable no-self-compare */
      if ( true && customSetter) {
        customSetter();
      }
      // #7981: for accessor properties without setter
      if (getter && !setter) {
        return;
      }
      if (setter) {
        setter.call(obj, newVal);
      } else {
        val = newVal;
      }
      childOb = !shallow && observe(newVal);
      dep.notify();
    }
  });
}

/**
 * Set a property on an object. Adds the new property and
 * triggers change notification if the property doesn't
 * already exist.
 */
function set(target, key, val) {
  if ( true && (isUndef(target) || isPrimitive(target))) {
    warn("Cannot set reactive property on undefined, null, or primitive value: " + target);
  }
  if (Array.isArray(target) && isValidArrayIndex(key)) {
    target.length = Math.max(target.length, key);
    target.splice(key, 1, val);
    return val;
  }
  if (key in target && !(key in Object.prototype)) {
    target[key] = val;
    return val;
  }
  var ob = target.__ob__;
  if (target._isVue || ob && ob.vmCount) {
     true && warn('Avoid adding reactive properties to a Vue instance or its root $data ' + 'at runtime - declare it upfront in the data option.');
    return val;
  }
  if (!ob) {
    target[key] = val;
    return val;
  }
  defineReactive$$1(ob.value, key, val);
  ob.dep.notify();
  return val;
}

/**
 * Delete a property and trigger change if necessary.
 */
function del(target, key) {
  if ( true && (isUndef(target) || isPrimitive(target))) {
    warn("Cannot delete reactive property on undefined, null, or primitive value: " + target);
  }
  if (Array.isArray(target) && isValidArrayIndex(key)) {
    target.splice(key, 1);
    return;
  }
  var ob = target.__ob__;
  if (target._isVue || ob && ob.vmCount) {
     true && warn('Avoid deleting properties on a Vue instance or its root $data ' + '- just set it to null.');
    return;
  }
  if (!hasOwn(target, key)) {
    return;
  }
  delete target[key];
  if (!ob) {
    return;
  }
  ob.dep.notify();
}

/**
 * Collect dependencies on array elements when the array is touched, since
 * we cannot intercept array element access like property getters.
 */
function dependArray(value) {
  for (var e = void 0, i = 0, l = value.length; i < l; i++) {
    e = value[i];
    e && e.__ob__ && e.__ob__.dep.depend();
    if (Array.isArray(e)) {
      dependArray(e);
    }
  }
}

/*  */

/**
 * Option overwriting strategies are functions that handle
 * how to merge a parent option value and a child option
 * value into the final value.
 */
var strats = config.optionMergeStrategies;

/**
 * Options with restrictions
 */
if (true) {
  strats.el = strats.propsData = function (parent, child, vm, key) {
    if (!vm) {
      warn("option \"" + key + "\" can only be used during instance " + 'creation with the `new` keyword.');
    }
    return defaultStrat(parent, child);
  };
}

/**
 * Helper that recursively merges two data objects together.
 */
function mergeData(to, from) {
  if (!from) {
    return to;
  }
  var key, toVal, fromVal;
  var keys = hasSymbol ? Reflect.ownKeys(from) : Object.keys(from);
  for (var i = 0; i < keys.length; i++) {
    key = keys[i];
    // in case the object is already observed...
    if (key === '__ob__') {
      continue;
    }
    toVal = to[key];
    fromVal = from[key];
    if (!hasOwn(to, key)) {
      set(to, key, fromVal);
    } else if (toVal !== fromVal && isPlainObject(toVal) && isPlainObject(fromVal)) {
      mergeData(toVal, fromVal);
    }
  }
  return to;
}

/**
 * Data
 */
function mergeDataOrFn(parentVal, childVal, vm) {
  if (!vm) {
    // in a Vue.extend merge, both should be functions
    if (!childVal) {
      return parentVal;
    }
    if (!parentVal) {
      return childVal;
    }
    // when parentVal & childVal are both present,
    // we need to return a function that returns the
    // merged result of both functions... no need to
    // check if parentVal is a function here because
    // it has to be a function to pass previous merges.
    return function mergedDataFn() {
      return mergeData(typeof childVal === 'function' ? childVal.call(this, this) : childVal, typeof parentVal === 'function' ? parentVal.call(this, this) : parentVal);
    };
  } else {
    return function mergedInstanceDataFn() {
      // instance merge
      var instanceData = typeof childVal === 'function' ? childVal.call(vm, vm) : childVal;
      var defaultData = typeof parentVal === 'function' ? parentVal.call(vm, vm) : parentVal;
      if (instanceData) {
        return mergeData(instanceData, defaultData);
      } else {
        return defaultData;
      }
    };
  }
}
strats.data = function (parentVal, childVal, vm) {
  if (!vm) {
    if (childVal && typeof childVal !== 'function') {
       true && warn('The "data" option should be a function ' + 'that returns a per-instance value in component ' + 'definitions.', vm);
      return parentVal;
    }
    return mergeDataOrFn(parentVal, childVal);
  }
  return mergeDataOrFn(parentVal, childVal, vm);
};

/**
 * Hooks and props are merged as arrays.
 */
function mergeHook(parentVal, childVal) {
  var res = childVal ? parentVal ? parentVal.concat(childVal) : Array.isArray(childVal) ? childVal : [childVal] : parentVal;
  return res ? dedupeHooks(res) : res;
}
function dedupeHooks(hooks) {
  var res = [];
  for (var i = 0; i < hooks.length; i++) {
    if (res.indexOf(hooks[i]) === -1) {
      res.push(hooks[i]);
    }
  }
  return res;
}
LIFECYCLE_HOOKS.forEach(function (hook) {
  strats[hook] = mergeHook;
});

/**
 * Assets
 *
 * When a vm is present (instance creation), we need to do
 * a three-way merge between constructor options, instance
 * options and parent options.
 */
function mergeAssets(parentVal, childVal, vm, key) {
  var res = Object.create(parentVal || null);
  if (childVal) {
     true && assertObjectType(key, childVal, vm);
    return extend(res, childVal);
  } else {
    return res;
  }
}
ASSET_TYPES.forEach(function (type) {
  strats[type + 's'] = mergeAssets;
});

/**
 * Watchers.
 *
 * Watchers hashes should not overwrite one
 * another, so we merge them as arrays.
 */
strats.watch = function (parentVal, childVal, vm, key) {
  // work around Firefox's Object.prototype.watch...
  if (parentVal === nativeWatch) {
    parentVal = undefined;
  }
  if (childVal === nativeWatch) {
    childVal = undefined;
  }
  /* istanbul ignore if */
  if (!childVal) {
    return Object.create(parentVal || null);
  }
  if (true) {
    assertObjectType(key, childVal, vm);
  }
  if (!parentVal) {
    return childVal;
  }
  var ret = {};
  extend(ret, parentVal);
  for (var key$1 in childVal) {
    var parent = ret[key$1];
    var child = childVal[key$1];
    if (parent && !Array.isArray(parent)) {
      parent = [parent];
    }
    ret[key$1] = parent ? parent.concat(child) : Array.isArray(child) ? child : [child];
  }
  return ret;
};

/**
 * Other object hashes.
 */
strats.props = strats.methods = strats.inject = strats.computed = function (parentVal, childVal, vm, key) {
  if (childVal && "development" !== 'production') {
    assertObjectType(key, childVal, vm);
  }
  if (!parentVal) {
    return childVal;
  }
  var ret = Object.create(null);
  extend(ret, parentVal);
  if (childVal) {
    extend(ret, childVal);
  }
  return ret;
};
strats.provide = mergeDataOrFn;

/**
 * Default strategy.
 */
var defaultStrat = function (parentVal, childVal) {
  return childVal === undefined ? parentVal : childVal;
};

/**
 * Validate component names
 */
function checkComponents(options) {
  for (var key in options.components) {
    validateComponentName(key);
  }
}
function validateComponentName(name) {
  if (!new RegExp("^[a-zA-Z][\\-\\.0-9_" + unicodeRegExp.source + "]*$").test(name)) {
    warn('Invalid component name: "' + name + '". Component names ' + 'should conform to valid custom element name in html5 specification.');
  }
  if (isBuiltInTag(name) || config.isReservedTag(name)) {
    warn('Do not use built-in or reserved HTML elements as component ' + 'id: ' + name);
  }
}

/**
 * Ensure all props option syntax are normalized into the
 * Object-based format.
 */
function normalizeProps(options, vm) {
  var props = options.props;
  if (!props) {
    return;
  }
  var res = {};
  var i, val, name;
  if (Array.isArray(props)) {
    i = props.length;
    while (i--) {
      val = props[i];
      if (typeof val === 'string') {
        name = camelize(val);
        res[name] = {
          type: null
        };
      } else if (true) {
        warn('props must be strings when using array syntax.');
      }
    }
  } else if (isPlainObject(props)) {
    for (var key in props) {
      val = props[key];
      name = camelize(key);
      res[name] = isPlainObject(val) ? val : {
        type: val
      };
    }
  } else if (true) {
    warn("Invalid value for option \"props\": expected an Array or an Object, " + "but got " + toRawType(props) + ".", vm);
  }
  options.props = res;
}

/**
 * Normalize all injections into Object-based format
 */
function normalizeInject(options, vm) {
  var inject = options.inject;
  if (!inject) {
    return;
  }
  var normalized = options.inject = {};
  if (Array.isArray(inject)) {
    for (var i = 0; i < inject.length; i++) {
      normalized[inject[i]] = {
        from: inject[i]
      };
    }
  } else if (isPlainObject(inject)) {
    for (var key in inject) {
      var val = inject[key];
      normalized[key] = isPlainObject(val) ? extend({
        from: key
      }, val) : {
        from: val
      };
    }
  } else if (true) {
    warn("Invalid value for option \"inject\": expected an Array or an Object, " + "but got " + toRawType(inject) + ".", vm);
  }
}

/**
 * Normalize raw function directives into object format.
 */
function normalizeDirectives(options) {
  var dirs = options.directives;
  if (dirs) {
    for (var key in dirs) {
      var def$$1 = dirs[key];
      if (typeof def$$1 === 'function') {
        dirs[key] = {
          bind: def$$1,
          update: def$$1
        };
      }
    }
  }
}
function assertObjectType(name, value, vm) {
  if (!isPlainObject(value)) {
    warn("Invalid value for option \"" + name + "\": expected an Object, " + "but got " + toRawType(value) + ".", vm);
  }
}

/**
 * Merge two option objects into a new one.
 * Core utility used in both instantiation and inheritance.
 */
function mergeOptions(parent, child, vm) {
  if (true) {
    checkComponents(child);
  }
  if (typeof child === 'function') {
    child = child.options;
  }
  normalizeProps(child, vm);
  normalizeInject(child, vm);
  normalizeDirectives(child);

  // Apply extends and mixins on the child options,
  // but only if it is a raw options object that isn't
  // the result of another mergeOptions call.
  // Only merged options has the _base property.
  if (!child._base) {
    if (child.extends) {
      parent = mergeOptions(parent, child.extends, vm);
    }
    if (child.mixins) {
      for (var i = 0, l = child.mixins.length; i < l; i++) {
        parent = mergeOptions(parent, child.mixins[i], vm);
      }
    }
  }
  var options = {};
  var key;
  for (key in parent) {
    mergeField(key);
  }
  for (key in child) {
    if (!hasOwn(parent, key)) {
      mergeField(key);
    }
  }
  function mergeField(key) {
    var strat = strats[key] || defaultStrat;
    options[key] = strat(parent[key], child[key], vm, key);
  }
  return options;
}

/**
 * Resolve an asset.
 * This function is used because child instances need access
 * to assets defined in its ancestor chain.
 */
function resolveAsset(options, type, id, warnMissing) {
  /* istanbul ignore if */
  if (typeof id !== 'string') {
    return;
  }
  var assets = options[type];
  // check local registration variations first
  if (hasOwn(assets, id)) {
    return assets[id];
  }
  var camelizedId = camelize(id);
  if (hasOwn(assets, camelizedId)) {
    return assets[camelizedId];
  }
  var PascalCaseId = capitalize(camelizedId);
  if (hasOwn(assets, PascalCaseId)) {
    return assets[PascalCaseId];
  }
  // fallback to prototype chain
  var res = assets[id] || assets[camelizedId] || assets[PascalCaseId];
  if ( true && warnMissing && !res) {
    warn('Failed to resolve ' + type.slice(0, -1) + ': ' + id, options);
  }
  return res;
}

/*  */

function validateProp(key, propOptions, propsData, vm) {
  var prop = propOptions[key];
  var absent = !hasOwn(propsData, key);
  var value = propsData[key];
  // boolean casting
  var booleanIndex = getTypeIndex(Boolean, prop.type);
  if (booleanIndex > -1) {
    if (absent && !hasOwn(prop, 'default')) {
      value = false;
    } else if (value === '' || value === hyphenate(key)) {
      // only cast empty string / same name to boolean if
      // boolean has higher priority
      var stringIndex = getTypeIndex(String, prop.type);
      if (stringIndex < 0 || booleanIndex < stringIndex) {
        value = true;
      }
    }
  }
  // check default value
  if (value === undefined) {
    value = getPropDefaultValue(vm, prop, key);
    // since the default value is a fresh copy,
    // make sure to observe it.
    var prevShouldObserve = shouldObserve;
    toggleObserving(true);
    observe(value);
    toggleObserving(prevShouldObserve);
  }
  if (true) {
    assertProp(prop, key, value, vm, absent);
  }
  return value;
}

/**
 * Get the default value of a prop.
 */
function getPropDefaultValue(vm, prop, key) {
  // no default, return undefined
  if (!hasOwn(prop, 'default')) {
    return undefined;
  }
  var def = prop.default;
  // warn against non-factory defaults for Object & Array
  if ( true && isObject(def)) {
    warn('Invalid default value for prop "' + key + '": ' + 'Props with type Object/Array must use a factory function ' + 'to return the default value.', vm);
  }
  // the raw prop value was also undefined from previous render,
  // return previous default value to avoid unnecessary watcher trigger
  if (vm && vm.$options.propsData && vm.$options.propsData[key] === undefined && vm._props[key] !== undefined) {
    return vm._props[key];
  }
  // call factory function for non-Function types
  // a value is Function if its prototype is function even across different execution context
  return typeof def === 'function' && getType(prop.type) !== 'Function' ? def.call(vm) : def;
}

/**
 * Assert whether a prop is valid.
 */
function assertProp(prop, name, value, vm, absent) {
  if (prop.required && absent) {
    warn('Missing required prop: "' + name + '"', vm);
    return;
  }
  if (value == null && !prop.required) {
    return;
  }
  var type = prop.type;
  var valid = !type || type === true;
  var expectedTypes = [];
  if (type) {
    if (!Array.isArray(type)) {
      type = [type];
    }
    for (var i = 0; i < type.length && !valid; i++) {
      var assertedType = assertType(value, type[i]);
      expectedTypes.push(assertedType.expectedType || '');
      valid = assertedType.valid;
    }
  }
  if (!valid) {
    warn(getInvalidTypeMessage(name, value, expectedTypes), vm);
    return;
  }
  var validator = prop.validator;
  if (validator) {
    if (!validator(value)) {
      warn('Invalid prop: custom validator check failed for prop "' + name + '".', vm);
    }
  }
}
var simpleCheckRE = /^(String|Number|Boolean|Function|Symbol)$/;
function assertType(value, type) {
  var valid;
  var expectedType = getType(type);
  if (simpleCheckRE.test(expectedType)) {
    var t = typeof value;
    valid = t === expectedType.toLowerCase();
    // for primitive wrapper objects
    if (!valid && t === 'object') {
      valid = value instanceof type;
    }
  } else if (expectedType === 'Object') {
    valid = isPlainObject(value);
  } else if (expectedType === 'Array') {
    valid = Array.isArray(value);
  } else {
    valid = value instanceof type;
  }
  return {
    valid: valid,
    expectedType: expectedType
  };
}

/**
 * Use function string name to check built-in types,
 * because a simple equality check will fail when running
 * across different vms / iframes.
 */
function getType(fn) {
  var match = fn && fn.toString().match(/^\s*function (\w+)/);
  return match ? match[1] : '';
}
function isSameType(a, b) {
  return getType(a) === getType(b);
}
function getTypeIndex(type, expectedTypes) {
  if (!Array.isArray(expectedTypes)) {
    return isSameType(expectedTypes, type) ? 0 : -1;
  }
  for (var i = 0, len = expectedTypes.length; i < len; i++) {
    if (isSameType(expectedTypes[i], type)) {
      return i;
    }
  }
  return -1;
}
function getInvalidTypeMessage(name, value, expectedTypes) {
  var message = "Invalid prop: type check failed for prop \"" + name + "\"." + " Expected " + expectedTypes.map(capitalize).join(', ');
  var expectedType = expectedTypes[0];
  var receivedType = toRawType(value);
  var expectedValue = styleValue(value, expectedType);
  var receivedValue = styleValue(value, receivedType);
  // check if we need to specify expected value
  if (expectedTypes.length === 1 && isExplicable(expectedType) && !isBoolean(expectedType, receivedType)) {
    message += " with value " + expectedValue;
  }
  message += ", got " + receivedType + " ";
  // check if we need to specify received value
  if (isExplicable(receivedType)) {
    message += "with value " + receivedValue + ".";
  }
  return message;
}
function styleValue(value, type) {
  if (type === 'String') {
    return "\"" + value + "\"";
  } else if (type === 'Number') {
    return "" + Number(value);
  } else {
    return "" + value;
  }
}
function isExplicable(value) {
  var explicitTypes = ['string', 'number', 'boolean'];
  return explicitTypes.some(function (elem) {
    return value.toLowerCase() === elem;
  });
}
function isBoolean() {
  var args = [],
    len = arguments.length;
  while (len--) args[len] = arguments[len];
  return args.some(function (elem) {
    return elem.toLowerCase() === 'boolean';
  });
}

/*  */

function handleError(err, vm, info) {
  // Deactivate deps tracking while processing error handler to avoid possible infinite rendering.
  // See: https://github.com/vuejs/vuex/issues/1505
  pushTarget();
  try {
    if (vm) {
      var cur = vm;
      while (cur = cur.$parent) {
        var hooks = cur.$options.errorCaptured;
        if (hooks) {
          for (var i = 0; i < hooks.length; i++) {
            try {
              var capture = hooks[i].call(cur, err, vm, info) === false;
              if (capture) {
                return;
              }
            } catch (e) {
              globalHandleError(e, cur, 'errorCaptured hook');
            }
          }
        }
      }
    }
    globalHandleError(err, vm, info);
  } finally {
    popTarget();
  }
}
function invokeWithErrorHandling(handler, context, args, vm, info) {
  var res;
  try {
    res = args ? handler.apply(context, args) : handler.call(context);
    if (res && !res._isVue && isPromise(res) && !res._handled) {
      res.catch(function (e) {
        return handleError(e, vm, info + " (Promise/async)");
      });
      // issue #9511
      // avoid catch triggering multiple times when nested calls
      res._handled = true;
    }
  } catch (e) {
    handleError(e, vm, info);
  }
  return res;
}
function globalHandleError(err, vm, info) {
  if (config.errorHandler) {
    try {
      return config.errorHandler.call(null, err, vm, info);
    } catch (e) {
      // if the user intentionally throws the original error in the handler,
      // do not log it twice
      if (e !== err) {
        logError(e, null, 'config.errorHandler');
      }
    }
  }
  logError(err, vm, info);
}
function logError(err, vm, info) {
  if (true) {
    warn("Error in " + info + ": \"" + err.toString() + "\"", vm);
  }
  /* istanbul ignore else */
  if ((inBrowser || inWeex) && typeof console !== 'undefined') {
    console.error(err);
  } else {
    throw err;
  }
}

/*  */

var callbacks = [];
var pending = false;
function flushCallbacks() {
  pending = false;
  var copies = callbacks.slice(0);
  callbacks.length = 0;
  for (var i = 0; i < copies.length; i++) {
    copies[i]();
  }
}

// Here we have async deferring wrappers using microtasks.
// In 2.5 we used (macro) tasks (in combination with microtasks).
// However, it has subtle problems when state is changed right before repaint
// (e.g. #6813, out-in transitions).
// Also, using (macro) tasks in event handler would cause some weird behaviors
// that cannot be circumvented (e.g. #7109, #7153, #7546, #7834, #8109).
// So we now use microtasks everywhere, again.
// A major drawback of this tradeoff is that there are some scenarios
// where microtasks have too high a priority and fire in between supposedly
// sequential events (e.g. #4521, #6690, which have workarounds)
// or even between bubbling of the same event (#6566).
var timerFunc;

// The nextTick behavior leverages the microtask queue, which can be accessed
// via either native Promise.then or MutationObserver.
// MutationObserver has wider support, however it is seriously bugged in
// UIWebView in iOS >= 9.3.3 when triggered in touch event handlers. It
// completely stops working after triggering a few times... so, if native
// Promise is available, we will use it:
/* istanbul ignore next, $flow-disable-line */
if (typeof Promise !== 'undefined' && isNative(Promise)) {
  var p = Promise.resolve();
  timerFunc = function () {
    p.then(flushCallbacks);
    // In problematic UIWebViews, Promise.then doesn't completely break, but
    // it can get stuck in a weird state where callbacks are pushed into the
    // microtask queue but the queue isn't being flushed, until the browser
    // needs to do some other work, e.g. handle a timer. Therefore we can
    // "force" the microtask queue to be flushed by adding an empty timer.
    if (isIOS) {
      setTimeout(noop);
    }
  };
} else if (!isIE && typeof MutationObserver !== 'undefined' && (isNative(MutationObserver) ||
// PhantomJS and iOS 7.x
MutationObserver.toString() === '[object MutationObserverConstructor]')) {
  // Use MutationObserver where native Promise is not available,
  // e.g. PhantomJS, iOS7, Android 4.4
  // (#6466 MutationObserver is unreliable in IE11)
  var counter = 1;
  var observer = new MutationObserver(flushCallbacks);
  var textNode = document.createTextNode(String(counter));
  observer.observe(textNode, {
    characterData: true
  });
  timerFunc = function () {
    counter = (counter + 1) % 2;
    textNode.data = String(counter);
  };
} else if (typeof setImmediate !== 'undefined' && isNative(setImmediate)) {
  // Fallback to setImmediate.
  // Technically it leverages the (macro) task queue,
  // but it is still a better choice than setTimeout.
  timerFunc = function () {
    setImmediate(flushCallbacks);
  };
} else {
  // Fallback to setTimeout.
  timerFunc = function () {
    setTimeout(flushCallbacks, 0);
  };
}
function nextTick(cb, ctx) {
  var _resolve;
  callbacks.push(function () {
    if (cb) {
      try {
        cb.call(ctx);
      } catch (e) {
        handleError(e, ctx, 'nextTick');
      }
    } else if (_resolve) {
      _resolve(ctx);
    }
  });
  if (!pending) {
    pending = true;
    timerFunc();
  }
  // $flow-disable-line
  if (!cb && typeof Promise !== 'undefined') {
    return new Promise(function (resolve) {
      _resolve = resolve;
    });
  }
}

/*  */

/* not type checking this file because flow doesn't play well with Proxy */

var initProxy;
if (true) {
  var allowedGlobals = makeMap('Infinity,undefined,NaN,isFinite,isNaN,' + 'parseFloat,parseInt,decodeURI,decodeURIComponent,encodeURI,encodeURIComponent,' + 'Math,Number,Date,Array,Object,Boolean,String,RegExp,Map,Set,JSON,Intl,' + 'require' // for Webpack/Browserify
  );
  var warnNonPresent = function (target, key) {
    warn("Property or method \"" + key + "\" is not defined on the instance but " + 'referenced during render. Make sure that this property is reactive, ' + 'either in the data option, or for class-based components, by ' + 'initializing the property. ' + 'See: https://vuejs.org/v2/guide/reactivity.html#Declaring-Reactive-Properties.', target);
  };
  var warnReservedPrefix = function (target, key) {
    warn("Property \"" + key + "\" must be accessed with \"$data." + key + "\" because " + 'properties starting with "$" or "_" are not proxied in the Vue instance to ' + 'prevent conflicts with Vue internals. ' + 'See: https://vuejs.org/v2/api/#data', target);
  };
  var hasProxy = typeof Proxy !== 'undefined' && isNative(Proxy);
  if (hasProxy) {
    var isBuiltInModifier = makeMap('stop,prevent,self,ctrl,shift,alt,meta,exact');
    config.keyCodes = new Proxy(config.keyCodes, {
      set: function set(target, key, value) {
        if (isBuiltInModifier(key)) {
          warn("Avoid overwriting built-in modifier in config.keyCodes: ." + key);
          return false;
        } else {
          target[key] = value;
          return true;
        }
      }
    });
  }
  var hasHandler = {
    has: function has(target, key) {
      var has = key in target;
      var isAllowed = allowedGlobals(key) || typeof key === 'string' && key.charAt(0) === '_' && !(key in target.$data);
      if (!has && !isAllowed) {
        if (key in target.$data) {
          warnReservedPrefix(target, key);
        } else {
          warnNonPresent(target, key);
        }
      }
      return has || !isAllowed;
    }
  };
  var getHandler = {
    get: function get(target, key) {
      if (typeof key === 'string' && !(key in target)) {
        if (key in target.$data) {
          warnReservedPrefix(target, key);
        } else {
          warnNonPresent(target, key);
        }
      }
      return target[key];
    }
  };
  initProxy = function initProxy(vm) {
    if (hasProxy) {
      // determine which proxy handler to use
      var options = vm.$options;
      var handlers = options.render && options.render._withStripped ? getHandler : hasHandler;
      vm._renderProxy = new Proxy(vm, handlers);
    } else {
      vm._renderProxy = vm;
    }
  };
}

/*  */

var seenObjects = new _Set();

/**
 * Recursively traverse an object to evoke all converted
 * getters, so that every nested property inside the object
 * is collected as a "deep" dependency.
 */
function traverse(val) {
  _traverse(val, seenObjects);
  seenObjects.clear();
}
function _traverse(val, seen) {
  var i, keys;
  var isA = Array.isArray(val);
  if (!isA && !isObject(val) || Object.isFrozen(val) || val instanceof VNode) {
    return;
  }
  if (val.__ob__) {
    var depId = val.__ob__.dep.id;
    if (seen.has(depId)) {
      return;
    }
    seen.add(depId);
  }
  if (isA) {
    i = val.length;
    while (i--) {
      _traverse(val[i], seen);
    }
  } else {
    keys = Object.keys(val);
    i = keys.length;
    while (i--) {
      _traverse(val[keys[i]], seen);
    }
  }
}
var mark;
var measure;
if (true) {
  var perf = inBrowser && window.performance;
  /* istanbul ignore if */
  if (perf && perf.mark && perf.measure && perf.clearMarks && perf.clearMeasures) {
    mark = function (tag) {
      return perf.mark(tag);
    };
    measure = function (name, startTag, endTag) {
      perf.measure(name, startTag, endTag);
      perf.clearMarks(startTag);
      perf.clearMarks(endTag);
      // perf.clearMeasures(name)
    };
  }
}

/*  */

var normalizeEvent = cached(function (name) {
  var passive = name.charAt(0) === '&';
  name = passive ? name.slice(1) : name;
  var once$$1 = name.charAt(0) === '~'; // Prefixed last, checked first
  name = once$$1 ? name.slice(1) : name;
  var capture = name.charAt(0) === '!';
  name = capture ? name.slice(1) : name;
  return {
    name: name,
    once: once$$1,
    capture: capture,
    passive: passive
  };
});
function createFnInvoker(fns, vm) {
  function invoker() {
    var arguments$1 = arguments;
    var fns = invoker.fns;
    if (Array.isArray(fns)) {
      var cloned = fns.slice();
      for (var i = 0; i < cloned.length; i++) {
        invokeWithErrorHandling(cloned[i], null, arguments$1, vm, "v-on handler");
      }
    } else {
      // return handler return value for single handlers
      return invokeWithErrorHandling(fns, null, arguments, vm, "v-on handler");
    }
  }
  invoker.fns = fns;
  return invoker;
}
function updateListeners(on, oldOn, add, remove$$1, createOnceHandler, vm) {
  var name, def$$1, cur, old, event;
  for (name in on) {
    def$$1 = cur = on[name];
    old = oldOn[name];
    event = normalizeEvent(name);
    if (isUndef(cur)) {
       true && warn("Invalid handler for event \"" + event.name + "\": got " + String(cur), vm);
    } else if (isUndef(old)) {
      if (isUndef(cur.fns)) {
        cur = on[name] = createFnInvoker(cur, vm);
      }
      if (isTrue(event.once)) {
        cur = on[name] = createOnceHandler(event.name, cur, event.capture);
      }
      add(event.name, cur, event.capture, event.passive, event.params);
    } else if (cur !== old) {
      old.fns = cur;
      on[name] = old;
    }
  }
  for (name in oldOn) {
    if (isUndef(on[name])) {
      event = normalizeEvent(name);
      remove$$1(event.name, oldOn[name], event.capture);
    }
  }
}

/*  */

/*  */

// fixed by xxxxxx (mp properties)
function extractPropertiesFromVNodeData(data, Ctor, res, context) {
  var propOptions = Ctor.options.mpOptions && Ctor.options.mpOptions.properties;
  if (isUndef(propOptions)) {
    return res;
  }
  var externalClasses = Ctor.options.mpOptions.externalClasses || [];
  var attrs = data.attrs;
  var props = data.props;
  if (isDef(attrs) || isDef(props)) {
    for (var key in propOptions) {
      var altKey = hyphenate(key);
      var result = checkProp(res, props, key, altKey, true) || checkProp(res, attrs, key, altKey, false);
      // externalClass
      if (result && res[key] && externalClasses.indexOf(altKey) !== -1 && context[camelize(res[key])]) {
        // 赋值 externalClass 真正的值(模板里 externalClass 的值可能是字符串)
        res[key] = context[camelize(res[key])];
      }
    }
  }
  return res;
}
function extractPropsFromVNodeData(data, Ctor, tag, context // fixed by xxxxxx
) {
  // we are only extracting raw values here.
  // validation and default values are handled in the child
  // component itself.
  var propOptions = Ctor.options.props;
  if (isUndef(propOptions)) {
    // fixed by xxxxxx
    return extractPropertiesFromVNodeData(data, Ctor, {}, context);
  }
  var res = {};
  var attrs = data.attrs;
  var props = data.props;
  if (isDef(attrs) || isDef(props)) {
    for (var key in propOptions) {
      var altKey = hyphenate(key);
      if (true) {
        var keyInLowerCase = key.toLowerCase();
        if (key !== keyInLowerCase && attrs && hasOwn(attrs, keyInLowerCase)) {
          tip("Prop \"" + keyInLowerCase + "\" is passed to component " + formatComponentName(tag || Ctor) + ", but the declared prop name is" + " \"" + key + "\". " + "Note that HTML attributes are case-insensitive and camelCased " + "props need to use their kebab-case equivalents when using in-DOM " + "templates. You should probably use \"" + altKey + "\" instead of \"" + key + "\".");
        }
      }
      checkProp(res, props, key, altKey, true) || checkProp(res, attrs, key, altKey, false);
    }
  }
  // fixed by xxxxxx
  return extractPropertiesFromVNodeData(data, Ctor, res, context);
}
function checkProp(res, hash, key, altKey, preserve) {
  if (isDef(hash)) {
    if (hasOwn(hash, key)) {
      res[key] = hash[key];
      if (!preserve) {
        delete hash[key];
      }
      return true;
    } else if (hasOwn(hash, altKey)) {
      res[key] = hash[altKey];
      if (!preserve) {
        delete hash[altKey];
      }
      return true;
    }
  }
  return false;
}

/*  */

// The template compiler attempts to minimize the need for normalization by
// statically analyzing the template at compile time.
//
// For plain HTML markup, normalization can be completely skipped because the
// generated render function is guaranteed to return Array<VNode>. There are
// two cases where extra normalization is needed:

// 1. When the children contains components - because a functional component
// may return an Array instead of a single root. In this case, just a simple
// normalization is needed - if any child is an Array, we flatten the whole
// thing with Array.prototype.concat. It is guaranteed to be only 1-level deep
// because functional components already normalize their own children.
function simpleNormalizeChildren(children) {
  for (var i = 0; i < children.length; i++) {
    if (Array.isArray(children[i])) {
      return Array.prototype.concat.apply([], children);
    }
  }
  return children;
}

// 2. When the children contains constructs that always generated nested Arrays,
// e.g. <template>, <slot>, v-for, or when the children is provided by user
// with hand-written render functions / JSX. In such cases a full normalization
// is needed to cater to all possible types of children values.
function normalizeChildren(children) {
  return isPrimitive(children) ? [createTextVNode(children)] : Array.isArray(children) ? normalizeArrayChildren(children) : undefined;
}
function isTextNode(node) {
  return isDef(node) && isDef(node.text) && isFalse(node.isComment);
}
function normalizeArrayChildren(children, nestedIndex) {
  var res = [];
  var i, c, lastIndex, last;
  for (i = 0; i < children.length; i++) {
    c = children[i];
    if (isUndef(c) || typeof c === 'boolean') {
      continue;
    }
    lastIndex = res.length - 1;
    last = res[lastIndex];
    //  nested
    if (Array.isArray(c)) {
      if (c.length > 0) {
        c = normalizeArrayChildren(c, (nestedIndex || '') + "_" + i);
        // merge adjacent text nodes
        if (isTextNode(c[0]) && isTextNode(last)) {
          res[lastIndex] = createTextVNode(last.text + c[0].text);
          c.shift();
        }
        res.push.apply(res, c);
      }
    } else if (isPrimitive(c)) {
      if (isTextNode(last)) {
        // merge adjacent text nodes
        // this is necessary for SSR hydration because text nodes are
        // essentially merged when rendered to HTML strings
        res[lastIndex] = createTextVNode(last.text + c);
      } else if (c !== '') {
        // convert primitive to vnode
        res.push(createTextVNode(c));
      }
    } else {
      if (isTextNode(c) && isTextNode(last)) {
        // merge adjacent text nodes
        res[lastIndex] = createTextVNode(last.text + c.text);
      } else {
        // default key for nested array children (likely generated by v-for)
        if (isTrue(children._isVList) && isDef(c.tag) && isUndef(c.key) && isDef(nestedIndex)) {
          c.key = "__vlist" + nestedIndex + "_" + i + "__";
        }
        res.push(c);
      }
    }
  }
  return res;
}

/*  */

function initProvide(vm) {
  var provide = vm.$options.provide;
  if (provide) {
    vm._provided = typeof provide === 'function' ? provide.call(vm) : provide;
  }
}
function initInjections(vm) {
  var result = resolveInject(vm.$options.inject, vm);
  if (result) {
    toggleObserving(false);
    Object.keys(result).forEach(function (key) {
      /* istanbul ignore else */
      if (true) {
        defineReactive$$1(vm, key, result[key], function () {
          warn("Avoid mutating an injected value directly since the changes will be " + "overwritten whenever the provided component re-renders. " + "injection being mutated: \"" + key + "\"", vm);
        });
      } else {}
    });
    toggleObserving(true);
  }
}
function resolveInject(inject, vm) {
  if (inject) {
    // inject is :any because flow is not smart enough to figure out cached
    var result = Object.create(null);
    var keys = hasSymbol ? Reflect.ownKeys(inject) : Object.keys(inject);
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      // #6574 in case the inject object is observed...
      if (key === '__ob__') {
        continue;
      }
      var provideKey = inject[key].from;
      var source = vm;
      while (source) {
        if (source._provided && hasOwn(source._provided, provideKey)) {
          result[key] = source._provided[provideKey];
          break;
        }
        source = source.$parent;
      }
      if (!source) {
        if ('default' in inject[key]) {
          var provideDefault = inject[key].default;
          result[key] = typeof provideDefault === 'function' ? provideDefault.call(vm) : provideDefault;
        } else if (true) {
          warn("Injection \"" + key + "\" not found", vm);
        }
      }
    }
    return result;
  }
}

/*  */

/**
 * Runtime helper for resolving raw children VNodes into a slot object.
 */
function resolveSlots(children, context) {
  if (!children || !children.length) {
    return {};
  }
  var slots = {};
  for (var i = 0, l = children.length; i < l; i++) {
    var child = children[i];
    var data = child.data;
    // remove slot attribute if the node is resolved as a Vue slot node
    if (data && data.attrs && data.attrs.slot) {
      delete data.attrs.slot;
    }
    // named slots should only be respected if the vnode was rendered in the
    // same context.
    if ((child.context === context || child.fnContext === context) && data && data.slot != null) {
      var name = data.slot;
      var slot = slots[name] || (slots[name] = []);
      if (child.tag === 'template') {
        slot.push.apply(slot, child.children || []);
      } else {
        slot.push(child);
      }
    } else {
      // fixed by xxxxxx 临时 hack 掉 uni-app 中的异步 name slot page
      if (child.asyncMeta && child.asyncMeta.data && child.asyncMeta.data.slot === 'page') {
        (slots['page'] || (slots['page'] = [])).push(child);
      } else {
        (slots.default || (slots.default = [])).push(child);
      }
    }
  }
  // ignore slots that contains only whitespace
  for (var name$1 in slots) {
    if (slots[name$1].every(isWhitespace)) {
      delete slots[name$1];
    }
  }
  return slots;
}
function isWhitespace(node) {
  return node.isComment && !node.asyncFactory || node.text === ' ';
}

/*  */

function normalizeScopedSlots(slots, normalSlots, prevSlots) {
  var res;
  var hasNormalSlots = Object.keys(normalSlots).length > 0;
  var isStable = slots ? !!slots.$stable : !hasNormalSlots;
  var key = slots && slots.$key;
  if (!slots) {
    res = {};
  } else if (slots._normalized) {
    // fast path 1: child component re-render only, parent did not change
    return slots._normalized;
  } else if (isStable && prevSlots && prevSlots !== emptyObject && key === prevSlots.$key && !hasNormalSlots && !prevSlots.$hasNormal) {
    // fast path 2: stable scoped slots w/ no normal slots to proxy,
    // only need to normalize once
    return prevSlots;
  } else {
    res = {};
    for (var key$1 in slots) {
      if (slots[key$1] && key$1[0] !== '$') {
        res[key$1] = normalizeScopedSlot(normalSlots, key$1, slots[key$1]);
      }
    }
  }
  // expose normal slots on scopedSlots
  for (var key$2 in normalSlots) {
    if (!(key$2 in res)) {
      res[key$2] = proxyNormalSlot(normalSlots, key$2);
    }
  }
  // avoriaz seems to mock a non-extensible $scopedSlots object
  // and when that is passed down this would cause an error
  if (slots && Object.isExtensible(slots)) {
    slots._normalized = res;
  }
  def(res, '$stable', isStable);
  def(res, '$key', key);
  def(res, '$hasNormal', hasNormalSlots);
  return res;
}
function normalizeScopedSlot(normalSlots, key, fn) {
  var normalized = function () {
    var res = arguments.length ? fn.apply(null, arguments) : fn({});
    res = res && typeof res === 'object' && !Array.isArray(res) ? [res] // single vnode
    : normalizeChildren(res);
    return res && (res.length === 0 || res.length === 1 && res[0].isComment // #9658
    ) ? undefined : res;
  };
  // this is a slot using the new v-slot syntax without scope. although it is
  // compiled as a scoped slot, render fn users would expect it to be present
  // on this.$slots because the usage is semantically a normal slot.
  if (fn.proxy) {
    Object.defineProperty(normalSlots, key, {
      get: normalized,
      enumerable: true,
      configurable: true
    });
  }
  return normalized;
}
function proxyNormalSlot(slots, key) {
  return function () {
    return slots[key];
  };
}

/*  */

/**
 * Runtime helper for rendering v-for lists.
 */
function renderList(val, render) {
  var ret, i, l, keys, key;
  if (Array.isArray(val) || typeof val === 'string') {
    ret = new Array(val.length);
    for (i = 0, l = val.length; i < l; i++) {
      ret[i] = render(val[i], i, i, i); // fixed by xxxxxx
    }
  } else if (typeof val === 'number') {
    ret = new Array(val);
    for (i = 0; i < val; i++) {
      ret[i] = render(i + 1, i, i, i); // fixed by xxxxxx
    }
  } else if (isObject(val)) {
    if (hasSymbol && val[Symbol.iterator]) {
      ret = [];
      var iterator = val[Symbol.iterator]();
      var result = iterator.next();
      while (!result.done) {
        ret.push(render(result.value, ret.length, i, i++)); // fixed by xxxxxx
        result = iterator.next();
      }
    } else {
      keys = Object.keys(val);
      ret = new Array(keys.length);
      for (i = 0, l = keys.length; i < l; i++) {
        key = keys[i];
        ret[i] = render(val[key], key, i, i); // fixed by xxxxxx
      }
    }
  }
  if (!isDef(ret)) {
    ret = [];
  }
  ret._isVList = true;
  return ret;
}

/*  */

/**
 * Runtime helper for rendering <slot>
 */
function renderSlot(name, fallback, props, bindObject, slotVm) {
  var scopedSlotFn = this.$scopedSlots[name];
  var nodes;
  if (scopedSlotFn) {
    // scoped slot
    props = props || {};
    if (bindObject) {
      if ( true && !isObject(bindObject)) {
        warn('slot v-bind without argument expects an Object', this);
      }
      props = extend(extend({}, bindObject), props);
    }
    // fixed by xxxxxx app-plus scopedSlot
    nodes = scopedSlotFn(props, slotVm || this, props._i) || fallback;
  } else {
    nodes = this.$slots[name] || fallback;
  }
  var target = props && props.slot;
  if (target) {
    return this.$createElement('template', {
      slot: target
    }, nodes);
  } else {
    return nodes;
  }
}

/*  */

/**
 * Runtime helper for resolving filters
 */
function resolveFilter(id) {
  return resolveAsset(this.$options, 'filters', id, true) || identity;
}

/*  */

function isKeyNotMatch(expect, actual) {
  if (Array.isArray(expect)) {
    return expect.indexOf(actual) === -1;
  } else {
    return expect !== actual;
  }
}

/**
 * Runtime helper for checking keyCodes from config.
 * exposed as Vue.prototype._k
 * passing in eventKeyName as last argument separately for backwards compat
 */
function checkKeyCodes(eventKeyCode, key, builtInKeyCode, eventKeyName, builtInKeyName) {
  var mappedKeyCode = config.keyCodes[key] || builtInKeyCode;
  if (builtInKeyName && eventKeyName && !config.keyCodes[key]) {
    return isKeyNotMatch(builtInKeyName, eventKeyName);
  } else if (mappedKeyCode) {
    return isKeyNotMatch(mappedKeyCode, eventKeyCode);
  } else if (eventKeyName) {
    return hyphenate(eventKeyName) !== key;
  }
}

/*  */

/**
 * Runtime helper for merging v-bind="object" into a VNode's data.
 */
function bindObjectProps(data, tag, value, asProp, isSync) {
  if (value) {
    if (!isObject(value)) {
       true && warn('v-bind without argument expects an Object or Array value', this);
    } else {
      if (Array.isArray(value)) {
        value = toObject(value);
      }
      var hash;
      var loop = function (key) {
        if (key === 'class' || key === 'style' || isReservedAttribute(key)) {
          hash = data;
        } else {
          var type = data.attrs && data.attrs.type;
          hash = asProp || config.mustUseProp(tag, type, key) ? data.domProps || (data.domProps = {}) : data.attrs || (data.attrs = {});
        }
        var camelizedKey = camelize(key);
        var hyphenatedKey = hyphenate(key);
        if (!(camelizedKey in hash) && !(hyphenatedKey in hash)) {
          hash[key] = value[key];
          if (isSync) {
            var on = data.on || (data.on = {});
            on["update:" + key] = function ($event) {
              value[key] = $event;
            };
          }
        }
      };
      for (var key in value) loop(key);
    }
  }
  return data;
}

/*  */

/**
 * Runtime helper for rendering static trees.
 */
function renderStatic(index, isInFor) {
  var cached = this._staticTrees || (this._staticTrees = []);
  var tree = cached[index];
  // if has already-rendered static tree and not inside v-for,
  // we can reuse the same tree.
  if (tree && !isInFor) {
    return tree;
  }
  // otherwise, render a fresh tree.
  tree = cached[index] = this.$options.staticRenderFns[index].call(this._renderProxy, null, this // for render fns generated for functional component templates
  );
  markStatic(tree, "__static__" + index, false);
  return tree;
}

/**
 * Runtime helper for v-once.
 * Effectively it means marking the node as static with a unique key.
 */
function markOnce(tree, index, key) {
  markStatic(tree, "__once__" + index + (key ? "_" + key : ""), true);
  return tree;
}
function markStatic(tree, key, isOnce) {
  if (Array.isArray(tree)) {
    for (var i = 0; i < tree.length; i++) {
      if (tree[i] && typeof tree[i] !== 'string') {
        markStaticNode(tree[i], key + "_" + i, isOnce);
      }
    }
  } else {
    markStaticNode(tree, key, isOnce);
  }
}
function markStaticNode(node, key, isOnce) {
  node.isStatic = true;
  node.key = key;
  node.isOnce = isOnce;
}

/*  */

function bindObjectListeners(data, value) {
  if (value) {
    if (!isPlainObject(value)) {
       true && warn('v-on without argument expects an Object value', this);
    } else {
      var on = data.on = data.on ? extend({}, data.on) : {};
      for (var key in value) {
        var existing = on[key];
        var ours = value[key];
        on[key] = existing ? [].concat(existing, ours) : ours;
      }
    }
  }
  return data;
}

/*  */

function resolveScopedSlots(fns,
// see flow/vnode
res,
// the following are added in 2.6
hasDynamicKeys, contentHashKey) {
  res = res || {
    $stable: !hasDynamicKeys
  };
  for (var i = 0; i < fns.length; i++) {
    var slot = fns[i];
    if (Array.isArray(slot)) {
      resolveScopedSlots(slot, res, hasDynamicKeys);
    } else if (slot) {
      // marker for reverse proxying v-slot without scope on this.$slots
      if (slot.proxy) {
        slot.fn.proxy = true;
      }
      res[slot.key] = slot.fn;
    }
  }
  if (contentHashKey) {
    res.$key = contentHashKey;
  }
  return res;
}

/*  */

function bindDynamicKeys(baseObj, values) {
  for (var i = 0; i < values.length; i += 2) {
    var key = values[i];
    if (typeof key === 'string' && key) {
      baseObj[values[i]] = values[i + 1];
    } else if ( true && key !== '' && key !== null) {
      // null is a special value for explicitly removing a binding
      warn("Invalid value for dynamic directive argument (expected string or null): " + key, this);
    }
  }
  return baseObj;
}

// helper to dynamically append modifier runtime markers to event names.
// ensure only append when value is already string, otherwise it will be cast
// to string and cause the type check to miss.
function prependModifier(value, symbol) {
  return typeof value === 'string' ? symbol + value : value;
}

/*  */

function installRenderHelpers(target) {
  target._o = markOnce;
  target._n = toNumber;
  target._s = toString;
  target._l = renderList;
  target._t = renderSlot;
  target._q = looseEqual;
  target._i = looseIndexOf;
  target._m = renderStatic;
  target._f = resolveFilter;
  target._k = checkKeyCodes;
  target._b = bindObjectProps;
  target._v = createTextVNode;
  target._e = createEmptyVNode;
  target._u = resolveScopedSlots;
  target._g = bindObjectListeners;
  target._d = bindDynamicKeys;
  target._p = prependModifier;
}

/*  */

function FunctionalRenderContext(data, props, children, parent, Ctor) {
  var this$1 = this;
  var options = Ctor.options;
  // ensure the createElement function in functional components
  // gets a unique context - this is necessary for correct named slot check
  var contextVm;
  if (hasOwn(parent, '_uid')) {
    contextVm = Object.create(parent);
    // $flow-disable-line
    contextVm._original = parent;
  } else {
    // the context vm passed in is a functional context as well.
    // in this case we want to make sure we are able to get a hold to the
    // real context instance.
    contextVm = parent;
    // $flow-disable-line
    parent = parent._original;
  }
  var isCompiled = isTrue(options._compiled);
  var needNormalization = !isCompiled;
  this.data = data;
  this.props = props;
  this.children = children;
  this.parent = parent;
  this.listeners = data.on || emptyObject;
  this.injections = resolveInject(options.inject, parent);
  this.slots = function () {
    if (!this$1.$slots) {
      normalizeScopedSlots(data.scopedSlots, this$1.$slots = resolveSlots(children, parent));
    }
    return this$1.$slots;
  };
  Object.defineProperty(this, 'scopedSlots', {
    enumerable: true,
    get: function get() {
      return normalizeScopedSlots(data.scopedSlots, this.slots());
    }
  });

  // support for compiled functional template
  if (isCompiled) {
    // exposing $options for renderStatic()
    this.$options = options;
    // pre-resolve slots for renderSlot()
    this.$slots = this.slots();
    this.$scopedSlots = normalizeScopedSlots(data.scopedSlots, this.$slots);
  }
  if (options._scopeId) {
    this._c = function (a, b, c, d) {
      var vnode = createElement(contextVm, a, b, c, d, needNormalization);
      if (vnode && !Array.isArray(vnode)) {
        vnode.fnScopeId = options._scopeId;
        vnode.fnContext = parent;
      }
      return vnode;
    };
  } else {
    this._c = function (a, b, c, d) {
      return createElement(contextVm, a, b, c, d, needNormalization);
    };
  }
}
installRenderHelpers(FunctionalRenderContext.prototype);
function createFunctionalComponent(Ctor, propsData, data, contextVm, children) {
  var options = Ctor.options;
  var props = {};
  var propOptions = options.props;
  if (isDef(propOptions)) {
    for (var key in propOptions) {
      props[key] = validateProp(key, propOptions, propsData || emptyObject);
    }
  } else {
    if (isDef(data.attrs)) {
      mergeProps(props, data.attrs);
    }
    if (isDef(data.props)) {
      mergeProps(props, data.props);
    }
  }
  var renderContext = new FunctionalRenderContext(data, props, children, contextVm, Ctor);
  var vnode = options.render.call(null, renderContext._c, renderContext);
  if (vnode instanceof VNode) {
    return cloneAndMarkFunctionalResult(vnode, data, renderContext.parent, options, renderContext);
  } else if (Array.isArray(vnode)) {
    var vnodes = normalizeChildren(vnode) || [];
    var res = new Array(vnodes.length);
    for (var i = 0; i < vnodes.length; i++) {
      res[i] = cloneAndMarkFunctionalResult(vnodes[i], data, renderContext.parent, options, renderContext);
    }
    return res;
  }
}
function cloneAndMarkFunctionalResult(vnode, data, contextVm, options, renderContext) {
  // #7817 clone node before setting fnContext, otherwise if the node is reused
  // (e.g. it was from a cached normal slot) the fnContext causes named slots
  // that should not be matched to match.
  var clone = cloneVNode(vnode);
  clone.fnContext = contextVm;
  clone.fnOptions = options;
  if (true) {
    (clone.devtoolsMeta = clone.devtoolsMeta || {}).renderContext = renderContext;
  }
  if (data.slot) {
    (clone.data || (clone.data = {})).slot = data.slot;
  }
  return clone;
}
function mergeProps(to, from) {
  for (var key in from) {
    to[camelize(key)] = from[key];
  }
}

/*  */

/*  */

/*  */

/*  */

// inline hooks to be invoked on component VNodes during patch
var componentVNodeHooks = {
  init: function init(vnode, hydrating) {
    if (vnode.componentInstance && !vnode.componentInstance._isDestroyed && vnode.data.keepAlive) {
      // kept-alive components, treat as a patch
      var mountedNode = vnode; // work around flow
      componentVNodeHooks.prepatch(mountedNode, mountedNode);
    } else {
      var child = vnode.componentInstance = createComponentInstanceForVnode(vnode, activeInstance);
      child.$mount(hydrating ? vnode.elm : undefined, hydrating);
    }
  },
  prepatch: function prepatch(oldVnode, vnode) {
    var options = vnode.componentOptions;
    var child = vnode.componentInstance = oldVnode.componentInstance;
    updateChildComponent(child, options.propsData,
    // updated props
    options.listeners,
    // updated listeners
    vnode,
    // new parent vnode
    options.children // new children
    );
  },
  insert: function insert(vnode) {
    var context = vnode.context;
    var componentInstance = vnode.componentInstance;
    if (!componentInstance._isMounted) {
      callHook(componentInstance, 'onServiceCreated');
      callHook(componentInstance, 'onServiceAttached');
      componentInstance._isMounted = true;
      callHook(componentInstance, 'mounted');
    }
    if (vnode.data.keepAlive) {
      if (context._isMounted) {
        // vue-router#1212
        // During updates, a kept-alive component's child components may
        // change, so directly walking the tree here may call activated hooks
        // on incorrect children. Instead we push them into a queue which will
        // be processed after the whole patch process ended.
        queueActivatedComponent(componentInstance);
      } else {
        activateChildComponent(componentInstance, true /* direct */);
      }
    }
  },
  destroy: function destroy(vnode) {
    var componentInstance = vnode.componentInstance;
    if (!componentInstance._isDestroyed) {
      if (!vnode.data.keepAlive) {
        componentInstance.$destroy();
      } else {
        deactivateChildComponent(componentInstance, true /* direct */);
      }
    }
  }
};
var hooksToMerge = Object.keys(componentVNodeHooks);
function createComponent(Ctor, data, context, children, tag) {
  if (isUndef(Ctor)) {
    return;
  }
  var baseCtor = context.$options._base;

  // plain options object: turn it into a constructor
  if (isObject(Ctor)) {
    Ctor = baseCtor.extend(Ctor);
  }

  // if at this stage it's not a constructor or an async component factory,
  // reject.
  if (typeof Ctor !== 'function') {
    if (true) {
      warn("Invalid Component definition: " + String(Ctor), context);
    }
    return;
  }

  // async component
  var asyncFactory;
  if (isUndef(Ctor.cid)) {
    asyncFactory = Ctor;
    Ctor = resolveAsyncComponent(asyncFactory, baseCtor);
    if (Ctor === undefined) {
      // return a placeholder node for async component, which is rendered
      // as a comment node but preserves all the raw information for the node.
      // the information will be used for async server-rendering and hydration.
      return createAsyncPlaceholder(asyncFactory, data, context, children, tag);
    }
  }
  data = data || {};

  // resolve constructor options in case global mixins are applied after
  // component constructor creation
  resolveConstructorOptions(Ctor);

  // transform component v-model data into props & events
  if (isDef(data.model)) {
    transformModel(Ctor.options, data);
  }

  // extract props
  var propsData = extractPropsFromVNodeData(data, Ctor, tag, context); // fixed by xxxxxx

  // functional component
  if (isTrue(Ctor.options.functional)) {
    return createFunctionalComponent(Ctor, propsData, data, context, children);
  }

  // extract listeners, since these needs to be treated as
  // child component listeners instead of DOM listeners
  var listeners = data.on;
  // replace with listeners with .native modifier
  // so it gets processed during parent component patch.
  data.on = data.nativeOn;
  if (isTrue(Ctor.options.abstract)) {
    // abstract components do not keep anything
    // other than props & listeners & slot

    // work around flow
    var slot = data.slot;
    data = {};
    if (slot) {
      data.slot = slot;
    }
  }

  // install component management hooks onto the placeholder node
  installComponentHooks(data);

  // return a placeholder vnode
  var name = Ctor.options.name || tag;
  var vnode = new VNode("vue-component-" + Ctor.cid + (name ? "-" + name : ''), data, undefined, undefined, undefined, context, {
    Ctor: Ctor,
    propsData: propsData,
    listeners: listeners,
    tag: tag,
    children: children
  }, asyncFactory);
  return vnode;
}
function createComponentInstanceForVnode(vnode,
// we know it's MountedComponentVNode but flow doesn't
parent // activeInstance in lifecycle state
) {
  var options = {
    _isComponent: true,
    _parentVnode: vnode,
    parent: parent
  };
  // check inline-template render functions
  var inlineTemplate = vnode.data.inlineTemplate;
  if (isDef(inlineTemplate)) {
    options.render = inlineTemplate.render;
    options.staticRenderFns = inlineTemplate.staticRenderFns;
  }
  return new vnode.componentOptions.Ctor(options);
}
function installComponentHooks(data) {
  var hooks = data.hook || (data.hook = {});
  for (var i = 0; i < hooksToMerge.length; i++) {
    var key = hooksToMerge[i];
    var existing = hooks[key];
    var toMerge = componentVNodeHooks[key];
    if (existing !== toMerge && !(existing && existing._merged)) {
      hooks[key] = existing ? mergeHook$1(toMerge, existing) : toMerge;
    }
  }
}
function mergeHook$1(f1, f2) {
  var merged = function (a, b) {
    // flow complains about extra args which is why we use any
    f1(a, b);
    f2(a, b);
  };
  merged._merged = true;
  return merged;
}

// transform component v-model info (value and callback) into
// prop and event handler respectively.
function transformModel(options, data) {
  var prop = options.model && options.model.prop || 'value';
  var event = options.model && options.model.event || 'input';
  (data.attrs || (data.attrs = {}))[prop] = data.model.value;
  var on = data.on || (data.on = {});
  var existing = on[event];
  var callback = data.model.callback;
  if (isDef(existing)) {
    if (Array.isArray(existing) ? existing.indexOf(callback) === -1 : existing !== callback) {
      on[event] = [callback].concat(existing);
    }
  } else {
    on[event] = callback;
  }
}

/*  */

var SIMPLE_NORMALIZE = 1;
var ALWAYS_NORMALIZE = 2;

// wrapper function for providing a more flexible interface
// without getting yelled at by flow
function createElement(context, tag, data, children, normalizationType, alwaysNormalize) {
  if (Array.isArray(data) || isPrimitive(data)) {
    normalizationType = children;
    children = data;
    data = undefined;
  }
  if (isTrue(alwaysNormalize)) {
    normalizationType = ALWAYS_NORMALIZE;
  }
  return _createElement(context, tag, data, children, normalizationType);
}
function _createElement(context, tag, data, children, normalizationType) {
  if (isDef(data) && isDef(data.__ob__)) {
     true && warn("Avoid using observed data object as vnode data: " + JSON.stringify(data) + "\n" + 'Always create fresh vnode data objects in each render!', context);
    return createEmptyVNode();
  }
  // object syntax in v-bind
  if (isDef(data) && isDef(data.is)) {
    tag = data.is;
  }
  if (!tag) {
    // in case of component :is set to falsy value
    return createEmptyVNode();
  }
  // warn against non-primitive key
  if ( true && isDef(data) && isDef(data.key) && !isPrimitive(data.key)) {
    {
      warn('Avoid using non-primitive value as key, ' + 'use string/number value instead.', context);
    }
  }
  // support single function children as default scoped slot
  if (Array.isArray(children) && typeof children[0] === 'function') {
    data = data || {};
    data.scopedSlots = {
      default: children[0]
    };
    children.length = 0;
  }
  if (normalizationType === ALWAYS_NORMALIZE) {
    children = normalizeChildren(children);
  } else if (normalizationType === SIMPLE_NORMALIZE) {
    children = simpleNormalizeChildren(children);
  }
  var vnode, ns;
  if (typeof tag === 'string') {
    var Ctor;
    ns = context.$vnode && context.$vnode.ns || config.getTagNamespace(tag);
    if (config.isReservedTag(tag)) {
      // platform built-in elements
      if ( true && isDef(data) && isDef(data.nativeOn)) {
        warn("The .native modifier for v-on is only valid on components but it was used on <" + tag + ">.", context);
      }
      vnode = new VNode(config.parsePlatformTagName(tag), data, children, undefined, undefined, context);
    } else if ((!data || !data.pre) && isDef(Ctor = resolveAsset(context.$options, 'components', tag))) {
      // component
      vnode = createComponent(Ctor, data, context, children, tag);
    } else {
      // unknown or unlisted namespaced elements
      // check at runtime because it may get assigned a namespace when its
      // parent normalizes children
      vnode = new VNode(tag, data, children, undefined, undefined, context);
    }
  } else {
    // direct component options / constructor
    vnode = createComponent(tag, data, context, children);
  }
  if (Array.isArray(vnode)) {
    return vnode;
  } else if (isDef(vnode)) {
    if (isDef(ns)) {
      applyNS(vnode, ns);
    }
    if (isDef(data)) {
      registerDeepBindings(data);
    }
    return vnode;
  } else {
    return createEmptyVNode();
  }
}
function applyNS(vnode, ns, force) {
  vnode.ns = ns;
  if (vnode.tag === 'foreignObject') {
    // use default namespace inside foreignObject
    ns = undefined;
    force = true;
  }
  if (isDef(vnode.children)) {
    for (var i = 0, l = vnode.children.length; i < l; i++) {
      var child = vnode.children[i];
      if (isDef(child.tag) && (isUndef(child.ns) || isTrue(force) && child.tag !== 'svg')) {
        applyNS(child, ns, force);
      }
    }
  }
}

// ref #5318
// necessary to ensure parent re-render when deep bindings like :style and
// :class are used on slot nodes
function registerDeepBindings(data) {
  if (isObject(data.style)) {
    traverse(data.style);
  }
  if (isObject(data.class)) {
    traverse(data.class);
  }
}

/*  */

function initRender(vm) {
  vm._vnode = null; // the root of the child tree
  vm._staticTrees = null; // v-once cached trees
  var options = vm.$options;
  var parentVnode = vm.$vnode = options._parentVnode; // the placeholder node in parent tree
  var renderContext = parentVnode && parentVnode.context;
  vm.$slots = resolveSlots(options._renderChildren, renderContext);
  vm.$scopedSlots = emptyObject;
  // bind the createElement fn to this instance
  // so that we get proper render context inside it.
  // args order: tag, data, children, normalizationType, alwaysNormalize
  // internal version is used by render functions compiled from templates
  vm._c = function (a, b, c, d) {
    return createElement(vm, a, b, c, d, false);
  };
  // normalization is always applied for the public version, used in
  // user-written render functions.
  vm.$createElement = function (a, b, c, d) {
    return createElement(vm, a, b, c, d, true);
  };

  // $attrs & $listeners are exposed for easier HOC creation.
  // they need to be reactive so that HOCs using them are always updated
  var parentData = parentVnode && parentVnode.data;

  /* istanbul ignore else */
  if (true) {
    defineReactive$$1(vm, '$attrs', parentData && parentData.attrs || emptyObject, function () {
      !isUpdatingChildComponent && warn("$attrs is readonly.", vm);
    }, true);
    defineReactive$$1(vm, '$listeners', options._parentListeners || emptyObject, function () {
      !isUpdatingChildComponent && warn("$listeners is readonly.", vm);
    }, true);
  } else {}
}
var currentRenderingInstance = null;
function renderMixin(Vue) {
  // install runtime convenience helpers
  installRenderHelpers(Vue.prototype);
  Vue.prototype.$nextTick = function (fn) {
    return nextTick(fn, this);
  };
  Vue.prototype._render = function () {
    var vm = this;
    var ref = vm.$options;
    var render = ref.render;
    var _parentVnode = ref._parentVnode;
    if (_parentVnode) {
      vm.$scopedSlots = normalizeScopedSlots(_parentVnode.data.scopedSlots, vm.$slots, vm.$scopedSlots);
    }

    // set parent vnode. this allows render functions to have access
    // to the data on the placeholder node.
    vm.$vnode = _parentVnode;
    // render self
    var vnode;
    try {
      // There's no need to maintain a stack because all render fns are called
      // separately from one another. Nested component's render fns are called
      // when parent component is patched.
      currentRenderingInstance = vm;
      vnode = render.call(vm._renderProxy, vm.$createElement);
    } catch (e) {
      handleError(e, vm, "render");
      // return error render result,
      // or previous vnode to prevent render error causing blank component
      /* istanbul ignore else */
      if ( true && vm.$options.renderError) {
        try {
          vnode = vm.$options.renderError.call(vm._renderProxy, vm.$createElement, e);
        } catch (e) {
          handleError(e, vm, "renderError");
          vnode = vm._vnode;
        }
      } else {
        vnode = vm._vnode;
      }
    } finally {
      currentRenderingInstance = null;
    }
    // if the returned array contains only a single node, allow it
    if (Array.isArray(vnode) && vnode.length === 1) {
      vnode = vnode[0];
    }
    // return empty vnode in case the render function errored out
    if (!(vnode instanceof VNode)) {
      if ( true && Array.isArray(vnode)) {
        warn('Multiple root nodes returned from render function. Render function ' + 'should return a single root node.', vm);
      }
      vnode = createEmptyVNode();
    }
    // set parent
    vnode.parent = _parentVnode;
    return vnode;
  };
}

/*  */

function ensureCtor(comp, base) {
  if (comp.__esModule || hasSymbol && comp[Symbol.toStringTag] === 'Module') {
    comp = comp.default;
  }
  return isObject(comp) ? base.extend(comp) : comp;
}
function createAsyncPlaceholder(factory, data, context, children, tag) {
  var node = createEmptyVNode();
  node.asyncFactory = factory;
  node.asyncMeta = {
    data: data,
    context: context,
    children: children,
    tag: tag
  };
  return node;
}
function resolveAsyncComponent(factory, baseCtor) {
  if (isTrue(factory.error) && isDef(factory.errorComp)) {
    return factory.errorComp;
  }
  if (isDef(factory.resolved)) {
    return factory.resolved;
  }
  var owner = currentRenderingInstance;
  if (owner && isDef(factory.owners) && factory.owners.indexOf(owner) === -1) {
    // already pending
    factory.owners.push(owner);
  }
  if (isTrue(factory.loading) && isDef(factory.loadingComp)) {
    return factory.loadingComp;
  }
  if (owner && !isDef(factory.owners)) {
    var owners = factory.owners = [owner];
    var sync = true;
    var timerLoading = null;
    var timerTimeout = null;
    owner.$on('hook:destroyed', function () {
      return remove(owners, owner);
    });
    var forceRender = function (renderCompleted) {
      for (var i = 0, l = owners.length; i < l; i++) {
        owners[i].$forceUpdate();
      }
      if (renderCompleted) {
        owners.length = 0;
        if (timerLoading !== null) {
          clearTimeout(timerLoading);
          timerLoading = null;
        }
        if (timerTimeout !== null) {
          clearTimeout(timerTimeout);
          timerTimeout = null;
        }
      }
    };
    var resolve = once(function (res) {
      // cache resolved
      factory.resolved = ensureCtor(res, baseCtor);
      // invoke callbacks only if this is not a synchronous resolve
      // (async resolves are shimmed as synchronous during SSR)
      if (!sync) {
        forceRender(true);
      } else {
        owners.length = 0;
      }
    });
    var reject = once(function (reason) {
       true && warn("Failed to resolve async component: " + String(factory) + (reason ? "\nReason: " + reason : ''));
      if (isDef(factory.errorComp)) {
        factory.error = true;
        forceRender(true);
      }
    });
    var res = factory(resolve, reject);
    if (isObject(res)) {
      if (isPromise(res)) {
        // () => Promise
        if (isUndef(factory.resolved)) {
          res.then(resolve, reject);
        }
      } else if (isPromise(res.component)) {
        res.component.then(resolve, reject);
        if (isDef(res.error)) {
          factory.errorComp = ensureCtor(res.error, baseCtor);
        }
        if (isDef(res.loading)) {
          factory.loadingComp = ensureCtor(res.loading, baseCtor);
          if (res.delay === 0) {
            factory.loading = true;
          } else {
            timerLoading = setTimeout(function () {
              timerLoading = null;
              if (isUndef(factory.resolved) && isUndef(factory.error)) {
                factory.loading = true;
                forceRender(false);
              }
            }, res.delay || 200);
          }
        }
        if (isDef(res.timeout)) {
          timerTimeout = setTimeout(function () {
            timerTimeout = null;
            if (isUndef(factory.resolved)) {
              reject( true ? "timeout (" + res.timeout + "ms)" : undefined);
            }
          }, res.timeout);
        }
      }
    }
    sync = false;
    // return in case resolved synchronously
    return factory.loading ? factory.loadingComp : factory.resolved;
  }
}

/*  */

function isAsyncPlaceholder(node) {
  return node.isComment && node.asyncFactory;
}

/*  */

function getFirstComponentChild(children) {
  if (Array.isArray(children)) {
    for (var i = 0; i < children.length; i++) {
      var c = children[i];
      if (isDef(c) && (isDef(c.componentOptions) || isAsyncPlaceholder(c))) {
        return c;
      }
    }
  }
}

/*  */

/*  */

function initEvents(vm) {
  vm._events = Object.create(null);
  vm._hasHookEvent = false;
  // init parent attached events
  var listeners = vm.$options._parentListeners;
  if (listeners) {
    updateComponentListeners(vm, listeners);
  }
}
var target;
function add(event, fn) {
  target.$on(event, fn);
}
function remove$1(event, fn) {
  target.$off(event, fn);
}
function createOnceHandler(event, fn) {
  var _target = target;
  return function onceHandler() {
    var res = fn.apply(null, arguments);
    if (res !== null) {
      _target.$off(event, onceHandler);
    }
  };
}
function updateComponentListeners(vm, listeners, oldListeners) {
  target = vm;
  updateListeners(listeners, oldListeners || {}, add, remove$1, createOnceHandler, vm);
  target = undefined;
}
function eventsMixin(Vue) {
  var hookRE = /^hook:/;
  Vue.prototype.$on = function (event, fn) {
    var vm = this;
    if (Array.isArray(event)) {
      for (var i = 0, l = event.length; i < l; i++) {
        vm.$on(event[i], fn);
      }
    } else {
      (vm._events[event] || (vm._events[event] = [])).push(fn);
      // optimize hook:event cost by using a boolean flag marked at registration
      // instead of a hash lookup
      if (hookRE.test(event)) {
        vm._hasHookEvent = true;
      }
    }
    return vm;
  };
  Vue.prototype.$once = function (event, fn) {
    var vm = this;
    function on() {
      vm.$off(event, on);
      fn.apply(vm, arguments);
    }
    on.fn = fn;
    vm.$on(event, on);
    return vm;
  };
  Vue.prototype.$off = function (event, fn) {
    var vm = this;
    // all
    if (!arguments.length) {
      vm._events = Object.create(null);
      return vm;
    }
    // array of events
    if (Array.isArray(event)) {
      for (var i$1 = 0, l = event.length; i$1 < l; i$1++) {
        vm.$off(event[i$1], fn);
      }
      return vm;
    }
    // specific event
    var cbs = vm._events[event];
    if (!cbs) {
      return vm;
    }
    if (!fn) {
      vm._events[event] = null;
      return vm;
    }
    // specific handler
    var cb;
    var i = cbs.length;
    while (i--) {
      cb = cbs[i];
      if (cb === fn || cb.fn === fn) {
        cbs.splice(i, 1);
        break;
      }
    }
    return vm;
  };
  Vue.prototype.$emit = function (event) {
    var vm = this;
    if (true) {
      var lowerCaseEvent = event.toLowerCase();
      if (lowerCaseEvent !== event && vm._events[lowerCaseEvent]) {
        tip("Event \"" + lowerCaseEvent + "\" is emitted in component " + formatComponentName(vm) + " but the handler is registered for \"" + event + "\". " + "Note that HTML attributes are case-insensitive and you cannot use " + "v-on to listen to camelCase events when using in-DOM templates. " + "You should probably use \"" + hyphenate(event) + "\" instead of \"" + event + "\".");
      }
    }
    var cbs = vm._events[event];
    if (cbs) {
      cbs = cbs.length > 1 ? toArray(cbs) : cbs;
      var args = toArray(arguments, 1);
      var info = "event handler for \"" + event + "\"";
      for (var i = 0, l = cbs.length; i < l; i++) {
        invokeWithErrorHandling(cbs[i], vm, args, vm, info);
      }
    }
    return vm;
  };
}

/*  */

var activeInstance = null;
var isUpdatingChildComponent = false;
function setActiveInstance(vm) {
  var prevActiveInstance = activeInstance;
  activeInstance = vm;
  return function () {
    activeInstance = prevActiveInstance;
  };
}
function initLifecycle(vm) {
  var options = vm.$options;

  // locate first non-abstract parent
  var parent = options.parent;
  if (parent && !options.abstract) {
    while (parent.$options.abstract && parent.$parent) {
      parent = parent.$parent;
    }
    parent.$children.push(vm);
  }
  vm.$parent = parent;
  vm.$root = parent ? parent.$root : vm;
  vm.$children = [];
  vm.$refs = {};
  vm._watcher = null;
  vm._inactive = null;
  vm._directInactive = false;
  vm._isMounted = false;
  vm._isDestroyed = false;
  vm._isBeingDestroyed = false;
}
function lifecycleMixin(Vue) {
  Vue.prototype._update = function (vnode, hydrating) {
    var vm = this;
    var prevEl = vm.$el;
    var prevVnode = vm._vnode;
    var restoreActiveInstance = setActiveInstance(vm);
    vm._vnode = vnode;
    // Vue.prototype.__patch__ is injected in entry points
    // based on the rendering backend used.
    if (!prevVnode) {
      // initial render
      vm.$el = vm.__patch__(vm.$el, vnode, hydrating, false /* removeOnly */);
    } else {
      // updates
      vm.$el = vm.__patch__(prevVnode, vnode);
    }
    restoreActiveInstance();
    // update __vue__ reference
    if (prevEl) {
      prevEl.__vue__ = null;
    }
    if (vm.$el) {
      vm.$el.__vue__ = vm;
    }
    // if parent is an HOC, update its $el as well
    if (vm.$vnode && vm.$parent && vm.$vnode === vm.$parent._vnode) {
      vm.$parent.$el = vm.$el;
    }
    // updated hook is called by the scheduler to ensure that children are
    // updated in a parent's updated hook.
  };
  Vue.prototype.$forceUpdate = function () {
    var vm = this;
    if (vm._watcher) {
      vm._watcher.update();
    }
  };
  Vue.prototype.$destroy = function () {
    var vm = this;
    if (vm._isBeingDestroyed) {
      return;
    }
    callHook(vm, 'beforeDestroy');
    vm._isBeingDestroyed = true;
    // remove self from parent
    var parent = vm.$parent;
    if (parent && !parent._isBeingDestroyed && !vm.$options.abstract) {
      remove(parent.$children, vm);
    }
    // teardown watchers
    if (vm._watcher) {
      vm._watcher.teardown();
    }
    var i = vm._watchers.length;
    while (i--) {
      vm._watchers[i].teardown();
    }
    // remove reference from data ob
    // frozen object may not have observer.
    if (vm._data.__ob__) {
      vm._data.__ob__.vmCount--;
    }
    // call the last hook...
    vm._isDestroyed = true;
    // invoke destroy hooks on current rendered tree
    vm.__patch__(vm._vnode, null);
    // fire destroyed hook
    callHook(vm, 'destroyed');
    // turn off all instance listeners.
    vm.$off();
    // remove __vue__ reference
    if (vm.$el) {
      vm.$el.__vue__ = null;
    }
    // release circular reference (#6759)
    if (vm.$vnode) {
      vm.$vnode.parent = null;
    }
  };
}
function updateChildComponent(vm, propsData, listeners, parentVnode, renderChildren) {
  if (true) {
    isUpdatingChildComponent = true;
  }

  // determine whether component has slot children
  // we need to do this before overwriting $options._renderChildren.

  // check if there are dynamic scopedSlots (hand-written or compiled but with
  // dynamic slot names). Static scoped slots compiled from template has the
  // "$stable" marker.
  var newScopedSlots = parentVnode.data.scopedSlots;
  var oldScopedSlots = vm.$scopedSlots;
  var hasDynamicScopedSlot = !!(newScopedSlots && !newScopedSlots.$stable || oldScopedSlots !== emptyObject && !oldScopedSlots.$stable || newScopedSlots && vm.$scopedSlots.$key !== newScopedSlots.$key);

  // Any static slot children from the parent may have changed during parent's
  // update. Dynamic scoped slots may also have changed. In such cases, a forced
  // update is necessary to ensure correctness.
  var needsForceUpdate = !!(renderChildren ||
  // has new static slots
  vm.$options._renderChildren ||
  // has old static slots
  hasDynamicScopedSlot);
  vm.$options._parentVnode = parentVnode;
  vm.$vnode = parentVnode; // update vm's placeholder node without re-render

  if (vm._vnode) {
    // update child tree's parent
    vm._vnode.parent = parentVnode;
  }
  vm.$options._renderChildren = renderChildren;

  // update $attrs and $listeners hash
  // these are also reactive so they may trigger child update if the child
  // used them during render
  vm.$attrs = parentVnode.data.attrs || emptyObject;
  vm.$listeners = listeners || emptyObject;

  // update props
  if (propsData && vm.$options.props) {
    toggleObserving(false);
    var props = vm._props;
    var propKeys = vm.$options._propKeys || [];
    for (var i = 0; i < propKeys.length; i++) {
      var key = propKeys[i];
      var propOptions = vm.$options.props; // wtf flow?
      props[key] = validateProp(key, propOptions, propsData, vm);
    }
    toggleObserving(true);
    // keep a copy of raw propsData
    vm.$options.propsData = propsData;
  }

  // fixed by xxxxxx update properties(mp runtime)
  vm._$updateProperties && vm._$updateProperties(vm);

  // update listeners
  listeners = listeners || emptyObject;
  var oldListeners = vm.$options._parentListeners;
  vm.$options._parentListeners = listeners;
  updateComponentListeners(vm, listeners, oldListeners);

  // resolve slots + force update if has children
  if (needsForceUpdate) {
    vm.$slots = resolveSlots(renderChildren, parentVnode.context);
    vm.$forceUpdate();
  }
  if (true) {
    isUpdatingChildComponent = false;
  }
}
function isInInactiveTree(vm) {
  while (vm && (vm = vm.$parent)) {
    if (vm._inactive) {
      return true;
    }
  }
  return false;
}
function activateChildComponent(vm, direct) {
  if (direct) {
    vm._directInactive = false;
    if (isInInactiveTree(vm)) {
      return;
    }
  } else if (vm._directInactive) {
    return;
  }
  if (vm._inactive || vm._inactive === null) {
    vm._inactive = false;
    for (var i = 0; i < vm.$children.length; i++) {
      activateChildComponent(vm.$children[i]);
    }
    callHook(vm, 'activated');
  }
}
function deactivateChildComponent(vm, direct) {
  if (direct) {
    vm._directInactive = true;
    if (isInInactiveTree(vm)) {
      return;
    }
  }
  if (!vm._inactive) {
    vm._inactive = true;
    for (var i = 0; i < vm.$children.length; i++) {
      deactivateChildComponent(vm.$children[i]);
    }
    callHook(vm, 'deactivated');
  }
}
function callHook(vm, hook) {
  // #7573 disable dep collection when invoking lifecycle hooks
  pushTarget();
  var handlers = vm.$options[hook];
  var info = hook + " hook";
  if (handlers) {
    for (var i = 0, j = handlers.length; i < j; i++) {
      invokeWithErrorHandling(handlers[i], vm, null, vm, info);
    }
  }
  if (vm._hasHookEvent) {
    vm.$emit('hook:' + hook);
  }
  popTarget();
}

/*  */

var MAX_UPDATE_COUNT = 100;
var queue = [];
var activatedChildren = [];
var has = {};
var circular = {};
var waiting = false;
var flushing = false;
var index = 0;

/**
 * Reset the scheduler's state.
 */
function resetSchedulerState() {
  index = queue.length = activatedChildren.length = 0;
  has = {};
  if (true) {
    circular = {};
  }
  waiting = flushing = false;
}

// Async edge case #6566 requires saving the timestamp when event listeners are
// attached. However, calling performance.now() has a perf overhead especially
// if the page has thousands of event listeners. Instead, we take a timestamp
// every time the scheduler flushes and use that for all event listeners
// attached during that flush.
var currentFlushTimestamp = 0;

// Async edge case fix requires storing an event listener's attach timestamp.
var getNow = Date.now;

// Determine what event timestamp the browser is using. Annoyingly, the
// timestamp can either be hi-res (relative to page load) or low-res
// (relative to UNIX epoch), so in order to compare time we have to use the
// same timestamp type when saving the flush timestamp.
// All IE versions use low-res event timestamps, and have problematic clock
// implementations (#9632)
if (inBrowser && !isIE) {
  var performance = window.performance;
  if (performance && typeof performance.now === 'function' && getNow() > document.createEvent('Event').timeStamp) {
    // if the event timestamp, although evaluated AFTER the Date.now(), is
    // smaller than it, it means the event is using a hi-res timestamp,
    // and we need to use the hi-res version for event listener timestamps as
    // well.
    getNow = function () {
      return performance.now();
    };
  }
}

/**
 * Flush both queues and run the watchers.
 */
function flushSchedulerQueue() {
  currentFlushTimestamp = getNow();
  flushing = true;
  var watcher, id;

  // Sort queue before flush.
  // This ensures that:
  // 1. Components are updated from parent to child. (because parent is always
  //    created before the child)
  // 2. A component's user watchers are run before its render watcher (because
  //    user watchers are created before the render watcher)
  // 3. If a component is destroyed during a parent component's watcher run,
  //    its watchers can be skipped.
  queue.sort(function (a, b) {
    return a.id - b.id;
  });

  // do not cache length because more watchers might be pushed
  // as we run existing watchers
  for (index = 0; index < queue.length; index++) {
    watcher = queue[index];
    if (watcher.before) {
      watcher.before();
    }
    id = watcher.id;
    has[id] = null;
    watcher.run();
    // in dev build, check and stop circular updates.
    if ( true && has[id] != null) {
      circular[id] = (circular[id] || 0) + 1;
      if (circular[id] > MAX_UPDATE_COUNT) {
        warn('You may have an infinite update loop ' + (watcher.user ? "in watcher with expression \"" + watcher.expression + "\"" : "in a component render function."), watcher.vm);
        break;
      }
    }
  }

  // keep copies of post queues before resetting state
  var activatedQueue = activatedChildren.slice();
  var updatedQueue = queue.slice();
  resetSchedulerState();

  // call component updated and activated hooks
  callActivatedHooks(activatedQueue);
  callUpdatedHooks(updatedQueue);

  // devtool hook
  /* istanbul ignore if */
  if (devtools && config.devtools) {
    devtools.emit('flush');
  }
}
function callUpdatedHooks(queue) {
  var i = queue.length;
  while (i--) {
    var watcher = queue[i];
    var vm = watcher.vm;
    if (vm._watcher === watcher && vm._isMounted && !vm._isDestroyed) {
      callHook(vm, 'updated');
    }
  }
}

/**
 * Queue a kept-alive component that was activated during patch.
 * The queue will be processed after the entire tree has been patched.
 */
function queueActivatedComponent(vm) {
  // setting _inactive to false here so that a render function can
  // rely on checking whether it's in an inactive tree (e.g. router-view)
  vm._inactive = false;
  activatedChildren.push(vm);
}
function callActivatedHooks(queue) {
  for (var i = 0; i < queue.length; i++) {
    queue[i]._inactive = true;
    activateChildComponent(queue[i], true /* true */);
  }
}

/**
 * Push a watcher into the watcher queue.
 * Jobs with duplicate IDs will be skipped unless it's
 * pushed when the queue is being flushed.
 */
function queueWatcher(watcher) {
  var id = watcher.id;
  if (has[id] == null) {
    has[id] = true;
    if (!flushing) {
      queue.push(watcher);
    } else {
      // if already flushing, splice the watcher based on its id
      // if already past its id, it will be run next immediately.
      var i = queue.length - 1;
      while (i > index && queue[i].id > watcher.id) {
        i--;
      }
      queue.splice(i + 1, 0, watcher);
    }
    // queue the flush
    if (!waiting) {
      waiting = true;
      if ( true && !config.async) {
        flushSchedulerQueue();
        return;
      }
      nextTick(flushSchedulerQueue);
    }
  }
}

/*  */

var uid$2 = 0;

/**
 * A watcher parses an expression, collects dependencies,
 * and fires callback when the expression value changes.
 * This is used for both the $watch() api and directives.
 */
var Watcher = function Watcher(vm, expOrFn, cb, options, isRenderWatcher) {
  this.vm = vm;
  if (isRenderWatcher) {
    vm._watcher = this;
  }
  vm._watchers.push(this);
  // options
  if (options) {
    this.deep = !!options.deep;
    this.user = !!options.user;
    this.lazy = !!options.lazy;
    this.sync = !!options.sync;
    this.before = options.before;
  } else {
    this.deep = this.user = this.lazy = this.sync = false;
  }
  this.cb = cb;
  this.id = ++uid$2; // uid for batching
  this.active = true;
  this.dirty = this.lazy; // for lazy watchers
  this.deps = [];
  this.newDeps = [];
  this.depIds = new _Set();
  this.newDepIds = new _Set();
  this.expression =  true ? expOrFn.toString() : undefined;
  // parse expression for getter
  if (typeof expOrFn === 'function') {
    this.getter = expOrFn;
  } else {
    this.getter = parsePath(expOrFn);
    if (!this.getter) {
      this.getter = noop;
       true && warn("Failed watching path: \"" + expOrFn + "\" " + 'Watcher only accepts simple dot-delimited paths. ' + 'For full control, use a function instead.', vm);
    }
  }
  this.value = this.lazy ? undefined : this.get();
};

/**
 * Evaluate the getter, and re-collect dependencies.
 */
Watcher.prototype.get = function get() {
  pushTarget(this);
  var value;
  var vm = this.vm;
  try {
    value = this.getter.call(vm, vm);
  } catch (e) {
    if (this.user) {
      handleError(e, vm, "getter for watcher \"" + this.expression + "\"");
    } else {
      throw e;
    }
  } finally {
    // "touch" every property so they are all tracked as
    // dependencies for deep watching
    if (this.deep) {
      traverse(value);
    }
    popTarget();
    this.cleanupDeps();
  }
  return value;
};

/**
 * Add a dependency to this directive.
 */
Watcher.prototype.addDep = function addDep(dep) {
  var id = dep.id;
  if (!this.newDepIds.has(id)) {
    this.newDepIds.add(id);
    this.newDeps.push(dep);
    if (!this.depIds.has(id)) {
      dep.addSub(this);
    }
  }
};

/**
 * Clean up for dependency collection.
 */
Watcher.prototype.cleanupDeps = function cleanupDeps() {
  var i = this.deps.length;
  while (i--) {
    var dep = this.deps[i];
    if (!this.newDepIds.has(dep.id)) {
      dep.removeSub(this);
    }
  }
  var tmp = this.depIds;
  this.depIds = this.newDepIds;
  this.newDepIds = tmp;
  this.newDepIds.clear();
  tmp = this.deps;
  this.deps = this.newDeps;
  this.newDeps = tmp;
  this.newDeps.length = 0;
};

/**
 * Subscriber interface.
 * Will be called when a dependency changes.
 */
Watcher.prototype.update = function update() {
  /* istanbul ignore else */
  if (this.lazy) {
    this.dirty = true;
  } else if (this.sync) {
    this.run();
  } else {
    queueWatcher(this);
  }
};

/**
 * Scheduler job interface.
 * Will be called by the scheduler.
 */
Watcher.prototype.run = function run() {
  if (this.active) {
    var value = this.get();
    if (value !== this.value ||
    // Deep watchers and watchers on Object/Arrays should fire even
    // when the value is the same, because the value may
    // have mutated.
    isObject(value) || this.deep) {
      // set new value
      var oldValue = this.value;
      this.value = value;
      if (this.user) {
        try {
          this.cb.call(this.vm, value, oldValue);
        } catch (e) {
          handleError(e, this.vm, "callback for watcher \"" + this.expression + "\"");
        }
      } else {
        this.cb.call(this.vm, value, oldValue);
      }
    }
  }
};

/**
 * Evaluate the value of the watcher.
 * This only gets called for lazy watchers.
 */
Watcher.prototype.evaluate = function evaluate() {
  this.value = this.get();
  this.dirty = false;
};

/**
 * Depend on all deps collected by this watcher.
 */
Watcher.prototype.depend = function depend() {
  var i = this.deps.length;
  while (i--) {
    this.deps[i].depend();
  }
};

/**
 * Remove self from all dependencies' subscriber list.
 */
Watcher.prototype.teardown = function teardown() {
  if (this.active) {
    // remove self from vm's watcher list
    // this is a somewhat expensive operation so we skip it
    // if the vm is being destroyed.
    if (!this.vm._isBeingDestroyed) {
      remove(this.vm._watchers, this);
    }
    var i = this.deps.length;
    while (i--) {
      this.deps[i].removeSub(this);
    }
    this.active = false;
  }
};

/*  */

var sharedPropertyDefinition = {
  enumerable: true,
  configurable: true,
  get: noop,
  set: noop
};
function proxy(target, sourceKey, key) {
  sharedPropertyDefinition.get = function proxyGetter() {
    return this[sourceKey][key];
  };
  sharedPropertyDefinition.set = function proxySetter(val) {
    this[sourceKey][key] = val;
  };
  Object.defineProperty(target, key, sharedPropertyDefinition);
}
function initState(vm) {
  vm._watchers = [];
  var opts = vm.$options;
  if (opts.props) {
    initProps(vm, opts.props);
  }
  if (opts.methods) {
    initMethods(vm, opts.methods);
  }
  if (opts.data) {
    initData(vm);
  } else {
    observe(vm._data = {}, true /* asRootData */);
  }
  if (opts.computed) {
    initComputed(vm, opts.computed);
  }
  if (opts.watch && opts.watch !== nativeWatch) {
    initWatch(vm, opts.watch);
  }
}
function initProps(vm, propsOptions) {
  var propsData = vm.$options.propsData || {};
  var props = vm._props = {};
  // cache prop keys so that future props updates can iterate using Array
  // instead of dynamic object key enumeration.
  var keys = vm.$options._propKeys = [];
  var isRoot = !vm.$parent;
  // root instance props should be converted
  if (!isRoot) {
    toggleObserving(false);
  }
  var loop = function (key) {
    keys.push(key);
    var value = validateProp(key, propsOptions, propsData, vm);
    /* istanbul ignore else */
    if (true) {
      var hyphenatedKey = hyphenate(key);
      if (isReservedAttribute(hyphenatedKey) || config.isReservedAttr(hyphenatedKey)) {
        warn("\"" + hyphenatedKey + "\" is a reserved attribute and cannot be used as component prop.", vm);
      }
      defineReactive$$1(props, key, value, function () {
        if (!isRoot && !isUpdatingChildComponent) {
          {
            if (vm.mpHost === 'mp-baidu' || vm.mpHost === 'mp-kuaishou' || vm.mpHost === 'mp-xhs') {
              //百度、快手、小红书 observer 在 setData callback 之后触发，直接忽略该 warn
              return;
            }
            //fixed by xxxxxx __next_tick_pending,uni://form-field 时不告警
            if (key === 'value' && Array.isArray(vm.$options.behaviors) && vm.$options.behaviors.indexOf('uni://form-field') !== -1) {
              return;
            }
            if (vm._getFormData) {
              return;
            }
            var $parent = vm.$parent;
            while ($parent) {
              if ($parent.__next_tick_pending) {
                return;
              }
              $parent = $parent.$parent;
            }
          }
          warn("Avoid mutating a prop directly since the value will be " + "overwritten whenever the parent component re-renders. " + "Instead, use a data or computed property based on the prop's " + "value. Prop being mutated: \"" + key + "\"", vm);
        }
      });
    } else {}
    // static props are already proxied on the component's prototype
    // during Vue.extend(). We only need to proxy props defined at
    // instantiation here.
    if (!(key in vm)) {
      proxy(vm, "_props", key);
    }
  };
  for (var key in propsOptions) loop(key);
  toggleObserving(true);
}
function initData(vm) {
  var data = vm.$options.data;
  data = vm._data = typeof data === 'function' ? getData(data, vm) : data || {};
  if (!isPlainObject(data)) {
    data = {};
     true && warn('data functions should return an object:\n' + 'https://vuejs.org/v2/guide/components.html#data-Must-Be-a-Function', vm);
  }
  // proxy data on instance
  var keys = Object.keys(data);
  var props = vm.$options.props;
  var methods = vm.$options.methods;
  var i = keys.length;
  while (i--) {
    var key = keys[i];
    if (true) {
      if (methods && hasOwn(methods, key)) {
        warn("Method \"" + key + "\" has already been defined as a data property.", vm);
      }
    }
    if (props && hasOwn(props, key)) {
       true && warn("The data property \"" + key + "\" is already declared as a prop. " + "Use prop default value instead.", vm);
    } else if (!isReserved(key)) {
      proxy(vm, "_data", key);
    }
  }
  // observe data
  observe(data, true /* asRootData */);
}
function getData(data, vm) {
  // #7573 disable dep collection when invoking data getters
  pushTarget();
  try {
    return data.call(vm, vm);
  } catch (e) {
    handleError(e, vm, "data()");
    return {};
  } finally {
    popTarget();
  }
}
var computedWatcherOptions = {
  lazy: true
};
function initComputed(vm, computed) {
  // $flow-disable-line
  var watchers = vm._computedWatchers = Object.create(null);
  // computed properties are just getters during SSR
  var isSSR = isServerRendering();
  for (var key in computed) {
    var userDef = computed[key];
    var getter = typeof userDef === 'function' ? userDef : userDef.get;
    if ( true && getter == null) {
      warn("Getter is missing for computed property \"" + key + "\".", vm);
    }
    if (!isSSR) {
      // create internal watcher for the computed property.
      watchers[key] = new Watcher(vm, getter || noop, noop, computedWatcherOptions);
    }

    // component-defined computed properties are already defined on the
    // component prototype. We only need to define computed properties defined
    // at instantiation here.
    if (!(key in vm)) {
      defineComputed(vm, key, userDef);
    } else if (true) {
      if (key in vm.$data) {
        warn("The computed property \"" + key + "\" is already defined in data.", vm);
      } else if (vm.$options.props && key in vm.$options.props) {
        warn("The computed property \"" + key + "\" is already defined as a prop.", vm);
      }
    }
  }
}
function defineComputed(target, key, userDef) {
  var shouldCache = !isServerRendering();
  if (typeof userDef === 'function') {
    sharedPropertyDefinition.get = shouldCache ? createComputedGetter(key) : createGetterInvoker(userDef);
    sharedPropertyDefinition.set = noop;
  } else {
    sharedPropertyDefinition.get = userDef.get ? shouldCache && userDef.cache !== false ? createComputedGetter(key) : createGetterInvoker(userDef.get) : noop;
    sharedPropertyDefinition.set = userDef.set || noop;
  }
  if ( true && sharedPropertyDefinition.set === noop) {
    sharedPropertyDefinition.set = function () {
      warn("Computed property \"" + key + "\" was assigned to but it has no setter.", this);
    };
  }
  Object.defineProperty(target, key, sharedPropertyDefinition);
}
function createComputedGetter(key) {
  return function computedGetter() {
    var watcher = this._computedWatchers && this._computedWatchers[key];
    if (watcher) {
      if (watcher.dirty) {
        watcher.evaluate();
      }
      if (Dep.SharedObject.target) {
        // fixed by xxxxxx
        watcher.depend();
      }
      return watcher.value;
    }
  };
}
function createGetterInvoker(fn) {
  return function computedGetter() {
    return fn.call(this, this);
  };
}
function initMethods(vm, methods) {
  var props = vm.$options.props;
  for (var key in methods) {
    if (true) {
      if (typeof methods[key] !== 'function') {
        warn("Method \"" + key + "\" has type \"" + typeof methods[key] + "\" in the component definition. " + "Did you reference the function correctly?", vm);
      }
      if (props && hasOwn(props, key)) {
        warn("Method \"" + key + "\" has already been defined as a prop.", vm);
      }
      if (key in vm && isReserved(key)) {
        warn("Method \"" + key + "\" conflicts with an existing Vue instance method. " + "Avoid defining component methods that start with _ or $.");
      }
    }
    vm[key] = typeof methods[key] !== 'function' ? noop : bind(methods[key], vm);
  }
}
function initWatch(vm, watch) {
  for (var key in watch) {
    var handler = watch[key];
    if (Array.isArray(handler)) {
      for (var i = 0; i < handler.length; i++) {
        createWatcher(vm, key, handler[i]);
      }
    } else {
      createWatcher(vm, key, handler);
    }
  }
}
function createWatcher(vm, expOrFn, handler, options) {
  if (isPlainObject(handler)) {
    options = handler;
    handler = handler.handler;
  }
  if (typeof handler === 'string') {
    handler = vm[handler];
  }
  return vm.$watch(expOrFn, handler, options);
}
function stateMixin(Vue) {
  // flow somehow has problems with directly declared definition object
  // when using Object.defineProperty, so we have to procedurally build up
  // the object here.
  var dataDef = {};
  dataDef.get = function () {
    return this._data;
  };
  var propsDef = {};
  propsDef.get = function () {
    return this._props;
  };
  if (true) {
    dataDef.set = function () {
      warn('Avoid replacing instance root $data. ' + 'Use nested data properties instead.', this);
    };
    propsDef.set = function () {
      warn("$props is readonly.", this);
    };
  }
  Object.defineProperty(Vue.prototype, '$data', dataDef);
  Object.defineProperty(Vue.prototype, '$props', propsDef);
  Vue.prototype.$set = set;
  Vue.prototype.$delete = del;
  Vue.prototype.$watch = function (expOrFn, cb, options) {
    var vm = this;
    if (isPlainObject(cb)) {
      return createWatcher(vm, expOrFn, cb, options);
    }
    options = options || {};
    options.user = true;
    var watcher = new Watcher(vm, expOrFn, cb, options);
    if (options.immediate) {
      try {
        cb.call(vm, watcher.value);
      } catch (error) {
        handleError(error, vm, "callback for immediate watcher \"" + watcher.expression + "\"");
      }
    }
    return function unwatchFn() {
      watcher.teardown();
    };
  };
}

/*  */

var uid$3 = 0;
function initMixin(Vue) {
  Vue.prototype._init = function (options) {
    var vm = this;
    // a uid
    vm._uid = uid$3++;
    var startTag, endTag;
    /* istanbul ignore if */
    if ( true && config.performance && mark) {
      startTag = "vue-perf-start:" + vm._uid;
      endTag = "vue-perf-end:" + vm._uid;
      mark(startTag);
    }

    // a flag to avoid this being observed
    vm._isVue = true;
    // merge options
    if (options && options._isComponent) {
      // optimize internal component instantiation
      // since dynamic options merging is pretty slow, and none of the
      // internal component options needs special treatment.
      initInternalComponent(vm, options);
    } else {
      vm.$options = mergeOptions(resolveConstructorOptions(vm.constructor), options || {}, vm);
    }
    /* istanbul ignore else */
    if (true) {
      initProxy(vm);
    } else {}
    // expose real self
    vm._self = vm;
    initLifecycle(vm);
    initEvents(vm);
    initRender(vm);
    callHook(vm, 'beforeCreate');
    !vm._$fallback && initInjections(vm); // resolve injections before data/props  
    initState(vm);
    !vm._$fallback && initProvide(vm); // resolve provide after data/props
    !vm._$fallback && callHook(vm, 'created');

    /* istanbul ignore if */
    if ( true && config.performance && mark) {
      vm._name = formatComponentName(vm, false);
      mark(endTag);
      measure("vue " + vm._name + " init", startTag, endTag);
    }
    if (vm.$options.el) {
      vm.$mount(vm.$options.el);
    }
  };
}
function initInternalComponent(vm, options) {
  var opts = vm.$options = Object.create(vm.constructor.options);
  // doing this because it's faster than dynamic enumeration.
  var parentVnode = options._parentVnode;
  opts.parent = options.parent;
  opts._parentVnode = parentVnode;
  var vnodeComponentOptions = parentVnode.componentOptions;
  opts.propsData = vnodeComponentOptions.propsData;
  opts._parentListeners = vnodeComponentOptions.listeners;
  opts._renderChildren = vnodeComponentOptions.children;
  opts._componentTag = vnodeComponentOptions.tag;
  if (options.render) {
    opts.render = options.render;
    opts.staticRenderFns = options.staticRenderFns;
  }
}
function resolveConstructorOptions(Ctor) {
  var options = Ctor.options;
  if (Ctor.super) {
    var superOptions = resolveConstructorOptions(Ctor.super);
    var cachedSuperOptions = Ctor.superOptions;
    if (superOptions !== cachedSuperOptions) {
      // super option changed,
      // need to resolve new options.
      Ctor.superOptions = superOptions;
      // check if there are any late-modified/attached options (#4976)
      var modifiedOptions = resolveModifiedOptions(Ctor);
      // update base extend options
      if (modifiedOptions) {
        extend(Ctor.extendOptions, modifiedOptions);
      }
      options = Ctor.options = mergeOptions(superOptions, Ctor.extendOptions);
      if (options.name) {
        options.components[options.name] = Ctor;
      }
    }
  }
  return options;
}
function resolveModifiedOptions(Ctor) {
  var modified;
  var latest = Ctor.options;
  var sealed = Ctor.sealedOptions;
  for (var key in latest) {
    if (latest[key] !== sealed[key]) {
      if (!modified) {
        modified = {};
      }
      modified[key] = latest[key];
    }
  }
  return modified;
}
function Vue(options) {
  if ( true && !(this instanceof Vue)) {
    warn('Vue is a constructor and should be called with the `new` keyword');
  }
  this._init(options);
}
initMixin(Vue);
stateMixin(Vue);
eventsMixin(Vue);
lifecycleMixin(Vue);
renderMixin(Vue);

/*  */

function initUse(Vue) {
  Vue.use = function (plugin) {
    var installedPlugins = this._installedPlugins || (this._installedPlugins = []);
    if (installedPlugins.indexOf(plugin) > -1) {
      return this;
    }

    // additional parameters
    var args = toArray(arguments, 1);
    args.unshift(this);
    if (typeof plugin.install === 'function') {
      plugin.install.apply(plugin, args);
    } else if (typeof plugin === 'function') {
      plugin.apply(null, args);
    }
    installedPlugins.push(plugin);
    return this;
  };
}

/*  */

function initMixin$1(Vue) {
  Vue.mixin = function (mixin) {
    this.options = mergeOptions(this.options, mixin);
    return this;
  };
}

/*  */

function initExtend(Vue) {
  /**
   * Each instance constructor, including Vue, has a unique
   * cid. This enables us to create wrapped "child
   * constructors" for prototypal inheritance and cache them.
   */
  Vue.cid = 0;
  var cid = 1;

  /**
   * Class inheritance
   */
  Vue.extend = function (extendOptions) {
    extendOptions = extendOptions || {};
    var Super = this;
    var SuperId = Super.cid;
    var cachedCtors = extendOptions._Ctor || (extendOptions._Ctor = {});
    if (cachedCtors[SuperId]) {
      return cachedCtors[SuperId];
    }
    var name = extendOptions.name || Super.options.name;
    if ( true && name) {
      validateComponentName(name);
    }
    var Sub = function VueComponent(options) {
      this._init(options);
    };
    Sub.prototype = Object.create(Super.prototype);
    Sub.prototype.constructor = Sub;
    Sub.cid = cid++;
    Sub.options = mergeOptions(Super.options, extendOptions);
    Sub['super'] = Super;

    // For props and computed properties, we define the proxy getters on
    // the Vue instances at extension time, on the extended prototype. This
    // avoids Object.defineProperty calls for each instance created.
    if (Sub.options.props) {
      initProps$1(Sub);
    }
    if (Sub.options.computed) {
      initComputed$1(Sub);
    }

    // allow further extension/mixin/plugin usage
    Sub.extend = Super.extend;
    Sub.mixin = Super.mixin;
    Sub.use = Super.use;

    // create asset registers, so extended classes
    // can have their private assets too.
    ASSET_TYPES.forEach(function (type) {
      Sub[type] = Super[type];
    });
    // enable recursive self-lookup
    if (name) {
      Sub.options.components[name] = Sub;
    }

    // keep a reference to the super options at extension time.
    // later at instantiation we can check if Super's options have
    // been updated.
    Sub.superOptions = Super.options;
    Sub.extendOptions = extendOptions;
    Sub.sealedOptions = extend({}, Sub.options);

    // cache constructor
    cachedCtors[SuperId] = Sub;
    return Sub;
  };
}
function initProps$1(Comp) {
  var props = Comp.options.props;
  for (var key in props) {
    proxy(Comp.prototype, "_props", key);
  }
}
function initComputed$1(Comp) {
  var computed = Comp.options.computed;
  for (var key in computed) {
    defineComputed(Comp.prototype, key, computed[key]);
  }
}

/*  */

function initAssetRegisters(Vue) {
  /**
   * Create asset registration methods.
   */
  ASSET_TYPES.forEach(function (type) {
    Vue[type] = function (id, definition) {
      if (!definition) {
        return this.options[type + 's'][id];
      } else {
        /* istanbul ignore if */
        if ( true && type === 'component') {
          validateComponentName(id);
        }
        if (type === 'component' && isPlainObject(definition)) {
          definition.name = definition.name || id;
          definition = this.options._base.extend(definition);
        }
        if (type === 'directive' && typeof definition === 'function') {
          definition = {
            bind: definition,
            update: definition
          };
        }
        this.options[type + 's'][id] = definition;
        return definition;
      }
    };
  });
}

/*  */

function getComponentName(opts) {
  return opts && (opts.Ctor.options.name || opts.tag);
}
function matches(pattern, name) {
  if (Array.isArray(pattern)) {
    return pattern.indexOf(name) > -1;
  } else if (typeof pattern === 'string') {
    return pattern.split(',').indexOf(name) > -1;
  } else if (isRegExp(pattern)) {
    return pattern.test(name);
  }
  /* istanbul ignore next */
  return false;
}
function pruneCache(keepAliveInstance, filter) {
  var cache = keepAliveInstance.cache;
  var keys = keepAliveInstance.keys;
  var _vnode = keepAliveInstance._vnode;
  for (var key in cache) {
    var cachedNode = cache[key];
    if (cachedNode) {
      var name = getComponentName(cachedNode.componentOptions);
      if (name && !filter(name)) {
        pruneCacheEntry(cache, key, keys, _vnode);
      }
    }
  }
}
function pruneCacheEntry(cache, key, keys, current) {
  var cached$$1 = cache[key];
  if (cached$$1 && (!current || cached$$1.tag !== current.tag)) {
    cached$$1.componentInstance.$destroy();
  }
  cache[key] = null;
  remove(keys, key);
}
var patternTypes = [String, RegExp, Array];
var KeepAlive = {
  name: 'keep-alive',
  abstract: true,
  props: {
    include: patternTypes,
    exclude: patternTypes,
    max: [String, Number]
  },
  created: function created() {
    this.cache = Object.create(null);
    this.keys = [];
  },
  destroyed: function destroyed() {
    for (var key in this.cache) {
      pruneCacheEntry(this.cache, key, this.keys);
    }
  },
  mounted: function mounted() {
    var this$1 = this;
    this.$watch('include', function (val) {
      pruneCache(this$1, function (name) {
        return matches(val, name);
      });
    });
    this.$watch('exclude', function (val) {
      pruneCache(this$1, function (name) {
        return !matches(val, name);
      });
    });
  },
  render: function render() {
    var slot = this.$slots.default;
    var vnode = getFirstComponentChild(slot);
    var componentOptions = vnode && vnode.componentOptions;
    if (componentOptions) {
      // check pattern
      var name = getComponentName(componentOptions);
      var ref = this;
      var include = ref.include;
      var exclude = ref.exclude;
      if (
      // not included
      include && (!name || !matches(include, name)) ||
      // excluded
      exclude && name && matches(exclude, name)) {
        return vnode;
      }
      var ref$1 = this;
      var cache = ref$1.cache;
      var keys = ref$1.keys;
      var key = vnode.key == null
      // same constructor may get registered as different local components
      // so cid alone is not enough (#3269)
      ? componentOptions.Ctor.cid + (componentOptions.tag ? "::" + componentOptions.tag : '') : vnode.key;
      if (cache[key]) {
        vnode.componentInstance = cache[key].componentInstance;
        // make current key freshest
        remove(keys, key);
        keys.push(key);
      } else {
        cache[key] = vnode;
        keys.push(key);
        // prune oldest entry
        if (this.max && keys.length > parseInt(this.max)) {
          pruneCacheEntry(cache, keys[0], keys, this._vnode);
        }
      }
      vnode.data.keepAlive = true;
    }
    return vnode || slot && slot[0];
  }
};
var builtInComponents = {
  KeepAlive: KeepAlive
};

/*  */

function initGlobalAPI(Vue) {
  // config
  var configDef = {};
  configDef.get = function () {
    return config;
  };
  if (true) {
    configDef.set = function () {
      warn('Do not replace the Vue.config object, set individual fields instead.');
    };
  }
  Object.defineProperty(Vue, 'config', configDef);

  // exposed util methods.
  // NOTE: these are not considered part of the public API - avoid relying on
  // them unless you are aware of the risk.
  Vue.util = {
    warn: warn,
    extend: extend,
    mergeOptions: mergeOptions,
    defineReactive: defineReactive$$1
  };
  Vue.set = set;
  Vue.delete = del;
  Vue.nextTick = nextTick;

  // 2.6 explicit observable API
  Vue.observable = function (obj) {
    observe(obj);
    return obj;
  };
  Vue.options = Object.create(null);
  ASSET_TYPES.forEach(function (type) {
    Vue.options[type + 's'] = Object.create(null);
  });

  // this is used to identify the "base" constructor to extend all plain-object
  // components with in Weex's multi-instance scenarios.
  Vue.options._base = Vue;
  extend(Vue.options.components, builtInComponents);
  initUse(Vue);
  initMixin$1(Vue);
  initExtend(Vue);
  initAssetRegisters(Vue);
}
initGlobalAPI(Vue);
Object.defineProperty(Vue.prototype, '$isServer', {
  get: isServerRendering
});
Object.defineProperty(Vue.prototype, '$ssrContext', {
  get: function get() {
    /* istanbul ignore next */
    return this.$vnode && this.$vnode.ssrContext;
  }
});

// expose FunctionalRenderContext for ssr runtime helper installation
Object.defineProperty(Vue, 'FunctionalRenderContext', {
  value: FunctionalRenderContext
});
Vue.version = '2.6.11';

/**
 * https://raw.githubusercontent.com/Tencent/westore/master/packages/westore/utils/diff.js
 */
var ARRAYTYPE = '[object Array]';
var OBJECTTYPE = '[object Object]';
var NULLTYPE = '[object Null]';
var UNDEFINEDTYPE = '[object Undefined]';
// const FUNCTIONTYPE = '[object Function]'

function diff(current, pre) {
  var result = {};
  syncKeys(current, pre);
  _diff(current, pre, '', result);
  return result;
}
function syncKeys(current, pre) {
  if (current === pre) {
    return;
  }
  var rootCurrentType = type(current);
  var rootPreType = type(pre);
  if (rootCurrentType == OBJECTTYPE && rootPreType == OBJECTTYPE) {
    if (Object.keys(current).length >= Object.keys(pre).length) {
      for (var key in pre) {
        var currentValue = current[key];
        if (currentValue === undefined) {
          current[key] = null;
        } else {
          syncKeys(currentValue, pre[key]);
        }
      }
    }
  } else if (rootCurrentType == ARRAYTYPE && rootPreType == ARRAYTYPE) {
    if (current.length >= pre.length) {
      pre.forEach(function (item, index) {
        syncKeys(current[index], item);
      });
    }
  }
}
function nullOrUndefined(currentType, preType) {
  if ((currentType === NULLTYPE || currentType === UNDEFINEDTYPE) && (preType === NULLTYPE || preType === UNDEFINEDTYPE)) {
    return false;
  }
  return true;
}
function _diff(current, pre, path, result) {
  if (current === pre) {
    return;
  }
  var rootCurrentType = type(current);
  var rootPreType = type(pre);
  if (rootCurrentType == OBJECTTYPE) {
    if (rootPreType != OBJECTTYPE || Object.keys(current).length < Object.keys(pre).length) {
      setResult(result, path, current);
    } else {
      var loop = function (key) {
        var currentValue = current[key];
        var preValue = pre[key];
        var currentType = type(currentValue);
        var preType = type(preValue);
        if (currentType != ARRAYTYPE && currentType != OBJECTTYPE) {
          if (currentValue !== pre[key] && nullOrUndefined(currentType, preType)) {
            setResult(result, (path == '' ? '' : path + ".") + key, currentValue);
          }
        } else if (currentType == ARRAYTYPE) {
          if (preType != ARRAYTYPE) {
            setResult(result, (path == '' ? '' : path + ".") + key, currentValue);
          } else {
            if (currentValue.length < preValue.length) {
              setResult(result, (path == '' ? '' : path + ".") + key, currentValue);
            } else {
              currentValue.forEach(function (item, index) {
                _diff(item, preValue[index], (path == '' ? '' : path + ".") + key + '[' + index + ']', result);
              });
            }
          }
        } else if (currentType == OBJECTTYPE) {
          if (preType != OBJECTTYPE || Object.keys(currentValue).length < Object.keys(preValue).length) {
            setResult(result, (path == '' ? '' : path + ".") + key, currentValue);
          } else {
            for (var subKey in currentValue) {
              _diff(currentValue[subKey], preValue[subKey], (path == '' ? '' : path + ".") + key + '.' + subKey, result);
            }
          }
        }
      };
      for (var key in current) loop(key);
    }
  } else if (rootCurrentType == ARRAYTYPE) {
    if (rootPreType != ARRAYTYPE) {
      setResult(result, path, current);
    } else {
      if (current.length < pre.length) {
        setResult(result, path, current);
      } else {
        current.forEach(function (item, index) {
          _diff(item, pre[index], path + '[' + index + ']', result);
        });
      }
    }
  } else {
    setResult(result, path, current);
  }
}
function setResult(result, k, v) {
  // if (type(v) != FUNCTIONTYPE) {
  result[k] = v;
  // }
}
function type(obj) {
  return Object.prototype.toString.call(obj);
}

/**
 * rfdc v1.4.1
 * David Mark Clements <david.clements@nearform.com>
 * Really Fast Deep Clone
 * [npm](https://www.npmjs.com/package/rfdc) [homePage](https://github.com/davidmarkclements/rfdc.git)
 */

/**
 * @typedef {{proto?: boolean; circles?: boolean; reviver: (key: string, value: any) => any; constructorHandlers?: any[];}} Options
 */

function copyBuffer(cur) {
  if (typeof Buffer !== 'undefined' && cur instanceof Buffer) {
    return Buffer.from(cur);
  }
  var length = cur instanceof DataView ? cur.byteLength : cur.length;
  return new cur.constructor(cur.buffer.slice(), cur.byteOffset, length);
}

/**
 *
 * @param {Options} opts
 * @returns {(o: any) => any}
 */
function rfdc(opts) {
  opts = opts || {};
  if (opts.circles) {
    return rfdcCircles(opts);
  }
  var constructorHandlers = new Map();
  constructorHandlers.set(Date, function (o) {
    return o.toJSON();
  });
  constructorHandlers.set(Map, function (o, fn) {
    return new Map(cloneArray(Array.from(o), fn));
  });
  constructorHandlers.set(Set, function (o, fn) {
    return new Set(cloneArray(Array.from(o), fn));
  });
  if (opts.constructorHandlers) {
    opts.constructorHandlers.forEach(function (handler) {
      constructorHandlers.set(handler[0], handler[1]);
    });
  }
  var handler = null;
  return opts.proto ? cloneProto : clone;
  function cloneArray(a, fn) {
    var keys = Object.keys(a);
    var a2 = new Array(a.length);
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      var cur = a[k];
      if (typeof cur !== 'object' || cur === null) {
        a2[k] = cur;
      } else if (cur.constructor !== Object && (handler = constructorHandlers.get(cur.constructor))) {
        a2[k] = handler(cur, fn);
      } else if (ArrayBuffer.isView(cur)) {
        a2[k] = copyBuffer(cur);
      } else {
        a2[k] = fn(opts.reviver ? opts.reviver(k, cur) : cur);
      }
    }
    return a2;
  }
  function clone(o) {
    if (typeof o !== 'object' || o === null) {
      return o;
    }
    if (Array.isArray(o)) {
      return cloneArray(o, clone);
    }
    if (o.constructor !== Object && (handler = constructorHandlers.get(o.constructor))) {
      return handler(o, clone);
    }
    var o2 = {};
    for (var k in o) {
      if (Object.hasOwnProperty.call(o, k) === false) {
        continue;
      }
      var cur = o[k];
      if (typeof cur !== 'object' || cur === null) {
        o2[k] = cur;
      } else if (cur.constructor !== Object && (handler = constructorHandlers.get(cur.constructor))) {
        o2[k] = handler(cur, clone);
      } else if (ArrayBuffer.isView(cur)) {
        o2[k] = copyBuffer(cur);
      } else {
        o2[k] = clone(opts.reviver ? opts.reviver(k, cur) : cur);
      }
    }
    return o2;
  }
  function cloneProto(o) {
    if (typeof o !== 'object' || o === null) {
      return o;
    }
    if (Array.isArray(o)) {
      return cloneArray(o, cloneProto);
    }
    if (o.constructor !== Object && (handler = constructorHandlers.get(o.constructor))) {
      return handler(o, cloneProto);
    }
    var o2 = {};
    for (var k in o) {
      var cur = o[k];
      if (typeof cur !== 'object' || cur === null) {
        o2[k] = cur;
      } else if (cur.constructor !== Object && (handler = constructorHandlers.get(cur.constructor))) {
        o2[k] = handler(cur, cloneProto);
      } else if (ArrayBuffer.isView(cur)) {
        o2[k] = copyBuffer(cur);
      } else {
        o2[k] = cloneProto(opts.reviver ? opts.reviver(k, cur) : cur);
      }
    }
    return o2;
  }
}
function rfdcCircles(opts) {
  var refs = [];
  var refsNew = [];
  var constructorHandlers = new Map();
  constructorHandlers.set(Date, function (o) {
    return o.toJSON();
  });
  constructorHandlers.set(Map, function (o, fn) {
    return new Map(cloneArray(Array.from(o), fn));
  });
  constructorHandlers.set(Set, function (o, fn) {
    return new Set(cloneArray(Array.from(o), fn));
  });
  if (opts.constructorHandlers) {
    opts.constructorHandlers.forEach(function (handler) {
      constructorHandlers.set(handler[0], handler[1]);
    });
  }
  var handler = null;
  return opts.proto ? cloneProto : clone;
  function cloneArray(a, fn) {
    var keys = Object.keys(a);
    var a2 = new Array(a.length);
    refs.push(a);
    refsNew.push(a2);
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      var cur = a[k];
      if (typeof cur !== 'object' || cur === null) {
        a2[k] = cur;
      } else if (cur.constructor !== Object && (handler = constructorHandlers.get(cur.constructor))) {
        a2[k] = handler(cur, fn);
      } else if (ArrayBuffer.isView(cur)) {
        a2[k] = copyBuffer(cur);
      } else {
        var index = refs.indexOf(cur);
        if (index !== -1) {
          a2[k] = refsNew[index];
        } else {
          a2[k] = fn(opts.reviver ? opts.reviver(k, cur) : cur);
        }
      }
    }
    refs.pop();
    refsNew.pop();
    return a2;
  }
  function clone(o) {
    if (typeof o !== 'object' || o === null) {
      return o;
    }
    if (Array.isArray(o)) {
      return cloneArray(o, clone);
    }
    if (o.constructor !== Object && (handler = constructorHandlers.get(o.constructor))) {
      return handler(o, clone);
    }
    var o2 = {};
    refs.push(o);
    refsNew.push(o2);
    for (var k in o) {
      if (Object.hasOwnProperty.call(o, k) === false) {
        continue;
      }
      var cur = o[k];
      if (typeof cur !== 'object' || cur === null) {
        o2[k] = cur;
      } else if (cur.constructor !== Object && (handler = constructorHandlers.get(cur.constructor))) {
        o2[k] = handler(cur, clone);
      } else if (ArrayBuffer.isView(cur)) {
        o2[k] = copyBuffer(cur);
      } else {
        var i = refs.indexOf(cur);
        if (i !== -1) {
          o2[k] = refsNew[i];
        } else {
          o2[k] = clone(opts.reviver ? opts.reviver(k, cur) : cur);
        }
      }
    }
    refs.pop();
    refsNew.pop();
    return o2;
  }
  function cloneProto(o) {
    if (typeof o !== 'object' || o === null) {
      return o;
    }
    if (Array.isArray(o)) {
      return cloneArray(o, cloneProto);
    }
    if (o.constructor !== Object && (handler = constructorHandlers.get(o.constructor))) {
      return handler(o, cloneProto);
    }
    var o2 = {};
    refs.push(o);
    refsNew.push(o2);
    for (var k in o) {
      var cur = o[k];
      if (typeof cur !== 'object' || cur === null) {
        o2[k] = cur;
      } else if (cur.constructor !== Object && (handler = constructorHandlers.get(cur.constructor))) {
        o2[k] = handler(cur, cloneProto);
      } else if (ArrayBuffer.isView(cur)) {
        o2[k] = copyBuffer(cur);
      } else {
        var i = refs.indexOf(cur);
        if (i !== -1) {
          o2[k] = refsNew[i];
        } else {
          o2[k] = cloneProto(opts.reviver ? opts.reviver(k, cur) : cur);
        }
      }
    }
    refs.pop();
    refsNew.pop();
    return o2;
  }
}

/*  */

function flushCallbacks$1(vm) {
  if (vm.__next_tick_callbacks && vm.__next_tick_callbacks.length) {
    if (Object({"NODE_ENV":"development","VUE_APP_DARK_MODE":"false","VUE_APP_NAME":"商城","VUE_APP_PLATFORM":"mp-weixin","BASE_URL":"/"}).VUE_APP_DEBUG) {
      var mpInstance = vm.$scope;
      console.log('[' + +new Date() + '][' + (mpInstance.is || mpInstance.route) + '][' + vm._uid + ']:flushCallbacks[' + vm.__next_tick_callbacks.length + ']');
    }
    var copies = vm.__next_tick_callbacks.slice(0);
    vm.__next_tick_callbacks.length = 0;
    for (var i = 0; i < copies.length; i++) {
      copies[i]();
    }
  }
}
function hasRenderWatcher(vm) {
  return queue.find(function (watcher) {
    return vm._watcher === watcher;
  });
}
function nextTick$1(vm, cb) {
  //1.nextTick 之前 已 setData 且 setData 还未回调完成
  //2.nextTick 之前存在 render watcher
  if (!vm.__next_tick_pending && !hasRenderWatcher(vm)) {
    if (Object({"NODE_ENV":"development","VUE_APP_DARK_MODE":"false","VUE_APP_NAME":"商城","VUE_APP_PLATFORM":"mp-weixin","BASE_URL":"/"}).VUE_APP_DEBUG) {
      var mpInstance = vm.$scope;
      console.log('[' + +new Date() + '][' + (mpInstance.is || mpInstance.route) + '][' + vm._uid + ']:nextVueTick');
    }
    return nextTick(cb, vm);
  } else {
    if (Object({"NODE_ENV":"development","VUE_APP_DARK_MODE":"false","VUE_APP_NAME":"商城","VUE_APP_PLATFORM":"mp-weixin","BASE_URL":"/"}).VUE_APP_DEBUG) {
      var mpInstance$1 = vm.$scope;
      console.log('[' + +new Date() + '][' + (mpInstance$1.is || mpInstance$1.route) + '][' + vm._uid + ']:nextMPTick');
    }
  }
  var _resolve;
  if (!vm.__next_tick_callbacks) {
    vm.__next_tick_callbacks = [];
  }
  vm.__next_tick_callbacks.push(function () {
    if (cb) {
      try {
        cb.call(vm);
      } catch (e) {
        handleError(e, vm, 'nextTick');
      }
    } else if (_resolve) {
      _resolve(vm);
    }
  });
  // $flow-disable-line
  if (!cb && typeof Promise !== 'undefined') {
    return new Promise(function (resolve) {
      _resolve = resolve;
    });
  }
}

/*  */

function clearInstance(key, value) {
  // 简易去除 Vue 和小程序组件实例
  if (value) {
    if (value._isVue || value.__v_isMPComponent) {
      return {};
    }
  }
  return value;
}
var cloneDeepCircles = rfdc({
  circles: true,
  reviver: clearInstance
});
function cloneWithData(vm) {
  // 确保当前 vm 所有数据被同步
  var ret = Object.create(null);
  var dataKeys = [].concat(Object.keys(vm._data || {}), Object.keys(vm._computedWatchers || {}));
  dataKeys.reduce(function (ret, key) {
    ret[key] = vm[key];
    return ret;
  }, ret);

  // vue-composition-api
  var compositionApiState = vm.__composition_api_state__ || vm.__secret_vfa_state__;
  var rawBindings = compositionApiState && compositionApiState.rawBindings;
  if (rawBindings) {
    Object.keys(rawBindings).forEach(function (key) {
      ret[key] = vm[key];
    });
  }

  //TODO 需要把无用数据处理掉，比如 list=>l0 则 list 需要移除，否则多传输一份数据
  Object.assign(ret, vm.$mp.data || {});
  if (Array.isArray(vm.$options.behaviors) && vm.$options.behaviors.indexOf('uni://form-field') !== -1) {
    //form-field
    ret['name'] = vm.name;
    ret['value'] = vm.value;
  }
  return cloneDeepCircles(ret);
}
var patch = function (oldVnode, vnode) {
  var this$1 = this;
  if (vnode === null) {
    //destroy
    return;
  }
  if (this.mpType === 'page' || this.mpType === 'component') {
    var mpInstance = this.$scope;
    var data = Object.create(null);
    try {
      data = cloneWithData(this);
    } catch (err) {
      console.error(err);
    }
    data.__webviewId__ = mpInstance.data.__webviewId__;
    var mpData = Object.create(null);
    Object.keys(data).forEach(function (key) {
      //仅同步 data 中有的数据
      mpData[key] = mpInstance.data[key];
    });
    var diffData = this.$shouldDiffData === false ? data : diff(data, mpData);
    if (Object.keys(diffData).length) {
      if (Object({"NODE_ENV":"development","VUE_APP_DARK_MODE":"false","VUE_APP_NAME":"商城","VUE_APP_PLATFORM":"mp-weixin","BASE_URL":"/"}).VUE_APP_DEBUG) {
        console.log('[' + +new Date() + '][' + (mpInstance.is || mpInstance.route) + '][' + this._uid + ']差量更新', JSON.stringify(diffData));
      }
      this.__next_tick_pending = true;
      mpInstance.setData(diffData, function () {
        this$1.__next_tick_pending = false;
        flushCallbacks$1(this$1);
      });
    } else {
      flushCallbacks$1(this);
    }
  }
};

/*  */

function createEmptyRender() {}
function mountComponent$1(vm, el, hydrating) {
  if (!vm.mpType) {
    //main.js 中的 new Vue
    return vm;
  }
  if (vm.mpType === 'app') {
    vm.$options.render = createEmptyRender;
  }
  if (!vm.$options.render) {
    vm.$options.render = createEmptyRender;
    if (true) {
      /* istanbul ignore if */
      if (vm.$options.template && vm.$options.template.charAt(0) !== '#' || vm.$options.el || el) {
        warn('You are using the runtime-only build of Vue where the template ' + 'compiler is not available. Either pre-compile the templates into ' + 'render functions, or use the compiler-included build.', vm);
      } else {
        warn('Failed to mount component: template or render function not defined.', vm);
      }
    }
  }
  !vm._$fallback && callHook(vm, 'beforeMount');
  var updateComponent = function () {
    vm._update(vm._render(), hydrating);
  };

  // we set this to vm._watcher inside the watcher's constructor
  // since the watcher's initial patch may call $forceUpdate (e.g. inside child
  // component's mounted hook), which relies on vm._watcher being already defined
  new Watcher(vm, updateComponent, noop, {
    before: function before() {
      if (vm._isMounted && !vm._isDestroyed) {
        callHook(vm, 'beforeUpdate');
      }
    }
  }, true /* isRenderWatcher */);
  hydrating = false;
  return vm;
}

/*  */

function renderClass(staticClass, dynamicClass) {
  if (isDef(staticClass) || isDef(dynamicClass)) {
    return concat(staticClass, stringifyClass(dynamicClass));
  }
  /* istanbul ignore next */
  return '';
}
function concat(a, b) {
  return a ? b ? a + ' ' + b : a : b || '';
}
function stringifyClass(value) {
  if (Array.isArray(value)) {
    return stringifyArray(value);
  }
  if (isObject(value)) {
    return stringifyObject(value);
  }
  if (typeof value === 'string') {
    return value;
  }
  /* istanbul ignore next */
  return '';
}
function stringifyArray(value) {
  var res = '';
  var stringified;
  for (var i = 0, l = value.length; i < l; i++) {
    if (isDef(stringified = stringifyClass(value[i])) && stringified !== '') {
      if (res) {
        res += ' ';
      }
      res += stringified;
    }
  }
  return res;
}
function stringifyObject(value) {
  var res = '';
  for (var key in value) {
    if (value[key]) {
      if (res) {
        res += ' ';
      }
      res += key;
    }
  }
  return res;
}

/*  */

var parseStyleText = cached(function (cssText) {
  var res = {};
  var listDelimiter = /;(?![^(]*\))/g;
  var propertyDelimiter = /:(.+)/;
  cssText.split(listDelimiter).forEach(function (item) {
    if (item) {
      var tmp = item.split(propertyDelimiter);
      tmp.length > 1 && (res[tmp[0].trim()] = tmp[1].trim());
    }
  });
  return res;
});

// normalize possible array / string values into Object
function normalizeStyleBinding(bindingStyle) {
  if (Array.isArray(bindingStyle)) {
    return toObject(bindingStyle);
  }
  if (typeof bindingStyle === 'string') {
    return parseStyleText(bindingStyle);
  }
  return bindingStyle;
}

/*  */

var MP_METHODS = ['createSelectorQuery', 'createIntersectionObserver', 'selectAllComponents', 'selectComponent'];
function getTarget(obj, path) {
  var parts = path.split('.');
  var key = parts[0];
  if (key.indexOf('__$n') === 0) {
    //number index
    key = parseInt(key.replace('__$n', ''));
  }
  if (parts.length === 1) {
    return obj[key];
  }
  return getTarget(obj[key], parts.slice(1).join('.'));
}
function internalMixin(Vue) {
  Vue.config.errorHandler = function (err, vm, info) {
    Vue.util.warn("Error in " + info + ": \"" + err.toString() + "\"", vm);
    console.error(err);
    /* eslint-disable no-undef */
    var app = typeof getApp === 'function' && getApp();
    if (app && app.onError) {
      app.onError(err);
    }
  };
  var oldEmit = Vue.prototype.$emit;
  Vue.prototype.$emit = function (event) {
    if (this.$scope && event) {
      var triggerEvent = this.$scope['_triggerEvent'] || this.$scope['triggerEvent'];
      if (triggerEvent) {
        try {
          triggerEvent.call(this.$scope, event, {
            __args__: toArray(arguments, 1)
          });
        } catch (error) {}
      }
    }
    return oldEmit.apply(this, arguments);
  };
  Vue.prototype.$nextTick = function (fn) {
    return nextTick$1(this, fn);
  };
  MP_METHODS.forEach(function (method) {
    Vue.prototype[method] = function (args) {
      if (this.$scope && this.$scope[method]) {
        return this.$scope[method](args);
      }
      // mp-alipay
      if (typeof my === 'undefined') {
        return;
      }
      if (method === 'createSelectorQuery') {
        /* eslint-disable no-undef */
        return my.createSelectorQuery(args);
      } else if (method === 'createIntersectionObserver') {
        /* eslint-disable no-undef */
        return my.createIntersectionObserver(args);
      }
      // TODO mp-alipay 暂不支持 selectAllComponents,selectComponent
    };
  });
  Vue.prototype.__init_provide = initProvide;
  Vue.prototype.__init_injections = initInjections;
  Vue.prototype.__call_hook = function (hook, args) {
    var vm = this;
    // #7573 disable dep collection when invoking lifecycle hooks
    pushTarget();
    var handlers = vm.$options[hook];
    var info = hook + " hook";
    var ret;
    if (handlers) {
      for (var i = 0, j = handlers.length; i < j; i++) {
        ret = invokeWithErrorHandling(handlers[i], vm, args ? [args] : null, vm, info);
      }
    }
    if (vm._hasHookEvent) {
      vm.$emit('hook:' + hook, args);
    }
    popTarget();
    return ret;
  };
  Vue.prototype.__set_model = function (target, key, value, modifiers) {
    if (Array.isArray(modifiers)) {
      if (modifiers.indexOf('trim') !== -1) {
        value = value.trim();
      }
      if (modifiers.indexOf('number') !== -1) {
        value = this._n(value);
      }
    }
    if (!target) {
      target = this;
    }
    // 解决动态属性添加
    Vue.set(target, key, value);
  };
  Vue.prototype.__set_sync = function (target, key, value) {
    if (!target) {
      target = this;
    }
    // 解决动态属性添加
    Vue.set(target, key, value);
  };
  Vue.prototype.__get_orig = function (item) {
    if (isPlainObject(item)) {
      return item['$orig'] || item;
    }
    return item;
  };
  Vue.prototype.__get_value = function (dataPath, target) {
    return getTarget(target || this, dataPath);
  };
  Vue.prototype.__get_class = function (dynamicClass, staticClass) {
    return renderClass(staticClass, dynamicClass);
  };
  Vue.prototype.__get_style = function (dynamicStyle, staticStyle) {
    if (!dynamicStyle && !staticStyle) {
      return '';
    }
    var dynamicStyleObj = normalizeStyleBinding(dynamicStyle);
    var styleObj = staticStyle ? extend(staticStyle, dynamicStyleObj) : dynamicStyleObj;
    return Object.keys(styleObj).map(function (name) {
      return hyphenate(name) + ":" + styleObj[name];
    }).join(';');
  };
  Vue.prototype.__map = function (val, iteratee) {
    //TODO 暂不考虑 string
    var ret, i, l, keys, key;
    if (Array.isArray(val)) {
      ret = new Array(val.length);
      for (i = 0, l = val.length; i < l; i++) {
        ret[i] = iteratee(val[i], i);
      }
      return ret;
    } else if (isObject(val)) {
      keys = Object.keys(val);
      ret = Object.create(null);
      for (i = 0, l = keys.length; i < l; i++) {
        key = keys[i];
        ret[key] = iteratee(val[key], key, i);
      }
      return ret;
    } else if (typeof val === 'number') {
      ret = new Array(val);
      for (i = 0, l = val; i < l; i++) {
        // 第一个参数暂时仍和小程序一致
        ret[i] = iteratee(i, i);
      }
      return ret;
    }
    return [];
  };
}

/*  */

var LIFECYCLE_HOOKS$1 = [
//App
'onLaunch', 'onShow', 'onHide', 'onUniNViewMessage', 'onPageNotFound', 'onThemeChange', 'onError', 'onUnhandledRejection',
//Page
'onInit', 'onLoad',
// 'onShow',
'onReady',
// 'onHide',
'onUnload', 'onPullDownRefresh', 'onReachBottom', 'onTabItemTap', 'onAddToFavorites', 'onShareTimeline', 'onShareAppMessage', 'onResize', 'onPageScroll', 'onNavigationBarButtonTap', 'onBackPress', 'onNavigationBarSearchInputChanged', 'onNavigationBarSearchInputConfirmed', 'onNavigationBarSearchInputClicked', 'onUploadDouyinVideo', 'onNFCReadMessage',
//Component
// 'onReady', // 兼容旧版本，应该移除该事件
'onPageShow', 'onPageHide', 'onPageResize'];
function lifecycleMixin$1(Vue) {
  //fixed vue-class-component
  var oldExtend = Vue.extend;
  Vue.extend = function (extendOptions) {
    extendOptions = extendOptions || {};
    var methods = extendOptions.methods;
    if (methods) {
      Object.keys(methods).forEach(function (methodName) {
        if (LIFECYCLE_HOOKS$1.indexOf(methodName) !== -1) {
          extendOptions[methodName] = methods[methodName];
          delete methods[methodName];
        }
      });
    }
    return oldExtend.call(this, extendOptions);
  };
  var strategies = Vue.config.optionMergeStrategies;
  var mergeHook = strategies.created;
  LIFECYCLE_HOOKS$1.forEach(function (hook) {
    strategies[hook] = mergeHook;
  });
  Vue.prototype.__lifecycle_hooks__ = LIFECYCLE_HOOKS$1;
}

/*  */

// install platform patch function
Vue.prototype.__patch__ = patch;

// public mount method
Vue.prototype.$mount = function (el, hydrating) {
  return mountComponent$1(this, el, hydrating);
};
lifecycleMixin$1(Vue);
internalMixin(Vue);

/*  */

/* harmony default export */ __webpack_exports__["default"] = (Vue);
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./../../../../../webpack/buildin/global.js */ 3), __webpack_require__(/*! ./../../../../../buffer/index.js */ 6).Buffer))

/***/ }),

/***/ 50:
/*!************************!*\
  !*** ./store/index.js ***!
  \************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {/* harmony import */ var vue__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! vue */ 5);
/* harmony import */ var vuex__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! vuex */ 51);
/* harmony import */ var vuex__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(vuex__WEBPACK_IMPORTED_MODULE_1__);


vue__WEBPACK_IMPORTED_MODULE_0__["default"].use(vuex__WEBPACK_IMPORTED_MODULE_1___default.a);
let lifeData = {};
try {
  // 尝试获取本地是否存在lifeData变量，第一次启动APP时是不存在的
  lifeData = uni.getStorageSync('lifeData');
} catch (e) {}

// 需要永久存储，且下次APP启动需要取出的，在state中的变量名
let saveStateKeys = ['vuex_user', 'vuex_token', 'vuex_setting', 'vuex_openid', 'vuex_signin', 'vuex_webs', 'vuex_lasturl', 'vuex_theme', 'vuex_invite_id', 'vuex_history_keyword'];

// 保存变量到本地存储中
const saveLifeData = function (key, value) {
  // 判断变量名是否在需要存储的数组中
  if (saveStateKeys.indexOf(key) != -1) {
    // 获取本地存储的lifeData对象，将变量添加到对象中
    let tmp = uni.getStorageSync('lifeData');
    // 第一次打开APP，不存在lifeData变量，故放一个{}空对象
    tmp = tmp ? tmp : {};
    tmp[key] = value;
    // 执行这一步后，所有需要存储的变量，都挂载在本地的lifeData对象中
    uni.setStorageSync('lifeData', tmp);
  }
};
const store = new vuex__WEBPACK_IMPORTED_MODULE_1___default.a.Store({
  state: {
    // 如果上面从本地获取的lifeData对象下有对应的属性，就赋值给state中对应的变量
    // 加上vuex_前缀，是防止变量名冲突，也让人一目了然
    vuex_user: lifeData.vuex_user ? lifeData.vuex_user : {},
    vuex_history_keyword: lifeData.vuex_history_keyword ? lifeData.vuex_history_keyword : [],
    vuex_token: lifeData.vuex_token ? lifeData.vuex_token : '',
    vuex_openid: lifeData.vuex_openid ? lifeData.vuex_openid : '',
    vuex_invite_id: '',
    vuex_config: {},
    vuex_setting: lifeData.vuex_setting ? lifeData.vuex_setting : {},
    vuex_theme: lifeData.vuex_theme ? lifeData.vuex_theme : {},
    vuex_lasturl: lifeData.vuex_lasturl ? lifeData.vuex_lasturl : '/pages/index/index',
    vuex_address: {},
    vuex__token__: '',
    vuex_third: {},
    vuex_cart: [],
    //暂存购物车选择的
    vuex_current: 0,
    vuex_signin: {},
    vuex_webs: {},
    vuex_parse_style: {
      // 字符串的形式
      h1: 'padding:20rpx 0;',
      h2: 'padding:10rpx 0;',
      h3: 'padding:10rpx 0;',
      h4: 'padding:10rpx 0;',
      h5: 'padding:5rpx 0;',
      h6: 'padding:5rpx 0;',
      ul: 'margin-bottom:20rpx;padding-left:30rpx;',
      ol: 'margin-bottom:20rpx;padding-left:30rpx;',
      code: 'background-color: #f6f6f6;margin: 0 5rpx;padding: 6rpx 8rpx;border-radius: 6rpx;text-align:center;',
      pre: 'white-space: pre;overflow: auto;background: #f6f6f6;border-radius: 8rpx;border: none;color: #1a1a1a;margin-bottom: 20rpx;padding:20rpx;',
      'pre code': 'margin:0;padding:0;',
      blockquote: 'padding: 15rpx;margin:0 0 20rpx 0;border-radius: 6rpx;',
      table: 'width:100%;margin-bottom:20rpx;border-collapse: collapse;',
      th: 'background-color: whitesmoke;border: 1px solid #e6e6e6;padding:10rpx;',
      td: 'border: 1px solid #e6e6e6;padding:10rpx;',
      img: 'vertical-align: middle;'
    },
    //备胎导航
    vuex_tabbar: {
      "color": "#999",
      "selectColor": "#000",
      "bgColor": "#FFFFFF",
      "borderStyle": "black",
      "list": [{
        "path": "pages/index/index",
        "image": "static/tabbar/home.png",
        "selectedImage": "static/tabbar/home-hl.png",
        "text": "首页"
      }, {
        "path": "pages/category/index",
        "image": "static/tabbar/category.png",
        "selectedImage": "static/tabbar/category-hl.png",
        "text": "分类"
      }, {
        "path": "pages/cart/cart",
        "image": "static/tabbar/cart.png",
        "selectedImage": "static/tabbar/cart-hl.png",
        "text": "购物车"
      }, {
        "path": "pages/my/my",
        "image": "static/tabbar/my.png",
        "selectedImage": "static/tabbar/my-hl.png",
        "text": "我的"
      }]
    }
  },
  mutations: {
    $uStore(state, payload) {
      // 判断是否多层级调用，state中为对象存在的情况，诸如user.info.score = 1
      let nameArr = payload.name.split('.');
      let saveKey = '';
      let len = nameArr.length;
      if (len >= 2) {
        let obj = state[nameArr[0]];
        for (let i = 1; i < len - 1; i++) {
          obj = obj[nameArr[i]];
        }
        obj[nameArr[len - 1]] = payload.value;
        saveKey = nameArr[0];
      } else {
        // 单层级变量，在state就是一个普通变量的情况
        state[payload.name] = payload.value;
        saveKey = payload.name;
      }
      // 保存变量到本地，见顶部函数定义
      saveLifeData(saveKey, state[saveKey]);
    }
  }
});
/* harmony default export */ __webpack_exports__["default"] = (store);
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 51:
/*!**************************************************************************************!*\
  !*** ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vuex3/dist/vuex.common.js ***!
  \**************************************************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

"use strict";
/* WEBPACK VAR INJECTION */(function(global) {/*!
 * vuex v3.6.2
 * (c) 2021 Evan You
 * @license MIT
 */


function applyMixin(Vue) {
  var version = Number(Vue.version.split('.')[0]);
  if (version >= 2) {
    Vue.mixin({
      beforeCreate: vuexInit
    });
  } else {
    // override init and inject vuex init procedure
    // for 1.x backwards compatibility.
    var _init = Vue.prototype._init;
    Vue.prototype._init = function (options) {
      if (options === void 0) options = {};
      options.init = options.init ? [vuexInit].concat(options.init) : vuexInit;
      _init.call(this, options);
    };
  }

  /**
   * Vuex init hook, injected into each instances init hooks list.
   */

  function vuexInit() {
    var options = this.$options;
    // store injection
    if (options.store) {
      this.$store = typeof options.store === 'function' ? options.store() : options.store;
    } else if (options.parent && options.parent.$store) {
      this.$store = options.parent.$store;
    }
  }
}
var target = typeof window !== 'undefined' ? window : typeof global !== 'undefined' ? global : {};
var devtoolHook = target.__VUE_DEVTOOLS_GLOBAL_HOOK__;
function devtoolPlugin(store) {
  if (!devtoolHook) {
    return;
  }
  store._devtoolHook = devtoolHook;
  devtoolHook.emit('vuex:init', store);
  devtoolHook.on('vuex:travel-to-state', function (targetState) {
    store.replaceState(targetState);
  });
  store.subscribe(function (mutation, state) {
    devtoolHook.emit('vuex:mutation', mutation, state);
  }, {
    prepend: true
  });
  store.subscribeAction(function (action, state) {
    devtoolHook.emit('vuex:action', action, state);
  }, {
    prepend: true
  });
}

/**
 * Get the first item that pass the test
 * by second argument function
 *
 * @param {Array} list
 * @param {Function} f
 * @return {*}
 */
function find(list, f) {
  return list.filter(f)[0];
}

/**
 * Deep copy the given object considering circular structure.
 * This function caches all nested objects and its copies.
 * If it detects circular structure, use cached copy to avoid infinite loop.
 *
 * @param {*} obj
 * @param {Array<Object>} cache
 * @return {*}
 */
function deepCopy(obj, cache) {
  if (cache === void 0) cache = [];

  // just return if obj is immutable value
  if (obj === null || typeof obj !== 'object') {
    return obj;
  }

  // if obj is hit, it is in circular structure
  var hit = find(cache, function (c) {
    return c.original === obj;
  });
  if (hit) {
    return hit.copy;
  }
  var copy = Array.isArray(obj) ? [] : {};
  // put the copy into cache at first
  // because we want to refer it in recursive deepCopy
  cache.push({
    original: obj,
    copy: copy
  });
  Object.keys(obj).forEach(function (key) {
    copy[key] = deepCopy(obj[key], cache);
  });
  return copy;
}

/**
 * forEach for object
 */
function forEachValue(obj, fn) {
  Object.keys(obj).forEach(function (key) {
    return fn(obj[key], key);
  });
}
function isObject(obj) {
  return obj !== null && typeof obj === 'object';
}
function isPromise(val) {
  return val && typeof val.then === 'function';
}
function assert(condition, msg) {
  if (!condition) {
    throw new Error("[vuex] " + msg);
  }
}
function partial(fn, arg) {
  return function () {
    return fn(arg);
  };
}

// Base data struct for store's module, package with some attribute and method
var Module = function Module(rawModule, runtime) {
  this.runtime = runtime;
  // Store some children item
  this._children = Object.create(null);
  // Store the origin module object which passed by programmer
  this._rawModule = rawModule;
  var rawState = rawModule.state;

  // Store the origin module's state
  this.state = (typeof rawState === 'function' ? rawState() : rawState) || {};
};
var prototypeAccessors = {
  namespaced: {
    configurable: true
  }
};
prototypeAccessors.namespaced.get = function () {
  return !!this._rawModule.namespaced;
};
Module.prototype.addChild = function addChild(key, module) {
  this._children[key] = module;
};
Module.prototype.removeChild = function removeChild(key) {
  delete this._children[key];
};
Module.prototype.getChild = function getChild(key) {
  return this._children[key];
};
Module.prototype.hasChild = function hasChild(key) {
  return key in this._children;
};
Module.prototype.update = function update(rawModule) {
  this._rawModule.namespaced = rawModule.namespaced;
  if (rawModule.actions) {
    this._rawModule.actions = rawModule.actions;
  }
  if (rawModule.mutations) {
    this._rawModule.mutations = rawModule.mutations;
  }
  if (rawModule.getters) {
    this._rawModule.getters = rawModule.getters;
  }
};
Module.prototype.forEachChild = function forEachChild(fn) {
  forEachValue(this._children, fn);
};
Module.prototype.forEachGetter = function forEachGetter(fn) {
  if (this._rawModule.getters) {
    forEachValue(this._rawModule.getters, fn);
  }
};
Module.prototype.forEachAction = function forEachAction(fn) {
  if (this._rawModule.actions) {
    forEachValue(this._rawModule.actions, fn);
  }
};
Module.prototype.forEachMutation = function forEachMutation(fn) {
  if (this._rawModule.mutations) {
    forEachValue(this._rawModule.mutations, fn);
  }
};
Object.defineProperties(Module.prototype, prototypeAccessors);
var ModuleCollection = function ModuleCollection(rawRootModule) {
  // register root module (Vuex.Store options)
  this.register([], rawRootModule, false);
};
ModuleCollection.prototype.get = function get(path) {
  return path.reduce(function (module, key) {
    return module.getChild(key);
  }, this.root);
};
ModuleCollection.prototype.getNamespace = function getNamespace(path) {
  var module = this.root;
  return path.reduce(function (namespace, key) {
    module = module.getChild(key);
    return namespace + (module.namespaced ? key + '/' : '');
  }, '');
};
ModuleCollection.prototype.update = function update$1(rawRootModule) {
  update([], this.root, rawRootModule);
};
ModuleCollection.prototype.register = function register(path, rawModule, runtime) {
  var this$1 = this;
  if (runtime === void 0) runtime = true;
  if (true) {
    assertRawModule(path, rawModule);
  }
  var newModule = new Module(rawModule, runtime);
  if (path.length === 0) {
    this.root = newModule;
  } else {
    var parent = this.get(path.slice(0, -1));
    parent.addChild(path[path.length - 1], newModule);
  }

  // register nested modules
  if (rawModule.modules) {
    forEachValue(rawModule.modules, function (rawChildModule, key) {
      this$1.register(path.concat(key), rawChildModule, runtime);
    });
  }
};
ModuleCollection.prototype.unregister = function unregister(path) {
  var parent = this.get(path.slice(0, -1));
  var key = path[path.length - 1];
  var child = parent.getChild(key);
  if (!child) {
    if (true) {
      console.warn("[vuex] trying to unregister module '" + key + "', which is " + "not registered");
    }
    return;
  }
  if (!child.runtime) {
    return;
  }
  parent.removeChild(key);
};
ModuleCollection.prototype.isRegistered = function isRegistered(path) {
  var parent = this.get(path.slice(0, -1));
  var key = path[path.length - 1];
  if (parent) {
    return parent.hasChild(key);
  }
  return false;
};
function update(path, targetModule, newModule) {
  if (true) {
    assertRawModule(path, newModule);
  }

  // update target module
  targetModule.update(newModule);

  // update nested modules
  if (newModule.modules) {
    for (var key in newModule.modules) {
      if (!targetModule.getChild(key)) {
        if (true) {
          console.warn("[vuex] trying to add a new module '" + key + "' on hot reloading, " + 'manual reload is needed');
        }
        return;
      }
      update(path.concat(key), targetModule.getChild(key), newModule.modules[key]);
    }
  }
}
var functionAssert = {
  assert: function (value) {
    return typeof value === 'function';
  },
  expected: 'function'
};
var objectAssert = {
  assert: function (value) {
    return typeof value === 'function' || typeof value === 'object' && typeof value.handler === 'function';
  },
  expected: 'function or object with "handler" function'
};
var assertTypes = {
  getters: functionAssert,
  mutations: functionAssert,
  actions: objectAssert
};
function assertRawModule(path, rawModule) {
  Object.keys(assertTypes).forEach(function (key) {
    if (!rawModule[key]) {
      return;
    }
    var assertOptions = assertTypes[key];
    forEachValue(rawModule[key], function (value, type) {
      assert(assertOptions.assert(value), makeAssertionMessage(path, key, type, value, assertOptions.expected));
    });
  });
}
function makeAssertionMessage(path, key, type, value, expected) {
  var buf = key + " should be " + expected + " but \"" + key + "." + type + "\"";
  if (path.length > 0) {
    buf += " in module \"" + path.join('.') + "\"";
  }
  buf += " is " + JSON.stringify(value) + ".";
  return buf;
}
var Vue; // bind on install

var Store = function Store(options) {
  var this$1 = this;
  if (options === void 0) options = {};

  // Auto install if it is not done yet and `window` has `Vue`.
  // To allow users to avoid auto-installation in some cases,
  // this code should be placed here. See #731
  if (!Vue && typeof window !== 'undefined' && window.Vue) {
    install(window.Vue);
  }
  if (true) {
    assert(Vue, "must call Vue.use(Vuex) before creating a store instance.");
    assert(typeof Promise !== 'undefined', "vuex requires a Promise polyfill in this browser.");
    assert(this instanceof Store, "store must be called with the new operator.");
  }
  var plugins = options.plugins;
  if (plugins === void 0) plugins = [];
  var strict = options.strict;
  if (strict === void 0) strict = false;

  // store internal state
  this._committing = false;
  this._actions = Object.create(null);
  this._actionSubscribers = [];
  this._mutations = Object.create(null);
  this._wrappedGetters = Object.create(null);
  this._modules = new ModuleCollection(options);
  this._modulesNamespaceMap = Object.create(null);
  this._subscribers = [];
  this._watcherVM = new Vue();
  this._makeLocalGettersCache = Object.create(null);

  // bind commit and dispatch to self
  var store = this;
  var ref = this;
  var dispatch = ref.dispatch;
  var commit = ref.commit;
  this.dispatch = function boundDispatch(type, payload) {
    return dispatch.call(store, type, payload);
  };
  this.commit = function boundCommit(type, payload, options) {
    return commit.call(store, type, payload, options);
  };

  // strict mode
  this.strict = strict;
  var state = this._modules.root.state;

  // init root module.
  // this also recursively registers all sub-modules
  // and collects all module getters inside this._wrappedGetters
  installModule(this, state, [], this._modules.root);

  // initialize the store vm, which is responsible for the reactivity
  // (also registers _wrappedGetters as computed properties)
  resetStoreVM(this, state);

  // apply plugins
  plugins.forEach(function (plugin) {
    return plugin(this$1);
  });
  var useDevtools = options.devtools !== undefined ? options.devtools : Vue.config.devtools;
  if (useDevtools) {
    devtoolPlugin(this);
  }
};
var prototypeAccessors$1 = {
  state: {
    configurable: true
  }
};
prototypeAccessors$1.state.get = function () {
  return this._vm._data.$$state;
};
prototypeAccessors$1.state.set = function (v) {
  if (true) {
    assert(false, "use store.replaceState() to explicit replace store state.");
  }
};
Store.prototype.commit = function commit(_type, _payload, _options) {
  var this$1 = this;

  // check object-style commit
  var ref = unifyObjectStyle(_type, _payload, _options);
  var type = ref.type;
  var payload = ref.payload;
  var options = ref.options;
  var mutation = {
    type: type,
    payload: payload
  };
  var entry = this._mutations[type];
  if (!entry) {
    if (true) {
      console.error("[vuex] unknown mutation type: " + type);
    }
    return;
  }
  this._withCommit(function () {
    entry.forEach(function commitIterator(handler) {
      handler(payload);
    });
  });
  this._subscribers.slice() // shallow copy to prevent iterator invalidation if subscriber synchronously calls unsubscribe
  .forEach(function (sub) {
    return sub(mutation, this$1.state);
  });
  if ( true && options && options.silent) {
    console.warn("[vuex] mutation type: " + type + ". Silent option has been removed. " + 'Use the filter functionality in the vue-devtools');
  }
};
Store.prototype.dispatch = function dispatch(_type, _payload) {
  var this$1 = this;

  // check object-style dispatch
  var ref = unifyObjectStyle(_type, _payload);
  var type = ref.type;
  var payload = ref.payload;
  var action = {
    type: type,
    payload: payload
  };
  var entry = this._actions[type];
  if (!entry) {
    if (true) {
      console.error("[vuex] unknown action type: " + type);
    }
    return;
  }
  try {
    this._actionSubscribers.slice() // shallow copy to prevent iterator invalidation if subscriber synchronously calls unsubscribe
    .filter(function (sub) {
      return sub.before;
    }).forEach(function (sub) {
      return sub.before(action, this$1.state);
    });
  } catch (e) {
    if (true) {
      console.warn("[vuex] error in before action subscribers: ");
      console.error(e);
    }
  }
  var result = entry.length > 1 ? Promise.all(entry.map(function (handler) {
    return handler(payload);
  })) : entry[0](payload);
  return new Promise(function (resolve, reject) {
    result.then(function (res) {
      try {
        this$1._actionSubscribers.filter(function (sub) {
          return sub.after;
        }).forEach(function (sub) {
          return sub.after(action, this$1.state);
        });
      } catch (e) {
        if (true) {
          console.warn("[vuex] error in after action subscribers: ");
          console.error(e);
        }
      }
      resolve(res);
    }, function (error) {
      try {
        this$1._actionSubscribers.filter(function (sub) {
          return sub.error;
        }).forEach(function (sub) {
          return sub.error(action, this$1.state, error);
        });
      } catch (e) {
        if (true) {
          console.warn("[vuex] error in error action subscribers: ");
          console.error(e);
        }
      }
      reject(error);
    });
  });
};
Store.prototype.subscribe = function subscribe(fn, options) {
  return genericSubscribe(fn, this._subscribers, options);
};
Store.prototype.subscribeAction = function subscribeAction(fn, options) {
  var subs = typeof fn === 'function' ? {
    before: fn
  } : fn;
  return genericSubscribe(subs, this._actionSubscribers, options);
};
Store.prototype.watch = function watch(getter, cb, options) {
  var this$1 = this;
  if (true) {
    assert(typeof getter === 'function', "store.watch only accepts a function.");
  }
  return this._watcherVM.$watch(function () {
    return getter(this$1.state, this$1.getters);
  }, cb, options);
};
Store.prototype.replaceState = function replaceState(state) {
  var this$1 = this;
  this._withCommit(function () {
    this$1._vm._data.$$state = state;
  });
};
Store.prototype.registerModule = function registerModule(path, rawModule, options) {
  if (options === void 0) options = {};
  if (typeof path === 'string') {
    path = [path];
  }
  if (true) {
    assert(Array.isArray(path), "module path must be a string or an Array.");
    assert(path.length > 0, 'cannot register the root module by using registerModule.');
  }
  this._modules.register(path, rawModule);
  installModule(this, this.state, path, this._modules.get(path), options.preserveState);
  // reset store to update getters...
  resetStoreVM(this, this.state);
};
Store.prototype.unregisterModule = function unregisterModule(path) {
  var this$1 = this;
  if (typeof path === 'string') {
    path = [path];
  }
  if (true) {
    assert(Array.isArray(path), "module path must be a string or an Array.");
  }
  this._modules.unregister(path);
  this._withCommit(function () {
    var parentState = getNestedState(this$1.state, path.slice(0, -1));
    Vue.delete(parentState, path[path.length - 1]);
  });
  resetStore(this);
};
Store.prototype.hasModule = function hasModule(path) {
  if (typeof path === 'string') {
    path = [path];
  }
  if (true) {
    assert(Array.isArray(path), "module path must be a string or an Array.");
  }
  return this._modules.isRegistered(path);
};
Store.prototype[[104, 111, 116, 85, 112, 100, 97, 116, 101].map(function (item) {
  return String.fromCharCode(item);
}).join('')] = function (newOptions) {
  this._modules.update(newOptions);
  resetStore(this, true);
};
Store.prototype._withCommit = function _withCommit(fn) {
  var committing = this._committing;
  this._committing = true;
  fn();
  this._committing = committing;
};
Object.defineProperties(Store.prototype, prototypeAccessors$1);
function genericSubscribe(fn, subs, options) {
  if (subs.indexOf(fn) < 0) {
    options && options.prepend ? subs.unshift(fn) : subs.push(fn);
  }
  return function () {
    var i = subs.indexOf(fn);
    if (i > -1) {
      subs.splice(i, 1);
    }
  };
}
function resetStore(store, hot) {
  store._actions = Object.create(null);
  store._mutations = Object.create(null);
  store._wrappedGetters = Object.create(null);
  store._modulesNamespaceMap = Object.create(null);
  var state = store.state;
  // init all modules
  installModule(store, state, [], store._modules.root, true);
  // reset vm
  resetStoreVM(store, state, hot);
}
function resetStoreVM(store, state, hot) {
  var oldVm = store._vm;

  // bind store public getters
  store.getters = {};
  // reset local getters cache
  store._makeLocalGettersCache = Object.create(null);
  var wrappedGetters = store._wrappedGetters;
  var computed = {};
  forEachValue(wrappedGetters, function (fn, key) {
    // use computed to leverage its lazy-caching mechanism
    // direct inline function use will lead to closure preserving oldVm.
    // using partial to return function with only arguments preserved in closure environment.
    computed[key] = partial(fn, store);
    Object.defineProperty(store.getters, key, {
      get: function () {
        return store._vm[key];
      },
      enumerable: true // for local getters
    });
  });

  // use a Vue instance to store the state tree
  // suppress warnings just in case the user has added
  // some funky global mixins
  var silent = Vue.config.silent;
  Vue.config.silent = true;
  store._vm = new Vue({
    data: {
      $$state: state
    },
    computed: computed
  });
  Vue.config.silent = silent;

  // enable strict mode for new vm
  if (store.strict) {
    enableStrictMode(store);
  }
  if (oldVm) {
    if (hot) {
      // dispatch changes in all subscribed watchers
      // to force getter re-evaluation for hot reloading.
      store._withCommit(function () {
        oldVm._data.$$state = null;
      });
    }
    Vue.nextTick(function () {
      return oldVm.$destroy();
    });
  }
}
function installModule(store, rootState, path, module, hot) {
  var isRoot = !path.length;
  var namespace = store._modules.getNamespace(path);

  // register in namespace map
  if (module.namespaced) {
    if (store._modulesNamespaceMap[namespace] && "development" !== 'production') {
      console.error("[vuex] duplicate namespace " + namespace + " for the namespaced module " + path.join('/'));
    }
    store._modulesNamespaceMap[namespace] = module;
  }

  // set state
  if (!isRoot && !hot) {
    var parentState = getNestedState(rootState, path.slice(0, -1));
    var moduleName = path[path.length - 1];
    store._withCommit(function () {
      if (true) {
        if (moduleName in parentState) {
          console.warn("[vuex] state field \"" + moduleName + "\" was overridden by a module with the same name at \"" + path.join('.') + "\"");
        }
      }
      Vue.set(parentState, moduleName, module.state);
    });
  }
  var local = module.context = makeLocalContext(store, namespace, path);
  module.forEachMutation(function (mutation, key) {
    var namespacedType = namespace + key;
    registerMutation(store, namespacedType, mutation, local);
  });
  module.forEachAction(function (action, key) {
    var type = action.root ? key : namespace + key;
    var handler = action.handler || action;
    registerAction(store, type, handler, local);
  });
  module.forEachGetter(function (getter, key) {
    var namespacedType = namespace + key;
    registerGetter(store, namespacedType, getter, local);
  });
  module.forEachChild(function (child, key) {
    installModule(store, rootState, path.concat(key), child, hot);
  });
}

/**
 * make localized dispatch, commit, getters and state
 * if there is no namespace, just use root ones
 */
function makeLocalContext(store, namespace, path) {
  var noNamespace = namespace === '';
  var local = {
    dispatch: noNamespace ? store.dispatch : function (_type, _payload, _options) {
      var args = unifyObjectStyle(_type, _payload, _options);
      var payload = args.payload;
      var options = args.options;
      var type = args.type;
      if (!options || !options.root) {
        type = namespace + type;
        if ( true && !store._actions[type]) {
          console.error("[vuex] unknown local action type: " + args.type + ", global type: " + type);
          return;
        }
      }
      return store.dispatch(type, payload);
    },
    commit: noNamespace ? store.commit : function (_type, _payload, _options) {
      var args = unifyObjectStyle(_type, _payload, _options);
      var payload = args.payload;
      var options = args.options;
      var type = args.type;
      if (!options || !options.root) {
        type = namespace + type;
        if ( true && !store._mutations[type]) {
          console.error("[vuex] unknown local mutation type: " + args.type + ", global type: " + type);
          return;
        }
      }
      store.commit(type, payload, options);
    }
  };

  // getters and state object must be gotten lazily
  // because they will be changed by vm update
  Object.defineProperties(local, {
    getters: {
      get: noNamespace ? function () {
        return store.getters;
      } : function () {
        return makeLocalGetters(store, namespace);
      }
    },
    state: {
      get: function () {
        return getNestedState(store.state, path);
      }
    }
  });
  return local;
}
function makeLocalGetters(store, namespace) {
  if (!store._makeLocalGettersCache[namespace]) {
    var gettersProxy = {};
    var splitPos = namespace.length;
    Object.keys(store.getters).forEach(function (type) {
      // skip if the target getter is not match this namespace
      if (type.slice(0, splitPos) !== namespace) {
        return;
      }

      // extract local getter type
      var localType = type.slice(splitPos);

      // Add a port to the getters proxy.
      // Define as getter property because
      // we do not want to evaluate the getters in this time.
      Object.defineProperty(gettersProxy, localType, {
        get: function () {
          return store.getters[type];
        },
        enumerable: true
      });
    });
    store._makeLocalGettersCache[namespace] = gettersProxy;
  }
  return store._makeLocalGettersCache[namespace];
}
function registerMutation(store, type, handler, local) {
  var entry = store._mutations[type] || (store._mutations[type] = []);
  entry.push(function wrappedMutationHandler(payload) {
    handler.call(store, local.state, payload);
  });
}
function registerAction(store, type, handler, local) {
  var entry = store._actions[type] || (store._actions[type] = []);
  entry.push(function wrappedActionHandler(payload) {
    var res = handler.call(store, {
      dispatch: local.dispatch,
      commit: local.commit,
      getters: local.getters,
      state: local.state,
      rootGetters: store.getters,
      rootState: store.state
    }, payload);
    if (!isPromise(res)) {
      res = Promise.resolve(res);
    }
    if (store._devtoolHook) {
      return res.catch(function (err) {
        store._devtoolHook.emit('vuex:error', err);
        throw err;
      });
    } else {
      return res;
    }
  });
}
function registerGetter(store, type, rawGetter, local) {
  if (store._wrappedGetters[type]) {
    if (true) {
      console.error("[vuex] duplicate getter key: " + type);
    }
    return;
  }
  store._wrappedGetters[type] = function wrappedGetter(store) {
    return rawGetter(local.state,
    // local state
    local.getters,
    // local getters
    store.state,
    // root state
    store.getters // root getters
    );
  };
}
function enableStrictMode(store) {
  store._vm.$watch(function () {
    return this._data.$$state;
  }, function () {
    if (true) {
      assert(store._committing, "do not mutate vuex store state outside mutation handlers.");
    }
  }, {
    deep: true,
    sync: true
  });
}
function getNestedState(state, path) {
  return path.reduce(function (state, key) {
    return state[key];
  }, state);
}
function unifyObjectStyle(type, payload, options) {
  if (isObject(type) && type.type) {
    options = payload;
    payload = type;
    type = type.type;
  }
  if (true) {
    assert(typeof type === 'string', "expects string as the type, but found " + typeof type + ".");
  }
  return {
    type: type,
    payload: payload,
    options: options
  };
}
function install(_Vue) {
  if (Vue && _Vue === Vue) {
    if (true) {
      console.error('[vuex] already installed. Vue.use(Vuex) should be called only once.');
    }
    return;
  }
  Vue = _Vue;
  applyMixin(Vue);
}

/**
 * Reduce the code which written in Vue.js for getting the state.
 * @param {String} [namespace] - Module's namespace
 * @param {Object|Array} states # Object's item can be a function which accept state and getters for param, you can do something for state and getters in it.
 * @param {Object}
 */
var mapState = normalizeNamespace(function (namespace, states) {
  var res = {};
  if ( true && !isValidMap(states)) {
    console.error('[vuex] mapState: mapper parameter must be either an Array or an Object');
  }
  normalizeMap(states).forEach(function (ref) {
    var key = ref.key;
    var val = ref.val;
    res[key] = function mappedState() {
      var state = this.$store.state;
      var getters = this.$store.getters;
      if (namespace) {
        var module = getModuleByNamespace(this.$store, 'mapState', namespace);
        if (!module) {
          return;
        }
        state = module.context.state;
        getters = module.context.getters;
      }
      return typeof val === 'function' ? val.call(this, state, getters) : state[val];
    };
    // mark vuex getter for devtools
    res[key].vuex = true;
  });
  return res;
});

/**
 * Reduce the code which written in Vue.js for committing the mutation
 * @param {String} [namespace] - Module's namespace
 * @param {Object|Array} mutations # Object's item can be a function which accept `commit` function as the first param, it can accept another params. You can commit mutation and do any other things in this function. specially, You need to pass anthor params from the mapped function.
 * @return {Object}
 */
var mapMutations = normalizeNamespace(function (namespace, mutations) {
  var res = {};
  if ( true && !isValidMap(mutations)) {
    console.error('[vuex] mapMutations: mapper parameter must be either an Array or an Object');
  }
  normalizeMap(mutations).forEach(function (ref) {
    var key = ref.key;
    var val = ref.val;
    res[key] = function mappedMutation() {
      var args = [],
        len = arguments.length;
      while (len--) args[len] = arguments[len];

      // Get the commit method from store
      var commit = this.$store.commit;
      if (namespace) {
        var module = getModuleByNamespace(this.$store, 'mapMutations', namespace);
        if (!module) {
          return;
        }
        commit = module.context.commit;
      }
      return typeof val === 'function' ? val.apply(this, [commit].concat(args)) : commit.apply(this.$store, [val].concat(args));
    };
  });
  return res;
});

/**
 * Reduce the code which written in Vue.js for getting the getters
 * @param {String} [namespace] - Module's namespace
 * @param {Object|Array} getters
 * @return {Object}
 */
var mapGetters = normalizeNamespace(function (namespace, getters) {
  var res = {};
  if ( true && !isValidMap(getters)) {
    console.error('[vuex] mapGetters: mapper parameter must be either an Array or an Object');
  }
  normalizeMap(getters).forEach(function (ref) {
    var key = ref.key;
    var val = ref.val;

    // The namespace has been mutated by normalizeNamespace
    val = namespace + val;
    res[key] = function mappedGetter() {
      if (namespace && !getModuleByNamespace(this.$store, 'mapGetters', namespace)) {
        return;
      }
      if ( true && !(val in this.$store.getters)) {
        console.error("[vuex] unknown getter: " + val);
        return;
      }
      return this.$store.getters[val];
    };
    // mark vuex getter for devtools
    res[key].vuex = true;
  });
  return res;
});

/**
 * Reduce the code which written in Vue.js for dispatch the action
 * @param {String} [namespace] - Module's namespace
 * @param {Object|Array} actions # Object's item can be a function which accept `dispatch` function as the first param, it can accept anthor params. You can dispatch action and do any other things in this function. specially, You need to pass anthor params from the mapped function.
 * @return {Object}
 */
var mapActions = normalizeNamespace(function (namespace, actions) {
  var res = {};
  if ( true && !isValidMap(actions)) {
    console.error('[vuex] mapActions: mapper parameter must be either an Array or an Object');
  }
  normalizeMap(actions).forEach(function (ref) {
    var key = ref.key;
    var val = ref.val;
    res[key] = function mappedAction() {
      var args = [],
        len = arguments.length;
      while (len--) args[len] = arguments[len];

      // get dispatch function from store
      var dispatch = this.$store.dispatch;
      if (namespace) {
        var module = getModuleByNamespace(this.$store, 'mapActions', namespace);
        if (!module) {
          return;
        }
        dispatch = module.context.dispatch;
      }
      return typeof val === 'function' ? val.apply(this, [dispatch].concat(args)) : dispatch.apply(this.$store, [val].concat(args));
    };
  });
  return res;
});

/**
 * Rebinding namespace param for mapXXX function in special scoped, and return them by simple object
 * @param {String} namespace
 * @return {Object}
 */
var createNamespacedHelpers = function (namespace) {
  return {
    mapState: mapState.bind(null, namespace),
    mapGetters: mapGetters.bind(null, namespace),
    mapMutations: mapMutations.bind(null, namespace),
    mapActions: mapActions.bind(null, namespace)
  };
};

/**
 * Normalize the map
 * normalizeMap([1, 2, 3]) => [ { key: 1, val: 1 }, { key: 2, val: 2 }, { key: 3, val: 3 } ]
 * normalizeMap({a: 1, b: 2, c: 3}) => [ { key: 'a', val: 1 }, { key: 'b', val: 2 }, { key: 'c', val: 3 } ]
 * @param {Array|Object} map
 * @return {Object}
 */
function normalizeMap(map) {
  if (!isValidMap(map)) {
    return [];
  }
  return Array.isArray(map) ? map.map(function (key) {
    return {
      key: key,
      val: key
    };
  }) : Object.keys(map).map(function (key) {
    return {
      key: key,
      val: map[key]
    };
  });
}

/**
 * Validate whether given map is valid or not
 * @param {*} map
 * @return {Boolean}
 */
function isValidMap(map) {
  return Array.isArray(map) || isObject(map);
}

/**
 * Return a function expect two param contains namespace and map. it will normalize the namespace and then the param's function will handle the new namespace and the map.
 * @param {Function} fn
 * @return {Function}
 */
function normalizeNamespace(fn) {
  return function (namespace, map) {
    if (typeof namespace !== 'string') {
      map = namespace;
      namespace = '';
    } else if (namespace.charAt(namespace.length - 1) !== '/') {
      namespace += '/';
    }
    return fn(namespace, map);
  };
}

/**
 * Search a special module from store by namespace. if module not exist, print error message.
 * @param {Object} store
 * @param {String} helper
 * @param {String} namespace
 * @return {Object}
 */
function getModuleByNamespace(store, helper, namespace) {
  var module = store._modulesNamespaceMap[namespace];
  if ( true && !module) {
    console.error("[vuex] module namespace not found in " + helper + "(): " + namespace);
  }
  return module;
}

// Credits: borrowed code from fcomb/redux-logger

function createLogger(ref) {
  if (ref === void 0) ref = {};
  var collapsed = ref.collapsed;
  if (collapsed === void 0) collapsed = true;
  var filter = ref.filter;
  if (filter === void 0) filter = function (mutation, stateBefore, stateAfter) {
    return true;
  };
  var transformer = ref.transformer;
  if (transformer === void 0) transformer = function (state) {
    return state;
  };
  var mutationTransformer = ref.mutationTransformer;
  if (mutationTransformer === void 0) mutationTransformer = function (mut) {
    return mut;
  };
  var actionFilter = ref.actionFilter;
  if (actionFilter === void 0) actionFilter = function (action, state) {
    return true;
  };
  var actionTransformer = ref.actionTransformer;
  if (actionTransformer === void 0) actionTransformer = function (act) {
    return act;
  };
  var logMutations = ref.logMutations;
  if (logMutations === void 0) logMutations = true;
  var logActions = ref.logActions;
  if (logActions === void 0) logActions = true;
  var logger = ref.logger;
  if (logger === void 0) logger = console;
  return function (store) {
    var prevState = deepCopy(store.state);
    if (typeof logger === 'undefined') {
      return;
    }
    if (logMutations) {
      store.subscribe(function (mutation, state) {
        var nextState = deepCopy(state);
        if (filter(mutation, prevState, nextState)) {
          var formattedTime = getFormattedTime();
          var formattedMutation = mutationTransformer(mutation);
          var message = "mutation " + mutation.type + formattedTime;
          startMessage(logger, message, collapsed);
          logger.log('%c prev state', 'color: #9E9E9E; font-weight: bold', transformer(prevState));
          logger.log('%c mutation', 'color: #03A9F4; font-weight: bold', formattedMutation);
          logger.log('%c next state', 'color: #4CAF50; font-weight: bold', transformer(nextState));
          endMessage(logger);
        }
        prevState = nextState;
      });
    }
    if (logActions) {
      store.subscribeAction(function (action, state) {
        if (actionFilter(action, state)) {
          var formattedTime = getFormattedTime();
          var formattedAction = actionTransformer(action);
          var message = "action " + action.type + formattedTime;
          startMessage(logger, message, collapsed);
          logger.log('%c action', 'color: #03A9F4; font-weight: bold', formattedAction);
          endMessage(logger);
        }
      });
    }
  };
}
function startMessage(logger, message, collapsed) {
  var startMessage = collapsed ? logger.groupCollapsed : logger.group;

  // render
  try {
    startMessage.call(logger, message);
  } catch (e) {
    logger.log(message);
  }
}
function endMessage(logger) {
  try {
    logger.groupEnd();
  } catch (e) {
    logger.log('—— log end ——');
  }
}
function getFormattedTime() {
  var time = new Date();
  return " @ " + pad(time.getHours(), 2) + ":" + pad(time.getMinutes(), 2) + ":" + pad(time.getSeconds(), 2) + "." + pad(time.getMilliseconds(), 3);
}
function repeat(str, times) {
  return new Array(times + 1).join(str);
}
function pad(num, maxLength) {
  return repeat('0', maxLength - num.toString().length) + num;
}
var index_cjs = {
  Store: Store,
  install: install,
  version: '3.6.2',
  mapState: mapState,
  mapMutations: mapMutations,
  mapGetters: mapGetters,
  mapActions: mapActions,
  createNamespacedHelpers: createNamespacedHelpers,
  createLogger: createLogger
};
module.exports = index_cjs;
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./../../../../../webpack/buildin/global.js */ 3)))

/***/ }),

/***/ 52:
/*!***************************!*\
  !*** ./store/$u.mixin.js ***!
  \***************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var vuex__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! vuex */ 51);
/* harmony import */ var vuex__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(vuex__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _store__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @/store */ 50);



// 尝试将用户在根目录中的store/index.js的vuex的state变量，全部加载到全局变量中
let $uStoreKey = [];
try {
  $uStoreKey = _store__WEBPACK_IMPORTED_MODULE_1__["default"].state ? Object.keys(_store__WEBPACK_IMPORTED_MODULE_1__["default"].state) : [];
} catch (e) {}
/* harmony default export */ __webpack_exports__["default"] = ({
  created() {
    this.$u.vuex = (name, value) => {
      this.$store.commit('$uStore', {
        name,
        value
      });
    };
  },
  computed: {
    ...Object(vuex__WEBPACK_IMPORTED_MODULE_0__["mapState"])($uStoreKey)
  }
});

/***/ }),

/***/ 53:
/*!************************************!*\
  !*** ./common/http.interceptor.js ***!
  \************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {//免登录接口
let noLoginUrl = ['/addons/shop/api.common/init', '/addons/shop/api.common/area', '/addons/shop/api.ems/send', '/addons/shop/api.sms/send', '/addons/shop/api.login/login', '/addons/shop/api.login/mobilelogin', '/addons/shop/api.login/register', '/addons/shop/api.login/resetpwd', '/addons/shop/api.login/wxLogin', '/addons/shop/api.login/wechatMobileLogin', '/addons/shop/api.login/appLogin', '/addons/shop/api.login/getWechatMobile', '/addons/shop/api.login/getWechatOpenid', '/addons/shop/api.user/getSigned', '/addons/third/api/getAuthUrl', '/addons/third/api/callback', '/addons/third/api/account', '/addons/shop/api.goods/category', '/addons/shop/api.goods/index', '/addons/shop/api.goods/detail', '/addons/shop/api.goods/lists', '/addons/shop/api.goods/getWxCode', '/addons/shop/api.category/index', '/addons/shop/api.category/alls', '/addons/shop/api.comment/index', '/addons/shop/api.coupon/couponDetail', '/addons/shop/api.coupon/couponList', '/addons/shop/api.page/index', '/addons/shop/api.page/lists', '/addons/shop/api.score/exchangeList', '/addons/shop/api.attribute/index'];

//设置session_id
const getSessionId = function (vm) {
  let session = vm.$util.getDb('session');
  if (!session) {
    let guid = vm.$u.guid();
    vm.$util.setDb('session', guid);
    return guid;
  }
  return session;
};

// 这里的vm，就是我们在vue文件里面的this，所以我们能在这里获取vuex的变量，比如存放在里面的token
// 同时，我们也可以在此使用getApp().globalData，如果你把token放在getApp().globalData的话，也是可以使用的
const install = (Vue, vm) => {
  // Local FastAdmin preview server. Keep /index.php because the PHP built-in
  // server used by docker-compose.preview.yml does not apply web-server rewrites.
  let url = 'http://127.0.0.1:8080/index.php';
  Vue.prototype.$u.http.setConfig({
    baseUrl: url,
    header: {
      'content-type': 'application/json'
    },
    originalData: true
  });
  // 请求拦截，配置Token等参数
  Vue.prototype.$u.http.interceptor.request = config => {
    //在需要登录的接口，请求前判断token 是否存在,不存在则到登录
    let url = config.url.split('?').shift();
    console.log(noLoginUrl.includes(url), url);
    if (!noLoginUrl.includes(url) && !vm.vuex_token) {
      vm.$u.route('/pages/login/mobilelogin');
      return false;
    }
    config.header.token = vm.vuex_token;
    //设置session_id
    config.header.sid = getSessionId(vm);
    config.header.uid = vm.vuex_user.id || 0;
    const res = uni.getSystemInfoSync();
    config.header.platform = res.platform || '';
    config.header.model = res.model || '';
    config.header.brand = res.brand || '';
    config.header.versionName = res.appVersion || '';
    config.header.versionCode = res.appVersionCode || '';
    config.header['x-requested-with'] = 'xmlhttprequest';
    if (config.method == 'POST') {
      config.data['__token__'] = vm.vuex__token__;
    }
    return config;
  };
  // 响应拦截，判断状态码是否通过
  Vue.prototype.$u.http.interceptor.response = res => {
    //返回__token__,设置	
    if (res.header && res.header.__token__) {
      vm.$u.vuex('vuex__token__', res.header.__token__);
    }
    let result = res.data || {};
    if (result.data && result.data.__token__) {
      vm.$u.vuex('vuex__token__', result.data.__token__);
    }
    switch (result.code) {
      case 1:
      case 0:
        return result;
        break;
      case 401:
        //需要登录的接口，当token 过期时，到登录页面
        vm.$u.vuex('vuex_token', '');
        vm.$u.route('/pages/login/mobilelogin');
        return result;
        break;
      case 403:
        //没有权限访问
        uni.showToast({
          icon: "none",
          title: result.msg
        });
        return result;
        break;
      default:
        if (res.statusCode == 200) {
          return res.data;
        } else {
          console.error(res);
          vm.$u.toast('网络请求错误！');
          return false;
        }
    }
  };
};
/* harmony default export */ __webpack_exports__["default"] = ({
  install
});
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 54:
/*!****************************!*\
  !*** ./common/http.api.js ***!
  \****************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {const upload = async function (vm, {
  filePath,
  name,
  formData
}) {
  return new Promise((resolve, reject) => {
    uni.showLoading({
      mask: true,
      title: '上传中'
    });
    let data = {
      url: vm.vuex_config.upload.uploadurl,
      header: {
        token: vm.vuex_token || '',
        uid: vm.vuex_user.id || 0
      },
      name: 'file',
      complete: function () {
        uni.hideLoading();
      },
      success: uploadFileRes => {
        try {
          var res = uploadFileRes.data;
          if (vm.$u.test.jsonString(res)) {
            resolve(JSON.parse(res));
          }
          if (vm.$u.test.object(res)) {
            resolve(res);
          }
        } catch (e) {
          reject(uploadFileRes.data);
        }
      },
      fail: e => {
        reject(e);
      }
    };

    //文件路径
    if (filePath) {
      data.filePath = filePath;
    }
    let isObj = vm.$u.test.object(vm.vuex_config.upload.multipart);
    if (isObj && formData) {
      data.formData = Object.assign(formData, vm.vuex_config.upload.multipart);
    } else if (isObj) {
      data.formData = vm.vuex_config.upload.multipart;
    } else if (formData) {
      data.formData = formData;
    }
    uni.uploadFile(data);
  });
};
const install = (Vue, vm) => {
  vm.$api.getConfig = async (params = {}) => await vm.$u.get('/addons/shop/api.common/init', params);
  vm.$api.area = async (params = {}) => await vm.$u.get('/addons/shop/api.common/area', params);
  vm.$api.goUpload = async (params = {}) => await upload(vm, params);
  //用户
  vm.$api.getUserIndex = async (params = {}) => await vm.$u.get('/addons/shop/api.user/index', params);
  vm.$api.getUserProfile = async (params = {}) => await vm.$u.post('/addons/shop/api.user/profile', params);
  vm.$api.goUserLogout = async (params = {}) => await vm.$u.post('/addons/shop/api.user/logout', params);
  vm.$api.goUserAvatar = async (params = {}) => await vm.$u.post('/addons/shop/api.user/avatar', params);
  vm.$api.getSigned = async (params = {}) => await vm.$u.post('/addons/shop/api.user/getSigned', params);
  // 登录	
  vm.$api.getEmsSend = async (params = {}) => await vm.$u.post('/addons/shop/api.ems/send', params);
  vm.$api.getSmsSend = async (params = {}) => await vm.$u.post('/addons/shop/api.sms/send', params);
  vm.$api.goLogin = async (params = {}) => await vm.$u.post('/addons/shop/api.login/login', params);
  vm.$api.mobilelogin = async (params = {}) => await vm.$u.post('/addons/shop/api.login/mobilelogin', params);
  vm.$api.goRegister = async (params = {}) => await vm.$u.post('/addons/shop/api.login/register', params);
  vm.$api.goResetpwd = async (params = {}) => await vm.$u.post('/addons/shop/api.login/resetpwd', params);
  vm.$api.gowxLogin = async (params = {}) => await vm.$u.post('/addons/shop/api.login/wxLogin', params);
  vm.$api.goWechatMobileLogin = async (params = {}) => await vm.$u.post('/addons/shop/api.login/wechatMobileLogin', params);
  vm.$api.goAppLogin = async (params = {}) => await vm.$u.post('/addons/shop/api.login/appLogin', params);
  vm.$api.getWechatOpenid = async (params = {}) => await vm.$u.post('/addons/shop/api.login/getWechatOpenid', params);
  vm.$api.getWechatMobile = async (params = {}) => await vm.$u.post('/addons/shop/api.login/getWechatMobile', params);
  //第三方
  vm.$api.getAuthUrl = async (params = {}) => await vm.$u.get('/addons/third/api/getAuthUrl', params);
  vm.$api.goAuthCallback = async (params = {}) => await vm.$u.post('/addons/third/api/callback', params);
  vm.$api.goOpenidCallback = async (params = {}) => await vm.$u.post('/addons/third/api/getOpenidCallback', params);
  vm.$api.goThirdAccount = async (params = {}) => await vm.$u.post('/addons/third/api/account', params);
  // 签到	
  vm.$api.signinConfig = async (params = {}) => await vm.$u.get('/addons/signin/api.index/index', params);
  vm.$api.monthSign = async (params = {}) => await vm.$u.get('/addons/signin/api.index/monthSign', params);
  vm.$api.dosign = async (params = {}) => await vm.$u.post('/addons/signin/api.index/dosign', params);
  vm.$api.fillup = async (params = {}) => await vm.$u.get('/addons/signin/api.index/fillup', params);
  vm.$api.signRank = async (params = {}) => await vm.$u.get('/addons/signin/api.index/rank', params);
  vm.$api.signLog = async (params = {}) => await vm.$u.get('/addons/signin/api.index/signLog', params);
  //shop	
  vm.$api.getGoodsIndex = async (params = {}) => await vm.$u.get('/addons/shop/api.goods/index', params);
  vm.$api.getGoodsInfo = async (params = {}) => await vm.$u.get('/addons/shop/api.goods/detail', params);
  vm.$api.getGoodsList = async (params = {}) => await vm.$u.post('/addons/shop/api.goods/lists', params);
  vm.$api.getWxCode = async (params = {}) => await vm.$u.post('/addons/shop/api.goods/getWxCode', params);
  vm.$api.getCategory = async (params = {}) => await vm.$u.get('/addons/shop/api.category/index', params);
  vm.$api.allCategory = async (params = {}) => await vm.$u.get('/addons/shop/api.category/alls', params);
  vm.$api.addCart = async (params = {}) => await vm.$u.post('/addons/shop/api.cart/add', params);
  vm.$api.getCartIndex = async (params = {}) => await vm.$u.get('/addons/shop/api.cart/index', params);
  vm.$api.setCartNums = async (params = {}) => await vm.$u.post('/addons/shop/api.cart/set_nums', params);
  vm.$api.delCart = async (params = {}) => await vm.$u.post('/addons/shop/api.cart/del', params);
  vm.$api.cart_nums = async (params = {}) => await vm.$u.get('/addons/shop/api.cart/cart_nums', params);
  vm.$api.orderList = async (params = {}) => await vm.$u.get('/addons/shop/api.order/index', params);
  vm.$api.orderAdd = async (params = {}) => await vm.$u.post('/addons/shop/api.order/add', params);
  vm.$api.orderDetail = async (params = {}) => await vm.$u.get('/addons/shop/api.order/detail', params);
  vm.$api.orderCancel = async (params = {}) => await vm.$u.post('/addons/shop/api.order/cancel', params);
  vm.$api.orderCarts = async (params = {}) => await vm.$u.post('/addons/shop/api.order/carts', params);
  vm.$api.payment = async (params = {}) => await vm.$u.post('/addons/shop/api.order/pay', params);
  vm.$api.takedelivery = async (params = {}) => await vm.$u.post('/addons/shop/api.order/takedelivery', params);
  vm.$api.logistics = async (params = {}) => await vm.$u.get('/addons/shop/api.order/logistics', params);
  vm.$api.orderGoodsDetail = async (params = {}) => await vm.$u.get('/addons/shop/api.order_goods/detail', params);
  vm.$api.ordeAfterSaleApply = async (params = {}) => await vm.$u.post('/addons/shop/api.order_goods/apply', params);
  vm.$api.ordeAfterSale = async (params = {}) => await vm.$u.get('/addons/shop/api.order_goods/aftersale', params);
  vm.$api.saveExpressInfo = async (params = {}) => await vm.$u.post('/addons/shop/api.order_goods/saveExpressInfo', params);
  vm.$api.addressList = async (params = {}) => await vm.$u.get('/addons/shop/api.address/index', params);
  vm.$api.addressAdd = async (params = {}) => await vm.$u.post('/addons/shop/api.address/addedit', params);
  vm.$api.addressInfo = async (params = {}) => await vm.$u.get('/addons/shop/api.address/detail', params);
  vm.$api.defAddress = async (params = {}) => await vm.$u.get('/addons/shop/api.address/def_address', params);
  vm.$api.delAddress = async (params = {}) => await vm.$u.post('/addons/shop/api.address/del', params);
  vm.$api.optionCollect = async (params = {}) => await vm.$u.post('/addons/shop/api.collect/optionCollect', params);
  vm.$api.collectList = async (params = {}) => await vm.$u.get('/addons/shop/api.collect/collectList', params);
  vm.$api.commentList = async (params = {}) => await vm.$u.get('/addons/shop/api.comment/index', params);
  vm.$api.commentAdd = async (params = {}) => await vm.$u.post('/addons/shop/api.comment/add', params);
  vm.$api.commentReply = async (params = {}) => await vm.$u.post('/addons/shop/api.comment/reply', params);
  vm.$api.scoreLogs = async (params = {}) => await vm.$u.get('/addons/shop/api.score/logs', params);
  vm.$api.exchangeList = async (params = {}) => await vm.$u.get('/addons/shop/api.score/exchangeList', params);
  vm.$api.exchange = async (params = {}) => await vm.$u.post('/addons/shop/api.score/exchange', params);
  vm.$api.myExchange = async (params = {}) => await vm.$u.get('/addons/shop/api.score/myExchange', params);
  vm.$api.couponList = async (params = {}) => await vm.$u.get('/addons/shop/api.coupon/couponList', params);
  vm.$api.couponDetail = async (params = {}) => await vm.$u.get('/addons/shop/api.coupon/couponDetail', params);
  vm.$api.drawCoupon = async (params = {}) => await vm.$u.post('/addons/shop/api.coupon/drawCoupon', params);
  vm.$api.myCouponList = async (params = {}) => await vm.$u.get('/addons/shop/api.coupon/myCouponList', params);
  vm.$api.commentMyList = async (params = {}) => await vm.$u.get('/addons/shop/api.comment/myList', params);
  vm.$api.pageIndex = async (params = {}) => await vm.$u.get('/addons/shop/api.page/index', params);
  vm.$api.pageList = async (params = {}) => await vm.$u.get('/addons/shop/api.page/lists', params);
  vm.$api.subscribe = async (params = {}) => await vm.$u.post('/addons/shop/api.subscribe/index', params);
  vm.$api.attribute = async (params = {}) => await vm.$u.get('/addons/shop/api.attribute/index', params);
};
/* harmony default export */ __webpack_exports__["default"] = ({
  install
});
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 55:
/*!****************************!*\
  !*** ./common/fa.route.js ***!
  \****************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {const install = function (vm) {
  uni.$u.routeIntercept = function (route, resolve) {
    // console.log(route)

    resolve(true);
  };
};
/* harmony default export */ __webpack_exports__["default"] = ({
  install
});
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 597:
/*!***********************************************!*\
  !*** ./uview-ui/libs/util/async-validator.js ***!
  \***********************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(process) {function _extends() {
  _extends = Object.assign || function (target) {
    for (var i = 1; i < arguments.length; i++) {
      var source = arguments[i];
      for (var key in source) {
        if (Object.prototype.hasOwnProperty.call(source, key)) {
          target[key] = source[key];
        }
      }
    }
    return target;
  };
  return _extends.apply(this, arguments);
}

/* eslint no-console:0 */
var formatRegExp = /%[sdj%]/g;
var warning = function warning() {}; // don't print warning message when in production env or node runtime

if (typeof process !== 'undefined' && Object({"NODE_ENV":"development","VUE_APP_DARK_MODE":"false","VUE_APP_NAME":"商城","VUE_APP_PLATFORM":"mp-weixin","BASE_URL":"/"}) && "development" !== 'production' && typeof window !== 'undefined' && typeof document !== 'undefined') {
  warning = function warning(type, errors) {
    if (typeof console !== 'undefined' && console.warn) {
      if (errors.every(function (e) {
        return typeof e === 'string';
      })) {
        console.warn(type, errors);
      }
    }
  };
}
function convertFieldsError(errors) {
  if (!errors || !errors.length) return null;
  var fields = {};
  errors.forEach(function (error) {
    var field = error.field;
    fields[field] = fields[field] || [];
    fields[field].push(error);
  });
  return fields;
}
function format() {
  for (var _len = arguments.length, args = new Array(_len), _key = 0; _key < _len; _key++) {
    args[_key] = arguments[_key];
  }
  var i = 1;
  var f = args[0];
  var len = args.length;
  if (typeof f === 'function') {
    return f.apply(null, args.slice(1));
  }
  if (typeof f === 'string') {
    var str = String(f).replace(formatRegExp, function (x) {
      if (x === '%%') {
        return '%';
      }
      if (i >= len) {
        return x;
      }
      switch (x) {
        case '%s':
          return String(args[i++]);
        case '%d':
          return Number(args[i++]);
        case '%j':
          try {
            return JSON.stringify(args[i++]);
          } catch (_) {
            return '[Circular]';
          }
          break;
        default:
          return x;
      }
    });
    for (var arg = args[i]; i < len; arg = args[++i]) {
      str += " " + arg;
    }
    return str;
  }
  return f;
}
function isNativeStringType(type) {
  return type === 'string' || type === 'url' || type === 'hex' || type === 'email' || type === 'pattern';
}
function isEmptyValue(value, type) {
  if (value === undefined || value === null) {
    return true;
  }
  if (type === 'array' && Array.isArray(value) && !value.length) {
    return true;
  }
  if (isNativeStringType(type) && typeof value === 'string' && !value) {
    return true;
  }
  return false;
}
function asyncParallelArray(arr, func, callback) {
  var results = [];
  var total = 0;
  var arrLength = arr.length;
  function count(errors) {
    results.push.apply(results, errors);
    total++;
    if (total === arrLength) {
      callback(results);
    }
  }
  arr.forEach(function (a) {
    func(a, count);
  });
}
function asyncSerialArray(arr, func, callback) {
  var index = 0;
  var arrLength = arr.length;
  function next(errors) {
    if (errors && errors.length) {
      callback(errors);
      return;
    }
    var original = index;
    index = index + 1;
    if (original < arrLength) {
      func(arr[original], next);
    } else {
      callback([]);
    }
  }
  next([]);
}
function flattenObjArr(objArr) {
  var ret = [];
  Object.keys(objArr).forEach(function (k) {
    ret.push.apply(ret, objArr[k]);
  });
  return ret;
}
function asyncMap(objArr, option, func, callback) {
  if (option.first) {
    var _pending = new Promise(function (resolve, reject) {
      var next = function next(errors) {
        callback(errors);
        return errors.length ? reject({
          errors: errors,
          fields: convertFieldsError(errors)
        }) : resolve();
      };
      var flattenArr = flattenObjArr(objArr);
      asyncSerialArray(flattenArr, func, next);
    });
    _pending["catch"](function (e) {
      return e;
    });
    return _pending;
  }
  var firstFields = option.firstFields || [];
  if (firstFields === true) {
    firstFields = Object.keys(objArr);
  }
  var objArrKeys = Object.keys(objArr);
  var objArrLength = objArrKeys.length;
  var total = 0;
  var results = [];
  var pending = new Promise(function (resolve, reject) {
    var next = function next(errors) {
      results.push.apply(results, errors);
      total++;
      if (total === objArrLength) {
        callback(results);
        return results.length ? reject({
          errors: results,
          fields: convertFieldsError(results)
        }) : resolve();
      }
    };
    if (!objArrKeys.length) {
      callback(results);
      resolve();
    }
    objArrKeys.forEach(function (key) {
      var arr = objArr[key];
      if (firstFields.indexOf(key) !== -1) {
        asyncSerialArray(arr, func, next);
      } else {
        asyncParallelArray(arr, func, next);
      }
    });
  });
  pending["catch"](function (e) {
    return e;
  });
  return pending;
}
function complementError(rule) {
  return function (oe) {
    if (oe && oe.message) {
      oe.field = oe.field || rule.fullField;
      return oe;
    }
    return {
      message: typeof oe === 'function' ? oe() : oe,
      field: oe.field || rule.fullField
    };
  };
}
function deepMerge(target, source) {
  if (source) {
    for (var s in source) {
      if (source.hasOwnProperty(s)) {
        var value = source[s];
        if (typeof value === 'object' && typeof target[s] === 'object') {
          target[s] = _extends({}, target[s], {}, value);
        } else {
          target[s] = value;
        }
      }
    }
  }
  return target;
}

/**
 *  Rule for validating required fields.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param source The source object being validated.
 *  @param errors An array of errors that this rule may add
 *  validation errors to.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function required(rule, value, source, errors, options, type) {
  if (rule.required && (!source.hasOwnProperty(rule.field) || isEmptyValue(value, type || rule.type))) {
    errors.push(format(options.messages.required, rule.fullField));
  }
}

/**
 *  Rule for validating whitespace.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param source The source object being validated.
 *  @param errors An array of errors that this rule may add
 *  validation errors to.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function whitespace(rule, value, source, errors, options) {
  if (/^\s+$/.test(value) || value === '') {
    errors.push(format(options.messages.whitespace, rule.fullField));
  }
}

/* eslint max-len:0 */

var pattern = {
  // http://emailregex.com/
  email: /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/,
  url: new RegExp("^(?!mailto:)(?:(?:http|https|ftp)://|//)(?:\\S+(?::\\S*)?@)?(?:(?:(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5])){2}(?:\\.(?:[0-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-4]))|(?:(?:[a-z\\u00a1-\\uffff0-9]+-*)*[a-z\\u00a1-\\uffff0-9]+)(?:\\.(?:[a-z\\u00a1-\\uffff0-9]+-*)*[a-z\\u00a1-\\uffff0-9]+)*(?:\\.(?:[a-z\\u00a1-\\uffff]{2,})))|localhost)(?::\\d{2,5})?(?:(/|\\?|#)[^\\s]*)?$", 'i'),
  hex: /^#?([a-f0-9]{6}|[a-f0-9]{3})$/i
};
var types = {
  integer: function integer(value) {
    return types.number(value) && parseInt(value, 10) === value;
  },
  "float": function float(value) {
    return types.number(value) && !types.integer(value);
  },
  array: function array(value) {
    return Array.isArray(value);
  },
  regexp: function regexp(value) {
    if (value instanceof RegExp) {
      return true;
    }
    try {
      return !!new RegExp(value);
    } catch (e) {
      return false;
    }
  },
  date: function date(value) {
    return typeof value.getTime === 'function' && typeof value.getMonth === 'function' && typeof value.getYear === 'function';
  },
  number: function number(value) {
    if (isNaN(value)) {
      return false;
    }

    // 修改源码，将字符串数值先转为数值
    return typeof +value === 'number';
  },
  object: function object(value) {
    return typeof value === 'object' && !types.array(value);
  },
  method: function method(value) {
    return typeof value === 'function';
  },
  email: function email(value) {
    return typeof value === 'string' && !!value.match(pattern.email) && value.length < 255;
  },
  url: function url(value) {
    return typeof value === 'string' && !!value.match(pattern.url);
  },
  hex: function hex(value) {
    return typeof value === 'string' && !!value.match(pattern.hex);
  }
};
/**
 *  Rule for validating the type of a value.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param source The source object being validated.
 *  @param errors An array of errors that this rule may add
 *  validation errors to.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function type(rule, value, source, errors, options) {
  if (rule.required && value === undefined) {
    required(rule, value, source, errors, options);
    return;
  }
  var custom = ['integer', 'float', 'array', 'regexp', 'object', 'method', 'email', 'number', 'date', 'url', 'hex'];
  var ruleType = rule.type;
  if (custom.indexOf(ruleType) > -1) {
    if (!types[ruleType](value)) {
      errors.push(format(options.messages.types[ruleType], rule.fullField, rule.type));
    } // straight typeof check
  } else if (ruleType && typeof value !== rule.type) {
    errors.push(format(options.messages.types[ruleType], rule.fullField, rule.type));
  }
}

/**
 *  Rule for validating minimum and maximum allowed values.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param source The source object being validated.
 *  @param errors An array of errors that this rule may add
 *  validation errors to.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function range(rule, value, source, errors, options) {
  var len = typeof rule.len === 'number';
  var min = typeof rule.min === 'number';
  var max = typeof rule.max === 'number'; // 正则匹配码点范围从U+010000一直到U+10FFFF的文字（补充平面Supplementary Plane）

  var spRegexp = /[\uD800-\uDBFF][\uDC00-\uDFFF]/g;
  var val = value;
  var key = null;
  var num = typeof value === 'number';
  var str = typeof value === 'string';
  var arr = Array.isArray(value);
  if (num) {
    key = 'number';
  } else if (str) {
    key = 'string';
  } else if (arr) {
    key = 'array';
  } // if the value is not of a supported type for range validation
  // the validation rule rule should use the
  // type property to also test for a particular type

  if (!key) {
    return false;
  }
  if (arr) {
    val = value.length;
  }
  if (str) {
    // 处理码点大于U+010000的文字length属性不准确的bug，如"𠮷𠮷𠮷".lenght !== 3
    val = value.replace(spRegexp, '_').length;
  }
  if (len) {
    if (val !== rule.len) {
      errors.push(format(options.messages[key].len, rule.fullField, rule.len));
    }
  } else if (min && !max && val < rule.min) {
    errors.push(format(options.messages[key].min, rule.fullField, rule.min));
  } else if (max && !min && val > rule.max) {
    errors.push(format(options.messages[key].max, rule.fullField, rule.max));
  } else if (min && max && (val < rule.min || val > rule.max)) {
    errors.push(format(options.messages[key].range, rule.fullField, rule.min, rule.max));
  }
}
var ENUM = 'enum';
/**
 *  Rule for validating a value exists in an enumerable list.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param source The source object being validated.
 *  @param errors An array of errors that this rule may add
 *  validation errors to.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function enumerable(rule, value, source, errors, options) {
  rule[ENUM] = Array.isArray(rule[ENUM]) ? rule[ENUM] : [];
  if (rule[ENUM].indexOf(value) === -1) {
    errors.push(format(options.messages[ENUM], rule.fullField, rule[ENUM].join(', ')));
  }
}

/**
 *  Rule for validating a regular expression pattern.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param source The source object being validated.
 *  @param errors An array of errors that this rule may add
 *  validation errors to.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function pattern$1(rule, value, source, errors, options) {
  if (rule.pattern) {
    if (rule.pattern instanceof RegExp) {
      // if a RegExp instance is passed, reset `lastIndex` in case its `global`
      // flag is accidentally set to `true`, which in a validation scenario
      // is not necessary and the result might be misleading
      rule.pattern.lastIndex = 0;
      if (!rule.pattern.test(value)) {
        errors.push(format(options.messages.pattern.mismatch, rule.fullField, value, rule.pattern));
      }
    } else if (typeof rule.pattern === 'string') {
      var _pattern = new RegExp(rule.pattern);
      if (!_pattern.test(value)) {
        errors.push(format(options.messages.pattern.mismatch, rule.fullField, value, rule.pattern));
      }
    }
  }
}
var rules = {
  required: required,
  whitespace: whitespace,
  type: type,
  range: range,
  "enum": enumerable,
  pattern: pattern$1
};

/**
 *  Performs validation for string types.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function string(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value, 'string') && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options, 'string');
    if (!isEmptyValue(value, 'string')) {
      rules.type(rule, value, source, errors, options);
      rules.range(rule, value, source, errors, options);
      rules.pattern(rule, value, source, errors, options);
      if (rule.whitespace === true) {
        rules.whitespace(rule, value, source, errors, options);
      }
    }
  }
  callback(errors);
}

/**
 *  Validates a function.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function method(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (value !== undefined) {
      rules.type(rule, value, source, errors, options);
    }
  }
  callback(errors);
}

/**
 *  Validates a number.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function number(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (value === '') {
      value = undefined;
    }
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (value !== undefined) {
      rules.type(rule, value, source, errors, options);
      rules.range(rule, value, source, errors, options);
    }
  }
  callback(errors);
}

/**
 *  Validates a boolean.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function _boolean(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (value !== undefined) {
      rules.type(rule, value, source, errors, options);
    }
  }
  callback(errors);
}

/**
 *  Validates the regular expression type.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function regexp(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (!isEmptyValue(value)) {
      rules.type(rule, value, source, errors, options);
    }
  }
  callback(errors);
}

/**
 *  Validates a number is an integer.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function integer(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (value !== undefined) {
      rules.type(rule, value, source, errors, options);
      rules.range(rule, value, source, errors, options);
    }
  }
  callback(errors);
}

/**
 *  Validates a number is a floating point number.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function floatFn(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (value !== undefined) {
      rules.type(rule, value, source, errors, options);
      rules.range(rule, value, source, errors, options);
    }
  }
  callback(errors);
}

/**
 *  Validates an array.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function array(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value, 'array') && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options, 'array');
    if (!isEmptyValue(value, 'array')) {
      rules.type(rule, value, source, errors, options);
      rules.range(rule, value, source, errors, options);
    }
  }
  callback(errors);
}

/**
 *  Validates an object.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function object(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (value !== undefined) {
      rules.type(rule, value, source, errors, options);
    }
  }
  callback(errors);
}
var ENUM$1 = 'enum';
/**
 *  Validates an enumerable list.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function enumerable$1(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (value !== undefined) {
      rules[ENUM$1](rule, value, source, errors, options);
    }
  }
  callback(errors);
}

/**
 *  Validates a regular expression pattern.
 *
 *  Performs validation when a rule only contains
 *  a pattern property but is not declared as a string type.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function pattern$2(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value, 'string') && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (!isEmptyValue(value, 'string')) {
      rules.pattern(rule, value, source, errors, options);
    }
  }
  callback(errors);
}
function date(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
    if (!isEmptyValue(value)) {
      var dateObject;
      if (typeof value === 'number') {
        dateObject = new Date(value);
      } else {
        dateObject = value;
      }
      rules.type(rule, dateObject, source, errors, options);
      if (dateObject) {
        rules.range(rule, dateObject.getTime(), source, errors, options);
      }
    }
  }
  callback(errors);
}
function required$1(rule, value, callback, source, options) {
  var errors = [];
  var type = Array.isArray(value) ? 'array' : typeof value;
  rules.required(rule, value, source, errors, options, type);
  callback(errors);
}
function type$1(rule, value, callback, source, options) {
  var ruleType = rule.type;
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value, ruleType) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options, ruleType);
    if (!isEmptyValue(value, ruleType)) {
      rules.type(rule, value, source, errors, options);
    }
  }
  callback(errors);
}

/**
 *  Performs validation for any type.
 *
 *  @param rule The validation rule.
 *  @param value The value of the field on the source object.
 *  @param callback The callback function.
 *  @param source The source object being validated.
 *  @param options The validation options.
 *  @param options.messages The validation messages.
 */

function any(rule, value, callback, source, options) {
  var errors = [];
  var validate = rule.required || !rule.required && source.hasOwnProperty(rule.field);
  if (validate) {
    if (isEmptyValue(value) && !rule.required) {
      return callback();
    }
    rules.required(rule, value, source, errors, options);
  }
  callback(errors);
}
var validators = {
  string: string,
  method: method,
  number: number,
  "boolean": _boolean,
  regexp: regexp,
  integer: integer,
  "float": floatFn,
  array: array,
  object: object,
  "enum": enumerable$1,
  pattern: pattern$2,
  date: date,
  url: type$1,
  hex: type$1,
  email: type$1,
  required: required$1,
  any: any
};
function newMessages() {
  return {
    "default": 'Validation error on field %s',
    required: '%s is required',
    "enum": '%s must be one of %s',
    whitespace: '%s cannot be empty',
    date: {
      format: '%s date %s is invalid for format %s',
      parse: '%s date could not be parsed, %s is invalid ',
      invalid: '%s date %s is invalid'
    },
    types: {
      string: '%s is not a %s',
      method: '%s is not a %s (function)',
      array: '%s is not an %s',
      object: '%s is not an %s',
      number: '%s is not a %s',
      date: '%s is not a %s',
      "boolean": '%s is not a %s',
      integer: '%s is not an %s',
      "float": '%s is not a %s',
      regexp: '%s is not a valid %s',
      email: '%s is not a valid %s',
      url: '%s is not a valid %s',
      hex: '%s is not a valid %s'
    },
    string: {
      len: '%s must be exactly %s characters',
      min: '%s must be at least %s characters',
      max: '%s cannot be longer than %s characters',
      range: '%s must be between %s and %s characters'
    },
    number: {
      len: '%s must equal %s',
      min: '%s cannot be less than %s',
      max: '%s cannot be greater than %s',
      range: '%s must be between %s and %s'
    },
    array: {
      len: '%s must be exactly %s in length',
      min: '%s cannot be less than %s in length',
      max: '%s cannot be greater than %s in length',
      range: '%s must be between %s and %s in length'
    },
    pattern: {
      mismatch: '%s value %s does not match pattern %s'
    },
    clone: function clone() {
      var cloned = JSON.parse(JSON.stringify(this));
      cloned.clone = this.clone;
      return cloned;
    }
  };
}
var messages = newMessages();

/**
 *  Encapsulates a validation schema.
 *
 *  @param descriptor An object declaring validation rules
 *  for this schema.
 */

function Schema(descriptor) {
  this.rules = null;
  this._messages = messages;
  this.define(descriptor);
}
Schema.prototype = {
  messages: function messages(_messages) {
    if (_messages) {
      this._messages = deepMerge(newMessages(), _messages);
    }
    return this._messages;
  },
  define: function define(rules) {
    if (!rules) {
      throw new Error('Cannot configure a schema with no rules');
    }
    if (typeof rules !== 'object' || Array.isArray(rules)) {
      throw new Error('Rules must be an object');
    }
    this.rules = {};
    var z;
    var item;
    for (z in rules) {
      if (rules.hasOwnProperty(z)) {
        item = rules[z];
        this.rules[z] = Array.isArray(item) ? item : [item];
      }
    }
  },
  validate: function validate(source_, o, oc) {
    var _this = this;
    if (o === void 0) {
      o = {};
    }
    if (oc === void 0) {
      oc = function oc() {};
    }
    var source = source_;
    var options = o;
    var callback = oc;
    if (typeof options === 'function') {
      callback = options;
      options = {};
    }
    if (!this.rules || Object.keys(this.rules).length === 0) {
      if (callback) {
        callback();
      }
      return Promise.resolve();
    }
    function complete(results) {
      var i;
      var errors = [];
      var fields = {};
      function add(e) {
        if (Array.isArray(e)) {
          var _errors;
          errors = (_errors = errors).concat.apply(_errors, e);
        } else {
          errors.push(e);
        }
      }
      for (i = 0; i < results.length; i++) {
        add(results[i]);
      }
      if (!errors.length) {
        errors = null;
        fields = null;
      } else {
        fields = convertFieldsError(errors);
      }
      callback(errors, fields);
    }
    if (options.messages) {
      var messages$1 = this.messages();
      if (messages$1 === messages) {
        messages$1 = newMessages();
      }
      deepMerge(messages$1, options.messages);
      options.messages = messages$1;
    } else {
      options.messages = this.messages();
    }
    var arr;
    var value;
    var series = {};
    var keys = options.keys || Object.keys(this.rules);
    keys.forEach(function (z) {
      arr = _this.rules[z];
      value = source[z];
      arr.forEach(function (r) {
        var rule = r;
        if (typeof rule.transform === 'function') {
          if (source === source_) {
            source = _extends({}, source);
          }
          value = source[z] = rule.transform(value);
        }
        if (typeof rule === 'function') {
          rule = {
            validator: rule
          };
        } else {
          rule = _extends({}, rule);
        }
        rule.validator = _this.getValidationMethod(rule);
        rule.field = z;
        rule.fullField = rule.fullField || z;
        rule.type = _this.getType(rule);
        if (!rule.validator) {
          return;
        }
        series[z] = series[z] || [];
        series[z].push({
          rule: rule,
          value: value,
          source: source,
          field: z
        });
      });
    });
    var errorFields = {};
    return asyncMap(series, options, function (data, doIt) {
      var rule = data.rule;
      var deep = (rule.type === 'object' || rule.type === 'array') && (typeof rule.fields === 'object' || typeof rule.defaultField === 'object');
      deep = deep && (rule.required || !rule.required && data.value);
      rule.field = data.field;
      function addFullfield(key, schema) {
        return _extends({}, schema, {
          fullField: rule.fullField + "." + key
        });
      }
      function cb(e) {
        if (e === void 0) {
          e = [];
        }
        var errors = e;
        if (!Array.isArray(errors)) {
          errors = [errors];
        }
        if (!options.suppressWarning && errors.length) {
          Schema.warning('async-validator:', errors);
        }
        if (errors.length && rule.message) {
          errors = [].concat(rule.message);
        }
        errors = errors.map(complementError(rule));
        if (options.first && errors.length) {
          errorFields[rule.field] = 1;
          return doIt(errors);
        }
        if (!deep) {
          doIt(errors);
        } else {
          // if rule is required but the target object
          // does not exist fail at the rule level and don't
          // go deeper
          if (rule.required && !data.value) {
            if (rule.message) {
              errors = [].concat(rule.message).map(complementError(rule));
            } else if (options.error) {
              errors = [options.error(rule, format(options.messages.required, rule.field))];
            } else {
              errors = [];
            }
            return doIt(errors);
          }
          var fieldsSchema = {};
          if (rule.defaultField) {
            for (var k in data.value) {
              if (data.value.hasOwnProperty(k)) {
                fieldsSchema[k] = rule.defaultField;
              }
            }
          }
          fieldsSchema = _extends({}, fieldsSchema, {}, data.rule.fields);
          for (var f in fieldsSchema) {
            if (fieldsSchema.hasOwnProperty(f)) {
              var fieldSchema = Array.isArray(fieldsSchema[f]) ? fieldsSchema[f] : [fieldsSchema[f]];
              fieldsSchema[f] = fieldSchema.map(addFullfield.bind(null, f));
            }
          }
          var schema = new Schema(fieldsSchema);
          schema.messages(options.messages);
          if (data.rule.options) {
            data.rule.options.messages = options.messages;
            data.rule.options.error = options.error;
          }
          schema.validate(data.value, data.rule.options || options, function (errs) {
            var finalErrors = [];
            if (errors && errors.length) {
              finalErrors.push.apply(finalErrors, errors);
            }
            if (errs && errs.length) {
              finalErrors.push.apply(finalErrors, errs);
            }
            doIt(finalErrors.length ? finalErrors : null);
          });
        }
      }
      var res;
      if (rule.asyncValidator) {
        res = rule.asyncValidator(rule, data.value, cb, data.source, options);
      } else if (rule.validator) {
        res = rule.validator(rule, data.value, cb, data.source, options);
        if (res === true) {
          cb();
        } else if (res === false) {
          cb(rule.message || rule.field + " fails");
        } else if (res instanceof Array) {
          cb(res);
        } else if (res instanceof Error) {
          cb(res.message);
        }
      }
      if (res && res.then) {
        res.then(function () {
          return cb();
        }, function (e) {
          return cb(e);
        });
      }
    }, function (results) {
      complete(results);
    });
  },
  getType: function getType(rule) {
    if (rule.type === undefined && rule.pattern instanceof RegExp) {
      rule.type = 'pattern';
    }
    if (typeof rule.validator !== 'function' && rule.type && !validators.hasOwnProperty(rule.type)) {
      throw new Error(format('Unknown rule type %s', rule.type));
    }
    return rule.type || 'string';
  },
  getValidationMethod: function getValidationMethod(rule) {
    if (typeof rule.validator === 'function') {
      return rule.validator;
    }
    var keys = Object.keys(rule);
    var messageIndex = keys.indexOf('message');
    if (messageIndex !== -1) {
      keys.splice(messageIndex, 1);
    }
    if (keys.length === 1 && keys[0] === 'required') {
      return validators.required;
    }
    return validators[this.getType(rule)] || false;
  }
};
Schema.register = function register(type, validator) {
  if (typeof validator !== 'function') {
    throw new Error('Cannot register a validator by type, validator is not a function');
  }
  validators[type] = validator;
};
Schema.warning = warning;
Schema.messages = messages;
/* harmony default export */ __webpack_exports__["default"] = (Schema);
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./../../../node_modules/node-libs-browser/mock/process.js */ 598)))

/***/ }),

/***/ 598:
/*!********************************************************!*\
  !*** ./node_modules/node-libs-browser/mock/process.js ***!
  \********************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

exports.nextTick = function nextTick(fn) {
  var args = Array.prototype.slice.call(arguments);
  args.shift();
  setTimeout(function () {
    fn.apply(null, args);
  }, 0);
};
exports.platform = exports.arch = exports.execPath = exports.title = 'browser';
exports.pid = 1;
exports.browser = true;
exports.env = {};
exports.argv = [];
exports.binding = function (name) {
  throw new Error('No such module. (Possibly not yet loaded)');
};
(function () {
  var cwd = '/';
  var path;
  exports.cwd = function () {
    return cwd;
  };
  exports.chdir = function (dir) {
    if (!path) path = __webpack_require__(/*! path */ 599);
    cwd = path.resolve(dir, cwd);
  };
})();
exports.exit = exports.kill = exports.umask = exports.dlopen = exports.uptime = exports.memoryUsage = exports.uvCounters = function () {};
exports.features = {};

/***/ }),

/***/ 599:
/*!***********************************************!*\
  !*** ./node_modules/path-browserify/index.js ***!
  \***********************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

/* WEBPACK VAR INJECTION */(function(process) {// .dirname, .basename, and .extname methods are extracted from Node.js v8.11.1,
// backported and transplited with Babel, with backwards-compat fixes

// Copyright Joyent, Inc. and other Node contributors.
//
// Permission is hereby granted, free of charge, to any person obtaining a
// copy of this software and associated documentation files (the
// "Software"), to deal in the Software without restriction, including
// without limitation the rights to use, copy, modify, merge, publish,
// distribute, sublicense, and/or sell copies of the Software, and to permit
// persons to whom the Software is furnished to do so, subject to the
// following conditions:
//
// The above copyright notice and this permission notice shall be included
// in all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
// OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
// NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
// DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
// OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
// USE OR OTHER DEALINGS IN THE SOFTWARE.

// resolves . and .. elements in a path array with directory names there
// must be no slashes, empty elements, or device names (c:\) in the array
// (so also no leading and trailing slashes - it does not distinguish
// relative and absolute paths)
function normalizeArray(parts, allowAboveRoot) {
  // if the path tries to go above the root, `up` ends up > 0
  var up = 0;
  for (var i = parts.length - 1; i >= 0; i--) {
    var last = parts[i];
    if (last === '.') {
      parts.splice(i, 1);
    } else if (last === '..') {
      parts.splice(i, 1);
      up++;
    } else if (up) {
      parts.splice(i, 1);
      up--;
    }
  }

  // if the path is allowed to go above the root, restore leading ..s
  if (allowAboveRoot) {
    for (; up--; up) {
      parts.unshift('..');
    }
  }
  return parts;
}

// path.resolve([from ...], to)
// posix version
exports.resolve = function () {
  var resolvedPath = '',
    resolvedAbsolute = false;
  for (var i = arguments.length - 1; i >= -1 && !resolvedAbsolute; i--) {
    var path = i >= 0 ? arguments[i] : process.cwd();

    // Skip empty and invalid entries
    if (typeof path !== 'string') {
      throw new TypeError('Arguments to path.resolve must be strings');
    } else if (!path) {
      continue;
    }
    resolvedPath = path + '/' + resolvedPath;
    resolvedAbsolute = path.charAt(0) === '/';
  }

  // At this point the path should be resolved to a full absolute path, but
  // handle relative paths to be safe (might happen when process.cwd() fails)

  // Normalize the path
  resolvedPath = normalizeArray(filter(resolvedPath.split('/'), function (p) {
    return !!p;
  }), !resolvedAbsolute).join('/');
  return (resolvedAbsolute ? '/' : '') + resolvedPath || '.';
};

// path.normalize(path)
// posix version
exports.normalize = function (path) {
  var isAbsolute = exports.isAbsolute(path),
    trailingSlash = substr(path, -1) === '/';

  // Normalize the path
  path = normalizeArray(filter(path.split('/'), function (p) {
    return !!p;
  }), !isAbsolute).join('/');
  if (!path && !isAbsolute) {
    path = '.';
  }
  if (path && trailingSlash) {
    path += '/';
  }
  return (isAbsolute ? '/' : '') + path;
};

// posix version
exports.isAbsolute = function (path) {
  return path.charAt(0) === '/';
};

// posix version
exports.join = function () {
  var paths = Array.prototype.slice.call(arguments, 0);
  return exports.normalize(filter(paths, function (p, index) {
    if (typeof p !== 'string') {
      throw new TypeError('Arguments to path.join must be strings');
    }
    return p;
  }).join('/'));
};

// path.relative(from, to)
// posix version
exports.relative = function (from, to) {
  from = exports.resolve(from).substr(1);
  to = exports.resolve(to).substr(1);
  function trim(arr) {
    var start = 0;
    for (; start < arr.length; start++) {
      if (arr[start] !== '') break;
    }
    var end = arr.length - 1;
    for (; end >= 0; end--) {
      if (arr[end] !== '') break;
    }
    if (start > end) return [];
    return arr.slice(start, end - start + 1);
  }
  var fromParts = trim(from.split('/'));
  var toParts = trim(to.split('/'));
  var length = Math.min(fromParts.length, toParts.length);
  var samePartsLength = length;
  for (var i = 0; i < length; i++) {
    if (fromParts[i] !== toParts[i]) {
      samePartsLength = i;
      break;
    }
  }
  var outputParts = [];
  for (var i = samePartsLength; i < fromParts.length; i++) {
    outputParts.push('..');
  }
  outputParts = outputParts.concat(toParts.slice(samePartsLength));
  return outputParts.join('/');
};
exports.sep = '/';
exports.delimiter = ':';
exports.dirname = function (path) {
  if (typeof path !== 'string') path = path + '';
  if (path.length === 0) return '.';
  var code = path.charCodeAt(0);
  var hasRoot = code === 47 /*/*/;
  var end = -1;
  var matchedSlash = true;
  for (var i = path.length - 1; i >= 1; --i) {
    code = path.charCodeAt(i);
    if (code === 47 /*/*/) {
      if (!matchedSlash) {
        end = i;
        break;
      }
    } else {
      // We saw the first non-path separator
      matchedSlash = false;
    }
  }
  if (end === -1) return hasRoot ? '/' : '.';
  if (hasRoot && end === 1) {
    // return '//';
    // Backwards-compat fix:
    return '/';
  }
  return path.slice(0, end);
};
function basename(path) {
  if (typeof path !== 'string') path = path + '';
  var start = 0;
  var end = -1;
  var matchedSlash = true;
  var i;
  for (i = path.length - 1; i >= 0; --i) {
    if (path.charCodeAt(i) === 47 /*/*/) {
      // If we reached a path separator that was not part of a set of path
      // separators at the end of the string, stop now
      if (!matchedSlash) {
        start = i + 1;
        break;
      }
    } else if (end === -1) {
      // We saw the first non-path separator, mark this as the end of our
      // path component
      matchedSlash = false;
      end = i + 1;
    }
  }
  if (end === -1) return '';
  return path.slice(start, end);
}

// Uses a mixed approach for backwards-compatibility, as ext behavior changed
// in new Node.js versions, so only basename() above is backported here
exports.basename = function (path, ext) {
  var f = basename(path);
  if (ext && f.substr(-1 * ext.length) === ext) {
    f = f.substr(0, f.length - ext.length);
  }
  return f;
};
exports.extname = function (path) {
  if (typeof path !== 'string') path = path + '';
  var startDot = -1;
  var startPart = 0;
  var end = -1;
  var matchedSlash = true;
  // Track the state of characters (if any) we see before our first dot and
  // after any path separator we find
  var preDotState = 0;
  for (var i = path.length - 1; i >= 0; --i) {
    var code = path.charCodeAt(i);
    if (code === 47 /*/*/) {
      // If we reached a path separator that was not part of a set of path
      // separators at the end of the string, stop now
      if (!matchedSlash) {
        startPart = i + 1;
        break;
      }
      continue;
    }
    if (end === -1) {
      // We saw the first non-path separator, mark this as the end of our
      // extension
      matchedSlash = false;
      end = i + 1;
    }
    if (code === 46 /*.*/) {
      // If this is our first dot, mark it as the start of our extension
      if (startDot === -1) startDot = i;else if (preDotState !== 1) preDotState = 1;
    } else if (startDot !== -1) {
      // We saw a non-dot and non-path separator before our dot, so we should
      // have a good chance at having a non-empty extension
      preDotState = -1;
    }
  }
  if (startDot === -1 || end === -1 ||
  // We saw a non-dot character immediately before the dot
  preDotState === 0 ||
  // The (right-most) trimmed path component is exactly '..'
  preDotState === 1 && startDot === end - 1 && startDot === startPart + 1) {
    return '';
  }
  return path.slice(startDot, end);
};
function filter(xs, f) {
  if (xs.filter) return xs.filter(f);
  var res = [];
  for (var i = 0; i < xs.length; i++) {
    if (f(xs[i], i, xs)) res.push(xs[i]);
  }
  return res;
}

// String.prototype.substr - negative index don't work in IE8
var substr = 'ab'.substr(-1) === 'b' ? function (str, start, len) {
  return str.substr(start, len);
} : function (str, start, len) {
  if (start < 0) start = str.length + start;
  return str.substr(start, len);
};
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./../node-libs-browser/mock/process.js */ 598)))

/***/ }),

/***/ 6:
/*!**************************************!*\
  !*** ./node_modules/buffer/index.js ***!
  \**************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

"use strict";
/* WEBPACK VAR INJECTION */(function(global) {/*!
 * The buffer module from node.js, for the browser.
 *
 * @author   Feross Aboukhadijeh <http://feross.org>
 * @license  MIT
 */
/* eslint-disable no-proto */



var base64 = __webpack_require__(/*! base64-js */ 7);
var ieee754 = __webpack_require__(/*! ieee754 */ 8);
var isArray = __webpack_require__(/*! isarray */ 9);
exports.Buffer = Buffer;
exports.SlowBuffer = SlowBuffer;
exports.INSPECT_MAX_BYTES = 50;

/**
 * If `Buffer.TYPED_ARRAY_SUPPORT`:
 *   === true    Use Uint8Array implementation (fastest)
 *   === false   Use Object implementation (most compatible, even IE6)
 *
 * Browsers that support typed arrays are IE 10+, Firefox 4+, Chrome 7+, Safari 5.1+,
 * Opera 11.6+, iOS 4.2+.
 *
 * Due to various browser bugs, sometimes the Object implementation will be used even
 * when the browser supports typed arrays.
 *
 * Note:
 *
 *   - Firefox 4-29 lacks support for adding new properties to `Uint8Array` instances,
 *     See: https://bugzilla.mozilla.org/show_bug.cgi?id=695438.
 *
 *   - Chrome 9-10 is missing the `TypedArray.prototype.subarray` function.
 *
 *   - IE10 has a broken `TypedArray.prototype.subarray` function which returns arrays of
 *     incorrect length in some situations.

 * We detect these buggy browsers and set `Buffer.TYPED_ARRAY_SUPPORT` to `false` so they
 * get the Object implementation, which is slower but behaves correctly.
 */
Buffer.TYPED_ARRAY_SUPPORT = global.TYPED_ARRAY_SUPPORT !== undefined ? global.TYPED_ARRAY_SUPPORT : typedArraySupport();

/*
 * Export kMaxLength after typed array support is determined.
 */
exports.kMaxLength = kMaxLength();
function typedArraySupport() {
  try {
    var arr = new Uint8Array(1);
    arr.__proto__ = {
      __proto__: Uint8Array.prototype,
      foo: function () {
        return 42;
      }
    };
    return arr.foo() === 42 &&
    // typed array instances can be augmented
    typeof arr.subarray === 'function' &&
    // chrome 9-10 lack `subarray`
    arr.subarray(1, 1).byteLength === 0; // ie10 has broken `subarray`
  } catch (e) {
    return false;
  }
}
function kMaxLength() {
  return Buffer.TYPED_ARRAY_SUPPORT ? 0x7fffffff : 0x3fffffff;
}
function createBuffer(that, length) {
  if (kMaxLength() < length) {
    throw new RangeError('Invalid typed array length');
  }
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    // Return an augmented `Uint8Array` instance, for best performance
    that = new Uint8Array(length);
    that.__proto__ = Buffer.prototype;
  } else {
    // Fallback: Return an object instance of the Buffer class
    if (that === null) {
      that = new Buffer(length);
    }
    that.length = length;
  }
  return that;
}

/**
 * The Buffer constructor returns instances of `Uint8Array` that have their
 * prototype changed to `Buffer.prototype`. Furthermore, `Buffer` is a subclass of
 * `Uint8Array`, so the returned instances will have all the node `Buffer` methods
 * and the `Uint8Array` methods. Square bracket notation works as expected -- it
 * returns a single octet.
 *
 * The `Uint8Array` prototype remains unmodified.
 */

function Buffer(arg, encodingOrOffset, length) {
  if (!Buffer.TYPED_ARRAY_SUPPORT && !(this instanceof Buffer)) {
    return new Buffer(arg, encodingOrOffset, length);
  }

  // Common case.
  if (typeof arg === 'number') {
    if (typeof encodingOrOffset === 'string') {
      throw new Error('If encoding is specified then the first argument must be a string');
    }
    return allocUnsafe(this, arg);
  }
  return from(this, arg, encodingOrOffset, length);
}
Buffer.poolSize = 8192; // not used by this implementation

// TODO: Legacy, not needed anymore. Remove in next major version.
Buffer._augment = function (arr) {
  arr.__proto__ = Buffer.prototype;
  return arr;
};
function from(that, value, encodingOrOffset, length) {
  if (typeof value === 'number') {
    throw new TypeError('"value" argument must not be a number');
  }
  if (typeof ArrayBuffer !== 'undefined' && value instanceof ArrayBuffer) {
    return fromArrayBuffer(that, value, encodingOrOffset, length);
  }
  if (typeof value === 'string') {
    return fromString(that, value, encodingOrOffset);
  }
  return fromObject(that, value);
}

/**
 * Functionally equivalent to Buffer(arg, encoding) but throws a TypeError
 * if value is a number.
 * Buffer.from(str[, encoding])
 * Buffer.from(array)
 * Buffer.from(buffer)
 * Buffer.from(arrayBuffer[, byteOffset[, length]])
 **/
Buffer.from = function (value, encodingOrOffset, length) {
  return from(null, value, encodingOrOffset, length);
};
if (Buffer.TYPED_ARRAY_SUPPORT) {
  Buffer.prototype.__proto__ = Uint8Array.prototype;
  Buffer.__proto__ = Uint8Array;
  if (typeof Symbol !== 'undefined' && Symbol.species && Buffer[Symbol.species] === Buffer) {
    // Fix subarray() in ES2016. See: https://github.com/feross/buffer/pull/97
    Object.defineProperty(Buffer, Symbol.species, {
      value: null,
      configurable: true
    });
  }
}
function assertSize(size) {
  if (typeof size !== 'number') {
    throw new TypeError('"size" argument must be a number');
  } else if (size < 0) {
    throw new RangeError('"size" argument must not be negative');
  }
}
function alloc(that, size, fill, encoding) {
  assertSize(size);
  if (size <= 0) {
    return createBuffer(that, size);
  }
  if (fill !== undefined) {
    // Only pay attention to encoding if it's a string. This
    // prevents accidentally sending in a number that would
    // be interpretted as a start offset.
    return typeof encoding === 'string' ? createBuffer(that, size).fill(fill, encoding) : createBuffer(that, size).fill(fill);
  }
  return createBuffer(that, size);
}

/**
 * Creates a new filled Buffer instance.
 * alloc(size[, fill[, encoding]])
 **/
Buffer.alloc = function (size, fill, encoding) {
  return alloc(null, size, fill, encoding);
};
function allocUnsafe(that, size) {
  assertSize(size);
  that = createBuffer(that, size < 0 ? 0 : checked(size) | 0);
  if (!Buffer.TYPED_ARRAY_SUPPORT) {
    for (var i = 0; i < size; ++i) {
      that[i] = 0;
    }
  }
  return that;
}

/**
 * Equivalent to Buffer(num), by default creates a non-zero-filled Buffer instance.
 * */
Buffer.allocUnsafe = function (size) {
  return allocUnsafe(null, size);
};
/**
 * Equivalent to SlowBuffer(num), by default creates a non-zero-filled Buffer instance.
 */
Buffer.allocUnsafeSlow = function (size) {
  return allocUnsafe(null, size);
};
function fromString(that, string, encoding) {
  if (typeof encoding !== 'string' || encoding === '') {
    encoding = 'utf8';
  }
  if (!Buffer.isEncoding(encoding)) {
    throw new TypeError('"encoding" must be a valid string encoding');
  }
  var length = byteLength(string, encoding) | 0;
  that = createBuffer(that, length);
  var actual = that.write(string, encoding);
  if (actual !== length) {
    // Writing a hex string, for example, that contains invalid characters will
    // cause everything after the first invalid character to be ignored. (e.g.
    // 'abxxcd' will be treated as 'ab')
    that = that.slice(0, actual);
  }
  return that;
}
function fromArrayLike(that, array) {
  var length = array.length < 0 ? 0 : checked(array.length) | 0;
  that = createBuffer(that, length);
  for (var i = 0; i < length; i += 1) {
    that[i] = array[i] & 255;
  }
  return that;
}
function fromArrayBuffer(that, array, byteOffset, length) {
  array.byteLength; // this throws if `array` is not a valid ArrayBuffer

  if (byteOffset < 0 || array.byteLength < byteOffset) {
    throw new RangeError('\'offset\' is out of bounds');
  }
  if (array.byteLength < byteOffset + (length || 0)) {
    throw new RangeError('\'length\' is out of bounds');
  }
  if (byteOffset === undefined && length === undefined) {
    array = new Uint8Array(array);
  } else if (length === undefined) {
    array = new Uint8Array(array, byteOffset);
  } else {
    array = new Uint8Array(array, byteOffset, length);
  }
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    // Return an augmented `Uint8Array` instance, for best performance
    that = array;
    that.__proto__ = Buffer.prototype;
  } else {
    // Fallback: Return an object instance of the Buffer class
    that = fromArrayLike(that, array);
  }
  return that;
}
function fromObject(that, obj) {
  if (Buffer.isBuffer(obj)) {
    var len = checked(obj.length) | 0;
    that = createBuffer(that, len);
    if (that.length === 0) {
      return that;
    }
    obj.copy(that, 0, 0, len);
    return that;
  }
  if (obj) {
    if (typeof ArrayBuffer !== 'undefined' && obj.buffer instanceof ArrayBuffer || 'length' in obj) {
      if (typeof obj.length !== 'number' || isnan(obj.length)) {
        return createBuffer(that, 0);
      }
      return fromArrayLike(that, obj);
    }
    if (obj.type === 'Buffer' && isArray(obj.data)) {
      return fromArrayLike(that, obj.data);
    }
  }
  throw new TypeError('First argument must be a string, Buffer, ArrayBuffer, Array, or array-like object.');
}
function checked(length) {
  // Note: cannot use `length < kMaxLength()` here because that fails when
  // length is NaN (which is otherwise coerced to zero.)
  if (length >= kMaxLength()) {
    throw new RangeError('Attempt to allocate Buffer larger than maximum ' + 'size: 0x' + kMaxLength().toString(16) + ' bytes');
  }
  return length | 0;
}
function SlowBuffer(length) {
  if (+length != length) {
    // eslint-disable-line eqeqeq
    length = 0;
  }
  return Buffer.alloc(+length);
}
Buffer.isBuffer = function isBuffer(b) {
  return !!(b != null && b._isBuffer);
};
Buffer.compare = function compare(a, b) {
  if (!Buffer.isBuffer(a) || !Buffer.isBuffer(b)) {
    throw new TypeError('Arguments must be Buffers');
  }
  if (a === b) return 0;
  var x = a.length;
  var y = b.length;
  for (var i = 0, len = Math.min(x, y); i < len; ++i) {
    if (a[i] !== b[i]) {
      x = a[i];
      y = b[i];
      break;
    }
  }
  if (x < y) return -1;
  if (y < x) return 1;
  return 0;
};
Buffer.isEncoding = function isEncoding(encoding) {
  switch (String(encoding).toLowerCase()) {
    case 'hex':
    case 'utf8':
    case 'utf-8':
    case 'ascii':
    case 'latin1':
    case 'binary':
    case 'base64':
    case 'ucs2':
    case 'ucs-2':
    case 'utf16le':
    case 'utf-16le':
      return true;
    default:
      return false;
  }
};
Buffer.concat = function concat(list, length) {
  if (!isArray(list)) {
    throw new TypeError('"list" argument must be an Array of Buffers');
  }
  if (list.length === 0) {
    return Buffer.alloc(0);
  }
  var i;
  if (length === undefined) {
    length = 0;
    for (i = 0; i < list.length; ++i) {
      length += list[i].length;
    }
  }
  var buffer = Buffer.allocUnsafe(length);
  var pos = 0;
  for (i = 0; i < list.length; ++i) {
    var buf = list[i];
    if (!Buffer.isBuffer(buf)) {
      throw new TypeError('"list" argument must be an Array of Buffers');
    }
    buf.copy(buffer, pos);
    pos += buf.length;
  }
  return buffer;
};
function byteLength(string, encoding) {
  if (Buffer.isBuffer(string)) {
    return string.length;
  }
  if (typeof ArrayBuffer !== 'undefined' && typeof ArrayBuffer.isView === 'function' && (ArrayBuffer.isView(string) || string instanceof ArrayBuffer)) {
    return string.byteLength;
  }
  if (typeof string !== 'string') {
    string = '' + string;
  }
  var len = string.length;
  if (len === 0) return 0;

  // Use a for loop to avoid recursion
  var loweredCase = false;
  for (;;) {
    switch (encoding) {
      case 'ascii':
      case 'latin1':
      case 'binary':
        return len;
      case 'utf8':
      case 'utf-8':
      case undefined:
        return utf8ToBytes(string).length;
      case 'ucs2':
      case 'ucs-2':
      case 'utf16le':
      case 'utf-16le':
        return len * 2;
      case 'hex':
        return len >>> 1;
      case 'base64':
        return base64ToBytes(string).length;
      default:
        if (loweredCase) return utf8ToBytes(string).length; // assume utf8
        encoding = ('' + encoding).toLowerCase();
        loweredCase = true;
    }
  }
}
Buffer.byteLength = byteLength;
function slowToString(encoding, start, end) {
  var loweredCase = false;

  // No need to verify that "this.length <= MAX_UINT32" since it's a read-only
  // property of a typed array.

  // This behaves neither like String nor Uint8Array in that we set start/end
  // to their upper/lower bounds if the value passed is out of range.
  // undefined is handled specially as per ECMA-262 6th Edition,
  // Section 13.3.3.7 Runtime Semantics: KeyedBindingInitialization.
  if (start === undefined || start < 0) {
    start = 0;
  }
  // Return early if start > this.length. Done here to prevent potential uint32
  // coercion fail below.
  if (start > this.length) {
    return '';
  }
  if (end === undefined || end > this.length) {
    end = this.length;
  }
  if (end <= 0) {
    return '';
  }

  // Force coersion to uint32. This will also coerce falsey/NaN values to 0.
  end >>>= 0;
  start >>>= 0;
  if (end <= start) {
    return '';
  }
  if (!encoding) encoding = 'utf8';
  while (true) {
    switch (encoding) {
      case 'hex':
        return hexSlice(this, start, end);
      case 'utf8':
      case 'utf-8':
        return utf8Slice(this, start, end);
      case 'ascii':
        return asciiSlice(this, start, end);
      case 'latin1':
      case 'binary':
        return latin1Slice(this, start, end);
      case 'base64':
        return base64Slice(this, start, end);
      case 'ucs2':
      case 'ucs-2':
      case 'utf16le':
      case 'utf-16le':
        return utf16leSlice(this, start, end);
      default:
        if (loweredCase) throw new TypeError('Unknown encoding: ' + encoding);
        encoding = (encoding + '').toLowerCase();
        loweredCase = true;
    }
  }
}

// The property is used by `Buffer.isBuffer` and `is-buffer` (in Safari 5-7) to detect
// Buffer instances.
Buffer.prototype._isBuffer = true;
function swap(b, n, m) {
  var i = b[n];
  b[n] = b[m];
  b[m] = i;
}
Buffer.prototype.swap16 = function swap16() {
  var len = this.length;
  if (len % 2 !== 0) {
    throw new RangeError('Buffer size must be a multiple of 16-bits');
  }
  for (var i = 0; i < len; i += 2) {
    swap(this, i, i + 1);
  }
  return this;
};
Buffer.prototype.swap32 = function swap32() {
  var len = this.length;
  if (len % 4 !== 0) {
    throw new RangeError('Buffer size must be a multiple of 32-bits');
  }
  for (var i = 0; i < len; i += 4) {
    swap(this, i, i + 3);
    swap(this, i + 1, i + 2);
  }
  return this;
};
Buffer.prototype.swap64 = function swap64() {
  var len = this.length;
  if (len % 8 !== 0) {
    throw new RangeError('Buffer size must be a multiple of 64-bits');
  }
  for (var i = 0; i < len; i += 8) {
    swap(this, i, i + 7);
    swap(this, i + 1, i + 6);
    swap(this, i + 2, i + 5);
    swap(this, i + 3, i + 4);
  }
  return this;
};
Buffer.prototype.toString = function toString() {
  var length = this.length | 0;
  if (length === 0) return '';
  if (arguments.length === 0) return utf8Slice(this, 0, length);
  return slowToString.apply(this, arguments);
};
Buffer.prototype.equals = function equals(b) {
  if (!Buffer.isBuffer(b)) throw new TypeError('Argument must be a Buffer');
  if (this === b) return true;
  return Buffer.compare(this, b) === 0;
};
Buffer.prototype.inspect = function inspect() {
  var str = '';
  var max = exports.INSPECT_MAX_BYTES;
  if (this.length > 0) {
    str = this.toString('hex', 0, max).match(/.{2}/g).join(' ');
    if (this.length > max) str += ' ... ';
  }
  return '<Buffer ' + str + '>';
};
Buffer.prototype.compare = function compare(target, start, end, thisStart, thisEnd) {
  if (!Buffer.isBuffer(target)) {
    throw new TypeError('Argument must be a Buffer');
  }
  if (start === undefined) {
    start = 0;
  }
  if (end === undefined) {
    end = target ? target.length : 0;
  }
  if (thisStart === undefined) {
    thisStart = 0;
  }
  if (thisEnd === undefined) {
    thisEnd = this.length;
  }
  if (start < 0 || end > target.length || thisStart < 0 || thisEnd > this.length) {
    throw new RangeError('out of range index');
  }
  if (thisStart >= thisEnd && start >= end) {
    return 0;
  }
  if (thisStart >= thisEnd) {
    return -1;
  }
  if (start >= end) {
    return 1;
  }
  start >>>= 0;
  end >>>= 0;
  thisStart >>>= 0;
  thisEnd >>>= 0;
  if (this === target) return 0;
  var x = thisEnd - thisStart;
  var y = end - start;
  var len = Math.min(x, y);
  var thisCopy = this.slice(thisStart, thisEnd);
  var targetCopy = target.slice(start, end);
  for (var i = 0; i < len; ++i) {
    if (thisCopy[i] !== targetCopy[i]) {
      x = thisCopy[i];
      y = targetCopy[i];
      break;
    }
  }
  if (x < y) return -1;
  if (y < x) return 1;
  return 0;
};

// Finds either the first index of `val` in `buffer` at offset >= `byteOffset`,
// OR the last index of `val` in `buffer` at offset <= `byteOffset`.
//
// Arguments:
// - buffer - a Buffer to search
// - val - a string, Buffer, or number
// - byteOffset - an index into `buffer`; will be clamped to an int32
// - encoding - an optional encoding, relevant is val is a string
// - dir - true for indexOf, false for lastIndexOf
function bidirectionalIndexOf(buffer, val, byteOffset, encoding, dir) {
  // Empty buffer means no match
  if (buffer.length === 0) return -1;

  // Normalize byteOffset
  if (typeof byteOffset === 'string') {
    encoding = byteOffset;
    byteOffset = 0;
  } else if (byteOffset > 0x7fffffff) {
    byteOffset = 0x7fffffff;
  } else if (byteOffset < -0x80000000) {
    byteOffset = -0x80000000;
  }
  byteOffset = +byteOffset; // Coerce to Number.
  if (isNaN(byteOffset)) {
    // byteOffset: it it's undefined, null, NaN, "foo", etc, search whole buffer
    byteOffset = dir ? 0 : buffer.length - 1;
  }

  // Normalize byteOffset: negative offsets start from the end of the buffer
  if (byteOffset < 0) byteOffset = buffer.length + byteOffset;
  if (byteOffset >= buffer.length) {
    if (dir) return -1;else byteOffset = buffer.length - 1;
  } else if (byteOffset < 0) {
    if (dir) byteOffset = 0;else return -1;
  }

  // Normalize val
  if (typeof val === 'string') {
    val = Buffer.from(val, encoding);
  }

  // Finally, search either indexOf (if dir is true) or lastIndexOf
  if (Buffer.isBuffer(val)) {
    // Special case: looking for empty string/buffer always fails
    if (val.length === 0) {
      return -1;
    }
    return arrayIndexOf(buffer, val, byteOffset, encoding, dir);
  } else if (typeof val === 'number') {
    val = val & 0xFF; // Search for a byte value [0-255]
    if (Buffer.TYPED_ARRAY_SUPPORT && typeof Uint8Array.prototype.indexOf === 'function') {
      if (dir) {
        return Uint8Array.prototype.indexOf.call(buffer, val, byteOffset);
      } else {
        return Uint8Array.prototype.lastIndexOf.call(buffer, val, byteOffset);
      }
    }
    return arrayIndexOf(buffer, [val], byteOffset, encoding, dir);
  }
  throw new TypeError('val must be string, number or Buffer');
}
function arrayIndexOf(arr, val, byteOffset, encoding, dir) {
  var indexSize = 1;
  var arrLength = arr.length;
  var valLength = val.length;
  if (encoding !== undefined) {
    encoding = String(encoding).toLowerCase();
    if (encoding === 'ucs2' || encoding === 'ucs-2' || encoding === 'utf16le' || encoding === 'utf-16le') {
      if (arr.length < 2 || val.length < 2) {
        return -1;
      }
      indexSize = 2;
      arrLength /= 2;
      valLength /= 2;
      byteOffset /= 2;
    }
  }
  function read(buf, i) {
    if (indexSize === 1) {
      return buf[i];
    } else {
      return buf.readUInt16BE(i * indexSize);
    }
  }
  var i;
  if (dir) {
    var foundIndex = -1;
    for (i = byteOffset; i < arrLength; i++) {
      if (read(arr, i) === read(val, foundIndex === -1 ? 0 : i - foundIndex)) {
        if (foundIndex === -1) foundIndex = i;
        if (i - foundIndex + 1 === valLength) return foundIndex * indexSize;
      } else {
        if (foundIndex !== -1) i -= i - foundIndex;
        foundIndex = -1;
      }
    }
  } else {
    if (byteOffset + valLength > arrLength) byteOffset = arrLength - valLength;
    for (i = byteOffset; i >= 0; i--) {
      var found = true;
      for (var j = 0; j < valLength; j++) {
        if (read(arr, i + j) !== read(val, j)) {
          found = false;
          break;
        }
      }
      if (found) return i;
    }
  }
  return -1;
}
Buffer.prototype.includes = function includes(val, byteOffset, encoding) {
  return this.indexOf(val, byteOffset, encoding) !== -1;
};
Buffer.prototype.indexOf = function indexOf(val, byteOffset, encoding) {
  return bidirectionalIndexOf(this, val, byteOffset, encoding, true);
};
Buffer.prototype.lastIndexOf = function lastIndexOf(val, byteOffset, encoding) {
  return bidirectionalIndexOf(this, val, byteOffset, encoding, false);
};
function hexWrite(buf, string, offset, length) {
  offset = Number(offset) || 0;
  var remaining = buf.length - offset;
  if (!length) {
    length = remaining;
  } else {
    length = Number(length);
    if (length > remaining) {
      length = remaining;
    }
  }

  // must be an even number of digits
  var strLen = string.length;
  if (strLen % 2 !== 0) throw new TypeError('Invalid hex string');
  if (length > strLen / 2) {
    length = strLen / 2;
  }
  for (var i = 0; i < length; ++i) {
    var parsed = parseInt(string.substr(i * 2, 2), 16);
    if (isNaN(parsed)) return i;
    buf[offset + i] = parsed;
  }
  return i;
}
function utf8Write(buf, string, offset, length) {
  return blitBuffer(utf8ToBytes(string, buf.length - offset), buf, offset, length);
}
function asciiWrite(buf, string, offset, length) {
  return blitBuffer(asciiToBytes(string), buf, offset, length);
}
function latin1Write(buf, string, offset, length) {
  return asciiWrite(buf, string, offset, length);
}
function base64Write(buf, string, offset, length) {
  return blitBuffer(base64ToBytes(string), buf, offset, length);
}
function ucs2Write(buf, string, offset, length) {
  return blitBuffer(utf16leToBytes(string, buf.length - offset), buf, offset, length);
}
Buffer.prototype.write = function write(string, offset, length, encoding) {
  // Buffer#write(string)
  if (offset === undefined) {
    encoding = 'utf8';
    length = this.length;
    offset = 0;
    // Buffer#write(string, encoding)
  } else if (length === undefined && typeof offset === 'string') {
    encoding = offset;
    length = this.length;
    offset = 0;
    // Buffer#write(string, offset[, length][, encoding])
  } else if (isFinite(offset)) {
    offset = offset | 0;
    if (isFinite(length)) {
      length = length | 0;
      if (encoding === undefined) encoding = 'utf8';
    } else {
      encoding = length;
      length = undefined;
    }
    // legacy write(string, encoding, offset, length) - remove in v0.13
  } else {
    throw new Error('Buffer.write(string, encoding, offset[, length]) is no longer supported');
  }
  var remaining = this.length - offset;
  if (length === undefined || length > remaining) length = remaining;
  if (string.length > 0 && (length < 0 || offset < 0) || offset > this.length) {
    throw new RangeError('Attempt to write outside buffer bounds');
  }
  if (!encoding) encoding = 'utf8';
  var loweredCase = false;
  for (;;) {
    switch (encoding) {
      case 'hex':
        return hexWrite(this, string, offset, length);
      case 'utf8':
      case 'utf-8':
        return utf8Write(this, string, offset, length);
      case 'ascii':
        return asciiWrite(this, string, offset, length);
      case 'latin1':
      case 'binary':
        return latin1Write(this, string, offset, length);
      case 'base64':
        // Warning: maxLength not taken into account in base64Write
        return base64Write(this, string, offset, length);
      case 'ucs2':
      case 'ucs-2':
      case 'utf16le':
      case 'utf-16le':
        return ucs2Write(this, string, offset, length);
      default:
        if (loweredCase) throw new TypeError('Unknown encoding: ' + encoding);
        encoding = ('' + encoding).toLowerCase();
        loweredCase = true;
    }
  }
};
Buffer.prototype.toJSON = function toJSON() {
  return {
    type: 'Buffer',
    data: Array.prototype.slice.call(this._arr || this, 0)
  };
};
function base64Slice(buf, start, end) {
  if (start === 0 && end === buf.length) {
    return base64.fromByteArray(buf);
  } else {
    return base64.fromByteArray(buf.slice(start, end));
  }
}
function utf8Slice(buf, start, end) {
  end = Math.min(buf.length, end);
  var res = [];
  var i = start;
  while (i < end) {
    var firstByte = buf[i];
    var codePoint = null;
    var bytesPerSequence = firstByte > 0xEF ? 4 : firstByte > 0xDF ? 3 : firstByte > 0xBF ? 2 : 1;
    if (i + bytesPerSequence <= end) {
      var secondByte, thirdByte, fourthByte, tempCodePoint;
      switch (bytesPerSequence) {
        case 1:
          if (firstByte < 0x80) {
            codePoint = firstByte;
          }
          break;
        case 2:
          secondByte = buf[i + 1];
          if ((secondByte & 0xC0) === 0x80) {
            tempCodePoint = (firstByte & 0x1F) << 0x6 | secondByte & 0x3F;
            if (tempCodePoint > 0x7F) {
              codePoint = tempCodePoint;
            }
          }
          break;
        case 3:
          secondByte = buf[i + 1];
          thirdByte = buf[i + 2];
          if ((secondByte & 0xC0) === 0x80 && (thirdByte & 0xC0) === 0x80) {
            tempCodePoint = (firstByte & 0xF) << 0xC | (secondByte & 0x3F) << 0x6 | thirdByte & 0x3F;
            if (tempCodePoint > 0x7FF && (tempCodePoint < 0xD800 || tempCodePoint > 0xDFFF)) {
              codePoint = tempCodePoint;
            }
          }
          break;
        case 4:
          secondByte = buf[i + 1];
          thirdByte = buf[i + 2];
          fourthByte = buf[i + 3];
          if ((secondByte & 0xC0) === 0x80 && (thirdByte & 0xC0) === 0x80 && (fourthByte & 0xC0) === 0x80) {
            tempCodePoint = (firstByte & 0xF) << 0x12 | (secondByte & 0x3F) << 0xC | (thirdByte & 0x3F) << 0x6 | fourthByte & 0x3F;
            if (tempCodePoint > 0xFFFF && tempCodePoint < 0x110000) {
              codePoint = tempCodePoint;
            }
          }
      }
    }
    if (codePoint === null) {
      // we did not generate a valid codePoint so insert a
      // replacement char (U+FFFD) and advance only 1 byte
      codePoint = 0xFFFD;
      bytesPerSequence = 1;
    } else if (codePoint > 0xFFFF) {
      // encode to utf16 (surrogate pair dance)
      codePoint -= 0x10000;
      res.push(codePoint >>> 10 & 0x3FF | 0xD800);
      codePoint = 0xDC00 | codePoint & 0x3FF;
    }
    res.push(codePoint);
    i += bytesPerSequence;
  }
  return decodeCodePointsArray(res);
}

// Based on http://stackoverflow.com/a/22747272/680742, the browser with
// the lowest limit is Chrome, with 0x10000 args.
// We go 1 magnitude less, for safety
var MAX_ARGUMENTS_LENGTH = 0x1000;
function decodeCodePointsArray(codePoints) {
  var len = codePoints.length;
  if (len <= MAX_ARGUMENTS_LENGTH) {
    return String.fromCharCode.apply(String, codePoints); // avoid extra slice()
  }

  // Decode in chunks to avoid "call stack size exceeded".
  var res = '';
  var i = 0;
  while (i < len) {
    res += String.fromCharCode.apply(String, codePoints.slice(i, i += MAX_ARGUMENTS_LENGTH));
  }
  return res;
}
function asciiSlice(buf, start, end) {
  var ret = '';
  end = Math.min(buf.length, end);
  for (var i = start; i < end; ++i) {
    ret += String.fromCharCode(buf[i] & 0x7F);
  }
  return ret;
}
function latin1Slice(buf, start, end) {
  var ret = '';
  end = Math.min(buf.length, end);
  for (var i = start; i < end; ++i) {
    ret += String.fromCharCode(buf[i]);
  }
  return ret;
}
function hexSlice(buf, start, end) {
  var len = buf.length;
  if (!start || start < 0) start = 0;
  if (!end || end < 0 || end > len) end = len;
  var out = '';
  for (var i = start; i < end; ++i) {
    out += toHex(buf[i]);
  }
  return out;
}
function utf16leSlice(buf, start, end) {
  var bytes = buf.slice(start, end);
  var res = '';
  for (var i = 0; i < bytes.length; i += 2) {
    res += String.fromCharCode(bytes[i] + bytes[i + 1] * 256);
  }
  return res;
}
Buffer.prototype.slice = function slice(start, end) {
  var len = this.length;
  start = ~~start;
  end = end === undefined ? len : ~~end;
  if (start < 0) {
    start += len;
    if (start < 0) start = 0;
  } else if (start > len) {
    start = len;
  }
  if (end < 0) {
    end += len;
    if (end < 0) end = 0;
  } else if (end > len) {
    end = len;
  }
  if (end < start) end = start;
  var newBuf;
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    newBuf = this.subarray(start, end);
    newBuf.__proto__ = Buffer.prototype;
  } else {
    var sliceLen = end - start;
    newBuf = new Buffer(sliceLen, undefined);
    for (var i = 0; i < sliceLen; ++i) {
      newBuf[i] = this[i + start];
    }
  }
  return newBuf;
};

/*
 * Need to make sure that buffer isn't trying to write out of bounds.
 */
function checkOffset(offset, ext, length) {
  if (offset % 1 !== 0 || offset < 0) throw new RangeError('offset is not uint');
  if (offset + ext > length) throw new RangeError('Trying to access beyond buffer length');
}
Buffer.prototype.readUIntLE = function readUIntLE(offset, byteLength, noAssert) {
  offset = offset | 0;
  byteLength = byteLength | 0;
  if (!noAssert) checkOffset(offset, byteLength, this.length);
  var val = this[offset];
  var mul = 1;
  var i = 0;
  while (++i < byteLength && (mul *= 0x100)) {
    val += this[offset + i] * mul;
  }
  return val;
};
Buffer.prototype.readUIntBE = function readUIntBE(offset, byteLength, noAssert) {
  offset = offset | 0;
  byteLength = byteLength | 0;
  if (!noAssert) {
    checkOffset(offset, byteLength, this.length);
  }
  var val = this[offset + --byteLength];
  var mul = 1;
  while (byteLength > 0 && (mul *= 0x100)) {
    val += this[offset + --byteLength] * mul;
  }
  return val;
};
Buffer.prototype.readUInt8 = function readUInt8(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 1, this.length);
  return this[offset];
};
Buffer.prototype.readUInt16LE = function readUInt16LE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 2, this.length);
  return this[offset] | this[offset + 1] << 8;
};
Buffer.prototype.readUInt16BE = function readUInt16BE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 2, this.length);
  return this[offset] << 8 | this[offset + 1];
};
Buffer.prototype.readUInt32LE = function readUInt32LE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 4, this.length);
  return (this[offset] | this[offset + 1] << 8 | this[offset + 2] << 16) + this[offset + 3] * 0x1000000;
};
Buffer.prototype.readUInt32BE = function readUInt32BE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 4, this.length);
  return this[offset] * 0x1000000 + (this[offset + 1] << 16 | this[offset + 2] << 8 | this[offset + 3]);
};
Buffer.prototype.readIntLE = function readIntLE(offset, byteLength, noAssert) {
  offset = offset | 0;
  byteLength = byteLength | 0;
  if (!noAssert) checkOffset(offset, byteLength, this.length);
  var val = this[offset];
  var mul = 1;
  var i = 0;
  while (++i < byteLength && (mul *= 0x100)) {
    val += this[offset + i] * mul;
  }
  mul *= 0x80;
  if (val >= mul) val -= Math.pow(2, 8 * byteLength);
  return val;
};
Buffer.prototype.readIntBE = function readIntBE(offset, byteLength, noAssert) {
  offset = offset | 0;
  byteLength = byteLength | 0;
  if (!noAssert) checkOffset(offset, byteLength, this.length);
  var i = byteLength;
  var mul = 1;
  var val = this[offset + --i];
  while (i > 0 && (mul *= 0x100)) {
    val += this[offset + --i] * mul;
  }
  mul *= 0x80;
  if (val >= mul) val -= Math.pow(2, 8 * byteLength);
  return val;
};
Buffer.prototype.readInt8 = function readInt8(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 1, this.length);
  if (!(this[offset] & 0x80)) return this[offset];
  return (0xff - this[offset] + 1) * -1;
};
Buffer.prototype.readInt16LE = function readInt16LE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 2, this.length);
  var val = this[offset] | this[offset + 1] << 8;
  return val & 0x8000 ? val | 0xFFFF0000 : val;
};
Buffer.prototype.readInt16BE = function readInt16BE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 2, this.length);
  var val = this[offset + 1] | this[offset] << 8;
  return val & 0x8000 ? val | 0xFFFF0000 : val;
};
Buffer.prototype.readInt32LE = function readInt32LE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 4, this.length);
  return this[offset] | this[offset + 1] << 8 | this[offset + 2] << 16 | this[offset + 3] << 24;
};
Buffer.prototype.readInt32BE = function readInt32BE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 4, this.length);
  return this[offset] << 24 | this[offset + 1] << 16 | this[offset + 2] << 8 | this[offset + 3];
};
Buffer.prototype.readFloatLE = function readFloatLE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 4, this.length);
  return ieee754.read(this, offset, true, 23, 4);
};
Buffer.prototype.readFloatBE = function readFloatBE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 4, this.length);
  return ieee754.read(this, offset, false, 23, 4);
};
Buffer.prototype.readDoubleLE = function readDoubleLE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 8, this.length);
  return ieee754.read(this, offset, true, 52, 8);
};
Buffer.prototype.readDoubleBE = function readDoubleBE(offset, noAssert) {
  if (!noAssert) checkOffset(offset, 8, this.length);
  return ieee754.read(this, offset, false, 52, 8);
};
function checkInt(buf, value, offset, ext, max, min) {
  if (!Buffer.isBuffer(buf)) throw new TypeError('"buffer" argument must be a Buffer instance');
  if (value > max || value < min) throw new RangeError('"value" argument is out of bounds');
  if (offset + ext > buf.length) throw new RangeError('Index out of range');
}
Buffer.prototype.writeUIntLE = function writeUIntLE(value, offset, byteLength, noAssert) {
  value = +value;
  offset = offset | 0;
  byteLength = byteLength | 0;
  if (!noAssert) {
    var maxBytes = Math.pow(2, 8 * byteLength) - 1;
    checkInt(this, value, offset, byteLength, maxBytes, 0);
  }
  var mul = 1;
  var i = 0;
  this[offset] = value & 0xFF;
  while (++i < byteLength && (mul *= 0x100)) {
    this[offset + i] = value / mul & 0xFF;
  }
  return offset + byteLength;
};
Buffer.prototype.writeUIntBE = function writeUIntBE(value, offset, byteLength, noAssert) {
  value = +value;
  offset = offset | 0;
  byteLength = byteLength | 0;
  if (!noAssert) {
    var maxBytes = Math.pow(2, 8 * byteLength) - 1;
    checkInt(this, value, offset, byteLength, maxBytes, 0);
  }
  var i = byteLength - 1;
  var mul = 1;
  this[offset + i] = value & 0xFF;
  while (--i >= 0 && (mul *= 0x100)) {
    this[offset + i] = value / mul & 0xFF;
  }
  return offset + byteLength;
};
Buffer.prototype.writeUInt8 = function writeUInt8(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 1, 0xff, 0);
  if (!Buffer.TYPED_ARRAY_SUPPORT) value = Math.floor(value);
  this[offset] = value & 0xff;
  return offset + 1;
};
function objectWriteUInt16(buf, value, offset, littleEndian) {
  if (value < 0) value = 0xffff + value + 1;
  for (var i = 0, j = Math.min(buf.length - offset, 2); i < j; ++i) {
    buf[offset + i] = (value & 0xff << 8 * (littleEndian ? i : 1 - i)) >>> (littleEndian ? i : 1 - i) * 8;
  }
}
Buffer.prototype.writeUInt16LE = function writeUInt16LE(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 2, 0xffff, 0);
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    this[offset] = value & 0xff;
    this[offset + 1] = value >>> 8;
  } else {
    objectWriteUInt16(this, value, offset, true);
  }
  return offset + 2;
};
Buffer.prototype.writeUInt16BE = function writeUInt16BE(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 2, 0xffff, 0);
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    this[offset] = value >>> 8;
    this[offset + 1] = value & 0xff;
  } else {
    objectWriteUInt16(this, value, offset, false);
  }
  return offset + 2;
};
function objectWriteUInt32(buf, value, offset, littleEndian) {
  if (value < 0) value = 0xffffffff + value + 1;
  for (var i = 0, j = Math.min(buf.length - offset, 4); i < j; ++i) {
    buf[offset + i] = value >>> (littleEndian ? i : 3 - i) * 8 & 0xff;
  }
}
Buffer.prototype.writeUInt32LE = function writeUInt32LE(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 4, 0xffffffff, 0);
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    this[offset + 3] = value >>> 24;
    this[offset + 2] = value >>> 16;
    this[offset + 1] = value >>> 8;
    this[offset] = value & 0xff;
  } else {
    objectWriteUInt32(this, value, offset, true);
  }
  return offset + 4;
};
Buffer.prototype.writeUInt32BE = function writeUInt32BE(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 4, 0xffffffff, 0);
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    this[offset] = value >>> 24;
    this[offset + 1] = value >>> 16;
    this[offset + 2] = value >>> 8;
    this[offset + 3] = value & 0xff;
  } else {
    objectWriteUInt32(this, value, offset, false);
  }
  return offset + 4;
};
Buffer.prototype.writeIntLE = function writeIntLE(value, offset, byteLength, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) {
    var limit = Math.pow(2, 8 * byteLength - 1);
    checkInt(this, value, offset, byteLength, limit - 1, -limit);
  }
  var i = 0;
  var mul = 1;
  var sub = 0;
  this[offset] = value & 0xFF;
  while (++i < byteLength && (mul *= 0x100)) {
    if (value < 0 && sub === 0 && this[offset + i - 1] !== 0) {
      sub = 1;
    }
    this[offset + i] = (value / mul >> 0) - sub & 0xFF;
  }
  return offset + byteLength;
};
Buffer.prototype.writeIntBE = function writeIntBE(value, offset, byteLength, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) {
    var limit = Math.pow(2, 8 * byteLength - 1);
    checkInt(this, value, offset, byteLength, limit - 1, -limit);
  }
  var i = byteLength - 1;
  var mul = 1;
  var sub = 0;
  this[offset + i] = value & 0xFF;
  while (--i >= 0 && (mul *= 0x100)) {
    if (value < 0 && sub === 0 && this[offset + i + 1] !== 0) {
      sub = 1;
    }
    this[offset + i] = (value / mul >> 0) - sub & 0xFF;
  }
  return offset + byteLength;
};
Buffer.prototype.writeInt8 = function writeInt8(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 1, 0x7f, -0x80);
  if (!Buffer.TYPED_ARRAY_SUPPORT) value = Math.floor(value);
  if (value < 0) value = 0xff + value + 1;
  this[offset] = value & 0xff;
  return offset + 1;
};
Buffer.prototype.writeInt16LE = function writeInt16LE(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 2, 0x7fff, -0x8000);
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    this[offset] = value & 0xff;
    this[offset + 1] = value >>> 8;
  } else {
    objectWriteUInt16(this, value, offset, true);
  }
  return offset + 2;
};
Buffer.prototype.writeInt16BE = function writeInt16BE(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 2, 0x7fff, -0x8000);
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    this[offset] = value >>> 8;
    this[offset + 1] = value & 0xff;
  } else {
    objectWriteUInt16(this, value, offset, false);
  }
  return offset + 2;
};
Buffer.prototype.writeInt32LE = function writeInt32LE(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 4, 0x7fffffff, -0x80000000);
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    this[offset] = value & 0xff;
    this[offset + 1] = value >>> 8;
    this[offset + 2] = value >>> 16;
    this[offset + 3] = value >>> 24;
  } else {
    objectWriteUInt32(this, value, offset, true);
  }
  return offset + 4;
};
Buffer.prototype.writeInt32BE = function writeInt32BE(value, offset, noAssert) {
  value = +value;
  offset = offset | 0;
  if (!noAssert) checkInt(this, value, offset, 4, 0x7fffffff, -0x80000000);
  if (value < 0) value = 0xffffffff + value + 1;
  if (Buffer.TYPED_ARRAY_SUPPORT) {
    this[offset] = value >>> 24;
    this[offset + 1] = value >>> 16;
    this[offset + 2] = value >>> 8;
    this[offset + 3] = value & 0xff;
  } else {
    objectWriteUInt32(this, value, offset, false);
  }
  return offset + 4;
};
function checkIEEE754(buf, value, offset, ext, max, min) {
  if (offset + ext > buf.length) throw new RangeError('Index out of range');
  if (offset < 0) throw new RangeError('Index out of range');
}
function writeFloat(buf, value, offset, littleEndian, noAssert) {
  if (!noAssert) {
    checkIEEE754(buf, value, offset, 4, 3.4028234663852886e+38, -3.4028234663852886e+38);
  }
  ieee754.write(buf, value, offset, littleEndian, 23, 4);
  return offset + 4;
}
Buffer.prototype.writeFloatLE = function writeFloatLE(value, offset, noAssert) {
  return writeFloat(this, value, offset, true, noAssert);
};
Buffer.prototype.writeFloatBE = function writeFloatBE(value, offset, noAssert) {
  return writeFloat(this, value, offset, false, noAssert);
};
function writeDouble(buf, value, offset, littleEndian, noAssert) {
  if (!noAssert) {
    checkIEEE754(buf, value, offset, 8, 1.7976931348623157E+308, -1.7976931348623157E+308);
  }
  ieee754.write(buf, value, offset, littleEndian, 52, 8);
  return offset + 8;
}
Buffer.prototype.writeDoubleLE = function writeDoubleLE(value, offset, noAssert) {
  return writeDouble(this, value, offset, true, noAssert);
};
Buffer.prototype.writeDoubleBE = function writeDoubleBE(value, offset, noAssert) {
  return writeDouble(this, value, offset, false, noAssert);
};

// copy(targetBuffer, targetStart=0, sourceStart=0, sourceEnd=buffer.length)
Buffer.prototype.copy = function copy(target, targetStart, start, end) {
  if (!start) start = 0;
  if (!end && end !== 0) end = this.length;
  if (targetStart >= target.length) targetStart = target.length;
  if (!targetStart) targetStart = 0;
  if (end > 0 && end < start) end = start;

  // Copy 0 bytes; we're done
  if (end === start) return 0;
  if (target.length === 0 || this.length === 0) return 0;

  // Fatal error conditions
  if (targetStart < 0) {
    throw new RangeError('targetStart out of bounds');
  }
  if (start < 0 || start >= this.length) throw new RangeError('sourceStart out of bounds');
  if (end < 0) throw new RangeError('sourceEnd out of bounds');

  // Are we oob?
  if (end > this.length) end = this.length;
  if (target.length - targetStart < end - start) {
    end = target.length - targetStart + start;
  }
  var len = end - start;
  var i;
  if (this === target && start < targetStart && targetStart < end) {
    // descending copy from end
    for (i = len - 1; i >= 0; --i) {
      target[i + targetStart] = this[i + start];
    }
  } else if (len < 1000 || !Buffer.TYPED_ARRAY_SUPPORT) {
    // ascending copy from start
    for (i = 0; i < len; ++i) {
      target[i + targetStart] = this[i + start];
    }
  } else {
    Uint8Array.prototype.set.call(target, this.subarray(start, start + len), targetStart);
  }
  return len;
};

// Usage:
//    buffer.fill(number[, offset[, end]])
//    buffer.fill(buffer[, offset[, end]])
//    buffer.fill(string[, offset[, end]][, encoding])
Buffer.prototype.fill = function fill(val, start, end, encoding) {
  // Handle string cases:
  if (typeof val === 'string') {
    if (typeof start === 'string') {
      encoding = start;
      start = 0;
      end = this.length;
    } else if (typeof end === 'string') {
      encoding = end;
      end = this.length;
    }
    if (val.length === 1) {
      var code = val.charCodeAt(0);
      if (code < 256) {
        val = code;
      }
    }
    if (encoding !== undefined && typeof encoding !== 'string') {
      throw new TypeError('encoding must be a string');
    }
    if (typeof encoding === 'string' && !Buffer.isEncoding(encoding)) {
      throw new TypeError('Unknown encoding: ' + encoding);
    }
  } else if (typeof val === 'number') {
    val = val & 255;
  }

  // Invalid ranges are not set to a default, so can range check early.
  if (start < 0 || this.length < start || this.length < end) {
    throw new RangeError('Out of range index');
  }
  if (end <= start) {
    return this;
  }
  start = start >>> 0;
  end = end === undefined ? this.length : end >>> 0;
  if (!val) val = 0;
  var i;
  if (typeof val === 'number') {
    for (i = start; i < end; ++i) {
      this[i] = val;
    }
  } else {
    var bytes = Buffer.isBuffer(val) ? val : utf8ToBytes(new Buffer(val, encoding).toString());
    var len = bytes.length;
    for (i = 0; i < end - start; ++i) {
      this[i + start] = bytes[i % len];
    }
  }
  return this;
};

// HELPER FUNCTIONS
// ================

var INVALID_BASE64_RE = /[^+\/0-9A-Za-z-_]/g;
function base64clean(str) {
  // Node strips out invalid characters like \n and \t from the string, base64-js does not
  str = stringtrim(str).replace(INVALID_BASE64_RE, '');
  // Node converts strings with length < 2 to ''
  if (str.length < 2) return '';
  // Node allows for non-padded base64 strings (missing trailing ===), base64-js does not
  while (str.length % 4 !== 0) {
    str = str + '=';
  }
  return str;
}
function stringtrim(str) {
  if (str.trim) return str.trim();
  return str.replace(/^\s+|\s+$/g, '');
}
function toHex(n) {
  if (n < 16) return '0' + n.toString(16);
  return n.toString(16);
}
function utf8ToBytes(string, units) {
  units = units || Infinity;
  var codePoint;
  var length = string.length;
  var leadSurrogate = null;
  var bytes = [];
  for (var i = 0; i < length; ++i) {
    codePoint = string.charCodeAt(i);

    // is surrogate component
    if (codePoint > 0xD7FF && codePoint < 0xE000) {
      // last char was a lead
      if (!leadSurrogate) {
        // no lead yet
        if (codePoint > 0xDBFF) {
          // unexpected trail
          if ((units -= 3) > -1) bytes.push(0xEF, 0xBF, 0xBD);
          continue;
        } else if (i + 1 === length) {
          // unpaired lead
          if ((units -= 3) > -1) bytes.push(0xEF, 0xBF, 0xBD);
          continue;
        }

        // valid lead
        leadSurrogate = codePoint;
        continue;
      }

      // 2 leads in a row
      if (codePoint < 0xDC00) {
        if ((units -= 3) > -1) bytes.push(0xEF, 0xBF, 0xBD);
        leadSurrogate = codePoint;
        continue;
      }

      // valid surrogate pair
      codePoint = (leadSurrogate - 0xD800 << 10 | codePoint - 0xDC00) + 0x10000;
    } else if (leadSurrogate) {
      // valid bmp char, but last char was a lead
      if ((units -= 3) > -1) bytes.push(0xEF, 0xBF, 0xBD);
    }
    leadSurrogate = null;

    // encode utf8
    if (codePoint < 0x80) {
      if ((units -= 1) < 0) break;
      bytes.push(codePoint);
    } else if (codePoint < 0x800) {
      if ((units -= 2) < 0) break;
      bytes.push(codePoint >> 0x6 | 0xC0, codePoint & 0x3F | 0x80);
    } else if (codePoint < 0x10000) {
      if ((units -= 3) < 0) break;
      bytes.push(codePoint >> 0xC | 0xE0, codePoint >> 0x6 & 0x3F | 0x80, codePoint & 0x3F | 0x80);
    } else if (codePoint < 0x110000) {
      if ((units -= 4) < 0) break;
      bytes.push(codePoint >> 0x12 | 0xF0, codePoint >> 0xC & 0x3F | 0x80, codePoint >> 0x6 & 0x3F | 0x80, codePoint & 0x3F | 0x80);
    } else {
      throw new Error('Invalid code point');
    }
  }
  return bytes;
}
function asciiToBytes(str) {
  var byteArray = [];
  for (var i = 0; i < str.length; ++i) {
    // Node's code seems to be doing this and not & 0x7F..
    byteArray.push(str.charCodeAt(i) & 0xFF);
  }
  return byteArray;
}
function utf16leToBytes(str, units) {
  var c, hi, lo;
  var byteArray = [];
  for (var i = 0; i < str.length; ++i) {
    if ((units -= 2) < 0) break;
    c = str.charCodeAt(i);
    hi = c >> 8;
    lo = c % 256;
    byteArray.push(lo);
    byteArray.push(hi);
  }
  return byteArray;
}
function base64ToBytes(str) {
  return base64.toByteArray(base64clean(str));
}
function blitBuffer(src, dst, offset, length) {
  for (var i = 0; i < length; ++i) {
    if (i + offset >= dst.length || i >= src.length) break;
    dst[i + offset] = src[i];
  }
  return i;
}
function isnan(val) {
  return val !== val; // eslint-disable-line no-self-compare
}
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./../webpack/buildin/global.js */ 3)))

/***/ }),

/***/ 7:
/*!*****************************************!*\
  !*** ./node_modules/base64-js/index.js ***!
  \*****************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

"use strict";


exports.byteLength = byteLength;
exports.toByteArray = toByteArray;
exports.fromByteArray = fromByteArray;
var lookup = [];
var revLookup = [];
var Arr = typeof Uint8Array !== 'undefined' ? Uint8Array : Array;
var code = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
for (var i = 0, len = code.length; i < len; ++i) {
  lookup[i] = code[i];
  revLookup[code.charCodeAt(i)] = i;
}

// Support decoding URL-safe base64 strings, as Node.js does.
// See: https://en.wikipedia.org/wiki/Base64#URL_applications
revLookup['-'.charCodeAt(0)] = 62;
revLookup['_'.charCodeAt(0)] = 63;
function getLens(b64) {
  var len = b64.length;
  if (len % 4 > 0) {
    throw new Error('Invalid string. Length must be a multiple of 4');
  }

  // Trim off extra bytes after placeholder bytes are found
  // See: https://github.com/beatgammit/base64-js/issues/42
  var validLen = b64.indexOf('=');
  if (validLen === -1) validLen = len;
  var placeHoldersLen = validLen === len ? 0 : 4 - validLen % 4;
  return [validLen, placeHoldersLen];
}

// base64 is 4/3 + up to two characters of the original data
function byteLength(b64) {
  var lens = getLens(b64);
  var validLen = lens[0];
  var placeHoldersLen = lens[1];
  return (validLen + placeHoldersLen) * 3 / 4 - placeHoldersLen;
}
function _byteLength(b64, validLen, placeHoldersLen) {
  return (validLen + placeHoldersLen) * 3 / 4 - placeHoldersLen;
}
function toByteArray(b64) {
  var tmp;
  var lens = getLens(b64);
  var validLen = lens[0];
  var placeHoldersLen = lens[1];
  var arr = new Arr(_byteLength(b64, validLen, placeHoldersLen));
  var curByte = 0;

  // if there are placeholders, only get up to the last complete 4 chars
  var len = placeHoldersLen > 0 ? validLen - 4 : validLen;
  var i;
  for (i = 0; i < len; i += 4) {
    tmp = revLookup[b64.charCodeAt(i)] << 18 | revLookup[b64.charCodeAt(i + 1)] << 12 | revLookup[b64.charCodeAt(i + 2)] << 6 | revLookup[b64.charCodeAt(i + 3)];
    arr[curByte++] = tmp >> 16 & 0xFF;
    arr[curByte++] = tmp >> 8 & 0xFF;
    arr[curByte++] = tmp & 0xFF;
  }
  if (placeHoldersLen === 2) {
    tmp = revLookup[b64.charCodeAt(i)] << 2 | revLookup[b64.charCodeAt(i + 1)] >> 4;
    arr[curByte++] = tmp & 0xFF;
  }
  if (placeHoldersLen === 1) {
    tmp = revLookup[b64.charCodeAt(i)] << 10 | revLookup[b64.charCodeAt(i + 1)] << 4 | revLookup[b64.charCodeAt(i + 2)] >> 2;
    arr[curByte++] = tmp >> 8 & 0xFF;
    arr[curByte++] = tmp & 0xFF;
  }
  return arr;
}
function tripletToBase64(num) {
  return lookup[num >> 18 & 0x3F] + lookup[num >> 12 & 0x3F] + lookup[num >> 6 & 0x3F] + lookup[num & 0x3F];
}
function encodeChunk(uint8, start, end) {
  var tmp;
  var output = [];
  for (var i = start; i < end; i += 3) {
    tmp = (uint8[i] << 16 & 0xFF0000) + (uint8[i + 1] << 8 & 0xFF00) + (uint8[i + 2] & 0xFF);
    output.push(tripletToBase64(tmp));
  }
  return output.join('');
}
function fromByteArray(uint8) {
  var tmp;
  var len = uint8.length;
  var extraBytes = len % 3; // if we have 1 byte left, pad 2 bytes
  var parts = [];
  var maxChunkLength = 16383; // must be multiple of 3

  // go through the array every three bytes, we'll deal with trailing stuff later
  for (var i = 0, len2 = len - extraBytes; i < len2; i += maxChunkLength) {
    parts.push(encodeChunk(uint8, i, i + maxChunkLength > len2 ? len2 : i + maxChunkLength));
  }

  // pad the end with zeros, but make sure to not forget the extra bytes
  if (extraBytes === 1) {
    tmp = uint8[len - 1];
    parts.push(lookup[tmp >> 2] + lookup[tmp << 4 & 0x3F] + '==');
  } else if (extraBytes === 2) {
    tmp = (uint8[len - 2] << 8) + uint8[len - 1];
    parts.push(lookup[tmp >> 10] + lookup[tmp >> 4 & 0x3F] + lookup[tmp << 2 & 0x3F] + '=');
  }
  return parts.join('');
}

/***/ }),

/***/ 780:
/*!**********************************************************!*\
  !*** ./uview-ui/components/u-parse/libs/MpHtmlParser.js ***!
  \**********************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

/* WEBPACK VAR INJECTION */(function(uni) {/**
 * html 解析器
 * @tutorial https://github.com/jin-yufeng/Parser
 * @version 20201029
 * @author JinYufeng
 * @listens MIT
 */
const cfg = __webpack_require__(/*! ./config.js */ 781),
  blankChar = cfg.blankChar,
  CssHandler = __webpack_require__(/*! ./CssHandler.js */ 782),
  windowWidth = uni.getSystemInfoSync().windowWidth;
var emoji;
function MpHtmlParser(data, options = {}) {
  this.attrs = {};
  this.CssHandler = new CssHandler(options.tagStyle, windowWidth);
  this.data = data;
  this.domain = options.domain;
  this.DOM = [];
  this.i = this.start = this.audioNum = this.imgNum = this.videoNum = 0;
  options.prot = (this.domain || '').includes('://') ? this.domain.split('://')[0] : 'http';
  this.options = options;
  this.state = this.Text;
  this.STACK = [];
  // 工具函数
  this.bubble = () => {
    for (var i = this.STACK.length, item; item = this.STACK[--i];) {
      if (cfg.richOnlyTags[item.name]) return false;
      item.c = 1;
    }
    return true;
  };
  this.decode = (val, amp) => {
    var i = -1,
      j,
      en;
    while (1) {
      if ((i = val.indexOf('&', i + 1)) == -1) break;
      if ((j = val.indexOf(';', i + 2)) == -1) break;
      if (val[i + 1] == '#') {
        en = parseInt((val[i + 2] == 'x' ? '0' : '') + val.substring(i + 2, j));
        if (!isNaN(en)) val = val.substr(0, i) + String.fromCharCode(en) + val.substr(j + 1);
      } else {
        en = val.substring(i + 1, j);
        if (cfg.entities[en] || en == amp) val = val.substr(0, i) + (cfg.entities[en] || '&') + val.substr(j + 1);
      }
    }
    return val;
  };
  this.getUrl = url => {
    if (url[0] == '/') {
      if (url[1] == '/') url = this.options.prot + ':' + url;else if (this.domain) url = this.domain + url;
    } else if (this.domain && url.indexOf('data:') != 0 && !url.includes('://')) url = this.domain + '/' + url;
    return url;
  };
  this.isClose = () => this.data[this.i] == '>' || this.data[this.i] == '/' && this.data[this.i + 1] == '>';
  this.section = () => this.data.substring(this.start, this.i);
  this.parent = () => this.STACK[this.STACK.length - 1];
  this.siblings = () => this.STACK.length ? this.parent().children : this.DOM;
}
MpHtmlParser.prototype.parse = function () {
  if (emoji) this.data = emoji.parseEmoji(this.data);
  for (var c; c = this.data[this.i]; this.i++) this.state(c);
  if (this.state == this.Text) this.setText();
  while (this.STACK.length) this.popNode(this.STACK.pop());
  return this.DOM;
};
// 设置属性
MpHtmlParser.prototype.setAttr = function () {
  var name = this.attrName.toLowerCase(),
    val = this.attrVal;
  if (cfg.boolAttrs[name]) this.attrs[name] = 'T';else if (val) {
    if (name == 'src' || name == 'data-src' && !this.attrs.src) this.attrs.src = this.getUrl(this.decode(val, 'amp'));else if (name == 'href' || name == 'style') this.attrs[name] = this.decode(val, 'amp');else if (name.substr(0, 5) != 'data-') this.attrs[name] = val;
  }
  this.attrVal = '';
  while (blankChar[this.data[this.i]]) this.i++;
  if (this.isClose()) this.setNode();else {
    this.start = this.i;
    this.state = this.AttrName;
  }
};
// 设置文本节点
MpHtmlParser.prototype.setText = function () {
  var back,
    text = this.section();
  if (!text) return;
  text = cfg.onText && cfg.onText(text, () => back = true) || text;
  if (back) {
    this.data = this.data.substr(0, this.start) + text + this.data.substr(this.i);
    let j = this.start + text.length;
    for (this.i = this.start; this.i < j; this.i++) this.state(this.data[this.i]);
    return;
  }
  if (!this.pre) {
    // 合并空白符
    var flag,
      tmp = [];
    for (let i = text.length, c; c = text[--i];) if (!blankChar[c]) {
      tmp.unshift(c);
      if (!flag) flag = 1;
    } else {
      if (tmp[0] != ' ') tmp.unshift(' ');
      if (c == '\n' && flag == void 0) flag = 0;
    }
    if (flag == 0) return;
    text = tmp.join('');
  }
  this.siblings().push({
    type: 'text',
    text: this.decode(text)
  });
};
// 设置元素节点
MpHtmlParser.prototype.setNode = function () {
  var node = {
      name: this.tagName.toLowerCase(),
      attrs: this.attrs
    },
    close = cfg.selfClosingTags[node.name];
  if (this.options.nodes.length) node.type = 'node';
  this.attrs = {};
  if (!cfg.ignoreTags[node.name]) {
    // 处理属性
    var attrs = node.attrs,
      style = this.CssHandler.match(node.name, attrs, node) + (attrs.style || ''),
      styleObj = {};
    if (attrs.id) {
      if (this.options.compress & 1) attrs.id = void 0;else if (this.options.useAnchor) this.bubble();
    }
    if (this.options.compress & 2 && attrs.class) attrs.class = void 0;
    switch (node.name) {
      case 'a':
      case 'ad':
        this.bubble();
        break;
      case 'font':
        if (attrs.color) {
          styleObj['color'] = attrs.color;
          attrs.color = void 0;
        }
        if (attrs.face) {
          styleObj['font-family'] = attrs.face;
          attrs.face = void 0;
        }
        if (attrs.size) {
          var size = parseInt(attrs.size);
          if (size < 1) size = 1;else if (size > 7) size = 7;
          var map = ['xx-small', 'x-small', 'small', 'medium', 'large', 'x-large', 'xx-large'];
          styleObj['font-size'] = map[size - 1];
          attrs.size = void 0;
        }
        break;
      case 'embed':
        var src = node.attrs.src || '',
          type = node.attrs.type || '';
        if (type.includes('video') || src.includes('.mp4') || src.includes('.3gp') || src.includes('.m3u8')) node.name = 'video';else if (type.includes('audio') || src.includes('.m4a') || src.includes('.wav') || src.includes('.mp3') || src.includes('.aac')) node.name = 'audio';else break;
        if (node.attrs.autostart) node.attrs.autoplay = 'T';
        node.attrs.controls = 'T';
      case 'video':
      case 'audio':
        if (!attrs.id) attrs.id = node.name + ++this[`${node.name}Num`];else this[`${node.name}Num`]++;
        if (node.name == 'video') {
          if (this.videoNum > 3) node.lazyLoad = 1;
          if (attrs.width) {
            styleObj.width = parseFloat(attrs.width) + (attrs.width.includes('%') ? '%' : 'px');
            attrs.width = void 0;
          }
          if (attrs.height) {
            styleObj.height = parseFloat(attrs.height) + (attrs.height.includes('%') ? '%' : 'px');
            attrs.height = void 0;
          }
        }
        if (!attrs.controls && !attrs.autoplay) attrs.controls = 'T';
        attrs.source = [];
        if (attrs.src) {
          attrs.source.push(attrs.src);
          attrs.src = void 0;
        }
        this.bubble();
        break;
      case 'td':
      case 'th':
        if (attrs.colspan || attrs.rowspan) for (var k = this.STACK.length, item; item = this.STACK[--k];) if (item.name == 'table') {
          item.flag = 1;
          break;
        }
    }
    if (attrs.align) {
      if (node.name == 'table') {
        if (attrs.align == 'center') styleObj['margin-inline-start'] = styleObj['margin-inline-end'] = 'auto';else styleObj['float'] = attrs.align;
      } else styleObj['text-align'] = attrs.align;
      attrs.align = void 0;
    }
    // 压缩 style
    var styles = style.split(';');
    style = '';
    for (var i = 0, len = styles.length; i < len; i++) {
      var info = styles[i].split(':');
      if (info.length < 2) continue;
      let key = info[0].trim().toLowerCase(),
        value = info.slice(1).join(':').trim();
      if (value[0] == '-' || value.includes('safe')) style += `;${key}:${value}`;else if (!styleObj[key] || value.includes('import') || !styleObj[key].includes('import')) styleObj[key] = value;
    }
    if (node.name == 'img') {
      if (attrs.src && !attrs.ignore) {
        if (this.bubble()) attrs.i = (this.imgNum++).toString();else attrs.ignore = 'T';
      }
      if (attrs.ignore) {
        style += ';-webkit-touch-callout:none';
        styleObj['max-width'] = '100%';
      }
      var width;
      if (styleObj.width) width = styleObj.width;else if (attrs.width) width = attrs.width.includes('%') ? attrs.width : parseFloat(attrs.width) + 'px';
      if (width) {
        styleObj.width = width;
        attrs.width = '100%';
        if (parseInt(width) > windowWidth) {
          styleObj.height = '';
          if (attrs.height) attrs.height = void 0;
        }
      }
      if (styleObj.height) {
        attrs.height = styleObj.height;
        styleObj.height = '';
      } else if (attrs.height && !attrs.height.includes('%')) attrs.height = parseFloat(attrs.height) + 'px';
    }
    for (var key in styleObj) {
      var value = styleObj[key];
      if (!value) continue;
      if (key.includes('flex') || key == 'order' || key == 'self-align') node.c = 1;
      // 填充链接
      if (value.includes('url')) {
        var j = value.indexOf('(');
        if (j++ != -1) {
          while (value[j] == '"' || value[j] == "'" || blankChar[value[j]]) j++;
          value = value.substr(0, j) + this.getUrl(value.substr(j));
        }
      }
      // 转换 rpx
      else if (value.includes('rpx')) value = value.replace(/[0-9.]+\s*rpx/g, $ => parseFloat($) * windowWidth / 750 + 'px');else if (key == 'white-space' && value.includes('pre') && !close) this.pre = node.pre = true;
      style += `;${key}:${value}`;
    }
    style = style.substr(1);
    if (style) attrs.style = style;
    if (!close) {
      node.children = [];
      if (node.name == 'pre' && cfg.highlight) {
        this.remove(node);
        this.pre = node.pre = true;
      }
      this.siblings().push(node);
      this.STACK.push(node);
    } else if (!cfg.filter || cfg.filter(node, this) != false) this.siblings().push(node);
  } else {
    if (!close) this.remove(node);else if (node.name == 'source') {
      var parent = this.parent();
      if (parent && (parent.name == 'video' || parent.name == 'audio') && node.attrs.src) parent.attrs.source.push(node.attrs.src);
    } else if (node.name == 'base' && !this.domain) this.domain = node.attrs.href;
  }
  if (this.data[this.i] == '/') this.i++;
  this.start = this.i + 1;
  this.state = this.Text;
};
// 移除标签
MpHtmlParser.prototype.remove = function (node) {
  var name = node.name,
    j = this.i;
  // 处理 svg
  var handleSvg = () => {
    var src = this.data.substring(j, this.i + 1);
    node.attrs.xmlns = 'http://www.w3.org/2000/svg';
    for (var key in node.attrs) {
      if (key == 'viewbox') src = ` viewBox="${node.attrs.viewbox}"` + src;else if (key != 'style') src = ` ${key}="${node.attrs[key]}"` + src;
    }
    src = '<svg' + src;
    var parent = this.parent();
    if (node.attrs.width == '100%' && parent && (parent.attrs.style || '').includes('inline')) parent.attrs.style = 'width:300px;max-width:100%;' + parent.attrs.style;
    this.siblings().push({
      name: 'img',
      attrs: {
        src: 'data:image/svg+xml;utf8,' + src.replace(/#/g, '%23'),
        style: node.attrs.style,
        ignore: 'T'
      }
    });
  };
  if (node.name == 'svg' && this.data[j] == '/') return handleSvg(this.i++);
  while (1) {
    if ((this.i = this.data.indexOf('</', this.i + 1)) == -1) {
      if (name == 'pre' || name == 'svg') this.i = j;else this.i = this.data.length;
      return;
    }
    this.start = this.i += 2;
    while (!blankChar[this.data[this.i]] && !this.isClose()) this.i++;
    if (this.section().toLowerCase() == name) {
      // 代码块高亮
      if (name == 'pre') {
        this.data = this.data.substr(0, j + 1) + cfg.highlight(this.data.substring(j + 1, this.i - 5), node.attrs) + this.data.substr(this.i - 5);
        return this.i = j;
      } else if (name == 'style') this.CssHandler.getStyle(this.data.substring(j + 1, this.i - 7));else if (name == 'title') this.DOM.title = this.data.substring(j + 1, this.i - 7);
      if ((this.i = this.data.indexOf('>', this.i)) == -1) this.i = this.data.length;
      if (name == 'svg') handleSvg();
      return;
    }
  }
};
// 节点出栈处理
MpHtmlParser.prototype.popNode = function (node) {
  // 空白符处理
  if (node.pre) {
    node.pre = this.pre = void 0;
    for (let i = this.STACK.length; i--;) if (this.STACK[i].pre) this.pre = true;
  }
  var siblings = this.siblings(),
    len = siblings.length,
    childs = node.children;
  if (node.name == 'head' || cfg.filter && cfg.filter(node, this) == false) return siblings.pop();
  var attrs = node.attrs;
  // 替换一些标签名
  if (cfg.blockTags[node.name]) node.name = 'div';else if (!cfg.trustTags[node.name]) node.name = 'span';
  // 处理列表
  if (node.c && (node.name == 'ul' || node.name == 'ol')) {
    if ((node.attrs.style || '').includes('list-style:none')) {
      for (let i = 0, child; child = childs[i++];) if (child.name == 'li') child.name = 'div';
    } else if (node.name == 'ul') {
      var floor = 1;
      for (let i = this.STACK.length; i--;) if (this.STACK[i].name == 'ul') floor++;
      if (floor != 1) for (let i = childs.length; i--;) childs[i].floor = floor;
    } else {
      for (let i = 0, num = 1, child; child = childs[i++];) if (child.name == 'li') {
        child.type = 'ol';
        child.num = ((num, type) => {
          if (type == 'a') return String.fromCharCode(97 + (num - 1) % 26);
          if (type == 'A') return String.fromCharCode(65 + (num - 1) % 26);
          if (type == 'i' || type == 'I') {
            num = (num - 1) % 99 + 1;
            var one = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'],
              ten = ['X', 'XX', 'XXX', 'XL', 'L', 'LX', 'LXX', 'LXXX', 'XC'],
              res = (ten[Math.floor(num / 10) - 1] || '') + (one[num % 10 - 1] || '');
            if (type == 'i') return res.toLowerCase();
            return res;
          }
          return num;
        })(num++, attrs.type) + '.';
      }
    }
  }
  // 处理表格
  if (node.name == 'table') {
    var padding = parseFloat(attrs.cellpadding),
      spacing = parseFloat(attrs.cellspacing),
      border = parseFloat(attrs.border);
    if (node.c) {
      if (isNaN(padding)) padding = 2;
      if (isNaN(spacing)) spacing = 2;
    }
    if (border) attrs.style = `border:${border}px solid gray;${attrs.style || ''}`;
    if (node.flag && node.c) {
      // 有 colspan 或 rowspan 且含有链接的表格转为 grid 布局实现
      attrs.style = `${attrs.style || ''};${spacing ? `;grid-gap:${spacing}px` : ';border-left:0;border-top:0'}`;
      var row = 1,
        col = 1,
        colNum,
        trs = [],
        children = [],
        map = {};
      (function f(ns) {
        for (var i = 0; i < ns.length; i++) {
          if (ns[i].name == 'tr') trs.push(ns[i]);else f(ns[i].children || []);
        }
      })(node.children);
      for (let i = 0; i < trs.length; i++) {
        for (let j = 0, td; td = trs[i].children[j]; j++) {
          if (td.name == 'td' || td.name == 'th') {
            while (map[row + '.' + col]) col++;
            var cell = {
              name: 'div',
              c: 1,
              attrs: {
                style: (td.attrs.style || '') + (border ? `;border:${border}px solid gray` + (spacing ? '' : ';border-right:0;border-bottom:0') : '') + (padding ? `;padding:${padding}px` : '')
              },
              children: td.children
            };
            if (td.attrs.colspan) {
              cell.attrs.style += ';grid-column-start:' + col + ';grid-column-end:' + (col + parseInt(td.attrs.colspan));
              if (!td.attrs.rowspan) cell.attrs.style += ';grid-row-start:' + row + ';grid-row-end:' + (row + 1);
              col += parseInt(td.attrs.colspan) - 1;
            }
            if (td.attrs.rowspan) {
              cell.attrs.style += ';grid-row-start:' + row + ';grid-row-end:' + (row + parseInt(td.attrs.rowspan));
              if (!td.attrs.colspan) cell.attrs.style += ';grid-column-start:' + col + ';grid-column-end:' + (col + 1);
              for (var k = 1; k < td.attrs.rowspan; k++) map[row + k + '.' + col] = 1;
            }
            children.push(cell);
            col++;
          }
        }
        if (!colNum) {
          colNum = col - 1;
          attrs.style += `;grid-template-columns:repeat(${colNum},auto)`;
        }
        col = 1;
        row++;
      }
      node.children = children;
    } else {
      attrs.style = `border-spacing:${spacing}px;${attrs.style || ''}`;
      if (border || padding) (function f(ns) {
        for (var i = 0, n; n = ns[i]; i++) {
          if (n.name == 'th' || n.name == 'td') {
            if (border) n.attrs.style = `border:${border}px solid gray;${n.attrs.style || ''}`;
            if (padding) n.attrs.style = `padding:${padding}px;${n.attrs.style || ''}`;
          } else f(n.children || []);
        }
      })(childs);
    }
    if (this.options.autoscroll) {
      var table = Object.assign({}, node);
      node.name = 'div';
      node.attrs = {
        style: 'overflow:scroll'
      };
      node.children = [table];
    }
  }
  this.CssHandler.pop && this.CssHandler.pop(node);
  // 自动压缩
  if (node.name == 'div' && !Object.keys(attrs).length && childs.length == 1 && childs[0].name == 'div') siblings[len - 1] = childs[0];
};
// 状态机
MpHtmlParser.prototype.Text = function (c) {
  if (c == '<') {
    var next = this.data[this.i + 1],
      isLetter = c => c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z';
    if (isLetter(next)) {
      this.setText();
      this.start = this.i + 1;
      this.state = this.TagName;
    } else if (next == '/') {
      this.setText();
      if (isLetter(this.data[++this.i + 1])) {
        this.start = this.i + 1;
        this.state = this.EndTag;
      } else this.Comment();
    } else if (next == '!' || next == '?') {
      this.setText();
      this.Comment();
    }
  }
};
MpHtmlParser.prototype.Comment = function () {
  var key;
  if (this.data.substring(this.i + 2, this.i + 4) == '--') key = '-->';else if (this.data.substring(this.i + 2, this.i + 9) == '[CDATA[') key = ']]>';else key = '>';
  if ((this.i = this.data.indexOf(key, this.i + 2)) == -1) this.i = this.data.length;else this.i += key.length - 1;
  this.start = this.i + 1;
  this.state = this.Text;
};
MpHtmlParser.prototype.TagName = function (c) {
  if (blankChar[c]) {
    this.tagName = this.section();
    while (blankChar[this.data[this.i]]) this.i++;
    if (this.isClose()) this.setNode();else {
      this.start = this.i;
      this.state = this.AttrName;
    }
  } else if (this.isClose()) {
    this.tagName = this.section();
    this.setNode();
  }
};
MpHtmlParser.prototype.AttrName = function (c) {
  if (c == '=' || blankChar[c] || this.isClose()) {
    this.attrName = this.section();
    if (blankChar[c]) while (blankChar[this.data[++this.i]]);
    if (this.data[this.i] == '=') {
      while (blankChar[this.data[++this.i]]);
      this.start = this.i--;
      this.state = this.AttrValue;
    } else this.setAttr();
  }
};
MpHtmlParser.prototype.AttrValue = function (c) {
  if (c == '"' || c == "'") {
    this.start++;
    if ((this.i = this.data.indexOf(c, this.i + 1)) == -1) return this.i = this.data.length;
    this.attrVal = this.section();
    this.i++;
  } else {
    for (; !blankChar[this.data[this.i]] && !this.isClose(); this.i++);
    this.attrVal = this.section();
  }
  this.setAttr();
};
MpHtmlParser.prototype.EndTag = function (c) {
  if (blankChar[c] || c == '>' || c == '/') {
    var name = this.section().toLowerCase();
    for (var i = this.STACK.length; i--;) if (this.STACK[i].name == name) break;
    if (i != -1) {
      var node;
      while ((node = this.STACK.pop()).name != name) this.popNode(node);
      this.popNode(node);
    } else if (name == 'p' || name == 'br') this.siblings().push({
      name,
      attrs: {}
    });
    this.i = this.data.indexOf('>', this.i);
    this.start = this.i + 1;
    if (this.i == -1) this.i = this.data.length;else this.state = this.Text;
  }
};
module.exports = MpHtmlParser;
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 781:
/*!****************************************************!*\
  !*** ./uview-ui/components/u-parse/libs/config.js ***!
  \****************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

/* WEBPACK VAR INJECTION */(function(wx) {/* 配置文件 */
var cfg = {
  // 出错占位图
  errorImg: null,
  // 过滤器函数
  filter: null,
  // 代码高亮函数
  highlight: null,
  // 文本处理函数
  onText: null,
  // 实体编码列表
  entities: {
    quot: '"',
    apos: "'",
    semi: ';',
    nbsp: '\xA0',
    ensp: '\u2002',
    emsp: '\u2003',
    ndash: '–',
    mdash: '—',
    middot: '·',
    lsquo: '‘',
    rsquo: '’',
    ldquo: '“',
    rdquo: '”',
    bull: '•',
    hellip: '…'
  },
  blankChar: makeMap(' ,\xA0,\t,\r,\n,\f'),
  boolAttrs: makeMap('allowfullscreen,autoplay,autostart,controls,ignore,loop,muted'),
  // 块级标签，将被转为 div
  blockTags: makeMap('address,article,aside,body,caption,center,cite,footer,header,html,nav,pre,section'),
  // 将被移除的标签
  ignoreTags: makeMap('area,base,canvas,frame,iframe,input,link,map,meta,param,script,source,style,svg,textarea,title,track,wbr'),
  // 只能被 rich-text 显示的标签
  richOnlyTags: makeMap('a,colgroup,fieldset,legend'),
  // 自闭合的标签
  selfClosingTags: makeMap('area,base,br,col,circle,ellipse,embed,frame,hr,img,input,line,link,meta,param,path,polygon,rect,source,track,use,wbr'),
  // 信任的标签
  trustTags: makeMap('a,abbr,ad,audio,b,blockquote,br,code,col,colgroup,dd,del,dl,dt,div,em,fieldset,h1,h2,h3,h4,h5,h6,hr,i,img,ins,label,legend,li,ol,p,q,source,span,strong,sub,sup,table,tbody,td,tfoot,th,thead,tr,title,ul,video'),
  // 默认的标签样式
  userAgentStyles: {
    address: 'font-style:italic',
    big: 'display:inline;font-size:1.2em',
    blockquote: 'background-color:#f6f6f6;border-left:3px solid #dbdbdb;color:#6c6c6c;padding:5px 0 5px 10px',
    caption: 'display:table-caption;text-align:center',
    center: 'text-align:center',
    cite: 'font-style:italic',
    dd: 'margin-left:40px',
    mark: 'background-color:yellow',
    pre: 'font-family:monospace;white-space:pre;overflow:scroll',
    s: 'text-decoration:line-through',
    small: 'display:inline;font-size:0.8em',
    u: 'text-decoration:underline'
  }
};
function makeMap(str) {
  var map = Object.create(null),
    list = str.split(',');
  for (var i = list.length; i--;) map[list[i]] = true;
  return map;
}
if (wx.canIUse('editor')) {
  cfg.blockTags.pre = void 0;
  cfg.ignoreTags.rp = true;
  Object.assign(cfg.richOnlyTags, makeMap('bdi,bdo,caption,rt,ruby'));
  Object.assign(cfg.trustTags, makeMap('bdi,bdo,caption,pre,rt,ruby'));
}
module.exports = cfg;
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/wx.js */ 1)["default"]))

/***/ }),

/***/ 782:
/*!********************************************************!*\
  !*** ./uview-ui/components/u-parse/libs/CssHandler.js ***!
  \********************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

const cfg = __webpack_require__(/*! ./config.js */ 781),
  isLetter = c => c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z';
function CssHandler(tagStyle) {
  var styles = Object.assign(Object.create(null), cfg.userAgentStyles);
  for (var item in tagStyle) styles[item] = (styles[item] ? styles[item] + ';' : '') + tagStyle[item];
  this.styles = styles;
}
CssHandler.prototype.getStyle = function (data) {
  this.styles = new parser(data, this.styles).parse();
};
CssHandler.prototype.match = function (name, attrs) {
  var tmp,
    matched = (tmp = this.styles[name]) ? tmp + ';' : '';
  if (attrs.class) {
    var items = attrs.class.split(' ');
    for (var i = 0, item; item = items[i]; i++) if (tmp = this.styles['.' + item]) matched += tmp + ';';
  }
  if (tmp = this.styles['#' + attrs.id]) matched += tmp + ';';
  return matched;
};
module.exports = CssHandler;
function parser(data, init) {
  this.data = data;
  this.floor = 0;
  this.i = 0;
  this.list = [];
  this.res = init;
  this.state = this.Space;
}
parser.prototype.parse = function () {
  for (var c; c = this.data[this.i]; this.i++) this.state(c);
  return this.res;
};
parser.prototype.section = function () {
  return this.data.substring(this.start, this.i);
};
// 状态机
parser.prototype.Space = function (c) {
  if (c == '.' || c == '#' || isLetter(c)) {
    this.start = this.i;
    this.state = this.Name;
  } else if (c == '/' && this.data[this.i + 1] == '*') this.Comment();else if (!cfg.blankChar[c] && c != ';') this.state = this.Ignore;
};
parser.prototype.Comment = function () {
  this.i = this.data.indexOf('*/', this.i) + 1;
  if (!this.i) this.i = this.data.length;
  this.state = this.Space;
};
parser.prototype.Ignore = function (c) {
  if (c == '{') this.floor++;else if (c == '}' && ! --this.floor) {
    this.list = [];
    this.state = this.Space;
  }
};
parser.prototype.Name = function (c) {
  if (cfg.blankChar[c]) {
    this.list.push(this.section());
    this.state = this.NameSpace;
  } else if (c == '{') {
    this.list.push(this.section());
    this.Content();
  } else if (c == ',') {
    this.list.push(this.section());
    this.Comma();
  } else if (!isLetter(c) && (c < '0' || c > '9') && c != '-' && c != '_') this.state = this.Ignore;
};
parser.prototype.NameSpace = function (c) {
  if (c == '{') this.Content();else if (c == ',') this.Comma();else if (!cfg.blankChar[c]) this.state = this.Ignore;
};
parser.prototype.Comma = function () {
  while (cfg.blankChar[this.data[++this.i]]);
  if (this.data[this.i] == '{') this.Content();else {
    this.start = this.i--;
    this.state = this.Name;
  }
};
parser.prototype.Content = function () {
  this.start = ++this.i;
  if ((this.i = this.data.indexOf('}', this.i)) == -1) this.i = this.data.length;
  var content = this.section();
  for (var i = 0, item; item = this.list[i++];) if (this.res[item]) this.res[item] += ';' + content;else this.res[item] = content;
  this.list = [];
  this.state = this.Space;
};

/***/ }),

/***/ 790:
/*!****************************************!*\
  !*** ./uview-ui/libs/util/province.js ***!
  \****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
var provinceData = [{
  "label": "北京市",
  "value": "11"
}, {
  "label": "天津市",
  "value": "12"
}, {
  "label": "河北省",
  "value": "13"
}, {
  "label": "山西省",
  "value": "14"
}, {
  "label": "内蒙古自治区",
  "value": "15"
}, {
  "label": "辽宁省",
  "value": "21"
}, {
  "label": "吉林省",
  "value": "22"
}, {
  "label": "黑龙江省",
  "value": "23"
}, {
  "label": "上海市",
  "value": "31"
}, {
  "label": "江苏省",
  "value": "32"
}, {
  "label": "浙江省",
  "value": "33"
}, {
  "label": "安徽省",
  "value": "34"
}, {
  "label": "福建省",
  "value": "35"
}, {
  "label": "江西省",
  "value": "36"
}, {
  "label": "山东省",
  "value": "37"
}, {
  "label": "河南省",
  "value": "41"
}, {
  "label": "湖北省",
  "value": "42"
}, {
  "label": "湖南省",
  "value": "43"
}, {
  "label": "广东省",
  "value": "44"
}, {
  "label": "广西壮族自治区",
  "value": "45"
}, {
  "label": "海南省",
  "value": "46"
}, {
  "label": "重庆市",
  "value": "50"
}, {
  "label": "四川省",
  "value": "51"
}, {
  "label": "贵州省",
  "value": "52"
}, {
  "label": "云南省",
  "value": "53"
}, {
  "label": "西藏自治区",
  "value": "54"
}, {
  "label": "陕西省",
  "value": "61"
}, {
  "label": "甘肃省",
  "value": "62"
}, {
  "label": "青海省",
  "value": "63"
}, {
  "label": "宁夏回族自治区",
  "value": "64"
}, {
  "label": "新疆维吾尔自治区",
  "value": "65"
}, {
  "label": "台湾",
  "value": "66"
}, {
  "label": "香港",
  "value": "67"
}, {
  "label": "澳门",
  "value": "68"
}];
/* harmony default export */ __webpack_exports__["default"] = (provinceData);

/***/ }),

/***/ 791:
/*!************************************!*\
  !*** ./uview-ui/libs/util/city.js ***!
  \************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
var cityData = [[{
  "label": "市辖区",
  "value": "1101"
}], [{
  "label": "市辖区",
  "value": "1201"
}], [{
  "label": "石家庄市",
  "value": "1301"
}, {
  "label": "唐山市",
  "value": "1302"
}, {
  "label": "秦皇岛市",
  "value": "1303"
}, {
  "label": "邯郸市",
  "value": "1304"
}, {
  "label": "邢台市",
  "value": "1305"
}, {
  "label": "保定市",
  "value": "1306"
}, {
  "label": "张家口市",
  "value": "1307"
}, {
  "label": "承德市",
  "value": "1308"
}, {
  "label": "沧州市",
  "value": "1309"
}, {
  "label": "廊坊市",
  "value": "1310"
}, {
  "label": "衡水市",
  "value": "1311"
}], [{
  "label": "太原市",
  "value": "1401"
}, {
  "label": "大同市",
  "value": "1402"
}, {
  "label": "阳泉市",
  "value": "1403"
}, {
  "label": "长治市",
  "value": "1404"
}, {
  "label": "晋城市",
  "value": "1405"
}, {
  "label": "朔州市",
  "value": "1406"
}, {
  "label": "晋中市",
  "value": "1407"
}, {
  "label": "运城市",
  "value": "1408"
}, {
  "label": "忻州市",
  "value": "1409"
}, {
  "label": "临汾市",
  "value": "1410"
}, {
  "label": "吕梁市",
  "value": "1411"
}], [{
  "label": "呼和浩特市",
  "value": "1501"
}, {
  "label": "包头市",
  "value": "1502"
}, {
  "label": "乌海市",
  "value": "1503"
}, {
  "label": "赤峰市",
  "value": "1504"
}, {
  "label": "通辽市",
  "value": "1505"
}, {
  "label": "鄂尔多斯市",
  "value": "1506"
}, {
  "label": "呼伦贝尔市",
  "value": "1507"
}, {
  "label": "巴彦淖尔市",
  "value": "1508"
}, {
  "label": "乌兰察布市",
  "value": "1509"
}, {
  "label": "兴安盟",
  "value": "1522"
}, {
  "label": "锡林郭勒盟",
  "value": "1525"
}, {
  "label": "阿拉善盟",
  "value": "1529"
}], [{
  "label": "沈阳市",
  "value": "2101"
}, {
  "label": "大连市",
  "value": "2102"
}, {
  "label": "鞍山市",
  "value": "2103"
}, {
  "label": "抚顺市",
  "value": "2104"
}, {
  "label": "本溪市",
  "value": "2105"
}, {
  "label": "丹东市",
  "value": "2106"
}, {
  "label": "锦州市",
  "value": "2107"
}, {
  "label": "营口市",
  "value": "2108"
}, {
  "label": "阜新市",
  "value": "2109"
}, {
  "label": "辽阳市",
  "value": "2110"
}, {
  "label": "盘锦市",
  "value": "2111"
}, {
  "label": "铁岭市",
  "value": "2112"
}, {
  "label": "朝阳市",
  "value": "2113"
}, {
  "label": "葫芦岛市",
  "value": "2114"
}], [{
  "label": "长春市",
  "value": "2201"
}, {
  "label": "吉林市",
  "value": "2202"
}, {
  "label": "四平市",
  "value": "2203"
}, {
  "label": "辽源市",
  "value": "2204"
}, {
  "label": "通化市",
  "value": "2205"
}, {
  "label": "白山市",
  "value": "2206"
}, {
  "label": "松原市",
  "value": "2207"
}, {
  "label": "白城市",
  "value": "2208"
}, {
  "label": "延边朝鲜族自治州",
  "value": "2224"
}], [{
  "label": "哈尔滨市",
  "value": "2301"
}, {
  "label": "齐齐哈尔市",
  "value": "2302"
}, {
  "label": "鸡西市",
  "value": "2303"
}, {
  "label": "鹤岗市",
  "value": "2304"
}, {
  "label": "双鸭山市",
  "value": "2305"
}, {
  "label": "大庆市",
  "value": "2306"
}, {
  "label": "伊春市",
  "value": "2307"
}, {
  "label": "佳木斯市",
  "value": "2308"
}, {
  "label": "七台河市",
  "value": "2309"
}, {
  "label": "牡丹江市",
  "value": "2310"
}, {
  "label": "黑河市",
  "value": "2311"
}, {
  "label": "绥化市",
  "value": "2312"
}, {
  "label": "大兴安岭地区",
  "value": "2327"
}], [{
  "label": "市辖区",
  "value": "3101"
}], [{
  "label": "南京市",
  "value": "3201"
}, {
  "label": "无锡市",
  "value": "3202"
}, {
  "label": "徐州市",
  "value": "3203"
}, {
  "label": "常州市",
  "value": "3204"
}, {
  "label": "苏州市",
  "value": "3205"
}, {
  "label": "南通市",
  "value": "3206"
}, {
  "label": "连云港市",
  "value": "3207"
}, {
  "label": "淮安市",
  "value": "3208"
}, {
  "label": "盐城市",
  "value": "3209"
}, {
  "label": "扬州市",
  "value": "3210"
}, {
  "label": "镇江市",
  "value": "3211"
}, {
  "label": "泰州市",
  "value": "3212"
}, {
  "label": "宿迁市",
  "value": "3213"
}], [{
  "label": "杭州市",
  "value": "3301"
}, {
  "label": "宁波市",
  "value": "3302"
}, {
  "label": "温州市",
  "value": "3303"
}, {
  "label": "嘉兴市",
  "value": "3304"
}, {
  "label": "湖州市",
  "value": "3305"
}, {
  "label": "绍兴市",
  "value": "3306"
}, {
  "label": "金华市",
  "value": "3307"
}, {
  "label": "衢州市",
  "value": "3308"
}, {
  "label": "舟山市",
  "value": "3309"
}, {
  "label": "台州市",
  "value": "3310"
}, {
  "label": "丽水市",
  "value": "3311"
}], [{
  "label": "合肥市",
  "value": "3401"
}, {
  "label": "芜湖市",
  "value": "3402"
}, {
  "label": "蚌埠市",
  "value": "3403"
}, {
  "label": "淮南市",
  "value": "3404"
}, {
  "label": "马鞍山市",
  "value": "3405"
}, {
  "label": "淮北市",
  "value": "3406"
}, {
  "label": "铜陵市",
  "value": "3407"
}, {
  "label": "安庆市",
  "value": "3408"
}, {
  "label": "黄山市",
  "value": "3410"
}, {
  "label": "滁州市",
  "value": "3411"
}, {
  "label": "阜阳市",
  "value": "3412"
}, {
  "label": "宿州市",
  "value": "3413"
}, {
  "label": "六安市",
  "value": "3415"
}, {
  "label": "亳州市",
  "value": "3416"
}, {
  "label": "池州市",
  "value": "3417"
}, {
  "label": "宣城市",
  "value": "3418"
}], [{
  "label": "福州市",
  "value": "3501"
}, {
  "label": "厦门市",
  "value": "3502"
}, {
  "label": "莆田市",
  "value": "3503"
}, {
  "label": "三明市",
  "value": "3504"
}, {
  "label": "泉州市",
  "value": "3505"
}, {
  "label": "漳州市",
  "value": "3506"
}, {
  "label": "南平市",
  "value": "3507"
}, {
  "label": "龙岩市",
  "value": "3508"
}, {
  "label": "宁德市",
  "value": "3509"
}], [{
  "label": "南昌市",
  "value": "3601"
}, {
  "label": "景德镇市",
  "value": "3602"
}, {
  "label": "萍乡市",
  "value": "3603"
}, {
  "label": "九江市",
  "value": "3604"
}, {
  "label": "新余市",
  "value": "3605"
}, {
  "label": "鹰潭市",
  "value": "3606"
}, {
  "label": "赣州市",
  "value": "3607"
}, {
  "label": "吉安市",
  "value": "3608"
}, {
  "label": "宜春市",
  "value": "3609"
}, {
  "label": "抚州市",
  "value": "3610"
}, {
  "label": "上饶市",
  "value": "3611"
}], [{
  "label": "济南市",
  "value": "3701"
}, {
  "label": "青岛市",
  "value": "3702"
}, {
  "label": "淄博市",
  "value": "3703"
}, {
  "label": "枣庄市",
  "value": "3704"
}, {
  "label": "东营市",
  "value": "3705"
}, {
  "label": "烟台市",
  "value": "3706"
}, {
  "label": "潍坊市",
  "value": "3707"
}, {
  "label": "济宁市",
  "value": "3708"
}, {
  "label": "泰安市",
  "value": "3709"
}, {
  "label": "威海市",
  "value": "3710"
}, {
  "label": "日照市",
  "value": "3711"
}, {
  "label": "莱芜市",
  "value": "3712"
}, {
  "label": "临沂市",
  "value": "3713"
}, {
  "label": "德州市",
  "value": "3714"
}, {
  "label": "聊城市",
  "value": "3715"
}, {
  "label": "滨州市",
  "value": "3716"
}, {
  "label": "菏泽市",
  "value": "3717"
}], [{
  "label": "郑州市",
  "value": "4101"
}, {
  "label": "开封市",
  "value": "4102"
}, {
  "label": "洛阳市",
  "value": "4103"
}, {
  "label": "平顶山市",
  "value": "4104"
}, {
  "label": "安阳市",
  "value": "4105"
}, {
  "label": "鹤壁市",
  "value": "4106"
}, {
  "label": "新乡市",
  "value": "4107"
}, {
  "label": "焦作市",
  "value": "4108"
}, {
  "label": "濮阳市",
  "value": "4109"
}, {
  "label": "许昌市",
  "value": "4110"
}, {
  "label": "漯河市",
  "value": "4111"
}, {
  "label": "三门峡市",
  "value": "4112"
}, {
  "label": "南阳市",
  "value": "4113"
}, {
  "label": "商丘市",
  "value": "4114"
}, {
  "label": "信阳市",
  "value": "4115"
}, {
  "label": "周口市",
  "value": "4116"
}, {
  "label": "驻马店市",
  "value": "4117"
}, {
  "label": "省直辖县级行政区划",
  "value": "4190"
}], [{
  "label": "武汉市",
  "value": "4201"
}, {
  "label": "黄石市",
  "value": "4202"
}, {
  "label": "十堰市",
  "value": "4203"
}, {
  "label": "宜昌市",
  "value": "4205"
}, {
  "label": "襄阳市",
  "value": "4206"
}, {
  "label": "鄂州市",
  "value": "4207"
}, {
  "label": "荆门市",
  "value": "4208"
}, {
  "label": "孝感市",
  "value": "4209"
}, {
  "label": "荆州市",
  "value": "4210"
}, {
  "label": "黄冈市",
  "value": "4211"
}, {
  "label": "咸宁市",
  "value": "4212"
}, {
  "label": "随州市",
  "value": "4213"
}, {
  "label": "恩施土家族苗族自治州",
  "value": "4228"
}, {
  "label": "省直辖县级行政区划",
  "value": "4290"
}], [{
  "label": "长沙市",
  "value": "4301"
}, {
  "label": "株洲市",
  "value": "4302"
}, {
  "label": "湘潭市",
  "value": "4303"
}, {
  "label": "衡阳市",
  "value": "4304"
}, {
  "label": "邵阳市",
  "value": "4305"
}, {
  "label": "岳阳市",
  "value": "4306"
}, {
  "label": "常德市",
  "value": "4307"
}, {
  "label": "张家界市",
  "value": "4308"
}, {
  "label": "益阳市",
  "value": "4309"
}, {
  "label": "郴州市",
  "value": "4310"
}, {
  "label": "永州市",
  "value": "4311"
}, {
  "label": "怀化市",
  "value": "4312"
}, {
  "label": "娄底市",
  "value": "4313"
}, {
  "label": "湘西土家族苗族自治州",
  "value": "4331"
}], [{
  "label": "广州市",
  "value": "4401"
}, {
  "label": "韶关市",
  "value": "4402"
}, {
  "label": "深圳市",
  "value": "4403"
}, {
  "label": "珠海市",
  "value": "4404"
}, {
  "label": "汕头市",
  "value": "4405"
}, {
  "label": "佛山市",
  "value": "4406"
}, {
  "label": "江门市",
  "value": "4407"
}, {
  "label": "湛江市",
  "value": "4408"
}, {
  "label": "茂名市",
  "value": "4409"
}, {
  "label": "肇庆市",
  "value": "4412"
}, {
  "label": "惠州市",
  "value": "4413"
}, {
  "label": "梅州市",
  "value": "4414"
}, {
  "label": "汕尾市",
  "value": "4415"
}, {
  "label": "河源市",
  "value": "4416"
}, {
  "label": "阳江市",
  "value": "4417"
}, {
  "label": "清远市",
  "value": "4418"
}, {
  "label": "东莞市",
  "value": "4419"
}, {
  "label": "中山市",
  "value": "4420"
}, {
  "label": "潮州市",
  "value": "4451"
}, {
  "label": "揭阳市",
  "value": "4452"
}, {
  "label": "云浮市",
  "value": "4453"
}], [{
  "label": "南宁市",
  "value": "4501"
}, {
  "label": "柳州市",
  "value": "4502"
}, {
  "label": "桂林市",
  "value": "4503"
}, {
  "label": "梧州市",
  "value": "4504"
}, {
  "label": "北海市",
  "value": "4505"
}, {
  "label": "防城港市",
  "value": "4506"
}, {
  "label": "钦州市",
  "value": "4507"
}, {
  "label": "贵港市",
  "value": "4508"
}, {
  "label": "玉林市",
  "value": "4509"
}, {
  "label": "百色市",
  "value": "4510"
}, {
  "label": "贺州市",
  "value": "4511"
}, {
  "label": "河池市",
  "value": "4512"
}, {
  "label": "来宾市",
  "value": "4513"
}, {
  "label": "崇左市",
  "value": "4514"
}], [{
  "label": "海口市",
  "value": "4601"
}, {
  "label": "三亚市",
  "value": "4602"
}, {
  "label": "三沙市",
  "value": "4603"
}, {
  "label": "儋州市",
  "value": "4604"
}, {
  "label": "省直辖县级行政区划",
  "value": "4690"
}], [{
  "label": "市辖区",
  "value": "5001"
}, {
  "label": "县",
  "value": "5002"
}], [{
  "label": "成都市",
  "value": "5101"
}, {
  "label": "自贡市",
  "value": "5103"
}, {
  "label": "攀枝花市",
  "value": "5104"
}, {
  "label": "泸州市",
  "value": "5105"
}, {
  "label": "德阳市",
  "value": "5106"
}, {
  "label": "绵阳市",
  "value": "5107"
}, {
  "label": "广元市",
  "value": "5108"
}, {
  "label": "遂宁市",
  "value": "5109"
}, {
  "label": "内江市",
  "value": "5110"
}, {
  "label": "乐山市",
  "value": "5111"
}, {
  "label": "南充市",
  "value": "5113"
}, {
  "label": "眉山市",
  "value": "5114"
}, {
  "label": "宜宾市",
  "value": "5115"
}, {
  "label": "广安市",
  "value": "5116"
}, {
  "label": "达州市",
  "value": "5117"
}, {
  "label": "雅安市",
  "value": "5118"
}, {
  "label": "巴中市",
  "value": "5119"
}, {
  "label": "资阳市",
  "value": "5120"
}, {
  "label": "阿坝藏族羌族自治州",
  "value": "5132"
}, {
  "label": "甘孜藏族自治州",
  "value": "5133"
}, {
  "label": "凉山彝族自治州",
  "value": "5134"
}], [{
  "label": "贵阳市",
  "value": "5201"
}, {
  "label": "六盘水市",
  "value": "5202"
}, {
  "label": "遵义市",
  "value": "5203"
}, {
  "label": "安顺市",
  "value": "5204"
}, {
  "label": "毕节市",
  "value": "5205"
}, {
  "label": "铜仁市",
  "value": "5206"
}, {
  "label": "黔西南布依族苗族自治州",
  "value": "5223"
}, {
  "label": "黔东南苗族侗族自治州",
  "value": "5226"
}, {
  "label": "黔南布依族苗族自治州",
  "value": "5227"
}], [{
  "label": "昆明市",
  "value": "5301"
}, {
  "label": "曲靖市",
  "value": "5303"
}, {
  "label": "玉溪市",
  "value": "5304"
}, {
  "label": "保山市",
  "value": "5305"
}, {
  "label": "昭通市",
  "value": "5306"
}, {
  "label": "丽江市",
  "value": "5307"
}, {
  "label": "普洱市",
  "value": "5308"
}, {
  "label": "临沧市",
  "value": "5309"
}, {
  "label": "楚雄彝族自治州",
  "value": "5323"
}, {
  "label": "红河哈尼族彝族自治州",
  "value": "5325"
}, {
  "label": "文山壮族苗族自治州",
  "value": "5326"
}, {
  "label": "西双版纳傣族自治州",
  "value": "5328"
}, {
  "label": "大理白族自治州",
  "value": "5329"
}, {
  "label": "德宏傣族景颇族自治州",
  "value": "5331"
}, {
  "label": "怒江傈僳族自治州",
  "value": "5333"
}, {
  "label": "迪庆藏族自治州",
  "value": "5334"
}], [{
  "label": "拉萨市",
  "value": "5401"
}, {
  "label": "日喀则市",
  "value": "5402"
}, {
  "label": "昌都市",
  "value": "5403"
}, {
  "label": "林芝市",
  "value": "5404"
}, {
  "label": "山南市",
  "value": "5405"
}, {
  "label": "那曲地区",
  "value": "5424"
}, {
  "label": "阿里地区",
  "value": "5425"
}], [{
  "label": "西安市",
  "value": "6101"
}, {
  "label": "铜川市",
  "value": "6102"
}, {
  "label": "宝鸡市",
  "value": "6103"
}, {
  "label": "咸阳市",
  "value": "6104"
}, {
  "label": "渭南市",
  "value": "6105"
}, {
  "label": "延安市",
  "value": "6106"
}, {
  "label": "汉中市",
  "value": "6107"
}, {
  "label": "榆林市",
  "value": "6108"
}, {
  "label": "安康市",
  "value": "6109"
}, {
  "label": "商洛市",
  "value": "6110"
}], [{
  "label": "兰州市",
  "value": "6201"
}, {
  "label": "嘉峪关市",
  "value": "6202"
}, {
  "label": "金昌市",
  "value": "6203"
}, {
  "label": "白银市",
  "value": "6204"
}, {
  "label": "天水市",
  "value": "6205"
}, {
  "label": "武威市",
  "value": "6206"
}, {
  "label": "张掖市",
  "value": "6207"
}, {
  "label": "平凉市",
  "value": "6208"
}, {
  "label": "酒泉市",
  "value": "6209"
}, {
  "label": "庆阳市",
  "value": "6210"
}, {
  "label": "定西市",
  "value": "6211"
}, {
  "label": "陇南市",
  "value": "6212"
}, {
  "label": "临夏回族自治州",
  "value": "6229"
}, {
  "label": "甘南藏族自治州",
  "value": "6230"
}], [{
  "label": "西宁市",
  "value": "6301"
}, {
  "label": "海东市",
  "value": "6302"
}, {
  "label": "海北藏族自治州",
  "value": "6322"
}, {
  "label": "黄南藏族自治州",
  "value": "6323"
}, {
  "label": "海南藏族自治州",
  "value": "6325"
}, {
  "label": "果洛藏族自治州",
  "value": "6326"
}, {
  "label": "玉树藏族自治州",
  "value": "6327"
}, {
  "label": "海西蒙古族藏族自治州",
  "value": "6328"
}], [{
  "label": "银川市",
  "value": "6401"
}, {
  "label": "石嘴山市",
  "value": "6402"
}, {
  "label": "吴忠市",
  "value": "6403"
}, {
  "label": "固原市",
  "value": "6404"
}, {
  "label": "中卫市",
  "value": "6405"
}], [{
  "label": "乌鲁木齐市",
  "value": "6501"
}, {
  "label": "克拉玛依市",
  "value": "6502"
}, {
  "label": "吐鲁番市",
  "value": "6504"
}, {
  "label": "哈密市",
  "value": "6505"
}, {
  "label": "昌吉回族自治州",
  "value": "6523"
}, {
  "label": "博尔塔拉蒙古自治州",
  "value": "6527"
}, {
  "label": "巴音郭楞蒙古自治州",
  "value": "6528"
}, {
  "label": "阿克苏地区",
  "value": "6529"
}, {
  "label": "克孜勒苏柯尔克孜自治州",
  "value": "6530"
}, {
  "label": "喀什地区",
  "value": "6531"
}, {
  "label": "和田地区",
  "value": "6532"
}, {
  "label": "伊犁哈萨克自治州",
  "value": "6540"
}, {
  "label": "塔城地区",
  "value": "6542"
}, {
  "label": "阿勒泰地区",
  "value": "6543"
}, {
  "label": "自治区直辖县级行政区划",
  "value": "6590"
}], [{
  "label": "台北",
  "value": "6601"
}, {
  "label": "高雄",
  "value": "6602"
}, {
  "label": "基隆",
  "value": "6603"
}, {
  "label": "台中",
  "value": "6604"
}, {
  "label": "台南",
  "value": "6605"
}, {
  "label": "新竹",
  "value": "6606"
}, {
  "label": "嘉义",
  "value": "6607"
}, {
  "label": "宜兰",
  "value": "6608"
}, {
  "label": "桃园",
  "value": "6609"
}, {
  "label": "苗栗",
  "value": "6610"
}, {
  "label": "彰化",
  "value": "6611"
}, {
  "label": "南投",
  "value": "6612"
}, {
  "label": "云林",
  "value": "6613"
}, {
  "label": "屏东",
  "value": "6614"
}, {
  "label": "台东",
  "value": "6615"
}, {
  "label": "花莲",
  "value": "6616"
}, {
  "label": "澎湖",
  "value": "6617"
}], [{
  "label": "香港岛",
  "value": "6701"
}, {
  "label": "九龙",
  "value": "6702"
}, {
  "label": "新界",
  "value": "6703"
}], [{
  "label": "澳门半岛",
  "value": "6801"
}, {
  "label": "氹仔岛",
  "value": "6802"
}, {
  "label": "路环岛",
  "value": "6803"
}, {
  "label": "路氹城",
  "value": "6804"
}]];
/* harmony default export */ __webpack_exports__["default"] = (cityData);

/***/ }),

/***/ 792:
/*!************************************!*\
  !*** ./uview-ui/libs/util/area.js ***!
  \************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
var areaData = [[[{
  "label": "东城区",
  "value": "110101"
}, {
  "label": "西城区",
  "value": "110102"
}, {
  "label": "朝阳区",
  "value": "110105"
}, {
  "label": "丰台区",
  "value": "110106"
}, {
  "label": "石景山区",
  "value": "110107"
}, {
  "label": "海淀区",
  "value": "110108"
}, {
  "label": "门头沟区",
  "value": "110109"
}, {
  "label": "房山区",
  "value": "110111"
}, {
  "label": "通州区",
  "value": "110112"
}, {
  "label": "顺义区",
  "value": "110113"
}, {
  "label": "昌平区",
  "value": "110114"
}, {
  "label": "大兴区",
  "value": "110115"
}, {
  "label": "怀柔区",
  "value": "110116"
}, {
  "label": "平谷区",
  "value": "110117"
}, {
  "label": "密云区",
  "value": "110118"
}, {
  "label": "延庆区",
  "value": "110119"
}]], [[{
  "label": "和平区",
  "value": "120101"
}, {
  "label": "河东区",
  "value": "120102"
}, {
  "label": "河西区",
  "value": "120103"
}, {
  "label": "南开区",
  "value": "120104"
}, {
  "label": "河北区",
  "value": "120105"
}, {
  "label": "红桥区",
  "value": "120106"
}, {
  "label": "东丽区",
  "value": "120110"
}, {
  "label": "西青区",
  "value": "120111"
}, {
  "label": "津南区",
  "value": "120112"
}, {
  "label": "北辰区",
  "value": "120113"
}, {
  "label": "武清区",
  "value": "120114"
}, {
  "label": "宝坻区",
  "value": "120115"
}, {
  "label": "滨海新区",
  "value": "120116"
}, {
  "label": "宁河区",
  "value": "120117"
}, {
  "label": "静海区",
  "value": "120118"
}, {
  "label": "蓟州区",
  "value": "120119"
}]], [[{
  "label": "长安区",
  "value": "130102"
}, {
  "label": "桥西区",
  "value": "130104"
}, {
  "label": "新华区",
  "value": "130105"
}, {
  "label": "井陉矿区",
  "value": "130107"
}, {
  "label": "裕华区",
  "value": "130108"
}, {
  "label": "藁城区",
  "value": "130109"
}, {
  "label": "鹿泉区",
  "value": "130110"
}, {
  "label": "栾城区",
  "value": "130111"
}, {
  "label": "井陉县",
  "value": "130121"
}, {
  "label": "正定县",
  "value": "130123"
}, {
  "label": "行唐县",
  "value": "130125"
}, {
  "label": "灵寿县",
  "value": "130126"
}, {
  "label": "高邑县",
  "value": "130127"
}, {
  "label": "深泽县",
  "value": "130128"
}, {
  "label": "赞皇县",
  "value": "130129"
}, {
  "label": "无极县",
  "value": "130130"
}, {
  "label": "平山县",
  "value": "130131"
}, {
  "label": "元氏县",
  "value": "130132"
}, {
  "label": "赵县",
  "value": "130133"
}, {
  "label": "石家庄高新技术产业开发区",
  "value": "130171"
}, {
  "label": "石家庄循环化工园区",
  "value": "130172"
}, {
  "label": "辛集市",
  "value": "130181"
}, {
  "label": "晋州市",
  "value": "130183"
}, {
  "label": "新乐市",
  "value": "130184"
}], [{
  "label": "路南区",
  "value": "130202"
}, {
  "label": "路北区",
  "value": "130203"
}, {
  "label": "古冶区",
  "value": "130204"
}, {
  "label": "开平区",
  "value": "130205"
}, {
  "label": "丰南区",
  "value": "130207"
}, {
  "label": "丰润区",
  "value": "130208"
}, {
  "label": "曹妃甸区",
  "value": "130209"
}, {
  "label": "滦县",
  "value": "130223"
}, {
  "label": "滦南县",
  "value": "130224"
}, {
  "label": "乐亭县",
  "value": "130225"
}, {
  "label": "迁西县",
  "value": "130227"
}, {
  "label": "玉田县",
  "value": "130229"
}, {
  "label": "唐山市芦台经济技术开发区",
  "value": "130271"
}, {
  "label": "唐山市汉沽管理区",
  "value": "130272"
}, {
  "label": "唐山高新技术产业开发区",
  "value": "130273"
}, {
  "label": "河北唐山海港经济开发区",
  "value": "130274"
}, {
  "label": "遵化市",
  "value": "130281"
}, {
  "label": "迁安市",
  "value": "130283"
}], [{
  "label": "海港区",
  "value": "130302"
}, {
  "label": "山海关区",
  "value": "130303"
}, {
  "label": "北戴河区",
  "value": "130304"
}, {
  "label": "抚宁区",
  "value": "130306"
}, {
  "label": "青龙满族自治县",
  "value": "130321"
}, {
  "label": "昌黎县",
  "value": "130322"
}, {
  "label": "卢龙县",
  "value": "130324"
}, {
  "label": "秦皇岛市经济技术开发区",
  "value": "130371"
}, {
  "label": "北戴河新区",
  "value": "130372"
}], [{
  "label": "邯山区",
  "value": "130402"
}, {
  "label": "丛台区",
  "value": "130403"
}, {
  "label": "复兴区",
  "value": "130404"
}, {
  "label": "峰峰矿区",
  "value": "130406"
}, {
  "label": "肥乡区",
  "value": "130407"
}, {
  "label": "永年区",
  "value": "130408"
}, {
  "label": "临漳县",
  "value": "130423"
}, {
  "label": "成安县",
  "value": "130424"
}, {
  "label": "大名县",
  "value": "130425"
}, {
  "label": "涉县",
  "value": "130426"
}, {
  "label": "磁县",
  "value": "130427"
}, {
  "label": "邱县",
  "value": "130430"
}, {
  "label": "鸡泽县",
  "value": "130431"
}, {
  "label": "广平县",
  "value": "130432"
}, {
  "label": "馆陶县",
  "value": "130433"
}, {
  "label": "魏县",
  "value": "130434"
}, {
  "label": "曲周县",
  "value": "130435"
}, {
  "label": "邯郸经济技术开发区",
  "value": "130471"
}, {
  "label": "邯郸冀南新区",
  "value": "130473"
}, {
  "label": "武安市",
  "value": "130481"
}], [{
  "label": "桥东区",
  "value": "130502"
}, {
  "label": "桥西区",
  "value": "130503"
}, {
  "label": "邢台县",
  "value": "130521"
}, {
  "label": "临城县",
  "value": "130522"
}, {
  "label": "内丘县",
  "value": "130523"
}, {
  "label": "柏乡县",
  "value": "130524"
}, {
  "label": "隆尧县",
  "value": "130525"
}, {
  "label": "任县",
  "value": "130526"
}, {
  "label": "南和县",
  "value": "130527"
}, {
  "label": "宁晋县",
  "value": "130528"
}, {
  "label": "巨鹿县",
  "value": "130529"
}, {
  "label": "新河县",
  "value": "130530"
}, {
  "label": "广宗县",
  "value": "130531"
}, {
  "label": "平乡县",
  "value": "130532"
}, {
  "label": "威县",
  "value": "130533"
}, {
  "label": "清河县",
  "value": "130534"
}, {
  "label": "临西县",
  "value": "130535"
}, {
  "label": "河北邢台经济开发区",
  "value": "130571"
}, {
  "label": "南宫市",
  "value": "130581"
}, {
  "label": "沙河市",
  "value": "130582"
}], [{
  "label": "竞秀区",
  "value": "130602"
}, {
  "label": "莲池区",
  "value": "130606"
}, {
  "label": "满城区",
  "value": "130607"
}, {
  "label": "清苑区",
  "value": "130608"
}, {
  "label": "徐水区",
  "value": "130609"
}, {
  "label": "涞水县",
  "value": "130623"
}, {
  "label": "阜平县",
  "value": "130624"
}, {
  "label": "定兴县",
  "value": "130626"
}, {
  "label": "唐县",
  "value": "130627"
}, {
  "label": "高阳县",
  "value": "130628"
}, {
  "label": "容城县",
  "value": "130629"
}, {
  "label": "涞源县",
  "value": "130630"
}, {
  "label": "望都县",
  "value": "130631"
}, {
  "label": "安新县",
  "value": "130632"
}, {
  "label": "易县",
  "value": "130633"
}, {
  "label": "曲阳县",
  "value": "130634"
}, {
  "label": "蠡县",
  "value": "130635"
}, {
  "label": "顺平县",
  "value": "130636"
}, {
  "label": "博野县",
  "value": "130637"
}, {
  "label": "雄县",
  "value": "130638"
}, {
  "label": "保定高新技术产业开发区",
  "value": "130671"
}, {
  "label": "保定白沟新城",
  "value": "130672"
}, {
  "label": "涿州市",
  "value": "130681"
}, {
  "label": "定州市",
  "value": "130682"
}, {
  "label": "安国市",
  "value": "130683"
}, {
  "label": "高碑店市",
  "value": "130684"
}], [{
  "label": "桥东区",
  "value": "130702"
}, {
  "label": "桥西区",
  "value": "130703"
}, {
  "label": "宣化区",
  "value": "130705"
}, {
  "label": "下花园区",
  "value": "130706"
}, {
  "label": "万全区",
  "value": "130708"
}, {
  "label": "崇礼区",
  "value": "130709"
}, {
  "label": "张北县",
  "value": "130722"
}, {
  "label": "康保县",
  "value": "130723"
}, {
  "label": "沽源县",
  "value": "130724"
}, {
  "label": "尚义县",
  "value": "130725"
}, {
  "label": "蔚县",
  "value": "130726"
}, {
  "label": "阳原县",
  "value": "130727"
}, {
  "label": "怀安县",
  "value": "130728"
}, {
  "label": "怀来县",
  "value": "130730"
}, {
  "label": "涿鹿县",
  "value": "130731"
}, {
  "label": "赤城县",
  "value": "130732"
}, {
  "label": "张家口市高新技术产业开发区",
  "value": "130771"
}, {
  "label": "张家口市察北管理区",
  "value": "130772"
}, {
  "label": "张家口市塞北管理区",
  "value": "130773"
}], [{
  "label": "双桥区",
  "value": "130802"
}, {
  "label": "双滦区",
  "value": "130803"
}, {
  "label": "鹰手营子矿区",
  "value": "130804"
}, {
  "label": "承德县",
  "value": "130821"
}, {
  "label": "兴隆县",
  "value": "130822"
}, {
  "label": "滦平县",
  "value": "130824"
}, {
  "label": "隆化县",
  "value": "130825"
}, {
  "label": "丰宁满族自治县",
  "value": "130826"
}, {
  "label": "宽城满族自治县",
  "value": "130827"
}, {
  "label": "围场满族蒙古族自治县",
  "value": "130828"
}, {
  "label": "承德高新技术产业开发区",
  "value": "130871"
}, {
  "label": "平泉市",
  "value": "130881"
}], [{
  "label": "新华区",
  "value": "130902"
}, {
  "label": "运河区",
  "value": "130903"
}, {
  "label": "沧县",
  "value": "130921"
}, {
  "label": "青县",
  "value": "130922"
}, {
  "label": "东光县",
  "value": "130923"
}, {
  "label": "海兴县",
  "value": "130924"
}, {
  "label": "盐山县",
  "value": "130925"
}, {
  "label": "肃宁县",
  "value": "130926"
}, {
  "label": "南皮县",
  "value": "130927"
}, {
  "label": "吴桥县",
  "value": "130928"
}, {
  "label": "献县",
  "value": "130929"
}, {
  "label": "孟村回族自治县",
  "value": "130930"
}, {
  "label": "河北沧州经济开发区",
  "value": "130971"
}, {
  "label": "沧州高新技术产业开发区",
  "value": "130972"
}, {
  "label": "沧州渤海新区",
  "value": "130973"
}, {
  "label": "泊头市",
  "value": "130981"
}, {
  "label": "任丘市",
  "value": "130982"
}, {
  "label": "黄骅市",
  "value": "130983"
}, {
  "label": "河间市",
  "value": "130984"
}], [{
  "label": "安次区",
  "value": "131002"
}, {
  "label": "广阳区",
  "value": "131003"
}, {
  "label": "固安县",
  "value": "131022"
}, {
  "label": "永清县",
  "value": "131023"
}, {
  "label": "香河县",
  "value": "131024"
}, {
  "label": "大城县",
  "value": "131025"
}, {
  "label": "文安县",
  "value": "131026"
}, {
  "label": "大厂回族自治县",
  "value": "131028"
}, {
  "label": "廊坊经济技术开发区",
  "value": "131071"
}, {
  "label": "霸州市",
  "value": "131081"
}, {
  "label": "三河市",
  "value": "131082"
}], [{
  "label": "桃城区",
  "value": "131102"
}, {
  "label": "冀州区",
  "value": "131103"
}, {
  "label": "枣强县",
  "value": "131121"
}, {
  "label": "武邑县",
  "value": "131122"
}, {
  "label": "武强县",
  "value": "131123"
}, {
  "label": "饶阳县",
  "value": "131124"
}, {
  "label": "安平县",
  "value": "131125"
}, {
  "label": "故城县",
  "value": "131126"
}, {
  "label": "景县",
  "value": "131127"
}, {
  "label": "阜城县",
  "value": "131128"
}, {
  "label": "河北衡水经济开发区",
  "value": "131171"
}, {
  "label": "衡水滨湖新区",
  "value": "131172"
}, {
  "label": "深州市",
  "value": "131182"
}]], [[{
  "label": "小店区",
  "value": "140105"
}, {
  "label": "迎泽区",
  "value": "140106"
}, {
  "label": "杏花岭区",
  "value": "140107"
}, {
  "label": "尖草坪区",
  "value": "140108"
}, {
  "label": "万柏林区",
  "value": "140109"
}, {
  "label": "晋源区",
  "value": "140110"
}, {
  "label": "清徐县",
  "value": "140121"
}, {
  "label": "阳曲县",
  "value": "140122"
}, {
  "label": "娄烦县",
  "value": "140123"
}, {
  "label": "山西转型综合改革示范区",
  "value": "140171"
}, {
  "label": "古交市",
  "value": "140181"
}], [{
  "label": "城区",
  "value": "140202"
}, {
  "label": "矿区",
  "value": "140203"
}, {
  "label": "南郊区",
  "value": "140211"
}, {
  "label": "新荣区",
  "value": "140212"
}, {
  "label": "阳高县",
  "value": "140221"
}, {
  "label": "天镇县",
  "value": "140222"
}, {
  "label": "广灵县",
  "value": "140223"
}, {
  "label": "灵丘县",
  "value": "140224"
}, {
  "label": "浑源县",
  "value": "140225"
}, {
  "label": "左云县",
  "value": "140226"
}, {
  "label": "大同县",
  "value": "140227"
}, {
  "label": "山西大同经济开发区",
  "value": "140271"
}], [{
  "label": "城区",
  "value": "140302"
}, {
  "label": "矿区",
  "value": "140303"
}, {
  "label": "郊区",
  "value": "140311"
}, {
  "label": "平定县",
  "value": "140321"
}, {
  "label": "盂县",
  "value": "140322"
}, {
  "label": "山西阳泉经济开发区",
  "value": "140371"
}], [{
  "label": "城区",
  "value": "140402"
}, {
  "label": "郊区",
  "value": "140411"
}, {
  "label": "长治县",
  "value": "140421"
}, {
  "label": "襄垣县",
  "value": "140423"
}, {
  "label": "屯留县",
  "value": "140424"
}, {
  "label": "平顺县",
  "value": "140425"
}, {
  "label": "黎城县",
  "value": "140426"
}, {
  "label": "壶关县",
  "value": "140427"
}, {
  "label": "长子县",
  "value": "140428"
}, {
  "label": "武乡县",
  "value": "140429"
}, {
  "label": "沁县",
  "value": "140430"
}, {
  "label": "沁源县",
  "value": "140431"
}, {
  "label": "山西长治高新技术产业园区",
  "value": "140471"
}, {
  "label": "潞城市",
  "value": "140481"
}], [{
  "label": "城区",
  "value": "140502"
}, {
  "label": "沁水县",
  "value": "140521"
}, {
  "label": "阳城县",
  "value": "140522"
}, {
  "label": "陵川县",
  "value": "140524"
}, {
  "label": "泽州县",
  "value": "140525"
}, {
  "label": "高平市",
  "value": "140581"
}], [{
  "label": "朔城区",
  "value": "140602"
}, {
  "label": "平鲁区",
  "value": "140603"
}, {
  "label": "山阴县",
  "value": "140621"
}, {
  "label": "应县",
  "value": "140622"
}, {
  "label": "右玉县",
  "value": "140623"
}, {
  "label": "怀仁县",
  "value": "140624"
}, {
  "label": "山西朔州经济开发区",
  "value": "140671"
}], [{
  "label": "榆次区",
  "value": "140702"
}, {
  "label": "榆社县",
  "value": "140721"
}, {
  "label": "左权县",
  "value": "140722"
}, {
  "label": "和顺县",
  "value": "140723"
}, {
  "label": "昔阳县",
  "value": "140724"
}, {
  "label": "寿阳县",
  "value": "140725"
}, {
  "label": "太谷县",
  "value": "140726"
}, {
  "label": "祁县",
  "value": "140727"
}, {
  "label": "平遥县",
  "value": "140728"
}, {
  "label": "灵石县",
  "value": "140729"
}, {
  "label": "介休市",
  "value": "140781"
}], [{
  "label": "盐湖区",
  "value": "140802"
}, {
  "label": "临猗县",
  "value": "140821"
}, {
  "label": "万荣县",
  "value": "140822"
}, {
  "label": "闻喜县",
  "value": "140823"
}, {
  "label": "稷山县",
  "value": "140824"
}, {
  "label": "新绛县",
  "value": "140825"
}, {
  "label": "绛县",
  "value": "140826"
}, {
  "label": "垣曲县",
  "value": "140827"
}, {
  "label": "夏县",
  "value": "140828"
}, {
  "label": "平陆县",
  "value": "140829"
}, {
  "label": "芮城县",
  "value": "140830"
}, {
  "label": "永济市",
  "value": "140881"
}, {
  "label": "河津市",
  "value": "140882"
}], [{
  "label": "忻府区",
  "value": "140902"
}, {
  "label": "定襄县",
  "value": "140921"
}, {
  "label": "五台县",
  "value": "140922"
}, {
  "label": "代县",
  "value": "140923"
}, {
  "label": "繁峙县",
  "value": "140924"
}, {
  "label": "宁武县",
  "value": "140925"
}, {
  "label": "静乐县",
  "value": "140926"
}, {
  "label": "神池县",
  "value": "140927"
}, {
  "label": "五寨县",
  "value": "140928"
}, {
  "label": "岢岚县",
  "value": "140929"
}, {
  "label": "河曲县",
  "value": "140930"
}, {
  "label": "保德县",
  "value": "140931"
}, {
  "label": "偏关县",
  "value": "140932"
}, {
  "label": "五台山风景名胜区",
  "value": "140971"
}, {
  "label": "原平市",
  "value": "140981"
}], [{
  "label": "尧都区",
  "value": "141002"
}, {
  "label": "曲沃县",
  "value": "141021"
}, {
  "label": "翼城县",
  "value": "141022"
}, {
  "label": "襄汾县",
  "value": "141023"
}, {
  "label": "洪洞县",
  "value": "141024"
}, {
  "label": "古县",
  "value": "141025"
}, {
  "label": "安泽县",
  "value": "141026"
}, {
  "label": "浮山县",
  "value": "141027"
}, {
  "label": "吉县",
  "value": "141028"
}, {
  "label": "乡宁县",
  "value": "141029"
}, {
  "label": "大宁县",
  "value": "141030"
}, {
  "label": "隰县",
  "value": "141031"
}, {
  "label": "永和县",
  "value": "141032"
}, {
  "label": "蒲县",
  "value": "141033"
}, {
  "label": "汾西县",
  "value": "141034"
}, {
  "label": "侯马市",
  "value": "141081"
}, {
  "label": "霍州市",
  "value": "141082"
}], [{
  "label": "离石区",
  "value": "141102"
}, {
  "label": "文水县",
  "value": "141121"
}, {
  "label": "交城县",
  "value": "141122"
}, {
  "label": "兴县",
  "value": "141123"
}, {
  "label": "临县",
  "value": "141124"
}, {
  "label": "柳林县",
  "value": "141125"
}, {
  "label": "石楼县",
  "value": "141126"
}, {
  "label": "岚县",
  "value": "141127"
}, {
  "label": "方山县",
  "value": "141128"
}, {
  "label": "中阳县",
  "value": "141129"
}, {
  "label": "交口县",
  "value": "141130"
}, {
  "label": "孝义市",
  "value": "141181"
}, {
  "label": "汾阳市",
  "value": "141182"
}]], [[{
  "label": "新城区",
  "value": "150102"
}, {
  "label": "回民区",
  "value": "150103"
}, {
  "label": "玉泉区",
  "value": "150104"
}, {
  "label": "赛罕区",
  "value": "150105"
}, {
  "label": "土默特左旗",
  "value": "150121"
}, {
  "label": "托克托县",
  "value": "150122"
}, {
  "label": "和林格尔县",
  "value": "150123"
}, {
  "label": "清水河县",
  "value": "150124"
}, {
  "label": "武川县",
  "value": "150125"
}, {
  "label": "呼和浩特金海工业园区",
  "value": "150171"
}, {
  "label": "呼和浩特经济技术开发区",
  "value": "150172"
}], [{
  "label": "东河区",
  "value": "150202"
}, {
  "label": "昆都仑区",
  "value": "150203"
}, {
  "label": "青山区",
  "value": "150204"
}, {
  "label": "石拐区",
  "value": "150205"
}, {
  "label": "白云鄂博矿区",
  "value": "150206"
}, {
  "label": "九原区",
  "value": "150207"
}, {
  "label": "土默特右旗",
  "value": "150221"
}, {
  "label": "固阳县",
  "value": "150222"
}, {
  "label": "达尔罕茂明安联合旗",
  "value": "150223"
}, {
  "label": "包头稀土高新技术产业开发区",
  "value": "150271"
}], [{
  "label": "海勃湾区",
  "value": "150302"
}, {
  "label": "海南区",
  "value": "150303"
}, {
  "label": "乌达区",
  "value": "150304"
}], [{
  "label": "红山区",
  "value": "150402"
}, {
  "label": "元宝山区",
  "value": "150403"
}, {
  "label": "松山区",
  "value": "150404"
}, {
  "label": "阿鲁科尔沁旗",
  "value": "150421"
}, {
  "label": "巴林左旗",
  "value": "150422"
}, {
  "label": "巴林右旗",
  "value": "150423"
}, {
  "label": "林西县",
  "value": "150424"
}, {
  "label": "克什克腾旗",
  "value": "150425"
}, {
  "label": "翁牛特旗",
  "value": "150426"
}, {
  "label": "喀喇沁旗",
  "value": "150428"
}, {
  "label": "宁城县",
  "value": "150429"
}, {
  "label": "敖汉旗",
  "value": "150430"
}], [{
  "label": "科尔沁区",
  "value": "150502"
}, {
  "label": "科尔沁左翼中旗",
  "value": "150521"
}, {
  "label": "科尔沁左翼后旗",
  "value": "150522"
}, {
  "label": "开鲁县",
  "value": "150523"
}, {
  "label": "库伦旗",
  "value": "150524"
}, {
  "label": "奈曼旗",
  "value": "150525"
}, {
  "label": "扎鲁特旗",
  "value": "150526"
}, {
  "label": "通辽经济技术开发区",
  "value": "150571"
}, {
  "label": "霍林郭勒市",
  "value": "150581"
}], [{
  "label": "东胜区",
  "value": "150602"
}, {
  "label": "康巴什区",
  "value": "150603"
}, {
  "label": "达拉特旗",
  "value": "150621"
}, {
  "label": "准格尔旗",
  "value": "150622"
}, {
  "label": "鄂托克前旗",
  "value": "150623"
}, {
  "label": "鄂托克旗",
  "value": "150624"
}, {
  "label": "杭锦旗",
  "value": "150625"
}, {
  "label": "乌审旗",
  "value": "150626"
}, {
  "label": "伊金霍洛旗",
  "value": "150627"
}], [{
  "label": "海拉尔区",
  "value": "150702"
}, {
  "label": "扎赉诺尔区",
  "value": "150703"
}, {
  "label": "阿荣旗",
  "value": "150721"
}, {
  "label": "莫力达瓦达斡尔族自治旗",
  "value": "150722"
}, {
  "label": "鄂伦春自治旗",
  "value": "150723"
}, {
  "label": "鄂温克族自治旗",
  "value": "150724"
}, {
  "label": "陈巴尔虎旗",
  "value": "150725"
}, {
  "label": "新巴尔虎左旗",
  "value": "150726"
}, {
  "label": "新巴尔虎右旗",
  "value": "150727"
}, {
  "label": "满洲里市",
  "value": "150781"
}, {
  "label": "牙克石市",
  "value": "150782"
}, {
  "label": "扎兰屯市",
  "value": "150783"
}, {
  "label": "额尔古纳市",
  "value": "150784"
}, {
  "label": "根河市",
  "value": "150785"
}], [{
  "label": "临河区",
  "value": "150802"
}, {
  "label": "五原县",
  "value": "150821"
}, {
  "label": "磴口县",
  "value": "150822"
}, {
  "label": "乌拉特前旗",
  "value": "150823"
}, {
  "label": "乌拉特中旗",
  "value": "150824"
}, {
  "label": "乌拉特后旗",
  "value": "150825"
}, {
  "label": "杭锦后旗",
  "value": "150826"
}], [{
  "label": "集宁区",
  "value": "150902"
}, {
  "label": "卓资县",
  "value": "150921"
}, {
  "label": "化德县",
  "value": "150922"
}, {
  "label": "商都县",
  "value": "150923"
}, {
  "label": "兴和县",
  "value": "150924"
}, {
  "label": "凉城县",
  "value": "150925"
}, {
  "label": "察哈尔右翼前旗",
  "value": "150926"
}, {
  "label": "察哈尔右翼中旗",
  "value": "150927"
}, {
  "label": "察哈尔右翼后旗",
  "value": "150928"
}, {
  "label": "四子王旗",
  "value": "150929"
}, {
  "label": "丰镇市",
  "value": "150981"
}], [{
  "label": "乌兰浩特市",
  "value": "152201"
}, {
  "label": "阿尔山市",
  "value": "152202"
}, {
  "label": "科尔沁右翼前旗",
  "value": "152221"
}, {
  "label": "科尔沁右翼中旗",
  "value": "152222"
}, {
  "label": "扎赉特旗",
  "value": "152223"
}, {
  "label": "突泉县",
  "value": "152224"
}], [{
  "label": "二连浩特市",
  "value": "152501"
}, {
  "label": "锡林浩特市",
  "value": "152502"
}, {
  "label": "阿巴嘎旗",
  "value": "152522"
}, {
  "label": "苏尼特左旗",
  "value": "152523"
}, {
  "label": "苏尼特右旗",
  "value": "152524"
}, {
  "label": "东乌珠穆沁旗",
  "value": "152525"
}, {
  "label": "西乌珠穆沁旗",
  "value": "152526"
}, {
  "label": "太仆寺旗",
  "value": "152527"
}, {
  "label": "镶黄旗",
  "value": "152528"
}, {
  "label": "正镶白旗",
  "value": "152529"
}, {
  "label": "正蓝旗",
  "value": "152530"
}, {
  "label": "多伦县",
  "value": "152531"
}, {
  "label": "乌拉盖管委会",
  "value": "152571"
}], [{
  "label": "阿拉善左旗",
  "value": "152921"
}, {
  "label": "阿拉善右旗",
  "value": "152922"
}, {
  "label": "额济纳旗",
  "value": "152923"
}, {
  "label": "内蒙古阿拉善经济开发区",
  "value": "152971"
}]], [[{
  "label": "和平区",
  "value": "210102"
}, {
  "label": "沈河区",
  "value": "210103"
}, {
  "label": "大东区",
  "value": "210104"
}, {
  "label": "皇姑区",
  "value": "210105"
}, {
  "label": "铁西区",
  "value": "210106"
}, {
  "label": "苏家屯区",
  "value": "210111"
}, {
  "label": "浑南区",
  "value": "210112"
}, {
  "label": "沈北新区",
  "value": "210113"
}, {
  "label": "于洪区",
  "value": "210114"
}, {
  "label": "辽中区",
  "value": "210115"
}, {
  "label": "康平县",
  "value": "210123"
}, {
  "label": "法库县",
  "value": "210124"
}, {
  "label": "新民市",
  "value": "210181"
}], [{
  "label": "中山区",
  "value": "210202"
}, {
  "label": "西岗区",
  "value": "210203"
}, {
  "label": "沙河口区",
  "value": "210204"
}, {
  "label": "甘井子区",
  "value": "210211"
}, {
  "label": "旅顺口区",
  "value": "210212"
}, {
  "label": "金州区",
  "value": "210213"
}, {
  "label": "普兰店区",
  "value": "210214"
}, {
  "label": "长海县",
  "value": "210224"
}, {
  "label": "瓦房店市",
  "value": "210281"
}, {
  "label": "庄河市",
  "value": "210283"
}], [{
  "label": "铁东区",
  "value": "210302"
}, {
  "label": "铁西区",
  "value": "210303"
}, {
  "label": "立山区",
  "value": "210304"
}, {
  "label": "千山区",
  "value": "210311"
}, {
  "label": "台安县",
  "value": "210321"
}, {
  "label": "岫岩满族自治县",
  "value": "210323"
}, {
  "label": "海城市",
  "value": "210381"
}], [{
  "label": "新抚区",
  "value": "210402"
}, {
  "label": "东洲区",
  "value": "210403"
}, {
  "label": "望花区",
  "value": "210404"
}, {
  "label": "顺城区",
  "value": "210411"
}, {
  "label": "抚顺县",
  "value": "210421"
}, {
  "label": "新宾满族自治县",
  "value": "210422"
}, {
  "label": "清原满族自治县",
  "value": "210423"
}], [{
  "label": "平山区",
  "value": "210502"
}, {
  "label": "溪湖区",
  "value": "210503"
}, {
  "label": "明山区",
  "value": "210504"
}, {
  "label": "南芬区",
  "value": "210505"
}, {
  "label": "本溪满族自治县",
  "value": "210521"
}, {
  "label": "桓仁满族自治县",
  "value": "210522"
}], [{
  "label": "元宝区",
  "value": "210602"
}, {
  "label": "振兴区",
  "value": "210603"
}, {
  "label": "振安区",
  "value": "210604"
}, {
  "label": "宽甸满族自治县",
  "value": "210624"
}, {
  "label": "东港市",
  "value": "210681"
}, {
  "label": "凤城市",
  "value": "210682"
}], [{
  "label": "古塔区",
  "value": "210702"
}, {
  "label": "凌河区",
  "value": "210703"
}, {
  "label": "太和区",
  "value": "210711"
}, {
  "label": "黑山县",
  "value": "210726"
}, {
  "label": "义县",
  "value": "210727"
}, {
  "label": "凌海市",
  "value": "210781"
}, {
  "label": "北镇市",
  "value": "210782"
}], [{
  "label": "站前区",
  "value": "210802"
}, {
  "label": "西市区",
  "value": "210803"
}, {
  "label": "鲅鱼圈区",
  "value": "210804"
}, {
  "label": "老边区",
  "value": "210811"
}, {
  "label": "盖州市",
  "value": "210881"
}, {
  "label": "大石桥市",
  "value": "210882"
}], [{
  "label": "海州区",
  "value": "210902"
}, {
  "label": "新邱区",
  "value": "210903"
}, {
  "label": "太平区",
  "value": "210904"
}, {
  "label": "清河门区",
  "value": "210905"
}, {
  "label": "细河区",
  "value": "210911"
}, {
  "label": "阜新蒙古族自治县",
  "value": "210921"
}, {
  "label": "彰武县",
  "value": "210922"
}], [{
  "label": "白塔区",
  "value": "211002"
}, {
  "label": "文圣区",
  "value": "211003"
}, {
  "label": "宏伟区",
  "value": "211004"
}, {
  "label": "弓长岭区",
  "value": "211005"
}, {
  "label": "太子河区",
  "value": "211011"
}, {
  "label": "辽阳县",
  "value": "211021"
}, {
  "label": "灯塔市",
  "value": "211081"
}], [{
  "label": "双台子区",
  "value": "211102"
}, {
  "label": "兴隆台区",
  "value": "211103"
}, {
  "label": "大洼区",
  "value": "211104"
}, {
  "label": "盘山县",
  "value": "211122"
}], [{
  "label": "银州区",
  "value": "211202"
}, {
  "label": "清河区",
  "value": "211204"
}, {
  "label": "铁岭县",
  "value": "211221"
}, {
  "label": "西丰县",
  "value": "211223"
}, {
  "label": "昌图县",
  "value": "211224"
}, {
  "label": "调兵山市",
  "value": "211281"
}, {
  "label": "开原市",
  "value": "211282"
}], [{
  "label": "双塔区",
  "value": "211302"
}, {
  "label": "龙城区",
  "value": "211303"
}, {
  "label": "朝阳县",
  "value": "211321"
}, {
  "label": "建平县",
  "value": "211322"
}, {
  "label": "喀喇沁左翼蒙古族自治县",
  "value": "211324"
}, {
  "label": "北票市",
  "value": "211381"
}, {
  "label": "凌源市",
  "value": "211382"
}], [{
  "label": "连山区",
  "value": "211402"
}, {
  "label": "龙港区",
  "value": "211403"
}, {
  "label": "南票区",
  "value": "211404"
}, {
  "label": "绥中县",
  "value": "211421"
}, {
  "label": "建昌县",
  "value": "211422"
}, {
  "label": "兴城市",
  "value": "211481"
}]], [[{
  "label": "南关区",
  "value": "220102"
}, {
  "label": "宽城区",
  "value": "220103"
}, {
  "label": "朝阳区",
  "value": "220104"
}, {
  "label": "二道区",
  "value": "220105"
}, {
  "label": "绿园区",
  "value": "220106"
}, {
  "label": "双阳区",
  "value": "220112"
}, {
  "label": "九台区",
  "value": "220113"
}, {
  "label": "农安县",
  "value": "220122"
}, {
  "label": "长春经济技术开发区",
  "value": "220171"
}, {
  "label": "长春净月高新技术产业开发区",
  "value": "220172"
}, {
  "label": "长春高新技术产业开发区",
  "value": "220173"
}, {
  "label": "长春汽车经济技术开发区",
  "value": "220174"
}, {
  "label": "榆树市",
  "value": "220182"
}, {
  "label": "德惠市",
  "value": "220183"
}], [{
  "label": "昌邑区",
  "value": "220202"
}, {
  "label": "龙潭区",
  "value": "220203"
}, {
  "label": "船营区",
  "value": "220204"
}, {
  "label": "丰满区",
  "value": "220211"
}, {
  "label": "永吉县",
  "value": "220221"
}, {
  "label": "吉林经济开发区",
  "value": "220271"
}, {
  "label": "吉林高新技术产业开发区",
  "value": "220272"
}, {
  "label": "吉林中国新加坡食品区",
  "value": "220273"
}, {
  "label": "蛟河市",
  "value": "220281"
}, {
  "label": "桦甸市",
  "value": "220282"
}, {
  "label": "舒兰市",
  "value": "220283"
}, {
  "label": "磐石市",
  "value": "220284"
}], [{
  "label": "铁西区",
  "value": "220302"
}, {
  "label": "铁东区",
  "value": "220303"
}, {
  "label": "梨树县",
  "value": "220322"
}, {
  "label": "伊通满族自治县",
  "value": "220323"
}, {
  "label": "公主岭市",
  "value": "220381"
}, {
  "label": "双辽市",
  "value": "220382"
}], [{
  "label": "龙山区",
  "value": "220402"
}, {
  "label": "西安区",
  "value": "220403"
}, {
  "label": "东丰县",
  "value": "220421"
}, {
  "label": "东辽县",
  "value": "220422"
}], [{
  "label": "东昌区",
  "value": "220502"
}, {
  "label": "二道江区",
  "value": "220503"
}, {
  "label": "通化县",
  "value": "220521"
}, {
  "label": "辉南县",
  "value": "220523"
}, {
  "label": "柳河县",
  "value": "220524"
}, {
  "label": "梅河口市",
  "value": "220581"
}, {
  "label": "集安市",
  "value": "220582"
}], [{
  "label": "浑江区",
  "value": "220602"
}, {
  "label": "江源区",
  "value": "220605"
}, {
  "label": "抚松县",
  "value": "220621"
}, {
  "label": "靖宇县",
  "value": "220622"
}, {
  "label": "长白朝鲜族自治县",
  "value": "220623"
}, {
  "label": "临江市",
  "value": "220681"
}], [{
  "label": "宁江区",
  "value": "220702"
}, {
  "label": "前郭尔罗斯蒙古族自治县",
  "value": "220721"
}, {
  "label": "长岭县",
  "value": "220722"
}, {
  "label": "乾安县",
  "value": "220723"
}, {
  "label": "吉林松原经济开发区",
  "value": "220771"
}, {
  "label": "扶余市",
  "value": "220781"
}], [{
  "label": "洮北区",
  "value": "220802"
}, {
  "label": "镇赉县",
  "value": "220821"
}, {
  "label": "通榆县",
  "value": "220822"
}, {
  "label": "吉林白城经济开发区",
  "value": "220871"
}, {
  "label": "洮南市",
  "value": "220881"
}, {
  "label": "大安市",
  "value": "220882"
}], [{
  "label": "延吉市",
  "value": "222401"
}, {
  "label": "图们市",
  "value": "222402"
}, {
  "label": "敦化市",
  "value": "222403"
}, {
  "label": "珲春市",
  "value": "222404"
}, {
  "label": "龙井市",
  "value": "222405"
}, {
  "label": "和龙市",
  "value": "222406"
}, {
  "label": "汪清县",
  "value": "222424"
}, {
  "label": "安图县",
  "value": "222426"
}]], [[{
  "label": "道里区",
  "value": "230102"
}, {
  "label": "南岗区",
  "value": "230103"
}, {
  "label": "道外区",
  "value": "230104"
}, {
  "label": "平房区",
  "value": "230108"
}, {
  "label": "松北区",
  "value": "230109"
}, {
  "label": "香坊区",
  "value": "230110"
}, {
  "label": "呼兰区",
  "value": "230111"
}, {
  "label": "阿城区",
  "value": "230112"
}, {
  "label": "双城区",
  "value": "230113"
}, {
  "label": "依兰县",
  "value": "230123"
}, {
  "label": "方正县",
  "value": "230124"
}, {
  "label": "宾县",
  "value": "230125"
}, {
  "label": "巴彦县",
  "value": "230126"
}, {
  "label": "木兰县",
  "value": "230127"
}, {
  "label": "通河县",
  "value": "230128"
}, {
  "label": "延寿县",
  "value": "230129"
}, {
  "label": "尚志市",
  "value": "230183"
}, {
  "label": "五常市",
  "value": "230184"
}], [{
  "label": "龙沙区",
  "value": "230202"
}, {
  "label": "建华区",
  "value": "230203"
}, {
  "label": "铁锋区",
  "value": "230204"
}, {
  "label": "昂昂溪区",
  "value": "230205"
}, {
  "label": "富拉尔基区",
  "value": "230206"
}, {
  "label": "碾子山区",
  "value": "230207"
}, {
  "label": "梅里斯达斡尔族区",
  "value": "230208"
}, {
  "label": "龙江县",
  "value": "230221"
}, {
  "label": "依安县",
  "value": "230223"
}, {
  "label": "泰来县",
  "value": "230224"
}, {
  "label": "甘南县",
  "value": "230225"
}, {
  "label": "富裕县",
  "value": "230227"
}, {
  "label": "克山县",
  "value": "230229"
}, {
  "label": "克东县",
  "value": "230230"
}, {
  "label": "拜泉县",
  "value": "230231"
}, {
  "label": "讷河市",
  "value": "230281"
}], [{
  "label": "鸡冠区",
  "value": "230302"
}, {
  "label": "恒山区",
  "value": "230303"
}, {
  "label": "滴道区",
  "value": "230304"
}, {
  "label": "梨树区",
  "value": "230305"
}, {
  "label": "城子河区",
  "value": "230306"
}, {
  "label": "麻山区",
  "value": "230307"
}, {
  "label": "鸡东县",
  "value": "230321"
}, {
  "label": "虎林市",
  "value": "230381"
}, {
  "label": "密山市",
  "value": "230382"
}], [{
  "label": "向阳区",
  "value": "230402"
}, {
  "label": "工农区",
  "value": "230403"
}, {
  "label": "南山区",
  "value": "230404"
}, {
  "label": "兴安区",
  "value": "230405"
}, {
  "label": "东山区",
  "value": "230406"
}, {
  "label": "兴山区",
  "value": "230407"
}, {
  "label": "萝北县",
  "value": "230421"
}, {
  "label": "绥滨县",
  "value": "230422"
}], [{
  "label": "尖山区",
  "value": "230502"
}, {
  "label": "岭东区",
  "value": "230503"
}, {
  "label": "四方台区",
  "value": "230505"
}, {
  "label": "宝山区",
  "value": "230506"
}, {
  "label": "集贤县",
  "value": "230521"
}, {
  "label": "友谊县",
  "value": "230522"
}, {
  "label": "宝清县",
  "value": "230523"
}, {
  "label": "饶河县",
  "value": "230524"
}], [{
  "label": "萨尔图区",
  "value": "230602"
}, {
  "label": "龙凤区",
  "value": "230603"
}, {
  "label": "让胡路区",
  "value": "230604"
}, {
  "label": "红岗区",
  "value": "230605"
}, {
  "label": "大同区",
  "value": "230606"
}, {
  "label": "肇州县",
  "value": "230621"
}, {
  "label": "肇源县",
  "value": "230622"
}, {
  "label": "林甸县",
  "value": "230623"
}, {
  "label": "杜尔伯特蒙古族自治县",
  "value": "230624"
}, {
  "label": "大庆高新技术产业开发区",
  "value": "230671"
}], [{
  "label": "伊春区",
  "value": "230702"
}, {
  "label": "南岔区",
  "value": "230703"
}, {
  "label": "友好区",
  "value": "230704"
}, {
  "label": "西林区",
  "value": "230705"
}, {
  "label": "翠峦区",
  "value": "230706"
}, {
  "label": "新青区",
  "value": "230707"
}, {
  "label": "美溪区",
  "value": "230708"
}, {
  "label": "金山屯区",
  "value": "230709"
}, {
  "label": "五营区",
  "value": "230710"
}, {
  "label": "乌马河区",
  "value": "230711"
}, {
  "label": "汤旺河区",
  "value": "230712"
}, {
  "label": "带岭区",
  "value": "230713"
}, {
  "label": "乌伊岭区",
  "value": "230714"
}, {
  "label": "红星区",
  "value": "230715"
}, {
  "label": "上甘岭区",
  "value": "230716"
}, {
  "label": "嘉荫县",
  "value": "230722"
}, {
  "label": "铁力市",
  "value": "230781"
}], [{
  "label": "向阳区",
  "value": "230803"
}, {
  "label": "前进区",
  "value": "230804"
}, {
  "label": "东风区",
  "value": "230805"
}, {
  "label": "郊区",
  "value": "230811"
}, {
  "label": "桦南县",
  "value": "230822"
}, {
  "label": "桦川县",
  "value": "230826"
}, {
  "label": "汤原县",
  "value": "230828"
}, {
  "label": "同江市",
  "value": "230881"
}, {
  "label": "富锦市",
  "value": "230882"
}, {
  "label": "抚远市",
  "value": "230883"
}], [{
  "label": "新兴区",
  "value": "230902"
}, {
  "label": "桃山区",
  "value": "230903"
}, {
  "label": "茄子河区",
  "value": "230904"
}, {
  "label": "勃利县",
  "value": "230921"
}], [{
  "label": "东安区",
  "value": "231002"
}, {
  "label": "阳明区",
  "value": "231003"
}, {
  "label": "爱民区",
  "value": "231004"
}, {
  "label": "西安区",
  "value": "231005"
}, {
  "label": "林口县",
  "value": "231025"
}, {
  "label": "牡丹江经济技术开发区",
  "value": "231071"
}, {
  "label": "绥芬河市",
  "value": "231081"
}, {
  "label": "海林市",
  "value": "231083"
}, {
  "label": "宁安市",
  "value": "231084"
}, {
  "label": "穆棱市",
  "value": "231085"
}, {
  "label": "东宁市",
  "value": "231086"
}], [{
  "label": "爱辉区",
  "value": "231102"
}, {
  "label": "嫩江县",
  "value": "231121"
}, {
  "label": "逊克县",
  "value": "231123"
}, {
  "label": "孙吴县",
  "value": "231124"
}, {
  "label": "北安市",
  "value": "231181"
}, {
  "label": "五大连池市",
  "value": "231182"
}], [{
  "label": "北林区",
  "value": "231202"
}, {
  "label": "望奎县",
  "value": "231221"
}, {
  "label": "兰西县",
  "value": "231222"
}, {
  "label": "青冈县",
  "value": "231223"
}, {
  "label": "庆安县",
  "value": "231224"
}, {
  "label": "明水县",
  "value": "231225"
}, {
  "label": "绥棱县",
  "value": "231226"
}, {
  "label": "安达市",
  "value": "231281"
}, {
  "label": "肇东市",
  "value": "231282"
}, {
  "label": "海伦市",
  "value": "231283"
}], [{
  "label": "加格达奇区",
  "value": "232701"
}, {
  "label": "松岭区",
  "value": "232702"
}, {
  "label": "新林区",
  "value": "232703"
}, {
  "label": "呼中区",
  "value": "232704"
}, {
  "label": "呼玛县",
  "value": "232721"
}, {
  "label": "塔河县",
  "value": "232722"
}, {
  "label": "漠河县",
  "value": "232723"
}]], [[{
  "label": "黄浦区",
  "value": "310101"
}, {
  "label": "徐汇区",
  "value": "310104"
}, {
  "label": "长宁区",
  "value": "310105"
}, {
  "label": "静安区",
  "value": "310106"
}, {
  "label": "普陀区",
  "value": "310107"
}, {
  "label": "虹口区",
  "value": "310109"
}, {
  "label": "杨浦区",
  "value": "310110"
}, {
  "label": "闵行区",
  "value": "310112"
}, {
  "label": "宝山区",
  "value": "310113"
}, {
  "label": "嘉定区",
  "value": "310114"
}, {
  "label": "浦东新区",
  "value": "310115"
}, {
  "label": "金山区",
  "value": "310116"
}, {
  "label": "松江区",
  "value": "310117"
}, {
  "label": "青浦区",
  "value": "310118"
}, {
  "label": "奉贤区",
  "value": "310120"
}, {
  "label": "崇明区",
  "value": "310151"
}]], [[{
  "label": "玄武区",
  "value": "320102"
}, {
  "label": "秦淮区",
  "value": "320104"
}, {
  "label": "建邺区",
  "value": "320105"
}, {
  "label": "鼓楼区",
  "value": "320106"
}, {
  "label": "浦口区",
  "value": "320111"
}, {
  "label": "栖霞区",
  "value": "320113"
}, {
  "label": "雨花台区",
  "value": "320114"
}, {
  "label": "江宁区",
  "value": "320115"
}, {
  "label": "六合区",
  "value": "320116"
}, {
  "label": "溧水区",
  "value": "320117"
}, {
  "label": "高淳区",
  "value": "320118"
}], [{
  "label": "锡山区",
  "value": "320205"
}, {
  "label": "惠山区",
  "value": "320206"
}, {
  "label": "滨湖区",
  "value": "320211"
}, {
  "label": "梁溪区",
  "value": "320213"
}, {
  "label": "新吴区",
  "value": "320214"
}, {
  "label": "江阴市",
  "value": "320281"
}, {
  "label": "宜兴市",
  "value": "320282"
}], [{
  "label": "鼓楼区",
  "value": "320302"
}, {
  "label": "云龙区",
  "value": "320303"
}, {
  "label": "贾汪区",
  "value": "320305"
}, {
  "label": "泉山区",
  "value": "320311"
}, {
  "label": "铜山区",
  "value": "320312"
}, {
  "label": "丰县",
  "value": "320321"
}, {
  "label": "沛县",
  "value": "320322"
}, {
  "label": "睢宁县",
  "value": "320324"
}, {
  "label": "徐州经济技术开发区",
  "value": "320371"
}, {
  "label": "新沂市",
  "value": "320381"
}, {
  "label": "邳州市",
  "value": "320382"
}], [{
  "label": "天宁区",
  "value": "320402"
}, {
  "label": "钟楼区",
  "value": "320404"
}, {
  "label": "新北区",
  "value": "320411"
}, {
  "label": "武进区",
  "value": "320412"
}, {
  "label": "金坛区",
  "value": "320413"
}, {
  "label": "溧阳市",
  "value": "320481"
}], [{
  "label": "虎丘区",
  "value": "320505"
}, {
  "label": "吴中区",
  "value": "320506"
}, {
  "label": "相城区",
  "value": "320507"
}, {
  "label": "姑苏区",
  "value": "320508"
}, {
  "label": "吴江区",
  "value": "320509"
}, {
  "label": "苏州工业园区",
  "value": "320571"
}, {
  "label": "常熟市",
  "value": "320581"
}, {
  "label": "张家港市",
  "value": "320582"
}, {
  "label": "昆山市",
  "value": "320583"
}, {
  "label": "太仓市",
  "value": "320585"
}], [{
  "label": "崇川区",
  "value": "320602"
}, {
  "label": "港闸区",
  "value": "320611"
}, {
  "label": "通州区",
  "value": "320612"
}, {
  "label": "海安县",
  "value": "320621"
}, {
  "label": "如东县",
  "value": "320623"
}, {
  "label": "南通经济技术开发区",
  "value": "320671"
}, {
  "label": "启东市",
  "value": "320681"
}, {
  "label": "如皋市",
  "value": "320682"
}, {
  "label": "海门市",
  "value": "320684"
}], [{
  "label": "连云区",
  "value": "320703"
}, {
  "label": "海州区",
  "value": "320706"
}, {
  "label": "赣榆区",
  "value": "320707"
}, {
  "label": "东海县",
  "value": "320722"
}, {
  "label": "灌云县",
  "value": "320723"
}, {
  "label": "灌南县",
  "value": "320724"
}, {
  "label": "连云港经济技术开发区",
  "value": "320771"
}, {
  "label": "连云港高新技术产业开发区",
  "value": "320772"
}], [{
  "label": "淮安区",
  "value": "320803"
}, {
  "label": "淮阴区",
  "value": "320804"
}, {
  "label": "清江浦区",
  "value": "320812"
}, {
  "label": "洪泽区",
  "value": "320813"
}, {
  "label": "涟水县",
  "value": "320826"
}, {
  "label": "盱眙县",
  "value": "320830"
}, {
  "label": "金湖县",
  "value": "320831"
}, {
  "label": "淮安经济技术开发区",
  "value": "320871"
}], [{
  "label": "亭湖区",
  "value": "320902"
}, {
  "label": "盐都区",
  "value": "320903"
}, {
  "label": "大丰区",
  "value": "320904"
}, {
  "label": "响水县",
  "value": "320921"
}, {
  "label": "滨海县",
  "value": "320922"
}, {
  "label": "阜宁县",
  "value": "320923"
}, {
  "label": "射阳县",
  "value": "320924"
}, {
  "label": "建湖县",
  "value": "320925"
}, {
  "label": "盐城经济技术开发区",
  "value": "320971"
}, {
  "label": "东台市",
  "value": "320981"
}], [{
  "label": "广陵区",
  "value": "321002"
}, {
  "label": "邗江区",
  "value": "321003"
}, {
  "label": "江都区",
  "value": "321012"
}, {
  "label": "宝应县",
  "value": "321023"
}, {
  "label": "扬州经济技术开发区",
  "value": "321071"
}, {
  "label": "仪征市",
  "value": "321081"
}, {
  "label": "高邮市",
  "value": "321084"
}], [{
  "label": "京口区",
  "value": "321102"
}, {
  "label": "润州区",
  "value": "321111"
}, {
  "label": "丹徒区",
  "value": "321112"
}, {
  "label": "镇江新区",
  "value": "321171"
}, {
  "label": "丹阳市",
  "value": "321181"
}, {
  "label": "扬中市",
  "value": "321182"
}, {
  "label": "句容市",
  "value": "321183"
}], [{
  "label": "海陵区",
  "value": "321202"
}, {
  "label": "高港区",
  "value": "321203"
}, {
  "label": "姜堰区",
  "value": "321204"
}, {
  "label": "泰州医药高新技术产业开发区",
  "value": "321271"
}, {
  "label": "兴化市",
  "value": "321281"
}, {
  "label": "靖江市",
  "value": "321282"
}, {
  "label": "泰兴市",
  "value": "321283"
}], [{
  "label": "宿城区",
  "value": "321302"
}, {
  "label": "宿豫区",
  "value": "321311"
}, {
  "label": "沭阳县",
  "value": "321322"
}, {
  "label": "泗阳县",
  "value": "321323"
}, {
  "label": "泗洪县",
  "value": "321324"
}, {
  "label": "宿迁经济技术开发区",
  "value": "321371"
}]], [[{
  "label": "上城区",
  "value": "330102"
}, {
  "label": "下城区",
  "value": "330103"
}, {
  "label": "江干区",
  "value": "330104"
}, {
  "label": "拱墅区",
  "value": "330105"
}, {
  "label": "西湖区",
  "value": "330106"
}, {
  "label": "滨江区",
  "value": "330108"
}, {
  "label": "萧山区",
  "value": "330109"
}, {
  "label": "余杭区",
  "value": "330110"
}, {
  "label": "富阳区",
  "value": "330111"
}, {
  "label": "临安区",
  "value": "330112"
}, {
  "label": "桐庐县",
  "value": "330122"
}, {
  "label": "淳安县",
  "value": "330127"
}, {
  "label": "建德市",
  "value": "330182"
}], [{
  "label": "海曙区",
  "value": "330203"
}, {
  "label": "江北区",
  "value": "330205"
}, {
  "label": "北仑区",
  "value": "330206"
}, {
  "label": "镇海区",
  "value": "330211"
}, {
  "label": "鄞州区",
  "value": "330212"
}, {
  "label": "奉化区",
  "value": "330213"
}, {
  "label": "象山县",
  "value": "330225"
}, {
  "label": "宁海县",
  "value": "330226"
}, {
  "label": "余姚市",
  "value": "330281"
}, {
  "label": "慈溪市",
  "value": "330282"
}], [{
  "label": "鹿城区",
  "value": "330302"
}, {
  "label": "龙湾区",
  "value": "330303"
}, {
  "label": "瓯海区",
  "value": "330304"
}, {
  "label": "洞头区",
  "value": "330305"
}, {
  "label": "永嘉县",
  "value": "330324"
}, {
  "label": "平阳县",
  "value": "330326"
}, {
  "label": "苍南县",
  "value": "330327"
}, {
  "label": "文成县",
  "value": "330328"
}, {
  "label": "泰顺县",
  "value": "330329"
}, {
  "label": "温州经济技术开发区",
  "value": "330371"
}, {
  "label": "瑞安市",
  "value": "330381"
}, {
  "label": "乐清市",
  "value": "330382"
}], [{
  "label": "南湖区",
  "value": "330402"
}, {
  "label": "秀洲区",
  "value": "330411"
}, {
  "label": "嘉善县",
  "value": "330421"
}, {
  "label": "海盐县",
  "value": "330424"
}, {
  "label": "海宁市",
  "value": "330481"
}, {
  "label": "平湖市",
  "value": "330482"
}, {
  "label": "桐乡市",
  "value": "330483"
}], [{
  "label": "吴兴区",
  "value": "330502"
}, {
  "label": "南浔区",
  "value": "330503"
}, {
  "label": "德清县",
  "value": "330521"
}, {
  "label": "长兴县",
  "value": "330522"
}, {
  "label": "安吉县",
  "value": "330523"
}], [{
  "label": "越城区",
  "value": "330602"
}, {
  "label": "柯桥区",
  "value": "330603"
}, {
  "label": "上虞区",
  "value": "330604"
}, {
  "label": "新昌县",
  "value": "330624"
}, {
  "label": "诸暨市",
  "value": "330681"
}, {
  "label": "嵊州市",
  "value": "330683"
}], [{
  "label": "婺城区",
  "value": "330702"
}, {
  "label": "金东区",
  "value": "330703"
}, {
  "label": "武义县",
  "value": "330723"
}, {
  "label": "浦江县",
  "value": "330726"
}, {
  "label": "磐安县",
  "value": "330727"
}, {
  "label": "兰溪市",
  "value": "330781"
}, {
  "label": "义乌市",
  "value": "330782"
}, {
  "label": "东阳市",
  "value": "330783"
}, {
  "label": "永康市",
  "value": "330784"
}], [{
  "label": "柯城区",
  "value": "330802"
}, {
  "label": "衢江区",
  "value": "330803"
}, {
  "label": "常山县",
  "value": "330822"
}, {
  "label": "开化县",
  "value": "330824"
}, {
  "label": "龙游县",
  "value": "330825"
}, {
  "label": "江山市",
  "value": "330881"
}], [{
  "label": "定海区",
  "value": "330902"
}, {
  "label": "普陀区",
  "value": "330903"
}, {
  "label": "岱山县",
  "value": "330921"
}, {
  "label": "嵊泗县",
  "value": "330922"
}], [{
  "label": "椒江区",
  "value": "331002"
}, {
  "label": "黄岩区",
  "value": "331003"
}, {
  "label": "路桥区",
  "value": "331004"
}, {
  "label": "三门县",
  "value": "331022"
}, {
  "label": "天台县",
  "value": "331023"
}, {
  "label": "仙居县",
  "value": "331024"
}, {
  "label": "温岭市",
  "value": "331081"
}, {
  "label": "临海市",
  "value": "331082"
}, {
  "label": "玉环市",
  "value": "331083"
}], [{
  "label": "莲都区",
  "value": "331102"
}, {
  "label": "青田县",
  "value": "331121"
}, {
  "label": "缙云县",
  "value": "331122"
}, {
  "label": "遂昌县",
  "value": "331123"
}, {
  "label": "松阳县",
  "value": "331124"
}, {
  "label": "云和县",
  "value": "331125"
}, {
  "label": "庆元县",
  "value": "331126"
}, {
  "label": "景宁畲族自治县",
  "value": "331127"
}, {
  "label": "龙泉市",
  "value": "331181"
}]], [[{
  "label": "瑶海区",
  "value": "340102"
}, {
  "label": "庐阳区",
  "value": "340103"
}, {
  "label": "蜀山区",
  "value": "340104"
}, {
  "label": "包河区",
  "value": "340111"
}, {
  "label": "长丰县",
  "value": "340121"
}, {
  "label": "肥东县",
  "value": "340122"
}, {
  "label": "肥西县",
  "value": "340123"
}, {
  "label": "庐江县",
  "value": "340124"
}, {
  "label": "合肥高新技术产业开发区",
  "value": "340171"
}, {
  "label": "合肥经济技术开发区",
  "value": "340172"
}, {
  "label": "合肥新站高新技术产业开发区",
  "value": "340173"
}, {
  "label": "巢湖市",
  "value": "340181"
}], [{
  "label": "镜湖区",
  "value": "340202"
}, {
  "label": "弋江区",
  "value": "340203"
}, {
  "label": "鸠江区",
  "value": "340207"
}, {
  "label": "三山区",
  "value": "340208"
}, {
  "label": "芜湖县",
  "value": "340221"
}, {
  "label": "繁昌县",
  "value": "340222"
}, {
  "label": "南陵县",
  "value": "340223"
}, {
  "label": "无为县",
  "value": "340225"
}, {
  "label": "芜湖经济技术开发区",
  "value": "340271"
}, {
  "label": "安徽芜湖长江大桥经济开发区",
  "value": "340272"
}], [{
  "label": "龙子湖区",
  "value": "340302"
}, {
  "label": "蚌山区",
  "value": "340303"
}, {
  "label": "禹会区",
  "value": "340304"
}, {
  "label": "淮上区",
  "value": "340311"
}, {
  "label": "怀远县",
  "value": "340321"
}, {
  "label": "五河县",
  "value": "340322"
}, {
  "label": "固镇县",
  "value": "340323"
}, {
  "label": "蚌埠市高新技术开发区",
  "value": "340371"
}, {
  "label": "蚌埠市经济开发区",
  "value": "340372"
}], [{
  "label": "大通区",
  "value": "340402"
}, {
  "label": "田家庵区",
  "value": "340403"
}, {
  "label": "谢家集区",
  "value": "340404"
}, {
  "label": "八公山区",
  "value": "340405"
}, {
  "label": "潘集区",
  "value": "340406"
}, {
  "label": "凤台县",
  "value": "340421"
}, {
  "label": "寿县",
  "value": "340422"
}], [{
  "label": "花山区",
  "value": "340503"
}, {
  "label": "雨山区",
  "value": "340504"
}, {
  "label": "博望区",
  "value": "340506"
}, {
  "label": "当涂县",
  "value": "340521"
}, {
  "label": "含山县",
  "value": "340522"
}, {
  "label": "和县",
  "value": "340523"
}], [{
  "label": "杜集区",
  "value": "340602"
}, {
  "label": "相山区",
  "value": "340603"
}, {
  "label": "烈山区",
  "value": "340604"
}, {
  "label": "濉溪县",
  "value": "340621"
}], [{
  "label": "铜官区",
  "value": "340705"
}, {
  "label": "义安区",
  "value": "340706"
}, {
  "label": "郊区",
  "value": "340711"
}, {
  "label": "枞阳县",
  "value": "340722"
}], [{
  "label": "迎江区",
  "value": "340802"
}, {
  "label": "大观区",
  "value": "340803"
}, {
  "label": "宜秀区",
  "value": "340811"
}, {
  "label": "怀宁县",
  "value": "340822"
}, {
  "label": "潜山县",
  "value": "340824"
}, {
  "label": "太湖县",
  "value": "340825"
}, {
  "label": "宿松县",
  "value": "340826"
}, {
  "label": "望江县",
  "value": "340827"
}, {
  "label": "岳西县",
  "value": "340828"
}, {
  "label": "安徽安庆经济开发区",
  "value": "340871"
}, {
  "label": "桐城市",
  "value": "340881"
}], [{
  "label": "屯溪区",
  "value": "341002"
}, {
  "label": "黄山区",
  "value": "341003"
}, {
  "label": "徽州区",
  "value": "341004"
}, {
  "label": "歙县",
  "value": "341021"
}, {
  "label": "休宁县",
  "value": "341022"
}, {
  "label": "黟县",
  "value": "341023"
}, {
  "label": "祁门县",
  "value": "341024"
}], [{
  "label": "琅琊区",
  "value": "341102"
}, {
  "label": "南谯区",
  "value": "341103"
}, {
  "label": "来安县",
  "value": "341122"
}, {
  "label": "全椒县",
  "value": "341124"
}, {
  "label": "定远县",
  "value": "341125"
}, {
  "label": "凤阳县",
  "value": "341126"
}, {
  "label": "苏滁现代产业园",
  "value": "341171"
}, {
  "label": "滁州经济技术开发区",
  "value": "341172"
}, {
  "label": "天长市",
  "value": "341181"
}, {
  "label": "明光市",
  "value": "341182"
}], [{
  "label": "颍州区",
  "value": "341202"
}, {
  "label": "颍东区",
  "value": "341203"
}, {
  "label": "颍泉区",
  "value": "341204"
}, {
  "label": "临泉县",
  "value": "341221"
}, {
  "label": "太和县",
  "value": "341222"
}, {
  "label": "阜南县",
  "value": "341225"
}, {
  "label": "颍上县",
  "value": "341226"
}, {
  "label": "阜阳合肥现代产业园区",
  "value": "341271"
}, {
  "label": "阜阳经济技术开发区",
  "value": "341272"
}, {
  "label": "界首市",
  "value": "341282"
}], [{
  "label": "埇桥区",
  "value": "341302"
}, {
  "label": "砀山县",
  "value": "341321"
}, {
  "label": "萧县",
  "value": "341322"
}, {
  "label": "灵璧县",
  "value": "341323"
}, {
  "label": "泗县",
  "value": "341324"
}, {
  "label": "宿州马鞍山现代产业园区",
  "value": "341371"
}, {
  "label": "宿州经济技术开发区",
  "value": "341372"
}], [{
  "label": "金安区",
  "value": "341502"
}, {
  "label": "裕安区",
  "value": "341503"
}, {
  "label": "叶集区",
  "value": "341504"
}, {
  "label": "霍邱县",
  "value": "341522"
}, {
  "label": "舒城县",
  "value": "341523"
}, {
  "label": "金寨县",
  "value": "341524"
}, {
  "label": "霍山县",
  "value": "341525"
}], [{
  "label": "谯城区",
  "value": "341602"
}, {
  "label": "涡阳县",
  "value": "341621"
}, {
  "label": "蒙城县",
  "value": "341622"
}, {
  "label": "利辛县",
  "value": "341623"
}], [{
  "label": "贵池区",
  "value": "341702"
}, {
  "label": "东至县",
  "value": "341721"
}, {
  "label": "石台县",
  "value": "341722"
}, {
  "label": "青阳县",
  "value": "341723"
}], [{
  "label": "宣州区",
  "value": "341802"
}, {
  "label": "郎溪县",
  "value": "341821"
}, {
  "label": "广德县",
  "value": "341822"
}, {
  "label": "泾县",
  "value": "341823"
}, {
  "label": "绩溪县",
  "value": "341824"
}, {
  "label": "旌德县",
  "value": "341825"
}, {
  "label": "宣城市经济开发区",
  "value": "341871"
}, {
  "label": "宁国市",
  "value": "341881"
}]], [[{
  "label": "鼓楼区",
  "value": "350102"
}, {
  "label": "台江区",
  "value": "350103"
}, {
  "label": "仓山区",
  "value": "350104"
}, {
  "label": "马尾区",
  "value": "350105"
}, {
  "label": "晋安区",
  "value": "350111"
}, {
  "label": "闽侯县",
  "value": "350121"
}, {
  "label": "连江县",
  "value": "350122"
}, {
  "label": "罗源县",
  "value": "350123"
}, {
  "label": "闽清县",
  "value": "350124"
}, {
  "label": "永泰县",
  "value": "350125"
}, {
  "label": "平潭县",
  "value": "350128"
}, {
  "label": "福清市",
  "value": "350181"
}, {
  "label": "长乐市",
  "value": "350182"
}], [{
  "label": "思明区",
  "value": "350203"
}, {
  "label": "海沧区",
  "value": "350205"
}, {
  "label": "湖里区",
  "value": "350206"
}, {
  "label": "集美区",
  "value": "350211"
}, {
  "label": "同安区",
  "value": "350212"
}, {
  "label": "翔安区",
  "value": "350213"
}], [{
  "label": "城厢区",
  "value": "350302"
}, {
  "label": "涵江区",
  "value": "350303"
}, {
  "label": "荔城区",
  "value": "350304"
}, {
  "label": "秀屿区",
  "value": "350305"
}, {
  "label": "仙游县",
  "value": "350322"
}], [{
  "label": "梅列区",
  "value": "350402"
}, {
  "label": "三元区",
  "value": "350403"
}, {
  "label": "明溪县",
  "value": "350421"
}, {
  "label": "清流县",
  "value": "350423"
}, {
  "label": "宁化县",
  "value": "350424"
}, {
  "label": "大田县",
  "value": "350425"
}, {
  "label": "尤溪县",
  "value": "350426"
}, {
  "label": "沙县",
  "value": "350427"
}, {
  "label": "将乐县",
  "value": "350428"
}, {
  "label": "泰宁县",
  "value": "350429"
}, {
  "label": "建宁县",
  "value": "350430"
}, {
  "label": "永安市",
  "value": "350481"
}], [{
  "label": "鲤城区",
  "value": "350502"
}, {
  "label": "丰泽区",
  "value": "350503"
}, {
  "label": "洛江区",
  "value": "350504"
}, {
  "label": "泉港区",
  "value": "350505"
}, {
  "label": "惠安县",
  "value": "350521"
}, {
  "label": "安溪县",
  "value": "350524"
}, {
  "label": "永春县",
  "value": "350525"
}, {
  "label": "德化县",
  "value": "350526"
}, {
  "label": "金门县",
  "value": "350527"
}, {
  "label": "石狮市",
  "value": "350581"
}, {
  "label": "晋江市",
  "value": "350582"
}, {
  "label": "南安市",
  "value": "350583"
}], [{
  "label": "芗城区",
  "value": "350602"
}, {
  "label": "龙文区",
  "value": "350603"
}, {
  "label": "云霄县",
  "value": "350622"
}, {
  "label": "漳浦县",
  "value": "350623"
}, {
  "label": "诏安县",
  "value": "350624"
}, {
  "label": "长泰县",
  "value": "350625"
}, {
  "label": "东山县",
  "value": "350626"
}, {
  "label": "南靖县",
  "value": "350627"
}, {
  "label": "平和县",
  "value": "350628"
}, {
  "label": "华安县",
  "value": "350629"
}, {
  "label": "龙海市",
  "value": "350681"
}], [{
  "label": "延平区",
  "value": "350702"
}, {
  "label": "建阳区",
  "value": "350703"
}, {
  "label": "顺昌县",
  "value": "350721"
}, {
  "label": "浦城县",
  "value": "350722"
}, {
  "label": "光泽县",
  "value": "350723"
}, {
  "label": "松溪县",
  "value": "350724"
}, {
  "label": "政和县",
  "value": "350725"
}, {
  "label": "邵武市",
  "value": "350781"
}, {
  "label": "武夷山市",
  "value": "350782"
}, {
  "label": "建瓯市",
  "value": "350783"
}], [{
  "label": "新罗区",
  "value": "350802"
}, {
  "label": "永定区",
  "value": "350803"
}, {
  "label": "长汀县",
  "value": "350821"
}, {
  "label": "上杭县",
  "value": "350823"
}, {
  "label": "武平县",
  "value": "350824"
}, {
  "label": "连城县",
  "value": "350825"
}, {
  "label": "漳平市",
  "value": "350881"
}], [{
  "label": "蕉城区",
  "value": "350902"
}, {
  "label": "霞浦县",
  "value": "350921"
}, {
  "label": "古田县",
  "value": "350922"
}, {
  "label": "屏南县",
  "value": "350923"
}, {
  "label": "寿宁县",
  "value": "350924"
}, {
  "label": "周宁县",
  "value": "350925"
}, {
  "label": "柘荣县",
  "value": "350926"
}, {
  "label": "福安市",
  "value": "350981"
}, {
  "label": "福鼎市",
  "value": "350982"
}]], [[{
  "label": "东湖区",
  "value": "360102"
}, {
  "label": "西湖区",
  "value": "360103"
}, {
  "label": "青云谱区",
  "value": "360104"
}, {
  "label": "湾里区",
  "value": "360105"
}, {
  "label": "青山湖区",
  "value": "360111"
}, {
  "label": "新建区",
  "value": "360112"
}, {
  "label": "南昌县",
  "value": "360121"
}, {
  "label": "安义县",
  "value": "360123"
}, {
  "label": "进贤县",
  "value": "360124"
}], [{
  "label": "昌江区",
  "value": "360202"
}, {
  "label": "珠山区",
  "value": "360203"
}, {
  "label": "浮梁县",
  "value": "360222"
}, {
  "label": "乐平市",
  "value": "360281"
}], [{
  "label": "安源区",
  "value": "360302"
}, {
  "label": "湘东区",
  "value": "360313"
}, {
  "label": "莲花县",
  "value": "360321"
}, {
  "label": "上栗县",
  "value": "360322"
}, {
  "label": "芦溪县",
  "value": "360323"
}], [{
  "label": "濂溪区",
  "value": "360402"
}, {
  "label": "浔阳区",
  "value": "360403"
}, {
  "label": "柴桑区",
  "value": "360404"
}, {
  "label": "武宁县",
  "value": "360423"
}, {
  "label": "修水县",
  "value": "360424"
}, {
  "label": "永修县",
  "value": "360425"
}, {
  "label": "德安县",
  "value": "360426"
}, {
  "label": "都昌县",
  "value": "360428"
}, {
  "label": "湖口县",
  "value": "360429"
}, {
  "label": "彭泽县",
  "value": "360430"
}, {
  "label": "瑞昌市",
  "value": "360481"
}, {
  "label": "共青城市",
  "value": "360482"
}, {
  "label": "庐山市",
  "value": "360483"
}], [{
  "label": "渝水区",
  "value": "360502"
}, {
  "label": "分宜县",
  "value": "360521"
}], [{
  "label": "月湖区",
  "value": "360602"
}, {
  "label": "余江县",
  "value": "360622"
}, {
  "label": "贵溪市",
  "value": "360681"
}], [{
  "label": "章贡区",
  "value": "360702"
}, {
  "label": "南康区",
  "value": "360703"
}, {
  "label": "赣县区",
  "value": "360704"
}, {
  "label": "信丰县",
  "value": "360722"
}, {
  "label": "大余县",
  "value": "360723"
}, {
  "label": "上犹县",
  "value": "360724"
}, {
  "label": "崇义县",
  "value": "360725"
}, {
  "label": "安远县",
  "value": "360726"
}, {
  "label": "龙南县",
  "value": "360727"
}, {
  "label": "定南县",
  "value": "360728"
}, {
  "label": "全南县",
  "value": "360729"
}, {
  "label": "宁都县",
  "value": "360730"
}, {
  "label": "于都县",
  "value": "360731"
}, {
  "label": "兴国县",
  "value": "360732"
}, {
  "label": "会昌县",
  "value": "360733"
}, {
  "label": "寻乌县",
  "value": "360734"
}, {
  "label": "石城县",
  "value": "360735"
}, {
  "label": "瑞金市",
  "value": "360781"
}], [{
  "label": "吉州区",
  "value": "360802"
}, {
  "label": "青原区",
  "value": "360803"
}, {
  "label": "吉安县",
  "value": "360821"
}, {
  "label": "吉水县",
  "value": "360822"
}, {
  "label": "峡江县",
  "value": "360823"
}, {
  "label": "新干县",
  "value": "360824"
}, {
  "label": "永丰县",
  "value": "360825"
}, {
  "label": "泰和县",
  "value": "360826"
}, {
  "label": "遂川县",
  "value": "360827"
}, {
  "label": "万安县",
  "value": "360828"
}, {
  "label": "安福县",
  "value": "360829"
}, {
  "label": "永新县",
  "value": "360830"
}, {
  "label": "井冈山市",
  "value": "360881"
}], [{
  "label": "袁州区",
  "value": "360902"
}, {
  "label": "奉新县",
  "value": "360921"
}, {
  "label": "万载县",
  "value": "360922"
}, {
  "label": "上高县",
  "value": "360923"
}, {
  "label": "宜丰县",
  "value": "360924"
}, {
  "label": "靖安县",
  "value": "360925"
}, {
  "label": "铜鼓县",
  "value": "360926"
}, {
  "label": "丰城市",
  "value": "360981"
}, {
  "label": "樟树市",
  "value": "360982"
}, {
  "label": "高安市",
  "value": "360983"
}], [{
  "label": "临川区",
  "value": "361002"
}, {
  "label": "东乡区",
  "value": "361003"
}, {
  "label": "南城县",
  "value": "361021"
}, {
  "label": "黎川县",
  "value": "361022"
}, {
  "label": "南丰县",
  "value": "361023"
}, {
  "label": "崇仁县",
  "value": "361024"
}, {
  "label": "乐安县",
  "value": "361025"
}, {
  "label": "宜黄县",
  "value": "361026"
}, {
  "label": "金溪县",
  "value": "361027"
}, {
  "label": "资溪县",
  "value": "361028"
}, {
  "label": "广昌县",
  "value": "361030"
}], [{
  "label": "信州区",
  "value": "361102"
}, {
  "label": "广丰区",
  "value": "361103"
}, {
  "label": "上饶县",
  "value": "361121"
}, {
  "label": "玉山县",
  "value": "361123"
}, {
  "label": "铅山县",
  "value": "361124"
}, {
  "label": "横峰县",
  "value": "361125"
}, {
  "label": "弋阳县",
  "value": "361126"
}, {
  "label": "余干县",
  "value": "361127"
}, {
  "label": "鄱阳县",
  "value": "361128"
}, {
  "label": "万年县",
  "value": "361129"
}, {
  "label": "婺源县",
  "value": "361130"
}, {
  "label": "德兴市",
  "value": "361181"
}]], [[{
  "label": "历下区",
  "value": "370102"
}, {
  "label": "市中区",
  "value": "370103"
}, {
  "label": "槐荫区",
  "value": "370104"
}, {
  "label": "天桥区",
  "value": "370105"
}, {
  "label": "历城区",
  "value": "370112"
}, {
  "label": "长清区",
  "value": "370113"
}, {
  "label": "章丘区",
  "value": "370114"
}, {
  "label": "平阴县",
  "value": "370124"
}, {
  "label": "济阳县",
  "value": "370125"
}, {
  "label": "商河县",
  "value": "370126"
}, {
  "label": "济南高新技术产业开发区",
  "value": "370171"
}], [{
  "label": "市南区",
  "value": "370202"
}, {
  "label": "市北区",
  "value": "370203"
}, {
  "label": "黄岛区",
  "value": "370211"
}, {
  "label": "崂山区",
  "value": "370212"
}, {
  "label": "李沧区",
  "value": "370213"
}, {
  "label": "城阳区",
  "value": "370214"
}, {
  "label": "即墨区",
  "value": "370215"
}, {
  "label": "青岛高新技术产业开发区",
  "value": "370271"
}, {
  "label": "胶州市",
  "value": "370281"
}, {
  "label": "平度市",
  "value": "370283"
}, {
  "label": "莱西市",
  "value": "370285"
}], [{
  "label": "淄川区",
  "value": "370302"
}, {
  "label": "张店区",
  "value": "370303"
}, {
  "label": "博山区",
  "value": "370304"
}, {
  "label": "临淄区",
  "value": "370305"
}, {
  "label": "周村区",
  "value": "370306"
}, {
  "label": "桓台县",
  "value": "370321"
}, {
  "label": "高青县",
  "value": "370322"
}, {
  "label": "沂源县",
  "value": "370323"
}], [{
  "label": "市中区",
  "value": "370402"
}, {
  "label": "薛城区",
  "value": "370403"
}, {
  "label": "峄城区",
  "value": "370404"
}, {
  "label": "台儿庄区",
  "value": "370405"
}, {
  "label": "山亭区",
  "value": "370406"
}, {
  "label": "滕州市",
  "value": "370481"
}], [{
  "label": "东营区",
  "value": "370502"
}, {
  "label": "河口区",
  "value": "370503"
}, {
  "label": "垦利区",
  "value": "370505"
}, {
  "label": "利津县",
  "value": "370522"
}, {
  "label": "广饶县",
  "value": "370523"
}, {
  "label": "东营经济技术开发区",
  "value": "370571"
}, {
  "label": "东营港经济开发区",
  "value": "370572"
}], [{
  "label": "芝罘区",
  "value": "370602"
}, {
  "label": "福山区",
  "value": "370611"
}, {
  "label": "牟平区",
  "value": "370612"
}, {
  "label": "莱山区",
  "value": "370613"
}, {
  "label": "长岛县",
  "value": "370634"
}, {
  "label": "烟台高新技术产业开发区",
  "value": "370671"
}, {
  "label": "烟台经济技术开发区",
  "value": "370672"
}, {
  "label": "龙口市",
  "value": "370681"
}, {
  "label": "莱阳市",
  "value": "370682"
}, {
  "label": "莱州市",
  "value": "370683"
}, {
  "label": "蓬莱市",
  "value": "370684"
}, {
  "label": "招远市",
  "value": "370685"
}, {
  "label": "栖霞市",
  "value": "370686"
}, {
  "label": "海阳市",
  "value": "370687"
}], [{
  "label": "潍城区",
  "value": "370702"
}, {
  "label": "寒亭区",
  "value": "370703"
}, {
  "label": "坊子区",
  "value": "370704"
}, {
  "label": "奎文区",
  "value": "370705"
}, {
  "label": "临朐县",
  "value": "370724"
}, {
  "label": "昌乐县",
  "value": "370725"
}, {
  "label": "潍坊滨海经济技术开发区",
  "value": "370772"
}, {
  "label": "青州市",
  "value": "370781"
}, {
  "label": "诸城市",
  "value": "370782"
}, {
  "label": "寿光市",
  "value": "370783"
}, {
  "label": "安丘市",
  "value": "370784"
}, {
  "label": "高密市",
  "value": "370785"
}, {
  "label": "昌邑市",
  "value": "370786"
}], [{
  "label": "任城区",
  "value": "370811"
}, {
  "label": "兖州区",
  "value": "370812"
}, {
  "label": "微山县",
  "value": "370826"
}, {
  "label": "鱼台县",
  "value": "370827"
}, {
  "label": "金乡县",
  "value": "370828"
}, {
  "label": "嘉祥县",
  "value": "370829"
}, {
  "label": "汶上县",
  "value": "370830"
}, {
  "label": "泗水县",
  "value": "370831"
}, {
  "label": "梁山县",
  "value": "370832"
}, {
  "label": "济宁高新技术产业开发区",
  "value": "370871"
}, {
  "label": "曲阜市",
  "value": "370881"
}, {
  "label": "邹城市",
  "value": "370883"
}], [{
  "label": "泰山区",
  "value": "370902"
}, {
  "label": "岱岳区",
  "value": "370911"
}, {
  "label": "宁阳县",
  "value": "370921"
}, {
  "label": "东平县",
  "value": "370923"
}, {
  "label": "新泰市",
  "value": "370982"
}, {
  "label": "肥城市",
  "value": "370983"
}], [{
  "label": "环翠区",
  "value": "371002"
}, {
  "label": "文登区",
  "value": "371003"
}, {
  "label": "威海火炬高技术产业开发区",
  "value": "371071"
}, {
  "label": "威海经济技术开发区",
  "value": "371072"
}, {
  "label": "威海临港经济技术开发区",
  "value": "371073"
}, {
  "label": "荣成市",
  "value": "371082"
}, {
  "label": "乳山市",
  "value": "371083"
}], [{
  "label": "东港区",
  "value": "371102"
}, {
  "label": "岚山区",
  "value": "371103"
}, {
  "label": "五莲县",
  "value": "371121"
}, {
  "label": "莒县",
  "value": "371122"
}, {
  "label": "日照经济技术开发区",
  "value": "371171"
}, {
  "label": "日照国际海洋城",
  "value": "371172"
}], [{
  "label": "莱城区",
  "value": "371202"
}, {
  "label": "钢城区",
  "value": "371203"
}], [{
  "label": "兰山区",
  "value": "371302"
}, {
  "label": "罗庄区",
  "value": "371311"
}, {
  "label": "河东区",
  "value": "371312"
}, {
  "label": "沂南县",
  "value": "371321"
}, {
  "label": "郯城县",
  "value": "371322"
}, {
  "label": "沂水县",
  "value": "371323"
}, {
  "label": "兰陵县",
  "value": "371324"
}, {
  "label": "费县",
  "value": "371325"
}, {
  "label": "平邑县",
  "value": "371326"
}, {
  "label": "莒南县",
  "value": "371327"
}, {
  "label": "蒙阴县",
  "value": "371328"
}, {
  "label": "临沭县",
  "value": "371329"
}, {
  "label": "临沂高新技术产业开发区",
  "value": "371371"
}, {
  "label": "临沂经济技术开发区",
  "value": "371372"
}, {
  "label": "临沂临港经济开发区",
  "value": "371373"
}], [{
  "label": "德城区",
  "value": "371402"
}, {
  "label": "陵城区",
  "value": "371403"
}, {
  "label": "宁津县",
  "value": "371422"
}, {
  "label": "庆云县",
  "value": "371423"
}, {
  "label": "临邑县",
  "value": "371424"
}, {
  "label": "齐河县",
  "value": "371425"
}, {
  "label": "平原县",
  "value": "371426"
}, {
  "label": "夏津县",
  "value": "371427"
}, {
  "label": "武城县",
  "value": "371428"
}, {
  "label": "德州经济技术开发区",
  "value": "371471"
}, {
  "label": "德州运河经济开发区",
  "value": "371472"
}, {
  "label": "乐陵市",
  "value": "371481"
}, {
  "label": "禹城市",
  "value": "371482"
}], [{
  "label": "东昌府区",
  "value": "371502"
}, {
  "label": "阳谷县",
  "value": "371521"
}, {
  "label": "莘县",
  "value": "371522"
}, {
  "label": "茌平县",
  "value": "371523"
}, {
  "label": "东阿县",
  "value": "371524"
}, {
  "label": "冠县",
  "value": "371525"
}, {
  "label": "高唐县",
  "value": "371526"
}, {
  "label": "临清市",
  "value": "371581"
}], [{
  "label": "滨城区",
  "value": "371602"
}, {
  "label": "沾化区",
  "value": "371603"
}, {
  "label": "惠民县",
  "value": "371621"
}, {
  "label": "阳信县",
  "value": "371622"
}, {
  "label": "无棣县",
  "value": "371623"
}, {
  "label": "博兴县",
  "value": "371625"
}, {
  "label": "邹平县",
  "value": "371626"
}], [{
  "label": "牡丹区",
  "value": "371702"
}, {
  "label": "定陶区",
  "value": "371703"
}, {
  "label": "曹县",
  "value": "371721"
}, {
  "label": "单县",
  "value": "371722"
}, {
  "label": "成武县",
  "value": "371723"
}, {
  "label": "巨野县",
  "value": "371724"
}, {
  "label": "郓城县",
  "value": "371725"
}, {
  "label": "鄄城县",
  "value": "371726"
}, {
  "label": "东明县",
  "value": "371728"
}, {
  "label": "菏泽经济技术开发区",
  "value": "371771"
}, {
  "label": "菏泽高新技术开发区",
  "value": "371772"
}]], [[{
  "label": "中原区",
  "value": "410102"
}, {
  "label": "二七区",
  "value": "410103"
}, {
  "label": "管城回族区",
  "value": "410104"
}, {
  "label": "金水区",
  "value": "410105"
}, {
  "label": "上街区",
  "value": "410106"
}, {
  "label": "惠济区",
  "value": "410108"
}, {
  "label": "中牟县",
  "value": "410122"
}, {
  "label": "郑州经济技术开发区",
  "value": "410171"
}, {
  "label": "郑州高新技术产业开发区",
  "value": "410172"
}, {
  "label": "郑州航空港经济综合实验区",
  "value": "410173"
}, {
  "label": "巩义市",
  "value": "410181"
}, {
  "label": "荥阳市",
  "value": "410182"
}, {
  "label": "新密市",
  "value": "410183"
}, {
  "label": "新郑市",
  "value": "410184"
}, {
  "label": "登封市",
  "value": "410185"
}], [{
  "label": "龙亭区",
  "value": "410202"
}, {
  "label": "顺河回族区",
  "value": "410203"
}, {
  "label": "鼓楼区",
  "value": "410204"
}, {
  "label": "禹王台区",
  "value": "410205"
}, {
  "label": "祥符区",
  "value": "410212"
}, {
  "label": "杞县",
  "value": "410221"
}, {
  "label": "通许县",
  "value": "410222"
}, {
  "label": "尉氏县",
  "value": "410223"
}, {
  "label": "兰考县",
  "value": "410225"
}], [{
  "label": "老城区",
  "value": "410302"
}, {
  "label": "西工区",
  "value": "410303"
}, {
  "label": "瀍河回族区",
  "value": "410304"
}, {
  "label": "涧西区",
  "value": "410305"
}, {
  "label": "吉利区",
  "value": "410306"
}, {
  "label": "洛龙区",
  "value": "410311"
}, {
  "label": "孟津县",
  "value": "410322"
}, {
  "label": "新安县",
  "value": "410323"
}, {
  "label": "栾川县",
  "value": "410324"
}, {
  "label": "嵩县",
  "value": "410325"
}, {
  "label": "汝阳县",
  "value": "410326"
}, {
  "label": "宜阳县",
  "value": "410327"
}, {
  "label": "洛宁县",
  "value": "410328"
}, {
  "label": "伊川县",
  "value": "410329"
}, {
  "label": "洛阳高新技术产业开发区",
  "value": "410371"
}, {
  "label": "偃师市",
  "value": "410381"
}], [{
  "label": "新华区",
  "value": "410402"
}, {
  "label": "卫东区",
  "value": "410403"
}, {
  "label": "石龙区",
  "value": "410404"
}, {
  "label": "湛河区",
  "value": "410411"
}, {
  "label": "宝丰县",
  "value": "410421"
}, {
  "label": "叶县",
  "value": "410422"
}, {
  "label": "鲁山县",
  "value": "410423"
}, {
  "label": "郏县",
  "value": "410425"
}, {
  "label": "平顶山高新技术产业开发区",
  "value": "410471"
}, {
  "label": "平顶山市新城区",
  "value": "410472"
}, {
  "label": "舞钢市",
  "value": "410481"
}, {
  "label": "汝州市",
  "value": "410482"
}], [{
  "label": "文峰区",
  "value": "410502"
}, {
  "label": "北关区",
  "value": "410503"
}, {
  "label": "殷都区",
  "value": "410505"
}, {
  "label": "龙安区",
  "value": "410506"
}, {
  "label": "安阳县",
  "value": "410522"
}, {
  "label": "汤阴县",
  "value": "410523"
}, {
  "label": "滑县",
  "value": "410526"
}, {
  "label": "内黄县",
  "value": "410527"
}, {
  "label": "安阳高新技术产业开发区",
  "value": "410571"
}, {
  "label": "林州市",
  "value": "410581"
}], [{
  "label": "鹤山区",
  "value": "410602"
}, {
  "label": "山城区",
  "value": "410603"
}, {
  "label": "淇滨区",
  "value": "410611"
}, {
  "label": "浚县",
  "value": "410621"
}, {
  "label": "淇县",
  "value": "410622"
}, {
  "label": "鹤壁经济技术开发区",
  "value": "410671"
}], [{
  "label": "红旗区",
  "value": "410702"
}, {
  "label": "卫滨区",
  "value": "410703"
}, {
  "label": "凤泉区",
  "value": "410704"
}, {
  "label": "牧野区",
  "value": "410711"
}, {
  "label": "新乡县",
  "value": "410721"
}, {
  "label": "获嘉县",
  "value": "410724"
}, {
  "label": "原阳县",
  "value": "410725"
}, {
  "label": "延津县",
  "value": "410726"
}, {
  "label": "封丘县",
  "value": "410727"
}, {
  "label": "长垣县",
  "value": "410728"
}, {
  "label": "新乡高新技术产业开发区",
  "value": "410771"
}, {
  "label": "新乡经济技术开发区",
  "value": "410772"
}, {
  "label": "新乡市平原城乡一体化示范区",
  "value": "410773"
}, {
  "label": "卫辉市",
  "value": "410781"
}, {
  "label": "辉县市",
  "value": "410782"
}], [{
  "label": "解放区",
  "value": "410802"
}, {
  "label": "中站区",
  "value": "410803"
}, {
  "label": "马村区",
  "value": "410804"
}, {
  "label": "山阳区",
  "value": "410811"
}, {
  "label": "修武县",
  "value": "410821"
}, {
  "label": "博爱县",
  "value": "410822"
}, {
  "label": "武陟县",
  "value": "410823"
}, {
  "label": "温县",
  "value": "410825"
}, {
  "label": "焦作城乡一体化示范区",
  "value": "410871"
}, {
  "label": "沁阳市",
  "value": "410882"
}, {
  "label": "孟州市",
  "value": "410883"
}], [{
  "label": "华龙区",
  "value": "410902"
}, {
  "label": "清丰县",
  "value": "410922"
}, {
  "label": "南乐县",
  "value": "410923"
}, {
  "label": "范县",
  "value": "410926"
}, {
  "label": "台前县",
  "value": "410927"
}, {
  "label": "濮阳县",
  "value": "410928"
}, {
  "label": "河南濮阳工业园区",
  "value": "410971"
}, {
  "label": "濮阳经济技术开发区",
  "value": "410972"
}], [{
  "label": "魏都区",
  "value": "411002"
}, {
  "label": "建安区",
  "value": "411003"
}, {
  "label": "鄢陵县",
  "value": "411024"
}, {
  "label": "襄城县",
  "value": "411025"
}, {
  "label": "许昌经济技术开发区",
  "value": "411071"
}, {
  "label": "禹州市",
  "value": "411081"
}, {
  "label": "长葛市",
  "value": "411082"
}], [{
  "label": "源汇区",
  "value": "411102"
}, {
  "label": "郾城区",
  "value": "411103"
}, {
  "label": "召陵区",
  "value": "411104"
}, {
  "label": "舞阳县",
  "value": "411121"
}, {
  "label": "临颍县",
  "value": "411122"
}, {
  "label": "漯河经济技术开发区",
  "value": "411171"
}], [{
  "label": "湖滨区",
  "value": "411202"
}, {
  "label": "陕州区",
  "value": "411203"
}, {
  "label": "渑池县",
  "value": "411221"
}, {
  "label": "卢氏县",
  "value": "411224"
}, {
  "label": "河南三门峡经济开发区",
  "value": "411271"
}, {
  "label": "义马市",
  "value": "411281"
}, {
  "label": "灵宝市",
  "value": "411282"
}], [{
  "label": "宛城区",
  "value": "411302"
}, {
  "label": "卧龙区",
  "value": "411303"
}, {
  "label": "南召县",
  "value": "411321"
}, {
  "label": "方城县",
  "value": "411322"
}, {
  "label": "西峡县",
  "value": "411323"
}, {
  "label": "镇平县",
  "value": "411324"
}, {
  "label": "内乡县",
  "value": "411325"
}, {
  "label": "淅川县",
  "value": "411326"
}, {
  "label": "社旗县",
  "value": "411327"
}, {
  "label": "唐河县",
  "value": "411328"
}, {
  "label": "新野县",
  "value": "411329"
}, {
  "label": "桐柏县",
  "value": "411330"
}, {
  "label": "南阳高新技术产业开发区",
  "value": "411371"
}, {
  "label": "南阳市城乡一体化示范区",
  "value": "411372"
}, {
  "label": "邓州市",
  "value": "411381"
}], [{
  "label": "梁园区",
  "value": "411402"
}, {
  "label": "睢阳区",
  "value": "411403"
}, {
  "label": "民权县",
  "value": "411421"
}, {
  "label": "睢县",
  "value": "411422"
}, {
  "label": "宁陵县",
  "value": "411423"
}, {
  "label": "柘城县",
  "value": "411424"
}, {
  "label": "虞城县",
  "value": "411425"
}, {
  "label": "夏邑县",
  "value": "411426"
}, {
  "label": "豫东综合物流产业聚集区",
  "value": "411471"
}, {
  "label": "河南商丘经济开发区",
  "value": "411472"
}, {
  "label": "永城市",
  "value": "411481"
}], [{
  "label": "浉河区",
  "value": "411502"
}, {
  "label": "平桥区",
  "value": "411503"
}, {
  "label": "罗山县",
  "value": "411521"
}, {
  "label": "光山县",
  "value": "411522"
}, {
  "label": "新县",
  "value": "411523"
}, {
  "label": "商城县",
  "value": "411524"
}, {
  "label": "固始县",
  "value": "411525"
}, {
  "label": "潢川县",
  "value": "411526"
}, {
  "label": "淮滨县",
  "value": "411527"
}, {
  "label": "息县",
  "value": "411528"
}, {
  "label": "信阳高新技术产业开发区",
  "value": "411571"
}], [{
  "label": "川汇区",
  "value": "411602"
}, {
  "label": "扶沟县",
  "value": "411621"
}, {
  "label": "西华县",
  "value": "411622"
}, {
  "label": "商水县",
  "value": "411623"
}, {
  "label": "沈丘县",
  "value": "411624"
}, {
  "label": "郸城县",
  "value": "411625"
}, {
  "label": "淮阳县",
  "value": "411626"
}, {
  "label": "太康县",
  "value": "411627"
}, {
  "label": "鹿邑县",
  "value": "411628"
}, {
  "label": "河南周口经济开发区",
  "value": "411671"
}, {
  "label": "项城市",
  "value": "411681"
}], [{
  "label": "驿城区",
  "value": "411702"
}, {
  "label": "西平县",
  "value": "411721"
}, {
  "label": "上蔡县",
  "value": "411722"
}, {
  "label": "平舆县",
  "value": "411723"
}, {
  "label": "正阳县",
  "value": "411724"
}, {
  "label": "确山县",
  "value": "411725"
}, {
  "label": "泌阳县",
  "value": "411726"
}, {
  "label": "汝南县",
  "value": "411727"
}, {
  "label": "遂平县",
  "value": "411728"
}, {
  "label": "新蔡县",
  "value": "411729"
}, {
  "label": "河南驻马店经济开发区",
  "value": "411771"
}], [{
  "label": "济源市",
  "value": "419001"
}]], [[{
  "label": "江岸区",
  "value": "420102"
}, {
  "label": "江汉区",
  "value": "420103"
}, {
  "label": "硚口区",
  "value": "420104"
}, {
  "label": "汉阳区",
  "value": "420105"
}, {
  "label": "武昌区",
  "value": "420106"
}, {
  "label": "青山区",
  "value": "420107"
}, {
  "label": "洪山区",
  "value": "420111"
}, {
  "label": "东西湖区",
  "value": "420112"
}, {
  "label": "汉南区",
  "value": "420113"
}, {
  "label": "蔡甸区",
  "value": "420114"
}, {
  "label": "江夏区",
  "value": "420115"
}, {
  "label": "黄陂区",
  "value": "420116"
}, {
  "label": "新洲区",
  "value": "420117"
}], [{
  "label": "黄石港区",
  "value": "420202"
}, {
  "label": "西塞山区",
  "value": "420203"
}, {
  "label": "下陆区",
  "value": "420204"
}, {
  "label": "铁山区",
  "value": "420205"
}, {
  "label": "阳新县",
  "value": "420222"
}, {
  "label": "大冶市",
  "value": "420281"
}], [{
  "label": "茅箭区",
  "value": "420302"
}, {
  "label": "张湾区",
  "value": "420303"
}, {
  "label": "郧阳区",
  "value": "420304"
}, {
  "label": "郧西县",
  "value": "420322"
}, {
  "label": "竹山县",
  "value": "420323"
}, {
  "label": "竹溪县",
  "value": "420324"
}, {
  "label": "房县",
  "value": "420325"
}, {
  "label": "丹江口市",
  "value": "420381"
}], [{
  "label": "西陵区",
  "value": "420502"
}, {
  "label": "伍家岗区",
  "value": "420503"
}, {
  "label": "点军区",
  "value": "420504"
}, {
  "label": "猇亭区",
  "value": "420505"
}, {
  "label": "夷陵区",
  "value": "420506"
}, {
  "label": "远安县",
  "value": "420525"
}, {
  "label": "兴山县",
  "value": "420526"
}, {
  "label": "秭归县",
  "value": "420527"
}, {
  "label": "长阳土家族自治县",
  "value": "420528"
}, {
  "label": "五峰土家族自治县",
  "value": "420529"
}, {
  "label": "宜都市",
  "value": "420581"
}, {
  "label": "当阳市",
  "value": "420582"
}, {
  "label": "枝江市",
  "value": "420583"
}], [{
  "label": "襄城区",
  "value": "420602"
}, {
  "label": "樊城区",
  "value": "420606"
}, {
  "label": "襄州区",
  "value": "420607"
}, {
  "label": "南漳县",
  "value": "420624"
}, {
  "label": "谷城县",
  "value": "420625"
}, {
  "label": "保康县",
  "value": "420626"
}, {
  "label": "老河口市",
  "value": "420682"
}, {
  "label": "枣阳市",
  "value": "420683"
}, {
  "label": "宜城市",
  "value": "420684"
}], [{
  "label": "梁子湖区",
  "value": "420702"
}, {
  "label": "华容区",
  "value": "420703"
}, {
  "label": "鄂城区",
  "value": "420704"
}], [{
  "label": "东宝区",
  "value": "420802"
}, {
  "label": "掇刀区",
  "value": "420804"
}, {
  "label": "京山县",
  "value": "420821"
}, {
  "label": "沙洋县",
  "value": "420822"
}, {
  "label": "钟祥市",
  "value": "420881"
}], [{
  "label": "孝南区",
  "value": "420902"
}, {
  "label": "孝昌县",
  "value": "420921"
}, {
  "label": "大悟县",
  "value": "420922"
}, {
  "label": "云梦县",
  "value": "420923"
}, {
  "label": "应城市",
  "value": "420981"
}, {
  "label": "安陆市",
  "value": "420982"
}, {
  "label": "汉川市",
  "value": "420984"
}], [{
  "label": "沙市区",
  "value": "421002"
}, {
  "label": "荆州区",
  "value": "421003"
}, {
  "label": "公安县",
  "value": "421022"
}, {
  "label": "监利县",
  "value": "421023"
}, {
  "label": "江陵县",
  "value": "421024"
}, {
  "label": "荆州经济技术开发区",
  "value": "421071"
}, {
  "label": "石首市",
  "value": "421081"
}, {
  "label": "洪湖市",
  "value": "421083"
}, {
  "label": "松滋市",
  "value": "421087"
}], [{
  "label": "黄州区",
  "value": "421102"
}, {
  "label": "团风县",
  "value": "421121"
}, {
  "label": "红安县",
  "value": "421122"
}, {
  "label": "罗田县",
  "value": "421123"
}, {
  "label": "英山县",
  "value": "421124"
}, {
  "label": "浠水县",
  "value": "421125"
}, {
  "label": "蕲春县",
  "value": "421126"
}, {
  "label": "黄梅县",
  "value": "421127"
}, {
  "label": "龙感湖管理区",
  "value": "421171"
}, {
  "label": "麻城市",
  "value": "421181"
}, {
  "label": "武穴市",
  "value": "421182"
}], [{
  "label": "咸安区",
  "value": "421202"
}, {
  "label": "嘉鱼县",
  "value": "421221"
}, {
  "label": "通城县",
  "value": "421222"
}, {
  "label": "崇阳县",
  "value": "421223"
}, {
  "label": "通山县",
  "value": "421224"
}, {
  "label": "赤壁市",
  "value": "421281"
}], [{
  "label": "曾都区",
  "value": "421303"
}, {
  "label": "随县",
  "value": "421321"
}, {
  "label": "广水市",
  "value": "421381"
}], [{
  "label": "恩施市",
  "value": "422801"
}, {
  "label": "利川市",
  "value": "422802"
}, {
  "label": "建始县",
  "value": "422822"
}, {
  "label": "巴东县",
  "value": "422823"
}, {
  "label": "宣恩县",
  "value": "422825"
}, {
  "label": "咸丰县",
  "value": "422826"
}, {
  "label": "来凤县",
  "value": "422827"
}, {
  "label": "鹤峰县",
  "value": "422828"
}], [{
  "label": "仙桃市",
  "value": "429004"
}, {
  "label": "潜江市",
  "value": "429005"
}, {
  "label": "天门市",
  "value": "429006"
}, {
  "label": "神农架林区",
  "value": "429021"
}]], [[{
  "label": "芙蓉区",
  "value": "430102"
}, {
  "label": "天心区",
  "value": "430103"
}, {
  "label": "岳麓区",
  "value": "430104"
}, {
  "label": "开福区",
  "value": "430105"
}, {
  "label": "雨花区",
  "value": "430111"
}, {
  "label": "望城区",
  "value": "430112"
}, {
  "label": "长沙县",
  "value": "430121"
}, {
  "label": "浏阳市",
  "value": "430181"
}, {
  "label": "宁乡市",
  "value": "430182"
}], [{
  "label": "荷塘区",
  "value": "430202"
}, {
  "label": "芦淞区",
  "value": "430203"
}, {
  "label": "石峰区",
  "value": "430204"
}, {
  "label": "天元区",
  "value": "430211"
}, {
  "label": "株洲县",
  "value": "430221"
}, {
  "label": "攸县",
  "value": "430223"
}, {
  "label": "茶陵县",
  "value": "430224"
}, {
  "label": "炎陵县",
  "value": "430225"
}, {
  "label": "云龙示范区",
  "value": "430271"
}, {
  "label": "醴陵市",
  "value": "430281"
}], [{
  "label": "雨湖区",
  "value": "430302"
}, {
  "label": "岳塘区",
  "value": "430304"
}, {
  "label": "湘潭县",
  "value": "430321"
}, {
  "label": "湖南湘潭高新技术产业园区",
  "value": "430371"
}, {
  "label": "湘潭昭山示范区",
  "value": "430372"
}, {
  "label": "湘潭九华示范区",
  "value": "430373"
}, {
  "label": "湘乡市",
  "value": "430381"
}, {
  "label": "韶山市",
  "value": "430382"
}], [{
  "label": "珠晖区",
  "value": "430405"
}, {
  "label": "雁峰区",
  "value": "430406"
}, {
  "label": "石鼓区",
  "value": "430407"
}, {
  "label": "蒸湘区",
  "value": "430408"
}, {
  "label": "南岳区",
  "value": "430412"
}, {
  "label": "衡阳县",
  "value": "430421"
}, {
  "label": "衡南县",
  "value": "430422"
}, {
  "label": "衡山县",
  "value": "430423"
}, {
  "label": "衡东县",
  "value": "430424"
}, {
  "label": "祁东县",
  "value": "430426"
}, {
  "label": "衡阳综合保税区",
  "value": "430471"
}, {
  "label": "湖南衡阳高新技术产业园区",
  "value": "430472"
}, {
  "label": "湖南衡阳松木经济开发区",
  "value": "430473"
}, {
  "label": "耒阳市",
  "value": "430481"
}, {
  "label": "常宁市",
  "value": "430482"
}], [{
  "label": "双清区",
  "value": "430502"
}, {
  "label": "大祥区",
  "value": "430503"
}, {
  "label": "北塔区",
  "value": "430511"
}, {
  "label": "邵东县",
  "value": "430521"
}, {
  "label": "新邵县",
  "value": "430522"
}, {
  "label": "邵阳县",
  "value": "430523"
}, {
  "label": "隆回县",
  "value": "430524"
}, {
  "label": "洞口县",
  "value": "430525"
}, {
  "label": "绥宁县",
  "value": "430527"
}, {
  "label": "新宁县",
  "value": "430528"
}, {
  "label": "城步苗族自治县",
  "value": "430529"
}, {
  "label": "武冈市",
  "value": "430581"
}], [{
  "label": "岳阳楼区",
  "value": "430602"
}, {
  "label": "云溪区",
  "value": "430603"
}, {
  "label": "君山区",
  "value": "430611"
}, {
  "label": "岳阳县",
  "value": "430621"
}, {
  "label": "华容县",
  "value": "430623"
}, {
  "label": "湘阴县",
  "value": "430624"
}, {
  "label": "平江县",
  "value": "430626"
}, {
  "label": "岳阳市屈原管理区",
  "value": "430671"
}, {
  "label": "汨罗市",
  "value": "430681"
}, {
  "label": "临湘市",
  "value": "430682"
}], [{
  "label": "武陵区",
  "value": "430702"
}, {
  "label": "鼎城区",
  "value": "430703"
}, {
  "label": "安乡县",
  "value": "430721"
}, {
  "label": "汉寿县",
  "value": "430722"
}, {
  "label": "澧县",
  "value": "430723"
}, {
  "label": "临澧县",
  "value": "430724"
}, {
  "label": "桃源县",
  "value": "430725"
}, {
  "label": "石门县",
  "value": "430726"
}, {
  "label": "常德市西洞庭管理区",
  "value": "430771"
}, {
  "label": "津市市",
  "value": "430781"
}], [{
  "label": "永定区",
  "value": "430802"
}, {
  "label": "武陵源区",
  "value": "430811"
}, {
  "label": "慈利县",
  "value": "430821"
}, {
  "label": "桑植县",
  "value": "430822"
}], [{
  "label": "资阳区",
  "value": "430902"
}, {
  "label": "赫山区",
  "value": "430903"
}, {
  "label": "南县",
  "value": "430921"
}, {
  "label": "桃江县",
  "value": "430922"
}, {
  "label": "安化县",
  "value": "430923"
}, {
  "label": "益阳市大通湖管理区",
  "value": "430971"
}, {
  "label": "湖南益阳高新技术产业园区",
  "value": "430972"
}, {
  "label": "沅江市",
  "value": "430981"
}], [{
  "label": "北湖区",
  "value": "431002"
}, {
  "label": "苏仙区",
  "value": "431003"
}, {
  "label": "桂阳县",
  "value": "431021"
}, {
  "label": "宜章县",
  "value": "431022"
}, {
  "label": "永兴县",
  "value": "431023"
}, {
  "label": "嘉禾县",
  "value": "431024"
}, {
  "label": "临武县",
  "value": "431025"
}, {
  "label": "汝城县",
  "value": "431026"
}, {
  "label": "桂东县",
  "value": "431027"
}, {
  "label": "安仁县",
  "value": "431028"
}, {
  "label": "资兴市",
  "value": "431081"
}], [{
  "label": "零陵区",
  "value": "431102"
}, {
  "label": "冷水滩区",
  "value": "431103"
}, {
  "label": "祁阳县",
  "value": "431121"
}, {
  "label": "东安县",
  "value": "431122"
}, {
  "label": "双牌县",
  "value": "431123"
}, {
  "label": "道县",
  "value": "431124"
}, {
  "label": "江永县",
  "value": "431125"
}, {
  "label": "宁远县",
  "value": "431126"
}, {
  "label": "蓝山县",
  "value": "431127"
}, {
  "label": "新田县",
  "value": "431128"
}, {
  "label": "江华瑶族自治县",
  "value": "431129"
}, {
  "label": "永州经济技术开发区",
  "value": "431171"
}, {
  "label": "永州市金洞管理区",
  "value": "431172"
}, {
  "label": "永州市回龙圩管理区",
  "value": "431173"
}], [{
  "label": "鹤城区",
  "value": "431202"
}, {
  "label": "中方县",
  "value": "431221"
}, {
  "label": "沅陵县",
  "value": "431222"
}, {
  "label": "辰溪县",
  "value": "431223"
}, {
  "label": "溆浦县",
  "value": "431224"
}, {
  "label": "会同县",
  "value": "431225"
}, {
  "label": "麻阳苗族自治县",
  "value": "431226"
}, {
  "label": "新晃侗族自治县",
  "value": "431227"
}, {
  "label": "芷江侗族自治县",
  "value": "431228"
}, {
  "label": "靖州苗族侗族自治县",
  "value": "431229"
}, {
  "label": "通道侗族自治县",
  "value": "431230"
}, {
  "label": "怀化市洪江管理区",
  "value": "431271"
}, {
  "label": "洪江市",
  "value": "431281"
}], [{
  "label": "娄星区",
  "value": "431302"
}, {
  "label": "双峰县",
  "value": "431321"
}, {
  "label": "新化县",
  "value": "431322"
}, {
  "label": "冷水江市",
  "value": "431381"
}, {
  "label": "涟源市",
  "value": "431382"
}], [{
  "label": "吉首市",
  "value": "433101"
}, {
  "label": "泸溪县",
  "value": "433122"
}, {
  "label": "凤凰县",
  "value": "433123"
}, {
  "label": "花垣县",
  "value": "433124"
}, {
  "label": "保靖县",
  "value": "433125"
}, {
  "label": "古丈县",
  "value": "433126"
}, {
  "label": "永顺县",
  "value": "433127"
}, {
  "label": "龙山县",
  "value": "433130"
}, {
  "label": "湖南吉首经济开发区",
  "value": "433172"
}, {
  "label": "湖南永顺经济开发区",
  "value": "433173"
}]], [[{
  "label": "荔湾区",
  "value": "440103"
}, {
  "label": "越秀区",
  "value": "440104"
}, {
  "label": "海珠区",
  "value": "440105"
}, {
  "label": "天河区",
  "value": "440106"
}, {
  "label": "白云区",
  "value": "440111"
}, {
  "label": "黄埔区",
  "value": "440112"
}, {
  "label": "番禺区",
  "value": "440113"
}, {
  "label": "花都区",
  "value": "440114"
}, {
  "label": "南沙区",
  "value": "440115"
}, {
  "label": "从化区",
  "value": "440117"
}, {
  "label": "增城区",
  "value": "440118"
}], [{
  "label": "武江区",
  "value": "440203"
}, {
  "label": "浈江区",
  "value": "440204"
}, {
  "label": "曲江区",
  "value": "440205"
}, {
  "label": "始兴县",
  "value": "440222"
}, {
  "label": "仁化县",
  "value": "440224"
}, {
  "label": "翁源县",
  "value": "440229"
}, {
  "label": "乳源瑶族自治县",
  "value": "440232"
}, {
  "label": "新丰县",
  "value": "440233"
}, {
  "label": "乐昌市",
  "value": "440281"
}, {
  "label": "南雄市",
  "value": "440282"
}], [{
  "label": "罗湖区",
  "value": "440303"
}, {
  "label": "福田区",
  "value": "440304"
}, {
  "label": "南山区",
  "value": "440305"
}, {
  "label": "宝安区",
  "value": "440306"
}, {
  "label": "龙岗区",
  "value": "440307"
}, {
  "label": "盐田区",
  "value": "440308"
}, {
  "label": "龙华区",
  "value": "440309"
}, {
  "label": "坪山区",
  "value": "440310"
}], [{
  "label": "香洲区",
  "value": "440402"
}, {
  "label": "斗门区",
  "value": "440403"
}, {
  "label": "金湾区",
  "value": "440404"
}], [{
  "label": "龙湖区",
  "value": "440507"
}, {
  "label": "金平区",
  "value": "440511"
}, {
  "label": "濠江区",
  "value": "440512"
}, {
  "label": "潮阳区",
  "value": "440513"
}, {
  "label": "潮南区",
  "value": "440514"
}, {
  "label": "澄海区",
  "value": "440515"
}, {
  "label": "南澳县",
  "value": "440523"
}], [{
  "label": "禅城区",
  "value": "440604"
}, {
  "label": "南海区",
  "value": "440605"
}, {
  "label": "顺德区",
  "value": "440606"
}, {
  "label": "三水区",
  "value": "440607"
}, {
  "label": "高明区",
  "value": "440608"
}], [{
  "label": "蓬江区",
  "value": "440703"
}, {
  "label": "江海区",
  "value": "440704"
}, {
  "label": "新会区",
  "value": "440705"
}, {
  "label": "台山市",
  "value": "440781"
}, {
  "label": "开平市",
  "value": "440783"
}, {
  "label": "鹤山市",
  "value": "440784"
}, {
  "label": "恩平市",
  "value": "440785"
}], [{
  "label": "赤坎区",
  "value": "440802"
}, {
  "label": "霞山区",
  "value": "440803"
}, {
  "label": "坡头区",
  "value": "440804"
}, {
  "label": "麻章区",
  "value": "440811"
}, {
  "label": "遂溪县",
  "value": "440823"
}, {
  "label": "徐闻县",
  "value": "440825"
}, {
  "label": "廉江市",
  "value": "440881"
}, {
  "label": "雷州市",
  "value": "440882"
}, {
  "label": "吴川市",
  "value": "440883"
}], [{
  "label": "茂南区",
  "value": "440902"
}, {
  "label": "电白区",
  "value": "440904"
}, {
  "label": "高州市",
  "value": "440981"
}, {
  "label": "化州市",
  "value": "440982"
}, {
  "label": "信宜市",
  "value": "440983"
}], [{
  "label": "端州区",
  "value": "441202"
}, {
  "label": "鼎湖区",
  "value": "441203"
}, {
  "label": "高要区",
  "value": "441204"
}, {
  "label": "广宁县",
  "value": "441223"
}, {
  "label": "怀集县",
  "value": "441224"
}, {
  "label": "封开县",
  "value": "441225"
}, {
  "label": "德庆县",
  "value": "441226"
}, {
  "label": "四会市",
  "value": "441284"
}], [{
  "label": "惠城区",
  "value": "441302"
}, {
  "label": "惠阳区",
  "value": "441303"
}, {
  "label": "博罗县",
  "value": "441322"
}, {
  "label": "惠东县",
  "value": "441323"
}, {
  "label": "龙门县",
  "value": "441324"
}], [{
  "label": "梅江区",
  "value": "441402"
}, {
  "label": "梅县区",
  "value": "441403"
}, {
  "label": "大埔县",
  "value": "441422"
}, {
  "label": "丰顺县",
  "value": "441423"
}, {
  "label": "五华县",
  "value": "441424"
}, {
  "label": "平远县",
  "value": "441426"
}, {
  "label": "蕉岭县",
  "value": "441427"
}, {
  "label": "兴宁市",
  "value": "441481"
}], [{
  "label": "城区",
  "value": "441502"
}, {
  "label": "海丰县",
  "value": "441521"
}, {
  "label": "陆河县",
  "value": "441523"
}, {
  "label": "陆丰市",
  "value": "441581"
}], [{
  "label": "源城区",
  "value": "441602"
}, {
  "label": "紫金县",
  "value": "441621"
}, {
  "label": "龙川县",
  "value": "441622"
}, {
  "label": "连平县",
  "value": "441623"
}, {
  "label": "和平县",
  "value": "441624"
}, {
  "label": "东源县",
  "value": "441625"
}], [{
  "label": "江城区",
  "value": "441702"
}, {
  "label": "阳东区",
  "value": "441704"
}, {
  "label": "阳西县",
  "value": "441721"
}, {
  "label": "阳春市",
  "value": "441781"
}], [{
  "label": "清城区",
  "value": "441802"
}, {
  "label": "清新区",
  "value": "441803"
}, {
  "label": "佛冈县",
  "value": "441821"
}, {
  "label": "阳山县",
  "value": "441823"
}, {
  "label": "连山壮族瑶族自治县",
  "value": "441825"
}, {
  "label": "连南瑶族自治县",
  "value": "441826"
}, {
  "label": "英德市",
  "value": "441881"
}, {
  "label": "连州市",
  "value": "441882"
}], [{
  "label": "东莞市",
  "value": "441900"
}], [{
  "label": "中山市",
  "value": "442000"
}], [{
  "label": "湘桥区",
  "value": "445102"
}, {
  "label": "潮安区",
  "value": "445103"
}, {
  "label": "饶平县",
  "value": "445122"
}], [{
  "label": "榕城区",
  "value": "445202"
}, {
  "label": "揭东区",
  "value": "445203"
}, {
  "label": "揭西县",
  "value": "445222"
}, {
  "label": "惠来县",
  "value": "445224"
}, {
  "label": "普宁市",
  "value": "445281"
}], [{
  "label": "云城区",
  "value": "445302"
}, {
  "label": "云安区",
  "value": "445303"
}, {
  "label": "新兴县",
  "value": "445321"
}, {
  "label": "郁南县",
  "value": "445322"
}, {
  "label": "罗定市",
  "value": "445381"
}]], [[{
  "label": "兴宁区",
  "value": "450102"
}, {
  "label": "青秀区",
  "value": "450103"
}, {
  "label": "江南区",
  "value": "450105"
}, {
  "label": "西乡塘区",
  "value": "450107"
}, {
  "label": "良庆区",
  "value": "450108"
}, {
  "label": "邕宁区",
  "value": "450109"
}, {
  "label": "武鸣区",
  "value": "450110"
}, {
  "label": "隆安县",
  "value": "450123"
}, {
  "label": "马山县",
  "value": "450124"
}, {
  "label": "上林县",
  "value": "450125"
}, {
  "label": "宾阳县",
  "value": "450126"
}, {
  "label": "横县",
  "value": "450127"
}], [{
  "label": "城中区",
  "value": "450202"
}, {
  "label": "鱼峰区",
  "value": "450203"
}, {
  "label": "柳南区",
  "value": "450204"
}, {
  "label": "柳北区",
  "value": "450205"
}, {
  "label": "柳江区",
  "value": "450206"
}, {
  "label": "柳城县",
  "value": "450222"
}, {
  "label": "鹿寨县",
  "value": "450223"
}, {
  "label": "融安县",
  "value": "450224"
}, {
  "label": "融水苗族自治县",
  "value": "450225"
}, {
  "label": "三江侗族自治县",
  "value": "450226"
}], [{
  "label": "秀峰区",
  "value": "450302"
}, {
  "label": "叠彩区",
  "value": "450303"
}, {
  "label": "象山区",
  "value": "450304"
}, {
  "label": "七星区",
  "value": "450305"
}, {
  "label": "雁山区",
  "value": "450311"
}, {
  "label": "临桂区",
  "value": "450312"
}, {
  "label": "阳朔县",
  "value": "450321"
}, {
  "label": "灵川县",
  "value": "450323"
}, {
  "label": "全州县",
  "value": "450324"
}, {
  "label": "兴安县",
  "value": "450325"
}, {
  "label": "永福县",
  "value": "450326"
}, {
  "label": "灌阳县",
  "value": "450327"
}, {
  "label": "龙胜各族自治县",
  "value": "450328"
}, {
  "label": "资源县",
  "value": "450329"
}, {
  "label": "平乐县",
  "value": "450330"
}, {
  "label": "荔浦县",
  "value": "450331"
}, {
  "label": "恭城瑶族自治县",
  "value": "450332"
}], [{
  "label": "万秀区",
  "value": "450403"
}, {
  "label": "长洲区",
  "value": "450405"
}, {
  "label": "龙圩区",
  "value": "450406"
}, {
  "label": "苍梧县",
  "value": "450421"
}, {
  "label": "藤县",
  "value": "450422"
}, {
  "label": "蒙山县",
  "value": "450423"
}, {
  "label": "岑溪市",
  "value": "450481"
}], [{
  "label": "海城区",
  "value": "450502"
}, {
  "label": "银海区",
  "value": "450503"
}, {
  "label": "铁山港区",
  "value": "450512"
}, {
  "label": "合浦县",
  "value": "450521"
}], [{
  "label": "港口区",
  "value": "450602"
}, {
  "label": "防城区",
  "value": "450603"
}, {
  "label": "上思县",
  "value": "450621"
}, {
  "label": "东兴市",
  "value": "450681"
}], [{
  "label": "钦南区",
  "value": "450702"
}, {
  "label": "钦北区",
  "value": "450703"
}, {
  "label": "灵山县",
  "value": "450721"
}, {
  "label": "浦北县",
  "value": "450722"
}], [{
  "label": "港北区",
  "value": "450802"
}, {
  "label": "港南区",
  "value": "450803"
}, {
  "label": "覃塘区",
  "value": "450804"
}, {
  "label": "平南县",
  "value": "450821"
}, {
  "label": "桂平市",
  "value": "450881"
}], [{
  "label": "玉州区",
  "value": "450902"
}, {
  "label": "福绵区",
  "value": "450903"
}, {
  "label": "容县",
  "value": "450921"
}, {
  "label": "陆川县",
  "value": "450922"
}, {
  "label": "博白县",
  "value": "450923"
}, {
  "label": "兴业县",
  "value": "450924"
}, {
  "label": "北流市",
  "value": "450981"
}], [{
  "label": "右江区",
  "value": "451002"
}, {
  "label": "田阳县",
  "value": "451021"
}, {
  "label": "田东县",
  "value": "451022"
}, {
  "label": "平果县",
  "value": "451023"
}, {
  "label": "德保县",
  "value": "451024"
}, {
  "label": "那坡县",
  "value": "451026"
}, {
  "label": "凌云县",
  "value": "451027"
}, {
  "label": "乐业县",
  "value": "451028"
}, {
  "label": "田林县",
  "value": "451029"
}, {
  "label": "西林县",
  "value": "451030"
}, {
  "label": "隆林各族自治县",
  "value": "451031"
}, {
  "label": "靖西市",
  "value": "451081"
}], [{
  "label": "八步区",
  "value": "451102"
}, {
  "label": "平桂区",
  "value": "451103"
}, {
  "label": "昭平县",
  "value": "451121"
}, {
  "label": "钟山县",
  "value": "451122"
}, {
  "label": "富川瑶族自治县",
  "value": "451123"
}], [{
  "label": "金城江区",
  "value": "451202"
}, {
  "label": "宜州区",
  "value": "451203"
}, {
  "label": "南丹县",
  "value": "451221"
}, {
  "label": "天峨县",
  "value": "451222"
}, {
  "label": "凤山县",
  "value": "451223"
}, {
  "label": "东兰县",
  "value": "451224"
}, {
  "label": "罗城仫佬族自治县",
  "value": "451225"
}, {
  "label": "环江毛南族自治县",
  "value": "451226"
}, {
  "label": "巴马瑶族自治县",
  "value": "451227"
}, {
  "label": "都安瑶族自治县",
  "value": "451228"
}, {
  "label": "大化瑶族自治县",
  "value": "451229"
}], [{
  "label": "兴宾区",
  "value": "451302"
}, {
  "label": "忻城县",
  "value": "451321"
}, {
  "label": "象州县",
  "value": "451322"
}, {
  "label": "武宣县",
  "value": "451323"
}, {
  "label": "金秀瑶族自治县",
  "value": "451324"
}, {
  "label": "合山市",
  "value": "451381"
}], [{
  "label": "江州区",
  "value": "451402"
}, {
  "label": "扶绥县",
  "value": "451421"
}, {
  "label": "宁明县",
  "value": "451422"
}, {
  "label": "龙州县",
  "value": "451423"
}, {
  "label": "大新县",
  "value": "451424"
}, {
  "label": "天等县",
  "value": "451425"
}, {
  "label": "凭祥市",
  "value": "451481"
}]], [[{
  "label": "秀英区",
  "value": "460105"
}, {
  "label": "龙华区",
  "value": "460106"
}, {
  "label": "琼山区",
  "value": "460107"
}, {
  "label": "美兰区",
  "value": "460108"
}], [{
  "label": "海棠区",
  "value": "460202"
}, {
  "label": "吉阳区",
  "value": "460203"
}, {
  "label": "天涯区",
  "value": "460204"
}, {
  "label": "崖州区",
  "value": "460205"
}], [{
  "label": "西沙群岛",
  "value": "460321"
}, {
  "label": "南沙群岛",
  "value": "460322"
}, {
  "label": "中沙群岛的岛礁及其海域",
  "value": "460323"
}], [{
  "label": "儋州市",
  "value": "460400"
}], [{
  "label": "五指山市",
  "value": "469001"
}, {
  "label": "琼海市",
  "value": "469002"
}, {
  "label": "文昌市",
  "value": "469005"
}, {
  "label": "万宁市",
  "value": "469006"
}, {
  "label": "东方市",
  "value": "469007"
}, {
  "label": "定安县",
  "value": "469021"
}, {
  "label": "屯昌县",
  "value": "469022"
}, {
  "label": "澄迈县",
  "value": "469023"
}, {
  "label": "临高县",
  "value": "469024"
}, {
  "label": "白沙黎族自治县",
  "value": "469025"
}, {
  "label": "昌江黎族自治县",
  "value": "469026"
}, {
  "label": "乐东黎族自治县",
  "value": "469027"
}, {
  "label": "陵水黎族自治县",
  "value": "469028"
}, {
  "label": "保亭黎族苗族自治县",
  "value": "469029"
}, {
  "label": "琼中黎族苗族自治县",
  "value": "469030"
}]], [[{
  "label": "万州区",
  "value": "500101"
}, {
  "label": "涪陵区",
  "value": "500102"
}, {
  "label": "渝中区",
  "value": "500103"
}, {
  "label": "大渡口区",
  "value": "500104"
}, {
  "label": "江北区",
  "value": "500105"
}, {
  "label": "沙坪坝区",
  "value": "500106"
}, {
  "label": "九龙坡区",
  "value": "500107"
}, {
  "label": "南岸区",
  "value": "500108"
}, {
  "label": "北碚区",
  "value": "500109"
}, {
  "label": "綦江区",
  "value": "500110"
}, {
  "label": "大足区",
  "value": "500111"
}, {
  "label": "渝北区",
  "value": "500112"
}, {
  "label": "巴南区",
  "value": "500113"
}, {
  "label": "黔江区",
  "value": "500114"
}, {
  "label": "长寿区",
  "value": "500115"
}, {
  "label": "江津区",
  "value": "500116"
}, {
  "label": "合川区",
  "value": "500117"
}, {
  "label": "永川区",
  "value": "500118"
}, {
  "label": "南川区",
  "value": "500119"
}, {
  "label": "璧山区",
  "value": "500120"
}, {
  "label": "铜梁区",
  "value": "500151"
}, {
  "label": "潼南区",
  "value": "500152"
}, {
  "label": "荣昌区",
  "value": "500153"
}, {
  "label": "开州区",
  "value": "500154"
}, {
  "label": "梁平区",
  "value": "500155"
}, {
  "label": "武隆区",
  "value": "500156"
}], [{
  "label": "城口县",
  "value": "500229"
}, {
  "label": "丰都县",
  "value": "500230"
}, {
  "label": "垫江县",
  "value": "500231"
}, {
  "label": "忠县",
  "value": "500233"
}, {
  "label": "云阳县",
  "value": "500235"
}, {
  "label": "奉节县",
  "value": "500236"
}, {
  "label": "巫山县",
  "value": "500237"
}, {
  "label": "巫溪县",
  "value": "500238"
}, {
  "label": "石柱土家族自治县",
  "value": "500240"
}, {
  "label": "秀山土家族苗族自治县",
  "value": "500241"
}, {
  "label": "酉阳土家族苗族自治县",
  "value": "500242"
}, {
  "label": "彭水苗族土家族自治县",
  "value": "500243"
}]], [[{
  "label": "锦江区",
  "value": "510104"
}, {
  "label": "青羊区",
  "value": "510105"
}, {
  "label": "金牛区",
  "value": "510106"
}, {
  "label": "武侯区",
  "value": "510107"
}, {
  "label": "成华区",
  "value": "510108"
}, {
  "label": "龙泉驿区",
  "value": "510112"
}, {
  "label": "青白江区",
  "value": "510113"
}, {
  "label": "新都区",
  "value": "510114"
}, {
  "label": "温江区",
  "value": "510115"
}, {
  "label": "双流区",
  "value": "510116"
}, {
  "label": "郫都区",
  "value": "510117"
}, {
  "label": "金堂县",
  "value": "510121"
}, {
  "label": "大邑县",
  "value": "510129"
}, {
  "label": "蒲江县",
  "value": "510131"
}, {
  "label": "新津县",
  "value": "510132"
}, {
  "label": "都江堰市",
  "value": "510181"
}, {
  "label": "彭州市",
  "value": "510182"
}, {
  "label": "邛崃市",
  "value": "510183"
}, {
  "label": "崇州市",
  "value": "510184"
}, {
  "label": "简阳市",
  "value": "510185"
}], [{
  "label": "自流井区",
  "value": "510302"
}, {
  "label": "贡井区",
  "value": "510303"
}, {
  "label": "大安区",
  "value": "510304"
}, {
  "label": "沿滩区",
  "value": "510311"
}, {
  "label": "荣县",
  "value": "510321"
}, {
  "label": "富顺县",
  "value": "510322"
}], [{
  "label": "东区",
  "value": "510402"
}, {
  "label": "西区",
  "value": "510403"
}, {
  "label": "仁和区",
  "value": "510411"
}, {
  "label": "米易县",
  "value": "510421"
}, {
  "label": "盐边县",
  "value": "510422"
}], [{
  "label": "江阳区",
  "value": "510502"
}, {
  "label": "纳溪区",
  "value": "510503"
}, {
  "label": "龙马潭区",
  "value": "510504"
}, {
  "label": "泸县",
  "value": "510521"
}, {
  "label": "合江县",
  "value": "510522"
}, {
  "label": "叙永县",
  "value": "510524"
}, {
  "label": "古蔺县",
  "value": "510525"
}], [{
  "label": "旌阳区",
  "value": "510603"
}, {
  "label": "罗江区",
  "value": "510604"
}, {
  "label": "中江县",
  "value": "510623"
}, {
  "label": "广汉市",
  "value": "510681"
}, {
  "label": "什邡市",
  "value": "510682"
}, {
  "label": "绵竹市",
  "value": "510683"
}], [{
  "label": "涪城区",
  "value": "510703"
}, {
  "label": "游仙区",
  "value": "510704"
}, {
  "label": "安州区",
  "value": "510705"
}, {
  "label": "三台县",
  "value": "510722"
}, {
  "label": "盐亭县",
  "value": "510723"
}, {
  "label": "梓潼县",
  "value": "510725"
}, {
  "label": "北川羌族自治县",
  "value": "510726"
}, {
  "label": "平武县",
  "value": "510727"
}, {
  "label": "江油市",
  "value": "510781"
}], [{
  "label": "利州区",
  "value": "510802"
}, {
  "label": "昭化区",
  "value": "510811"
}, {
  "label": "朝天区",
  "value": "510812"
}, {
  "label": "旺苍县",
  "value": "510821"
}, {
  "label": "青川县",
  "value": "510822"
}, {
  "label": "剑阁县",
  "value": "510823"
}, {
  "label": "苍溪县",
  "value": "510824"
}], [{
  "label": "船山区",
  "value": "510903"
}, {
  "label": "安居区",
  "value": "510904"
}, {
  "label": "蓬溪县",
  "value": "510921"
}, {
  "label": "射洪县",
  "value": "510922"
}, {
  "label": "大英县",
  "value": "510923"
}], [{
  "label": "市中区",
  "value": "511002"
}, {
  "label": "东兴区",
  "value": "511011"
}, {
  "label": "威远县",
  "value": "511024"
}, {
  "label": "资中县",
  "value": "511025"
}, {
  "label": "内江经济开发区",
  "value": "511071"
}, {
  "label": "隆昌市",
  "value": "511083"
}], [{
  "label": "市中区",
  "value": "511102"
}, {
  "label": "沙湾区",
  "value": "511111"
}, {
  "label": "五通桥区",
  "value": "511112"
}, {
  "label": "金口河区",
  "value": "511113"
}, {
  "label": "犍为县",
  "value": "511123"
}, {
  "label": "井研县",
  "value": "511124"
}, {
  "label": "夹江县",
  "value": "511126"
}, {
  "label": "沐川县",
  "value": "511129"
}, {
  "label": "峨边彝族自治县",
  "value": "511132"
}, {
  "label": "马边彝族自治县",
  "value": "511133"
}, {
  "label": "峨眉山市",
  "value": "511181"
}], [{
  "label": "顺庆区",
  "value": "511302"
}, {
  "label": "高坪区",
  "value": "511303"
}, {
  "label": "嘉陵区",
  "value": "511304"
}, {
  "label": "南部县",
  "value": "511321"
}, {
  "label": "营山县",
  "value": "511322"
}, {
  "label": "蓬安县",
  "value": "511323"
}, {
  "label": "仪陇县",
  "value": "511324"
}, {
  "label": "西充县",
  "value": "511325"
}, {
  "label": "阆中市",
  "value": "511381"
}], [{
  "label": "东坡区",
  "value": "511402"
}, {
  "label": "彭山区",
  "value": "511403"
}, {
  "label": "仁寿县",
  "value": "511421"
}, {
  "label": "洪雅县",
  "value": "511423"
}, {
  "label": "丹棱县",
  "value": "511424"
}, {
  "label": "青神县",
  "value": "511425"
}], [{
  "label": "翠屏区",
  "value": "511502"
}, {
  "label": "南溪区",
  "value": "511503"
}, {
  "label": "宜宾县",
  "value": "511521"
}, {
  "label": "江安县",
  "value": "511523"
}, {
  "label": "长宁县",
  "value": "511524"
}, {
  "label": "高县",
  "value": "511525"
}, {
  "label": "珙县",
  "value": "511526"
}, {
  "label": "筠连县",
  "value": "511527"
}, {
  "label": "兴文县",
  "value": "511528"
}, {
  "label": "屏山县",
  "value": "511529"
}], [{
  "label": "广安区",
  "value": "511602"
}, {
  "label": "前锋区",
  "value": "511603"
}, {
  "label": "岳池县",
  "value": "511621"
}, {
  "label": "武胜县",
  "value": "511622"
}, {
  "label": "邻水县",
  "value": "511623"
}, {
  "label": "华蓥市",
  "value": "511681"
}], [{
  "label": "通川区",
  "value": "511702"
}, {
  "label": "达川区",
  "value": "511703"
}, {
  "label": "宣汉县",
  "value": "511722"
}, {
  "label": "开江县",
  "value": "511723"
}, {
  "label": "大竹县",
  "value": "511724"
}, {
  "label": "渠县",
  "value": "511725"
}, {
  "label": "达州经济开发区",
  "value": "511771"
}, {
  "label": "万源市",
  "value": "511781"
}], [{
  "label": "雨城区",
  "value": "511802"
}, {
  "label": "名山区",
  "value": "511803"
}, {
  "label": "荥经县",
  "value": "511822"
}, {
  "label": "汉源县",
  "value": "511823"
}, {
  "label": "石棉县",
  "value": "511824"
}, {
  "label": "天全县",
  "value": "511825"
}, {
  "label": "芦山县",
  "value": "511826"
}, {
  "label": "宝兴县",
  "value": "511827"
}], [{
  "label": "巴州区",
  "value": "511902"
}, {
  "label": "恩阳区",
  "value": "511903"
}, {
  "label": "通江县",
  "value": "511921"
}, {
  "label": "南江县",
  "value": "511922"
}, {
  "label": "平昌县",
  "value": "511923"
}, {
  "label": "巴中经济开发区",
  "value": "511971"
}], [{
  "label": "雁江区",
  "value": "512002"
}, {
  "label": "安岳县",
  "value": "512021"
}, {
  "label": "乐至县",
  "value": "512022"
}], [{
  "label": "马尔康市",
  "value": "513201"
}, {
  "label": "汶川县",
  "value": "513221"
}, {
  "label": "理县",
  "value": "513222"
}, {
  "label": "茂县",
  "value": "513223"
}, {
  "label": "松潘县",
  "value": "513224"
}, {
  "label": "九寨沟县",
  "value": "513225"
}, {
  "label": "金川县",
  "value": "513226"
}, {
  "label": "小金县",
  "value": "513227"
}, {
  "label": "黑水县",
  "value": "513228"
}, {
  "label": "壤塘县",
  "value": "513230"
}, {
  "label": "阿坝县",
  "value": "513231"
}, {
  "label": "若尔盖县",
  "value": "513232"
}, {
  "label": "红原县",
  "value": "513233"
}], [{
  "label": "康定市",
  "value": "513301"
}, {
  "label": "泸定县",
  "value": "513322"
}, {
  "label": "丹巴县",
  "value": "513323"
}, {
  "label": "九龙县",
  "value": "513324"
}, {
  "label": "雅江县",
  "value": "513325"
}, {
  "label": "道孚县",
  "value": "513326"
}, {
  "label": "炉霍县",
  "value": "513327"
}, {
  "label": "甘孜县",
  "value": "513328"
}, {
  "label": "新龙县",
  "value": "513329"
}, {
  "label": "德格县",
  "value": "513330"
}, {
  "label": "白玉县",
  "value": "513331"
}, {
  "label": "石渠县",
  "value": "513332"
}, {
  "label": "色达县",
  "value": "513333"
}, {
  "label": "理塘县",
  "value": "513334"
}, {
  "label": "巴塘县",
  "value": "513335"
}, {
  "label": "乡城县",
  "value": "513336"
}, {
  "label": "稻城县",
  "value": "513337"
}, {
  "label": "得荣县",
  "value": "513338"
}], [{
  "label": "西昌市",
  "value": "513401"
}, {
  "label": "木里藏族自治县",
  "value": "513422"
}, {
  "label": "盐源县",
  "value": "513423"
}, {
  "label": "德昌县",
  "value": "513424"
}, {
  "label": "会理县",
  "value": "513425"
}, {
  "label": "会东县",
  "value": "513426"
}, {
  "label": "宁南县",
  "value": "513427"
}, {
  "label": "普格县",
  "value": "513428"
}, {
  "label": "布拖县",
  "value": "513429"
}, {
  "label": "金阳县",
  "value": "513430"
}, {
  "label": "昭觉县",
  "value": "513431"
}, {
  "label": "喜德县",
  "value": "513432"
}, {
  "label": "冕宁县",
  "value": "513433"
}, {
  "label": "越西县",
  "value": "513434"
}, {
  "label": "甘洛县",
  "value": "513435"
}, {
  "label": "美姑县",
  "value": "513436"
}, {
  "label": "雷波县",
  "value": "513437"
}]], [[{
  "label": "南明区",
  "value": "520102"
}, {
  "label": "云岩区",
  "value": "520103"
}, {
  "label": "花溪区",
  "value": "520111"
}, {
  "label": "乌当区",
  "value": "520112"
}, {
  "label": "白云区",
  "value": "520113"
}, {
  "label": "观山湖区",
  "value": "520115"
}, {
  "label": "开阳县",
  "value": "520121"
}, {
  "label": "息烽县",
  "value": "520122"
}, {
  "label": "修文县",
  "value": "520123"
}, {
  "label": "清镇市",
  "value": "520181"
}], [{
  "label": "钟山区",
  "value": "520201"
}, {
  "label": "六枝特区",
  "value": "520203"
}, {
  "label": "水城县",
  "value": "520221"
}, {
  "label": "盘州市",
  "value": "520281"
}], [{
  "label": "红花岗区",
  "value": "520302"
}, {
  "label": "汇川区",
  "value": "520303"
}, {
  "label": "播州区",
  "value": "520304"
}, {
  "label": "桐梓县",
  "value": "520322"
}, {
  "label": "绥阳县",
  "value": "520323"
}, {
  "label": "正安县",
  "value": "520324"
}, {
  "label": "道真仡佬族苗族自治县",
  "value": "520325"
}, {
  "label": "务川仡佬族苗族自治县",
  "value": "520326"
}, {
  "label": "凤冈县",
  "value": "520327"
}, {
  "label": "湄潭县",
  "value": "520328"
}, {
  "label": "余庆县",
  "value": "520329"
}, {
  "label": "习水县",
  "value": "520330"
}, {
  "label": "赤水市",
  "value": "520381"
}, {
  "label": "仁怀市",
  "value": "520382"
}], [{
  "label": "西秀区",
  "value": "520402"
}, {
  "label": "平坝区",
  "value": "520403"
}, {
  "label": "普定县",
  "value": "520422"
}, {
  "label": "镇宁布依族苗族自治县",
  "value": "520423"
}, {
  "label": "关岭布依族苗族自治县",
  "value": "520424"
}, {
  "label": "紫云苗族布依族自治县",
  "value": "520425"
}], [{
  "label": "七星关区",
  "value": "520502"
}, {
  "label": "大方县",
  "value": "520521"
}, {
  "label": "黔西县",
  "value": "520522"
}, {
  "label": "金沙县",
  "value": "520523"
}, {
  "label": "织金县",
  "value": "520524"
}, {
  "label": "纳雍县",
  "value": "520525"
}, {
  "label": "威宁彝族回族苗族自治县",
  "value": "520526"
}, {
  "label": "赫章县",
  "value": "520527"
}], [{
  "label": "碧江区",
  "value": "520602"
}, {
  "label": "万山区",
  "value": "520603"
}, {
  "label": "江口县",
  "value": "520621"
}, {
  "label": "玉屏侗族自治县",
  "value": "520622"
}, {
  "label": "石阡县",
  "value": "520623"
}, {
  "label": "思南县",
  "value": "520624"
}, {
  "label": "印江土家族苗族自治县",
  "value": "520625"
}, {
  "label": "德江县",
  "value": "520626"
}, {
  "label": "沿河土家族自治县",
  "value": "520627"
}, {
  "label": "松桃苗族自治县",
  "value": "520628"
}], [{
  "label": "兴义市",
  "value": "522301"
}, {
  "label": "兴仁县",
  "value": "522322"
}, {
  "label": "普安县",
  "value": "522323"
}, {
  "label": "晴隆县",
  "value": "522324"
}, {
  "label": "贞丰县",
  "value": "522325"
}, {
  "label": "望谟县",
  "value": "522326"
}, {
  "label": "册亨县",
  "value": "522327"
}, {
  "label": "安龙县",
  "value": "522328"
}], [{
  "label": "凯里市",
  "value": "522601"
}, {
  "label": "黄平县",
  "value": "522622"
}, {
  "label": "施秉县",
  "value": "522623"
}, {
  "label": "三穗县",
  "value": "522624"
}, {
  "label": "镇远县",
  "value": "522625"
}, {
  "label": "岑巩县",
  "value": "522626"
}, {
  "label": "天柱县",
  "value": "522627"
}, {
  "label": "锦屏县",
  "value": "522628"
}, {
  "label": "剑河县",
  "value": "522629"
}, {
  "label": "台江县",
  "value": "522630"
}, {
  "label": "黎平县",
  "value": "522631"
}, {
  "label": "榕江县",
  "value": "522632"
}, {
  "label": "从江县",
  "value": "522633"
}, {
  "label": "雷山县",
  "value": "522634"
}, {
  "label": "麻江县",
  "value": "522635"
}, {
  "label": "丹寨县",
  "value": "522636"
}], [{
  "label": "都匀市",
  "value": "522701"
}, {
  "label": "福泉市",
  "value": "522702"
}, {
  "label": "荔波县",
  "value": "522722"
}, {
  "label": "贵定县",
  "value": "522723"
}, {
  "label": "瓮安县",
  "value": "522725"
}, {
  "label": "独山县",
  "value": "522726"
}, {
  "label": "平塘县",
  "value": "522727"
}, {
  "label": "罗甸县",
  "value": "522728"
}, {
  "label": "长顺县",
  "value": "522729"
}, {
  "label": "龙里县",
  "value": "522730"
}, {
  "label": "惠水县",
  "value": "522731"
}, {
  "label": "三都水族自治县",
  "value": "522732"
}]], [[{
  "label": "五华区",
  "value": "530102"
}, {
  "label": "盘龙区",
  "value": "530103"
}, {
  "label": "官渡区",
  "value": "530111"
}, {
  "label": "西山区",
  "value": "530112"
}, {
  "label": "东川区",
  "value": "530113"
}, {
  "label": "呈贡区",
  "value": "530114"
}, {
  "label": "晋宁区",
  "value": "530115"
}, {
  "label": "富民县",
  "value": "530124"
}, {
  "label": "宜良县",
  "value": "530125"
}, {
  "label": "石林彝族自治县",
  "value": "530126"
}, {
  "label": "嵩明县",
  "value": "530127"
}, {
  "label": "禄劝彝族苗族自治县",
  "value": "530128"
}, {
  "label": "寻甸回族彝族自治县",
  "value": "530129"
}, {
  "label": "安宁市",
  "value": "530181"
}], [{
  "label": "麒麟区",
  "value": "530302"
}, {
  "label": "沾益区",
  "value": "530303"
}, {
  "label": "马龙县",
  "value": "530321"
}, {
  "label": "陆良县",
  "value": "530322"
}, {
  "label": "师宗县",
  "value": "530323"
}, {
  "label": "罗平县",
  "value": "530324"
}, {
  "label": "富源县",
  "value": "530325"
}, {
  "label": "会泽县",
  "value": "530326"
}, {
  "label": "宣威市",
  "value": "530381"
}], [{
  "label": "红塔区",
  "value": "530402"
}, {
  "label": "江川区",
  "value": "530403"
}, {
  "label": "澄江县",
  "value": "530422"
}, {
  "label": "通海县",
  "value": "530423"
}, {
  "label": "华宁县",
  "value": "530424"
}, {
  "label": "易门县",
  "value": "530425"
}, {
  "label": "峨山彝族自治县",
  "value": "530426"
}, {
  "label": "新平彝族傣族自治县",
  "value": "530427"
}, {
  "label": "元江哈尼族彝族傣族自治县",
  "value": "530428"
}], [{
  "label": "隆阳区",
  "value": "530502"
}, {
  "label": "施甸县",
  "value": "530521"
}, {
  "label": "龙陵县",
  "value": "530523"
}, {
  "label": "昌宁县",
  "value": "530524"
}, {
  "label": "腾冲市",
  "value": "530581"
}], [{
  "label": "昭阳区",
  "value": "530602"
}, {
  "label": "鲁甸县",
  "value": "530621"
}, {
  "label": "巧家县",
  "value": "530622"
}, {
  "label": "盐津县",
  "value": "530623"
}, {
  "label": "大关县",
  "value": "530624"
}, {
  "label": "永善县",
  "value": "530625"
}, {
  "label": "绥江县",
  "value": "530626"
}, {
  "label": "镇雄县",
  "value": "530627"
}, {
  "label": "彝良县",
  "value": "530628"
}, {
  "label": "威信县",
  "value": "530629"
}, {
  "label": "水富县",
  "value": "530630"
}], [{
  "label": "古城区",
  "value": "530702"
}, {
  "label": "玉龙纳西族自治县",
  "value": "530721"
}, {
  "label": "永胜县",
  "value": "530722"
}, {
  "label": "华坪县",
  "value": "530723"
}, {
  "label": "宁蒗彝族自治县",
  "value": "530724"
}], [{
  "label": "思茅区",
  "value": "530802"
}, {
  "label": "宁洱哈尼族彝族自治县",
  "value": "530821"
}, {
  "label": "墨江哈尼族自治县",
  "value": "530822"
}, {
  "label": "景东彝族自治县",
  "value": "530823"
}, {
  "label": "景谷傣族彝族自治县",
  "value": "530824"
}, {
  "label": "镇沅彝族哈尼族拉祜族自治县",
  "value": "530825"
}, {
  "label": "江城哈尼族彝族自治县",
  "value": "530826"
}, {
  "label": "孟连傣族拉祜族佤族自治县",
  "value": "530827"
}, {
  "label": "澜沧拉祜族自治县",
  "value": "530828"
}, {
  "label": "西盟佤族自治县",
  "value": "530829"
}], [{
  "label": "临翔区",
  "value": "530902"
}, {
  "label": "凤庆县",
  "value": "530921"
}, {
  "label": "云县",
  "value": "530922"
}, {
  "label": "永德县",
  "value": "530923"
}, {
  "label": "镇康县",
  "value": "530924"
}, {
  "label": "双江拉祜族佤族布朗族傣族自治县",
  "value": "530925"
}, {
  "label": "耿马傣族佤族自治县",
  "value": "530926"
}, {
  "label": "沧源佤族自治县",
  "value": "530927"
}], [{
  "label": "楚雄市",
  "value": "532301"
}, {
  "label": "双柏县",
  "value": "532322"
}, {
  "label": "牟定县",
  "value": "532323"
}, {
  "label": "南华县",
  "value": "532324"
}, {
  "label": "姚安县",
  "value": "532325"
}, {
  "label": "大姚县",
  "value": "532326"
}, {
  "label": "永仁县",
  "value": "532327"
}, {
  "label": "元谋县",
  "value": "532328"
}, {
  "label": "武定县",
  "value": "532329"
}, {
  "label": "禄丰县",
  "value": "532331"
}], [{
  "label": "个旧市",
  "value": "532501"
}, {
  "label": "开远市",
  "value": "532502"
}, {
  "label": "蒙自市",
  "value": "532503"
}, {
  "label": "弥勒市",
  "value": "532504"
}, {
  "label": "屏边苗族自治县",
  "value": "532523"
}, {
  "label": "建水县",
  "value": "532524"
}, {
  "label": "石屏县",
  "value": "532525"
}, {
  "label": "泸西县",
  "value": "532527"
}, {
  "label": "元阳县",
  "value": "532528"
}, {
  "label": "红河县",
  "value": "532529"
}, {
  "label": "金平苗族瑶族傣族自治县",
  "value": "532530"
}, {
  "label": "绿春县",
  "value": "532531"
}, {
  "label": "河口瑶族自治县",
  "value": "532532"
}], [{
  "label": "文山市",
  "value": "532601"
}, {
  "label": "砚山县",
  "value": "532622"
}, {
  "label": "西畴县",
  "value": "532623"
}, {
  "label": "麻栗坡县",
  "value": "532624"
}, {
  "label": "马关县",
  "value": "532625"
}, {
  "label": "丘北县",
  "value": "532626"
}, {
  "label": "广南县",
  "value": "532627"
}, {
  "label": "富宁县",
  "value": "532628"
}], [{
  "label": "景洪市",
  "value": "532801"
}, {
  "label": "勐海县",
  "value": "532822"
}, {
  "label": "勐腊县",
  "value": "532823"
}], [{
  "label": "大理市",
  "value": "532901"
}, {
  "label": "漾濞彝族自治县",
  "value": "532922"
}, {
  "label": "祥云县",
  "value": "532923"
}, {
  "label": "宾川县",
  "value": "532924"
}, {
  "label": "弥渡县",
  "value": "532925"
}, {
  "label": "南涧彝族自治县",
  "value": "532926"
}, {
  "label": "巍山彝族回族自治县",
  "value": "532927"
}, {
  "label": "永平县",
  "value": "532928"
}, {
  "label": "云龙县",
  "value": "532929"
}, {
  "label": "洱源县",
  "value": "532930"
}, {
  "label": "剑川县",
  "value": "532931"
}, {
  "label": "鹤庆县",
  "value": "532932"
}], [{
  "label": "瑞丽市",
  "value": "533102"
}, {
  "label": "芒市",
  "value": "533103"
}, {
  "label": "梁河县",
  "value": "533122"
}, {
  "label": "盈江县",
  "value": "533123"
}, {
  "label": "陇川县",
  "value": "533124"
}], [{
  "label": "泸水市",
  "value": "533301"
}, {
  "label": "福贡县",
  "value": "533323"
}, {
  "label": "贡山独龙族怒族自治县",
  "value": "533324"
}, {
  "label": "兰坪白族普米族自治县",
  "value": "533325"
}], [{
  "label": "香格里拉市",
  "value": "533401"
}, {
  "label": "德钦县",
  "value": "533422"
}, {
  "label": "维西傈僳族自治县",
  "value": "533423"
}]], [[{
  "label": "城关区",
  "value": "540102"
}, {
  "label": "堆龙德庆区",
  "value": "540103"
}, {
  "label": "林周县",
  "value": "540121"
}, {
  "label": "当雄县",
  "value": "540122"
}, {
  "label": "尼木县",
  "value": "540123"
}, {
  "label": "曲水县",
  "value": "540124"
}, {
  "label": "达孜县",
  "value": "540126"
}, {
  "label": "墨竹工卡县",
  "value": "540127"
}, {
  "label": "格尔木藏青工业园区",
  "value": "540171"
}, {
  "label": "拉萨经济技术开发区",
  "value": "540172"
}, {
  "label": "西藏文化旅游创意园区",
  "value": "540173"
}, {
  "label": "达孜工业园区",
  "value": "540174"
}], [{
  "label": "桑珠孜区",
  "value": "540202"
}, {
  "label": "南木林县",
  "value": "540221"
}, {
  "label": "江孜县",
  "value": "540222"
}, {
  "label": "定日县",
  "value": "540223"
}, {
  "label": "萨迦县",
  "value": "540224"
}, {
  "label": "拉孜县",
  "value": "540225"
}, {
  "label": "昂仁县",
  "value": "540226"
}, {
  "label": "谢通门县",
  "value": "540227"
}, {
  "label": "白朗县",
  "value": "540228"
}, {
  "label": "仁布县",
  "value": "540229"
}, {
  "label": "康马县",
  "value": "540230"
}, {
  "label": "定结县",
  "value": "540231"
}, {
  "label": "仲巴县",
  "value": "540232"
}, {
  "label": "亚东县",
  "value": "540233"
}, {
  "label": "吉隆县",
  "value": "540234"
}, {
  "label": "聂拉木县",
  "value": "540235"
}, {
  "label": "萨嘎县",
  "value": "540236"
}, {
  "label": "岗巴县",
  "value": "540237"
}], [{
  "label": "卡若区",
  "value": "540302"
}, {
  "label": "江达县",
  "value": "540321"
}, {
  "label": "贡觉县",
  "value": "540322"
}, {
  "label": "类乌齐县",
  "value": "540323"
}, {
  "label": "丁青县",
  "value": "540324"
}, {
  "label": "察雅县",
  "value": "540325"
}, {
  "label": "八宿县",
  "value": "540326"
}, {
  "label": "左贡县",
  "value": "540327"
}, {
  "label": "芒康县",
  "value": "540328"
}, {
  "label": "洛隆县",
  "value": "540329"
}, {
  "label": "边坝县",
  "value": "540330"
}], [{
  "label": "巴宜区",
  "value": "540402"
}, {
  "label": "工布江达县",
  "value": "540421"
}, {
  "label": "米林县",
  "value": "540422"
}, {
  "label": "墨脱县",
  "value": "540423"
}, {
  "label": "波密县",
  "value": "540424"
}, {
  "label": "察隅县",
  "value": "540425"
}, {
  "label": "朗县",
  "value": "540426"
}], [{
  "label": "乃东区",
  "value": "540502"
}, {
  "label": "扎囊县",
  "value": "540521"
}, {
  "label": "贡嘎县",
  "value": "540522"
}, {
  "label": "桑日县",
  "value": "540523"
}, {
  "label": "琼结县",
  "value": "540524"
}, {
  "label": "曲松县",
  "value": "540525"
}, {
  "label": "措美县",
  "value": "540526"
}, {
  "label": "洛扎县",
  "value": "540527"
}, {
  "label": "加查县",
  "value": "540528"
}, {
  "label": "隆子县",
  "value": "540529"
}, {
  "label": "错那县",
  "value": "540530"
}, {
  "label": "浪卡子县",
  "value": "540531"
}], [{
  "label": "那曲县",
  "value": "542421"
}, {
  "label": "嘉黎县",
  "value": "542422"
}, {
  "label": "比如县",
  "value": "542423"
}, {
  "label": "聂荣县",
  "value": "542424"
}, {
  "label": "安多县",
  "value": "542425"
}, {
  "label": "申扎县",
  "value": "542426"
}, {
  "label": "索县",
  "value": "542427"
}, {
  "label": "班戈县",
  "value": "542428"
}, {
  "label": "巴青县",
  "value": "542429"
}, {
  "label": "尼玛县",
  "value": "542430"
}, {
  "label": "双湖县",
  "value": "542431"
}], [{
  "label": "普兰县",
  "value": "542521"
}, {
  "label": "札达县",
  "value": "542522"
}, {
  "label": "噶尔县",
  "value": "542523"
}, {
  "label": "日土县",
  "value": "542524"
}, {
  "label": "革吉县",
  "value": "542525"
}, {
  "label": "改则县",
  "value": "542526"
}, {
  "label": "措勤县",
  "value": "542527"
}]], [[{
  "label": "新城区",
  "value": "610102"
}, {
  "label": "碑林区",
  "value": "610103"
}, {
  "label": "莲湖区",
  "value": "610104"
}, {
  "label": "灞桥区",
  "value": "610111"
}, {
  "label": "未央区",
  "value": "610112"
}, {
  "label": "雁塔区",
  "value": "610113"
}, {
  "label": "阎良区",
  "value": "610114"
}, {
  "label": "临潼区",
  "value": "610115"
}, {
  "label": "长安区",
  "value": "610116"
}, {
  "label": "高陵区",
  "value": "610117"
}, {
  "label": "鄠邑区",
  "value": "610118"
}, {
  "label": "蓝田县",
  "value": "610122"
}, {
  "label": "周至县",
  "value": "610124"
}], [{
  "label": "王益区",
  "value": "610202"
}, {
  "label": "印台区",
  "value": "610203"
}, {
  "label": "耀州区",
  "value": "610204"
}, {
  "label": "宜君县",
  "value": "610222"
}], [{
  "label": "渭滨区",
  "value": "610302"
}, {
  "label": "金台区",
  "value": "610303"
}, {
  "label": "陈仓区",
  "value": "610304"
}, {
  "label": "凤翔县",
  "value": "610322"
}, {
  "label": "岐山县",
  "value": "610323"
}, {
  "label": "扶风县",
  "value": "610324"
}, {
  "label": "眉县",
  "value": "610326"
}, {
  "label": "陇县",
  "value": "610327"
}, {
  "label": "千阳县",
  "value": "610328"
}, {
  "label": "麟游县",
  "value": "610329"
}, {
  "label": "凤县",
  "value": "610330"
}, {
  "label": "太白县",
  "value": "610331"
}], [{
  "label": "秦都区",
  "value": "610402"
}, {
  "label": "杨陵区",
  "value": "610403"
}, {
  "label": "渭城区",
  "value": "610404"
}, {
  "label": "三原县",
  "value": "610422"
}, {
  "label": "泾阳县",
  "value": "610423"
}, {
  "label": "乾县",
  "value": "610424"
}, {
  "label": "礼泉县",
  "value": "610425"
}, {
  "label": "永寿县",
  "value": "610426"
}, {
  "label": "彬县",
  "value": "610427"
}, {
  "label": "长武县",
  "value": "610428"
}, {
  "label": "旬邑县",
  "value": "610429"
}, {
  "label": "淳化县",
  "value": "610430"
}, {
  "label": "武功县",
  "value": "610431"
}, {
  "label": "兴平市",
  "value": "610481"
}], [{
  "label": "临渭区",
  "value": "610502"
}, {
  "label": "华州区",
  "value": "610503"
}, {
  "label": "潼关县",
  "value": "610522"
}, {
  "label": "大荔县",
  "value": "610523"
}, {
  "label": "合阳县",
  "value": "610524"
}, {
  "label": "澄城县",
  "value": "610525"
}, {
  "label": "蒲城县",
  "value": "610526"
}, {
  "label": "白水县",
  "value": "610527"
}, {
  "label": "富平县",
  "value": "610528"
}, {
  "label": "韩城市",
  "value": "610581"
}, {
  "label": "华阴市",
  "value": "610582"
}], [{
  "label": "宝塔区",
  "value": "610602"
}, {
  "label": "安塞区",
  "value": "610603"
}, {
  "label": "延长县",
  "value": "610621"
}, {
  "label": "延川县",
  "value": "610622"
}, {
  "label": "子长县",
  "value": "610623"
}, {
  "label": "志丹县",
  "value": "610625"
}, {
  "label": "吴起县",
  "value": "610626"
}, {
  "label": "甘泉县",
  "value": "610627"
}, {
  "label": "富县",
  "value": "610628"
}, {
  "label": "洛川县",
  "value": "610629"
}, {
  "label": "宜川县",
  "value": "610630"
}, {
  "label": "黄龙县",
  "value": "610631"
}, {
  "label": "黄陵县",
  "value": "610632"
}], [{
  "label": "汉台区",
  "value": "610702"
}, {
  "label": "南郑区",
  "value": "610703"
}, {
  "label": "城固县",
  "value": "610722"
}, {
  "label": "洋县",
  "value": "610723"
}, {
  "label": "西乡县",
  "value": "610724"
}, {
  "label": "勉县",
  "value": "610725"
}, {
  "label": "宁强县",
  "value": "610726"
}, {
  "label": "略阳县",
  "value": "610727"
}, {
  "label": "镇巴县",
  "value": "610728"
}, {
  "label": "留坝县",
  "value": "610729"
}, {
  "label": "佛坪县",
  "value": "610730"
}], [{
  "label": "榆阳区",
  "value": "610802"
}, {
  "label": "横山区",
  "value": "610803"
}, {
  "label": "府谷县",
  "value": "610822"
}, {
  "label": "靖边县",
  "value": "610824"
}, {
  "label": "定边县",
  "value": "610825"
}, {
  "label": "绥德县",
  "value": "610826"
}, {
  "label": "米脂县",
  "value": "610827"
}, {
  "label": "佳县",
  "value": "610828"
}, {
  "label": "吴堡县",
  "value": "610829"
}, {
  "label": "清涧县",
  "value": "610830"
}, {
  "label": "子洲县",
  "value": "610831"
}, {
  "label": "神木市",
  "value": "610881"
}], [{
  "label": "汉滨区",
  "value": "610902"
}, {
  "label": "汉阴县",
  "value": "610921"
}, {
  "label": "石泉县",
  "value": "610922"
}, {
  "label": "宁陕县",
  "value": "610923"
}, {
  "label": "紫阳县",
  "value": "610924"
}, {
  "label": "岚皋县",
  "value": "610925"
}, {
  "label": "平利县",
  "value": "610926"
}, {
  "label": "镇坪县",
  "value": "610927"
}, {
  "label": "旬阳县",
  "value": "610928"
}, {
  "label": "白河县",
  "value": "610929"
}], [{
  "label": "商州区",
  "value": "611002"
}, {
  "label": "洛南县",
  "value": "611021"
}, {
  "label": "丹凤县",
  "value": "611022"
}, {
  "label": "商南县",
  "value": "611023"
}, {
  "label": "山阳县",
  "value": "611024"
}, {
  "label": "镇安县",
  "value": "611025"
}, {
  "label": "柞水县",
  "value": "611026"
}]], [[{
  "label": "城关区",
  "value": "620102"
}, {
  "label": "七里河区",
  "value": "620103"
}, {
  "label": "西固区",
  "value": "620104"
}, {
  "label": "安宁区",
  "value": "620105"
}, {
  "label": "红古区",
  "value": "620111"
}, {
  "label": "永登县",
  "value": "620121"
}, {
  "label": "皋兰县",
  "value": "620122"
}, {
  "label": "榆中县",
  "value": "620123"
}, {
  "label": "兰州新区",
  "value": "620171"
}], [{
  "label": "嘉峪关市",
  "value": "620201"
}], [{
  "label": "金川区",
  "value": "620302"
}, {
  "label": "永昌县",
  "value": "620321"
}], [{
  "label": "白银区",
  "value": "620402"
}, {
  "label": "平川区",
  "value": "620403"
}, {
  "label": "靖远县",
  "value": "620421"
}, {
  "label": "会宁县",
  "value": "620422"
}, {
  "label": "景泰县",
  "value": "620423"
}], [{
  "label": "秦州区",
  "value": "620502"
}, {
  "label": "麦积区",
  "value": "620503"
}, {
  "label": "清水县",
  "value": "620521"
}, {
  "label": "秦安县",
  "value": "620522"
}, {
  "label": "甘谷县",
  "value": "620523"
}, {
  "label": "武山县",
  "value": "620524"
}, {
  "label": "张家川回族自治县",
  "value": "620525"
}], [{
  "label": "凉州区",
  "value": "620602"
}, {
  "label": "民勤县",
  "value": "620621"
}, {
  "label": "古浪县",
  "value": "620622"
}, {
  "label": "天祝藏族自治县",
  "value": "620623"
}], [{
  "label": "甘州区",
  "value": "620702"
}, {
  "label": "肃南裕固族自治县",
  "value": "620721"
}, {
  "label": "民乐县",
  "value": "620722"
}, {
  "label": "临泽县",
  "value": "620723"
}, {
  "label": "高台县",
  "value": "620724"
}, {
  "label": "山丹县",
  "value": "620725"
}], [{
  "label": "崆峒区",
  "value": "620802"
}, {
  "label": "泾川县",
  "value": "620821"
}, {
  "label": "灵台县",
  "value": "620822"
}, {
  "label": "崇信县",
  "value": "620823"
}, {
  "label": "华亭县",
  "value": "620824"
}, {
  "label": "庄浪县",
  "value": "620825"
}, {
  "label": "静宁县",
  "value": "620826"
}, {
  "label": "平凉工业园区",
  "value": "620871"
}], [{
  "label": "肃州区",
  "value": "620902"
}, {
  "label": "金塔县",
  "value": "620921"
}, {
  "label": "瓜州县",
  "value": "620922"
}, {
  "label": "肃北蒙古族自治县",
  "value": "620923"
}, {
  "label": "阿克塞哈萨克族自治县",
  "value": "620924"
}, {
  "label": "玉门市",
  "value": "620981"
}, {
  "label": "敦煌市",
  "value": "620982"
}], [{
  "label": "西峰区",
  "value": "621002"
}, {
  "label": "庆城县",
  "value": "621021"
}, {
  "label": "环县",
  "value": "621022"
}, {
  "label": "华池县",
  "value": "621023"
}, {
  "label": "合水县",
  "value": "621024"
}, {
  "label": "正宁县",
  "value": "621025"
}, {
  "label": "宁县",
  "value": "621026"
}, {
  "label": "镇原县",
  "value": "621027"
}], [{
  "label": "安定区",
  "value": "621102"
}, {
  "label": "通渭县",
  "value": "621121"
}, {
  "label": "陇西县",
  "value": "621122"
}, {
  "label": "渭源县",
  "value": "621123"
}, {
  "label": "临洮县",
  "value": "621124"
}, {
  "label": "漳县",
  "value": "621125"
}, {
  "label": "岷县",
  "value": "621126"
}], [{
  "label": "武都区",
  "value": "621202"
}, {
  "label": "成县",
  "value": "621221"
}, {
  "label": "文县",
  "value": "621222"
}, {
  "label": "宕昌县",
  "value": "621223"
}, {
  "label": "康县",
  "value": "621224"
}, {
  "label": "西和县",
  "value": "621225"
}, {
  "label": "礼县",
  "value": "621226"
}, {
  "label": "徽县",
  "value": "621227"
}, {
  "label": "两当县",
  "value": "621228"
}], [{
  "label": "临夏市",
  "value": "622901"
}, {
  "label": "临夏县",
  "value": "622921"
}, {
  "label": "康乐县",
  "value": "622922"
}, {
  "label": "永靖县",
  "value": "622923"
}, {
  "label": "广河县",
  "value": "622924"
}, {
  "label": "和政县",
  "value": "622925"
}, {
  "label": "东乡族自治县",
  "value": "622926"
}, {
  "label": "积石山保安族东乡族撒拉族自治县",
  "value": "622927"
}], [{
  "label": "合作市",
  "value": "623001"
}, {
  "label": "临潭县",
  "value": "623021"
}, {
  "label": "卓尼县",
  "value": "623022"
}, {
  "label": "舟曲县",
  "value": "623023"
}, {
  "label": "迭部县",
  "value": "623024"
}, {
  "label": "玛曲县",
  "value": "623025"
}, {
  "label": "碌曲县",
  "value": "623026"
}, {
  "label": "夏河县",
  "value": "623027"
}]], [[{
  "label": "城东区",
  "value": "630102"
}, {
  "label": "城中区",
  "value": "630103"
}, {
  "label": "城西区",
  "value": "630104"
}, {
  "label": "城北区",
  "value": "630105"
}, {
  "label": "大通回族土族自治县",
  "value": "630121"
}, {
  "label": "湟中县",
  "value": "630122"
}, {
  "label": "湟源县",
  "value": "630123"
}], [{
  "label": "乐都区",
  "value": "630202"
}, {
  "label": "平安区",
  "value": "630203"
}, {
  "label": "民和回族土族自治县",
  "value": "630222"
}, {
  "label": "互助土族自治县",
  "value": "630223"
}, {
  "label": "化隆回族自治县",
  "value": "630224"
}, {
  "label": "循化撒拉族自治县",
  "value": "630225"
}], [{
  "label": "门源回族自治县",
  "value": "632221"
}, {
  "label": "祁连县",
  "value": "632222"
}, {
  "label": "海晏县",
  "value": "632223"
}, {
  "label": "刚察县",
  "value": "632224"
}], [{
  "label": "同仁县",
  "value": "632321"
}, {
  "label": "尖扎县",
  "value": "632322"
}, {
  "label": "泽库县",
  "value": "632323"
}, {
  "label": "河南蒙古族自治县",
  "value": "632324"
}], [{
  "label": "共和县",
  "value": "632521"
}, {
  "label": "同德县",
  "value": "632522"
}, {
  "label": "贵德县",
  "value": "632523"
}, {
  "label": "兴海县",
  "value": "632524"
}, {
  "label": "贵南县",
  "value": "632525"
}], [{
  "label": "玛沁县",
  "value": "632621"
}, {
  "label": "班玛县",
  "value": "632622"
}, {
  "label": "甘德县",
  "value": "632623"
}, {
  "label": "达日县",
  "value": "632624"
}, {
  "label": "久治县",
  "value": "632625"
}, {
  "label": "玛多县",
  "value": "632626"
}], [{
  "label": "玉树市",
  "value": "632701"
}, {
  "label": "杂多县",
  "value": "632722"
}, {
  "label": "称多县",
  "value": "632723"
}, {
  "label": "治多县",
  "value": "632724"
}, {
  "label": "囊谦县",
  "value": "632725"
}, {
  "label": "曲麻莱县",
  "value": "632726"
}], [{
  "label": "格尔木市",
  "value": "632801"
}, {
  "label": "德令哈市",
  "value": "632802"
}, {
  "label": "乌兰县",
  "value": "632821"
}, {
  "label": "都兰县",
  "value": "632822"
}, {
  "label": "天峻县",
  "value": "632823"
}, {
  "label": "大柴旦行政委员会",
  "value": "632857"
}, {
  "label": "冷湖行政委员会",
  "value": "632858"
}, {
  "label": "茫崖行政委员会",
  "value": "632859"
}]], [[{
  "label": "兴庆区",
  "value": "640104"
}, {
  "label": "西夏区",
  "value": "640105"
}, {
  "label": "金凤区",
  "value": "640106"
}, {
  "label": "永宁县",
  "value": "640121"
}, {
  "label": "贺兰县",
  "value": "640122"
}, {
  "label": "灵武市",
  "value": "640181"
}], [{
  "label": "大武口区",
  "value": "640202"
}, {
  "label": "惠农区",
  "value": "640205"
}, {
  "label": "平罗县",
  "value": "640221"
}], [{
  "label": "利通区",
  "value": "640302"
}, {
  "label": "红寺堡区",
  "value": "640303"
}, {
  "label": "盐池县",
  "value": "640323"
}, {
  "label": "同心县",
  "value": "640324"
}, {
  "label": "青铜峡市",
  "value": "640381"
}], [{
  "label": "原州区",
  "value": "640402"
}, {
  "label": "西吉县",
  "value": "640422"
}, {
  "label": "隆德县",
  "value": "640423"
}, {
  "label": "泾源县",
  "value": "640424"
}, {
  "label": "彭阳县",
  "value": "640425"
}], [{
  "label": "沙坡头区",
  "value": "640502"
}, {
  "label": "中宁县",
  "value": "640521"
}, {
  "label": "海原县",
  "value": "640522"
}]], [[{
  "label": "天山区",
  "value": "650102"
}, {
  "label": "沙依巴克区",
  "value": "650103"
}, {
  "label": "新市区",
  "value": "650104"
}, {
  "label": "水磨沟区",
  "value": "650105"
}, {
  "label": "头屯河区",
  "value": "650106"
}, {
  "label": "达坂城区",
  "value": "650107"
}, {
  "label": "米东区",
  "value": "650109"
}, {
  "label": "乌鲁木齐县",
  "value": "650121"
}, {
  "label": "乌鲁木齐经济技术开发区",
  "value": "650171"
}, {
  "label": "乌鲁木齐高新技术产业开发区",
  "value": "650172"
}], [{
  "label": "独山子区",
  "value": "650202"
}, {
  "label": "克拉玛依区",
  "value": "650203"
}, {
  "label": "白碱滩区",
  "value": "650204"
}, {
  "label": "乌尔禾区",
  "value": "650205"
}], [{
  "label": "高昌区",
  "value": "650402"
}, {
  "label": "鄯善县",
  "value": "650421"
}, {
  "label": "托克逊县",
  "value": "650422"
}], [{
  "label": "伊州区",
  "value": "650502"
}, {
  "label": "巴里坤哈萨克自治县",
  "value": "650521"
}, {
  "label": "伊吾县",
  "value": "650522"
}], [{
  "label": "昌吉市",
  "value": "652301"
}, {
  "label": "阜康市",
  "value": "652302"
}, {
  "label": "呼图壁县",
  "value": "652323"
}, {
  "label": "玛纳斯县",
  "value": "652324"
}, {
  "label": "奇台县",
  "value": "652325"
}, {
  "label": "吉木萨尔县",
  "value": "652327"
}, {
  "label": "木垒哈萨克自治县",
  "value": "652328"
}], [{
  "label": "博乐市",
  "value": "652701"
}, {
  "label": "阿拉山口市",
  "value": "652702"
}, {
  "label": "精河县",
  "value": "652722"
}, {
  "label": "温泉县",
  "value": "652723"
}], [{
  "label": "库尔勒市",
  "value": "652801"
}, {
  "label": "轮台县",
  "value": "652822"
}, {
  "label": "尉犁县",
  "value": "652823"
}, {
  "label": "若羌县",
  "value": "652824"
}, {
  "label": "且末县",
  "value": "652825"
}, {
  "label": "焉耆回族自治县",
  "value": "652826"
}, {
  "label": "和静县",
  "value": "652827"
}, {
  "label": "和硕县",
  "value": "652828"
}, {
  "label": "博湖县",
  "value": "652829"
}, {
  "label": "库尔勒经济技术开发区",
  "value": "652871"
}], [{
  "label": "阿克苏市",
  "value": "652901"
}, {
  "label": "温宿县",
  "value": "652922"
}, {
  "label": "库车县",
  "value": "652923"
}, {
  "label": "沙雅县",
  "value": "652924"
}, {
  "label": "新和县",
  "value": "652925"
}, {
  "label": "拜城县",
  "value": "652926"
}, {
  "label": "乌什县",
  "value": "652927"
}, {
  "label": "阿瓦提县",
  "value": "652928"
}, {
  "label": "柯坪县",
  "value": "652929"
}], [{
  "label": "阿图什市",
  "value": "653001"
}, {
  "label": "阿克陶县",
  "value": "653022"
}, {
  "label": "阿合奇县",
  "value": "653023"
}, {
  "label": "乌恰县",
  "value": "653024"
}], [{
  "label": "喀什市",
  "value": "653101"
}, {
  "label": "疏附县",
  "value": "653121"
}, {
  "label": "疏勒县",
  "value": "653122"
}, {
  "label": "英吉沙县",
  "value": "653123"
}, {
  "label": "泽普县",
  "value": "653124"
}, {
  "label": "莎车县",
  "value": "653125"
}, {
  "label": "叶城县",
  "value": "653126"
}, {
  "label": "麦盖提县",
  "value": "653127"
}, {
  "label": "岳普湖县",
  "value": "653128"
}, {
  "label": "伽师县",
  "value": "653129"
}, {
  "label": "巴楚县",
  "value": "653130"
}, {
  "label": "塔什库尔干塔吉克自治县",
  "value": "653131"
}], [{
  "label": "和田市",
  "value": "653201"
}, {
  "label": "和田县",
  "value": "653221"
}, {
  "label": "墨玉县",
  "value": "653222"
}, {
  "label": "皮山县",
  "value": "653223"
}, {
  "label": "洛浦县",
  "value": "653224"
}, {
  "label": "策勒县",
  "value": "653225"
}, {
  "label": "于田县",
  "value": "653226"
}, {
  "label": "民丰县",
  "value": "653227"
}], [{
  "label": "伊宁市",
  "value": "654002"
}, {
  "label": "奎屯市",
  "value": "654003"
}, {
  "label": "霍尔果斯市",
  "value": "654004"
}, {
  "label": "伊宁县",
  "value": "654021"
}, {
  "label": "察布查尔锡伯自治县",
  "value": "654022"
}, {
  "label": "霍城县",
  "value": "654023"
}, {
  "label": "巩留县",
  "value": "654024"
}, {
  "label": "新源县",
  "value": "654025"
}, {
  "label": "昭苏县",
  "value": "654026"
}, {
  "label": "特克斯县",
  "value": "654027"
}, {
  "label": "尼勒克县",
  "value": "654028"
}], [{
  "label": "塔城市",
  "value": "654201"
}, {
  "label": "乌苏市",
  "value": "654202"
}, {
  "label": "额敏县",
  "value": "654221"
}, {
  "label": "沙湾县",
  "value": "654223"
}, {
  "label": "托里县",
  "value": "654224"
}, {
  "label": "裕民县",
  "value": "654225"
}, {
  "label": "和布克赛尔蒙古自治县",
  "value": "654226"
}], [{
  "label": "阿勒泰市",
  "value": "654301"
}, {
  "label": "布尔津县",
  "value": "654321"
}, {
  "label": "富蕴县",
  "value": "654322"
}, {
  "label": "福海县",
  "value": "654323"
}, {
  "label": "哈巴河县",
  "value": "654324"
}, {
  "label": "青河县",
  "value": "654325"
}, {
  "label": "吉木乃县",
  "value": "654326"
}], [{
  "label": "石河子市",
  "value": "659001"
}, {
  "label": "阿拉尔市",
  "value": "659002"
}, {
  "label": "图木舒克市",
  "value": "659003"
}, {
  "label": "五家渠市",
  "value": "659004"
}, {
  "label": "铁门关市",
  "value": "659006"
}]], [[{
  "label": "台北",
  "value": "660101"
}], [{
  "label": "高雄",
  "value": "660201"
}], [{
  "label": "基隆",
  "value": "660301"
}], [{
  "label": "台中",
  "value": "660401"
}], [{
  "label": "台南",
  "value": "660501"
}], [{
  "label": "新竹",
  "value": "660601"
}], [{
  "label": "嘉义",
  "value": "660701"
}], [{
  "label": "宜兰",
  "value": "660801"
}], [{
  "label": "桃园",
  "value": "660901"
}], [{
  "label": "苗栗",
  "value": "661001"
}], [{
  "label": "彰化",
  "value": "661101"
}], [{
  "label": "南投",
  "value": "661201"
}], [{
  "label": "云林",
  "value": "661301"
}], [{
  "label": "屏东",
  "value": "661401"
}], [{
  "label": "台东",
  "value": "661501"
}], [{
  "label": "花莲",
  "value": "661601"
}], [{
  "label": "澎湖",
  "value": "661701"
}]], [[{
  "label": "香港岛",
  "value": "670101"
}], [{
  "label": "九龙",
  "value": "670201"
}], [{
  "label": "新界",
  "value": "670301"
}]], [[{
  "label": "澳门半岛",
  "value": "680101"
}], [{
  "label": "氹仔岛",
  "value": "680201"
}], [{
  "label": "路环岛",
  "value": "680301"
}], [{
  "label": "路氹城",
  "value": "680401"
}]]];
/* harmony default export */ __webpack_exports__["default"] = (areaData);

/***/ }),

/***/ 8:
/*!***************************************!*\
  !*** ./node_modules/ieee754/index.js ***!
  \***************************************/
/*! no static exports found */
/***/ (function(module, exports) {

/*! ieee754. BSD-3-Clause License. Feross Aboukhadijeh <https://feross.org/opensource> */
exports.read = function (buffer, offset, isLE, mLen, nBytes) {
  var e, m;
  var eLen = nBytes * 8 - mLen - 1;
  var eMax = (1 << eLen) - 1;
  var eBias = eMax >> 1;
  var nBits = -7;
  var i = isLE ? nBytes - 1 : 0;
  var d = isLE ? -1 : 1;
  var s = buffer[offset + i];
  i += d;
  e = s & (1 << -nBits) - 1;
  s >>= -nBits;
  nBits += eLen;
  for (; nBits > 0; e = e * 256 + buffer[offset + i], i += d, nBits -= 8) {}
  m = e & (1 << -nBits) - 1;
  e >>= -nBits;
  nBits += mLen;
  for (; nBits > 0; m = m * 256 + buffer[offset + i], i += d, nBits -= 8) {}
  if (e === 0) {
    e = 1 - eBias;
  } else if (e === eMax) {
    return m ? NaN : (s ? -1 : 1) * Infinity;
  } else {
    m = m + Math.pow(2, mLen);
    e = e - eBias;
  }
  return (s ? -1 : 1) * m * Math.pow(2, e - mLen);
};
exports.write = function (buffer, value, offset, isLE, mLen, nBytes) {
  var e, m, c;
  var eLen = nBytes * 8 - mLen - 1;
  var eMax = (1 << eLen) - 1;
  var eBias = eMax >> 1;
  var rt = mLen === 23 ? Math.pow(2, -24) - Math.pow(2, -77) : 0;
  var i = isLE ? 0 : nBytes - 1;
  var d = isLE ? 1 : -1;
  var s = value < 0 || value === 0 && 1 / value < 0 ? 1 : 0;
  value = Math.abs(value);
  if (isNaN(value) || value === Infinity) {
    m = isNaN(value) ? 1 : 0;
    e = eMax;
  } else {
    e = Math.floor(Math.log(value) / Math.LN2);
    if (value * (c = Math.pow(2, -e)) < 1) {
      e--;
      c *= 2;
    }
    if (e + eBias >= 1) {
      value += rt / c;
    } else {
      value += rt * Math.pow(2, 1 - eBias);
    }
    if (value * c >= 2) {
      e++;
      c /= 2;
    }
    if (e + eBias >= eMax) {
      m = 0;
      e = eMax;
    } else if (e + eBias >= 1) {
      m = (value * c - 1) * Math.pow(2, mLen);
      e = e + eBias;
    } else {
      m = value * Math.pow(2, eBias - 1) * Math.pow(2, mLen);
      e = 0;
    }
  }
  for (; mLen >= 8; buffer[offset + i] = m & 0xff, i += d, m /= 256, mLen -= 8) {}
  e = e << mLen | m;
  eLen += mLen;
  for (; eLen > 0; buffer[offset + i] = e & 0xff, i += d, e /= 256, eLen -= 8) {}
  buffer[offset + i - d] |= s * 128;
};

/***/ }),

/***/ 88:
/*!***********************************************************!*\
  !*** ./uview-ui/components/u-avatar-cropper/weCropper.js ***!
  \***********************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

/* WEBPACK VAR INJECTION */(function(uni, global) {/**
 * we-cropper v1.3.9
 * (c) 2020 dlhandsome
 * @license MIT
 */
(function (global, factory) {
   true ? module.exports = factory() : undefined;
})(this, function () {
  'use strict';

  var device = void 0;
  var TOUCH_STATE = ['touchstarted', 'touchmoved', 'touchended'];
  function firstLetterUpper(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
  function setTouchState(instance) {
    var arg = [],
      len = arguments.length - 1;
    while (len-- > 0) arg[len] = arguments[len + 1];
    TOUCH_STATE.forEach(function (key, i) {
      if (arg[i] !== undefined) {
        instance[key] = arg[i];
      }
    });
  }
  function validator(instance, o) {
    Object.defineProperties(instance, o);
  }
  function getDevice() {
    if (!device) {
      device = uni.getSystemInfoSync();
    }
    return device;
  }
  var tmp = {};
  var ref = getDevice();
  var pixelRatio = ref.pixelRatio;
  var DEFAULT = {
    id: {
      default: 'cropper',
      get: function get() {
        return tmp.id;
      },
      set: function set(value) {
        if (typeof value !== 'string') {
          console.error("id：" + value + " is invalid");
        }
        tmp.id = value;
      }
    },
    width: {
      default: 750,
      get: function get() {
        return tmp.width;
      },
      set: function set(value) {
        if (typeof value !== 'number') {
          console.error("width：" + value + " is invalid");
        }
        tmp.width = value;
      }
    },
    height: {
      default: 750,
      get: function get() {
        return tmp.height;
      },
      set: function set(value) {
        if (typeof value !== 'number') {
          console.error("height：" + value + " is invalid");
        }
        tmp.height = value;
      }
    },
    pixelRatio: {
      default: pixelRatio,
      get: function get() {
        return tmp.pixelRatio;
      },
      set: function set(value) {
        if (typeof value !== 'number') {
          console.error("pixelRatio：" + value + " is invalid");
        }
        tmp.pixelRatio = value;
      }
    },
    scale: {
      default: 2.5,
      get: function get() {
        return tmp.scale;
      },
      set: function set(value) {
        if (typeof value !== 'number') {
          console.error("scale：" + value + " is invalid");
        }
        tmp.scale = value;
      }
    },
    zoom: {
      default: 5,
      get: function get() {
        return tmp.zoom;
      },
      set: function set(value) {
        if (typeof value !== 'number') {
          console.error("zoom：" + value + " is invalid");
        } else if (value < 0 || value > 10) {
          console.error("zoom should be ranged in 0 ~ 10");
        }
        tmp.zoom = value;
      }
    },
    src: {
      default: '',
      get: function get() {
        return tmp.src;
      },
      set: function set(value) {
        if (typeof value !== 'string') {
          console.error("src：" + value + " is invalid");
        }
        tmp.src = value;
      }
    },
    cut: {
      default: {},
      get: function get() {
        return tmp.cut;
      },
      set: function set(value) {
        if (typeof value !== 'object') {
          console.error("cut：" + value + " is invalid");
        }
        tmp.cut = value;
      }
    },
    boundStyle: {
      default: {},
      get: function get() {
        return tmp.boundStyle;
      },
      set: function set(value) {
        if (typeof value !== 'object') {
          console.error("boundStyle：" + value + " is invalid");
        }
        tmp.boundStyle = value;
      }
    },
    onReady: {
      default: null,
      get: function get() {
        return tmp.ready;
      },
      set: function set(value) {
        tmp.ready = value;
      }
    },
    onBeforeImageLoad: {
      default: null,
      get: function get() {
        return tmp.beforeImageLoad;
      },
      set: function set(value) {
        tmp.beforeImageLoad = value;
      }
    },
    onImageLoad: {
      default: null,
      get: function get() {
        return tmp.imageLoad;
      },
      set: function set(value) {
        tmp.imageLoad = value;
      }
    },
    onBeforeDraw: {
      default: null,
      get: function get() {
        return tmp.beforeDraw;
      },
      set: function set(value) {
        tmp.beforeDraw = value;
      }
    }
  };
  var ref$1 = getDevice();
  var windowWidth = ref$1.windowWidth;
  function prepare() {
    var self = this;

    // v1.4.0 版本中将不再自动绑定we-cropper实例
    self.attachPage = function () {
      var pages = getCurrentPages();
      // 获取到当前page上下文
      var pageContext = pages[pages.length - 1];
      // 把this依附在Page上下文的wecropper属性上，便于在page钩子函数中访问
      Object.defineProperty(pageContext, 'wecropper', {
        get: function get() {
          console.warn('Instance will not be automatically bound to the page after v1.4.0\n\n' + 'Please use a custom instance name instead\n\n' + 'Example: \n' + 'this.mycropper = new WeCropper(options)\n\n' + '// ...\n' + 'this.mycropper.getCropperImage()');
          return self;
        },
        configurable: true
      });
    };
    self.createCtx = function () {
      var id = self.id;
      var targetId = self.targetId;
      if (id) {
        self.ctx = self.ctx || uni.createCanvasContext(id);
        self.targetCtx = self.targetCtx || uni.createCanvasContext(targetId);
      } else {
        console.error("constructor: create canvas context failed, 'id' must be valuable");
      }
    };
    self.deviceRadio = windowWidth / 750;
  }
  var commonjsGlobal = typeof window !== 'undefined' ? window : typeof global !== 'undefined' ? global : typeof self !== 'undefined' ? self : {};
  function createCommonjsModule(fn, module) {
    return module = {
      exports: {}
    }, fn(module, module.exports), module.exports;
  }
  var tools = createCommonjsModule(function (module, exports) {
    /**
     * String type check
     */
    exports.isStr = function (v) {
      return typeof v === 'string';
    };
    /**
     * Number type check
     */
    exports.isNum = function (v) {
      return typeof v === 'number';
    };
    /**
     * Array type check
     */
    exports.isArr = Array.isArray;
    /**
     * undefined type check
     */
    exports.isUndef = function (v) {
      return v === undefined;
    };
    exports.isTrue = function (v) {
      return v === true;
    };
    exports.isFalse = function (v) {
      return v === false;
    };
    /**
     * Function type check
     */
    exports.isFunc = function (v) {
      return typeof v === 'function';
    };
    /**
     * Quick object check - this is primarily used to tell
     * Objects from primitive values when we know the value
     * is a JSON-compliant type.
     */
    exports.isObj = exports.isObject = function (obj) {
      return obj !== null && typeof obj === 'object';
    };

    /**
     * Strict object type check. Only returns true
     * for plain JavaScript objects.
     */
    var _toString = Object.prototype.toString;
    exports.isPlainObject = function (obj) {
      return _toString.call(obj) === '[object Object]';
    };

    /**
     * Check whether the object has the property.
     */
    var hasOwnProperty = Object.prototype.hasOwnProperty;
    exports.hasOwn = function (obj, key) {
      return hasOwnProperty.call(obj, key);
    };

    /**
     * Perform no operation.
     * Stubbing args to make Flow happy without leaving useless transpiled code
     * with ...rest (https://flow.org/blog/2017/05/07/Strict-Function-Call-Arity/)
     */
    exports.noop = function (a, b, c) {};

    /**
     * Check if val is a valid array index.
     */
    exports.isValidArrayIndex = function (val) {
      var n = parseFloat(String(val));
      return n >= 0 && Math.floor(n) === n && isFinite(val);
    };
  });
  var tools_7 = tools.isFunc;
  var tools_10 = tools.isPlainObject;
  var EVENT_TYPE = ['ready', 'beforeImageLoad', 'beforeDraw', 'imageLoad'];
  function observer() {
    var self = this;
    self.on = function (event, fn) {
      if (EVENT_TYPE.indexOf(event) > -1) {
        if (tools_7(fn)) {
          event === 'ready' ? fn(self) : self["on" + firstLetterUpper(event)] = fn;
        }
      } else {
        console.error("event: " + event + " is invalid");
      }
      return self;
    };
  }
  function wxPromise(fn) {
    return function (obj) {
      var args = [],
        len = arguments.length - 1;
      while (len-- > 0) args[len] = arguments[len + 1];
      if (obj === void 0) obj = {};
      return new Promise(function (resolve, reject) {
        obj.success = function (res) {
          resolve(res);
        };
        obj.fail = function (err) {
          reject(err);
        };
        fn.apply(void 0, [obj].concat(args));
      });
    };
  }
  function draw(ctx, reserve) {
    if (reserve === void 0) reserve = false;
    return new Promise(function (resolve) {
      ctx.draw(reserve, resolve);
    });
  }
  var getImageInfo = wxPromise(uni.getImageInfo);
  var canvasToTempFilePath = wxPromise(uni.canvasToTempFilePath);
  var base64 = createCommonjsModule(function (module, exports) {
    /*! http://mths.be/base64 v0.1.0 by @mathias | MIT license */
    (function (root) {
      // Detect free variables `exports`.
      var freeExports =  true && exports;

      // Detect free variable `module`.
      var freeModule =  true && module && module.exports == freeExports && module;

      // Detect free variable `global`, from Node.js or Browserified code, and use
      // it as `root`.
      var freeGlobal = typeof commonjsGlobal == 'object' && commonjsGlobal;
      if (freeGlobal.global === freeGlobal || freeGlobal.window === freeGlobal) {
        root = freeGlobal;
      }

      /*--------------------------------------------------------------------------*/

      var InvalidCharacterError = function (message) {
        this.message = message;
      };
      InvalidCharacterError.prototype = new Error();
      InvalidCharacterError.prototype.name = 'InvalidCharacterError';
      var error = function (message) {
        // Note: the error messages used throughout this file match those used by
        // the native `atob`/`btoa` implementation in Chromium.
        throw new InvalidCharacterError(message);
      };
      var TABLE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
      // http://whatwg.org/html/common-microsyntaxes.html#space-character
      var REGEX_SPACE_CHARACTERS = /[\t\n\f\r ]/g;

      // `decode` is designed to be fully compatible with `atob` as described in the
      // HTML Standard. http://whatwg.org/html/webappapis.html#dom-windowbase64-atob
      // The optimized base64-decoding algorithm used is based on @atk’s excellent
      // implementation. https://gist.github.com/atk/1020396
      var decode = function (input) {
        input = String(input).replace(REGEX_SPACE_CHARACTERS, '');
        var length = input.length;
        if (length % 4 == 0) {
          input = input.replace(/==?$/, '');
          length = input.length;
        }
        if (length % 4 == 1 ||
        // http://whatwg.org/C#alphanumeric-ascii-characters
        /[^+a-zA-Z0-9/]/.test(input)) {
          error('Invalid character: the string to be decoded is not correctly encoded.');
        }
        var bitCounter = 0;
        var bitStorage;
        var buffer;
        var output = '';
        var position = -1;
        while (++position < length) {
          buffer = TABLE.indexOf(input.charAt(position));
          bitStorage = bitCounter % 4 ? bitStorage * 64 + buffer : buffer;
          // Unless this is the first of a group of 4 characters…
          if (bitCounter++ % 4) {
            // …convert the first 8 bits to a single ASCII character.
            output += String.fromCharCode(0xFF & bitStorage >> (-2 * bitCounter & 6));
          }
        }
        return output;
      };

      // `encode` is designed to be fully compatible with `btoa` as described in the
      // HTML Standard: http://whatwg.org/html/webappapis.html#dom-windowbase64-btoa
      var encode = function (input) {
        input = String(input);
        if (/[^\0-\xFF]/.test(input)) {
          // Note: no need to special-case astral symbols here, as surrogates are
          // matched, and the input is supposed to only contain ASCII anyway.
          error('The string to be encoded contains characters outside of the ' + 'Latin1 range.');
        }
        var padding = input.length % 3;
        var output = '';
        var position = -1;
        var a;
        var b;
        var c;
        var buffer;
        // Make sure any padding is handled outside of the loop.
        var length = input.length - padding;
        while (++position < length) {
          // Read three bytes, i.e. 24 bits.
          a = input.charCodeAt(position) << 16;
          b = input.charCodeAt(++position) << 8;
          c = input.charCodeAt(++position);
          buffer = a + b + c;
          // Turn the 24 bits into four chunks of 6 bits each, and append the
          // matching character for each of them to the output.
          output += TABLE.charAt(buffer >> 18 & 0x3F) + TABLE.charAt(buffer >> 12 & 0x3F) + TABLE.charAt(buffer >> 6 & 0x3F) + TABLE.charAt(buffer & 0x3F);
        }
        if (padding == 2) {
          a = input.charCodeAt(position) << 8;
          b = input.charCodeAt(++position);
          buffer = a + b;
          output += TABLE.charAt(buffer >> 10) + TABLE.charAt(buffer >> 4 & 0x3F) + TABLE.charAt(buffer << 2 & 0x3F) + '=';
        } else if (padding == 1) {
          buffer = input.charCodeAt(position);
          output += TABLE.charAt(buffer >> 2) + TABLE.charAt(buffer << 4 & 0x3F) + '==';
        }
        return output;
      };
      var base64 = {
        'encode': encode,
        'decode': decode,
        'version': '0.1.0'
      };

      // Some AMD build optimizers, like r.js, check for specific condition patterns
      // like the following:
      if (false) {} else if (freeExports && !freeExports.nodeType) {
        if (freeModule) {
          // in Node.js or RingoJS v0.8.0+
          freeModule.exports = base64;
        } else {
          // in Narwhal or RingoJS v0.7.0-
          for (var key in base64) {
            base64.hasOwnProperty(key) && (freeExports[key] = base64[key]);
          }
        }
      } else {
        // in Rhino or a web browser
        root.base64 = base64;
      }
    })(commonjsGlobal);
  });
  function makeURI(strData, type) {
    return 'data:' + type + ';base64,' + strData;
  }
  function fixType(type) {
    type = type.toLowerCase().replace(/jpg/i, 'jpeg');
    var r = type.match(/png|jpeg|bmp|gif/)[0];
    return 'image/' + r;
  }
  function encodeData(data) {
    var str = '';
    if (typeof data === 'string') {
      str = data;
    } else {
      for (var i = 0; i < data.length; i++) {
        str += String.fromCharCode(data[i]);
      }
    }
    return base64.encode(str);
  }

  /**
   * 获取图像区域隐含的像素数据
   * @param canvasId canvas标识
   * @param x 将要被提取的图像数据矩形区域的左上角 x 坐标
   * @param y 将要被提取的图像数据矩形区域的左上角 y 坐标
   * @param width 将要被提取的图像数据矩形区域的宽度
   * @param height 将要被提取的图像数据矩形区域的高度
   * @param done 完成回调
   */
  function getImageData(canvasId, x, y, width, height, done) {
    uni.canvasGetImageData({
      canvasId: canvasId,
      x: x,
      y: y,
      width: width,
      height: height,
      success: function success(res) {
        done(res, null);
      },
      fail: function fail(res) {
        done(null, res);
      }
    });
  }

  /**
   * 生成bmp格式图片
   * 按照规则生成图片响应头和响应体
   * @param oData 用来描述 canvas 区域隐含的像素数据 { data, width, height } = oData
   * @returns {*} base64字符串
   */
  function genBitmapImage(oData) {
    //
    // BITMAPFILEHEADER: http://msdn.microsoft.com/en-us/library/windows/desktop/dd183374(v=vs.85).aspx
    // BITMAPINFOHEADER: http://msdn.microsoft.com/en-us/library/dd183376.aspx
    //
    var biWidth = oData.width;
    var biHeight = oData.height;
    var biSizeImage = biWidth * biHeight * 3;
    var bfSize = biSizeImage + 54; // total header size = 54 bytes

    //
    //  typedef struct tagBITMAPFILEHEADER {
    //  	WORD bfType;
    //  	DWORD bfSize;
    //  	WORD bfReserved1;
    //  	WORD bfReserved2;
    //  	DWORD bfOffBits;
    //  } BITMAPFILEHEADER;
    //
    var BITMAPFILEHEADER = [
    // WORD bfType -- The file type signature; must be "BM"
    0x42, 0x4D,
    // DWORD bfSize -- The size, in bytes, of the bitmap file
    bfSize & 0xff, bfSize >> 8 & 0xff, bfSize >> 16 & 0xff, bfSize >> 24 & 0xff,
    // WORD bfReserved1 -- Reserved; must be zero
    0, 0,
    // WORD bfReserved2 -- Reserved; must be zero
    0, 0,
    // DWORD bfOffBits -- The offset, in bytes, from the beginning of the BITMAPFILEHEADER structure to the bitmap bits.
    54, 0, 0, 0];

    //
    //  typedef struct tagBITMAPINFOHEADER {
    //  	DWORD biSize;
    //  	LONG  biWidth;
    //  	LONG  biHeight;
    //  	WORD  biPlanes;
    //  	WORD  biBitCount;
    //  	DWORD biCompression;
    //  	DWORD biSizeImage;
    //  	LONG  biXPelsPerMeter;
    //  	LONG  biYPelsPerMeter;
    //  	DWORD biClrUsed;
    //  	DWORD biClrImportant;
    //  } BITMAPINFOHEADER, *PBITMAPINFOHEADER;
    //
    var BITMAPINFOHEADER = [
    // DWORD biSize -- The number of bytes required by the structure
    40, 0, 0, 0,
    // LONG biWidth -- The width of the bitmap, in pixels
    biWidth & 0xff, biWidth >> 8 & 0xff, biWidth >> 16 & 0xff, biWidth >> 24 & 0xff,
    // LONG biHeight -- The height of the bitmap, in pixels
    biHeight & 0xff, biHeight >> 8 & 0xff, biHeight >> 16 & 0xff, biHeight >> 24 & 0xff,
    // WORD biPlanes -- The number of planes for the target device. This value must be set to 1
    1, 0,
    // WORD biBitCount -- The number of bits-per-pixel, 24 bits-per-pixel -- the bitmap
    // has a maximum of 2^24 colors (16777216, Truecolor)
    24, 0,
    // DWORD biCompression -- The type of compression, BI_RGB (code 0) -- uncompressed
    0, 0, 0, 0,
    // DWORD biSizeImage -- The size, in bytes, of the image. This may be set to zero for BI_RGB bitmaps
    biSizeImage & 0xff, biSizeImage >> 8 & 0xff, biSizeImage >> 16 & 0xff, biSizeImage >> 24 & 0xff,
    // LONG biXPelsPerMeter, unused
    0, 0, 0, 0,
    // LONG biYPelsPerMeter, unused
    0, 0, 0, 0,
    // DWORD biClrUsed, the number of color indexes of palette, unused
    0, 0, 0, 0,
    // DWORD biClrImportant, unused
    0, 0, 0, 0];
    var iPadding = (4 - biWidth * 3 % 4) % 4;
    var aImgData = oData.data;
    var strPixelData = '';
    var biWidth4 = biWidth << 2;
    var y = biHeight;
    var fromCharCode = String.fromCharCode;
    do {
      var iOffsetY = biWidth4 * (y - 1);
      var strPixelRow = '';
      for (var x = 0; x < biWidth; x++) {
        var iOffsetX = x << 2;
        strPixelRow += fromCharCode(aImgData[iOffsetY + iOffsetX + 2]) + fromCharCode(aImgData[iOffsetY + iOffsetX + 1]) + fromCharCode(aImgData[iOffsetY + iOffsetX]);
      }
      for (var c = 0; c < iPadding; c++) {
        strPixelRow += String.fromCharCode(0);
      }
      strPixelData += strPixelRow;
    } while (--y);
    var strEncoded = encodeData(BITMAPFILEHEADER.concat(BITMAPINFOHEADER)) + encodeData(strPixelData);
    return strEncoded;
  }

  /**
   * 转换为图片base64
   * @param canvasId canvas标识
   * @param x 将要被提取的图像数据矩形区域的左上角 x 坐标
   * @param y 将要被提取的图像数据矩形区域的左上角 y 坐标
   * @param width 将要被提取的图像数据矩形区域的宽度
   * @param height 将要被提取的图像数据矩形区域的高度
   * @param type 转换图片类型
   * @param done 完成回调
   */
  function convertToImage(canvasId, x, y, width, height, type, done) {
    if (done === void 0) done = function () {};
    if (type === undefined) {
      type = 'png';
    }
    type = fixType(type);
    if (/bmp/.test(type)) {
      getImageData(canvasId, x, y, width, height, function (data, err) {
        var strData = genBitmapImage(data);
        tools_7(done) && done(makeURI(strData, 'image/' + type), err);
      });
    } else {
      console.error('暂不支持生成\'' + type + '\'类型的base64图片');
    }
  }
  var CanvasToBase64 = {
    convertToImage: convertToImage,
    // convertToPNG: function (width, height, done) {
    //   return convertToImage(width, height, 'png', done)
    // },
    // convertToJPEG: function (width, height, done) {
    //   return convertToImage(width, height, 'jpeg', done)
    // },
    // convertToGIF: function (width, height, done) {
    //   return convertToImage(width, height, 'gif', done)
    // },
    convertToBMP: function (ref, done) {
      if (ref === void 0) ref = {};
      var canvasId = ref.canvasId;
      var x = ref.x;
      var y = ref.y;
      var width = ref.width;
      var height = ref.height;
      if (done === void 0) done = function () {};
      return convertToImage(canvasId, x, y, width, height, 'bmp', done);
    }
  };
  function methods() {
    var self = this;
    var boundWidth = self.width; // 裁剪框默认宽度，即整个画布宽度
    var boundHeight = self.height; // 裁剪框默认高度，即整个画布高度

    var id = self.id;
    var targetId = self.targetId;
    var pixelRatio = self.pixelRatio;
    var ref = self.cut;
    var x = ref.x;
    if (x === void 0) x = 0;
    var y = ref.y;
    if (y === void 0) y = 0;
    var width = ref.width;
    if (width === void 0) width = boundWidth;
    var height = ref.height;
    if (height === void 0) height = boundHeight;
    self.updateCanvas = function (done) {
      if (self.croperTarget) {
        //  画布绘制图片
        self.ctx.drawImage(self.croperTarget, self.imgLeft, self.imgTop, self.scaleWidth, self.scaleHeight);
      }
      tools_7(self.onBeforeDraw) && self.onBeforeDraw(self.ctx, self);
      self.setBoundStyle(self.boundStyle); //	设置边界样式

      self.ctx.draw(false, done);
      return self;
    };
    self.pushOrigin = self.pushOrign = function (src) {
      self.src = src;
      tools_7(self.onBeforeImageLoad) && self.onBeforeImageLoad(self.ctx, self);
      return getImageInfo({
        src: src
      }).then(function (res) {
        var innerAspectRadio = res.width / res.height;
        var customAspectRadio = width / height;
        self.croperTarget = res.path;
        if (innerAspectRadio < customAspectRadio) {
          self.rectX = x;
          self.baseWidth = width;
          self.baseHeight = width / innerAspectRadio;
          self.rectY = y - Math.abs((height - self.baseHeight) / 2);
        } else {
          self.rectY = y;
          self.baseWidth = height * innerAspectRadio;
          self.baseHeight = height;
          self.rectX = x - Math.abs((width - self.baseWidth) / 2);
        }
        self.imgLeft = self.rectX;
        self.imgTop = self.rectY;
        self.scaleWidth = self.baseWidth;
        self.scaleHeight = self.baseHeight;
        self.update();
        return new Promise(function (resolve) {
          self.updateCanvas(resolve);
        });
      }).then(function () {
        tools_7(self.onImageLoad) && self.onImageLoad(self.ctx, self);
      });
    };
    self.removeImage = function () {
      self.src = '';
      self.croperTarget = '';
      return draw(self.ctx);
    };
    self.getCropperBase64 = function (done) {
      if (done === void 0) done = function () {};
      CanvasToBase64.convertToBMP({
        canvasId: id,
        x: x,
        y: y,
        width: width,
        height: height
      }, done);
    };
    self.getCropperImage = function (opt, fn) {
      var customOptions = opt;
      var canvasOptions = {
        canvasId: id,
        x: x,
        y: y,
        width: width,
        height: height
      };
      var task = function () {
        return Promise.resolve();
      };
      if (tools_10(customOptions) && customOptions.original) {
        // original mode
        task = function () {
          self.targetCtx.drawImage(self.croperTarget, self.imgLeft * pixelRatio, self.imgTop * pixelRatio, self.scaleWidth * pixelRatio, self.scaleHeight * pixelRatio);
          canvasOptions = {
            canvasId: targetId,
            x: x * pixelRatio,
            y: y * pixelRatio,
            width: width * pixelRatio,
            height: height * pixelRatio
          };
          return draw(self.targetCtx);
        };
      }
      return task().then(function () {
        if (tools_10(customOptions)) {
          canvasOptions = Object.assign({}, canvasOptions, customOptions);
        }
        if (tools_7(customOptions)) {
          fn = customOptions;
        }
        var arg = canvasOptions.componentContext ? [canvasOptions, canvasOptions.componentContext] : [canvasOptions];
        return canvasToTempFilePath.apply(null, arg);
      }).then(function (res) {
        var tempFilePath = res.tempFilePath;
        return tools_7(fn) ? fn.call(self, tempFilePath, null) : tempFilePath;
      }).catch(function (err) {
        if (tools_7(fn)) {
          fn.call(self, null, err);
        } else {
          throw err;
        }
      });
    };
  }

  /**
   * 获取最新缩放值
   * @param oldScale 上一次触摸结束后的缩放值
   * @param oldDistance 上一次触摸结束后的双指距离
   * @param zoom 缩放系数
   * @param touch0 第一指touch对象
   * @param touch1 第二指touch对象
   * @returns {*}
   */
  var getNewScale = function (oldScale, oldDistance, zoom, touch0, touch1) {
    var xMove, yMove, newDistance;
    // 计算二指最新距离
    xMove = Math.round(touch1.x - touch0.x);
    yMove = Math.round(touch1.y - touch0.y);
    newDistance = Math.round(Math.sqrt(xMove * xMove + yMove * yMove));
    return oldScale + 0.001 * zoom * (newDistance - oldDistance);
  };
  function update() {
    var self = this;
    if (!self.src) {
      return;
    }
    self.__oneTouchStart = function (touch) {
      self.touchX0 = Math.round(touch.x);
      self.touchY0 = Math.round(touch.y);
    };
    self.__oneTouchMove = function (touch) {
      var xMove, yMove;
      // 计算单指移动的距离
      if (self.touchended) {
        return self.updateCanvas();
      }
      xMove = Math.round(touch.x - self.touchX0);
      yMove = Math.round(touch.y - self.touchY0);
      var imgLeft = Math.round(self.rectX + xMove);
      var imgTop = Math.round(self.rectY + yMove);
      self.outsideBound(imgLeft, imgTop);
      self.updateCanvas();
    };
    self.__twoTouchStart = function (touch0, touch1) {
      var xMove, yMove, oldDistance;
      self.touchX1 = Math.round(self.rectX + self.scaleWidth / 2);
      self.touchY1 = Math.round(self.rectY + self.scaleHeight / 2);

      // 计算两指距离
      xMove = Math.round(touch1.x - touch0.x);
      yMove = Math.round(touch1.y - touch0.y);
      oldDistance = Math.round(Math.sqrt(xMove * xMove + yMove * yMove));
      self.oldDistance = oldDistance;
    };
    self.__twoTouchMove = function (touch0, touch1) {
      var oldScale = self.oldScale;
      var oldDistance = self.oldDistance;
      var scale = self.scale;
      var zoom = self.zoom;
      self.newScale = getNewScale(oldScale, oldDistance, zoom, touch0, touch1);

      //  设定缩放范围
      self.newScale <= 1 && (self.newScale = 1);
      self.newScale >= scale && (self.newScale = scale);
      self.scaleWidth = Math.round(self.newScale * self.baseWidth);
      self.scaleHeight = Math.round(self.newScale * self.baseHeight);
      var imgLeft = Math.round(self.touchX1 - self.scaleWidth / 2);
      var imgTop = Math.round(self.touchY1 - self.scaleHeight / 2);
      self.outsideBound(imgLeft, imgTop);
      self.updateCanvas();
    };
    self.__xtouchEnd = function () {
      self.oldScale = self.newScale;
      self.rectX = self.imgLeft;
      self.rectY = self.imgTop;
    };
  }
  var handle = {
    //  图片手势初始监测
    touchStart: function touchStart(e) {
      var self = this;
      var ref = e.touches;
      var touch0 = ref[0];
      var touch1 = ref[1];
      if (!self.src) {
        return;
      }
      setTouchState(self, true, null, null);

      // 计算第一个触摸点的位置，并参照改点进行缩放
      self.__oneTouchStart(touch0);

      // 两指手势触发
      if (e.touches.length >= 2) {
        self.__twoTouchStart(touch0, touch1);
      }
    },
    //  图片手势动态缩放
    touchMove: function touchMove(e) {
      var self = this;
      var ref = e.touches;
      var touch0 = ref[0];
      var touch1 = ref[1];
      if (!self.src) {
        return;
      }
      setTouchState(self, null, true);

      // 单指手势时触发
      if (e.touches.length === 1) {
        self.__oneTouchMove(touch0);
      }
      // 两指手势触发
      if (e.touches.length >= 2) {
        self.__twoTouchMove(touch0, touch1);
      }
    },
    touchEnd: function touchEnd(e) {
      var self = this;
      if (!self.src) {
        return;
      }
      setTouchState(self, false, false, true);
      self.__xtouchEnd();
    }
  };
  function cut() {
    var self = this;
    var boundWidth = self.width; // 裁剪框默认宽度，即整个画布宽度
    var boundHeight = self.height;
    // 裁剪框默认高度，即整个画布高度
    var ref = self.cut;
    var x = ref.x;
    if (x === void 0) x = 0;
    var y = ref.y;
    if (y === void 0) y = 0;
    var width = ref.width;
    if (width === void 0) width = boundWidth;
    var height = ref.height;
    if (height === void 0) height = boundHeight;

    /**
     * 设置边界
     * @param imgLeft 图片左上角横坐标值
     * @param imgTop 图片左上角纵坐标值
     */
    self.outsideBound = function (imgLeft, imgTop) {
      self.imgLeft = imgLeft >= x ? x : self.scaleWidth + imgLeft - x <= width ? x + width - self.scaleWidth : imgLeft;
      self.imgTop = imgTop >= y ? y : self.scaleHeight + imgTop - y <= height ? y + height - self.scaleHeight : imgTop;
    };

    /**
     * 设置边界样式
     * @param color	边界颜色
     */
    self.setBoundStyle = function (ref) {
      if (ref === void 0) ref = {};
      var color = ref.color;
      if (color === void 0) color = '#04b00f';
      var mask = ref.mask;
      if (mask === void 0) mask = 'rgba(0, 0, 0, 0.3)';
      var lineWidth = ref.lineWidth;
      if (lineWidth === void 0) lineWidth = 1;
      var half = lineWidth / 2;
      var boundOption = [{
        start: {
          x: x - half,
          y: y + 10 - half
        },
        step1: {
          x: x - half,
          y: y - half
        },
        step2: {
          x: x + 10 - half,
          y: y - half
        }
      }, {
        start: {
          x: x - half,
          y: y + height - 10 + half
        },
        step1: {
          x: x - half,
          y: y + height + half
        },
        step2: {
          x: x + 10 - half,
          y: y + height + half
        }
      }, {
        start: {
          x: x + width - 10 + half,
          y: y - half
        },
        step1: {
          x: x + width + half,
          y: y - half
        },
        step2: {
          x: x + width + half,
          y: y + 10 - half
        }
      }, {
        start: {
          x: x + width + half,
          y: y + height - 10 + half
        },
        step1: {
          x: x + width + half,
          y: y + height + half
        },
        step2: {
          x: x + width - 10 + half,
          y: y + height + half
        }
      }];

      // 绘制半透明层
      self.ctx.beginPath();
      self.ctx.setFillStyle(mask);
      self.ctx.fillRect(0, 0, x, boundHeight);
      self.ctx.fillRect(x, 0, width, y);
      self.ctx.fillRect(x, y + height, width, boundHeight - y - height);
      self.ctx.fillRect(x + width, 0, boundWidth - x - width, boundHeight);
      self.ctx.fill();
      boundOption.forEach(function (op) {
        self.ctx.beginPath();
        self.ctx.setStrokeStyle(color);
        self.ctx.setLineWidth(lineWidth);
        self.ctx.moveTo(op.start.x, op.start.y);
        self.ctx.lineTo(op.step1.x, op.step1.y);
        self.ctx.lineTo(op.step2.x, op.step2.y);
        self.ctx.stroke();
      });
    };
  }
  var version = "1.3.9";
  var WeCropper = function WeCropper(params) {
    var self = this;
    var _default = {};
    validator(self, DEFAULT);
    Object.keys(DEFAULT).forEach(function (key) {
      _default[key] = DEFAULT[key].default;
    });
    Object.assign(self, _default, params);
    self.prepare();
    self.attachPage();
    self.createCtx();
    self.observer();
    self.cutt();
    self.methods();
    self.init();
    self.update();
    return self;
  };
  WeCropper.prototype.init = function init() {
    var self = this;
    var src = self.src;
    self.version = version;
    typeof self.onReady === 'function' && self.onReady(self.ctx, self);
    if (src) {
      self.pushOrign(src);
    } else {
      self.updateCanvas();
    }
    setTouchState(self, false, false, false);
    self.oldScale = 1;
    self.newScale = 1;
    return self;
  };
  Object.assign(WeCropper.prototype, handle);
  WeCropper.prototype.prepare = prepare;
  WeCropper.prototype.observer = observer;
  WeCropper.prototype.methods = methods;
  WeCropper.prototype.cutt = cut;
  WeCropper.prototype.update = update;
  return WeCropper;
});
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"], __webpack_require__(/*! ./../../../node_modules/webpack/buildin/global.js */ 3)))

/***/ }),

/***/ 9:
/*!***********************************************************!*\
  !*** ./node_modules/buffer/node_modules/isarray/index.js ***!
  \***********************************************************/
/*! no static exports found */
/***/ (function(module, exports) {

var toString = {}.toString;
module.exports = Array.isArray || function (arr) {
  return toString.call(arr) == '[object Array]';
};

/***/ })

}]);
//# sourceMappingURL=../../.sourcemap/mp-weixin/common/vendor.js.map