import type { WorkspaceSnapshot } from './persistence'
import { deepClone } from './utils'
import { markRaw } from 'vue'
import { immutableCopy, sameSnapshot, snapshotSize } from './edit-snapshot'

export type EditSnapshot = Pick<WorkspaceSnapshot, 'sections' | 'papers' | 'title' | 'titleHtml' | 'style' | 'hiddenElements' | 'templateId' | 'customTemplate' | 'grade' | 'subject' | 'keyword' | 'selectedTags' | 'difficulty' | 'view' | 'paperCount' | 'addDayLabel'>
interface EditWorkspace extends EditSnapshot {
  generating: boolean
  accountChanged: boolean
  hasPendingEdits: boolean
  canUndo: boolean
  canRedo: boolean
  layoutMode: boolean
  undoStack: EditSnapshot[]
  redoStack: EditSnapshot[]
}

const editBursts = new WeakMap<object, { key: string; at: number }>()
const layouts = new WeakMap<object, { snapshot: EditSnapshot; undo: EditSnapshot[]; redo: EditSnapshot[] }>()

export function beginLayout(source: EditWorkspace) {
  if (source.layoutMode || source.generating || source.accountChanged || source.hasPendingEdits) return
  layouts.set(source, { snapshot: captureEdit(source), undo: [...source.undoStack], redo: [...source.redoStack] })
  recordEdit(source)
  source.layoutMode = true
}

export function finishLayout(source: EditWorkspace, cancel = false) {
  const previous = layouts.get(source)
  layouts.delete(source)
  editBursts.delete(source)
  if (cancel && previous) {
    Object.assign(source, deepClone(previous.snapshot))
    source.undoStack = previous.undo
    source.redoStack = previous.redo
  }
  source.layoutMode = false
}
export function captureEdit(source: EditSnapshot): EditSnapshot {
  return markRaw({ sections: immutableCopy(source.sections), papers: immutableCopy(source.papers), title: source.title, titleHtml: source.titleHtml,
    style: immutableCopy(source.style), hiddenElements: immutableCopy(source.hiddenElements), templateId: source.templateId, customTemplate: immutableCopy(source.customTemplate),
    grade: source.grade, subject: source.subject, keyword: source.keyword, selectedTags: immutableCopy(source.selectedTags),
    difficulty: source.difficulty, view: source.view, paperCount: source.paperCount, addDayLabel: source.addDayLabel })
}

export function recordEdit(source: EditWorkspace, key = '') {
  if (source.generating || source.accountChanged || source.hasPendingEdits || source.layoutMode) return
  const previous = editBursts.get(source), at = Date.now()
  editBursts.set(source, { key, at })
  if (key && previous?.key === key && at - previous.at < 500) return
  const snapshot = captureEdit(source)
  const previousSnapshot = source.undoStack[source.undoStack.length - 1]
  if (previousSnapshot && sameSnapshot(previousSnapshot, snapshot)) return
  source.undoStack.push(snapshot); source.redoStack = []
  while (source.undoStack.length > 20 || (source.undoStack.length > 1 && source.undoStack.reduce((size, item) => size + snapshotSize(item), 0) > 4_000_000)) source.undoStack.shift()
}

export function undoEdit(source: EditWorkspace) {
  if (!source.canUndo) return
  editBursts.delete(source)
  source.redoStack.push(captureEdit(source))
  Object.assign(source, deepClone(source.undoStack.pop()!))
}

export function redoEdit(source: EditWorkspace) {
  if (!source.canRedo) return
  editBursts.delete(source)
  source.undoStack.push(captureEdit(source))
  Object.assign(source, deepClone(source.redoStack.pop()!))
}
