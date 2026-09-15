import assert from 'node:assert/strict'
import test from 'node:test'
import { AVATAR_CHOICES, avatarChoice, difficultyLabel, exerciseText, exerciseTitle, membershipBadge, profileAvatar, subjectOptions, subjectTagType } from '../src/presentation'
import type { User } from '../src/types'

test('legacy labels are presented as exercises without changing source records', () => {
  const paper = { title: '三年级数学试卷', description: '试卷库中的原卷预览', category: '同步试卷' }
  assert.equal(exerciseText(paper.title), '三年级数学习题')
  assert.equal(exerciseText(paper.description), '习题库中的原稿预览')
  assert.equal(exerciseText(paper.category), '同步习题')
  assert.equal(paper.title, '三年级数学试卷')
  assert.equal(exerciseText(undefined), '')
  assert.equal(exerciseText(null), '')
})

test('difficulty metadata uses Chinese labels and preserves custom values', () => {
  assert.equal(difficultyLabel('easy'), '基础')
  assert.equal(difficultyLabel('medium'), '进阶')
  assert.equal(difficultyLabel('hard'), '挑战')
  assert.equal(difficultyLabel('mixed'), '综合')
  assert.equal(difficultyLabel('巩固提升'), '巩固提升')
  assert.equal(difficultyLabel(undefined), '未标注')
})

test('titles omit only an exact grade and subject prefix already displayed as labels', () => {
  const paper = { title: '三年级数学 第一单元试卷', grade: '小学三年级', subject: '数学' }
  assert.equal(exerciseTitle(paper), '第一单元习题')
  assert.equal(paper.title, '三年级数学 第一单元试卷')
  assert.equal(exerciseTitle({ ...paper, title: '小学三年级数学 综合练习' }), '综合练习')
  assert.equal(exerciseTitle({ ...paper, title: '小学三年级数学 ' }), '小学三年级数学 ')
  assert.equal(exerciseTitle({ ...paper, title: '三年级数学家的故事' }), '三年级数学家的故事')
  assert.equal(exerciseTitle({ ...paper, title: '四年级数学 课后练习' }), '四年级数学 课后练习')
})

test('subject tabs are unique and ordered without losing new subjects', () => {
  const subjects = ['物理', '英语', '数学', '语文', '数学', '科学']
  assert.deepEqual(subjectOptions(subjects), ['语文', '数学', '英语', '物理', '科学'])
  assert.equal(subjects.length, 6)
  assert.equal(subjectTagType('语文'), 'volcano')
  assert.equal(subjectTagType('数学'), 'primary')
  assert.equal(subjectTagType('英语'), 'success')
  assert.equal(subjectTagType('科学'), 'warning')
})

test('membership badge stays short enough for the profile overview cell', () => {
  const day = (y: number, m: number, d: number) => Date.UTC(y, m - 1, d)
  const base: User = {
    id: 'u1', username: '认真的小鹿1234', avatar: '', has_password: true,
    membership: 'regular', is_vip: false,
    vip_expires_at: null, membership_status: 'regular',
  }
  assert.equal(membershipBadge(base, day(2026, 9, 15)), '未开通')
  assert.equal(membershipBadge({ ...base, membership_status: 'expired' }, day(2026, 9, 15)), '已到期')
  assert.equal(membershipBadge({ ...base, membership: 'vip', is_vip: true, membership_status: 'active' }, day(2026, 9, 15)), '长期')
  const vip = { ...base, membership: 'vip' as const, is_vip: true, membership_status: 'active' as const }
  assert.equal(membershipBadge({ ...vip, vip_expires_at: day(2026, 9, 25) / 1000 }, day(2026, 9, 15)), '10 天')
  assert.equal(membershipBadge({ ...vip, vip_expires_at: day(2026, 9, 15) / 1000 }, day(2026, 9, 15)), '已到期')
  assert.equal(membershipBadge(vip, day(2026, 9, 15)), '长期')
  assert.equal(membershipBadge(null), '未开通')
})

test('avatar presets are unique, complete and internally consistent', () => {
  const keys = AVATAR_CHOICES.map(choice => choice.key)
  assert.equal(new Set(keys).size, keys.length)
  assert.ok(keys.length >= 12)
  for (const choice of AVATAR_CHOICES) {
    assert.ok(choice.glyph && choice.label, choice.key)
    assert.match(choice.background, /^#[0-9a-f]{6}$/)
    assert.match(choice.color, /^#[0-9a-f]{6}$/)
    assert.equal(avatarChoice(choice.key), choice)
  }
  assert.equal(avatarChoice(''), null)
  assert.equal(avatarChoice('dragon'), null)
})

test('chosen avatars win over the id-derived fallback and stay stable per account', () => {
  const reader: User = {
    id: 'u1', username: '认真的小鹿1234', avatar: '', has_password: false,
    membership: 'regular', is_vip: false, vip_expires_at: null, membership_status: 'regular',
  }
  const preset = profileAvatar({ ...reader, avatar: 'fox' })
  assert.deepEqual(preset, {
    glyph: '🦊', initial: '认', background: avatarChoice('fox')!.background, color: avatarChoice('fox')!.color, preset: true,
  })
  // 没选头像：首字 + 由账号 id 派生的配色，同一账号重复调用保持一致
  const fallback = profileAvatar(reader)
  assert.equal(fallback.preset, false)
  assert.equal(fallback.glyph, '')
  assert.equal(fallback.initial, '认')
  assert.match(fallback.background, /^hsl\(\d+, 44%, 92%\)$/)
  assert.deepEqual(profileAvatar({ ...reader, id: 'u1' }), fallback)
  // 换一个 id（换个账号）配色就不同，避免所有新用户头像一个样
  assert.notEqual(profileAvatar({ ...reader, id: 'a-completely-different-id' }).background, fallback.background)
  // 未知头像键（例如旧版本前端写入的值）也回落到默认形象，不会白屏
  assert.equal(profileAvatar({ ...reader, avatar: 'dragon' }).preset, false)
  // 游客态：没有用户名也不会炸
  assert.deepEqual(profileAvatar(null), { glyph: '', initial: '', background: 'hsl(0, 44%, 92%)', color: 'hsl(0, 32%, 36%)', preset: false })
})
