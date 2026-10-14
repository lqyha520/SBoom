/** 固定名称、每阶段最多 60 条本地计时，不记录题目或账号，不自动上传。 */
type ExportStage = 'layout' | 'rasterize' | 'encode' | 'assemble'

export async function measureExport<T>(stage: ExportStage, run: () => Promise<T>): Promise<T> {
  const started = performance.now()
  try { return await run() }
  finally {
    try {
      const name = `lc.export.${stage}`
      if (performance.getEntriesByName(name, 'measure').length >= 60) performance.clearMeasures(name)
      performance.measure(name, { start: started, duration: performance.now() - started })
    } catch { /* 旧浏览器不支持 User Timing Level 3 时仍须完成导出。 */ }
  }
}
