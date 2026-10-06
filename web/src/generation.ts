import * as api from './api'
import type { Difficulty, GameData, PaperData, Question, Section } from './types'
import { deepClone, ensureQids } from './utils'
// crypto.randomUUID 是 [SecureContext] 限定 API，http://内网IP 下不存在
import { randomId } from '../../shared/webcrypto'

export interface GenerationContext {
  grade: string
  subject: string
  keyword: string
  title: string
  titleHtml?: string
  difficulty: Difficulty
  hiddenElements: string[]
  sections: (Pick<Section, 'id' | 'type' | 'name' | 'count' | 'layout'> & {
    lockedQuestions?: { index: number; question: Question }[]
  })[]
  count: number
}

export interface GenerationChunk {
  requestId: string
  items: api.BatchItemReq[]
  state: 'new' | 'running' | 'succeeded' | 'failed' | 'unknown'
  result?: api.BatchRespSection[]
  error?: string
  errorCode?: string
}

export interface GenerationJob {
  index: number
  chunks: GenerationChunk[]
  startedAt?: number
  finishedAt?: number
  error?: string
  context?: GenerationContext
}

export interface GenerationRun {
  context: GenerationContext
  jobs: GenerationJob[]
}

export type GenerationMode = 'send' | 'recover' | 'retry'
export class RequestNotRecorded extends Error { constructor() { super('请求记录保存失败，请先恢复本地存储；未发送付费请求') } }
export class GenerationStopped extends Error { constructor() { super('已停止后续请求，可稍后继续') } }

export function createGenerationRun(context: GenerationContext): GenerationRun {
  const snapshot = deepClone(context)
  const items = snapshot.sections.map(section => ({ section_id: section.id, game_type: section.type,
    question_count: section.count - (section.lockedQuestions?.length || 0),
  })).filter(item => item.question_count > 0)
  const groups: api.BatchItemReq[][] = []
  for (const item of items) {
    let group = groups[groups.length - 1]
    if (!group || group.length >= 10 || group.reduce((n, value) => n + value.question_count, 0) + item.question_count > 30) {
      group = []; groups.push(group)
    }
    group.push(item)
  }
  return {
    context: snapshot,
    jobs: Array.from({ length: snapshot.count }, (_, index) => ({
      index,
      chunks: groups.map(items => ({
        requestId: randomId(), state: 'new' as const,
        items: deepClone(items),
      })),
    })),
  }
}

function hasQuestions(result?: api.BatchRespSection[]): boolean {
  return !!result?.some(section => Array.isArray(section.questions) && section.questions.length)
}

function completedResults(chunk: GenerationChunk, values?: api.BatchRespSection[]): api.BatchRespSection[] {
  if (!Array.isArray(values)) return []
  return chunk.items.flatMap(item => {
    const matches = values.filter(value => value?.section_id === item.section_id)
    const value = matches[0]
    return matches.length === 1 && value.game_type === item.game_type
      && Array.isArray(value.questions) && value.questions.length === item.question_count
      && !value.missing_count && (item.game_type !== 'reading' || !!value.passage?.trim()) ? [deepClone(value)] : []
  })
}

function retainTruncated(chunk: GenerationChunk, values?: api.BatchRespSection[]) {
  chunk.result = completedResults(chunk, values)
  chunk.errorCode = 'generation_truncated'
  chunk.state = chunk.result.length === chunk.items.length ? 'succeeded' : 'failed'
}

async function runChunk(chunk: GenerationChunk, context: GenerationContext, mode: GenerationMode, beforeSend?: () => Promise<void>) {
  if (chunk.state === 'succeeded' && hasQuestions(chunk.result)) return
  if (chunk.errorCode === 'generation_truncated' && mode === 'retry') return
  if (mode !== 'send' && chunk.state !== 'new') {
    try {
      const status = await api.fetchGenerationStatus(chunk.requestId)
      if (status.status === 'running') {
        chunk.state = 'unknown'
        chunk.error = '原请求仍在处理中，请稍后查询结果'
        throw new Error(chunk.error)
      }
      if (status.result && Array.isArray(status.result.sections)) {
        chunk.result = deepClone(status.result.sections)
        chunk.state = 'succeeded'
        if (hasQuestions(chunk.result)) return
      }
      if (status.error?.code === 'generation_truncated') {
        retainTruncated(chunk, status.error.partial_sections)
        chunk.error = status.error.error || '生成达到输出上限，已保留完整大题，请手动补齐'
        if (chunk.state === 'succeeded' || mode === 'retry') return
      }
      if (mode === 'recover') {
        chunk.error = status.error?.error || (status.cache_expired ? '原请求结果缓存已过期' : '原请求没有可恢复的结果')
        throw new Error(chunk.error)
      }
    } catch (error) {
      if (!(error instanceof api.ApiError && error.status === 404)) throw error
      if (mode === 'recover') throw new Error('原请求未被服务端受理，可手动重试')
    }
  } else if (mode === 'recover') {
    throw new Error('该部分尚未发送，可手动重试')
  }
  if (mode === 'retry') chunk.requestId = randomId()
  chunk.state = 'running'
  chunk.error = ''
  chunk.errorCode = ''
  try {
    await beforeSend?.()
    chunk.result = deepClone(await api.generateBatch({
      grade: context.grade, subject: context.subject, keyword: context.keyword,
      difficulty: context.difficulty, items: chunk.items,
    }, chunk.requestId))
    chunk.state = 'succeeded'
  } catch (error) {
    if (error instanceof api.ApiError && error.code === 'generation_truncated') {
      retainTruncated(chunk, error.partialSections)
      chunk.error = error.message
      if (chunk.state === 'succeeded') return
      throw error
    }
    chunk.state = error instanceof GenerationStopped || error instanceof RequestNotRecorded ? 'new' : error instanceof api.ApiError && error.status >= 400 && error.status < 500
      && error.code !== 'generation_pending' ? 'failed' : 'unknown'
    chunk.errorCode = error instanceof api.ApiError ? error.code : ''
    chunk.error = error instanceof Error ? error.message : '生成失败'
    throw error
  }
}

export function matchSectionResults(context: GenerationContext, responses: api.BatchRespSection[]) {
  const types = new Map<string, number>()
  context.sections.forEach(section => types.set(section.type, (types.get(section.type) || 0) + 1))
  return context.sections.map(section => {
    const exact = responses.filter(value => value.section_id === section.id)
    if (exact.length) {
      if (exact.some(value => value.game_type !== section.type)) return undefined
      return exact.length === 1 ? exact[0] : undefined
    }
    const legacy = responses.filter(value => !value.section_id && value.game_type === section.type)
    return types.get(section.type) === 1 && legacy.length === 1 ? legacy[0] : undefined
  })
}

export function assemblePaper(context: GenerationContext, job: GenerationJob): PaperData {
  let responses = job.chunks.flatMap(chunk => chunk.result || [])
  // 只合并本地拆分到不同请求的大题；同一响应内的重复 ID 仍视为不明确。
  for (const section of context.sections) {
    const parts = job.chunks.filter(chunk => chunk.items.some(item => item.section_id === section.id))
    if (section.type === 'reading' || parts.length < 2) continue
    const results = parts.map(part => (part.result || []).filter(value => value.section_id === section.id))
    if (!results.every(values => values.length === 1 && values[0].game_type === section.type)) continue
    const values = results.map(value => value[0])
    responses = responses.filter(value => value.section_id !== section.id)
    responses.push({ ...values[0], questions: values.flatMap(value => value.questions || []),
      missing_count: values.reduce((sum, value) => sum + (value.missing_count || 0), 0),
      quality_warnings: values.flatMap(value => value.quality_warnings || []) })
  }
  const matched = matchSectionResults(context, responses)
  const sections = context.sections.map((section, index) => {
    const result = matched[index]
    const generated = Array.isArray(result?.questions) ? deepClone(result.questions) : []
    const locked = new Map(section.lockedQuestions?.map(item => [item.index, deepClone(item.question)]) || [])
    const questions: Question[] = []
    for (let index = 0; index < section.count; index++) {
      const question = locked.get(index) || generated.shift()
      if (question) questions.push(question)
    }
    const missing = Math.max(0, section.count - questions.length, result?.missing_count || 0)
    const warnings = [...(result?.quality_warnings || [])]
    if (missing && !warnings.some(warning => new RegExp(`缺少\\s*${missing}\\s*道`).test(warning))) {
      warnings.push(`缺少 ${missing} 道题（请求 ${section.count} 道，实际 ${questions.length} 道）`)
    }
    const data: GameData = { questions, passage: result?.passage, topic: result?.topic,
      missing_count: missing, quality_warnings: warnings }
    ensureQids(data)
    return { type: section.type, name: section.name, _sid: section.id, requestedCount: section.count,
      data, layout: deepClone(section.layout), warn: [...new Set(warnings)].join('；') }
  })
  if (!sections.some(section => section.data.questions.length)) throw new Error('没有可用题目，未创建空试卷；可查询原请求或手动重试')
  return {
    grade: context.grade, subject: context.subject, keyword: context.keyword,
    title: context.title, titleHtml: context.titleHtml, difficulty: context.difficulty,
    hiddenElements: [...context.hiddenElements], sections,
    day: context.count > 1 ? job.index + 1 : undefined,
  }
}

function splitTruncated(chunk: GenerationChunk): GenerationChunk[] {
  const result = completedResults(chunk, chunk.result)
  const completed = new Set(result.map(value => value.section_id))
  const pending = chunk.items.filter(item => !completed.has(item.section_id))
  const kept: GenerationChunk[] = result.length ? [{ ...chunk, state: 'succeeded', result,
    items: chunk.items.filter(item => completed.has(item.section_id)), error: '', errorCode: '' }] : []
  if (!pending.length) return kept
  const groups: api.BatchItemReq[][] = chunk.items.length > 1 ? pending.map(item => [item]) : []
  if (!groups.length) {
    const item = pending[0]
    if (item.question_count < 2 || item.game_type === 'reading') {
      throw new Error('这一部分已达到模型输出上限且无法继续拆分，请减少题量或请管理员提高输出上限后重新生成；已完成的结果仍保留')
    }
    const half = Math.ceil(item.question_count / 2)
    groups.push([{ ...item, question_count: half }], [{ ...item, question_count: item.question_count - half }])
  }
  return [...kept, ...groups.map(items => ({ requestId: randomId(), state: 'new' as const, items }))]
}

export async function runGenerationJob(context: GenerationContext, job: GenerationJob, mode: GenerationMode, beforeSend?: () => Promise<void>) {
  for (let index = 0; index < job.chunks.length; index++) {
    const chunk = job.chunks[index]
    await runChunk(chunk, context, mode, beforeSend)
    // 原请求查询也可能第一次发现截断；先保留完整结果，再准备新的小请求。
    if (mode === 'retry' && chunk.state !== 'succeeded' && chunk.errorCode === 'generation_truncated') {
      job.chunks.splice(index, 1, ...splitTruncated(chunk))
      index--
    }
  }
  return assemblePaper(context, job)
}
