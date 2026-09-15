export function createLatestRequest() {
  let sequence = 0
  return {
    begin() {
      const current = ++sequence
      return () => current === sequence
    },
    invalidate() { sequence++ },
  }
}
