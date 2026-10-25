import type { GameData, Question } from './types'

/**
 * 搭建阶段使用的卷面格式示例。
 *
 * 这些题目只存在于预览快照中，不能写入 store，也不能作为正式试题导出。
 */
export function previewSampleData(type: string, count: number, sectionId = 'section'): GameData {
  // 搭建预览要和题量控件一致；正式生成仍使用 store 中的 count。
  const sampleCount = Math.max(1, Math.min(30, Math.round(count || 1)))
  const questions = Array.from({ length: sampleCount }, (_, index) => sampleQuestion(type, index, sectionId))
  const data: GameData = { questions }
  if (type === 'reading') data.passage = '春天来了，校园里的花儿陆续开放。小朋友们来到操场，感受着温暖的阳光。'
  return data
}

function sampleQuestion(type: string, index: number, sectionId: string): Question {
  const suffix = index + 1
  const qid = `preview-${sectionId}-${suffix}`
  const samples: Record<string, Question> = {
    quiz: {
      type: 'quiz',
      stem: '下面哪个数是偶数？',
      options: ['12', '15', '19', '23'],
      answer: 0,
    },
    fill_blank: {
      type: 'fill_blank',
      stem: '56 + 27 =',
      answer: '83',
    },
    true_false: {
      type: 'true_false',
      stem: '一个三角形的内角和是180度。',
      answer: '正确',
    },
    match_pair: {
      type: 'match_pair',
      left_items: ['春天', '夏天', '秋天'],
      right_items: ['荷花盛开', '大雁南飞', '百花盛开'],
      answer: [[0, 2], [1, 0], [2, 1]],
    },
    oral_math: {
      type: 'oral_math',
      stem: '24 ÷ 6 =',
      answer: '4',
    },
    vertical_calc: {
      type: 'vertical_calc',
      stem: '326 + 147 = ____',
      answer: '473',
    },
    recursive_calc: {
      type: 'recursive_calc',
      stem: '48 ÷ 6 × 5 = ____',
      answer: '40',
    },
    smart_calc: {
      type: 'smart_calc',
      stem: '25 × 4 = ____',
      answer: '100',
    },
    number_split: {
      type: 'number_split',
      top: 10,
      left: 6,
      right: 4,
      answer: '6和4',
    },
    compare: {
      type: 'compare',
      left_expr: '3/4',
      right_expr: '2/3',
      answer: '>',
    },
    word_problem: {
      type: 'word_problem',
      stem: '小明有24本书，又买来8本，现在一共有多少本？',
      answer: '32本',
    },
    challenge: {
      type: 'challenge',
      stem: '找规律填数：2，4，6，____。',
      options: ['7', '8', '9', '10'],
      answer: 1,
    },
    reading: {
      type: 'quiz',
      stem: '短文中写到了什么季节？',
      options: ['春天', '夏天', '秋天', '冬天'],
      answer: 0,
    },
  }
  const question = { ...(samples[type] || {
    type,
    stem: '请根据所学知识完成这道题。',
  }) }
  question._qid = qid
  question._preview = true
  return question
}

/**
 * 大题已有正式题目但题数更高时，预览按题数补齐待生成占位。
 *
 * 占位同样带 _preview 标记，只服务卷面预览，不参与排版回写。
 */
export function previewPendingSamples(type: string, count: number, sectionId = 'section', filled = 0): Question[] {
  return previewSampleData(type, count, sectionId).questions.slice(Math.max(0, filled))
}
