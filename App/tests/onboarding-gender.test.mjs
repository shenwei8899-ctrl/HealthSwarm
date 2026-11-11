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
const compiled = compile(source.match(/<template>([\s\S]*?)<\/template>/)[1], {
  filename: 'OnboardingBasics.vue', prefixIdentifiers: true, mode: 'module',
  miniProgram: {
    class: { array: true }, slot: { $slots: '$slots' }, directive: 'wx:',
    emitFile: file => { template = file.source },
  },
})
const render = new Function('_e', '_f', '_o', '_p', '_t',
  compiled.code.slice(compiled.code.indexOf('export function render')).replace('export ', '') + ';return render'
)(Object.assign, (items, callback) => items.map(callback), handler => handler, props => props, String)
const button = template.match(/<button\b[^>]*role="radio"[^>]*>/)[0]
const attribute = name => button.match(new RegExp(name + '="([^"]+)"'))[1]
const listKey = attribute('wx:for').slice(2, -2)
const itemName = attribute('wx:for-item')
const valueAt = (expression, scope) => expression.split('.').reduce((value, key) => value[key], scope)
const disabledKey = attribute('disabled').slice(2, -2)
const clickKey = attribute('bindtap').slice(2, -2)
const checkedKey = attribute('aria-checked').slice(2, -2)
const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')

for (const [label, sourcePermissions, readOnly, disabled] of [
  ['initial onboarding', undefined, false, false],
  ['editable archive', { editable_fields: ['sex'] }, false, false],
  ['archive without sex permission', { editable_fields: [] }, false, true],
  ['read-only archive', { editable_fields: ['sex'] }, true, true],
]) {
  test(`compiled WeChat gender buttons respect ${label}`, () => {
    const member = { name: '合成成员', gender: '女', birthDate: '' }
    const props = { member, source: sourcePermissions, readOnly }
    const editable = new Function('defineProps', script + ';return editable')(() => props)
    const context = { ...props, editable, shanghaiDate: () => '2026-11-07' }
    for (let index = 0; index < 3; index++) {
      const data = render(context, [])
      const scope = { ...data, [itemName]: data[listKey][index] }
      assert.equal(valueAt(disabledKey, scope), disabled)
      if (!disabled) {
        valueAt(clickKey, scope)({})
        assert.equal(member.gender, ['女', '男', '未填写'][index])
        const updated = render(context, [])
        assert.equal(valueAt(checkedKey, { ...updated, [itemName]: updated[listKey][index] }), true)
      }
    }
  })
}

test('archive gender changes produce the corresponding saved sex field', () => {
  for (const [gender, sex] of [['男', 'male'], ['未填写', 'unspecified'], ['女', 'female']]) {
    const original = { gender: gender === '女' ? '男' : '女' }
    assert.deepEqual(memberProfileChanges(original, { gender }, { editable_fields: ['sex'] }), { sex })
  }
})
