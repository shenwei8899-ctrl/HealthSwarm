import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { ref } from 'vue'

const source = readFileSync(new URL('../src/pages/index/index.vue', import.meta.url), 'utf8')
const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
const copy = value => structuredClone(value)

function deferred() {
  let resolve, reject
  const promise = new Promise((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

function welcome({ onboarded = false, progress, login, navigate } = {}) {
  const existingProfile = { householdName: '已有家庭', members: [{ id: 17, name: '已有成员' }], marker: 'keep' }
  const storage = new Map()
  if (onboarded) storage.set('frontend-onboarded-v1', true)
  if (progress) storage.set('frontend-onboarding-progress-v1', copy(progress))
  const calls = { login: [], navigation: [], profiles: [], cancelled: 0 }
  const hooks = {}
  let profile = copy(existingProfile)
  const deps = {
    ref,
    onShow: callback => { hooks.show = callback },
    onHide: callback => { hooks.hide = callback },
    onUnload: callback => { hooks.unload = callback },
    isMockMode: true,
    canUseBusinessLogin: false,
    isCommerceEnabled: false,
    getSession: () => null,
    wechatAuth: { cancelPending() { calls.cancelled++ } },
    service: { async login(account) { calls.login.push(account); return login?.(account, calls.login.length) } },
    scopedStorage: {
      getStorageSync: key => storage.has(key) ? copy(storage.get(key)) : undefined,
      setStorageSync: (key, value) => storage.set(key, copy(value)),
    },
    getProfile: () => copy(profile),
    saveProfile: value => { profile = copy(value); calls.profiles.push(copy(value)) },
    newMember: index => ({ id: 'member-' + index, name: '默认姓名', relation: '其他', age: 30 }),
    normalizeMember: copy,
    uni: {
      reLaunch(options) {
        calls.navigation.push(options.url)
        if (navigate) navigate(options, calls.navigation.length)
        else options.success({ errMsg: 'reLaunch:ok' })
      },
    },
  }
  const page = new Function('deps', `const {${Object.keys(deps)}}=deps;${script};return {start,continueLogin,closeLoginSheet,loginOpen,loggingIn,loginError,testAccount}`)(deps)
  return { page, calls, hooks, storage, existingProfile, profile: () => copy(profile) }
}

test('new mock account creates the self profile and opens onboarding', async () => {
  const h = welcome()
  h.page.testAccount.value = 'fresh-user'
  h.page.start()
  assert.equal(h.page.loginOpen.value, true)
  await h.page.continueLogin()
  assert.deepEqual(h.calls.login, ['fresh-user'])
  assert.deepEqual(h.storage.get('frontend-sample-profile-v1'), h.existingProfile)
  assert.deepEqual(h.calls.profiles, [{
    householdName: '我的家', usageMode: '个人使用',
    members: [{ id: 'member-0', name: '我', relation: '本人', age: '', claimedBy: 'creator' }],
    defaultDiners: ['member-0'], goals: [], tastes: [], memories: [],
  }])
  assert.deepEqual(h.calls.navigation, ['/pages/onboarding/index'])
  assert.equal(h.page.loginOpen.value, false)
  assert.equal(h.page.loggingIn.value, false)
})

test('returning mock account opens chat without replacing its profile', async () => {
  const h = welcome({ onboarded: true })
  h.page.start()
  await h.page.continueLogin()
  assert.deepEqual(h.calls.navigation, ['/pages/chat/index'])
  assert.deepEqual(h.calls.profiles, [])
  assert.deepEqual(h.profile(), h.existingProfile)
  assert.equal(h.storage.has('frontend-sample-profile-v1'), false)
})

test('unfinished onboarding keeps the saved profile and progress', async () => {
  const progress = { step: 2, memberName: '待完善成员' }
  const h = welcome({ progress })
  h.page.start()
  await h.page.continueLogin()
  assert.deepEqual(h.calls.navigation, ['/pages/onboarding/index'])
  assert.deepEqual(h.calls.profiles, [])
  assert.deepEqual(h.storage.get('frontend-onboarding-progress-v1'), progress)
  assert.deepEqual(h.profile(), h.existingProfile)
})

test('repeated presses while login is pending submit only once', async () => {
  const pending = deferred()
  const h = welcome({ login: () => pending.promise })
  h.page.start()
  const first = h.page.continueLogin()
  assert.equal(h.page.loggingIn.value, true)
  await h.page.continueLogin()
  await h.page.continueLogin()
  assert.deepEqual(h.calls.login, ['creator'])
  assert.deepEqual(h.calls.navigation, [])
  pending.resolve()
  await first
  assert.deepEqual(h.calls.navigation, ['/pages/onboarding/index'])
  assert.equal(h.page.loggingIn.value, false)
})

test('login failure leaves the sheet open with an error and permits retry', async () => {
  const h = welcome({ login: (_account, attempt) => {
    if (attempt === 1) throw new Error('模拟登录暂时失败')
  } })
  h.page.start()
  await h.page.continueLogin()
  assert.equal(h.page.loginOpen.value, true)
  assert.match(h.page.loginError.value, /模拟登录暂时失败/)
  assert.equal(h.page.loggingIn.value, false)
  assert.deepEqual(h.calls.navigation, [])
  await h.page.continueLogin()
  assert.equal(h.calls.login.length, 2)
  assert.deepEqual(h.calls.navigation, ['/pages/onboarding/index'])
  assert.equal(h.page.loginError.value, '')
  assert.equal(h.page.loginOpen.value, false)
})

test('native navigation failure is visible and permits retry', async () => {
  const h = welcome({ navigate: (options, attempt) => {
    if (attempt === 1) options.fail({ errMsg: 'reLaunch:fail synthetic navigation failure' })
    else options.success({ errMsg: 'reLaunch:ok' })
  } })
  h.page.start()
  await h.page.continueLogin()
  assert.equal(h.page.loginOpen.value, true)
  assert.ok(h.page.loginError.value, '页面打开失败必须显示错误')
  assert.equal(h.page.loggingIn.value, false)
  await h.page.continueLogin()
  assert.equal(h.calls.login.length, 2)
  assert.deepEqual(h.calls.navigation, ['/pages/onboarding/index', '/pages/onboarding/index'])
  assert.equal(h.page.loginError.value, '')
  assert.equal(h.page.loginOpen.value, false)
})

test('login stays busy until the native navigation callback completes', async () => {
  let navigation
  const h = welcome({ navigate: options => { navigation = options } })
  h.page.start()
  const pending = h.page.continueLogin()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(h.calls.navigation, ['/pages/onboarding/index'])
  assert.equal(h.page.loggingIn.value, true)
  assert.equal(h.page.loginOpen.value, true)
  navigation.success({ errMsg: 'reLaunch:ok' })
  await pending
  assert.equal(h.page.loggingIn.value, false)
  assert.equal(h.page.loginOpen.value, false)
})

for (const action of ['close', 'hide', 'unload']) {
  test(`${action} cancels a pending login without late navigation`, async () => {
    const pending = deferred()
    const h = welcome({ login: () => pending.promise })
    h.page.start()
    const login = h.page.continueLogin()
    if (action === 'close') h.page.closeLoginSheet()
    else h.hooks[action]()
    assert.equal(h.page.loginOpen.value, false)
    assert.equal(h.page.loggingIn.value, false)
    assert.equal(h.calls.cancelled, 1)
    pending.resolve()
    await login
    assert.deepEqual(h.calls.navigation, [])
    assert.deepEqual(h.calls.profiles, [])
    assert.equal(h.page.loginError.value, '')
  })
}

test('WeChat compilation prevents mock sheet taps from bubbling to the closing mask', () => {
  const require = createRequire(import.meta.url)
  const weixinRequire = createRequire(require.resolve('@dcloudio/uni-mp-weixin/package.json'))
  const { compile } = weixinRequire('@dcloudio/uni-mp-compiler')
  function wxml(template) {
    const assets = []
    // Match the event, slot and directive options used by the installed WeChat compiler.
    compile(template, {
      filename: 'pages/index/index.wxml',
      miniProgram: {
        directive: 'wx:', event: { key: true }, class: { array: true },
        slot: { fallbackContent: false, dynamicSlotNames: true },
        emitFile: asset => assets.push(asset),
      },
    })
    assert.equal(assets.length, 1)
    return String(assets[0].source)
  }

  const compiled = wxml(source.match(/<template>([\s\S]*?)<\/template>/)[1])
  const heading = compiled.indexOf('模拟微信登录')
  assert.ok(heading >= 0, '实际欢迎页必须包含模拟登录弹窗')
  const sheetStart = compiled.lastIndexOf('<view class="sheet"', heading)
  assert.ok(sheetStart >= 0)
  const sheetTag = compiled.slice(sheetStart, compiled.indexOf('>', sheetStart) + 1)
  assert.match(sheetTag, /\bcatchtap="\{\{[^}]+\}\}"/, '模拟弹窗内容必须生成微信原生 catchtap')

  const legacy = wxml('<view class="sheet-mask" @click.self="closeLoginSheet"><view class="sheet"><button @click="continueLogin">模拟登录并继续</button></view></view>')
  assert.match(legacy, /class="sheet-mask" bindtap=/)
  assert.doesNotMatch(legacy, /\bcatchtap=/, '旧 self 修饰符无法阻止微信 tap 冒泡')
})
