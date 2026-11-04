import test from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { accessSync } from 'node:fs'
import { join } from 'node:path'

// Run against a fresh uni build using the WCC shipped with WeChat DevTools.
// Vue rendering and the uni build alone do not validate WXML expressions.
const compiler = process.env.WECHAT_WXML_COMPILER
const buildDirectory = process.env.WECHAT_MINIAPP_BUILD_DIR

test('meal capture output compiles with the native WeChat WXML compiler', {
  skip: !compiler || !buildDirectory ? 'Set WECHAT_WXML_COMPILER and WECHAT_MINIAPP_BUILD_DIR for the native check' : false,
}, () => {
  const component = 'components/CloudMealCapture.wxml'
  accessSync(join(buildDirectory, component))
  const result = spawnSync(compiler, [component], {
    cwd: buildDirectory,
    encoding: 'utf8',
    stdio: ['ignore', 'ignore', 'pipe'],
    timeout: 30000,
  })
  assert.ifError(result.error)
  assert.equal(result.status, 0, result.stderr || `WXML compiler exited with ${result.status}`)
})
