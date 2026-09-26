import type { ExamState } from './exam-state'
import type { EditSnapshot } from '../workspace-history'
import type { WorkspaceSnapshot, HistoryReason } from '../persistence'
import type { GenerationMode } from '../generation'
import type { PaperSection, PaperStyle, Section } from '../types'

/** 各业务动作依赖的工作台接口；不反向导入 Pinia store，避免类型与运行时循环。 */
export interface ExamWorkspace extends ExamState {
  canGenerate: boolean
  canUndo: boolean
  canRedo: boolean
  hasPendingEdits: boolean
  recordEdit(key?: string): void
  editSnapshot(): EditSnapshot
  questionSection(id: string, paperIndex?: number): Section | PaperSection | undefined
  captureSnapshot(): WorkspaceSnapshot
  applySnapshot(snapshot: WorkspaceSnapshot): void
  initPersistence(): Promise<void>
  flushDraft(): Promise<boolean>
  refreshHistory(query?: string, offset?: number): Promise<void>
  saveHistory(reason?: HistoryReason): Promise<boolean>
  refreshUsage(): Promise<void>
  selectSubject(subject: string): Promise<void>
  persistTemplates(): boolean
  syncTemplate(name: string): Promise<boolean>
  syncTemplatesFromServer(): Promise<void>
  setStyle(patch: Partial<PaperStyle>): void
  setTemplate(id: string): void
  generate(): Promise<void>
  runPendingGeneration(mode: GenerationMode): Promise<void>
}
