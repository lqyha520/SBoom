import { games, gameKey, type GameId } from './catalog'

export const GAME_SAVE_EVENT = 'lc:game-save'
export function writeGameSave(key: string, value: unknown) {
  const raw = JSON.stringify(value)
  const changed = localStorage.getItem(key) !== raw
  localStorage.setItem(key, raw)
  if (changed) {
    try { localStorage.setItem(key + ':played', String(Date.now())) } catch { /* 主存档已保存，最近游玩时间允许缺失。 */ }
    window.dispatchEvent(new CustomEvent(GAME_SAVE_EVENT, { detail: { key } }))
  }
}

export function localProgress(id: GameId, owner: string) {
  try {
    const key = gameKey(id, owner), raw = localStorage.getItem(key)
    if (!raw) return null
    const value = JSON.parse(raw)
    if (!value || value.version !== 1) return null
    const count = (input: unknown, max = 999999) => typeof input === 'number' && Number.isFinite(input) ? Math.max(0, Math.min(max, Math.floor(input))) : 0
    const playedAt = count(Number(localStorage.getItem(key + ':played')), Number.MAX_SAFE_INTEGER)
    let label = '已有本机进度'
    if (id === 'little-shop') label = `营业第 ${Math.max(1, count(value.day))} 天 · 接待 ${count(value.lifetimeServed)} 位顾客`
    else if (id === 'robot-maze') label = `第 ${Math.min(36, count(value.level) + 1)} 关 · 已获 ${Array.isArray(value.stars) ? value.stars.reduce((sum: number, n: unknown) => sum + count(n, 3), 0) : 0} 星`
    else if (id === 'creative-studio') label = `画廊 ${count(value.round?.gallery?.length,12)} 幅作品 · 当前 ${count(value.round?.marks?.length,64)} 笔`
    else if (id === 'little-farm') label = `第 ${Math.max(1,count(value.round?.day))} 天 · 收获 ${count(value.round?.harvested)} 次`
    else if (id === 'forest-rescue') label = `帮助 ${count(value.round?.rescued?.length,3)} 只动物 · 完成 ${count(value.rounds)} 轮`
    else if (id === 'animal-catch') label = `已接到 ${count(value.round?.caught)} 份食物 · 完成 ${count(value.rounds)} 轮`
    else {
      const best = value.best && typeof value.best === 'object' ? Math.max(0, ...Object.values(value.best).map(n => count(n, 3))) : 0
      const total = count(value.rounds ?? value.flights), round=value.round || value.flight
      const difficulty={starter:'入门',explorer:'进阶',master:'挑战',cozy:'轻松',focus:'专注',pilot:'乘法'}[value.difficulty as string] || ''
      const stage=Math.max(1,count(round?.stage || total+1))
      const part=typeof round?.index==='number' && Array.isArray(round.questions) && !round.finished ? ` · 第 ${Math.min(round.questions.length,round.index+1)} 题` : ''
      label = `${difficulty}${round?.finished?' · 已通关':` · 第 ${stage} 关${part}`} · 最佳 ${best} 星`
    }
    return { id, label, playedAt }
  } catch { return null }
}
export const recentGames = (owner: string) => games.map(game => localProgress(game.id, owner)).filter(value => value !== null).sort((a, b) => b.playedAt - a.playedAt)
