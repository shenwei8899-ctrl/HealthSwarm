import assert from 'node:assert/strict'
import test from 'node:test'

import { createPinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'

const storageValues = new Map()
globalThis.localStorage = {
  getItem: (key) => storageValues.get(key) ?? null,
  setItem: (key, value) => storageValues.set(key, String(value)),
  removeItem: (key) => storageValues.delete(key),
  clear: () => storageValues.clear()
}

async function withServer(run) {
  const server = await createServer({
    server: { middlewareMode: true },
    appType: 'custom',
    // 测试只经 SSR 加载模块，避免为每个实例扫描客户端入口。
    optimizeDeps: { noDiscovery: true, include: [] },
    ssr: { noExternal: ['ant-design-vue'] },
    plugins: [
      {
        name: 'test-message-api',
        enforce: 'pre',
        resolveId(id) {
          return id === 'ant-design-vue' ? '\0test-message-api' : null
        },
        load(id) {
          if (id !== '\0test-message-api') return null
          return `export const message = {
            error(value) { globalThis.__apiBoundaryMessages.push(value) }
          }`
        }
      }
    ]
  })

  try {
    await run(server)
  } finally {
    await server.close()
  }
}

test('公开登录 401 保留服务端错误且不清理当前会话', async () => {
  await withServer(async (server) => {
    storageValues.set('user_token', 'existing-token')
    globalThis.__apiBoundaryMessages = []
    globalThis.window = { location: { href: '/current' } }
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ detail: '用户名或密码错误' }), {
        status: 401,
        headers: { 'content-type': 'application/json' }
      })

    const { authApi } = await server.ssrLoadModule('/src/apis/auth_api.js')

    await assert.rejects(
      authApi.login({ loginId: 'someone', password: 'wrong' }),
      (error) => error.message === '用户名或密码错误' && error.status === 401
    )
    assert.equal(storageValues.get('user_token'), 'existing-token')
    assert.equal(window.location.href, '/current')
    assert.deepEqual(globalThis.__apiBoundaryMessages, [])
  })
})

test('登录 423 保留锁定状态、文案和剩余时间响应头', async () => {
  await withServer(async (server) => {
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ detail: '账户已锁定 60 秒' }), {
        status: 423,
        headers: {
          'content-type': 'application/json',
          'X-Lock-Remaining': '60'
        }
      })

    const { authApi } = await server.ssrLoadModule('/src/apis/auth_api.js')

    await assert.rejects(authApi.login({ loginId: 'someone', password: 'wrong' }), (error) => {
      assert.equal(error.message, '账户已锁定 60 秒')
      assert.equal(error.status, 423)
      assert.equal(error.headers.get('X-Lock-Remaining'), '60')
      return true
    })
  })
})

test('受保护请求的 401 才清理会话并立即跳转登录页', async () => {
  await withServer(async (server) => {
    storageValues.set('user_token', 'expired-token')
    globalThis.__apiBoundaryMessages = []
    const redirects = mockLocation('/agent?project_id=project-1#composer')
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ detail: '令牌已过期' }), {
        status: 401,
        headers: { 'content-type': 'application/json' }
      })

    setActivePinia(createPinia())
    const { apiGet } = await server.ssrLoadModule('/src/apis/base.js')
    const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
    const userStore = useUserStore()

    await assert.rejects(apiGet('/api/protected'), (error) => error.status === 401)
    assert.equal(userStore.isLoggedIn, false)
    assert.equal(storageValues.has('user_token'), false)
    assert.equal(sessionStorage.getItem('redirect'), '/agent?project_id=project-1#composer')
    assert.deepEqual(redirects, ['/login'])
    assert.deepEqual(globalThis.__apiBoundaryMessages, ['登录已过期，请重新登录'])
  })
})

test('旧会话请求迟到的 401 不清理刚登录的新会话', async (t) => {
  await withServer(async (server) => {
    storageValues.set('user_token', 'previous-session')
    globalThis.__apiBoundaryMessages = []
    const redirects = mockLocation('/agent')
    const previousResponse = deferred()
    globalThis.fetch = async (url) => {
      if (url === '/api/protected') return previousResponse.promise
      assert.equal(url, '/api/auth/token')
      return new Response(
        JSON.stringify({
          access_token: 'current-session',
          user_id: 2,
          uid: 'current-user',
          username: '当前用户',
          role: 'user'
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      )
    }

    setActivePinia(createPinia())
    const { apiGet } = await server.ssrLoadModule('/src/apis/base.js')
    const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
    const userStore = useUserStore()
    const logout = t.mock.method(userStore, 'logout')
    const oldRequest = assert.rejects(apiGet('/api/protected'), (error) => error.status === 401)

    await userStore.login({ loginId: 'current-user', password: 'synthetic-password' })
    previousResponse.resolve(unauthorizedResponse())
    await oldRequest

    assert.equal(userStore.isLoggedIn, true)
    assert.equal(userStore.userId, 2)
    assert.equal(userStore.uid, 'current-user')
    assert.equal(userStore.token, 'current-session')
    assert.equal(storageValues.get('user_token'), 'current-session')
    assert.equal(logout.mock.callCount(), 0)
    assert.equal(sessionStorage.getItem('redirect'), null)
    assert.deepEqual(redirects, [])
    assert.deepEqual(globalThis.__apiBoundaryMessages, [])
  })
})

test('同一会话的并发 401 只退出、提示和跳转一次', async (t) => {
  await withServer(async (server) => {
    storageValues.set('user_token', 'expired-session')
    globalThis.__apiBoundaryMessages = []
    const redirects = mockLocation('/agent')
    const responses = [deferred(), deferred()]
    let requested = 0
    globalThis.fetch = async () => responses[requested++].promise

    setActivePinia(createPinia())
    const { apiGet } = await server.ssrLoadModule('/src/apis/base.js')
    const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
    const userStore = useUserStore()
    const logout = t.mock.method(userStore, 'logout')
    const requests = [
      assert.rejects(apiGet('/api/protected/one'), (error) => error.status === 401),
      assert.rejects(apiGet('/api/protected/two'), (error) => error.status === 401)
    ]
    assert.equal(requested, 2)
    responses.forEach((response) => response.resolve(unauthorizedResponse()))
    await Promise.all(requests)

    assert.equal(userStore.isLoggedIn, false)
    assert.equal(storageValues.has('user_token'), false)
    assert.equal(logout.mock.callCount(), 1)
    assert.deepEqual(redirects, ['/login'])
    assert.deepEqual(globalThis.__apiBoundaryMessages, ['登录已过期，请重新登录'])
  })
})

test('已在登录页时受保护请求 401 不触发重复导航', async () => {
  await withServer(async (server) => {
    storageValues.set('user_token', 'expired-session')
    globalThis.__apiBoundaryMessages = []
    const redirects = mockLocation('/login')
    globalThis.fetch = async () => unauthorizedResponse()

    setActivePinia(createPinia())
    const { apiGet } = await server.ssrLoadModule('/src/apis/base.js')
    const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
    const userStore = useUserStore()

    await assert.rejects(apiGet('/api/protected'), (error) => error.status === 401)
    assert.equal(userStore.isLoggedIn, false)
    assert.equal(storageValues.has('user_token'), false)
    assert.deepEqual(redirects, [])
    assert.deepEqual(globalThis.__apiBoundaryMessages, ['登录已过期，请重新登录'])
  })
})

/** 记录真实重定向动作，避免用立即执行定时器掩盖延迟行为。 */
function mockLocation(path) {
  const redirects = []
  const url = new URL(path, 'http://healthswarm.local')
  const sessionValues = new Map()
  globalThis.sessionStorage = {
    getItem: (key) => sessionValues.get(key) ?? null,
    setItem: (key, value) => sessionValues.set(key, String(value)),
    removeItem: (key) => sessionValues.delete(key)
  }
  globalThis.window = {
    location: {
      pathname: url.pathname,
      search: url.search,
      hash: url.hash,
      href: path,
      replace(path) {
        redirects.push(path)
      }
    }
  }
  return redirects
}

/** 每个请求持有独立响应，验证响应到达时的会话归属。 */
function deferred() {
  let resolve
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

/** 返回可重复消费的独立认证失败响应。 */
function unauthorizedResponse() {
  return new Response(JSON.stringify({ detail: '令牌已过期' }), {
    status: 401,
    headers: { 'content-type': 'application/json' }
  })
}

test('用户 Store 的 422 传播链不泄露认证头、密码或 Pydantic input', async () => {
  await withServer(async (server) => {
    storageValues.clear()
    const secretToken = 'secret-bearer-token'
    const secretPassword = 'secret-password'
    const secretResponse = 'secret-response-context'
    const logged = []
    const originalConsoleError = console.error

    try {
      console.error = (...values) => logged.push(values)
      globalThis.fetch = async () =>
        new Response(
          JSON.stringify({
            detail: [
              {
                loc: ['body', 'password'],
                msg: 'Value error',
                type: 'value_error',
                input: secretPassword,
                ctx: { secret: secretResponse }
              }
            ]
          }),
          {
            status: 422,
            statusText: 'Unprocessable Entity',
            headers: { 'content-type': 'application/json' }
          }
        )

      setActivePinia(createPinia())
      const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
      const userStore = useUserStore()
      userStore.token = secretToken
      userStore.userId = 1

      await assert.rejects(
        userStore.createUser({ username: 'new-user', password: secretPassword }),
        (error) => error.status === 422
      )

      const serializedLogs = JSON.stringify(logged)
      assert.equal(serializedLogs.includes(secretToken), false)
      assert.equal(serializedLogs.includes(secretPassword), false)
      assert.equal(serializedLogs.includes(secretResponse), false)
      assert.equal(serializedLogs.includes('/api/auth/users'), true)
      assert.equal(serializedLogs.includes('422'), true)
    } finally {
      console.error = originalConsoleError
    }
  })
})

test('用户 Store 的普通错误传播链不附着或记录服务端任意响应上下文', async () => {
  await withServer(async (server) => {
    storageValues.clear()
    const secretToken = 'secret-bearer-token'
    const secretPassword = 'secret-password'
    const secretResponse = 'secret-response-context'
    const logged = []
    const originalConsoleError = console.error

    try {
      console.error = (...values) => logged.push(values)
      globalThis.fetch = async () =>
        new Response(
          JSON.stringify({
            detail: {
              message: secretResponse,
              context: { note: secretPassword }
            }
          }),
          {
            status: 400,
            statusText: secretResponse,
            headers: { 'content-type': 'application/json' }
          }
        )

      setActivePinia(createPinia())
      const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
      const userStore = useUserStore()
      userStore.token = secretToken
      userStore.userId = 1

      await assert.rejects(
        userStore.createUser({ username: 'new-user', password: secretPassword }),
        (error) => {
          assert.equal(error.status, 400)
          assert.equal(error.message, '请求参数错误')
          assert.deepEqual(error.response.data, { detail: '请求参数错误' })
          return true
        }
      )

      const serializedLogs = JSON.stringify(logged)
      assert.equal(serializedLogs.includes(secretToken), false)
      assert.equal(serializedLogs.includes(secretPassword), false)
      assert.equal(serializedLogs.includes(secretResponse), false)
      assert.equal(serializedLogs.includes('/api/auth/users'), true)
      assert.equal(serializedLogs.includes('400'), true)
    } finally {
      console.error = originalConsoleError
    }
  })
})

test('用户管理分页 API 只请求当前页并编码服务端筛选条件', async () => {
  await withServer(async (server) => {
    storageValues.set('user_token', 'test-token')
    const requests = []
    globalThis.fetch = async (url) => {
      requests.push(String(url))
      return new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 40 }), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    }

    setActivePinia(createPinia())
    const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
    useUserStore().userRole = 'superadmin'
    const { authApi } = await server.ssrLoadModule('/src/apis/auth_api.js')

    const page = await authApi.getUsersPage({
      offset: 40,
      limit: 20,
      search: '张 三',
      departmentId: 3,
      role: 'admin'
    })

    assert.deepEqual(requests, [
      '/api/auth/users/page?offset=40&limit=20&search=%E5%BC%A0+%E4%B8%89&department_id=3&role=admin'
    ])
    assert.equal(page.total, 0)
  })
})

test('用户管理组件不再通过 Store 全量加载用户', async () => {
  const source = await import('node:fs/promises').then((fs) =>
    fs.readFile(
      new URL('../../src/components/UserManagementComponent.vue', import.meta.url),
      'utf8'
    )
  )

  assert.equal(source.includes('authApi.getUsersPage('), true)
  assert.equal(source.includes('userStore.getUsers()'), false)
  assert.equal(source.includes('filteredUsers'), false)
  assert.equal(source.includes('paginatedUsers'), false)
})

test('知识库 API 单一构造并编码文件上传端点', async () => {
  await withServer(async (server) => {
    const { fileApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')

    assert.equal(fileApi.getUploadUrl(), '/api/knowledge/files/upload')
    assert.equal(
      fileApi.getUploadUrl('kb/with space'),
      '/api/knowledge/files/upload?kb_id=kb%2Fwith%20space'
    )
  })
})

test('共享查询参数边界保留 false/0 并省略 undefined/null/空字符串', async () => {
  await withServer(async (server) => {
    const { buildQuery } = await server.ssrLoadModule('/src/apis/base.js')

    assert.equal(
      buildQuery({
        false_value: false,
        zero_value: 0,
        empty_value: '',
        null_value: null,
        undefined_value: undefined,
        text: 'a b/c'
      }),
      'false_value=false&zero_value=0&text=a+b%2Fc'
    )
  })
})

test('四个 API 模块复用查询参数边界并保持 endpoint 问号语义', async () => {
  await withServer(async (server) => {
    storageValues.set('user_token', 'test-token')
    const requests = []
    globalThis.fetch = async (url) => {
      requests.push(String(url))
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    }

    setActivePinia(createPinia())
    const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
    useUserStore().userRole = 'admin'
    const { projectApi } = await server.ssrLoadModule('/src/apis/project_api.js')
    const { searchViewerFiles } = await server.ssrLoadModule('/src/apis/viewer_filesystem.js')
    const { getWorkspaceKnowledgeTree } = await server.ssrLoadModule('/src/apis/workspace_api.js')
    const { documentApi } = await server.ssrLoadModule('/src/apis/knowledge_api.js')

    await projectApi.getHistoryCandidates({ query: '', limit: 0, offset: 0 })
    await searchViewerFiles('thread-1', '')
    await getWorkspaceKnowledgeTree('kb-1', {
      page: 0,
      pageSize: false,
      recursive: false,
      filesOnly: false
    })
    await documentApi.listDocuments('kb-1', {
      page: 0,
      page_size: false,
      empty: '',
      ignored: null
    })
    await documentApi.listDocuments('kb-1')
    await documentApi.documentExists('kb-1')

    assert.deepEqual(requests, [
      '/api/projects/history-candidates?limit=0&offset=0',
      '/api/viewer/filesystem/search?thread_id=thread-1',
      '/api/workspace/knowledge/tree?kb_id=kb-1&page=0&page_size=false&recursive=false&files_only=false',
      '/api/knowledge/databases/kb-1/documents?page=0&page_size=false',
      '/api/knowledge/databases/kb-1/documents',
      '/api/knowledge/databases/kb-1/documents/exists?'
    ])
  })
})

test('Project 与 Workspace API 按 xhome 契约构造请求', async () => {
  await withServer(async (server) => {
    storageValues.set('user_token', 'test-token')
    const requests = []
    globalThis.fetch = async (url, options = {}) => {
      requests.push({ url, options })
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    }

    setActivePinia(createPinia())
    const { projectApi } = await server.ssrLoadModule('/src/apis/project_api.js')
    const { createWorkspaceDirectory, getWorkspaceTree } = await server.ssrLoadModule(
      '/src/apis/workspace_api.js'
    )

    await projectApi.getProjects()
    await projectApi.createProject({
      requestId: 'request-1',
      name: '客户交付',
      mode: 'linked',
      path: '/clients/acme'
    })
    await projectApi.getHistoryCandidates({ query: '交付', limit: 10, offset: 20 })
    await getWorkspaceTree('/projects')
    await getWorkspaceTree('/projects', false, false, true)
    await createWorkspaceDirectory('/projects', '客户交付')

    assert.equal(requests[0].url, '/api/projects')
    assert.deepEqual(JSON.parse(requests[1].options.body), {
      request_id: 'request-1',
      name: '客户交付',
      workdir: { mode: 'linked', path: 'clients/acme' }
    })
    assert.equal(
      requests[2].url,
      '/api/projects/history-candidates?q=%E4%BA%A4%E4%BB%98&limit=10&offset=20'
    )
    assert.equal(
      requests[3].url,
      '/api/workspace/tree?path=%2Fprojects&recursive=false&files_only=false'
    )
    assert.equal(
      requests[4].url,
      '/api/workspace/tree?path=%2Fprojects&recursive=false&files_only=false&include_unbound_project_dirs=true'
    )
    assert.deepEqual(JSON.parse(requests[5].options.body), {
      parent_path: '/projects',
      name: '客户交付'
    })
  })
})

test('工具元数据 API 使用普通用户认证且普通用户可正常请求', async () => {
  await withServer(async (server) => {
    storageValues.clear()
    storageValues.set('user_token', 'user-token')
    globalThis.fetch = async (url) => {
      assert.equal(url, '/api/system/tools')
      return new Response(
        JSON.stringify({ success: true, data: [{ name: '搜索', slug: 'web_search' }] }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' }
        }
      )
    }

    setActivePinia(createPinia())
    const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
    const userStore = useUserStore()
    userStore.token = 'user-token'
    userStore.role = 'user' // 非管理员

    const { toolApi } = await server.ssrLoadModule('/src/apis/tool_api.js')
    const result = await toolApi.getTools()
    assert.equal(result.success, true)
    assert.equal(result.data.length, 1)
    assert.equal(result.data[0].slug, 'web_search')
  })
})
