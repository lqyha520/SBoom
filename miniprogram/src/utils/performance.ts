/**
 * 防抖函数 - 减少函数执行频率
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null
  
  return function(this: any, ...args: Parameters<T>) {
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(() => {
      func.apply(this, args)
    }, wait)
  }
}

/**
 * 节流函数 - 限制函数执行频率
 */
export function throttle<T extends (...args: any[]) => any>(
  func: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle: boolean
  
  return function(this: any, ...args: Parameters<T>) {
    if (!inThrottle) {
      func.apply(this, args)
      inThrottle = true
      setTimeout(() => inThrottle = false, limit)
    }
  }
}

/**
 * 图片懒加载工具 - 增强版
 */
export function lazyLoadImage(
  imageUrl: string,
  options?: {
    quality?: number
    format?: 'webp' | 'jpeg' | 'png'
    width?: number
    height?: number
  }
): string {
  const { quality = 80, format = 'webp', width, height } = options || {}
  
  // 构建优化参数
  const params = new URLSearchParams()
  params.append('quality', quality.toString())
  params.append('format', format)
  if (width) params.append('width', width.toString())
  if (height) params.append('height', height.toString())
  
  // 这里可以添加图片处理逻辑，比如添加 CDN 参数
  // 实际使用时需要根据你的 CDN 配置调整
  if (imageUrl.includes('?')) {
    return `${imageUrl}&${params.toString()}`
  }
  return `${imageUrl}?${params.toString()}`
}

/**
 * 图片预加载
 */
export function preloadImage(imageUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = imageUrl
  })
}

/**
 * 批量预加载图片
 */
export async function preloadImages(imageUrls: string[], concurrency: number = 3): Promise<void> {
  const chunks: string[][] = []
  for (let i = 0; i < imageUrls.length; i += concurrency) {
    chunks.push(imageUrls.slice(i, i + concurrency))
  }
  
  for (const chunk of chunks) {
    await Promise.all(chunk.map(url => preloadImage(url).catch(() => {})))
  }
}

/**
 * 格式化文件大小
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
}

/**
 * 缓存键生成
 */
export function getCacheKey(key: string, userId?: string): string {
  const prefix = userId ? `lc_${userId}_` : 'lc_'
  return prefix + key
}

/**
 * 本地存储封装
 */
export const storage = {
  get<T>(key: string, defaultValue?: T): T | null {
    try {
      const value = uni.getStorageSync(key)
      return value ? JSON.parse(value) : defaultValue || null
    } catch {
      return defaultValue || null
    }
  },
  
  set(key: string, value: any): void {
    try {
      uni.setStorageSync(key, JSON.stringify(value))
    } catch (e) {
      console.error('Storage set error:', e)
    }
  },
  
  remove(key: string): void {
    try {
      uni.removeStorageSync(key)
    } catch (e) {
      console.error('Storage remove error:', e)
    }
  },
  
  clear(): void {
    try {
      uni.clearStorageSync()
    } catch (e) {
      console.error('Storage clear error:', e)
    }
  }
}

/**
 * 网络请求重试工具
 */
export async function retryRequest<T>(
  requestFn: () => Promise<T>,
  maxRetries: number = 3,
  delay: number = 1000
): Promise<T> {
  let lastError: Error
  
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      lastError = error as Error
      if (i < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, delay * (i + 1)))
      }
    }
  }
  
  throw lastError!
}

/**
 * 触觉反馈
 */
export function vibrate(pattern: number | number[] = 10): void {
  // #ifdef MP-WEIXIN
  uni.vibrateShort?.(pattern)
  // #endif
}

/**
 * 页面预加载
 */
export function preloadPage(url: string): void {
  // #ifdef MP-WEIXIN
  uni.preloadPage?.({
    url
  })
  // #endif
}

/**
 * 虚拟滚动工具 - 用于大列表性能优化
 */
export interface VirtualScrollOptions {
  itemHeight: number
  containerHeight: number
  totalItems: number
  overscan?: number
}

export interface VirtualScrollResult {
  visibleStart: number
  visibleEnd: number
  offsetY: number
  visibleItems: number[]
}

export function calculateVirtualScroll(
  scrollTop: number,
  options: VirtualScrollOptions
): VirtualScrollResult {
  const { itemHeight, containerHeight, totalItems, overscan = 3 } = options
  
  const visibleCount = Math.ceil(containerHeight / itemHeight)
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan)
  const endIndex = Math.min(totalItems - 1, startIndex + visibleCount + overscan * 2)
  const offsetY = startIndex * itemHeight
  
  const visibleItems: number[] = []
  for (let i = startIndex; i <= endIndex; i++) {
    visibleItems.push(i)
  }
  
  return {
    visibleStart: startIndex,
    visibleEnd: endIndex,
    offsetY,
    visibleItems
  }
}

/**
 * Intersection Observer 工具 - 用于图片懒加载
 */
export function createIntersectionObserver(
  callback: IntersectionObserverCallback,
  options?: IntersectionObserverInit
): IntersectionObserver {
  return new IntersectionObserver(callback, {
    rootMargin: '50px',
    threshold: 0.01,
    ...options
  })
}

/**
 * 资源清理工具
 */
export class ResourceCleaner {
  private resources: Array<() => void> = []
  
  register(cleanup: () => void): void {
    this.resources.push(cleanup)
  }
  
  cleanup(): void {
    this.resources.forEach(cleanup => {
      try {
        cleanup()
      } catch (error) {
        console.error('Resource cleanup error:', error)
      }
    })
    this.resources = []
  }
}

/**
 * 性能监控
 */
export class PerformanceMonitor {
  private marks: Map<string, number> = new Map()
  
  mark(name: string): void {
    this.marks.set(name, Date.now())
  }
  
  measure(name: string, startMark: string, endMark?: string): number {
    const start = this.marks.get(startMark)
    const end = endMark ? this.marks.get(endMark) : Date.now()
    
    if (start && end) {
      const duration = end - start
      console.log(`[Performance] ${name}: ${duration}ms`)
      return duration
    }
    return 0
  }
  
  clear(): void {
    this.marks.clear()
  }
}

// 导出单例
export const perfMonitor = new PerformanceMonitor()
