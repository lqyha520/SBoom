import { contentDeck,rememberContent,validContentHistory,type ContentHistory } from './challenge-journey'
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

export interface PoemSave extends ContentHistory {
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
  {"id": "new-starter-1", "title": "绝句·迟日江山丽", "author": "杜甫", "lines": ["迟日江山丽", "春风花草香", "泥融飞燕子", "沙暖睡鸳鸯"]},
  {"id": "new-starter-2", "title": "绝句·江碧鸟逾白", "author": "杜甫", "lines": ["江碧鸟逾白", "山青花欲燃", "今春看又过", "何日是归年"]},
  {"id": "new-starter-3", "title": "江上渔者", "author": "范仲淹", "lines": ["江上往来人", "但爱鲈鱼美", "君看一叶舟", "出没风波里"]},
  {"id": "new-starter-4", "title": "池上", "author": "白居易", "lines": ["小娃撑小艇", "偷采白莲回", "不解藏踪迹", "浮萍一道开"]},
  {"id": "new-starter-5", "title": "画", "author": "佚名", "lines": ["远看山有色", "近听水无声", "春去花还在", "人来鸟不惊"]},
  {"id": "new-starter-6", "title": "乐游原", "author": "李商隐", "lines": ["向晚意不适", "驱车登古原", "夕阳无限好", "只是近黄昏"]},
  {"id": "new-starter-7", "title": "送灵澈上人", "author": "刘长卿", "lines": ["苍苍竹林寺", "杳杳钟声晚", "荷笠带斜阳", "青山独归远"]},
  {"id": "new-starter-8", "title": "送朱大入秦", "author": "孟浩然", "lines": ["游人五陵去", "宝剑值千金", "分手脱相赠", "平生一片心"]},
  {"id": "new-starter-9", "title": "宿建德江", "author": "孟浩然", "lines": ["移舟泊烟渚", "日暮客愁新", "野旷天低树", "江清月近人"]},
  {"id": "new-starter-10", "title": "夜宿山寺", "author": "李白", "lines": ["危楼高百尺", "手可摘星辰", "不敢高声语", "恐惊天上人"]},
  {"id": "new-starter-11", "title": "古朗月行·节选", "author": "李白", "lines": ["小时不识月", "呼作白玉盘", "又疑瑶台镜", "飞在青云端"]},
  {"id": "new-starter-12", "title": "竹里馆", "author": "王维", "lines": ["独坐幽篁里", "弹琴复长啸", "深林人不知", "明月来相照"]},
  {"id": "new-starter-13", "title": "鸟鸣涧", "author": "王维", "lines": ["人闲桂花落", "夜静春山空", "月出惊山鸟", "时鸣春涧中"]},
  {"id": "new-starter-14", "title": "送别·山中相送罢", "author": "王维", "lines": ["山中相送罢", "日暮掩柴扉", "春草明年绿", "王孙归不归"]},
  {"id": "new-starter-15", "title": "杂诗·君自故乡来", "author": "王维", "lines": ["君自故乡来", "应知故乡事", "来日绮窗前", "寒梅著花未"]},
  {"id": "new-starter-16", "title": "终南望余雪", "author": "祖咏", "lines": ["终南阴岭秀", "积雪浮云端", "林表明霁色", "城中增暮寒"]},
  {"id": "new-starter-17", "title": "渡汉江", "author": "宋之问", "lines": ["岭外音书断", "经冬复历春", "近乡情更怯", "不敢问来人"]},
  {"id": "new-starter-18", "title": "问刘十九", "author": "白居易", "lines": ["绿蚁新醅酒", "红泥小火炉", "晚来天欲雪", "能饮一杯无"]},
  {"id": "new-starter-19", "title": "悯农·春种一粒粟", "author": "李绅", "lines": ["春种一粒粟", "秋收万颗子", "四海无闲田", "农夫犹饿死"]},
  {"id": "new-starter-20", "title": "梅花", "author": "王安石", "lines": ["墙角数枝梅", "凌寒独自开", "遥知不是雪", "为有暗香来"]},
  {"id": "new-starter-21", "title": "夏日绝句", "author": "李清照", "lines": ["生当作人杰", "死亦为鬼雄", "至今思项羽", "不肯过江东"]},
  {"id": "new-starter-22", "title": "山中", "author": "王勃", "lines": ["长江悲已滞", "万里念将归", "况属高风晚", "山山黄叶飞"]},
  {"id": "new-starter-23", "title": "春怨", "author": "金昌绪", "lines": ["打起黄莺儿", "莫教枝上啼", "啼时惊妾梦", "不得到辽西"]},
  {"id": "new-starter-24", "title": "八阵图", "author": "杜甫", "lines": ["功盖三分国", "名成八阵图", "江流石不转", "遗恨失吞吴"]},
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
  {"id": "new-explorer-1", "title": "赠汪伦", "author": "李白", "lines": ["李白乘舟将欲行", "忽闻岸上踏歌声", "桃花潭水深千尺", "不及汪伦送我情"]},
  {"id": "new-explorer-2", "title": "九月九日忆山东兄弟", "author": "王维", "lines": ["独在异乡为异客", "每逢佳节倍思亲", "遥知兄弟登高处", "遍插茱萸少一人"]},
  {"id": "new-explorer-3", "title": "望天门山", "author": "李白", "lines": ["天门中断楚江开", "碧水东流至此回", "两岸青山相对出", "孤帆一片日边来"]},
  {"id": "new-explorer-4", "title": "小儿垂钓", "author": "胡令能", "lines": ["蓬头稚子学垂纶", "侧坐莓苔草映身", "路人借问遥招手", "怕得鱼惊不应人"]},
  {"id": "new-explorer-5", "title": "石灰吟", "author": "于谦", "lines": ["千锤万凿出深山", "烈火焚烧若等闲", "粉骨碎身浑不怕", "要留清白在人间"]},
  {"id": "new-explorer-6", "title": "村居", "author": "高鼎", "lines": ["草长莺飞二月天", "拂堤杨柳醉春烟", "儿童散学归来早", "忙趁东风放纸鸢"]},
  {"id": "new-explorer-7", "title": "小池", "author": "杨万里", "lines": ["泉眼无声惜细流", "树阴照水爱晴柔", "小荷才露尖尖角", "早有蜻蜓立上头"]},
  {"id": "new-explorer-8", "title": "惠崇春江晚景", "author": "苏轼", "lines": ["竹外桃花三两枝", "春江水暖鸭先知", "蒌蒿满地芦芽短", "正是河豚欲上时"]},
  {"id": "new-explorer-9", "title": "春日", "author": "朱熹", "lines": ["胜日寻芳泗水滨", "无边光景一时新", "等闲识得东风面", "万紫千红总是春"]},
  {"id": "new-explorer-10", "title": "游园不值", "author": "叶绍翁", "lines": ["应怜屐齿印苍苔", "小扣柴扉久不开", "春色满园关不住", "一枝红杏出墙来"]},
  {"id": "new-explorer-11", "title": "清明", "author": "杜牧", "lines": ["清明时节雨纷纷", "路上行人欲断魂", "借问酒家何处有", "牧童遥指杏花村"]},
  {"id": "new-explorer-12", "title": "江南春", "author": "杜牧", "lines": ["千里莺啼绿映红", "水村山郭酒旗风", "南朝四百八十寺", "多少楼台烟雨中"]},
  {"id": "new-explorer-13", "title": "秋夕", "author": "杜牧", "lines": ["银烛秋光冷画屏", "轻罗小扇扑流萤", "天阶夜色凉如水", "坐看牵牛织女星"]},
  {"id": "new-explorer-14", "title": "题都城南庄", "author": "崔护", "lines": ["去年今日此门中", "人面桃花相映红", "人面不知何处去", "桃花依旧笑春风"]},
  {"id": "new-explorer-15", "title": "芙蓉楼送辛渐", "author": "王昌龄", "lines": ["寒雨连江夜入吴", "平明送客楚山孤", "洛阳亲友如相问", "一片冰心在玉壶"]},
  {"id": "new-explorer-16", "title": "出塞", "author": "王昌龄", "lines": ["秦时明月汉时关", "万里长征人未还", "但使龙城飞将在", "不教胡马度阴山"]},
  {"id": "new-explorer-17", "title": "凉州词·黄河远上", "author": "王之涣", "lines": ["黄河远上白云间", "一片孤城万仞山", "羌笛何须怨杨柳", "春风不度玉门关"]},
  {"id": "new-explorer-18", "title": "凉州词·葡萄美酒", "author": "王翰", "lines": ["葡萄美酒夜光杯", "欲饮琵琶马上催", "醉卧沙场君莫笑", "古来征战几人回"]},
  {"id": "new-explorer-19", "title": "墨梅", "author": "王冕", "lines": ["我家洗砚池头树", "朵朵花开淡墨痕", "不要人夸好颜色", "只留清气满乾坤"]},
  {"id": "new-explorer-20", "title": "竹石", "author": "郑燮", "lines": ["咬定青山不放松", "立根原在破岩中", "千磨万击还坚劲", "任尔东西南北风"]},
  {"id": "new-explorer-21", "title": "雪梅", "author": "卢钺", "lines": ["梅雪争春未肯降", "骚人阁笔费评章", "梅须逊雪三分白", "雪却输梅一段香"]},
  {"id": "new-explorer-22", "title": "冬夜读书示子聿", "author": "陆游", "lines": ["古人学问无遗力", "少壮工夫老始成", "纸上得来终觉浅", "绝知此事要躬行"]},
  {"id": "new-explorer-23", "title": "四时田园杂兴·其三十一", "author": "范成大", "lines": ["昼出耘田夜绩麻", "村庄儿女各当家", "童孙未解供耕织", "也傍桑阴学种瓜"]},
  {"id": "new-explorer-24", "title": "四时田园杂兴·其二十五", "author": "范成大", "lines": ["梅子金黄杏子肥", "麦花雪白菜花稀", "日长篱落无人过", "惟有蜻蜓蛱蝶飞"]},
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

export function newPoemRound(difficulty: PoemDifficulty, rng: Rng = Math.random, history: string[] = []): PoemRound {
  const selected=contentDeck(poolFor(difficulty),POEM_QUESTIONS,item=>item.id,history,rng)
  const used = new Set(poolFor(difficulty).filter(item=>!selected.includes(item)).map(item=>item.id))
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

export function movePoemTile(save: PoemSave, index: number, delta: number): boolean {
  const round = save.round, target = index+delta
  if (round.finished || round.solved || !Number.isInteger(index) || ![-1,1].includes(delta) || index < 0 || index >= round.selected.length || target < 0 || target >= round.selected.length) return false
  ;[round.selected[index],round.selected[target]] = [round.selected[target],round.selected[index]]
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
  const index = question.answer.findIndex((id,index)=>round.selected[index]!==id)
  const first = question.tiles.find(tile => tile.id === question.answer[index])
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
  const history=rememberContent(save,save.difficulty,save.round.questions.map(question=>question.poemId))
  save.round = newPoemRound(save.difficulty, rng,history)
}

export function switchPoemDifficulty(save: PoemSave, difficulty: PoemDifficulty, rng: Rng = Math.random): void {
  rememberContent(save,save.difficulty,save.round.questions.map(question=>question.poemId))
  save.difficulty = difficulty
  save.round = newPoemRound(difficulty, rng,save.contentHistory?.[difficulty] || [])
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
    if (!value || !validContentHistory(value.contentHistory) || value.version !== 1 || !isPoemDifficulty(value.difficulty)) return null
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
