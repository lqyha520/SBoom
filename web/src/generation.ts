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
export class GenerationStopped extends Error { constructor() { super('已停止后续请求，可稍后继续') } }

export function createGenerationRun(context: GenerationContext): GenerationRun {
  const snapshot = deepClone(context)
  const items = snapshot.sections.map(section => ({ section_id: section.id, game_type: section.type,
    question_count: section.count - (section.lockedQuestions?.length || 0),
  })).filter(item => item.question_count > 0)
  return {
    context: snapshot,
    jobs: Array.from({ length: snapshot.count }, (_, index) => ({
      index,
      chunks: Array.from({ length: Math.ceil(items.length / 10) }, (_, chunk) => ({
        requestId: randomId(), state: 'new' as const,
        items: items.slice(chunk * 10, chunk * 10 + 10),
      })),
    })),
  }
}

function hasQuestions(result?: api.BatchRespSection[]): boolean {
  return !!result?.some(section => Array.isArray(section.questions) && section.questions.length)
}

async function runChunk(chunk: GenerationChunk, context: GenerationContext, mode: GenerationMode, beforeSend?: () => Promise<void>) {
  if (chunk.state === 'succeeded' && hasQuestions(chunk.result)) return
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
  try {
    await beforeSend?.()
    chunk.result = deepClone(await api.generateBatch({
      grade: context.grade, subject: context.subject, keyword: context.keyword,
      difficulty: context.difficulty, items: chunk.items,
    }, chunk.requestId))
    chunk.state = 'succeeded'
  } catch (error) {
    chunk.state = error instanceof GenerationStopped ? 'new' : error instanceof api.ApiError && error.status >= 400 && error.status < 500
      && error.code !== 'generation_pending' ? 'failed' : 'unknown'
    chunk.error = error instanceof Error ? error.message : '生成失败'
    throw error
  }
}

export function matchSectionResults(context: GenerationContext, responses: api.BatchRespSection[]) {
  const types = new Map<string, number>()
  context.sections.forEach(section => types.set(section.type, (types.get(section.type) || 0) + 1))
  return context.sections.map(section => {
    const exact = responses.filter(value => value.section_id === section.id)
    if (exact.length) return exact.length === 1 && exact[0].game_type === section.type ? exact[0] : undefined
    const legacy = responses.filter(value => !value.section_id && value.game_type === section.type)
    return types.get(section.type) === 1 && legacy.length === 1 ? legacy[0] : undefined
  })
}

export function assemblePaper(context: GenerationContext, job: GenerationJob): PaperData {
  const responses = job.chunks.flatMap(chunk => chunk.result || [])
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
    if (missing) warnings.push(`缺少 ${missing} 道题（请求 ${section.count} 道，实际 ${questions.length} 道）`)
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

export async function runGenerationJob(context: GenerationContext, job: GenerationJob, mode: GenerationMode, beforeSend?: () => Promise<void>) {
  for (const chunk of job.chunks) await runChunk(chunk, context, mode, beforeSend)
  return assemblePaper(context, job)
}
