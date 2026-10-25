import { randomInt, shuffle, type Rng } from './random'

export type IdiomDifficulty = 'starter' | 'explorer' | 'master'

export interface IdiomSource {
  id: string
  text: string
  blank: number
  answer: string
  options: string[]
  pinyin: string
  meaning: string
}

export interface IdiomQuestion {
  idiomId: string
  options: string[]
}

export interface IdiomRound {
  version: 1
  difficulty: IdiomDifficulty
  questions: IdiomQuestion[]
  index: number
  correct: number
  mistakes: number
  answered: string | null
  finished: boolean
}

export interface IdiomSave {
  version: 1
  difficulty: IdiomDifficulty
  round: IdiomRound
  best: Record<IdiomDifficulty, number>
  totalCorrect: number
  rounds: number
}

export const IDIOM_QUESTIONS = 8

export const idiomDifficulties = [
  { id: 'starter' as const, name: '初识', detail: '常用成语', age: '6-8 岁' },
  { id: 'explorer' as const, name: '进阶', detail: '易混字形', age: '8-10 岁' },
  { id: 'master' as const, name: '挑战', detail: '高阶成语', age: '9-12 岁' },
]

const starterIdioms: IdiomSource[] = [
  { id: 'yixinyiyi', text: '一心一意', blank: 3, answer: '意', options: ['意', '义', '艺', '议'], pinyin: 'yī xīn yī yì', meaning: '形容心思专一，没有别的念头。' },
  { id: 'sanxineryi', text: '三心二意', blank: 2, answer: '二', options: ['二', '两', '再', '双'], pinyin: 'sān xīn èr yì', meaning: '形容犹豫不决，或心思不专一。' },
  { id: 'jingdizhiwa', text: '井底之蛙', blank: 3, answer: '蛙', options: ['蛙', '娃', '洼', '哇'], pinyin: 'jǐng dǐ zhī wā', meaning: '比喻见识狭窄的人。' },
  { id: 'huashetianzu', text: '画蛇添足', blank: 3, answer: '足', options: ['足', '走', '手', '竹'], pinyin: 'huà shé tiān zú', meaning: '比喻做了多余的事，反而不合适。' },
  { id: 'shouzhudaitu', text: '守株待兔', blank: 2, answer: '待', options: ['待', '侍', '持', '特'], pinyin: 'shǒu zhū dài tù', meaning: '比喻不主动努力，只想靠运气得到成果。' },
  { id: 'wangyangbulao', text: '亡羊补牢', blank: 2, answer: '补', options: ['补', '捕', '哺', '卜'], pinyin: 'wáng yáng bǔ láo', meaning: '比喻出了问题及时补救，还不算晚。' },
  { id: 'yanerdaoling', text: '掩耳盗铃', blank: 3, answer: '铃', options: ['铃', '玲', '岭', '领'], pinyin: 'yǎn ěr dào líng', meaning: '比喻自己欺骗自己，明明掩盖不住。' },
  { id: 'duiniutanqin', text: '对牛弹琴', blank: 3, answer: '琴', options: ['琴', '勤', '芹', '禽'], pinyin: 'duì niú tán qín', meaning: '比喻对不懂道理的人讲道理，白费口舌。' },
  { id: 'kezhouqiujian', text: '刻舟求剑', blank: 3, answer: '剑', options: ['剑', '箭', '建', '健'], pinyin: 'kè zhōu qiú jiàn', meaning: '比喻拘泥成法，不知道随情况变化。' },
  { id: 'hujiahuwei', text: '狐假虎威', blank: 3, answer: '威', options: ['威', '微', '危', '违'], pinyin: 'hú jiǎ hǔ wēi', meaning: '比喻依仗别人的势力来欺压人。' },
]

const explorerIdioms: IdiomSource[] = [
  { id: 'beigongsheying', text: '杯弓蛇影', blank: 3, answer: '影', options: ['影', '映', '应', '硬'], pinyin: 'bēi gōng shé yǐng', meaning: '比喻因疑神疑鬼而引起恐惧。' },
  { id: 'jinggongzhiniao', text: '惊弓之鸟', blank: 0, answer: '惊', options: ['惊', '京', '精', '经'], pinyin: 'jīng gōng zhī niǎo', meaning: '比喻受过惊吓，遇到类似情况就害怕的人。' },
  { id: 'wangmeizhike', text: '望梅止渴', blank: 3, answer: '渴', options: ['渴', '喝', '竭', '揭'], pinyin: 'wàng méi zhǐ kě', meaning: '比喻用空想来安慰自己。' },
  { id: 'pofuchenzhou', text: '破釜沉舟', blank: 1, answer: '釜', options: ['釜', '斧', '府', '辅'], pinyin: 'pò fǔ chén zhōu', meaning: '比喻下定决心，不顾一切干到底。' },
  { id: 'woxinchangdan', text: '卧薪尝胆', blank: 1, answer: '薪', options: ['薪', '新', '心', '欣'], pinyin: 'wò xīn cháng dǎn', meaning: '形容刻苦自励，发愤图强。' },
  { id: 'xuezhongsongtan', text: '雪中送炭', blank: 3, answer: '炭', options: ['炭', '碳', '汤', '烫'], pinyin: 'xuě zhōng sòng tàn', meaning: '比喻在别人急需时给予帮助。' },
  { id: 'jinshangtianhua', text: '锦上添花', blank: 2, answer: '添', options: ['添', '填', '甜', '忝'], pinyin: 'jǐn shàng tiān huā', meaning: '比喻使美好的事物更加美好。' },
  { id: 'xiongyouchengzhu', text: '胸有成竹', blank: 3, answer: '竹', options: ['竹', '足', '烛', '逐'], pinyin: 'xiōng yǒu chéng zhú', meaning: '比喻做事之前已经有充分的把握。' },
  { id: 'lanyuchongshu', text: '滥竽充数', blank: 1, answer: '竽', options: ['竽', '芋', '鱼', '于'], pinyin: 'làn yú chōng shù', meaning: '比喻没有真才实学的人混在行家里面充数。' },
  { id: 'hualongdianjing', text: '画龙点睛', blank: 3, answer: '睛', options: ['睛', '晴', '精', '请'], pinyin: 'huà lóng diǎn jīng', meaning: '比喻在关键处点明要旨，使内容更加生动。' },
]

const masterIdioms: IdiomSource[] = [
  { id: 'yiguzuoqi', text: '一鼓作气', blank: 1, answer: '鼓', options: ['鼓', '股', '古', '故'], pinyin: 'yī gǔ zuò qì', meaning: '比喻趁劲头大的时候，一口气把事情做完。' },
  { id: 'nanyuanbeizhe', text: '南辕北辙', blank: 3, answer: '辙', options: ['辙', '撤', '澈', '彻'], pinyin: 'nán yuán běi zhé', meaning: '比喻行动和目的正好相反。' },
  { id: 'shirupozhu', text: '势如破竹', blank: 0, answer: '势', options: ['势', '事', '是', '世'], pinyin: 'shì rú pò zhú', meaning: '形容节节胜利，毫无阻碍。' },
  { id: 'chuleibacui', text: '出类拔萃', blank: 3, answer: '萃', options: ['萃', '碎', '翠', '粹'], pinyin: 'chū lèi bá cuì', meaning: '形容超出同类之上，非常优秀。' },
  { id: 'luoyibujue', text: '络绎不绝', blank: 1, answer: '绎', options: ['绎', '译', '择', '驿'], pinyin: 'luò yì bù jué', meaning: '形容行人车马来来往往，接连不断。' },
  { id: 'xiangfuxiangcheng', text: '相辅相成', blank: 1, answer: '辅', options: ['辅', '捕', '补', '浦'], pinyin: 'xiāng fǔ xiāng chéng', meaning: '指两件事物互相补充、互相配合。' },
  { id: 'biechuxincai', text: '别出心裁', blank: 3, answer: '裁', options: ['裁', '载', '栽', '哉'], pinyin: 'bié chū xīn cái', meaning: '形容独创一格，与众不同。' },
  { id: 'xuxurushing', text: '栩栩如生', blank: 0, answer: '栩', options: ['栩', '许', '羽', '诩'], pinyin: 'xǔ xǔ rú shēng', meaning: '形容形象生动逼真，像活的一样。' },
  { id: 'kuaizhirenkou', text: '脍炙人口', blank: 1, answer: '炙', options: ['炙', '灸', '治', '质'], pinyin: 'kuài zhì rén kǒu', meaning: '比喻好的诗文或事物受到人们称赞。' },
  { id: 'yimingjingren', text: '一鸣惊人', blank: 1, answer: '鸣', options: ['鸣', '名', '明', '命'], pinyin: 'yī míng jīng rén', meaning: '比喻平时没有突出表现，一下子做出惊人的成绩。' },
]

export const idiomPools: Record<IdiomDifficulty, IdiomSource[]> = {
  starter: starterIdioms,
  explorer: explorerIdioms,
  master: masterIdioms,
}

export function isIdiomDifficulty(value: unknown): value is IdiomDifficulty {
  return value === 'starter' || value === 'explorer' || value === 'master'
}

export function idiomById(difficulty: IdiomDifficulty, id: string): IdiomSource | undefined {
  return idiomPools[difficulty].find(item => item.id === id)
}

export function newIdiomRound(difficulty: IdiomDifficulty, rng: Rng = Math.random): IdiomRound {
  const pool = [...idiomPools[difficulty]]
  const used = new Set<string>()
  const questions: IdiomQuestion[] = []
  for (let index = 0; index < IDIOM_QUESTIONS; index++) {
    const available = pool.filter(item => !used.has(item.id))
    const item = available[randomInt(rng, 0, available.length - 1)]
    used.add(item.id)
    questions.push({ idiomId: item.id, options: shuffle(item.options, rng) })
  }
  return {
    version: 1,
    difficulty,
    questions,
    index: 0,
    correct: 0,
    mistakes: 0,
    answered: null,
    finished: false,
  }
}

export function newIdiom(difficulty: IdiomDifficulty = 'starter', rng: Rng = Math.random): IdiomSave {
  return {
    version: 1,
    difficulty,
    round: newIdiomRound(difficulty, rng),
    best: { starter: 0, explorer: 0, master: 0 },
    totalCorrect: 0,
    rounds: 0,
  }
}

export function idiomStars(round: Pick<IdiomRound, 'mistakes'>): number {
  return round.mistakes === 0 ? 3 : round.mistakes === 1 ? 2 : 1
}

export function answerIdiom(save: IdiomSave, char: string): boolean | null {
  const round = save.round
  if (round.finished || round.answered !== null) return null
  const question = round.questions[round.index]
  if (!question.options.includes(char)) return null
  const source = idiomById(round.difficulty, question.idiomId)
  if (!source) return null
  round.answered = char
  if (char === source.answer) round.correct++
  else round.mistakes++
  return char === source.answer
}

export function advanceIdiom(save: IdiomSave): 'next' | 'finished' | null {
  const round = save.round
  if (round.finished || round.answered === null) return null
  if (round.index < IDIOM_QUESTIONS - 1) {
    round.index++
    round.answered = null
    return 'next'
  }
  round.finished = true
  round.answered = null
  save.best[round.difficulty] = Math.max(save.best[round.difficulty], idiomStars(round))
  save.totalCorrect += round.correct
  save.rounds++
  return 'finished'
}

export function restartIdiom(save: IdiomSave, rng: Rng = Math.random): void {
  save.round = newIdiomRound(save.difficulty, rng)
}

export function switchIdiomDifficulty(save: IdiomSave, difficulty: IdiomDifficulty, rng: Rng = Math.random): void {
  save.difficulty = difficulty
  save.round = newIdiomRound(difficulty, rng)
}

function isInt(value: unknown, min: number, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max
}

function validQuestion(question: IdiomQuestion, difficulty: IdiomDifficulty): boolean {
  const source = idiomById(difficulty, question?.idiomId)
  if (!source) return false
  if (!Array.isArray(question.options) || question.options.length !== 4) return false
  if (!question.options.every(char => typeof char === 'string')) return false
  if (new Set(question.options).size !== 4) return false
  return question.options.every(char => source.options.includes(char)) && question.options.includes(source.answer)
}

export function restoreIdiom(raw: string | null): IdiomSave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as IdiomSave
    if (!value || value.version !== 1 || !isIdiomDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !idiomDifficulties.every(item => isInt(best[item.id], 0, 3))) return null
    if (!isInt(value.totalCorrect, 0, 1_000_000) || !isInt(value.rounds, 0, 1_000_000)) return null
    const round = value.round
    if (!round || round.version !== 1 || round.difficulty !== value.difficulty) return null
    if (!Array.isArray(round.questions) || round.questions.length !== IDIOM_QUESTIONS) return null
    if (!round.questions.every(question => validQuestion(question, value.difficulty))) return null
    if (new Set(round.questions.map(question => question.idiomId)).size !== IDIOM_QUESTIONS) return null
    if (!isInt(round.index, 0, IDIOM_QUESTIONS - 1) || typeof round.finished !== 'boolean') return null
    if (!isInt(round.correct, 0, IDIOM_QUESTIONS) || !isInt(round.mistakes, 0, IDIOM_QUESTIONS)) return null
    const question = round.questions[round.index]
    if (round.answered !== null && (typeof round.answered !== 'string' || !question.options.includes(round.answered))) return null
    if (!round.finished) {
      const answeredCount = round.index + (round.answered === null ? 0 : 1)
      if (round.correct + round.mistakes !== answeredCount) return null
    }
    if (round.finished) {
      if (round.index !== IDIOM_QUESTIONS - 1 || round.answered !== null) return null
      if (round.correct + round.mistakes !== IDIOM_QUESTIONS) return null
      if ((best[value.difficulty] as number) < idiomStars(round)) return null
    }
    return value
  } catch {
    return null
  }
}
