import { test } from 'node:test'
import assert from 'node:assert/strict'
import { authorizeLocalRequest } from './xhs-authorization.mjs'

test('无凭证或后台拒绝时不授权；超时及非 JSON 也拒绝', async () => {
  const input = { headers: {}, method: 'POST', url: '/accounts/add' }
  assert.equal(await authorizeLocalRequest(input, 'https://localhost', () => { throw new Error('不应请求') }), false)
  input.headers['x-admin-capability'] = 'fixture'
  for (const verify of [async () => new Response('{}', { status: 403 }), async () => new Response('oops'), async () => { throw new Error('timeout') }]) {
    assert.equal(await authorizeLocalRequest(input, 'https://localhost', verify), false)
  }
})

test('仅接受后台肯定答复，核验携带原始来源、方法与完整路径', async () => {
  const input = { headers: { 'x-admin-capability': 'proof' }, method: 'GET', url: '/publisher/state?account_id=abc' }
  let calls = 0
  assert.equal(await authorizeLocalRequest(input, 'https://localhost', async (url, options) => {
    calls++
    assert.equal(String(url), 'https://localhost/api/v1/local-access/verify')
    assert.equal(options.redirect, 'error')
    assert.deepEqual(JSON.parse(options.body), { token: 'proof', origin: 'https://localhost', path: input.url, method: 'GET' })
    return new Response('{"authorized":true}')
  }), true)
  assert.equal(calls, 1)
})
