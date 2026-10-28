import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveLoginRedirect } from '../../src/utils/oidcAutoStart.js'

test('登录目标保留业务路径、查询参数和锚点', () => {
  for (const target of [
    '/agent',
    '/family?tab=profiles',
    '/extensions/knowledgebase/kb_1#knowledge'
  ]) {
    assert.equal(resolveLoginRedirect(target), target)
  }
})

test('缺省、站外和认证页面目标统一回到业务入口，避免成功后仍停留登录页', () => {
  for (const target of [
    undefined,
    null,
    '',
    '/',
    '/?redirect=/login',
    'https://example.com/',
    '//example.com/',
    '/\\example.com/',
    ['family'],
    '/login',
    '/Login',
    '/LOGIN?redirect=/family',
    '/AUTH/OIDC/CALLBACK',
    '/login?redirect=/family',
    '/login/#form',
    '/auth/oidc/callback',
    '/auth/oidc/callback?code=expired'
  ]) {
    assert.equal(resolveLoginRedirect(target), '/agent', `目标 ${String(target)}`)
  }
})
