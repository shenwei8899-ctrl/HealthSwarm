import { spawn } from 'node:child_process'
import { access, readFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'

const projectDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const usage = 'node scripts/build-wechat-api.mjs --api-base-url https://api.example.com --commerce-base-url https://shop.example.com --appid wx0123456789abcdef [--check-only]'

export function validateBaseUrl(value, label) {
  let url
  try { url = new URL(value) } catch { throw new Error(`${label} 必须是完整的 HTTPS 地址`) }
  if (!/^https:\/\//i.test(value) || /[\s\\?#]/.test(value) || url.protocol !== 'https:' ||
      url.username || url.password || /^https:\/\/[^/]*@/i.test(value)) {
    throw new Error(`${label} 必须使用 HTTPS，且不能包含用户凭据、查询参数或片段`)
  }
  const host = url.hostname.toLowerCase().replace(/\.$/, '')
  if (host === 'trycloudflare.com' || host.endsWith('.trycloudflare.com')) {
    throw new Error(`${label} 不能使用临时 trycloudflare.com 域名`)
  }
  return url.href.replace(/\/+$/, '')
}

export function parseArguments(args) {
  const values = {}, names = { '--api-base-url': 'apiBaseUrl', '--commerce-base-url': 'commerceBaseUrl', '--appid': 'appid' }
  let checkOnly = false
  for (let index = 0; index < args.length; index++) {
    const [flag, ...inline] = args[index].split('=')
    if (flag === '--check-only' && !inline.length && !checkOnly) { checkOnly = true; continue }
    const name = names[flag]
    if (!name || Object.hasOwn(values, name)) throw new Error(`未知或重复参数；用法：${usage}`)
    const value = inline.length ? inline.join('=') : args[++index]
    if (!value || value.startsWith('--')) throw new Error(`缺少 ${flag} 的值；用法：${usage}`)
    values[name] = value
  }
  for (const [flag, name] of Object.entries(names)) {
    if (!values[name]) throw new Error(`必须提供 ${flag}；用法：${usage}`)
  }
  if (!/^wx[0-9a-f]{16}$/i.test(values.appid)) throw new Error('appid 必须是有效的小程序 AppID')
  return { apiBaseUrl: validateBaseUrl(values.apiBaseUrl, 'Agent 地址'),
    commerceBaseUrl: validateBaseUrl(values.commerceBaseUrl, 'Shop 地址'), appid: values.appid, checkOnly }
}

async function readEndpoint(url, label, transport) {
  const origin = new URL(url).origin
  for (let redirects = 0; redirects <= 3; redirects++) {
    let response
    try {
      response = await transport(url, { method: 'GET', headers: { Accept: 'application/json' },
        redirect: 'manual', credentials: 'omit', cache: 'no-store', signal: AbortSignal.timeout(10000) })
    } catch { throw new Error(`${label} 网络或超时错误，未开始构建`) }
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get('location')
      if (!location) throw new Error(`${label} 返回无效重定向`)
      let target
      try { target = new URL(location, url) } catch { throw new Error(`${label} 返回无效重定向`) }
      if (target.origin !== origin || target.username || target.password) throw new Error(`${label} 重定向到异域或含凭据地址，已阻止构建`)
      if (redirects === 3) throw new Error(`${label} 重定向次数过多，已阻止构建`)
      url = target.href
      continue
    }
    if (!/\bapplication\/(?:[\w.-]+\+)?json\b/i.test(response.headers.get('content-type') || '')) {
      throw new Error(`${label} 未返回 JSON（HTTP ${response.status}），已阻止构建`)
    }
    let data
    try { data = await response.json() } catch { throw new Error(`${label} 返回无效 JSON，已阻止构建`) }
    return { status: response.status, data }
  }
}

export async function preflight(options, transport = globalThis.fetch) {
  const wechat = await readEndpoint(options.apiBaseUrl + '/api/auth/wechat/config', 'Agent 微信配置', transport)
  if (wechat.status !== 200 || wechat.data?.available !== true || wechat.data?.appid !== options.appid) {
    throw new Error(`Agent 微信配置不可用或 AppID 不匹配（HTTP ${wechat.status}），已阻止构建`)
  }
  const ready = await readEndpoint(options.apiBaseUrl + '/api/system/ready', 'Agent readiness', transport)
  if (ready.status !== 200 || ready.data?.status !== 'ready' || ready.data?.degraded !== false) {
    throw new Error(`Agent 尚未 ready 或处于 degraded 状态（HTTP ${ready.status}），已阻止构建`)
  }
  const shop = await readEndpoint(options.commerceBaseUrl + '/api/v1/commerce/session', 'Shop session', transport)
  if (shop.status !== 401) throw new Error(`Shop session 应返回 JSON 401，实际为 HTTP ${shop.status}，已阻止构建`)
}

export function buildEnvironment(options, projectRoot, inherited = process.env) {
  const env = Object.fromEntries(Object.entries(inherited).filter(([key]) => !/^(VITE_|UNI_)/i.test(key)))
  return { ...env, NODE_ENV: 'production', UNI_PLATFORM: 'mp-weixin', UNI_CLI_CONTEXT: projectRoot,
    UNI_INPUT_DIR: join(projectRoot, 'src'), UNI_OUTPUT_DIR: join(projectRoot, 'dist', 'build', 'mp-weixin'),
    VITE_SERVICE_MODE: 'api', VITE_API_BASE_URL: options.apiBaseUrl,
    VITE_COMMERCE_MODE: 'api', VITE_COMMERCE_API_BASE_URL: options.commerceBaseUrl, VITE_WECHAT_APPID: options.appid,
    VITE_ALLOW_LOCAL_HEALTH_API: '0', VITE_LOCAL_BUSINESS_LOGIN: '0',
    VITE_H5_TEST_LOGIN: '0', VITE_H5_TEST_ORIGIN: '', VITE_PHONE_BINDING_DEMO: '0' }
}

function runUni(command, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, stdio: 'inherit', shell: false })
    child.once('error', () => reject(new Error('无法启动本项目的 uni CLI')))
    child.once('exit', (code, signal) => {
      if (code === 0) resolve()
      else reject(new Error(`uni 构建失败（${signal || '退出码 ' + code}）`))
    })
  })
}

export async function verifyArtifacts(options, projectRoot) {
  const output = join(projectRoot, 'dist', 'build', 'mp-weixin')
  const project = JSON.parse(await readFile(join(output, 'project.config.json'), 'utf8'))
  if (project.appid !== options.appid || project.setting?.urlCheck !== true) {
    throw new Error('构建产物 AppID 或 urlCheck 不符合正式微信配置')
  }
  const source = await readFile(join(output, 'services', 'config.js'), 'utf8')
  let policySource
  if (source.includes('local-login-policy.js')) policySource = await readFile(join(output, 'services', 'local-login-policy.js'), 'utf8')
  const device = { getDeviceInfo: () => ({ platform: 'devtools' }) }
  const execute = (code, require) => {
    const module = { exports: {} }
    vm.runInNewContext(code, { module, exports: module.exports, require, URL, uni: device, wx: device }, { timeout: 1000 })
    return module.exports
  }
  const config = execute(source, name => {
    if (name === '../common/vendor.js') return { index: device }
    if (name === './local-login-policy.js') return execute(policySource, () => { throw new Error('登录策略存在未知依赖') })
    throw new Error('编译配置存在未知依赖')
  })
  const expected = { serviceMode: 'api', isMockMode: false, apiBaseUrl: options.apiBaseUrl,
    isCommerceEnabled: true, commerceApiBaseUrl: options.commerceBaseUrl, wechatAppId: options.appid,
    allowLocalHealthApi: false, canUseBusinessLogin: false, canUsePasswordLogin: false,
    canUseH5TestLogin: false, phoneBindingDemo: false }
  for (const [name, value] of Object.entries(expected)) {
    if (config[name] !== value) throw new Error(`编译配置 ${name} 不符合正式 API 构建要求`)
  }
  return output
}

export async function buildWechatApi(args, { transport = globalThis.fetch, runner = runUni,
  projectRoot = projectDirectory, env = process.env } = {}) {
  const options = parseArguments(args)
  await preflight(options, transport)
  if (options.checkOnly) return { checked: true, built: false }
  const cli = join(projectRoot, 'node_modules', '@dcloudio', 'vite-plugin-uni', 'bin', 'uni.js')
  try { await access(cli) } catch { throw new Error('未找到本项目 node_modules 中的 uni CLI，请先安装项目依赖') }
  await runner(process.execPath, [cli, 'build', '-p', 'mp-weixin'], {
    cwd: projectRoot, env: buildEnvironment(options, projectRoot, env),
  })
  return { checked: true, built: true, output: await verifyArtifacts(options, projectRoot) }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  buildWechatApi(process.argv.slice(2)).then(result => {
    console.log(result.built ? `正式微信 API 构建及产物检查通过：${result.output}` : '正式微信 API 预检通过；未运行构建。')
  }).catch(error => { console.error(error.message); process.exitCode = 1 })
}
