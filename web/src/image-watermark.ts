export const MAX_WATERMARK_LINE_LENGTH = 40
export const MAX_WATERMARK_LINES = 3
export const MAX_WATERMARK_TEXT_LENGTH = MAX_WATERMARK_LINE_LENGTH * MAX_WATERMARK_LINES + MAX_WATERMARK_LINES - 1
export const DEFAULT_WATERMARK_TRANSPARENCY = 45

export const WATERMARK_POSITIONS = [
  { value: 'bottom-right', label: '右下角' },
  { value: 'bottom-left', label: '左下角' },
  { value: 'top-right', label: '右上角' },
  { value: 'top-left', label: '左上角' },
  { value: 'center', label: '居中' },
] as const
export type WatermarkPosition = typeof WATERMARK_POSITIONS[number]['value']
export const WATERMARK_LAYOUTS = [
  { value: 'single', label: '单处文字' },
  { value: 'tiled', label: '整图平铺' },
  { value: 'diagonal', label: '斜向平铺' },
] as const
export type WatermarkLayout = typeof WATERMARK_LAYOUTS[number]['value']
export interface ImageWatermark {
  text: string
  position: WatermarkPosition
  layout?: WatermarkLayout
  opacity?: number
}

export function watermarkText(value: string): string {
  const text = value.replace(/\r\n?/gu, '\n').split('\n').map(line => line.replace(/\s+/gu, ' ').trim()).join('\n').trim()
  if (!text) throw new Error('请填写水印文字')
  const lines = text.split('\n')
  if (lines.length > MAX_WATERMARK_LINES) throw new Error(`水印文字最多 ${MAX_WATERMARK_LINES} 行`)
  if (lines.some(line => line.length > MAX_WATERMARK_LINE_LENGTH)) throw new Error(`水印文字每行最多 ${MAX_WATERMARK_LINE_LENGTH} 个字符，请换行`)
  return text
}

/** 仅处理下载副本，保持原始尺寸；关闭水印时直接返回原图。 */
export async function watermarkImage(source: Blob, watermark?: ImageWatermark, cancelled: () => boolean = () => false): Promise<Blob> {
  const checkCancelled = () => { if (cancelled()) throw new Error('已停止导出') }
  checkCancelled()
  if (!watermark) return source
  const text = watermarkText(watermark.text)
  const position = watermark.position
  if (!WATERMARK_POSITIONS.some(item => item.value === position)) throw new Error('请选择有效的水印位置')
  const layout = watermark.layout ?? 'single', opacity = watermark.opacity ?? (100 - DEFAULT_WATERMARK_TRANSPARENCY) / 100
  if (!WATERMARK_LAYOUTS.some(item => item.value === layout)) throw new Error('请选择有效的水印布局')
  if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) throw new Error('水印透明度无效')
  if (opacity === 0) return source
  const lines = text.split('\n')
  const url = URL.createObjectURL(source)
  const image = new Image()
  let canvas: HTMLCanvasElement | undefined
  try {
    image.src = url
    try { await image.decode() } catch { throw new Error('图片无法读取，请重新获取图片后再添加水印') }
    checkCancelled()
    const width = image.naturalWidth, height = image.naturalHeight
    if (!(width > 0 && height > 0) || width * height > 16_000_000) throw new Error('图片尺寸无效')
    canvas = document.createElement('canvas')
    canvas.width = width; canvas.height = height
    const draw = canvas.getContext('2d')
    if (!draw) throw new Error('浏览器无法添加水印，请更换浏览器或关闭水印后下载')
    draw.drawImage(image, 0, 0)
    const edge = Math.min(width, height)
    const margin = edge * 0.025
    let size = edge * 0.032
    const font = () => `600 ${size}px "Microsoft YaHei", "PingFang SC", sans-serif`
    draw.font = font()
    const measuredWidth = Math.max(1, ...lines.map(line => draw.measureText(line).width))
    const maxWidth = layout === 'single' ? width * 0.8 : edge * 0.45
    size *= Math.min(1, maxWidth / measuredWidth)
    draw.font = font()
    const lineHeight = size * 1.4, blockHeight = size + (lines.length - 1) * lineHeight
    const blockWidth = Math.max(...lines.map(line => draw.measureText(line).width))
    draw.textBaseline = 'middle'
    draw.lineJoin = 'round'; draw.lineWidth = size * 0.16
    draw.globalAlpha = opacity
    draw.strokeStyle = '#fff'; draw.fillStyle = '#253044'
    const drawBlock = (x: number, y: number) => {
      lines.forEach((line, index) => {
        const baseline = y + (index - (lines.length - 1) / 2) * lineHeight
        draw.strokeText(line, x, baseline)
        draw.fillText(line, x, baseline)
      })
    }
    if (layout === 'single') {
      const center = position === 'center', left = position.endsWith('left'), top = position.startsWith('top')
      const x = center ? width / 2 : left ? margin : width - margin
      const y = center ? height / 2 : top ? margin + blockHeight / 2 : height - margin - blockHeight / 2
      draw.textAlign = center ? 'center' : left ? 'left' : 'right'
      drawBlock(x, y)
    } else {
      const angle = layout === 'diagonal' ? -Math.PI / 6 : 0
      const cos = Math.abs(Math.cos(angle)), sin = Math.abs(Math.sin(angle))
      const areaWidth = width * cos + height * sin, areaHeight = width * sin + height * cos
      // 覆盖旋转后的画布四角，同时限制极端长宽比图片的平铺次数。
      const stepX = Math.max(blockWidth + edge * 0.14, edge * 0.34, areaWidth / 12)
      const stepY = Math.max(blockHeight + edge * 0.1, edge * 0.2, areaHeight / 18)
      const columns = Math.ceil(areaWidth / stepX / 2), rows = Math.ceil(areaHeight / stepY / 2)
      draw.textAlign = 'center'
      draw.translate(width / 2, height / 2); draw.rotate(angle)
      for (let row = -rows; row <= rows; row++) {
        checkCancelled()
        for (let column = -columns; column <= columns; column++) drawBlock(column * stepX, row * stepY)
      }
    }
    const blob = await new Promise<Blob>((resolve, reject) => canvas!.toBlob(
      value => value ? resolve(value) : reject(new Error('添加水印失败，请重试')), 'image/png'))
    checkCancelled()
    return blob
  } finally {
    URL.revokeObjectURL(url)
    image.src = ''
    if (canvas) { canvas.width = 0; canvas.height = 0 }
  }
}
