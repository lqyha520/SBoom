import { expect, it } from 'vitest'
import { draftImages, exportDraft, materialPdf } from '../xhs-content-export'
import { newDraft, newMaterial } from '../xhs-workflow'

it('导出前明确定位学生卷缺失的题干，以及答案卷缺失的答案与讲解', async () => {
  const data = { ...newMaterial(), questions: [{ stem: '1+1=?', options: [], answer: '', analysis: '', quality_issues: [] }] }
  await expect(materialPdf(data, true)).rejects.toThrow('第 1 题的答案或讲解未补全')
  data.questions[0]!.stem = ' '
  await expect(materialPdf(data, false)).rejects.toThrow('第 1 题还没有题干')
})

it('空封面与空白内页在生成图片前给出明确错误', async () => {
  await expect(draftImages(newDraft())).rejects.toThrow('请先填写封面主标题或发布标题')
  await expect(draftImages({ ...newDraft(), headline: '练习资料', cards: [{ heading: ' ', body: '' }] })).rejects.toThrow('第 1 张内页没有内容')
})

it('缺少发布正文时不导出看似完整的素材压缩包', async () => {
  await expect(exportDraft({ ...newDraft(), headline: '练习资料' })).rejects.toThrow('请先补全发布标题和正文')
})
