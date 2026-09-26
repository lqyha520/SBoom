/** 测量后的行高转为页段；纯计算模块，不依赖浏览器布局。 */
export interface PageChunk {
  sec: number
  qFrom: number
  qTo: number
  first: boolean
}
export interface MeasuredSection {
  sec: number
  total: number
  headBlockH: number
  rows: number[]
  rowStride: number
}

export function paginateSections(segments: MeasuredSection[], capacity: number, tailHeight: number): PageChunk[][] {
  const pages: PageChunk[][] = []
  let page: PageChunk[] = [],
    used = 0
  const push = () => {
    if (page.length) pages.push(page)
    page = []
    used = 0
  }
  const height = (chunk: PageChunk) => {
    const segment = segments.find((value) => value.sec === chunk.sec)!
    return (
      (chunk.first ? segment.headBlockH : 0) +
      segment.rows
        .slice(Math.floor(chunk.qFrom / segment.rowStride), Math.ceil(chunk.qTo / segment.rowStride))
        .reduce((sum, row) => sum + row, 0)
    )
  }
  for (const segment of segments) {
    const whole = segment.headBlockH + segment.rows.reduce((sum, row) => sum + row, 0)
    if (used + whole <= capacity || !segment.total) {
      if (used + whole > capacity) push()
      page.push({ sec: segment.sec, qFrom: 0, qTo: segment.total, first: true })
      used += whole
      continue
    }
    let from = 0
    while (from < segment.total) {
      const first = from === 0,
        heading = first ? segment.headBlockH : 0
      const firstRow = segment.rows[Math.floor(from / segment.rowStride)] || 0
      if (page.length && used + heading + firstRow > capacity) push()
      let amount = heading,
        to = from
      while (to < segment.total) {
        const row = segment.rows[Math.floor(to / segment.rowStride)] || 0
        if (to > from && used + amount + row > capacity) break
        amount += row
        to = Math.min(segment.total, to + segment.rowStride)
        if (used + amount > capacity) break
      }
      page.push({ sec: segment.sec, qFrom: from, qTo: to, first })
      used += amount
      from = to
      if (from < segment.total) push()
    }
  }
  push()
  if (!pages.length) return [[]]

  // 从真实末页重新计算，避免清空临时页之后丢失 used；单大题也需要为卷尾腾位置。
  const last = pages[pages.length - 1]
  if (last.reduce((sum, chunk) => sum + height(chunk), 0) + tailHeight <= capacity) return pages
  const chunk = last[last.length - 1]
  if (last.length > 1 && height(chunk) + tailHeight <= capacity) {
    last.pop()
    pages.push([chunk])
    return pages
  }
  const segment = segments.find((value) => value.sec === chunk.sec)!
  const finalRow = Math.floor((chunk.qTo - 1) / segment.rowStride) * segment.rowStride
  if (finalRow > chunk.qFrom && (segment.rows[segment.rows.length - 1] || 0) + tailHeight <= capacity) {
    const end = chunk.qTo
    chunk.qTo = finalRow
    pages.push([{ sec: chunk.sec, qFrom: finalRow, qTo: end, first: false }])
  } else {
    // 一行无法与卷尾共页时，让卷尾独占末页，绝不直接裁掉。
    pages.push([])
  }
  return pages
}
