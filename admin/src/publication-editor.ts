import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  reactive,
  ref,
  watch,
} from 'vue'
import { ApiError } from './api'
import { useCatalogImportQueue } from './catalog-import-queue'
import { useImagePdfComposer } from './image-pdf'
import {
  defaultDownloadSettings,
  downloadPayload,
  downloadSettingsIssue,
} from './download-settings'
import {
  catalogDetail,
  catalogSources,
  createPublication,
  updatePublication,
  type CatalogDetail,
  type CatalogImportMeta,
  type CatalogPaper,
  type CatalogSource,
  type PublicationEdit,
  type PublicationStatus,
} from './catalog'
import { createCategory, siteCategories, siteDictionary } from './site'
import { useBeforeUnload } from './unsaved'
import { useAdminLeaveGuard } from './navigation'

const answerReadiness: Record<string, string> = {
  included: '原稿包含答案',
  separate: '已关联答案版',
  missing: '未配套',
  unknown: '待核对',
}
export const publicationLabels: Record<PublicationStatus, string> = {
  draft: '草稿',
  published: '已发布',
  withdrawn: '已下架',
}
export const publicationStatuses = [
  { label: '全部状态', value: 'all' },
  ...Object.entries(publicationLabels).map(([value, label]) => ({
    label,
    value,
  })),
]
export type PublicationSection = 'details' | 'metadata' | 'editions' | 'revision'

export function usePublicationEditor(
  userId: number,
  created: (paper: CatalogDetail, existingOnly?: boolean) => void,
  saved: (notice: string, revealCreated?: boolean) => Promise<void>,
) {
  const categories = ref<{ label: string; value: string }[]>([])
  const filterCategories = ref<{ label: string; value: string }[]>([])
  const statuses = publicationStatuses
  const message = (cause: unknown) =>
    cause instanceof Error ? cause.message : '操作失败，请重试'
  const dialog = ref(false)
  const section = ref<PublicationSection>('details')
  const target = ref<CatalogPaper | null>(null)
  const saving = ref(false)
  const categoryName = ref('')
  const categoryCreating = ref(false)
  const imageComposer = useImagePdfComposer()
  const imageFields = reactive({
    grade: '',
    subject: '',
    category_id: '',
    mode: 'student' as CatalogImportMeta['mode'],
  })
  const active = ref(true)

  const importQueue = useCatalogImportQueue(userId, created)
  const busy = computed(
    () => saving.value || categoryCreating.value || importQueue.busy || imageComposer.busy,
  )
  const dialogError = ref('')
  const dialogNotice = ref('')
  const editConflict = ref(false)
  const pendingImport = computed(
    () =>
      busy.value ||
      importQueue.rows.some(
        (item) => !item.created || (!!item.answer && item.answerState !== 'succeeded'),
      ) ||
      imageComposer.pages.length > 0,
  )
  const form = ref<PublicationEdit>({
    ...defaultDownloadSettings(),
    revision: 1,
    title: '',
    description: '',
    category_id: '',
    status: 'draft',
    featured: false,
    confirm_publication: false,
    view_access: 'inherit',
    download_access: 'inherit',
  })
  const accessOptions = [
    { label: '继承题型权限', value: 'inherit' },
    { label: '普通用户与 VIP', value: 'free' },
    { label: '仅 VIP 会员', value: 'vip' },
  ]
  watch(
    () => form.value.view_access,
    (value) => {
      if (value === 'vip') form.value.download_access = 'vip'
    },
    { flush: 'sync' },
  )
  const sourceQuery = ref('')
  const sources = ref<CatalogSource[]>([])
  const sourceId = ref('')
  const sourceMore = ref(false)
  const sourceLoading = ref(false)
  let sourceSequence = 0
  const sourceItems = computed(() =>
    sources.value.map((item) => ({
      value: item.id,
      label: `${item.title} · ${item.grade} · v${item.version}${item.file_status !== 'ready' ? ' · 文件未完成' : ''}`,
    })),
  )
  const mode = ref<'source' | 'import' | 'images' | 'link'>('source')
  const initialForm = ref('')
  const formSnapshot = () =>
    JSON.stringify({
      form: form.value,
      mode: mode.value,
      sourceId: sourceId.value,
      imageFields,
      imageTitle: imageComposer.title,
      categoryName: categoryName.value,
    })
  const dirty = computed(
    () =>
      dialog.value &&
      !!initialForm.value &&
      formSnapshot() !== initialForm.value,
  )
  const unsaved = computed(
    () => active.value && (dirty.value || pendingImport.value),
  )
  const markSaved = () => {
    initialForm.value = formSnapshot()
  }
  useBeforeUnload(unsaved)
  useAdminLeaveGuard(
    () =>
      !active.value || (!saving.value && !categoryCreating.value && (!unsaved.value ||
      window.confirm(
        pendingImport.value
          ? '导入尚未完成，离开会停止队列；未保存的表单修改也会丢失。确认离开？'
          : '有未保存的修改，确认放弃并离开？',
      ))),
  )
  function setDialogOpen(open: boolean): boolean {
    if (busy.value) return false
    if (
      !open &&
      dirty.value &&
      !window.confirm('有未保存的修改，确认放弃并关闭？')
    )
      return false
    dialog.value = open
    return true
  }
  watch(mode, (value) => {
    if (value === 'link') form.value.download_mode = 'external'
  })
  const gradeOptions = ref<{ label: string; value: string }[]>([])
  const subjectOptions = ref<{ label: string; value: string }[]>([])
  const dictionaryError = ref('')
  const categoryError = ref('')
  const dictionaryLoading = ref(false)
  const categoryLoading = ref(false)
  async function addCategory() {
    if (!categoryName.value.trim() || categoryCreating.value) return
    categoryCreating.value = true
    try {
      const item = await createCategory(userId, { name: categoryName.value.trim(), description: '', icon: '', sort_order: 0, is_visible: true })
      categories.value.push({ label: item.name, value: item.id })
      filterCategories.value.push({ label: item.name, value: item.id })
      form.value.category_id = item.id
      imageFields.category_id = item.id
      categoryName.value = ''
      categoryError.value = ''
    } catch (cause) { dialogError.value = message(cause) }
    finally { categoryCreating.value = false }
  }
  async function loadDictionaryOptions() {
    if (dictionaryLoading.value) return
    dictionaryLoading.value = true
    dictionaryError.value = ''
    try {
      const [grades, subjects] = await Promise.all([
        siteDictionary('grade'),
        siteDictionary('subject'),
      ])
      gradeOptions.value = grades.items.map((item) => ({
        label: item.label || item.value,
        value: item.value,
      }))
      subjectOptions.value = subjects.items.map((item) => ({
        label: item.label || item.value,
        value: item.value,
      }))
    } catch {
      dictionaryError.value = '年级与科目加载失败，请重试后继续填写'
    } finally {
      dictionaryLoading.value = false
    }
  }
  const publishing = computed(
    () =>
      !!target.value &&
      form.value.status === 'published' &&
      target.value.status !== 'published',
  )
  const importing = computed(
    () => !target.value && ['import', 'images'].includes(mode.value),
  )
  const valid = computed(
    () =>
      !categoryLoading.value &&
      !categoryError.value &&
      (importing.value
        ? !dictionaryLoading.value &&
          !dictionaryError.value &&
          (mode.value === 'images'
            ? imageComposer.ready &&
              !!imageFields.grade &&
              !!imageFields.subject &&
              !!imageFields.category_id &&
              !downloadSettingsIssue(form.value)
            : importQueue.pending.length > 0)
        : !!form.value.title.trim() &&
          !!form.value.category_id &&
          !downloadSettingsIssue(form.value) &&
          (!!target.value ||
            (mode.value === 'link'
              ? !dictionaryLoading.value &&
                !dictionaryError.value &&
                !!imageFields.grade &&
                !!imageFields.subject
              : !!sourceId.value))) &&
      (!publishing.value || form.value.confirm_publication),
  )

  async function loadCategories() {
    if (categoryLoading.value) return
    categoryLoading.value = true
    categoryError.value = ''
    try {
      const result = (await siteCategories()).items
      filterCategories.value = result.map(item => ({ label: item.name + (item.is_visible ? '' : '（隐藏）'), value: item.id }))
      categories.value = result
        .filter((item) => item.is_visible)
        .map((item) => ({ label: item.name, value: item.id }))
    } catch {
      categoryError.value = '分类加载失败，请重试后继续填写'
    } finally {
      categoryLoading.value = false
    }
  }

  async function loadSources(more = false) {
    const current = ++sourceSequence
    sourceLoading.value = true
    dialogError.value = ''
    try {
      const result = await catalogSources(
        sourceQuery.value.trim(),
        more ? sources.value.length : 0,
      )
      if (current !== sourceSequence) return
      sources.value = more ? [...sources.value, ...result.items] : result.items
      sourceMore.value = result.has_more
    } catch (cause) {
      if (current === sourceSequence) dialogError.value = message(cause)
    } finally {
      if (current === sourceSequence) sourceLoading.value = false
    }
  }
  function create() {
    if (busy.value) return
    if (importQueue.rows.length && !target.value && mode.value === 'import') {
      dialog.value = true
      return
    }
    if (
      imageComposer.pages.length &&
      !target.value &&
      mode.value === 'images'
    ) {
      dialog.value = true
      return
    }
    target.value = null
    categoryName.value = ''
    section.value = 'details'
    mode.value = 'source'
    sourceId.value = ''
    sourceQuery.value = ''
    sources.value = []
    Object.assign(imageFields, {
      grade: '',
      subject: '',
      category_id: '',
      mode: 'student',
    })
    imageComposer.title = ''
    dialogError.value = ''
    dialogNotice.value = ''
    form.value = {
      ...defaultDownloadSettings(),
      revision: 1,
      title: '',
      description: '',
      category_id: categories.value[0]?.value || '',
      status: 'draft',
      featured: false,
      confirm_publication: false,
      view_access: 'inherit',
      download_access: 'inherit',
    }
    dialog.value = true
    markSaved()
    void loadSources()
    void loadDictionaryOptions()
  }
  function edit(item: CatalogPaper, nextSection: PublicationSection = 'details') {
    if (busy.value) return
    if (
      dirty.value &&
      !window.confirm('有未保存的修改，确认放弃并编辑另一份资料？')
    )
      return
    target.value = item
    categoryName.value = ''
    section.value = nextSection
    dialogError.value = ''
    dialogNotice.value = ''
    editConflict.value = false
    form.value = {
      ...downloadPayload(item),
      revision: item.revision,
      title: item.title,
      description: item.description,
      category_id: item.category_id || '',
      status: item.status,
      featured: item.featured,
      confirm_publication: false,
      view_access: item.view_access,
      download_access: item.download_access,
    }
    dialog.value = true
    markSaved()
  }
  watch(sourceId, (id) => {
    const item = sources.value.find((source) => source.id === id)
    if (item) form.value.title = item.title
  })
  async function save() {
    if (busy.value || !valid.value) return
    if (!target.value && mode.value === 'images') {
      await saveImages()
      return
    }
    if (importing.value) {
      await runImport()
      return
    }
    saving.value = true
    dialogError.value = ''
    dialogNotice.value = ''
    try {
      if (target.value) {
        const result = await updatePublication(userId, target.value.id, {
          ...form.value,
          ...downloadPayload(form.value),
          title: form.value.title.trim(),
        })
        target.value = result
        form.value.revision = result.revision
        form.value.title = result.title
        form.value.confirm_publication = false
        markSaved()
        created(result, true)
        dialogNotice.value =
          '公共习题已更新 · ' + publicationLabels[result.status]
        await saved(dialogNotice.value)
      } else {
        const result = await createPublication(userId, {
          ...downloadPayload(form.value),
          paper_id: mode.value === 'link' ? '' : sourceId.value,
          ...(mode.value === 'link'
            ? { grade: imageFields.grade, subject: imageFields.subject }
            : {}),
          title: form.value.title.trim(),
          description: form.value.description,
          category_id: form.value.category_id,
          view_access: form.value.view_access,
          download_access: form.value.download_access,
        })
        created(result)
        target.value = result
        form.value.title = result.title
        form.value.revision = result.revision
        form.value.status = result.status
        form.value.confirm_publication = false
        markSaved()
        dialogNotice.value = '习题草稿已创建'
        await saved(dialogNotice.value)
      }
    } catch (cause) {
      editConflict.value = cause instanceof ApiError && cause.status === 409
      dialogError.value = message(cause)
    } finally {
      saving.value = false
    }
  }
  async function reloadEdited() {
    if (!target.value) return
    try {
      const latest = await catalogDetail(target.value.id)
      target.value = latest
      form.value.revision = latest.revision
      form.value.confirm_publication = false
      editConflict.value = false
      dialogNotice.value = '已载入最新版本，您的修改已保留，请核对后保存'
    } catch (cause) {
      dialogError.value = message(cause)
    }
  }
  async function refreshTarget() {
    if (!target.value) return null
    const id = target.value.id
    const latest = await catalogDetail(id)
    if (target.value?.id !== id) return null
    // 子面板保存只更新并发版本，不覆盖主表单尚未保存的字段。
    const baseline = initialForm.value ? JSON.parse(initialForm.value) : null
    target.value = latest
    form.value.revision = latest.revision
    if (baseline) {
      baseline.form.revision = latest.revision
      initialForm.value = JSON.stringify(baseline)
    }
    created(latest, true)
    await saved('资料已更新')
    return latest
  }
  async function runImport(retry = false) {
    if (
      busy.value ||
      categoryError.value ||
      dictionaryError.value ||
      categoryLoading.value ||
      dictionaryLoading.value
    )
      return
    await importQueue.run(
      {
        description: form.value.description,
        view_access: form.value.view_access,
        download_access: form.value.download_access,
      },
      retry,
    )
    markSaved()
    await saved(`已创建 ${importQueue.succeeded} 份草稿，可预览并发布`)
  }
  async function saveImages() {
    const title = imageComposer.title.trim()
    const file = await imageComposer.build()
    if (!file || !active.value) return
    saving.value = true
    dialogError.value = ''
    try {
      await importQueue.add([file], {
        ...imageFields,
        ...downloadPayload(form.value),
      })
      const row = importQueue.rows.find((item) => item.file === file)
      if (!row || row.fileError) {
        dialogError.value = row?.fileError || 'PDF 未能加入导入清单，请重试'
        return
      }
      row.meta.title = title
      imageComposer.clear()
      mode.value = 'import'
      if (!active.value) return
      await importQueue.run(
        {
          description: form.value.description,
          view_access: form.value.view_access,
          download_access: form.value.download_access,
        },
        false,
        row.id,
      )
      markSaved()
      await saved(
        row.created
          ? '图片已合并成一份 PDF 并创建草稿，可预览并发布'
          : 'PDF 已合并，请在导入清单中重试上传',
      )
    } catch (cause) {
      dialogError.value = message(cause)
    } finally {
      saving.value = false
    }
  }

  onActivated(() => {
    active.value = true
    void loadCategories()
    void loadDictionaryOptions()
  })
  onDeactivated(() => {
    active.value = false
    imageComposer.cancel()
    importQueue.stop()
    sourceSequence++
    sourceLoading.value = false
    dialog.value = false
  })
  onBeforeUnmount(() => {
    active.value = false
    imageComposer.dispose()
    importQueue.stop()
  })
  return reactive({
    dialog,
    userId,
    section,
    refreshTarget,
    categoryName,
    categoryCreating,
    addCategory,
    dirty,
    setDialogOpen,
    target,
    busy,
    pendingImport,
    saving,
    imageComposer,
    imageFields,
    importQueue,
    form,
    sourceQuery,
    sources,
    sourceId,
    sourceMore,
    sourceLoading,
    sourceItems,
    mode,
    gradeOptions,
    subjectOptions,
    dictionaryError,
    categoryError,
    dictionaryLoading,
    categoryLoading,
    categories,
    filterCategories,
    publishing,
    importing,
    valid,
    accessOptions,
    statuses,
    answerReadiness,
    dialogError,
    dialogNotice,
    editConflict,
    loadCategories,
    loadDictionaryOptions,
    loadSources,
    create,
    edit,
    save,
    reloadEdited,
    runImport,
  })
}
