<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { hanoiRemaining, lightPreview, pictureLines, slidingDistance, sudokuCandidates } from './puzzle-reasoning'
import { pictureName } from './varied-puzzles'
import GameNav from './GameNav.vue'
import { games, gameKey } from './catalog'
import { writeGameSave } from './game-storage'
import { revealGameHint } from './game-activity'
import {
  hanoiTop, moveHanoi, newPuzzle, nextPuzzle, pictureClues, pipeBits, pipePort, pipeWater,
  playPuzzle, puzzleDifficulties, puzzleHint, puzzleStars, restorePuzzle, shapeNames, shapes,
  sudokuConflicts, type PuzzleDifficulty, type PuzzleId, type PuzzleRound,
} from './puzzle-games'

const props = defineProps<{ gameId: PuzzleId; storageKey?: string }>()
const key = computed(() => props.storageKey || gameKey(props.gameId))
function readSave() { try { return restorePuzzle(localStorage.getItem(key.value), props.gameId) } catch { return null } }
const save = ref(readSave() || newPuzzle(props.gameId))
const game = computed(() => games.find(game => game.id === props.gameId)!)
const round = computed(() => save.value.round)
const selected = ref(-1), peg = ref(-1), paint = ref(1), hovered = ref(-1)
const candidates = computed(()=>selected.value<0 ? [] : sudokuCandidates(round.value.cells,selected.value))
const candidateLabel=computed(()=>candidates.value.map(shape=>shapeNames[shape]).join('、') || '暂无候选，先检查重复图形')
const lines = computed(()=>props.gameId==='picture-logic' ? pictureLines(round.value) : [])
const preview = computed(()=>props.gameId==='lights-out' && hovered.value>=0 ? lightPreview(round.value,hovered.value) : [])
function boardKeyboard(event:KeyboardEvent){
  if(round.value.finished || props.gameId!=='sliding-puzzle')return
  const delta={ArrowUp:round.value.size,ArrowDown:-round.value.size,ArrowLeft:1,ArrowRight:-1}[event.key]
  if(delta===undefined)return
  event.preventDefault();const index=round.value.cells.indexOf(0)+delta
  if(index>=0 && index<round.value.cells.length && isNeighbor(index))clickCell(index)
}
const hint = ref<{ index: number; text: string } | null>(null)
watch(hint,value=>{if(value)void revealGameHint()})

const feedback = ref(''), saveError = ref(false), helpOpen = ref(false), resetOpen = ref(false)
const targetDifficulty = ref<PuzzleDifficulty>('starter')
const history = ref<PuzzleRound[]>([])
const conflicts = computed(() => props.gameId === 'shape-sudoku' ? sudokuConflicts(round.value.cells) : [])
const clues = computed(() => pictureClues(round.value.solution, round.value.size))
const wet = computed(() => props.gameId === 'pipe-connect' ? pipeWater(round.value) : [])
const ports = computed(() => props.gameId === 'pipe-connect' ? [pipePort(round.value), pipePort(round.value, true)] : [])
const towers = computed(() => [0, 1, 2].map(peg => round.value.cells.flatMap((value, index) => value === peg ? [index + 1] : []).reverse()))
const difficulty = computed(() => puzzleDifficulties.find(item => item.id === save.value.difficulty)!)
const rules: Record<PuzzleId, string[]> = {
  'shape-sudoku': ['每行、每列和每个 2 × 2 小方框都要各有一个圆形、三角形、正方形和菱形。', '先选空格，再点下面的图形；浅色图形是已知条件，不能修改。', '红色边框表示图形重复。先找只缺一种图形的行或列。'],
  'sliding-puzzle': ['点击空格旁边的数字，把它移进空格。其他数字暂时不能移动。', '从左上角开始，按 1、2、3……排列，最后一格留空。', '先排好第一行，再处理下一行。可以撤回一步，慢慢尝试。'],
  'lights-out': ['点击一颗星星，它和上下左右的星星会一起改变亮暗。', '把所有星星点亮就过关。棋盘一定有解。', '同一位置点击两次会回到原来的样子，先观察再动手。'],
  'tower-hanoi': ['把全部圆盘搬到 C 柱，A、B 柱可以中转；后续关卡会从不同盘面出发。', '每次只能移动最上面的一个盘，大盘不能放在小盘上。', '先点来源柱，再点目标柱。想想怎样为最大的盘腾出路线。'],
  'picture-logic': ['行和列旁边的数字表示连续填色的格子数，例如 2、1 表示一组两格和一组一格。', '不同组之间至少隔一个空格；数字 0 表示这一行或列全部为空。', '用“填色”和“标空”完成每个格子，再次点击可以取消。所有行列都符合数字就过关。'],
  'pipe-connect': ['点击水管，每次顺时针转动四分之一圈。', '把进水口连到出水口，并让水流经过所有格子，不能留下漏口。', '蓝色表示水已经流到这里。先沿着进水口看看下一段应该朝哪个方向。'],
}
const prompts: Record<PuzzleId, string> = {
  'shape-sudoku': '每一行、每一列和小方框，都要有四种不同的图形。',
  'sliding-puzzle': '把数字排回顺序，右下角留出一个空格。',
  'lights-out': '一次点击改变一片星光，让所有星星一起亮起来。',
  'tower-hanoi': '小盘在上、大盘在下，慢慢把圆盘搬到 C 柱。',
  'picture-logic': '读懂边上的数字，发现藏在格子里的小图案。',
  'pipe-connect': '转一转水管，让清水经过每一格，流到出水口。',
}
function remember() { history.value.push(structuredClone({ ...round.value, cells: [...round.value.cells], initial: [...round.value.initial], solution: [...round.value.solution], fixed: [...round.value.fixed], route: [...round.value.route], plan: [...round.value.plan] })); if (history.value.length > 30) history.value.shift() }
function clearSelection() { selected.value = -1; peg.value = -1; hint.value = null; feedback.value = '' }
function acted(ok: boolean) {
  if (ok) { hint.value = null; feedback.value = round.value.finished ? '完成啦！你的观察和思考找到了答案。' : '' }
  else history.value.pop()
}
function clickCell(index: number) {
  if (round.value.finished) return
  if (props.gameId === 'shape-sudoku') { if (!round.value.fixed.includes(index)) selected.value = index; return }
  remember(); acted(playPuzzle(save.value, index, paint.value))
}
function chooseShape(value: number) {
  if (selected.value < 0) { feedback.value = '先选一个空格，再选择图形。'; return }
  remember(); acted(playPuzzle(save.value, selected.value, value))
}
function choosePeg(index: number) {
  if (round.value.finished) return
  if (peg.value < 0 || peg.value === index) {
    if (hanoiTop(round.value, index) < 0) { feedback.value = '这根柱子没有圆盘，先选另一根柱子。'; return }
    peg.value = peg.value === index ? -1 : index; feedback.value = ''; return
  }
  remember()
  if (moveHanoi(save.value, peg.value, index)) { peg.value = -1; acted(true) }
  else { history.value.pop(); feedback.value = '大圆盘不能放在小圆盘上。换一根柱子试试。' }
}
function undo() {
  const previous = history.value.pop()
  if (!previous || round.value.finished) return
  previous.moves = round.value.moves + 1; previous.hints = round.value.hints
  save.value.round = previous; clearSelection(); feedback.value = '已撤回一步，可以换个思路。'
}
function giveHint() { hint.value = puzzleHint(save.value); if (props.gameId === 'shape-sudoku' && hint.value) selected.value = hint.value.index }
function requestReset(id = save.value.difficulty) { targetDifficulty.value = id; resetOpen.value = true }
function reset() { nextPuzzle(save.value, targetDifficulty.value, targetDifficulty.value === save.value.difficulty && !round.value.finished); history.value = []; clearSelection(); resetOpen.value = false }
function next() { nextPuzzle(save.value); history.value = []; clearSelection() }
function checkPicture() {
  const conflict=lines.value.find(line=>line.state==='conflict')
  feedback.value = conflict ? `${conflict.name}的标记和数字不一致，先检查这一处。` : round.value.cells.includes(0) ? '还有格子没有确定。用“标空”记下不需要填色的位置。' : '还有行或列不符合数字，看看连续填色的长度和组与组之间的空格。'
}
function cellLabel(index: number) {
  const position = `第 ${Math.floor(index / round.value.size) + 1} 行第 ${index % round.value.size + 1} 列`
  if (props.gameId === 'shape-sudoku') return `${position}，${shapeNames[round.value.cells[index]]}${round.value.fixed.includes(index) ? '，已知图形' : ''}`
  if (props.gameId === 'sliding-puzzle') return round.value.cells[index] ? `移动数字 ${round.value.cells[index]}` : '空格'
  if (props.gameId === 'lights-out') return `${position}，星星${round.value.cells[index] ? '亮着' : '未亮'}`
  if (props.gameId === 'picture-logic') return `${position}，${['未确定', '已填色', '已标空'][round.value.cells[index]]}`
  return `${position}，旋转水管${ports.value[0]?.index === index ? '，进水口' : ports.value[1]?.index === index ? '，出水口' : ''}`
}
const isNeighbor = (index: number) => { const blank = round.value.cells.indexOf(0), size = round.value.size; return Math.abs(Math.floor(index / size) - Math.floor(blank / size)) + Math.abs(index % size - blank % size) === 1 }
function cellClasses(index: number) {
  return { preview:preview.value.includes(index), fixed: round.value.fixed.includes(index), chosen: selected.value === index, conflict: conflicts.value.includes(index), hinted: hint.value?.index === index, lit: props.gameId === 'lights-out' && !!round.value.cells[index], blank: props.gameId === 'sliding-puzzle' && round.value.cells[index] === 0, movable: props.gameId === 'sliding-puzzle' && isNeighbor(index), watered: wet.value.includes(index), filled: props.gameId === 'picture-logic' && round.value.cells[index] === 1, crossed: props.gameId === 'picture-logic' && round.value.cells[index] === 2, 'block-right': props.gameId === 'shape-sudoku' && index % 4 === 1, 'block-bottom': props.gameId === 'shape-sudoku' && Math.floor(index / 4) === 1 }
}
watch(save, value => { try { writeGameSave(key.value, value); saveError.value = false } catch { saveError.value = true } }, { deep: true, immediate: true, flush: 'post' })
watch(key, () => { save.value = readSave() || newPuzzle(props.gameId); history.value = []; clearSelection() })
</script>

<template>
  <div :class="['puzzle-play', gameId]">
    <GameNav :active="gameId" />
    <main class="puzzle-content">
      <header class="puzzle-heading">
        <div><span class="puzzle-kicker">益智乐园 · {{ game.skills }}</span><h1>{{ game.title }}<span>.</span></h1><p>{{ prompts[gameId] }}</p></div>
        <div class="puzzle-tools">
          <div class="puzzle-difficulties" role="group" aria-label="游戏难度"><button v-for="item in puzzleDifficulties" :key="item.id" :class="{ active: item.id === save.difficulty }" :aria-pressed="item.id === save.difficulty" @click="item.id !== save.difficulty && requestReset(item.id)">{{ item.name }}</button></div>
          <button class="help-button" aria-label="怎么玩" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" /></button>
        </div>
      </header>
      <section class="puzzle-stats" aria-label="游戏进度">
        <span><UIcon :name="game.icon" /><strong>{{ difficulty.name }}</strong><small>{{ gameId === 'tower-hanoi' ? `${round.size} 个圆盘` : `${round.size} × ${round.size} 棋盘` }}</small></span>
        <span>尝试步数<strong>{{ round.moves }}</strong></span><span>已完成<strong>{{ save.rounds }} 局</strong></span><span class="best-stars" :aria-label="`当前难度最佳 ${save.best[save.difficulty]} 颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></span>
      </section>
      <p v-if="saveError" class="puzzle-notice" role="alert">浏览器暂时无法保存进度，本局仍可继续。</p>
      <p class="challenge-stage">连续挑战 · 第 {{ round.stage || 1 }} 关<template v-if="gameId==='tower-hanoi'"> · {{ round.size }} 个圆盘 · 从不同位置继续搬运</template></p><div class="puzzle-layout">
        <section :class="['puzzle-stage', { night: gameId === 'lights-out' }]" :aria-label="`${game.title}棋盘`">
          <div class="stage-top"><span>{{ gameId === 'lights-out' ? '星光实验室' : gameId === 'pipe-connect' ? '清泉工坊' : gameId==='picture-logic'?pictureName(round.stage || 1):'今天的小小挑战' }}</span><span>{{ round.finished ? '已完成' : '慢慢想，不用赶' }}</span></div>
          <p v-if="gameId==='tower-hanoi'" class="brain-caption">从当前盘面到 C 柱，最少还需 {{ hanoiRemaining(round) }} 步。</p><p v-if="gameId==='sliding-puzzle'" class="brain-caption">数字距离目标合计 {{ slidingDistance(round) }} 格 · 方向键可移动数字</p><p v-if="gameId==='shape-sudoku' && selected>=0" class="brain-caption" aria-label="当前格候选">当前格可填：{{ candidateLabel }}</p><div v-if="gameId === 'tower-hanoi'" class="hanoi-board">
            <button v-for="(disks, index) in towers" :key="index" :class="['hanoi-peg', { selected: peg === index, hinted: hint?.index === index }]" :aria-label="`${'ABC'[index]} 柱，${disks.length} 个圆盘`" :aria-pressed="peg === index" :disabled="round.finished" @click="choosePeg(index)">
              <span class="peg-rod" aria-hidden="true" /><span class="peg-disks" aria-hidden="true"><span v-for="disk in disks" :key="disk" :class="`disk disk-${disk}`" :style="{ width: `${30 + disk / round.size * 60}%` }">{{ disk }}</span></span><strong>{{ 'ABC'[index] }}</strong><small>{{ index === 2 ? '终点' : index === 0 ? '起点' : '中转' }}</small>
            </button>
          </div>
          <div v-else-if="gameId === 'picture-logic'" class="picture-wrap">
            <table class="picture-board" aria-label="像素拼图数字线索"><thead><tr><td class="clue-corner" /><th v-for="(column, index) in clues.columns" :key="index" :class="{'clue-done':lines[round.size+index]?.state==='done','clue-conflict':lines[round.size+index]?.state==='conflict'}" scope="col" :aria-label="`第 ${index + 1} 列线索 ${column.join('、')}`"><span v-for="(number, order) in column" :key="order">{{ number }}</span></th></tr></thead><tbody><tr v-for="(row, y) in clues.rows" :key="y"><th :class="{'clue-done':lines[y]?.state==='done','clue-conflict':lines[y]?.state==='conflict'}" scope="row" :aria-label="`第 ${y + 1} 行线索 ${row.join('、')}`">{{ row.join(' ') }}</th><td v-for="x in round.size" :key="x"><button :class="['puzzle-cell', cellClasses(y * round.size + x - 1)]" :data-cell="y * round.size + x - 1" :aria-label="cellLabel(y * round.size + x - 1)" :disabled="round.finished" @click="clickCell(y * round.size + x - 1)"><span v-if="round.cells[y * round.size + x - 1] === 2" aria-hidden="true">×</span></button></td></tr></tbody></table>
          </div>
          <div v-else class="puzzle-grid" tabindex="0" aria-label="棋盘键盘控制" @keydown="boardKeyboard" :style="{ gridTemplateColumns: `repeat(${round.size}, minmax(0, 1fr))` }">
            <button v-for="(cell, index) in round.cells" :key="index" :class="['puzzle-cell', cellClasses(index)]" :data-cell="index" :aria-label="cellLabel(index)" :aria-pressed="gameId === 'shape-sudoku' ? selected === index : undefined" :disabled="round.finished || gameId === 'shape-sudoku' && round.fixed.includes(index) || gameId === 'sliding-puzzle' && !isNeighbor(index)" @mouseenter="hovered=index" @mouseleave="hovered=-1" @focus="hovered=index" @blur="hovered=-1" @click="clickCell(index)">
              <span v-if="gameId === 'shape-sudoku'" :class="`shape shape-${cell}`" aria-hidden="true">{{ shapes[cell] }}</span>
              <span v-else-if="gameId === 'sliding-puzzle'" aria-hidden="true">{{ cell || '' }}</span>
              <UIcon v-else-if="gameId === 'lights-out'" name="i-lucide-star" aria-hidden="true" />
              <template v-else><svg viewBox="0 0 100 100" aria-hidden="true"><g class="pipe-outline"><line v-for="bit in pipeBits.filter(bit => (cell & bit) !== 0)" :key="bit" x1="50" y1="50" :x2="bit === 2 ? 100 : bit === 8 ? 0 : 50" :y2="bit === 1 ? 0 : bit === 4 ? 100 : 50" /></g><g class="pipe-stream"><line v-for="bit in pipeBits.filter(bit => (cell & bit) !== 0)" :key="bit" x1="50" y1="50" :x2="bit === 2 ? 100 : bit === 8 ? 0 : 50" :y2="bit === 1 ? 0 : bit === 4 ? 100 : 50" /></g><circle cx="50" cy="50" r="7" class="pipe-joint" /></svg><span v-for="(port, order) in ports.filter(port => port.index === index)" :key="order" :class="['pipe-port', `port-${port.bit}`, { outlet: ports[1].index === index }]">{{ ports[1].index === index ? '出' : '入' }}</span></template>
            </button>
          </div>
          <div v-if="gameId === 'shape-sudoku'" class="shape-palette" role="group" aria-label="选择图形"><button v-for="value in 4" :key="value" :aria-label="`填入${shapeNames[value]}`" :disabled="round.finished" @click="chooseShape(value)"><span :class="`shape shape-${value}`" aria-hidden="true">{{ shapes[value] }}</span><small>{{ shapeNames[value] }}</small></button><button aria-label="清除当前格子" :disabled="round.finished || selected < 0" @click="chooseShape(0)"><UIcon name="i-lucide-eraser" /><small>清除</small></button></div>
          <div v-if="gameId === 'picture-logic'" class="paint-tools" role="group" aria-label="拼图标记方式"><button :aria-pressed="paint === 1" :class="{ active: paint === 1 }" :disabled="round.finished" @click="paint = 1"><UIcon name="i-lucide-paintbrush" />填色</button><button :aria-pressed="paint === 2" :class="{ active: paint === 2 }" :disabled="round.finished" @click="paint = 2"><UIcon name="i-lucide-x" />标空</button><button v-if="!round.finished" @click="checkPicture">检查拼图</button></div>
          <p v-if="gameId === 'shape-sudoku' && conflicts.length" class="conflict-note" role="status">红框内有重复图形，换一种试试看。</p>
          <div v-if="round.finished" class="puzzle-success" role="status" aria-label="过关反馈"><div class="success-stars" :aria-label="`本局获得 ${puzzleStars(round)} 颗星`"><UIcon v-for="n in puzzleStars(round)" :key="n" name="i-lucide-star" /></div><h2>你解开了这个小挑战！</h2><p>{{ round.moves }} 次尝试，每一步都有收获。</p><button class="primary-button" @click="next">前往下一关<UIcon name="i-lucide-arrow-right" /></button></div>
          <p class="puzzle-feedback" role="status" aria-label="操作反馈">{{ feedback || (gameId === 'tower-hanoi' && peg >= 0 ? `已选 ${'ABC'[peg]} 柱，再选要放入的柱子。` : gameId === 'shape-sudoku' && selected >= 0 ? '格子选好了，选择下面的一种图形。' : '') }}</p>
        </section>
        <aside class="puzzle-sidebar">
          <div class="thinking-card"><span class="sidebar-kicker"><UIcon name="i-lucide-lightbulb" />动动脑筋</span><h2>先观察，再试一试。</h2><p v-for="(rule, index) in rules[gameId]" :key="rule"><span class="rule-number">{{ index + 1 }}</span>{{ rule }}</p></div>
          <div v-if="hint && !round.finished" class="hint-card" role="status" aria-label="游戏提示"><strong><UIcon name="i-lucide-sparkles" />给你一点线索</strong><p>{{ hint.text }}</p></div>
          <div class="board-tools"><button :disabled="round.finished" @click="giveHint"><UIcon name="i-lucide-lightbulb" />给我提示</button><button :disabled="!history.length || round.finished" @click="undo"><UIcon name="i-lucide-undo-2" />撤回一步</button><button @click="requestReset()"><UIcon name="i-lucide-refresh-cw" />重新开始</button></div>
          <p class="puzzle-footnote"><UIcon name="i-lucide-leaf" />没有倒计时，想一想、歇一歇都可以。</p>
        </aside>
      </div>
    </main>
    <UModal v-model:open="helpOpen" :title="`${game.title}怎么玩`" description="按照自己的节奏，慢慢探索。"><template #body><ol class="help-rules"><li v-for="rule in rules[gameId]" :key="rule">{{ rule }}</li></ol></template><template #footer><button class="primary-button" @click="helpOpen = false">知道啦</button></template></UModal>
    <UModal v-model:open="resetOpen" :title="targetDifficulty === save.difficulty ? '重新开始这一局？' : `切换到${puzzleDifficulties.find(item => item.id === targetDifficulty)?.name}？`" description="重试保留本关布局；切换难度会进入新的路线。已完成关数和星星保留。"><template #footer><button class="secondary-button" @click="resetOpen = false">继续当前游戏</button><button class="primary-button" @click="reset">{{ targetDifficulty === save.difficulty && !round.finished ? '重试本关' : '开始新挑战' }}</button></template></UModal>
  </div>
</template>

<style scoped src="./puzzle-play.css"></style>
<style scoped>
.clue-done{color:#458456!important;background:#e7f3e5!important}.clue-conflict{color:#b45d45!important;background:#fff0e8!important}.puzzle-cell.preview{outline:2px dashed #dfbd64;outline-offset:-4px}.brain-caption{font-size:12px;line-height:1.8;text-align:center;margin:12px 0;color:#869375}.puzzle-grid:focus-visible{outline:2px dashed #a3b7a3;outline-offset:5px}
</style>
