/** 后台分类图标可选集合；未知图标回退，避免字体子集遗漏导致空白。 */
export const categoryIcons = ['book', 'copy', 'edit', 'file', 'folder', 'star', 'heart', 'apps', 'history', 'time-line', 'tags', 'check', 'check-circle', 'search-line', 'idcard', 'formula', 'translate', 'download', 'list', 'tag'] as const
export function categoryIcon(value: string, fallback = 'book') {
  return (categoryIcons as readonly string[]).includes(value) ? value : fallback
}
