import assert from 'node:assert/strict'
import test from 'node:test'
import { homeSelection, membershipExpiry, subjectTone } from '../src/presentation'
import { catalogFilters } from '../src/services/navigation'
import type { PaperSummary, User } from '../src/types'

function paper(id: string, featured = false): PaperSummary {
  return { id, featured, scope: 'catalog', source_id: '', version: 1, title: id, grade: '小学三年级', subject: '数学',
    can_view: true, can_download: true, required_view: 'free', required_download: 'free', view_access: 'inherit', download_access: 'inherit', question_types: ['quiz'],
    keyword: '', question_count: 10, folder_id: null, folder_name: null, group_id: '', group_name: '', favorite: false,
    file_status: 'ready', file_error: '', page_count: 2, created_at: 1, updated_at: 1, thumbnail_id: null, thumbnail_url: null }
}

test('home pairs wrap through actual results without duplicates or mutating the feed', () => {
  const papers = [paper('a'), paper('b'), paper('c')]
  assert.deepEqual(homeSelection([], 0), [])
  assert.deepEqual(homeSelection([papers[0]!], 3), [papers[0]])
  assert.deepEqual(homeSelection(papers, 0).map(item => item.id), ['a', 'b'])
  assert.deepEqual(homeSelection(papers, 2).map(item => item.id), ['c', 'a'])
  assert.deepEqual(homeSelection(papers, -1).map(item => item.id), ['c', 'a'])
  assert.deepEqual(homeSelection(papers, 6).map(item => item.id), ['a', 'b'])
  assert.deepEqual(papers.map(item => item.id), ['a', 'b', 'c'])
})

test('membership copy distinguishes ordinary, active, permanent and expired accounts', () => {
  const user: User = { id: 'user', username: 'reader', avatar: '', has_password: true, membership: 'regular', is_vip: false, vip_expires_at: null, membership_status: 'regular' }
  assert.equal(membershipExpiry(null), '未开通 VIP')
  assert.equal(membershipExpiry(user), '未开通 VIP')
  assert.equal(membershipExpiry({ ...user, membership: 'vip', membership_status: 'expired' }), '会员已到期')
  assert.equal(membershipExpiry({ ...user, is_vip: true, membership_status: 'active' }), '长期有效')
  const expiring = new Date(2026, 10, 2, 12).getTime() / 1000
  assert.equal(membershipExpiry({ ...user, is_vip: true, membership_status: 'active', vip_expires_at: expiring }), '2026-11-02 到期')
})

test('subject, grade and category entry points clear unrelated filters', () => {
  assert.deepEqual(catalogFilters({ subject: '英语' }), { q: '', grade: '', subject: '英语', category: '', topic: '' })
  assert.deepEqual(catalogFilters({ grade: '小学三年级' }), { q: '', grade: '小学三年级', subject: '', category: '', topic: '' })
  assert.deepEqual(catalogFilters({ category: '期末复习' }), { q: '', grade: '', subject: '', category: '期末复习', topic: '' })
  assert.deepEqual(catalogFilters(), { q: '', grade: '', subject: '', category: '', topic: '' })
  assert.deepEqual(catalogFilters({ topic: 'revision-week' }), { q: '', grade: '', subject: '', category: '', topic: 'revision-week' })
})

test('home search trims input and stays within the API query limit', () => {
  assert.equal(catalogFilters({ q: '  第一单元  ' }).q, '第一单元')
  assert.equal(catalogFilters({ q: 'a'.repeat(200) }).q.length, 120)
})

test('subject colors have a neutral fallback for new subjects', () => {
  assert.equal(subjectTone('语文'), 'language')
  assert.equal(subjectTone('数学'), 'math')
  assert.equal(subjectTone('英语'), 'english')
  assert.equal(subjectTone('科学'), 'general')
})
