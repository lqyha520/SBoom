import { onMounted, ref, watch, type Ref } from 'vue'
import { TYPE_NAME } from './constants'
import { MAX_WORKSHEET_IMAGES } from './generation-limits'
import type { ImageWorksheetParams } from './image-generation'

export function validImageDraft(value: unknown): value is ImageWorksheetParams {
  const v = value as ImageWorksheetParams | null
  return (
    !!v &&
    typeof v.grade === 'string' &&
    typeof v.subject === 'string' &&
    typeof v.keyword === 'string' &&
    v.keyword.length <= 100 &&
    typeof v.requirements === 'string' &&
    ['easy', 'medium', 'hard'].includes(v.difficulty) &&
    ['playful', 'clean', 'black_white'].includes(v.style) &&
    Array.isArray(v.items) &&
    v.items.length <= 5 &&
    v.items.every(
      (item) =>
        item &&
        typeof item.game_type === 'string' &&
        !!TYPE_NAME[item.game_type] &&
        (item.question_count == null ||
          (Number.isInteger(item.question_count) && item.question_count >= 1 && item.question_count <= 20))
    ) &&
    (v.image_count === undefined ||
      (Number.isInteger(v.image_count) && v.image_count >= 1 && v.image_count <= MAX_WORKSHEET_IMAGES))
  )
}

/** 配置恢复与批次恢复分离，加载期间不把默认值覆盖到已保存草稿。 */
export function useImageDraft(
  params: Readonly<Ref<ImageWorksheetParams>>,
  storageKey: string,
  current: () => boolean,
  applyParams: (params: ImageWorksheetParams) => void
) {
  const draftKey = storageKey + '_draft',
    draftLoaded = ref(false),
    draftStatus = ref('')
  watch(
    params,
    () => {
      if (!draftLoaded.value || !current()) return
      try {
        localStorage.setItem(draftKey, JSON.stringify(params.value))
        draftStatus.value = '配置已保存到本机'
      } catch {
        draftStatus.value = '配置未能保存，请勿刷新页面'
      }
    },
    { flush: 'sync' }
  )
  onMounted(() => {
    let draft: unknown
    try {
      draft = JSON.parse(localStorage.getItem(draftKey) || 'null')
    } catch {
      /* 忽略损坏的配置草稿。 */
    }
    if (validImageDraft(draft)) {
      applyParams(draft)
      draftStatus.value = '已恢复本机配置'
    } else {
      try {
        const previous = JSON.parse(localStorage.getItem(storageKey) || 'null')
        if (validImageDraft(previous?.input))
          applyParams({ ...previous.input, image_count: previous.pages?.length || 1 })
      } catch {
        /* 无有效历史配置时保留默认值。 */
      }
    }
    draftLoaded.value = true
  })
  return { draftLoaded, draftStatus }
}
