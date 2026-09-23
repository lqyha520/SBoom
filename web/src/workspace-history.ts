import type { WorkspaceSnapshot } from './persistence'
import { deepClone } from './utils'

export type EditSnapshot = Pick<WorkspaceSnapshot, 'sections' | 'papers' | 'title' | 'titleHtml' | 'style' | 'hiddenElements' | 'templateId' | 'customTemplate'>
interface EditWorkspace extends EditSnapshot {
  generating: boolean
  accountChanged: boolean
  hasPendingEdits: boolean
  canUndo: boolean
  canRedo: boolean
  undoStack: EditSnapshot[]
  redoStack: EditSnapshot[]
}

const editBursts = new WeakMap<object, { key: string; at: number }>()
const snapshotEncoding = new WeakMap<object, string>()
function encodeSnapshot(snapshot: object): string {
  let value = snapshotEncoding.get(snapshot)
  if (value === undefined) { value = JSON.stringify(snapshot); snapshotEncoding.set(snapshot, value) }
  return value
}

export function captureEdit(source: EditSnapshot): EditSnapshot {
  return deepClone({ sections: source.sections, papers: source.papers, title: source.title, titleHtml: source.titleHtml,
    style: source.style, hiddenElements: source.hiddenElements, templateId: source.templateId, customTemplate: source.customTemplate })
}

export function recordEdit(source: EditWorkspace, key = '') {
  if (source.generating || source.accountChanged || source.hasPendingEdits) return
  const previous = editBursts.get(source), at = Date.now()
  editBursts.set(source, { key, at })
  if (key && previous?.key === key && at - previous.at < 500) return
  const snapshot = captureEdit(source)
  const encoded = encodeSnapshot(snapshot)
  const previousSnapshot = source.undoStack[source.undoStack.length - 1]
  if (previousSnapshot && encodeSnapshot(previousSnapshot) === encoded) return
  source.undoStack.push(snapshot); source.redoStack = []
  while (source.undoStack.length > 20 || source.undoStack.reduce((size, item) => size + encodeSnapshot(item).length + 1, 2) > 4_000_000) source.undoStack.shift()
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
