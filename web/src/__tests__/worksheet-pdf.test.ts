import { expect, it } from 'vitest'
import { buildWorksheetPdf } from '../worksheet-pdf'
import type { WorksheetImage } from '../image-generation'

// Actual PNGs, so PDF assembly and image decoding run without canvas/PDF mocks.
const tall = 'iVBORw0KGgoAAAANSUhEUgAAABgAAAAgCAIAAACHPC9vAAAAMElEQVR4nO3QMQEAAAiEwNf+nTUCi4MDF4CBmtzoo04MMR8xHzEfMR8xHzEfsX+PFkOXAT/05ckTAAAAAElFTkSuQmCC'
const wide = 'iVBORw0KGgoAAAANSUhEUgAAACAAAAAYCAIAAAAUMWhjAAAAM0lEQVR4nO3RwQ0AMAjDwJT9d6YjmE9+vgGCZF6yaZrqejxw4A+QiZCJkImQiZCJUD3RB+/KAS9SCGTbAAAAAElFTkSuQmCC'
const image = (b64_json = tall): WorksheetImage => ({ request_id: 'test', b64_json, mime_type: 'image/png', width: 24, height: 32, prompt: 'offline fixture' })

it('exports exactly one page per image, in source order, using actual portrait/landscape dimensions', async () => {
  const done: number[] = []
  const blob = await buildWorksheetPdf([image(), image(wide), image()], count => done.push(count))
  expect(blob.type).toBe('application/pdf')
  const text = await blob.text()
  expect(text.startsWith('%PDF-')).toBe(true)
  expect(text.match(/\/Type \/Page\b/g)).toHaveLength(3)
  const boxes = [...text.matchAll(/\/MediaBox \[([^\]]+)\]/g)].map(match => match[1].split(' ').map(Number))
  expect(boxes.map(box => box[2] > box[3])).toEqual([false, true, false])
  expect(done).toEqual([1, 2, 3])
})

it('supports an older single image without adding a blank page', async () => {
  const text = await (await buildWorksheetPdf([image()])).text()
  expect(text.match(/\/Type \/Page\b/g)).toHaveLength(1)
})

it('rejects empty, oversized or broken image groups and never returns a partial PDF after cancellation', async () => {
  await expect(buildWorksheetPdf([])).rejects.toThrow('1 至 10')
  await expect(buildWorksheetPdf(Array.from({ length: 11 }, () => image()))).rejects.toThrow('1 至 10')
  await expect(buildWorksheetPdf([image(btoa('broken'))])).rejects.toThrow()
  let cancelled = false
  await expect(buildWorksheetPdf([image(), image(wide)], () => { cancelled = true }, () => cancelled)).rejects.toThrow('已停止导出')
})
