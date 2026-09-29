import { expect, it } from 'vitest'
import { reactive, isReactive } from 'vue'
import { safeLibraryUrl } from '../library'
import { deepClone } from '../utils'
import { captureEdit } from '../workspace-history'
import { createPinia, setActivePinia } from 'pinia'
import { useExamStore } from '../stores/exam'

it('只允许同源试卷库下载地址', () => {
  expect(safeLibraryUrl('/api/v1/library/papers/1/files/2')).toContain('/api/v1/library/')
  for (const url of ['https://outside.test/api/v1/library/a', '//outside.test/api/v1/library/a', '/admin/', 'javascript:alert(1)', '/api/v1/library/../../auth/me']) expect(() => safeLibraryUrl(url)).toThrow('下载地址无效')
})
it('解包嵌套代理并保存原生 Date；撤销快照不会重新代理', () => {
  const source = reactive({ items: [{ count: 1 }], date: new Date('2026-01-01') })
  const clone = deepClone({ source })
  expect(clone.source.date).toBeInstanceOf(Date)
  clone.source.items[0].count = 2
  expect(source.items[0].count).toBe(1)
  setActivePinia(createPinia())
  const state = reactive({ snapshot: captureEdit(useExamStore()) })
  expect(isReactive(state.snapshot)).toBe(false)
})
