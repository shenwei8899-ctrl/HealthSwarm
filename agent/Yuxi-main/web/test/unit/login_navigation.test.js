import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { setImmediate } from 'node:timers'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { createRenderer, h, nextTick } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createServer } from 'vite'

const makeNode = (type) => ({ type, children: [], props: {}, parent: null, text: '' })
const renderer = createRenderer({
  createElement: makeNode,
  createText: (text) => ({ ...makeNode('text'), text }),
  createComment: makeNode,
  insert(child, parent, anchor = null) {
    child.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(child)
    else parent.children.splice(index, 0, child)
  },
  remove(child) {
    const siblings = child.parent?.children
    const index = siblings?.indexOf(child) ?? -1
    if (index >= 0) siblings.splice(index, 1)
  },
  setText(node, text) {
    node.text = text
  },
  setElementText(node, text) {
    node.text = text
    node.children = []
  },
  patchProp(node, key, _previous, value) {
    node.props[key] = value
  },
  parentNode: (node) => node.parent,
  nextSibling: (node) => node.parent?.children[node.parent.children.indexOf(node) + 1] || null
})

const find = (node, predicate) =>
  predicate(node) ? node : node.children.map((child) => find(child, predicate)).find(Boolean)
const textContent = (node) => [node.text, ...node.children.map(textContent)].join('')
const memoryStorage = () => {
  const entries = new Map()
  return {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, String(value)),
    removeItem: (key) => entries.delete(key)
  }
}

async function waitFor(predicate, label) {
  const deadline = Date.now() + 300
  while (!predicate() && Date.now() < deadline) {
    await new Promise((resolve) => setImmediate(resolve))
  }
  assert.ok(predicate(), label)
}

async function mountLogin(t, { path = '/login', view = 'LoginView', storedRedirect } = {}) {
  globalThis.localStorage = memoryStorage()
  globalThis.sessionStorage = memoryStorage()
  globalThis.window = { location: { search: '' } }
  if (storedRedirect) sessionStorage.setItem('redirect', storedRedirect)
  const messages = []
  globalThis.__loginNavigationMessages = messages
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true, include: [] },
    ssr: { noExternal: ['ant-design-vue'] },
    plugins: [
      {
        name: 'login-client-template-test',
        enforce: 'pre',
        resolveId(id) {
          if (id === 'virtual:login-view-test' || id === 'ant-design-vue') return '\0' + id
        },
        load(id) {
          if (id === '\0ant-design-vue') {
            return `export const message = Object.fromEntries(['success', 'warning', 'error'].map(
              (kind) => [kind, (text) => globalThis.__loginNavigationMessages.push({ kind, text })]))`
          }
          if (id !== '\0virtual:login-view-test') return
          const source = readFileSync(
            new URL(`../../src/views/${view}.vue`, import.meta.url),
            'utf8'
          )
          const { descriptor } = parse(source)
          return compileScript(descriptor, { id: 'login-navigation', inlineTemplate: true }).content
        }
      }
    ]
  })
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/login', '/auth/oidc/callback', '/agent', '/family'].map((route) => ({
      path: route,
      component: { render: () => h('div') }
    }))
  })
  await router.push('/agent')
  await router.push(path)
  const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
  const { useAgentStore } = await server.ssrLoadModule('/src/stores/agent.js')
  const { authApi } = await server.ssrLoadModule('/src/apis/auth_api.js')
  const { healthApi } = await server.ssrLoadModule('/src/apis/system_api.js')
  const user = useUserStore()
  const agent = useAgentStore()
  const initialize = t.mock.method(agent, 'initialize', () => new Promise(() => {}))
  t.mock.method(healthApi, 'checkHealth', async () => ({ status: 'ok' }))
  t.mock.method(user, 'checkFirstRun', async () => false)
  t.mock.method(authApi, 'getOIDCConfig', async () => ({ enabled: false }))
  const { default: View } = await server.ssrLoadModule('virtual:login-view-test')
  const host = makeNode('root')
  const app = renderer.createApp(View)
  app.use(pinia)
  app.use(router)
  for (const name of [
    'a-form-item',
    'a-button',
    'a-input',
    'a-input-password',
    'a-checkbox',
    'a-skeleton-button',
    'a-spin',
    'a-result'
  ]) {
    app.component(name, {
      setup:
        (_props, { slots, attrs }) =>
        () =>
          h(name, attrs, slots.default?.())
    })
  }
  app.component('a-form', {
    props: ['model'],
    emits: ['finish'],
    setup:
      (props, { emit, slots }) =>
      () =>
        h(
          'form',
          { model: props.model, onSubmit: () => emit('finish', props.model) },
          slots.default?.()
        )
  })
  t.after(async () => {
    app.unmount()
    disposePinia(pinia)
    await server.close()
    delete globalThis.window
    delete globalThis.sessionStorage
    delete globalThis.__loginNavigationMessages
  })
  const mount = async () => {
    app.mount(host)
    await new Promise((resolve) => setImmediate(resolve))
    await nextTick()
  }
  const submit = () => {
    const form = find(host, (node) => node.type === 'form')
    assert.ok(form, '真实登录模板已绑定 finish 事件')
    form.props.model.loginId = 'fixture_user'
    form.props.model.password = 'fixture-password'
    form.props.onSubmit()
  }
  return { mount, host, submit, router, user, authApi, initialize, messages }
}

test('智能体初始化一直未完成，密码登录仍立即进入业务页，跳转后才提示成功', async (t) => {
  const fixture = await mountLogin(t)
  const login = t.mock.method(fixture.user, 'login', async () => true)
  const successPaths = []
  fixture.router.afterEach(() => successPaths.push(fixture.messages.length))
  await fixture.mount()
  fixture.submit()
  await waitFor(() => fixture.router.currentRoute.value.path === '/agent', '登录不等待辅助资源')
  assert.equal(login.mock.callCount(), 1)
  assert.equal(fixture.initialize.mock.callCount(), 0)
  assert.deepEqual(successPaths, [0])
  assert.deepEqual(fixture.messages, [{ kind: 'success', text: '登录成功' }])
  assert.equal(sessionStorage.getItem('redirect'), null)
})

test('密码登录优先保留 URL 中的业务页和查询参数，并替换登录历史', async (t) => {
  const fixture = await mountLogin(t, {
    path: '/login?redirect=%2Ffamily%3Ftab%3Dprofiles',
    storedRedirect: '/agent'
  })
  t.mock.method(fixture.user, 'login', async () => true)
  await fixture.mount()
  fixture.submit()
  await waitFor(
    () => fixture.router.currentRoute.value.fullPath === '/family?tab=profiles',
    '回到原先访问的家庭档案'
  )
  assert.equal(sessionStorage.getItem('redirect'), null)
  fixture.router.back()
  await waitFor(() => fixture.router.currentRoute.value.path === '/agent', '返回不会再次进入登录页')
})

test('密码登录使用保存的目标；请求未结束时重复提交只发送一次', async (t) => {
  const fixture = await mountLogin(t, { storedRedirect: '/family?tab=profiles' })
  let finishLogin
  const login = t.mock.method(
    fixture.user,
    'login',
    () =>
      new Promise((resolve) => {
        finishLogin = resolve
      })
  )
  await fixture.mount()
  fixture.submit()
  fixture.submit()
  assert.equal(login.mock.callCount(), 1)
  assert.equal(fixture.router.currentRoute.value.path, '/login')
  assert.deepEqual(fixture.messages, [])
  finishLogin(true)
  await waitFor(
    () => fixture.router.currentRoute.value.fullPath === '/family?tab=profiles',
    '认证完成后恢复保存的业务目标'
  )
})

test('密码错误可重试，账户锁定展示剩余时间并阻止再次提交', async (t) => {
  const fixture = await mountLogin(t)
  t.mock.method(console, 'error', () => {})
  let attempts = 0
  const login = t.mock.method(fixture.user, 'login', async () => {
    if (++attempts === 1) throw new Error('账号或密码错误')
    throw Object.assign(new Error('账户已锁定'), {
      status: 423,
      headers: new Headers({ 'X-Lock-Remaining': '120' })
    })
  })
  await fixture.mount()
  fixture.submit()
  await waitFor(
    () => textContent(fixture.host).includes('账号或密码错误'),
    '认证失败仍显示可恢复错误'
  )
  assert.equal(fixture.router.currentRoute.value.path, '/login')
  fixture.submit()
  await waitFor(() => textContent(fixture.host).includes('账户已锁定'), '锁定状态显示倒计时')
  assert.ok(textContent(fixture.host).includes('2分0秒'))
  fixture.submit()
  assert.equal(login.mock.callCount(), 2)
  assert.equal(fixture.router.currentRoute.value.path, '/login')
  assert.ok(fixture.messages.every(({ kind }) => kind !== 'success'))
})

test('OIDC 交换完成立即进入业务页，复用统一会话并保存数字用户 ID', async (t) => {
  const fixture = await mountLogin(t, {
    view: 'OIDCCallbackView',
    path: '/auth/oidc/callback?code=fixture-code'
  })
  sessionStorage.setItem('oidc_redirect', '/family?tab=profiles')
  sessionStorage.setItem('oidc_auto_start_attempted', '1')
  const exchange = t.mock.method(fixture.authApi, 'exchangeOIDCCode', async () => ({
    access_token: 'fixture-session',
    user_id: 42,
    uid: 'fixture_user',
    username: '合成用户',
    role: 'user'
  }))
  await fixture.mount()
  await waitFor(
    () => fixture.router.currentRoute.value.fullPath === '/family?tab=profiles',
    'OIDC 不使用延时器或等待智能体初始化'
  )
  assert.deepEqual(exchange.mock.calls[0].arguments, ['fixture-code'])
  assert.equal(fixture.user.userId, 42)
  assert.equal(fixture.user.token, 'fixture-session')
  assert.equal(localStorage.getItem('user_token'), 'fixture-session')
  assert.equal(fixture.initialize.mock.callCount(), 0)
  assert.equal(sessionStorage.getItem('oidc_redirect'), null)
  assert.equal(sessionStorage.getItem('oidc_auto_start_attempted'), null)
  assert.deepEqual(fixture.messages, [{ kind: 'success', text: '登录成功' }])
})

test('OIDC 缺少 code 不创建会话，也不显示登录成功', async (t) => {
  const fixture = await mountLogin(t, {
    view: 'OIDCCallbackView',
    path: '/auth/oidc/callback'
  })
  const exchange = t.mock.method(fixture.authApi, 'exchangeOIDCCode', async () => ({}))
  await fixture.mount()
  const error = find(fixture.host, (node) => node.props.title === '参数错误')
  assert.ok(error)
  assert.equal(exchange.mock.callCount(), 0)
  assert.equal(fixture.user.isLoggedIn, false)
  assert.deepEqual(fixture.messages, [])
  assert.equal(fixture.router.currentRoute.value.path, '/auth/oidc/callback')
})
