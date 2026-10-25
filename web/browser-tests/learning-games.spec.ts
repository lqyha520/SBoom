import { expect, test, type Page } from '@playwright/test'
import { idiomById, type IdiomDifficulty } from '../src/games/idiom-fill'

const rocketKey = 'lc_game_rocket_math_v1_guest'
const memoryKey = 'lc_game_memory_match_v1_guest'
const fractionKey = 'lc_game_fraction_pizza_v1_guest'
const poemKey = 'lc_game_poem_order_v1_guest'
const idiomKey = 'lc_game_idiom_fill_v1_guest'
const spellKey = 'lc_game_word_spell_v1_guest'
const marketKey = 'lc_game_word_market_v1_guest'
const clockKey = 'lc_game_clock_town_v1_guest'

interface RocketView {
  flight: {
    index: number
    answered: number | null
    finished: boolean
    mistakes: number
    questions: Array<{ answer: number; options: number[] }>
  }
  best: Record<string, number>
  flights: number
}
interface MemoryView {
  difficulty: string
  round: { cards: Array<{ id: number; pairId: string }>; flipped: number[]; matched: string[]; moves: number; finished: boolean }
  best: Record<string, number>
}
interface FractionView {
  difficulty: string
  flight: { index: number; answered: string | null; finished: boolean; questions: Array<{ answer: string; options: string[] }> }
  best: Record<string, number>
  flights: number
}
interface PoemView {
  difficulty: string
  round: {
    index: number
    solved: boolean
    finished: boolean
    mistakes: number
    questions: Array<{ answer: string[]; tiles: Array<{ id: string; text: string }> }>
  }
  best: Record<string, number>
  totalPoems: number
  rounds: number
}
interface IdiomView {
  difficulty: IdiomDifficulty
  round: { index: number; answered: string | null; finished: boolean; questions: Array<{ idiomId: string; options: string[] }> }
  best: Record<string, number>
  rounds: number
}
interface SpellView {
  difficulty: string
  round: {
    index: number
    solved: boolean
    finished: boolean
    mistakes: number
    hints: number
    questions: Array<{ word: string; answer: string[]; tiles: Array<{ id: string; letter: string }> }>
  }
  best: Record<string, number>
  totalWords: number
  rounds: number
}
interface MarketView {
  difficulty: string
  round: { index: number; answered: string | null; finished: boolean; questions: Array<{ wordId: string; options: string[] }> }
  best: Record<string, number>
  rounds: number
}
interface ClockView {
  difficulty: string
  round: { index: number; answered: string | null; finished: boolean; questions: Array<{ answer: string; options: string[] }> }
  best: Record<string, number>
  rounds: number
}
async function getSave<T>(page: Page, key: string): Promise<T> {
  return page.evaluate(k => JSON.parse(localStorage.getItem(k)!), key) as Promise<T>
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}
async function activeNavFits(page: Page) {
  return page.evaluate(() => {
    const nav = document.querySelector('nav[aria-label="游戏导航"]')
    const current = nav?.querySelector('[aria-current="page"]')
    if (!nav || !current) return false
    const view = nav.getBoundingClientRect()
    const link = current.getBoundingClientRect()
    return link.left >= view.left - 1 && link.right <= view.right + 1
  })
}
function pairsOf(view: MemoryView) {
  const grouped = new Map<string, number[]>()
  for (const card of view.round.cards) grouped.set(card.pairId, [...(grouped.get(card.pairId) ?? []), card.id])
  return [...grouped.values()]
}

test('三款新游戏：火箭答题纠错、翻牌配对、披萨分数与刷新恢复', async ({ page }, info) => {
  test.setTimeout(90_000)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const errors: string[] = []
  const apiRequests: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (request.url().includes('/api/')) apiRequests.push(request.url()) })

  await page.goto('/#/games/rocket-math')
  await expect(page.getByRole('heading', { name: '口算火箭.' })).toBeVisible()
  await noOverflow(page)
  let rocket = await getSave<RocketView>(page, rocketKey)
  const wrong = rocket.flight.questions[0].options.find(value => value !== rocket.flight.questions[0].answer)!
  await page.getByRole('button', { name: `选择答案 ${wrong}`, exact: true }).click()
  await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('差一点点')
  await page.screenshot({ path: info.outputPath('rocket-math-flight.png'), fullPage: true })
  await page.reload()
  await expect(page.getByRole('heading', { name: '口算火箭.' })).toBeVisible()
  await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('差一点点')
  expect((await getSave<RocketView>(page, rocketKey)).flight.answered).toBe(wrong)
  await page.getByRole('button', { name: '下一题', exact: true }).click()
  for (let index = 1; index < 8; index++) {
    rocket = await getSave<RocketView>(page, rocketKey)
    const question = rocket.flight.questions[rocket.flight.index]
    await page.getByRole('button', { name: `选择答案 ${question.answer}`, exact: true }).click()
    await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('答对了')
    await page.getByRole('button', { name: index === 7 ? '查看飞行报告' : '下一题', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '顺利着陆，再练一次会更稳！' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('rocket-math-report.png'), fullPage: true })
  rocket = await getSave<RocketView>(page, rocketKey)
  expect(rocket.flight.finished).toBe(true)
  expect(rocket.best.starter).toBe(2)
  expect(rocket.flights).toBe(1)

  await page.getByRole('link', { name: '记忆翻牌', exact: true }).click()
  await expect(page.getByRole('heading', { name: '记忆翻牌.' })).toBeVisible()
  await noOverflow(page)
  const memory = await getSave<MemoryView>(page, memoryKey)
  const memoryPairs = pairsOf(memory)
  for (const [index, ids] of memoryPairs.entries()) {
    await page.locator(`.memory-card[data-card-id="${ids[0]}"]`).click()
    await page.locator(`.memory-card[data-card-id="${ids[1]}"]`).click()
    await expect.poll(async () => (await getSave<MemoryView>(page, memoryKey)).round.matched.length).toBe(index + 1)
  }
  await expect(page.getByRole('dialog')).toContainText('全部配对成功')
  await page.screenshot({ path: info.outputPath('memory-match-complete.png'), fullPage: true })
  const completedMemory = await getSave<MemoryView>(page, memoryKey)
  expect(completedMemory.round.finished).toBe(true)
  expect(completedMemory.round.moves).toBe(memoryPairs.length)
  expect(completedMemory.best.cozy).toBe(3)
  await page.getByRole('button', { name: '关闭完成提示', exact: true }).click()

  await page.getByRole('link', { name: '披萨分数', exact: true }).click()
  await expect(page.getByRole('heading', { name: '披萨分数.' })).toBeVisible()
  await noOverflow(page)
  for (let index = 0; index < 8; index++) {
    const fraction = await getSave<FractionView>(page, fractionKey)
    const question = fraction.flight.questions[fraction.flight.index]
    await page.locator(`.fraction-options button[data-fraction="${question.answer}"]`).click()
    await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('答对了')
    await page.getByRole('button', { name: index === 7 ? '查看披萨成绩单' : '下一盘披萨', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '满分披萨师傅，出炉！' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('fraction-pizza-report.png'), fullPage: true })
  const fraction = await getSave<FractionView>(page, fractionKey)
  expect(fraction.flight.finished).toBe(true)
  expect(fraction.best.starter).toBe(3)
  expect(fraction.flights).toBe(1)
  await page.reload()
  await expect(page.getByRole('heading', { name: '满分披萨师傅，出炉！' })).toBeVisible()
  expect(apiRequests).toEqual([])
  expect(errors).toEqual([])
})

test('语文新游戏：诗句排队、成语补字完整通关与刷新恢复', async ({ page }, info) => {
  test.setTimeout(120_000)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const errors: string[] = []
  const apiRequests: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (request.url().includes('/api/')) apiRequests.push(request.url()) })

  await page.goto('/#/games/poem-order')
  await expect(page.getByRole('heading', { name: '诗句排队.' })).toBeVisible()
  await noOverflow(page)
  for (let index = 0; index < 8; index++) {
    const poem = await getSave<PoemView>(page, poemKey)
    const question = poem.round.questions[poem.round.index]
    for (const id of question.answer) await page.locator(`.poem-tile[data-tile-id="${id}"]`).click()
    await expect(page.locator('.poem-slot.filled')).toHaveCount(4)
    await page.getByRole('button', { name: '排好了，读一读', exact: true }).click()
    const firstLine = question.tiles.find(tile => tile.id === question.answer[0])!.text
    await expect(page.getByRole('status', { name: '排序反馈' })).toContainText(firstLine)
    if (index === 0) {
      await page.screenshot({ path: info.outputPath('poem-order-solved.png'), fullPage: true })
      await page.reload()
      await expect(page.getByRole('heading', { name: '诗句排队.' })).toBeVisible()
      await expect(page.getByRole('status', { name: '排序反馈' })).toContainText(firstLine)
      expect((await getSave<PoemView>(page, poemKey)).round.solved).toBe(true)
    }
    await page.getByRole('button', { name: index === 7 ? '查看诗会成绩' : '下一首诗', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '一字不差，小诗人真棒！' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('poem-order-report.png'), fullPage: true })
  const poem = await getSave<PoemView>(page, poemKey)
  expect(poem.round.finished).toBe(true)
  expect(poem.best.starter).toBe(3)
  expect(poem.totalPoems).toBe(8)
  expect(poem.rounds).toBe(1)

  await page.getByRole('link', { name: '成语补字', exact: true }).click()
  await expect(page.getByRole('heading', { name: '成语补字.' })).toBeVisible()
  await noOverflow(page)
  for (let index = 0; index < 8; index++) {
    const idiom = await getSave<IdiomView>(page, idiomKey)
    const question = idiom.round.questions[idiom.round.index]
    const answer = idiomById(idiom.difficulty, question.idiomId)!.answer
    await page.getByRole('button', { name: `选择汉字 ${answer}`, exact: true }).click()
    await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('补对啦')
    await page.getByRole('button', { name: index === 7 ? '查看学习成果' : '下一个成语', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '字字准确，成语小达人！' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('idiom-fill-report.png'), fullPage: true })
  const idiom = await getSave<IdiomView>(page, idiomKey)
  expect(idiom.round.finished).toBe(true)
  expect(idiom.best.starter).toBe(3)
  expect(idiom.rounds).toBe(1)
  await page.reload()
  await expect(page.getByRole('heading', { name: '字字准确，成语小达人！' })).toBeVisible()
  expect(apiRequests).toEqual([])
  expect(errors).toEqual([])
})

test('英语与数学新游戏：拼写、集市、时钟完整通关与刷新恢复', async ({ page }, info) => {
  test.setTimeout(120_000)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const errors: string[] = []
  const apiRequests: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (request.url().includes('/api/')) apiRequests.push(request.url()) })

  await page.goto('/#/games/word-spell')
  await expect(page.getByRole('heading', { name: '单词拼写.' })).toBeVisible()
  await noOverflow(page)
  for (let index = 0; index < 8; index++) {
    const spell = await getSave<SpellView>(page, spellKey)
    const question = spell.round.questions[spell.round.index]
    for (const id of question.answer) await page.locator(`.letter-tile[data-tile-id="${id}"]`).click()
    await page.getByRole('button', { name: '检查拼写', exact: true }).click()
    await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('拼对啦')
    await page.getByRole('button', { name: index === 7 ? '查看拼词报告' : '下一个单词', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '字母排得整整齐齐，拼词小能手！' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('word-spell-report.png'), fullPage: true })
  const spell = await getSave<SpellView>(page, spellKey)
  expect(spell.round.finished).toBe(true)
  expect(spell.best.starter).toBe(3)
  expect(spell.totalWords).toBe(8)
  expect(spell.rounds).toBe(1)

  await page.getByRole('link', { name: '单词集市', exact: true }).click()
  await expect(page.getByRole('heading', { name: '单词集市.' })).toBeVisible()
  await noOverflow(page)
  for (let index = 0; index < 8; index++) {
    const market = await getSave<MarketView>(page, marketKey)
    const question = market.round.questions[market.round.index]
    await page.locator(`.word-option[data-word="${question.wordId}"]`).click()
    await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('找到啦')
    await page.getByRole('button', { name: index === 7 ? '查看集市成绩' : '下一个单词', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '单词全卖光，集市小老板真厉害！' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('word-market-report.png'), fullPage: true })
  const market = await getSave<MarketView>(page, marketKey)
  expect(market.round.finished).toBe(true)
  expect(market.best.starter).toBe(3)
  expect(market.rounds).toBe(1)

  await page.getByRole('link', { name: '时钟小镇', exact: true }).click()
  await expect(page.getByRole('heading', { name: '时钟小镇.' })).toBeVisible()
  await noOverflow(page)
  for (let index = 0; index < 8; index++) {
    const clock = await getSave<ClockView>(page, clockKey)
    const question = clock.round.questions[clock.round.index]
    await page.locator(`.time-options button[data-time="${question.answer}"]`).click()
    await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('读对啦')
    await page.getByRole('button', { name: index === 7 ? '查看读时成绩' : '下一个时间', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '时间读得又快又准，钟楼小主人！' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('clock-town-report.png'), fullPage: true })
  const clock = await getSave<ClockView>(page, clockKey)
  expect(clock.round.finished).toBe(true)
  expect(clock.best.starter).toBe(3)
  expect(clock.rounds).toBe(1)
  await page.reload()
  await expect(page.getByRole('heading', { name: '时间读得又快又准，钟楼小主人！' })).toBeVisible()
  expect(apiRequests).toEqual([])
  expect(errors).toEqual([])
})

test('新游戏：已登录用户刷新后仍写入账号存档', async ({ page }) => {
  await page.addInitScript(() => { try { localStorage.setItem('lc_uid', '4242') } catch { /* 忽略存储限制 */ } })
  const apiRequests: string[] = []
  page.on('request', request => { if (request.url().includes('/api/')) apiRequests.push(request.url()) })
  await page.goto('/#/games/clock-town')
  await expect(page.getByRole('heading', { name: '时钟小镇.' })).toBeVisible()
  const accountKey = 'lc_u4242_game_clock_town_v1'
  const clock = await getSave<ClockView>(page, accountKey)
  const question = clock.round.questions[clock.round.index]
  await page.locator(`.time-options button[data-time="${question.answer}"]`).click()
  await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('读对啦')
  expect(await page.evaluate(() => localStorage.getItem('lc_game_clock_town_v1_guest'))).toBeNull()
  await page.reload()
  await expect(page.getByRole('heading', { name: '时钟小镇.' })).toBeVisible()
  await expect(page.getByRole('status', { name: '答题反馈' })).toContainText('读对啦')
  expect((await getSave<ClockView>(page, accountKey)).round.answered).toBe(question.answer)
  expect(await page.evaluate(() => localStorage.getItem('lc_game_clock_town_v1_guest'))).toBeNull()
  expect(apiRequests).toEqual([])
})

test('手机：翻牌纠错、挑战难度、玩法说明和十款游戏导航', async ({ page }, info) => {
  test.setTimeout(120_000)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 390, height: 844 })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/#/games/memory-match')
  await expect(page.getByRole('heading', { name: '记忆翻牌.' })).toBeVisible()
  await noOverflow(page)
  await expect.poll(() => activeNavFits(page)).toBe(true)
  await page.screenshot({ path: info.outputPath('memory-match-mobile.png'), fullPage: true })
  await page.getByRole('button', { name: '挑战', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('切换游戏难度')
  await page.getByRole('button', { name: '切换并开始', exact: true }).click()
  await expect.poll(async () => (await getSave<MemoryView>(page, memoryKey)).round.cards.length).toBe(20)
  const memory = await getSave<MemoryView>(page, memoryKey)
  const first = memory.round.cards[0]
  const different = memory.round.cards.find(card => card.pairId !== first.pairId)!
  await page.locator(`.memory-card[data-card-id="${first.id}"]`).click()
  await page.locator(`.memory-card[data-card-id="${different.id}"]`).click()
  await expect(page.getByRole('status', { name: '翻牌反馈' })).toContainText('不是一对')
  await expect.poll(async () => {
    const view = await getSave<MemoryView>(page, memoryKey)
    return view.round.moves === 1 && view.round.flipped.length === 0
  }).toBe(true)
  const pair = pairsOf(memory).find(ids => !ids.includes(first.id) && !ids.includes(different.id))!
  await page.locator(`.memory-card[data-card-id="${pair[0]}"]`).click()
  await page.locator(`.memory-card[data-card-id="${pair[1]}"]`).click()
  await expect.poll(async () => (await getSave<MemoryView>(page, memoryKey)).round.matched.length).toBe(1)
  await page.getByRole('button', { name: '怎么玩', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('每次翻开两张卡片')
  await page.getByRole('button', { name: '关闭玩法说明', exact: true }).click()
  await page.setViewportSize({ width: 320, height: 740 })
  await noOverflow(page)
  await page.getByRole('link', { name: '口算火箭', exact: true }).click()
  await expect(page.getByRole('heading', { name: '口算火箭.' })).toBeVisible()
  await noOverflow(page)
  await expect.poll(() => activeNavFits(page)).toBe(true)
  await page.screenshot({ path: info.outputPath('rocket-math-mobile.png'), fullPage: true })
  await page.getByRole('link', { name: '披萨分数', exact: true }).click()
  await expect(page.getByRole('heading', { name: '披萨分数.' })).toBeVisible()
  await noOverflow(page)
  await expect.poll(() => activeNavFits(page)).toBe(true)
  await page.screenshot({ path: info.outputPath('fraction-pizza-mobile.png'), fullPage: true })
  await page.getByRole('button', { name: '怎么玩', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('分母')
  await page.getByRole('button', { name: '关闭玩法说明', exact: true }).click()
  const tours = [
    { link: '诗句排队', heading: '诗句排队.', slug: 'poem-order' },
    { link: '成语补字', heading: '成语补字.', slug: 'idiom-fill' },
    { link: '单词拼写', heading: '单词拼写.', slug: 'word-spell' },
    { link: '单词集市', heading: '单词集市.', slug: 'word-market' },
    { link: '时钟小镇', heading: '时钟小镇.', slug: 'clock-town' },
  ]
  for (const tour of tours) {
    await page.getByRole('link', { name: tour.link, exact: true }).click()
    await expect(page.getByRole('heading', { name: tour.heading })).toBeVisible()
    await noOverflow(page)
    await expect.poll(() => activeNavFits(page)).toBe(true)
    await page.screenshot({ path: info.outputPath(`${tour.slug}-mobile.png`), fullPage: true })
    if (tour.slug === 'poem-order') {
      await page.getByRole('button', { name: '怎么玩', exact: true }).click()
      await expect(page.getByRole('dialog')).toContainText('诗句纸条')
      await page.getByRole('button', { name: '关闭玩法说明', exact: true }).click()
    }
    if (tour.slug === 'clock-town') {
      await page.getByRole('button', { name: '怎么玩', exact: true }).click()
      await expect(page.getByRole('dialog')).toContainText('分针')
      await page.getByRole('button', { name: '关闭玩法说明', exact: true }).click()
    }
  }
  await expect(page.getByRole('link', { name: '时钟小镇', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('link', { name: '小小店长', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '机器人闯迷宫', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
