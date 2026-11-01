import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const script = fileURLToPath(new URL('../scripts/check-miniapp-size.mjs', import.meta.url))
function check(main, sub) {
  const root = mkdtempSync(join(tmpdir(), 'partner-package-budget-'))
  mkdirSync(join(root, 'partner'))
  writeFileSync(join(root, 'project.config.json'), JSON.stringify({ packOptions: { ignore: [] } }))
  writeFileSync(join(root, 'app.json'), JSON.stringify({ pages: [], subPackages: [{ root: 'partner', pages: [] }] }))
  writeFileSync(join(root, 'main.bin'), Buffer.alloc(main))
  writeFileSync(join(root, 'partner/page.bin'), Buffer.alloc(sub))
  return spawnSync(process.execPath, [script, root], { encoding: 'utf8' })
}
test('mini-program budget checks real main and subpackage boundaries independently', () => {
  const result = check(1024 * 1024, 1024 * 1024)
  assert.equal(result.status, 0, result.stderr)
  const data = JSON.parse(result.stdout)
  assert.ok(data.upload_bytes > data.budget_bytes)
  assert.ok(data.packages.every(item => item.upload_bytes <= data.budget_bytes))
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
