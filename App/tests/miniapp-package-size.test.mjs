import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const script = fileURLToPath(new URL('../scripts/check-miniapp-size.mjs', import.meta.url))
function check(main, sub, compiled) {
  const root = mkdtempSync(join(tmpdir(), 'partner-package-budget-'))
  mkdirSync(join(root, 'partner'))
  writeFileSync(join(root, 'project.config.json'), JSON.stringify({ packOptions: { ignore: [] } }))
  writeFileSync(join(root, 'app.json'), JSON.stringify({ pages: [], subPackages: [{ root: 'partner', pages: [] }] }))
  writeFileSync(join(root, 'main.bin'), Buffer.alloc(main))
  writeFileSync(join(root, 'partner/page.bin'), Buffer.alloc(sub))
  const args = [script, root]
  if (compiled) {
    const info = join(root, 'preview-info.json')
    writeFileSync(info, JSON.stringify(compiled))
    args.push('--wechat-info', info)
  }
  return spawnSync(process.execPath, args, { encoding: 'utf8' })
}
test('mini-program budget checks real main and subpackage boundaries independently', () => {
  const result = check(1024 * 1024, 1024 * 1024)
  assert.equal(result.status, 0, result.stderr)
  const data = JSON.parse(result.stdout)
  assert.ok(data.upload_bytes > data.budget_bytes)
  assert.ok(data.packages.every(item => item.upload_bytes <= data.budget_bytes))
  assert.equal(data.verification, 'source-estimate-only')
})
test('a main package exceeding its budget still fails with a small subpackage', () => {
  const result = check(1900 * 1024, 1)
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /main uses/)
})
test('an oversized subpackage fails even when the main package is small', () => {
  const result = check(1, 1900 * 1024)
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /partner\/ uses/)
})

const preview = (main, sub) => ({ size: { total: main + sub, packages: [
  { name: 'TOTAL', size: main + sub }, { name: 'main', size: main }, { name: '/partner/', size: sub },
] } })

test('WeChat compilation over 2 MiB fails even when source files fit', () => {
  const result = check(1024, 1024, preview(2102550, 1024))
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /WeChat compiled main uses 2102550 bytes/)
})

test('a source package between the old and new budgets fails early', () => {
  assert.notEqual(check(1800 * 1024, 1).status, 0)
})

test('matching WeChat preview results report compiled verification', () => {
  const result = check(1024, 1024, preview(1900 * 1024, 2048))
  assert.equal(result.status, 0, result.stderr)
  assert.equal(JSON.parse(result.stdout).verification, 'wechat-compiled')
})

test('preview output for a different package layout is rejected', () => {
  const info = preview(1024, 1024)
  info.size.packages[2].name = '/wrong/'
  const result = check(1024, 1024, info)
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /do not match app.json/)
})
