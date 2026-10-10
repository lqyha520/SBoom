import type { ScopeData } from './types'

/** 只展示有教材来源的目录，旧 allowed/semesters 不能作为备用知识点。 */
export function textbookGroups(scope: ScopeData | null) {
  return (scope?.books || []).map(book => ({
    label: book.semester,
    items: book.units.flatMap(unit => [
      { label: unit.title, value: book.semester + '·' + unit.title },
      ...unit.topics.map(topic => ({ label: unit.title + ' / ' + topic, value: book.semester + '·' + unit.title + '·' + topic })),
    ]),
  }))
}
