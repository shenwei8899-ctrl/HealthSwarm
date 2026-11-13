import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { memberProfileChanges } from '../src/services/member-profile.js'

const require = createRequire(import.meta.url)
const wechatRequire = createRequire(require.resolve('@dcloudio/uni-mp-weixin/package.json'))
const { compile } = wechatRequire('@dcloudio/uni-mp-compiler')
const source = readFileSync(new URL('../src/components/OnboardingBasics.vue', import.meta.url), 'utf8')
let template
compile(source.match(/<template>([\s\S]*?)<\/template>/)[1], {
  filename: 'OnboardingBasics.vue', prefixIdentifiers: true, mode: 'module',
  miniProgram: { class: { array: true }, slot: { $slots: '$slots' }, directive: 'wx:', emitFile: file => { template = file.source } },
})
const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')

test('WeChat template uses native radio change and disables unavailable choices', () => {
  assert.match(template, /<radio-group\b[^>]*bindchange=/)
  assert.match(template, /<radio\b[^>]*u-p=/)
  assert.match(source, /<radio\s+:value="genderOption"\s+:checked=/)
  assert.match(source, /:disabled="!editable\('sex'\)"/)
})

for (const [label, sourcePermissions, readOnly, enabled] of [
  ['initial onboarding', undefined, false, true],
  ['editable archive', { editable_fields: ['sex'] }, false, true],
  ['archive without sex permission', { editable_fields: [] }, false, false],
  ['read-only archive', { editable_fields: ['sex'] }, true, false],
]) test(`native gender change respects ${label}`, () => {
  const member = { gender: '未填写' }, props = { member, source: sourcePermissions, readOnly }
  const { selectGender } = new Function('defineProps', script + ';return {selectGender}')(() => props)
  selectGender({detail:{value:'男'}})
  assert.equal(member.gender, enabled ? '男' : '未填写')
  selectGender({detail:{value:'invalid'}})
  assert.equal(member.gender, enabled ? '男' : '未填写')
})

test('archive gender changes produce the corresponding saved sex field', () => {
  for (const [gender, sex] of [['男', 'male'], ['女', 'female']]) {
    const original = { gender: gender === '女' ? '男' : '女' }
    assert.deepEqual(memberProfileChanges(original, { gender }, { editable_fields: ['sex'] }), { sex })
  }
  assert.throws(()=>memberProfileChanges({gender:'女'},{gender:'未填写'},{editable_fields:['sex']}),/性别/)
})
