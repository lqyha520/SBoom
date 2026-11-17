import type { ApiSchemas } from '../../../shared/api-schema'
import type { PuzzleId } from './puzzle-games'
import type { BrainId } from './brain-types'
import type { ExperienceId } from './experience-types'

export type CloudGameId = ApiSchemas['GameSave']['game_id']
export type GameId = CloudGameId | PuzzleId | BrainId | ExperienceId
export type GameSubject = '数学' | '语文' | '英语' | '逻辑' | '益智' | '音乐' | '自然' | '探险' | '创作' | '反应' | '生活'
export interface GameInfo { id: GameId; title: string; subject: GameSubject; ages: [number, number]; icon: string; color: string; description: string; skills: string; duration: string; localOnly?: boolean }
export const games: GameInfo[] = [
  { id: 'little-shop', title: '小小店长', subject: '数学', ages: [4, 10], icon: 'i-lucide-store', color: 'peach', description: '开一家水果店，接待顾客、装好水果，再算算该找多少钱。', skills: '数数量 · 算总价 · 找零钱', duration: '每天 4 单' },
  { id: 'robot-maze', title: '机器人闯迷宫', subject: '逻辑', ages: [6, 12], icon: 'i-lucide-bot', color: 'mint', description: '用指令和循环积木规划路线，让机器人带着零件回到充电站。', skills: '顺序 · 方向 · 循环', duration: '36 个关卡' },
  { id: 'rocket-math', title: '口算火箭', subject: '数学', ages: [5, 10], icon: 'i-lucide-rocket', color: 'lavender', description: '完成一段星际航程，在一次次尝试中练熟加减法和乘法口诀。', skills: '20 以内 · 100 以内 · 乘法', duration: '每轮 8 题' },
  { id: 'memory-match', title: '记忆翻牌', subject: '数学', ages: [5, 10], icon: 'i-lucide-brain', color: 'rose', description: '记住卡片的位置，把算式和正确答案配成一对。', skills: '观察 · 记忆 · 心算', duration: '6 至 12 对卡片' },
  { id: 'fraction-pizza', title: '披萨分数', subject: '数学', ages: [7, 12], icon: 'i-lucide-pizza', color: 'peach', description: '观察一份披萨怎样平均分，认识分数并比较它们的大小。', skills: '平均分 · 分数 · 大小比较', duration: '三档难度' },
  { id: 'poem-order', title: '诗句排队', subject: '语文', ages: [6, 12], icon: 'i-lucide-scroll-text', color: 'mint', description: '把打乱的诗句排回原诗，一边回想，一边感受诗词的节奏。', skills: '古诗 · 语序 · 记忆', duration: '三档难度' },
  { id: 'idiom-fill', title: '成语补字', subject: '语文', ages: [6, 12], icon: 'i-lucide-book-marked', color: 'peach', description: '观察成语中缺少的字，结合提示把熟悉的表达补完整。', skills: '识字 · 成语 · 词语积累', duration: '三档难度' },
  { id: 'word-spell', title: '单词拼写', subject: '英语', ages: [6, 12], icon: 'i-lucide-spell-check-2', color: 'lavender', description: '挑选字母、拼出单词，把词义和拼写一起记住。', skills: '字母顺序 · 单词拼写', duration: '三档难度' },
  { id: 'word-market', title: '单词集市', subject: '英语', ages: [6, 12], icon: 'i-lucide-shopping-basket', color: 'rose', description: '逛逛单词集市，找到与提示对应的英语词语。', skills: '词义辨认 · 日常词汇', duration: '三档难度' },
  { id: 'clock-town', title: '时钟小镇', subject: '数学', ages: [5, 10], icon: 'i-lucide-clock-3', color: 'mint', description: '观察钟面和指针，从认识整点开始，慢慢读懂一刻和分钟。', skills: '整点 · 半点 · 五分钟', duration: '三档难度' },
  { id: 'shape-sudoku', title: '图形数独', subject: '益智', ages: [5, 12], icon: 'i-lucide-grid-2x2', color: 'peach', description: '用四种图形填满小方格，从已知条件中一步步找出答案。', skills: '观察 · 排除 · 逻辑推理', duration: '三档难度', localOnly: true },
  { id: 'sliding-puzzle', title: '数字华容道', subject: '益智', ages: [6, 12], icon: 'i-lucide-panels-top-left', color: 'lavender', description: '移动空格旁边的数字，让打乱的棋盘重新排好队。', skills: '空间思维 · 顺序 · 路线规划', duration: '3 × 3 至 4 × 4', localOnly: true },
  { id: 'lights-out', title: '点亮星星', subject: '益智', ages: [5, 12], icon: 'i-lucide-star', color: 'lavender', description: '一次点击改变一片星光，想想怎样让所有星星一起点亮。', skills: '因果观察 · 策略 · 逆向思考', duration: '3 × 3 至 5 × 5', localOnly: true },
  { id: 'tower-hanoi', title: '汉诺塔', subject: '益智', ages: [6, 12], icon: 'i-lucide-layers-3', color: 'rose', description: '借助中转柱搬运圆盘，先安排小盘，再为大盘腾出路线。', skills: '分步思考 · 规划 · 耐心', duration: '3 至 6 个圆盘', localOnly: true },
  { id: 'picture-logic', title: '像素拼图', subject: '益智', ages: [7, 12], icon: 'i-lucide-paintbrush', color: 'mint', description: '读懂行列数字，填色、标空，发现藏在格子里的图案。', skills: '交叉验证 · 推理 · 专注', duration: '5 × 5 至 7 × 7', localOnly: true },
  { id: 'pipe-connect', title: '水管连线', subject: '益智', ages: [5, 12], icon: 'i-lucide-waypoints', color: 'mint', description: '旋转弯管和直管，把进水口连到出口，让清水流过每一格。', skills: '方向 · 空间想象 · 路径规划', duration: '3 × 3 至 5 × 5', localOnly: true },
  { id: 'tangram', title: '七巧板', subject: '益智', ages: [5, 12], icon: 'i-lucide-puzzle', color: 'peach', description: '旋转、翻面和摆放七块几何图形，拼出正方形、三角形和斜方块。', skills: '几何 · 空间想象 · 拼搭', duration: '27 种目标轮廓', localOnly: true },
  { id: 'sokoban', title: '推箱子', subject: '益智', ages: [6, 12], icon: 'i-lucide-package', color: 'mint', description: '绕到箱子后方，留好转弯的位置，把每只木箱推到目标上。', skills: '规划 · 预判 · 逆向思考', duration: '72 张地图', localOnly: true },
  { id: 'pattern-train', title: '找规律', subject: '益智', ages: [4, 10], icon: 'i-lucide-shapes', color: 'lavender', description: '跟着小火车观察图形和数字变化，找出下一节车厢的秘密。', skills: '观察 · 归纳 · 数列', duration: '每轮 6 题', localOnly: true },
  { id: 'one-stroke', title: '一笔画', subject: '益智', ages: [5, 12], icon: 'i-lucide-route', color: 'rose', description: '一笔走完所有线，先想好分支的顺序，再连接下一个点。', skills: '路径规划 · 图形观察 · 策略', duration: '三档路线', localOnly: true },
  { id: 'balance-scale', title: '天平称重', subject: '益智', ages: [5, 10], icon: 'i-lucide-scale', color: 'peach', description: '搭配不同重量的砝码，让天平两边一样重，找到等量关系。', skills: '轻重 · 加法 · 等量关系', duration: '三档重量', localOnly: true },
  { id: 'color-sort', title: '颜色排序', subject: '益智', ages: [5, 12], icon: 'i-lucide-flask-conical', color: 'lavender', description: '借助空管中转，把混合的色块分开，让同一种颜色住在一起。', skills: '分类 · 容量 · 策略', duration: '2 至 6 种颜色', localOnly: true },
  { id: 'mirror-draw', title: '镜面对称', subject: '益智', ages: [5, 10], icon: 'i-lucide-flip-horizontal-2', color: 'mint', description: '像照镜子一样，沿着一条或两条对称轴补全彩色图案。', skills: '对称 · 位置 · 空间观察', duration: '单轴与双轴', localOnly: true },
  { id: 'spot-difference', title: '找不同', subject: '益智', ages: [4, 10], icon: 'i-lucide-scan-eye', color: 'rose', description: '看看小花园里的两幅图，找出变了颜色或细节的小图案。', skills: '观察 · 比较 · 专注', duration: '3 至 5 处不同', localOnly: true },
  { id: 'rhythm-band', title: '节奏小乐队', subject: '音乐', ages: [4, 12], icon: 'i-lucide-music-2', color: 'lavender', description: '听听大鼓、木琴和铃铛，跟着鼓点演奏，也能编出自己的8 至 16 拍音乐。', skills: '节奏 · 听觉 · 协调', duration: '跟奏与自由编曲', localOnly: true },
  { id: 'little-farm', title: '小小农场', subject: '自然', ages: [4, 10], icon: 'i-lucide-sprout', color: 'mint', description: '在温室播种、浇水、逐日观察生长，收获作物并照顾动物伙伴。', skills: '种植 · 规划 · 责任感', duration: '四季温室农场', localOnly: true },
  { id: 'science-lab', title: '科学实验室', subject: '自然', ages: [5, 12], icon: 'i-lucide-flask-conical', color: 'peach', description: '把材料放入水中，靠近磁铁，混合颜料，观察每次实验的变化。', skills: '实验 · 观察 · 因果理解', duration: '浮沉、磁铁、混色', localOnly: true },
  { id: 'forest-rescue', title: '森林救援队', subject: '探险', ages: [5, 12], icon: 'i-lucide-trees', color: 'mint', description: '和护林员一起探索森林，选择故事路线，帮助小鸟、乌龟和小兔。', skills: '阅读 · 同理心 · 合作', duration: '分支故事探索', localOnly: true },
  { id: 'creative-studio', title: '创意画室', subject: '创作', ages: [4, 12], icon: 'i-lucide-palette', color: 'rose', description: '用画笔、颜色和印章画出自己的小世界，保存作品并导出图片。', skills: '想象 · 表达 · 审美', duration: '自由绘画与小画廊', localOnly: true },
  { id: 'animal-catch', title: '动物接接乐', subject: '反应', ages: [4, 10], icon: 'i-lucide-apple', color: 'peach', description: '移动篮子接住动物喜欢的食物，调慢速度，练习眼睛与手的配合。', skills: '反应 · 协调 · 动物常识', duration: '速度可调，随时暂停', localOnly: true },
  { id: 'daily-life', title: '生活小达人', subject: '生活', ages: [4, 10], icon: 'i-lucide-backpack', color: 'lavender', description: '整理书包、选择天气合适的衣物，在模拟路口练习和大人一起过街。', skills: '自理 · 生活常识 · 出行', duration: '六种活动 · 出行准备', localOnly: true },
  { id: 'eco-guardian', title: '环保小卫士', subject: '自然', ages: [4, 12], icon: 'i-lucide-recycle', color: 'mint', description: '用模拟夹子清理海滩、公园和步道，分类垃圾，和救护站一起帮助动物重返干净的家。', skills: '环保 · 分类 · 责任感', duration: '三地清理与动物帮助', localOnly: true },
]
export const cloudGames = games.filter((game): game is GameInfo & { id: CloudGameId } => !game.localOnly)
export function gameFromHash(hash: string): GameInfo | undefined { const route = hash.split('?')[0].replace(/\/+$/, ''); return games.find(game => route === `#/games/${game.id}`) }
export function gameKey(id: GameId, owner = ''): string {
  const suffix = `${id.replace(/-/g, '_')}_v1`
  return owner ? `lc_u${owner}_game_${suffix}` : `lc_game_${suffix}_guest`
}
export const gameHref = (id: GameId) => `#/games/${id}`

/** 用各游戏已有的严格恢复函数校验云存档，损坏数据不会覆盖本机存档。 */
export async function validSave(id: GameId, raw: string): Promise<boolean> {
  switch (id) {
    case 'little-shop': return !!(await import('./little-shop')).restoreShop(raw)
    case 'robot-maze': return !!(await import('./robot-maze')).restoreMaze(raw)
    case 'rocket-math': return !!(await import('./rocket-math')).restoreRocket(raw)
    case 'memory-match': return !!(await import('./memory-match')).restoreMemory(raw)
    case 'fraction-pizza': return !!(await import('./fraction-pizza')).restoreFraction(raw)
    case 'poem-order': return !!(await import('./poem-order')).restorePoem(raw)
    case 'idiom-fill': return !!(await import('./idiom-fill')).restoreIdiom(raw)
    case 'word-spell': return !!(await import('./word-spell')).restoreSpell(raw)
    case 'word-market': return !!(await import('./word-market')).restoreMarket(raw)
    case 'clock-town': return !!(await import('./clock-town')).restoreClock(raw)
    case 'rhythm-band': case 'little-farm': case 'science-lab': case 'forest-rescue':
    case 'creative-studio': case 'animal-catch': case 'daily-life': case 'eco-guardian':
      return !!(await import('./experience-games')).restoreExperience(raw, id)
    case 'tangram': case 'sokoban': case 'pattern-train': case 'one-stroke':
    case 'balance-scale': case 'color-sort': case 'mirror-draw': case 'spot-difference':
      return !!(await import('./brain-games')).restoreBrain(raw, id)
    default: return !!(await import('./puzzle-games')).restorePuzzle(raw, id)
  }
}
