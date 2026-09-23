/** 未读数读取按发起顺序更新；已读写入会使之前及写入期间的读取失效。 */
export function createUnreadTracker(currentEpoch: () => number, update: (count: number) => void) {
  let epoch = currentEpoch(), revision = 0, sequence = 0, applied = 0, writing = 0
  function scope() {
    if (epoch === currentEpoch()) return
    epoch = currentEpoch(); revision++; writing = 0; applied = 0
  }
  return {
    version() { scope(); return `${epoch}:${revision}` },
    changed() { scope(); revision++ },
    read() {
      scope()
      const owner = epoch, version = revision, ticket = ++sequence
      return (count: number, pending = 0) => {
        scope()
        if (owner !== epoch || version !== revision || writing || ticket < applied) return false
        applied = ticket; update(Math.max(0, count - pending)); return true
      }
    },
    write() {
      scope(); revision++; writing++
      const owner = epoch, ticket = ++sequence
      return (count?: number, pending = 0) => {
        scope()
        if (owner !== epoch) return false
        writing--; revision++
        if (count === undefined || ticket < applied) return false
        applied = ticket; update(Math.max(0, count - pending)); return true
      }
    },
  }
}
