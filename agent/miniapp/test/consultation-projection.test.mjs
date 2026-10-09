import test from 'node:test'
import assert from 'node:assert/strict'
import { consultationMember, consultationPolicy, boundConsultation, consultationList, historyProjection,
  resultProjection, visibleHistory, requestProjection, runProjection, activeRunProjection } from '../src/ui/consultation-projection.js'

const expected = { run_id: 'run', thread_id: 'thread', request_id: 'request', uid: 'uid' }
const result = () => ({ status: 'completed', output: '公开最终回答', agent_slug: 'health-consultation',
  thread_id: 'thread', agent_run_id: 'run', request_id: 'request', final_message_id: 22, private_data: '不进入投影' })
const history = () => ({ thread: { id: 'thread', uid: 'uid', agent_id: 'health-consultation', metadata: { secret: true } },
  runs: [{ run_id: 'run', request_id: 'request', status: 'completed', run_type: 'chat', created_by_run_id: null }],
  history: [{ id: 11, type: 'human', message_type: 'text', content: '公开问题', run_id: 'run', request_id: 'request' },
    { id: 22, type: 'ai', message_type: 'text', content: '历史正文不是权威回答', run_id: 'run', request_id: 'request' }] })

test('本人身份必须同时满足拥有、本人关系、档案授权；只投影当前所需权限', () => {
  const row = { id: 'member', is_owner: true, relationship_label: '本人', display_name: '合成本人',
    scopes: ['profile_view', 'profile_edit', 'ai_use', 'report_view', 'diet_edit', 'admin'], profile: '私有档案' }
  assert.deepEqual(consultationMember([row], 'member'), { id: 'member', display_name: '合成本人',
    scopes: ['profile_view', 'profile_edit', 'ai_use', 'report_view', 'diet_edit'] })
  for (const changed of [{ is_owner: false }, { relationship_label: '父亲' }, { scopes: ['ai_use'] }]) {
    assert.throws(() => consultationMember([{ ...row, ...changed }], 'member'))
  }
})

test('政策和真实成员咨询分页丢弃配置、正文等无关字段', () => {
  assert.deepEqual(consultationPolicy({ policy_version: 'v1', secret: 'hidden', consultation: {
    available: true, reason: null, model: 'model', processor: 'processor', private_config: {} } }), {
    available: true, reason: '', policy_version: 'v1', model: 'model', processor: 'processor' })
  const binding = { member_id: 'member', thread_id: 'thread', agent_slug: 'health-consultation', business_date: null, created_at: 'date', title: '隐藏标题', content: '私有' }
  const page = consultationList({ items: [binding], has_more: true, next_offset: 20 }, 'member')
  assert.deepEqual(page.items, [{ member_id: 'member', thread_id: 'thread', agent_slug: 'health-consultation', business_date: null, created_at: 'date' }])
  assert.throws(() => boundConsultation({ ...binding, member_id: 'other' }, 'member'))
  assert.throws(() => consultationList({ items: [], has_more: true, next_offset: null }, 'member'))
})

test('未审批政策的空字段保留不可用原因；不伪造模型与处理方', () => {
  assert.deepEqual(consultationPolicy({ policy_version: '', consultation: { available: false,
    reason: '尚未审批云处理政策', model: '', processor: '' } }), {
    available: false, reason: '尚未审批云处理政策', policy_version: '', model: '', processor: '' })
})

test('真实Integer最终消息ID与history统一精确匹配，拒绝无效数值ID', () => {
  const projected = historyProjection(history(), 'thread', 'uid')
  assert.equal(projected.rows[1].id, '22'); assert.equal(resultProjection(result(), expected).id, '22')
  assert.equal(visibleHistory(projected, [resultProjection({ ...result(), final_message_id: '22' }, expected)]).at(-1).text, '公开最终回答')
  for (const final_message_id of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1, null, '', 'answer', '1.5', ' 22 ']) {
    assert.throws(() => resultProjection({ ...result(), final_message_id }, expected), error => error.code === 'protocol_mismatch')
  }
})

test('公开历史只接收完成顶层纯文本；AI正文取权威result而非历史或工具', () => {
  const value = history()
  value.runs.push({ run_id: 'child', request_id: 'child-request', status: 'completed', run_type: 'chat', created_by_run_id: 'run' },
    { run_id: 'resume', request_id: 'resume-request', status: 'completed', run_type: 'resume', created_by_run_id: 'run' },
    { run_id: 'pending', request_id: 'pending-request', status: 'running', run_type: 'chat' })
  value.history.push(...['tool', 'system'].map((type, index) => ({ id: 30 + index, type, content: '内部资料', message_type: 'text', run_id: 'run', request_id: 'request' })),
    { id: 32, type: 'ai', content: '审计', message_type: 'model_audit', run_id: 'run', request_id: 'request' },
    { id: 33, type: 'ai', content: '内部调用', message_type: 'text', tool_calls: [{ secret: true }], run_id: 'run', request_id: 'request' },
    { id: 34, type: 'ai', content: '子运行', message_type: 'text', run_id: 'child', request_id: 'child-request' },
    { id: 35, type: 'ai', content: '未完成', message_type: 'text', run_id: 'pending', request_id: 'pending-request' })
  const projected = historyProjection(value, 'thread', 'uid')
  assert.equal(projected.rows[1].text, '')
  assert.deepEqual(visibleHistory(projected, [resultProjection(result(), expected)]).map(row => row.text), ['公开问题', '公开最终回答'])
  assert.equal(JSON.stringify(projected).includes('内部'), false)
})

test('历史按最近20个完成顶层Run窗口展示；每条回答必须匹配最终消息ID', () => {
  const value = history()
  value.runs = Array.from({ length: 25 }, (_, index) => ({ run_id: `r${index}`, request_id: `q${index}`, status: 'completed', run_type: 'chat' }))
  const projection = historyProjection(value, 'thread', 'uid')
  assert.equal(projection.completed.length, 20); assert.equal(projection.completed[0].run_id, 'r5')
  assert.deepEqual(visibleHistory(historyProjection(history(), 'thread', 'uid'), [{ ...resultProjection(result(), expected), id: 'different' }]).filter(row => row.role === 'assistant'), [])
})

test('错误账号、线程、Run、Request、最终消息或非completed结果都拒绝展示', () => {
  for (const changed of [{ status: 'running' }, { agent_slug: 'other' }, { thread_id: 'other' }, { agent_run_id: 'other' },
    { request_id: 'other' }, { final_message_id: null }, { error: { type: 'anything' } }]) assert.throws(() => resultProjection({ ...result(), ...changed }, expected))
  assert.throws(() => historyProjection(history(), 'wrong', 'uid'))
  assert.throws(() => historyProjection(history(), 'thread', 'other'))
  assert.throws(() => resultProjection({ status: 'failed', output: '', error: { type: 'run_not_found' } }, expected), error => error.status === 404)
})

test('POST的run_id和GET的dispatched_run_id分别解析，不读取同名伪字段', () => {
  assert.equal(requestProjection({ request_id: 'request', thread_id: 'thread', status: 'queued', run_id: null, dispatched_run_id: 'wrong' }, expected, true).run_id, null)
  assert.equal(requestProjection({ request: { request_id: 'request', thread_id: 'thread', uid: 'uid', agent_slug: 'health-consultation', status: 'dispatched', dispatched_run_id: 'run', run_id: 'wrong', private_input: 'secret' } }, expected).run_id, 'run')
  assert.throws(() => requestProjection({ request: { request_id: 'request', thread_id: 'thread', uid: 'other', agent_slug: 'health-consultation', status: 'queued' } }, expected))
})

test('运行投影保留现有状态，active null不自行推断撤权', () => {
  const run = { id: 'run', request_id: 'request', conversation_thread_id: 'thread', agent_slug: 'health-consultation', status: 'interrupted', input_payload: '私有', run_type: 'chat' }
  assert.deepEqual(runProjection({ run }, expected), { run_id: 'run', request_id: 'request', status: 'interrupted' })
  assert.equal(activeRunProjection({ run: null }, 'thread'), null)
  assert.throws(() => activeRunProjection({ run: { ...run, conversation_thread_id: 'other' } }, 'thread'))
  assert.throws(() => runProjection({ run: { ...run, created_by_run_id: 'parent' } }, expected))
  assert.throws(() => runProjection({ run: { ...run, run_type: 'resume' } }, expected))
})
