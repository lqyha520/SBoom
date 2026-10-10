import { computed, toRaw, type ComputedRef } from 'vue'
import type { PaperSection } from './types'
import type { MeasuredSection } from './paper-pagination'

/** 每个大题独立追踪几何字段，标题变化不再序列化全卷题目。 */
export function createSectionSignatures() {
  const keys = new WeakMap<object, ComputedRef<string>>()
  return (section: PaperSection) => {
    const raw = toRaw(section)
    let signature = keys.get(raw)
    if (!signature) {
      signature = computed(() => JSON.stringify([
        section.type, section.name, section.data.passage, section.data.topic,
        (section.data.questions || []).map(q => [q._qid, q.type, q.stem, q._stemHtml, q.options, q._optsHtml,
          q.answer, q.left_items, q.right_items, q.top, q.left, q.right, q.left_expr,
          q.right_expr, q.difficulty_level]), section.layout,
      ]))
      keys.set(raw, signature)
    }
    return signature.value
  }
}

export function createSectionMeasurements() {
  let stored: { key: string; section: MeasuredSection }[] = []
  let context = ''
  return {
    dirty(keys: string[], nextContext: string) {
      return keys.flatMap((key, index) => context !== nextContext || stored[index]?.key !== key ? [index] : [])
    },
    commit(keys: string[], nextContext: string, updates: Map<number, MeasuredSection>) {
      stored = keys.map((key, index) => {
        const section = updates.get(index) || (context === nextContext && stored[index]?.key === key ? stored[index].section : undefined)
        if (!section) throw new Error('大题测量未完成')
        return { key, section }
      })
      context = nextContext
      return stored.map(item => item.section)
    },
  }
}
