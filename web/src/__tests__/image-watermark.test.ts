import { expect, it } from 'vitest'
import { watermarkImage, watermarkText } from '../image-watermark'

it('保留多行文字并规范空白，限制每行长度和总行数', () => {
  expect(watermarkText('  王老师\r\n 数学课堂  ')).toBe('王老师\n数学课堂')
  expect(watermarkText('  王老师\t  课堂  ')).toBe('王老师 课堂')
  expect(watermarkText('字'.repeat(40))).toHaveLength(40)
  expect(watermarkText(Array(3).fill('字'.repeat(40)).join('\n')).split('\n')).toHaveLength(3)
  expect(() => watermarkText(' \t\n ')).toThrow('请填写水印文字')
  expect(() => watermarkText('字'.repeat(41))).toThrow('最多 40')
  expect(() => watermarkText('第一行\n第二行\n第三行\n第四行')).toThrow('最多 3 行')
})

it('关闭水印保留原始 Blob，取消和无效选项在处理图片前退出', async () => {
  const source = new Blob(['original'], { type: 'image/png' })
  expect(await watermarkImage(source)).toBe(source)
  await expect(watermarkImage(source, undefined, () => true)).rejects.toThrow('已停止导出')
  await expect(watermarkImage(source, { text: ' ', position: 'center' })).rejects.toThrow('请填写水印文字')
  await expect(watermarkImage(source, { text: '老师', position: 'unknown' as 'center' })).rejects.toThrow('水印位置')
  await expect(watermarkImage(source, { text: '老师', position: 'center', layout: 'unknown' as 'single' })).rejects.toThrow('水印布局')
  for (const opacity of [-0.1, 1.1, NaN, Infinity]) {
    await expect(watermarkImage(source, { text: '老师', position: 'center', opacity })).rejects.toThrow('透明度无效')
  }
})

it('完全透明时保留原始图片字节，依然响应取消', async () => {
  const source = new Blob(['original'], { type: 'image/png' })
  const watermark = { text: '第一行\n第二行', position: 'center' as const, layout: 'diagonal' as const, opacity: 0 }
  expect(await watermarkImage(source, watermark)).toBe(source)
  await expect(watermarkImage(source, watermark, () => true)).rejects.toThrow('已停止导出')
})
