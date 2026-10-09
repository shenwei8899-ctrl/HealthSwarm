import test from 'node:test'
import assert from 'node:assert/strict'
import { familyChoices, familyMemberChoices, eligibleHealthMembers, profileLinkSummary, basicProfileSummary } from '../src/ui/member-projection.js'

test('family rendering drops health fields and account-derived permission guesses', () => {
  const member = familyMemberChoices({ members: [{ id: 'source', name: '我', relationship: '本人', is_self: true, is_active: true, profile: { disease: 'private' }, subject_uid: 'private', ready: true }] })[0]
  assert.deepEqual(member, { id: 'source', name: '我', relationship: '本人', is_self: true, is_active: true })
  assert.deepEqual(familyChoices([{ id: 'family', name: '家', is_owner: 'true', health: 'private' }]), [{ id: 'family', name: '家', is_owner: false }])
})

test('health selection requires real ownership, self relationship and both scopes', () => {
  const self = { id: 'self', display_name: '我', is_owner: true, relationship_label: '本人', scopes: ['profile_view', 'profile_edit'] }
  const rows = [self, { ...self, id: 'other', relationship_label: '家人' }, { ...self, id: 'delegated', is_owner: false }, { ...self, id: 'readonly', scopes: ['profile_view'] }, { ...self, id: 'unreadable', scopes: ['profile_edit'] }, { ...self, id: 'string-owner', is_owner: 'true' }]
  assert.deepEqual(eligibleHealthMembers(rows), [{ id: 'self', display_name: '我' }])
})

test('empty or malformed API collections do not become demo candidates', () => {
  assert.deepEqual(familyChoices(null), [])
  assert.deepEqual(familyMemberChoices({ profile: {} }), [])
  assert.deepEqual(eligibleHealthMembers({ items: [] }), [])
})

test('mapping summary retains UUID facts and excludes profile text', () => {
  assert.deepEqual(profileLinkSummary({ member_id: 'health', source_member_id: 'source', family_id: 'family', profile: { private: true } }), { member_id: 'health', source_member_id: 'source', family_id: 'family', linked_at: null })
  assert.throws(() => profileLinkSummary({}), /成员关联/)
})

test('basic profile readiness never retains clinical or private profile fields', () => {
  assert.deepEqual(basicProfileSummary({ status: 'ready', code: 'self_confirmed_profile', profile_available: true, confirmed_version: 3, profile: { private: true }, nutrition_safety_ready: true }), { ready: true, description: '已确认的基础档案可读取', confirmed_version: 3 })
  assert.equal(basicProfileSummary({ status: 'not_ready', code: 'profile_unconfirmed', profile_available: false }).ready, false)
  assert.throws(() => basicProfileSummary(null), /基础档案状态/)
})
