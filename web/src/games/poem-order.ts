import { randomInt, shuffle, type Rng } from './random'

export type PoemDifficulty = 'starter' | 'explorer' | 'master'

export interface PoemSource {
  id: string
  title: string
  author: string
  lines: string[]
}

export interface PoemTile {
  id: string
  text: string
}

export interface PoemQuestion {
  poemId: string
  title: string
  author: string
  lineCount: number
  answer: string[]
  tiles: PoemTile[]
}

export interface PoemRound {
  version: 1
  difficulty: PoemDifficulty
  questions: PoemQuestion[]
  index: number
  correct: number
  mistakes: number
  hints: number
  selected: string[]
  solved: boolean
  finished: boolean
}

export interface PoemSave {
  version: 1
  difficulty: PoemDifficulty
  round: PoemRound
  best: Record<PoemDifficulty, number>
  totalPoems: number
  rounds: number
}

export const POEM_QUESTIONS = 8

export const poemDifficulties = [
  { id: 'starter' as const, name: '初读', detail: '五言绝句', age: '6-8 岁' },
  { id: 'explorer' as const, name: '进阶', detail: '七言绝句', age: '7-9 岁' },
  { id: 'master' as const, name: '挑战', detail: '七言 + 干扰句', age: '8-10 岁' },
]

const starterPoems: PoemSource[] = [
  { id: 'jingyesi', title: '静夜思', author: '李白', lines: ['床前明月光', '疑是地上霜', '举头望明月', '低头思故乡'] },
  { id: 'chunxiao', title: '春晓', author: '孟浩然', lines: ['春眠不觉晓', '处处闻啼鸟', '夜来风雨声', '花落知多少'] },
  { id: 'dengguequelou', title: '登鹳雀楼', author: '王之涣', lines: ['白日依山尽', '黄河入海流', '欲穷千里目', '更上一层楼'] },
  { id: 'minnong', title: '悯农', author: '李绅', lines: ['锄禾日当午', '汗滴禾下土', '谁知盘中餐', '粒粒皆辛苦'] },
  { id: 'jiangxue', title: '江雪', author: '柳宗元', lines: ['千山鸟飞绝', '万径人踪灭', '孤舟蓑笠翁', '独钓寒江雪'] },
  { id: 'luzhai', title: '鹿柴', author: '王维', lines: ['空山不见人', '但闻人语响', '返景入深林', '复照青苔上'] },
  { id: 'xiangsi', title: '相思', author: '王维', lines: ['红豆生南国', '春来发几枝', '愿君多采撷', '此物最相思'] },
  { id: 'yonge', title: '咏鹅', author: '骆宾王', lines: ['鹅，鹅，鹅', '曲项向天歌', '白毛浮绿水', '红掌拨清波'] },
  { id: 'feng', title: '风', author: '李峤', lines: ['解落三秋叶', '能开二月花', '过江千尺浪', '入竹万竿斜'] },
  { id: 'qiupuge', title: '秋浦歌', author: '李白', lines: ['白发三千丈', '缘愁似个长', '不知明镜里', '何处得秋霜'] },
  { id: 'jingtingshan', title: '独坐敬亭山', author: '李白', lines: ['众鸟高飞尽', '孤云独去闲', '相看两不厌', '只有敬亭山'] },
  { id: 'xunyinzhe', title: '寻隐者不遇', author: '贾岛', lines: ['松下问童子', '言师采药去', '只在此山中', '云深不知处'] },
]

const explorerPoems: PoemSource[] = [
  { id: 'lushanpubu', title: '望庐山瀑布', author: '李白', lines: ['日照香炉生紫烟', '遥看瀑布挂前川', '飞流直下三千尺', '疑是银河落九天'] },
  { id: 'baidicheng', title: '早发白帝城', author: '李白', lines: ['朝辞白帝彩云间', '千里江陵一日还', '两岸猿声啼不住', '轻舟已过万重山'] },
  { id: 'jueju', title: '绝句', author: '杜甫', lines: ['两个黄鹂鸣翠柳', '一行白鹭上青天', '窗含西岭千秋雪', '门泊东吴万里船'] },
  { id: 'shanxing', title: '山行', author: '杜牧', lines: ['远上寒山石径斜', '白云生处有人家', '停车坐爱枫林晚', '霜叶红于二月花'] },
  { id: 'yongliu', title: '咏柳', author: '贺知章', lines: ['碧玉妆成一树高', '万条垂下绿丝绦', '不知细叶谁裁出', '二月春风似剪刀'] },
  { id: 'huixiang', title: '回乡偶书', author: '贺知章', lines: ['少小离家老大回', '乡音无改鬓毛衰', '儿童相见不相识', '笑问客从何处来'] },
  { id: 'huanghelou', title: '黄鹤楼送孟浩然之广陵', author: '李白', lines: ['故人西辞黄鹤楼', '烟花三月下扬州', '孤帆远影碧空尽', '唯见长江天际流'] },
  { id: 'fengqiao', title: '枫桥夜泊', author: '张继', lines: ['月落乌啼霜满天', '江枫渔火对愁眠', '姑苏城外寒山寺', '夜半钟声到客船'] },
  { id: 'xilinbi', title: '题西林壁', author: '苏轼', lines: ['横看成岭侧成峰', '远近高低各不同', '不识庐山真面目', '只缘身在此山中'] },
  { id: 'jingci', title: '晓出净慈寺送林子方', author: '杨万里', lines: ['毕竟西湖六月中', '风光不与四时同', '接天莲叶无穷碧', '映日荷花别样红'] },
  { id: 'guazhou', title: '泊船瓜洲', author: '王安石', lines: ['京口瓜洲一水间', '钟山只隔数重山', '春风又绿江南岸', '明月何时照我还'] },
  { id: 'yinshi', title: '饮湖上初晴后雨', author: '苏轼', lines: ['水光潋滟晴方好', '山色空蒙雨亦奇', '欲把西湖比西子', '淡妆浓抹总相宜'] },
]

export const poemPools: Record<'starter' | 'explorer', PoemSource[]> = {
  starter: starterPoems,
  explorer: explorerPoems,
}

function poolFor(difficulty: PoemDifficulty): PoemSource[] {
  return difficulty === 'starter' ? starterPoems : explorerPoems
}

export function isPoemDifficulty(value: unknown): value is PoemDifficulty {
  return value === 'starter' || value === 'explorer' || value === 'master'
}

function makeQuestion(difficulty: PoemDifficulty, rng: Rng, used: Set<string>): PoemQuestion {
  const pool = poolFor(difficulty)
  const available = pool.filter(poem => !used.has(poem.id))
  const poem = available[randomInt(rng, 0, available.length - 1)]
  used.add(poem.id)
  const answer = poem.lines.map((_, index) => `${poem.id}-${index}`)
  const tiles: PoemTile[] = poem.lines.map((text, index) => ({ id: answer[index], text }))
  if (difficulty === 'master') {
    const donors = pool.filter(item => item.id !== poem.id && item.lines.some(line => !poem.lines.includes(line)))
    const donor = donors[randomInt(rng, 0, donors.length - 1)]
    const line = donor.lines.find(text => !poem.lines.includes(text))!
    tiles.push({ id: `extra-${donor.id}-${poem.id}`, text: line })
  }
  return { poemId: poem.id, title: poem.title, author: poem.author, lineCount: poem.lines.length, answer, tiles: shuffle(tiles, rng) }
}

export function newPoemRound(difficulty: PoemDifficulty, rng: Rng = Math.random): PoemRound {
  const used = new Set<string>()
  return {
    version: 1,
    difficulty,
    questions: Array.from({ length: POEM_QUESTIONS }, () => makeQuestion(difficulty, rng, used)),
    index: 0,
    correct: 0,
    mistakes: 0,
    hints: 0,
    selected: [],
    solved: false,
    finished: false,
  }
}

export function newPoem(difficulty: PoemDifficulty = 'starter', rng: Rng = Math.random): PoemSave {
  return {
    version: 1,
    difficulty,
    round: newPoemRound(difficulty, rng),
    best: { starter: 0, explorer: 0, master: 0 },
    totalPoems: 0,
    rounds: 0,
  }
}

export function poemStars(round: Pick<PoemRound, 'mistakes'>): number {
  return round.mistakes === 0 ? 3 : round.mistakes <= 2 ? 2 : 1
}

export function selectPoemTile(save: PoemSave, tileId: string): boolean {
  const round = save.round
  if (round.finished || round.solved) return false
  const question = round.questions[round.index]
  if (!question.tiles.some(tile => tile.id === tileId)) return false
  const existing = round.selected.indexOf(tileId)
  if (existing >= 0) {
    round.selected.splice(existing, 1)
    return true
  }
  if (round.selected.length >= question.lineCount) return false
  round.selected.push(tileId)
  return true
}

export function clearPoemSelection(save: PoemSave): void {
  if (save.round.finished || save.round.solved) return
  save.round.selected = []
}

export function poemHint(save: PoemSave): string | null {
  const round = save.round
  if (round.finished || round.solved) return null
  const question = round.questions[round.index]
  const first = question.tiles.find(tile => tile.id === question.answer[0])
  if (!first) return null
  round.hints++
  return first.text
}

export function checkPoem(save: PoemSave): boolean | null {
  const round = save.round
  if (round.finished || round.solved) return null
  const question = round.questions[round.index]
  if (round.selected.length !== question.lineCount) return null
  const correct = round.selected.every((id, index) => id === question.answer[index])
  if (correct) {
    round.solved = true
    round.correct++
  } else {
    round.mistakes++
  }
  return correct
}

export function advancePoem(save: PoemSave): 'next' | 'finished' | null {
  const round = save.round
  if (round.finished || !round.solved) return null
  if (round.index < POEM_QUESTIONS - 1) {
    round.index++
    round.selected = []
    round.solved = false
    return 'next'
  }
  round.finished = true
  round.solved = false
  round.selected = []
  save.best[round.difficulty] = Math.max(save.best[round.difficulty], poemStars(round))
  save.totalPoems += POEM_QUESTIONS
  save.rounds++
  return 'finished'
}

export function restartPoem(save: PoemSave, rng: Rng = Math.random): void {
  save.round = newPoemRound(save.difficulty, rng)
}

export function switchPoemDifficulty(save: PoemSave, difficulty: PoemDifficulty, rng: Rng = Math.random): void {
  save.difficulty = difficulty
  save.round = newPoemRound(difficulty, rng)
}

function isInt(value: unknown, min: number, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max
}

function validQuestion(question: PoemQuestion, difficulty: PoemDifficulty): boolean {
  const source = poolFor(difficulty).find(poem => poem.id === question?.poemId)
  if (!source || question.title !== source.title || question.author !== source.author) return false
  if (question.lineCount !== source.lines.length) return false
  if (!Array.isArray(question.answer) || question.answer.length !== source.lines.length) return false
  if (!Array.isArray(question.tiles) || question.tiles.length !== source.lines.length + (difficulty === 'master' ? 1 : 0)) return false
  const ids = question.tiles.map(tile => tile?.id)
  if (!ids.every(id => typeof id === 'string') || new Set(ids).size !== ids.length) return false
  const texts = question.tiles.map(tile => tile?.text)
  if (!texts.every(text => typeof text === 'string') || new Set(texts).size !== texts.length) return false
  for (let index = 0; index < source.lines.length; index++) {
    const expectedId = `${source.id}-${index}`
    if (question.answer[index] !== expectedId) return false
    const tile = question.tiles.find(item => item.id === expectedId)
    if (!tile || tile.text !== source.lines[index]) return false
  }
  const extras = question.tiles.filter(tile => !question.answer.includes(tile.id))
  return difficulty === 'master' ? extras.length === 1 && !source.lines.includes(extras[0].text) : extras.length === 0
}

export function restorePoem(raw: string | null): PoemSave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as PoemSave
    if (!value || value.version !== 1 || !isPoemDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !poemDifficulties.every(item => isInt(best[item.id], 0, 3))) return null
    if (!isInt(value.totalPoems, 0, 1_000_000) || !isInt(value.rounds, 0, 1_000_000)) return null
    const round = value.round
    if (!round || round.version !== 1 || round.difficulty !== value.difficulty) return null
    if (!Array.isArray(round.questions) || round.questions.length !== POEM_QUESTIONS) return null
    if (!round.questions.every(question => validQuestion(question, value.difficulty))) return null
    if (new Set(round.questions.map(question => question.poemId)).size !== POEM_QUESTIONS) return null
    if (!isInt(round.index, 0, POEM_QUESTIONS - 1) || typeof round.solved !== 'boolean' || typeof round.finished !== 'boolean') return null
    if (!isInt(round.correct, 0, POEM_QUESTIONS) || !isInt(round.mistakes, 0, 9999) || !isInt(round.hints, 0, 9999)) return null
    if (!Array.isArray(round.selected) || !round.selected.every(id => typeof id === 'string')) return null
    const question = round.questions[round.index]
    if (new Set(round.selected).size !== round.selected.length) return null
    if (!round.selected.every(id => question.tiles.some(tile => tile.id === id))) return null
    if (round.selected.length > question.lineCount) return null
    if (!round.finished) {
      if (round.correct !== round.index + (round.solved ? 1 : 0)) return null
      if (round.solved && (round.selected.length !== question.lineCount || !round.selected.every((id, index) => id === question.answer[index]))) return null
    }
    if (round.finished) {
      if (round.index !== POEM_QUESTIONS - 1 || round.solved || round.correct !== POEM_QUESTIONS || round.selected.length !== 0) return null
      if ((best[value.difficulty] as number) < poemStars(round)) return null
    }
    return value
  } catch {
    return null
  }
}
