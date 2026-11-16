import type { PosterDraft } from './referral-poster'

/** 背景来自图片模型，文案与真实活动码始终在浏览器内排版。 */
export async function promotionPoster(art: Blob, qr: Blob, draft: PosterDraft): Promise<Blob> {
  const background = await createImageBitmap(art)
  let code: ImageBitmap | undefined
  try {
    code = await createImageBitmap(qr)
    await document.fonts.ready
    const canvas = document.createElement('canvas'); canvas.width = 1080; canvas.height = 1440
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('当前浏览器无法生成海报，请下载活动码')
    const palettes = { editorial: ['#fff8ef', '#213d37', '#d85536'], playful: ['#f1f8ed', '#294f43', '#c66135'], minimal: ['#eff6ff', '#183c70', '#2665dd'] }
    const [paper, ink, accent] = palettes[draft.style]!
    const font = '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif'
    ctx.fillStyle = paper!; ctx.fillRect(0, 0, 1080, 1440)
    const scale = Math.max(1080 / background.width, 1360 / background.height)
    ctx.drawImage(background, (1080 - background.width * scale) / 2, (1360 - background.height * scale) / 2, background.width * scale, background.height * scale)
    const veil = ctx.createLinearGradient(0, 0, 0, 580)
    veil.addColorStop(0, paper!); veil.addColorStop(0.62, paper! + 'ed'); veil.addColorStop(1, paper! + '00')
    ctx.fillStyle = veil; ctx.fillRect(0, 0, 1080, 580)
    const foot = ctx.createLinearGradient(0, 980, 0, 1420)
    foot.addColorStop(0, paper! + '00'); foot.addColorStop(0.4, paper!); foot.addColorStop(1, paper!)
    ctx.fillStyle = foot; ctx.fillRect(0, 980, 1080, 460)
    ctx.fillStyle = accent!; ctx.fillRect(72, 69, 10, 30)
    ctx.fillStyle = ink!; ctx.font = `500 26px ${font}`; ctx.fillText('习题库  /  学习灵感', 102, 94)
    function wrap(text: string, width: number) {
      const output: string[] = []; let line = ''
      for (const char of text.trim()) {
        if (char === '\n') { output.push(line); line = ''; continue }
        if (line && ctx!.measureText(line + char).width > width) { output.push(line); line = '' }
        line += char
      }
      if (line) output.push(line)
      return output
    }
    function fit(text: string, width: number, maxHeight: number, initial: number, min: number, weight: number) {
      for (let size = initial; size >= min; size -= 2) {
        ctx!.font = `${weight} ${size}px ${font}`
        const lines = wrap(text, width), height = size * 1.35
        if (lines.length * height <= maxHeight) return { lines, height }
      }
      throw new Error('文案过长或换行过多，请精简后预览，文字不会被截断')
    }
    const headline = fit(draft.title, 936, 345, 84, 36, 700)
    ctx.fillStyle = ink!; ctx.textBaseline = 'top'
    headline.lines.forEach((line, i) => ctx.fillText(line, 72, 152 + i * headline.height))
    const ruleY = 172 + headline.lines.length * headline.height
    ctx.fillStyle = accent!; ctx.fillRect(76, ruleY, 72, 6)
    ctx.fillStyle = '#ffffff'; ctx.beginPath(); ctx.roundRect(56, 1062, 968, 310, 30); ctx.fill()
    ctx.fillStyle = ink!; ctx.font = `700 32px ${font}`
    ctx.fillText('把好奇心，变成每天的进步', 92, 1100)
    const body = fit(draft.caption, 594, 186, 28, 20, 400)
    ctx.fillStyle = '#52615e'
    body.lines.forEach((line, i) => ctx.fillText(line, 92, 1160 + i * body.height))
    // 保留完整码图及周边白色净空；不裁切、不覆盖中心图标。
    const qrSize = 228, qrScale = Math.min(qrSize / code.width, qrSize / code.height)
    ctx.drawImage(code, 754 + (qrSize - code.width * qrScale) / 2, 1084 + (qrSize - code.height * qrScale) / 2, code.width * qrScale, code.height * qrScale)
    ctx.fillStyle = ink!; ctx.font = `500 22px ${font}`; ctx.textAlign = 'center'; ctx.fillText('微信扫码查看', 868, 1330)
    ctx.font = `20px ${font}`; ctx.fillStyle = '#66736b'
    ctx.fillText(draft.version === 'release' ? '学习资料 · 扫码进入小程序' : '体验 / 开发版 · 仅限获授权账号', 540, 1400)
    return await new Promise<Blob>((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('海报生成失败，请重试')), 'image/png'))
  } finally { background.close(); code?.close() }
}
