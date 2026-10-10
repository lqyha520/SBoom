import { computed, isReactive, markRaw, toRaw, type ComputedRef } from 'vue'
import { deepClone } from './utils'

const copies = new WeakMap<object, ComputedRef<unknown>>()
const sizes = new WeakMap<object, number>()

/** 响应式树按节点保存不可变副本；修改一题只复制该题及其祖先。 */
export function immutableCopy<T>(value: T): T {
  if (!value || typeof value !== 'object') return value
  if (!isReactive(value) || (!Array.isArray(value) && Object.prototype.toString.call(value) !== '[object Object]')) return deepClone(value)
  const raw = toRaw(value)
  let cached = copies.get(raw)
  if (!cached) {
    cached = computed(() => markRaw(Array.isArray(value)
      ? value.map(item => immutableCopy(item))
      : Object.fromEntries(Object.entries(value).map(([key, item]) => [key, immutableCopy(item)]))))
    copies.set(raw, cached)
  }
  return cached.value as T
}

/** 共享节点直接比较引用；普通非响应式输入仍按内容去重。 */
export function sameSnapshot(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false
  const left = Object.entries(a), right = Object.entries(b)
  return left.length === right.length && left.every(([key, value]) => Object.prototype.hasOwnProperty.call(b, key) && sameSnapshot(value, (b as Record<string, unknown>)[key]))
}

/** 缓存不可变子树大小，避免每次编辑再序列化全部历史。 */
export function snapshotSize(value: unknown): number {
  if (!value || typeof value !== 'object') return JSON.stringify(value)?.length ?? 0
  const cached = sizes.get(value)
  if (cached !== undefined) return cached
  const size = Array.isArray(value)
    ? 2 + value.reduce((total, item) => total + snapshotSize(item) + 1, 0)
    : 2 + Object.entries(value).reduce((total, [key, item]) => total + JSON.stringify(key).length + snapshotSize(item) + 2, 0)
  sizes.set(value, size)
  return size
}
