import { computed, ref } from 'vue'
import type { CatalogPaper } from './catalog'

/** 跨分页保留选择和选择时的修订号；显式刷新后才能覆盖他人的修改。 */
export function useCatalogSelection() {
  const selected = ref<CatalogPaper[]>([])
  const ids = computed(() => selected.value.map(item => item.id))
  function toggle(item: CatalogPaper) {
    if (ids.value.includes(item.id)) selected.value = selected.value.filter(value => value.id !== item.id)
    else if (selected.value.length < 50) selected.value.push({ ...item })
    else return false
    return true
  }
  function page(items: CatalogPaper[], checked: boolean) {
    if (!checked) { const ids = new Set(items.map(item => item.id)); selected.value = selected.value.filter(item => !ids.has(item.id)); return true }
    const added = items.filter(item => !ids.value.includes(item.id))
    if (selected.value.length + added.length > 50) return false
    selected.value.push(...added.map(item => ({ ...item }))); return true
  }
  return { selected, ids, toggle, page, clear: () => { selected.value = [] } }
}
