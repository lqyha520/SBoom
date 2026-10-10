import { expect, it } from 'vitest'
import { textbookGroups } from '../knowledge-points'

it('不把旧 allowed 或 semesters 当作新目录的备用内容', () => {
  expect(textbookGroups(null)).toEqual([])
  expect(textbookGroups({ allowed: ['旧知识点'], semesters: { 上册: ['旧上册'], 下册: [] } })).toEqual([])
})

it('保留细分知识点所属的册次和单元', () => {
  const groups = textbookGroups({ allowed: ['旧知识点'], books: [{
    id: '1221001102241', semester: '下册', series: '人教版数学', source_url: 'https://book.pep.com.cn/1221001102241/',
    verified_on: '2026-10-10', units: [{ title: '认识平面图形', page: 1, topics: ['长方形', '圆'] }],
  }] })
  expect(groups).toEqual([{ label: '下册', items: [
    { label: '认识平面图形', value: '下册·认识平面图形' },
    { label: '认识平面图形 / 长方形', value: '下册·认识平面图形·长方形' },
    { label: '认识平面图形 / 圆', value: '下册·认识平面图形·圆' },
  ] }])
})
