<script setup lang="ts">
import { computed, ref } from 'vue'
import { navigateAdmin, type AdminTab } from '../navigation'
import { getTutorial } from '../xhs-workspace'
import { workflowError, type WorkflowKind } from '../xhs-workflow'
const props = defineProps<{ userId: number }>()
const open = ref(false), index = ref(0), busy = ref(false), error = ref(''), records = ref<Partial<Record<WorkflowKind, string>>>({}), checked = ref<number[]>([])
const key = () => `xhs-guide-v1:${props.userId}`
const steps: { title: string; text: string; outcome: string; action: string; tab: AdminTab; kind?: WorkflowKind }[] = [
  { title: '1 · 找一个具体问题', text: '例如“一年级孩子会接着写数字，却说不清变化规律”。先选一个账号，用“找规律”采集参考内容。没有账号也可以先看示例选题。', outcome: '找出一个读者问题，不照搬参考笔记。', action: '打开选题调研', tab: 'xhsResearch' },
  { title: '2 · 明确选题', text: '示例是“先示范，再练习，最后说出理由”。填写目标读者、问题和自己的切入点，点击“保存并制作资料”。', outcome: '得到一份具体的内容计划。', action: '打开示例选题', tab: 'xhsIdeas', kind: 'ideas' },
  { title: '3 · 做出资料', text: '示例题为 1、2、3、__，答案是 4，每次增加 1。检查题目、答案与讲解，完善后完成复核，可导出练习 PDF。', outcome: '得到读者可以实际使用的原创资料。', action: '打开示例资料', tab: 'xhsMaterials', kind: 'materials' },
  { title: '4 · 制作笔记', text: '选择账号定位，调整发布标题、正文和话题。检查封面与内页，也可从素材库应用已核实来源的模板。', outcome: '准备好文案和有序配图。', action: '打开示例笔记', tab: 'xhsDrafts', kind: 'drafts' },
  { title: '5 · 检查并手动发布', text: '填写账号和时间，在日历检查排期。完成版权、事实、隐私等复核后，选择素材并辅助填入。最终由你在小红书确认发布，成功后登记真实链接和时间。', outcome: '得到一条真实、可追踪的发布记录。示例本身不会自动发帖。', action: '打开示例发布计划', tab: 'xhsPublishing', kind: 'publications' },
  { title: '6 · 复盘并安排下一篇', text: '实际发布后的第 1、3、7 天录入浏览、收藏和互动数据，写下读者反馈。点击“复盘转选题”，检查建议后加入选题库。', outcome: '根据实际反馈形成下一轮内容计划。不要把示例当成已发布数据。', action: '打开效果复盘', tab: 'xhsAnalytics' },
]
const current = computed(() => steps[index.value]!)
async function show() { open.value = true; error.value = ''; try { const saved = JSON.parse(localStorage.getItem(key()) || '[]'); checked.value = Array.isArray(saved) ? saved.filter(value => Number.isInteger(value) && value >= 0 && value < steps.length) : [] } catch { checked.value = [] }; try { records.value = (await getTutorial()).records } catch (cause) { error.value = workflowError(cause) } }
async function create() { busy.value = true; error.value = ''; try { records.value = (await getTutorial(true)).records } catch (cause) { error.value = workflowError(cause) } finally { busy.value = false } }
function remember(value: boolean) { checked.value = value ? [...new Set([...checked.value, index.value])] : checked.value.filter(item => item !== index.value); try { localStorage.setItem(key(), JSON.stringify(checked.value)) } catch { error.value = '当前浏览器无法保存引导进度，本次仍可继续。' } }
function go() { const step = current.value, id = step.kind && records.value[step.kind]; open.value = false; navigateAdmin(step.tab, id ? { id } : {}) }
function publishPhotos() { open.value = false; navigateAdmin('xhsPublishing', { new: '1' }) }
</script>
<template><UButton label="新手引导" icon="i-lucide-book-open" color="neutral" variant="ghost" size="sm" @click="show" /><UModal v-model:open="open" title="用一套示例走完内容制作" :ui="{content:'max-w-3xl'}"><template #body><div class="getting-started"><div class="workflow-step"><strong>已经有图片，只想发图文？</strong><p>选图片、填写标题正文，预览后去小红书发布。</p><UButton label="直接发图文" @click="publishPhotos" /></div><p>下面的完整示例适合从选题开始制作内容。</p><p>示例会创建标有“示例”的选题、资料、笔记和未发布计划。它们可以修改；重复点击不会重复创建，也不会覆盖你的编辑。</p><UButton :label="records.ideas?'检查并补齐示例':'创建入门示例'" :loading="busy" variant="outline" @click="create" /><div class="guide-steps"><UButton v-for="(step,i) in steps" :key="step.title" :label="(checked.includes(i)?'✓ ':'')+step.title" :variant="i===index?'solid':'ghost'" @click="index=i" /></div><article><h3>{{ current.title }}</h3><p>{{ current.text }}</p><p><strong>这一步的目标：</strong>{{ current.outcome }}</p><UCheckbox :model-value="checked.includes(index)" label="我已了解这一步" @update:model-value="remember(Boolean($event))" /><p class="workflow-hint">此勾选仅记录学习进度，不会修改内容的完成、发布或复盘状态。</p><UButton :label="current.action" :disabled="!!current.kind && !records[current.kind]" @click="go" /></article><div class="workflow-actions"><UButton label="上一步" variant="outline" :disabled="index===0" @click="index--" /><span>{{ index+1 }} / {{ steps.length }}</span><UButton label="下一步" variant="outline" :disabled="index===steps.length-1" @click="index++" /></div><UAlert v-if="error" :title="error" color="error" /></div></template></UModal></template>
<style scoped>.getting-started{display:grid;gap:18px}.getting-started p{font-size:14px;line-height:1.8;color:var(--ui-text-muted)}.guide-steps{display:flex;flex-wrap:wrap;gap:6px}.getting-started article{display:grid;gap:16px;padding:20px;border:1px solid var(--ui-border);border-radius:14px}.getting-started h3{font-size:18px;font-weight:650}</style>
