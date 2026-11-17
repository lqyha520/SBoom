export interface GenerationTrace {
  version: number
  source: string
  revision: string
  phase: string
  elapsed_ms: number
  stages: { stage: string; status: string; duration_ms: number }[]
  calls: { model: string; stage: string; status: string; duration_ms?: number; prompt_tokens: number | null; completion_tokens: number | null }[]
  rejections: { stage: string; reason: string; count: number }[]
  progress: { batch?: number; total_batches?: number; completed_questions?: number }
}

export const generationPhase: Record<string, string> = {
  preparing: '准备任务', generate: '生成题目', validate_refill: '检查与补题', refill: '补齐缺题',
  review: '生成解析与复核', succeeded: '已完成', failed: '失败', unknown: '等待确认',
}

export function traceProgress(trace?: GenerationTrace | null): string {
  if (!trace) return '处理中'
  const label = generationPhase[trace.phase] || '处理中'
  const progress = trace.progress
  return trace.phase === 'review' && progress.total_batches
    ? `${label} · 第 ${progress.batch}/${progress.total_batches} 批` : label
}
