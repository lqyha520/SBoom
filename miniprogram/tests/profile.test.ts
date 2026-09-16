import assert from 'node:assert/strict'
import test from 'node:test'
import { nicknameError, registrationAccountError } from '../../shared/mini-profile'
import { profileAvatar } from '../src/presentation'

test('WeChat display names accept single characters, spaces and emoji', () => {
  for (const value of ['一', '  王老师  ', '小明 😀', '👩‍🏫 王老师', '😀'.repeat(32)]) assert.equal(nicknameError(value), '', value)
  assert.equal(profileAvatar({ id: 'reader', username: 'login-id', nickname: '😀 小明', avatar: '' }).initial, '😀')
})

test('display names reject empty values, control characters and overlong Unicode text', () => {
  for (const value of ['', ' ', 'a\nb', 'a\u202eb', '😀'.repeat(33)]) assert.notEqual(nicknameError(value), '', JSON.stringify(value))
})

test('registration uses ASCII accounts while Chinese remains valid for display names', () => {
  for (const name of ['reader', 'wx1234567890', 'reader_2026-test', '  reader22  ']) assert.equal(registrationAccountError(name), '')
  for (const name of ['中文账号', 'reader小明', 'ｒｅａｄｅｒ', 'réader', 'x', 'a'.repeat(33)]) assert.notEqual(registrationAccountError(name), '')
  assert.equal(nicknameError('小海豚'), '')
})
