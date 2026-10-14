/** 整卷、单大题和单题生成任务，以及原请求恢复。 */
import type { ExamWorkspace } from './exam-context'
import * as api from '../api'
import { deepClone } from '../utils'
import { questionKey } from '../question-quality'
import type { Difficulty, Question, Section } from '../types'
import {
  createGenerationRun,
  runGenerationJob,
  GenerationStopped,
  RequestNotRecorded,
  NoGenerationNeeded,
  type GenerationContext,
  type GenerationMode,
} from '../generation'

async function ensureRequestRecorded(store: ExamWorkspace) {
  if (store.accountChanged) throw new RequestNotRecorded()
  const owner = store.ownerId
  if (!store.persistenceReady || !store.ownerId || !await store.flushDraft()) throw new RequestNotRecorded()
  if (store.accountChanged || store.ownerId !== owner) throw new RequestNotRecorded()
}

function generationSections(sections: Section[]): GenerationContext['sections'] {
  return sections.map((section) => ({
    id: section.id,
    type: section.type,
    name: section.name,
    count: section.count,
    layout: deepClone(section.layout),
    lockedQuestions:
      section.data?.questions.flatMap((question, index) =>
        question._locked && index < section.count ? [{ index, question: deepClone(question) }] : [],
      ) || [],
  }))
}

function preserveQuestionEdits(questions: Question[], previous: Question[] = []): Question[] {
  const existing = new Map(previous.filter(question => question._qid).map(question => [question._qid, question]))
  return questions.map(question => deepClone(existing.get(question._qid) || question))
}

export const generationActions = {
  async replaceQuestion(this: ExamWorkspace, id: string, qid: string, paperIndex?: number) {
    if (this.generating || this.accountChanged) return
    const section = this.questionSection(id, paperIndex)
    const question = section?.data?.questions.find((item) => item._qid === qid)
    if (!section || !question || question._locked || section.type === 'reading') return
    const source = paperIndex === undefined ? this : this.papers[paperIndex]
    if (!source.grade || !source.subject || !source.keyword.trim()) throw new Error('请先填写年级、科目和知识点')
    const context: GenerationContext = {
      grade: source.grade,
      subject: source.subject,
      keyword: source.keyword,
      title: source.title,
      difficulty: source.difficulty as Difficulty,
      hiddenElements: [],
      count: 1,
      sections: [{ id, type: section.type, name: section.name, count: 1, layout: deepClone(section.layout) }],
    }
    const existing = question._replacement
    const run = existing || createGenerationRun(context)
    question._replacement = run
    this.generating = true
    try {
      const result = await runGenerationJob(run.context, run.jobs[0], existing ? 'retry' : 'send', async () => {
        if (this.accountChanged) throw new Error('账号已变化，未发送请求')
        await ensureRequestRecorded(this)
      })
      if (this.accountChanged) return
      const replacement = result.sections[0]?.data.questions[0]
      if (!replacement) throw new Error('没有生成可替换的题目，原题已保留')
      if (source.sections.some(candidate => candidate.data?.questions.some(item =>
        questionKey(item, candidate.data?.passage) === questionKey(replacement, section.data?.passage)))) {
        delete question._replacement
        throw new Error('新题与现有题目重复，原题已保留；可重新换题')
      }
      delete question._replacement
      this.generating = false
      this.recordEdit()
      const index = section.data!.questions.findIndex((item) => item._qid === qid)
      section.data!.questions[index] = { ...deepClone(replacement), _qid: qid }
    } finally {
      this.generating = false
      if (this.persistenceReady) await this.flushDraft()
      void this.refreshUsage()
    }
  },

  async refreshUsage(this: ExamWorkspace) {
    try {
      this.usage = await api.fetchGenerationUsage()
    } catch {
      this.usage = null
    }
  },

  async retrySection(this: ExamWorkspace, id: string, mode: 'retry' | 'recover' = 'retry') {
    if (this.generating || this.accountChanged) return
    const section = this.sections.find((value) => value.id === id)
    if (!section || !this.grade || !this.subject || !this.keyword.trim()) return
    const context: GenerationContext = {
      grade: this.grade,
      subject: this.subject,
      keyword: this.keyword,
      title: this.title,
      titleHtml: this.titleHtml,
      difficulty: this.difficulty,
      hiddenElements: [...this.hiddenElements],
      count: 1,
      sections: generationSections([section]),
    }
    const existing = section.pendingGeneration
    if (mode === 'recover' && !existing) {
      section.error = '没有可查询的原请求，未发送新请求'
      return
    }
    if (
      existing &&
      (existing.context.grade !== this.grade ||
        existing.context.subject !== this.subject ||
        existing.context.keyword !== this.keyword ||
        existing.context.sections[0].count !== section.count)
    ) {
      section.error = '原请求的条件已变化，请恢复原草稿或重新生成整卷'
      return
    }
    const run = existing || createGenerationRun(context)
    if (!run.jobs[0].chunks.length) {
      section.error = new NoGenerationNeeded().message
      section.status = 'error'
      return
    }
    section.pendingGeneration = run
    section.status = 'loading'
    section.error = ''
    this.generating = true
    try {
      const paper = await runGenerationJob(run.context, run.jobs[0], existing ? mode : 'send', async () => {
        if (this.accountChanged) throw new Error('账号已变化，未发送请求')
        await ensureRequestRecorded(this)
      })
      if (this.accountChanged) return
      const data = deepClone(paper.sections[0].data)
      data.questions = preserveQuestionEdits(data.questions, section.data?.questions)
      section.data = data
      section.warn = paper.sections[0].warn
      if (section.data.missing_count) {
        section.status = 'error'
        section.error = `缺少 ${section.data.missing_count} 道题，可手动补齐`
      } else {
        section.status = 'ready'
        delete section.pendingGeneration
      }
    } catch (error) {
      section.status = 'error'
      section.error = error instanceof Error ? error.message : '生成失败，未自动重试'
    } finally {
      this.generating = false
      if (this.persistenceReady) await this.flushDraft()
      void this.refreshUsage()
    }
  },

  async generate(this: ExamWorkspace) {
    if (!this.canGenerate) return
    this.generating = true
    try {
      if (
        (this.papers.length || this.pendingRun || this.sections.some((section) => section.pendingGeneration)) &&
        this.persistenceReady &&
        this.ownerId &&
        !(await this.saveHistory('before-generate'))
      )
        return
      if (this.accountChanged) return
      const context: GenerationContext = {
        grade: this.grade,
        subject: this.subject,
        keyword: this.keyword.trim(),
        title: this.title,
        titleHtml: this.titleHtml || undefined,
        difficulty: this.difficulty,
        hiddenElements: [...this.hiddenElements],
        count: Math.max(1, Math.min(20, Math.round(this.paperCount) || 1)),
        sections: generationSections(this.sections),
      }
      const run = createGenerationRun(context)
      // Each result paper has its own locks; preserve them for the corresponding next paper.
      run.jobs.forEach((job) => {
        const previous = this.papers.find((paper, index) => (paper.day || index + 1) === job.index + 1)
        if (
          !previous ||
          previous.grade !== context.grade ||
          previous.subject !== context.subject ||
          previous.keyword !== context.keyword
        )
          return
        const perPaper = deepClone(context)
        perPaper.sections.forEach((section) => {
          const old = previous.sections.find((item) => item._sid === section.id)
          if (old)
            section.lockedQuestions = old.data.questions.flatMap((question, index) =>
              question._locked && index < section.count ? [{ index, question: deepClone(question) }] : [],
            )
        })
        job.context = perPaper
        job.chunks = createGenerationRun({ ...perPaper, count: 1 }).jobs[0].chunks
      })
      if (run.jobs.some(job => !job.chunks.length)) {
        this.generateError = new NoGenerationNeeded().message
        return
      }
      this.undoStack = []
      this.redoStack = []
      this.pendingRun = run
      // 生成期间留在搭建页显示进度，取得可用试卷后再切换结果。
      this.view = 'build'
      this.papers = []
      this.failedCount = 0
    } finally {
      this.generating = false
    }
    await this.runPendingGeneration('send')
  },

  async runPendingGeneration(this: ExamWorkspace, mode: GenerationMode) {
    const run = this.pendingRun
    if (!run || this.generating || this.accountChanged) return
    this.generating = true
    this.stopRequested = false
    this.generateError = ''
    this.generateWarn = ''
    const pending = [...run.jobs]
    this.generationJobs = [...run.jobs]
    const completed = new Set<number>()
    const errors: string[] = []
    const total = pending.length
    let finished = 0
    let filled = false
    const prefix = mode === 'recover' ? '正在查询' : mode === 'retry' ? '正在补齐' : '正在生成'
    this.generateProgress = prefix + ' 0/' + total + ' 份'
    try {
      await Promise.all(
        // 按份串行，控制同一工作台的在途生成请求数量。
        Array.from({ length: Math.min(1, total) }, async () => {
          while (pending.length && !this.accountChanged && !this.stopRequested) {
            const job = pending.shift()!
            job.startedAt = Date.now()
            job.finishedAt = undefined
            job.error = ''
            try {
              const paper = await runGenerationJob(job.context || run.context, job, mode, async () => {
                if (this.accountChanged) throw new Error('账号已变化，未发送新请求')
                if (this.stopRequested) throw new GenerationStopped()
                await ensureRequestRecorded(this)
                if (this.accountChanged) throw new Error('账号已变化，未发送新请求')
                if (this.stopRequested) throw new GenerationStopped()
              })
              if (this.accountChanged) return
              const missing = paper.sections.reduce((sum, section) => sum + (section.data.missing_count || 0), 0)
              if (!missing) {
                completed.add(job.index)
                run.jobs = run.jobs.filter((value) => value.index !== job.index)
              } else {
                job.error = `缺少 ${missing} 道题，可手动补齐`
              }
              const existing = this.papers.findIndex(value => (value.day || 1) === job.index + 1)
              if (existing >= 0) {
                const previous = this.papers[existing]
                paper.sections.forEach(section => {
                  const old = previous.sections.find(value => value._sid === section._sid)
                  if (!old) return
                  section.data.questions = preserveQuestionEdits(section.data.questions, old.data.questions)
                  section.layout = deepClone(old.layout)
                  section.name = old.name
                })
                this.papers[existing] = { ...previous, sections: paper.sections }
              } else this.papers.push(paper)
              this.papers.sort((a, b) => (a.day || 1) - (b.day || 1))
              if (
                !filled &&
                this.grade === run.context.grade &&
                this.subject === run.context.subject &&
                this.keyword.trim() === run.context.keyword
              ) {
                filled = true
                paper.sections.forEach((result) => {
                  const section = this.sections.find((value) => value.id === result._sid)
                  if (!section) return
                  section.data = deepClone(result.data)
                  section.warn = result.warn
                  section.status = result.data.missing_count ? 'error' : 'ready'
                  section.error = result.data.missing_count ? `缺少 ${result.data.missing_count} 道题，可手动补齐` : ''
                })
              }
            } catch (error) {
              job.error = error instanceof Error ? error.message : '生成失败'
              errors.push(error instanceof Error ? error.message : '生成失败')
            }
            job.finishedAt = Date.now()
            finished++
            this.generateProgress = prefix + ' ' + finished + '/' + total + ' 份'
          }
        }),
      )
      if (this.accountChanged) return
      run.jobs = run.jobs.filter((job) => !completed.has(job.index))
      this.failedCount = run.jobs.length
      if (!run.jobs.length) this.pendingRun = null
      const warningCount = this.papers.reduce(
        (count, paper) => count + paper.sections.filter((section) => section.warn).length,
        0,
      )
      const warnings = []
      if (this.failedCount) warnings.push(this.failedCount + ' 份尚未完成，未自动重发；可查询原请求或手动补齐')
      if (warningCount) warnings.push(warningCount + ' 个大题有质量或缺题提示，请核对后使用')
      this.generateWarn = warnings.join('；')
      if (this.papers.length) {
        this.showAnswers = false
        this.view = 'result'
        if (completed.size) await this.saveHistory('generated')
      } else {
        this.generateError = errors[0] || '没有可用试卷'
      }
    } finally {
      this.generating = false
      this.generateProgress = ''
      if (this.persistenceReady) await this.flushDraft()
      void this.refreshUsage()
    }
  },

  async recoverPending(this: ExamWorkspace) {
    await this.runPendingGeneration('recover')
  },

  async retryFailed(this: ExamWorkspace) {
    await this.runPendingGeneration('retry')
  },

  async regenerate(this: ExamWorkspace) {
    await this.generate()
  },
}
