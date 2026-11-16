import type { BaseData, DraftData, IdeaData, MaterialData, PublicationData, WorkflowRecord } from './xhs-workflow'
import { formatWorkflowDate } from './xhs-workflow'

export const workflowIcons = { ideas: 'i-lucide-lightbulb', materials: 'i-lucide-notebook-pen', drafts: 'i-lucide-panels-top-left', publications: 'i-lucide-calendar-days' }

export function workflowSummary(item: WorkflowRecord<BaseData>) {
  switch (item.kind) {
    case 'ideas': {
      const data = item.data as IdeaData
      return [data.grade, data.subject, data.keyword, data.format].filter(Boolean).join(' · ')
    }
    case 'materials': {
      const data = item.data as MaterialData
      return [data.grade, data.subject, data.questions?.length ? `${data.questions.length} 道题` : '题目待完善'].filter(Boolean).join(' · ')
    }
    case 'drafts': {
      const data = item.data as DraftData
      return [data.headline || data.cover_title, data.cards?.length ? `${data.cards.length} 张内页` : '内页待完善'].filter(Boolean).join(' · ')
    }
    case 'publications': {
      const data = item.data as PublicationData
      const time = data.published_at || data.scheduled_at
      return [data.account || '账号待填写', time ? `${data.published_at ? '发布于' : '计划于'} ${formatWorkflowDate(time)}` : '尚未排期'].join(' · ')
    }
  }
}
