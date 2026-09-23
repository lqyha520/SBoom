export interface RequestScope { onCancel(callback: () => void): () => void }
export function createLatestRequest() {
  let sequence = 0
  const callbacks = new Set<() => void>()
  function invalidate() { sequence++; for (const cancel of callbacks) cancel(); callbacks.clear() }
  return {
    begin() {
      invalidate()
      const current = sequence
      return Object.assign(() => current === sequence, {
        onCancel(callback: () => void) {
          if (current !== sequence) { callback(); return () => {} }
          callbacks.add(callback)
          return () => { callbacks.delete(callback) }
        },
      })
    },
    invalidate,
  }
}
