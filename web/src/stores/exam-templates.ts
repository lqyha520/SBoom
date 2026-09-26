/** 个人模板的本地保存、服务端修订冲突和同步。 */
import type { ExamWorkspace } from './exam-context'
import * as api from '../api'
import { DEFAULT_LAYOUT, LS } from '../constants'
import type { MyTemplate } from '../types'
import { deepClone, mockQuestions, uid } from '../utils'
import { K, safeSet, migrateMyTemplates, applyOldSnapshot } from './exam-local'

function sameTemplate(a: MyTemplate, b: MyTemplate) {
  const content = ({ _revision, _syncState, _syncError, ...rest }: MyTemplate) => rest
  return JSON.stringify(content(a)) === JSON.stringify(content(b))
}

export const templatesActions = {
  persistTemplates(this: ExamWorkspace): boolean {
    const saved = safeSet(K(this.ownerId, LS.myTemplates), JSON.stringify(this.myTemplates))
    if (!saved) this.storageError = '模板本地保存失败，请检查浏览器存储空间'
    return saved
  },

  async syncTemplate(this: ExamWorkspace, name: string): Promise<boolean> {
    if (this.templateBusy.includes(name) || this.accountChanged) return false
    const template = this.myTemplates.find((value) => value.name === name)
    if (!template || template._syncState === 'conflict') return false
    const sent = deepClone(template)
    this.templateBusy.push(name)
    try {
      const revision = await api.upsertTemplate(sent)
      if (this.accountChanged) return false
      const current = this.myTemplates.find((value) => value.name === name)
      if (current) {
        const unchanged = sameTemplate(current, sent)
        current._revision = revision
        current._syncState = unchanged ? 'synced' : 'pending'
        current._syncError = ''
        this.persistTemplates()
      }
      return true
    } catch (error) {
      const current = this.myTemplates.find((value) => value.name === name)
      if (current) {
        current._syncState = error instanceof api.ApiError && error.status === 409 ? 'conflict' : 'pending'
        current._syncError = error instanceof Error ? error.message : '同步失败'
        this.persistTemplates()
      }
      return false
    } finally {
      this.templateBusy = this.templateBusy.filter((value) => value !== name)
    }
  },

  async syncTemplatesFromServer(this: ExamWorkspace) {
    if (this.templatesSyncing || this.accountChanged) return
    this.templatesSyncing = true
    try {
      const server = migrateMyTemplates(await api.fetchTemplates())
      if (this.accountChanged) return
      const local = new Map(this.myTemplates.map((template) => [template.name, template]))
      const merged = server.map((remote) => {
        const own = local.get(remote.name)
        local.delete(remote.name)
        if (!own || own._syncState === 'synced' || sameTemplate(own, remote))
          return { ...remote, _syncState: 'synced' as const }
        if ((own._revision || 0) !== remote._revision) {
          own._syncState = 'conflict'
          own._syncError = '服务端存在其他版本，本地修改已保留；请另存为新模板'
        }
        return own
      })
      for (const own of local.values()) {
        if (own._revision) {
          own._syncState = 'conflict'
          own._syncError = '服务端模板已删除，本地副本已保留'
        }
        merged.push(own)
      }
      this.myTemplates = merged
      this.persistTemplates()
      for (const template of this.myTemplates.filter((value) => value._syncState === 'pending'))
        await this.syncTemplate(template.name)
    } catch {
      /* Offline edits remain pending and visible. */
    } finally {
      this.templatesSyncing = false
    }
  },

  async saveMyTemplate(this: ExamWorkspace, name: string) {
    if (!name.trim() || name.length > 120 || this.accountChanged) return { local: false, synced: false }
    const existing = this.myTemplates.find((template) => template.name === name)
    const tpl: MyTemplate = {
      name,
      _revision: existing?._revision || 0,
      _syncState: existing?._syncState === 'conflict' ? 'conflict' : 'pending',
      _syncError: existing?._syncState === 'conflict' ? existing._syncError : '',
      grade: this.grade,
      subject: this.subject,
      keyword: this.keyword,
      title: this.title,
      titleHtml: this.titleHtml || undefined,
      difficulty: this.difficulty,
      templateId: this.templateId,
      style: { ...this.style },
      hiddenElements: [...this.hiddenElements],
      cards: this.sections.map((s) => ({ type: s.type, name: s.name, count: s.count, layout: { ...s.layout } })),
      // 完整数据：含每题编辑后的文字与富文本（加粗/字号/颜色），恢复时原样还原
      sections: deepClone(this.sections).map((s: any) => ({
        type: s.type,
        name: s.name,
        count: s.count,
        layout: s.layout,
        data: s.data,
      })),
    }
    const idx = this.myTemplates.findIndex((t) => t.name === name)
    if (idx >= 0) this.myTemplates[idx] = tpl
    else this.myTemplates.unshift(tpl)
    const local = this.persistTemplates()
    const synced = await this.syncTemplate(name)
    return { local, synced }
  },

  loadMyTemplate(this: ExamWorkspace, name: string): boolean {
    if (this.generating || this.accountChanged) return false
    const tpl = this.myTemplates.find((t) => t.name === name)
    if (!tpl) return false
    if (!tpl.cards.length && !tpl.sections?.length) return false
    this.grade = tpl.grade
    this.subject = tpl.subject
    this.keyword = tpl.keyword
    this.selectedTags = []
    this.difficulty = tpl.difficulty
    this.templateId = tpl.templateId
    this.title = tpl.title || ''
    this.titleHtml = (tpl as any).titleHtml || ''
    if (tpl.style) this.setStyle(tpl.style)
    this.hiddenElements = [...(tpl.hiddenElements || [])]

    if (tpl.sections?.length) {
      // V2：完整还原（每题文字、版式、数量都在）
      this.sections = deepClone(tpl.sections).map((s: any) => ({
        id: uid('s'),
        type: s.type,
        name: s.name,
        count: s.count,
        status: 'ready' as const,
        data: s.data,
        layout: { ...DEFAULT_LAYOUT, ...s.layout },
      }))
    } else {
      // 旧格式：mock 占位 + 快照文字回填
      const cards = tpl.cards.map((c) => ({
        type: c.type,
        name: (c as any).name,
        count: c.count,
        data: { questions: mockQuestions(c.type, c.count) },
        layout: { ...DEFAULT_LAYOUT, ...c.layout },
      }))
      if (tpl.paperSnapshot) applyOldSnapshot(cards, tpl.paperSnapshot)
      this.sections = cards.map((c) => ({
        id: uid('s'),
        type: c.type,
        name: c.name,
        count: c.count,
        status: 'ready' as const,
        data: c.data,
        layout: c.layout,
      }))
    }
    this.selectSubject(tpl.subject)
    return true
  },

  async deleteMyTemplate(this: ExamWorkspace, name: string) {
    if (this.accountChanged || this.templateBusy.includes(name)) throw new Error('模板正在同步，请稍后再试')
    const template = this.myTemplates.find((value) => value.name === name)
    if (!template) return
    let revision = template._revision || 0
    if (!revision) {
      const remote = (await api.fetchTemplates()).find((value) => value.name === name)
      if (remote) {
        if (!sameTemplate(template, migrateMyTemplates([remote])[0]))
          throw new Error('服务端存在同名的其他版本，未删除任何数据')
        revision = remote._revision || 0
      }
    }
    if (revision) await api.deleteTemplateOnServer(name, revision)
    if (this.accountChanged) return
    this.myTemplates = this.myTemplates.filter((template) => template.name !== name)
    this.persistTemplates()
  },

  async copyMyTemplate(this: ExamWorkspace, name: string, newName: string): Promise<boolean> {
    const original = this.myTemplates.find((template) => template.name === name)
    if (!original || !newName.trim() || newName.length > 120 || this.accountChanged) return false
    if (this.myTemplates.some((template) => template.name === newName.trim()))
      throw new Error('已有同名模板，请更换名称')
    this.myTemplates.unshift({
      ...deepClone(original),
      name: newName.trim(),
      _revision: 0,
      _syncState: 'pending',
      _syncError: '',
    })
    const local = this.persistTemplates()
    const synced = await this.syncTemplate(newName.trim())
    return local || synced
  },
}
