<script setup lang="ts">
import { permissionDirective as vPermission, canPermission } from '../permissions'
import { useAdminLeaveGuard, useAdminListRoute } from "../navigation";
import { computed, onActivated, onDeactivated, ref, watch } from "vue";
import { ApiError, type UserInfo } from "../api";
import { useBeforeUnload } from "../unsaved";
import {
  getFeedback,
  getFeedbackDetail,
  saveFeedback,
  statusOptions,
  kindLabels,
  type Feedback,
} from "../experience";
import { catalogDetail, type CatalogDetail } from "../catalog";
const props = defineProps<{ user: UserInfo }>();
const status = ref("pending");
const page = ref(1);
const total = ref(0);
const items = ref<Feedback[]>([]);
const selected = ref<Feedback | null>(null);
const dialog = ref(false);
const preview = ref<CatalogDetail | null>(null);
const previewOpen = ref(false);
const busy = ref(false);
const loading = ref(false);
const error = ref("");
const formError = ref("");
const notice = ref("");
let sequence = 0;
const feedbackConflict = ref(false);
const latestFeedback = ref<Feedback | null>(null);
const feedbackBaseline = ref("");
const feedbackValue = () => selected.value ? JSON.stringify([selected.value.status, selected.value.reply, selected.value.internal_note]) : "";
const feedbackDirty = computed(() => feedbackValue() !== feedbackBaseline.value);
const dirty = feedbackDirty;
const active = ref(true);
useBeforeUnload(computed(() => active.value && dirty.value));
useAdminLeaveGuard(() => !active.value || (!busy.value && (!dirty.value || window.confirm('有未保存的反馈回复，确认离开？'))));
function closeFeedback() {
  if (busy.value || (feedbackDirty.value && !window.confirm("放弃尚未保存的反馈回复？"))) return;
  selected.value = null;
  feedbackBaseline.value = "";
  dialog.value = false;
}
function handleDialogOpenChange(value: boolean) {
  if (!value) closeFeedback();
}
async function reloadFeedback() {
  if (!selected.value || busy.value) return;
  busy.value = true;
  const selectedId = selected.value.id;
  try {
    const latest = await getFeedbackDetail(selectedId);
    if (!active.value || selected.value?.id !== selectedId) return;
    latestFeedback.value = latest;
    selected.value = { ...latest, status: selected.value.status, reply: selected.value.reply, internal_note: selected.value.internal_note };
    feedbackConflict.value = false;
    formError.value = "已载入最新版本，您的修改已保留，请核对后保存";
  } catch (cause) {
    if (active.value && selected.value?.id === selectedId) formError.value = message(cause);
  } finally {
    busy.value = false;
  }
}
const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : "操作失败，请重试";
async function load() {
  const current = ++sequence;
  loading.value = true;
  error.value = "";
  try {
    const data = await getFeedback(
      status.value === "all" ? "" : status.value,
      (page.value - 1) * 20,
    );
    if (current === sequence) {
      items.value = data.items;
      total.value = data.total;
    }
  } catch (cause) {
    if (current === sequence) error.value = message(cause);
  } finally {
    if (current === sequence) loading.value = false;
  }
}
onActivated(() => {
  active.value = true;
  void load();
});
onDeactivated(() => {
  active.value = false;
  sequence++;
  dialog.value = false;
  previewOpen.value = false;
});
const routeState = useAdminListRoute("supportCenter", { status, page }, () => {
  void load();
});
watch(page, load);
watch(status, () => {
  if (routeState.restoring) return;
  if (page.value === 1) void load();
  else page.value = 1;
});
function edit(item: Feedback) {
  if (feedbackDirty.value) {
    if (selected.value?.id === item.id) { dialog.value = true; return; }
    if (!window.confirm("放弃尚未保存的反馈回复？")) return;
  }
  selected.value = { ...item };
  feedbackBaseline.value = feedbackValue();
  formError.value = "";
  feedbackConflict.value = false;
  latestFeedback.value = null;
  dialog.value = true;
}
async function save() {
  if (busy.value || !selected.value) return;
  if (
    ["resolved", "closed"].includes(selected.value.status) &&
    !selected.value.reply.trim()
  ) {
    formError.value = "解决或关闭反馈前请填写回复";
    return;
  }
  busy.value = true;
  formError.value = "";
  try {
    await saveFeedback(props.user.id, selected.value);
    feedbackBaseline.value = feedbackValue();
    dialog.value = false;
    notice.value = "处理结果已保存，用户可在小程序查看回复";
    await load();
  } catch (cause) {
    feedbackConflict.value = cause instanceof ApiError && cause.status === 409;
    formError.value = message(cause);
  } finally {
    busy.value = false;
  }
}
async function inspect() {
  if (!selected.value?.catalog_id) return;
  formError.value = "";
  try {
    preview.value = await catalogDetail(selected.value.catalog_id);
    previewOpen.value = true;
  } catch (cause) {
    formError.value = message(cause);
  }
}
</script>
<template>
  <section class="admin-section">
    <UAlert v-if="error" :title="error" color="error" class="notice" /><UAlert
      v-if="notice"
      :title="notice"
      color="success"
      class="notice"
    />
    <div class="section-toolbar">
        <USelect
          v-model="status"
          :items="[{ label: '全部状态', value: 'all' }, ...statusOptions]"
          aria-label="反馈状态"
        /><UButton
          label="刷新"
          color="neutral"
          variant="outline"
          :loading="loading"
          @click="load"
        />
      </div>
      <div class="data-scroll">
        <table class="data-table action-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>当前身份</th>
              <th>问题</th>
              <th>资料</th>
              <th>状态</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.id">
              <td>{{ item.nickname || item.username }}</td>
              <td>
                <UBadge :color="item.is_vip ? 'warning' : 'neutral'" variant="soft">
                  {{ item.is_vip ? 'VIP 会员' : '普通用户' }}
                </UBadge>
                <div v-if="item.membership_status === 'expired'" class="feedback-membership-note">会员已到期</div>
              </td>
              <td>
                <strong>{{ kindLabels[item.kind] }}</strong>
                <div class="feedback-excerpt">{{ item.body }}</div>
              </td>
              <td>{{ item.paper_title || "—" }}</td>
              <td>
                {{
                  statusOptions.find((value) => value.value === item.status)
                    ?.label
                }}
              </td>
              <td>{{ new Date(item.updated_at * 1000).toLocaleString() }}</td>
              <td>
                <UButton
                  label="处理与回复"
                  variant="soft"
                  @click="edit(item)"
                />
              </td>
            </tr>
            <tr v-if="!items.length">
              <td colspan="7">
                {{ loading ? "正在加载" : "暂无符合条件的反馈" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <UPagination
        v-if="total > 20"
        v-model:page="page"
        :total="total"
        :items-per-page="20"
        class="mt-4"
    />
    <UModal
      :open="dialog"
      @update:open="handleDialogOpenChange"
      title="处理小程序反馈"
      :dismissible="!busy"
      :close="!busy"
      ><template #body
        ><form
          v-if="selected"
          id="feedback-reply"
          class="field-stack"
          @submit.prevent="canPermission('supportCenter:update') && (save())"
        >
          <div class="feedback-original">
            <strong
              >{{ selected.nickname || selected.username }} ·
              {{ kindLabels[selected.kind] }}</strong
            >
            <div class="feedback-identity">
              <span>当前身份</span>
              <UBadge :color="selected.is_vip ? 'warning' : 'neutral'" variant="soft">
                {{ selected.is_vip ? 'VIP 会员' : '普通用户' }}
              </UBadge>
              <span v-if="selected.membership_status === 'expired'">会员已到期</span>
            </div>
            <p>{{ selected.body }}</p>
            <p v-if="selected.paper_title">
              关联资料：{{ selected.paper_title }}
            </p>
            <UButton v-permission="'papers:view'"
              v-if="selected.catalog_id"
              label="查看关联资料"
              variant="outline"
              @click="inspect"
            />
          </div>
          <UFormField label="处理状态"
            ><USelect
 :disabled="!canPermission('supportCenter:update')"              v-model="selected.status"
              :items="statusOptions" /></UFormField
          ><UFormField label="回复用户"
            ><UTextarea
 :disabled="!canPermission('supportCenter:update')"              v-model="selected.reply"
              :maxlength="2000"
              :rows="4"
              class="w-full"
              placeholder="这段回复会显示在用户的小程序中" /></UFormField
          ><UFormField label="内部处理备注"
            ><UTextarea
 :disabled="!canPermission('supportCenter:update')"              v-model="selected.internal_note"
              :maxlength="2000"
              :rows="3"
              class="w-full"
              placeholder="仅后台可见" /></UFormField
          ><div v-if="latestFeedback" class="feedback-original">
            <strong>服务器最新回复</strong>
            <p>{{ statusOptions.find(value => value.value === latestFeedback?.status)?.label }}</p>
            <p>{{ latestFeedback.reply || '尚无回复' }}</p>
            <p>{{ latestFeedback.internal_note || '无内部备注' }}</p>
          </div><UButton
            v-if="feedbackConflict"
            label="载入最新并保留我的修改"
            @click="reloadFeedback"
          /><UAlert
            v-if="formError"
            :title="formError"
            color="error"
          /></form></template
      ><template #footer
        ><UButton
          label="取消"
          color="neutral"
          :disabled="busy"
          @click="closeFeedback" /><UButton v-permission="'supportCenter:update'"
          type="submit"
          form="feedback-reply"
          label="保存处理结果"
          :loading="busy" /></template
    ></UModal>
    <UModal v-model:open="previewOpen" :title="preview?.title || '关联资料'"
      ><template #body
        ><template v-if="preview"
          ><p>{{ preview.grade }} · {{ preview.subject }}</p>
          <img
            v-for="asset in preview.assets
              .filter((item) => item.kind === 'page')
              .slice(0, 6)"
            :key="asset.id"
            :src="asset.url"
            alt="资料原稿"
            class="w-full my-3"
            loading="lazy" /></template></template
    ></UModal>
  </section>
</template>
<style scoped>
.feedback-identity {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  color: var(--ui-text-muted);
  font-size: 12px;
}
.feedback-membership-note {
  margin-top: 6px;
  color: var(--ui-text-muted);
  font-size: 12px;
}
.feedback-excerpt {
  max-width: 300px;
  white-space: normal;
  overflow-wrap: anywhere;
  margin-top: 6px;
}
.feedback-original p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.7;
  margin: 12px 0;
}
</style>
