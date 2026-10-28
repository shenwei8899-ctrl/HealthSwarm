import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { buildEnvironment, buildWechatApi, parseArguments } from '../scripts/build-wechat-api.mjs'

const appid = 'wx0123456789abcdef', api = 'https://agent.example.test', shop = 'https://shop.example.test'
const args = ['--api-base-url', api, '--commerce-base-url', shop, '--appid', appid]
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } })
const redirect = location => new Response(null, { status: 302, headers: { Location: location } })

function transport(overrides = {}, calls = []) {
  return async (url, options) => {
    calls.push({ url, options })
    assert.equal(options.method, 'GET')
    assert.equal(options.redirect, 'manual')
    assert.equal(options.credentials, 'omit')
    assert.deepEqual(options.headers, { Accept: 'application/json' })
    if (Object.hasOwn(overrides, url)) return overrides[url]()
    if (url === api + '/api/auth/wechat/config') return json({ available: true, appid })
    if (url === api + '/api/system/ready') return json({ status: 'ready', degraded: false })
    if (url === shop + '/api/v1/commerce/session') return json({ code: 401, message: 'synthetic unauthenticated' }, 401)
    assert.fail('Unexpected synthetic endpoint: ' + url)
  }
}

async function sandbox(t) {
  const root = await mkdtemp(join(tmpdir(), 'wechat-api-build-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const cli = join(root, 'node_modules', '@dcloudio', 'vite-plugin-uni', 'bin', 'uni.js')
  await mkdir(join(cli, '..'), { recursive: true })
  await writeFile(cli, '// synthetic runner target\n')
  const output = join(root, 'dist', 'build', 'mp-weixin')
  await mkdir(output, { recursive: true })
  await writeFile(join(output, 'preserve.txt'), 'existing output')
  return { root, cli, output }
}

async function artifacts(output, env, changes = {}, project = {}) {
  await mkdir(join(output, 'services'), { recursive: true })
  await writeFile(join(output, 'project.config.json'), JSON.stringify({ appid: env.VITE_WECHAT_APPID, setting: { urlCheck: true }, ...project }))
  const config = { serviceMode: env.VITE_SERVICE_MODE, isMockMode: env.VITE_SERVICE_MODE !== 'api', apiBaseUrl: env.VITE_API_BASE_URL,
    isCommerceEnabled: env.VITE_COMMERCE_MODE === 'api', commerceApiBaseUrl: env.VITE_COMMERCE_API_BASE_URL, wechatAppId: env.VITE_WECHAT_APPID,
    allowLocalHealthApi: env.VITE_ALLOW_LOCAL_HEALTH_API === '1', canUseBusinessLogin: env.VITE_LOCAL_BUSINESS_LOGIN === '1',
    canUseH5TestLogin: env.VITE_H5_TEST_LOGIN === '1', canUsePasswordLogin: false, phoneBindingDemo: env.VITE_PHONE_BINDING_DEMO === '1', ...changes }
  await writeFile(join(output, 'services', 'config.js'), 'Object.assign(exports,' + JSON.stringify(config) + ');\n')
}

test('arguments are mandatory, canonical and never fall back to environment values', () => {
  assert.deepEqual(parseArguments(['--api-base-url=' + api + '/', '--commerce-base-url=' + shop + '/', '--appid=' + appid, '--check-only']),
    { apiBaseUrl: api, commerceBaseUrl: shop, appid, checkOnly: true })
  for (const invalid of [[], args.slice(2), args.slice(0, 2).concat(args.slice(4)), args.slice(0, 4),
    [...args, '--appid', appid], [...args, '--other'], [...args, 'unexpected'], [...args, '--check-only', '--check-only'],
    [...args.slice(0, 4), '--appid', 'touristappid'], ['--api-base-url']]) {
    assert.throws(() => parseArguments(invalid))
  }
})

test('both URLs reject HTTP, credentials, queries, fragments and temporary tunnel hosts', () => {
  for (const url of ['http://agent.example.test', 'ftp://agent.example.test', 'https://user:pass@agent.example.test',
    'https://@agent.example.test', api + '?', api + '?token=synthetic', api + '#', api + '#fragment', api + '/bad path',
    'https://demo.trycloudflare.com', 'https://deep.demo.trycloudflare.com', 'https://demo.trycloudflare.com.',
    'https://TRYCLOUDFLARE.COM', 'not-a-url', 'https:\\agent.example.test']) {
    assert.throws(() => parseArguments(['--api-base-url', url, '--commerce-base-url', shop, '--appid', appid]))
    assert.throws(() => parseArguments(['--api-base-url', api, '--commerce-base-url', url, '--appid', appid]))
  }
})

test('check-only probes the three real contracts without calling a runner or touching dist', async t => {
  const { root, output } = await sandbox(t), calls = []
  const result = await buildWechatApi([...args, '--check-only'], { projectRoot: root, transport: transport({}, calls), runner: () => assert.fail('must not build') })
  assert.deepEqual(result, { checked: true, built: false })
  assert.equal(calls.length, 3)
  assert.equal(await readFile(join(output, 'preserve.txt'), 'utf8'), 'existing output')
})

test('every failed prerequisite blocks the runner and preserves existing output', async t => {
  const { root, output } = await sandbox(t)
  const cases = [
    [api + '/api/auth/wechat/config', () => json({ available: true, appid }, 404)],
    [api + '/api/auth/wechat/config', () => json({ available: false, appid })],
    [api + '/api/auth/wechat/config', () => json({ available: true, appid: 'wx1111111111111111' })],
    [api + '/api/system/ready', () => json({ status: 'not_ready', degraded: false })],
    [api + '/api/system/ready', () => json({ status: 'ready', degraded: true })],
    [api + '/api/system/ready', () => json({ status: 'ready' })],
    [shop + '/api/v1/commerce/session', () => json({ code: 0 })],
    [shop + '/api/v1/commerce/session', () => json({ code: 404 }, 404)],
    [shop + '/api/v1/commerce/session', () => new Response('<html>synthetic</html>', { status: 401, headers: { 'Content-Type': 'text/html' } })],
    [shop + '/api/v1/commerce/session', () => new Response('{broken', { status: 401, headers: { 'Content-Type': 'application/json' } })],
  ]
  for (const [url, response] of cases) {
    await assert.rejects(buildWechatApi(args, { projectRoot: root, transport: transport({ [url]: response }), runner: () => assert.fail('must not build') }))
    assert.equal(await readFile(join(output, 'preserve.txt'), 'utf8'), 'existing output')
  }
})

test('cross-origin redirects are rejected before a request reaches the other host', async () => {
  const calls = []
  await assert.rejects(buildWechatApi([...args, '--check-only'], {
    transport: transport({ [api + '/api/auth/wechat/config']: () => redirect('https://other.example.test/config') }, calls),
    runner: () => assert.fail('must not build'),
  }), /异域/)
  assert.equal(calls.length, 1)
})

test('same-origin redirects can satisfy a contract, but loops and credential redirects fail', async () => {
  const endpoint = api + '/api/auth/wechat/config'
  const followed = transport({ [endpoint]: () => redirect('/wechat-config'), [api + '/wechat-config']: () => json({ available: true, appid }) })
  assert.equal((await buildWechatApi([...args, '--check-only'], { transport: followed })).checked, true)
  for (const location of [endpoint, 'https://synthetic:password@agent.example.test/config']) {
    await assert.rejects(buildWechatApi([...args, '--check-only'], { transport: transport({ [endpoint]: () => redirect(location) }) }), /重定向/)
  }
  await assert.rejects(buildWechatApi([...args, '--check-only'], { transport: transport({ [endpoint]: () => new Response(null, { status: 302 }) }) }), /无效重定向/)
})

test('network errors do not disclose response or transport details', async () => {
  await assert.rejects(buildWechatApi([...args, '--check-only'], { transport: async () => { throw new Error('synthetic-secret-must-stay-private') } }),
    error => /网络或超时/.test(error.message) && !error.message.includes('synthetic-secret'))
})

test('the build uses the local uni CLI and overrides inherited test or mock settings', async t => {
  const { root, cli, output } = await sandbox(t), calls = []
  const inherited = { PATH: 'synthetic-path', VITE_SERVICE_MODE: 'mock', VITE_API_BASE_URL: 'http://localhost:15050',
    VITE_ALLOW_LOCAL_HEALTH_API: '1', VITE_LOCAL_BUSINESS_LOGIN: '1', VITE_H5_TEST_LOGIN: '1',
    VITE_H5_TEST_ORIGIN: 'https://test.example.test', VITE_PHONE_BINDING_DEMO: '1', UNI_OUTPUT_DIR: 'elsewhere', VITE_UNUSED: 'discard' }
  const result = await buildWechatApi(args, { projectRoot: root, env: inherited, transport: transport(),
    runner: async (command, parameters, options) => {
      calls.push({ command, parameters, options })
      await artifacts(output, options.env)
    } })
  assert.deepEqual(calls[0].parameters, [cli, 'build', '-p', 'mp-weixin'])
  assert.equal(calls[0].command, process.execPath)
  assert.equal(calls[0].options.cwd, root)
  assert.equal(calls[0].options.env.UNI_OUTPUT_DIR, output)
  assert.equal(calls[0].options.env.VITE_UNUSED, undefined)
  assert.equal(calls[0].options.env.PATH, inherited.PATH)
  for (const key of ['VITE_ALLOW_LOCAL_HEALTH_API', 'VITE_LOCAL_BUSINESS_LOGIN', 'VITE_H5_TEST_LOGIN', 'VITE_PHONE_BINDING_DEMO']) {
    assert.equal(calls[0].options.env[key], '0')
  }
  assert.equal(calls[0].options.env.VITE_H5_TEST_ORIGIN, '')
  assert.equal(inherited.VITE_SERVICE_MODE, 'mock')
  assert.deepEqual(result, { checked: true, built: true, output })
})

test('post-build verification rejects wrong AppID, disabled URL checks, mock APIs and test switches', async t => {
  const { root, output } = await sandbox(t)
  for (const [changes, project] of [
    [{}, { appid: 'touristappid' }], [{}, { setting: { urlCheck: false } }],
    [{ serviceMode: 'mock' }, {}], [{ isMockMode: true }, {}], [{ apiBaseUrl: 'https://wrong.example.test' }, {}],
    [{ isCommerceEnabled: false }, {}], [{ commerceApiBaseUrl: 'https://wrong.example.test' }, {}], [{ wechatAppId: 'touristappid' }, {}],
    ...['allowLocalHealthApi', 'canUseBusinessLogin', 'canUsePasswordLogin', 'canUseH5TestLogin', 'phoneBindingDemo'].map(name => [{ [name]: true }, {}]),
  ]) {
    await assert.rejects(buildWechatApi(args, { projectRoot: root, transport: transport(),
      runner: async (_command, _args, options) => artifacts(output, options.env, changes, project) }), /构建产物|编译配置/)
  }
})

test('build failures are propagated and missing local dependencies never use a global CLI', async t => {
  const { root, cli } = await sandbox(t)
  await assert.rejects(buildWechatApi(args, { projectRoot: root, transport: transport(), runner: async () => { throw new Error('synthetic build failed') } }), /synthetic build failed/)
  await rm(cli)
  await assert.rejects(buildWechatApi(args, { projectRoot: root, transport: transport(), runner: () => assert.fail('must not build') }), /本项目 node_modules/)
})

test('compiled login policy is evaluated with a restricted local module loader', async t => {
  const { root, output } = await sandbox(t)
  await buildWechatApi(args, { projectRoot: root, transport: transport(), runner: async (_command, _args, options) => {
    await artifacts(output, options.env)
    const path = join(output, 'services', 'config.js')
    await writeFile(path, await readFile(path, 'utf8') + '\nconst vendor=require("../common/vendor.js"); const policy=require("./local-login-policy.js"); exports.canUseBusinessLogin=policy.enabled(vendor.index.getDeviceInfo().platform);')
    await writeFile(join(output, 'services', 'local-login-policy.js'), 'exports.enabled=platform=>platform!=="devtools";')
  } })
  assert.equal(buildEnvironment(parseArguments(args), root, {}).UNI_PLATFORM, 'mp-weixin')
})
