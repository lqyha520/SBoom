<script setup lang="ts">
import type { ImagePdfComposer } from '../image-pdf'
const props = defineProps<{ composer: ImagePdfComposer; disabled: boolean }>()
async function pick(event: Event) {
  const input = event.target as HTMLInputElement, files = Array.from(input.files || [])
  input.value = ''; if (!props.disabled) await props.composer.add(files)
}
</script>
<template>
  <div class="image-composer">
    <p class="text-sm text-muted">多张图片合成一份 PDF，每张图一页。按下方顺序排列，可调整顺序和旋转；图片等比居中放入 A4 页面，不裁切，横竖方向随图片调整。</p>
    <UFormField label="添加图片" hint="支持 JPG、PNG、WebP；最多 40 张，每张不超过 20 MB，合计不超过 200 MB。">
      <UInput type="file" multiple accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" aria-label="添加图片" :disabled="disabled || composer.busy" @change="pick" />
    </UFormField>
    <UFormField label="公开标题" required><UInput v-model="composer.title" maxlength="240" aria-label="图片合成习题标题" placeholder="例如：三年级数学练习" :disabled="disabled || composer.busy" class="w-full" /></UFormField>
    <div class="actions-row"><span class="text-sm">{{ composer.pages.length }} 张图片 → {{ composer.pages.length }} 页 PDF</span><UButton v-if="composer.pages.length" label="清空图片" variant="ghost" color="neutral" :disabled="disabled || composer.busy" @click="composer.clear" /></div>
    <p v-if="composer.progress" role="status">{{ composer.progress }}</p>
    <UAlert v-if="composer.error" :title="composer.error" color="error" />
    <ol class="image-pages" aria-label="图片页面顺序">
      <li v-for="(page, index) in composer.pages" :key="page.id" class="image-page">
        <div class="image-preview"><img v-if="page.preview" :src="page.preview" :alt="'第 ' + (index + 1) + ' 页预览'" :style="{ transform: 'rotate(' + page.rotation + 'deg)' }" /><UIcon v-else name="i-lucide-image-off" class="size-8 text-muted" /></div>
        <strong>第 {{ index + 1 }} 页 · {{ page.file.name }}</strong>
        <p v-if="page.error" class="text-xs text-error" role="alert">{{ page.error }}</p><span v-else class="text-xs text-muted">{{ page.width }} × {{ page.height }} · 已旋转 {{ page.rotation }}°</span>
        <div class="actions-row"><UButton icon="i-lucide-arrow-up" :aria-label="'上移第 ' + (index + 1) + ' 张图片'" color="neutral" variant="outline" size="xs" :disabled="disabled || composer.busy || index === 0" @click="composer.move(index, -1)" /><UButton icon="i-lucide-arrow-down" :aria-label="'下移第 ' + (index + 1) + ' 张图片'" color="neutral" variant="outline" size="xs" :disabled="disabled || composer.busy || index === composer.pages.length - 1" @click="composer.move(index, 1)" /><UButton icon="i-lucide-rotate-cw" :aria-label="'旋转第 ' + (index + 1) + ' 张图片'" color="neutral" variant="outline" size="xs" :disabled="disabled || composer.busy || !!page.error" @click="composer.rotate(page.id)" /><UButton icon="i-lucide-x" :aria-label="'移除第 ' + (index + 1) + ' 张图片'" color="neutral" variant="ghost" size="xs" :disabled="disabled || composer.busy" @click="composer.remove(page.id)" /></div>
      </li>
    </ol>
  </div>
</template>
<style scoped>
.image-composer{display:grid;gap:16px}.image-pages{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.image-page{display:flex;flex-direction:column;gap:10px;padding:12px;border:1px solid var(--ui-border);border-radius:10px}.image-page strong{font-size:13px;overflow-wrap:anywhere}.image-preview{height:180px;display:flex;align-items:center;justify-content:center;background:var(--ui-bg-muted);overflow:hidden;border-radius:6px}.image-preview img{max-width:125px;max-height:125px;object-fit:contain}.image-page .actions-row{margin-top:auto}@media(max-width:720px){.image-pages{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:420px){.image-pages{grid-template-columns:1fr}}
</style>
