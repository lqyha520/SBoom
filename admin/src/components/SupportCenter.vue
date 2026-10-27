<script setup lang="ts">
import { useAdminLeaveGuard, useAdminListRoute } from "../navigation";
import { computed, onActivated, onDeactivated, ref, watch } from "vue";
import { ApiError, type UserInfo } from "../api";
import { useBeforeUnload } from "../unsaved";
import {
  getSupport,
  saveSupport,
  getFeedback,
  getFeedbackDetail,
  saveFeedback,
  statusOptions,
  kindLabels,
  type Feedback,
  type SupportSettings,
} from "../experience";
import { catalogDetail, type CatalogDetail } from "../catalog";
const props = defineProps<{ user: UserInfo }>();
const tab = ref("feedback");
const status = ref("pending");
const page = ref(1);
const total = ref(0);
const items = ref<Feedback[]>([]);
const settings = ref<SupportSettings | null>(null);
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
let settingsSequence = 0;
const settingsBaseline = ref("");
const contactConflict = ref(false);
const feedbackConflict = ref(false);
const latestFeedback = ref<Feedback | null>(null);
const settingsDirty = computed(
  () =>
    !!settings.value &&
    JSON.stringify(settings.value) !== settingsBaseline.value,
);
const feedbackBaseline = ref("");
const feedbackValue = () => selected.value ? JSON.stringify([selected.value.status, selected.value.reply, selected.value.internal_note]) : "";
const feedbackDirty = computed(() => feedbackValue() !== feedbackBaseline.value);
const dirty = computed(() => settingsDirty.value || feedbackDirty.value);
const active = ref(true);
useBeforeUnload(computed(() => active.value && dirty.value));
useAdminLeaveGuard(() => !active.value || (!busy.value && (!dirty.value || window.confirm('有未保存的服务设置或反馈回复，确认离开？'))));
function closeFeedback() {
  if (busy.value || (feedbackDirty.value && !window.confirm("放弃尚未保存的反馈回复？"))) return;
  selected.value = null;
  feedbackBaseline.value = "";
  dialog.value = false;
}
function handleDialogOpenChange(value: boolean) {
  if (!value) closeFeedback();
}
function updateContact(field: Exclude<keyof SupportSettings, 'revision'>, value: string | number | undefined) {
  if (settings.value) settings.value[field] = String(value ?? '');
}
async function loadSettings(preserve = false) {
  const id = ++settingsSequence;
  try {
    const latest = await getSupport();
    if (id !== settingsSequence) return;
    if (preserve && settings.value) {
      settings.value.revision = latest.revision;
      contactConflict.value = false;
      notice.value = '已载入最新版本，您的修改已保留，请核对后保存';
    } else if (!settingsDirty.value) settings.value = latest;
    settingsBaseline.value = JSON.stringify(latest);
  } catch (cause) {
    error.value = message(cause);
  }
}
async function reloadFeedback() {
  if (!selected.value || busy.value) return;
  busy.value = true;
  const selectedId = selected.value.id;
  try {
    const latest = await getFeedbackDetail(selectedId);
    if (!active.value || selected.value?.id !== selectedId) return;
    latestFeedback.value = latest;
    selected.value.revision = latest.revision;
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
  void loadSettings();
});
onDeactivated(() => {
  active.value = false;
  sequence++;
  settingsSequence++;
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
async function saveContact() {
  if (busy.value || !settings.value) return;
  if (
    settings.value.phone &&
    !/^[0-9+() -]{0,40}$/.test(settings.value.phone)
  ) {
    error.value = "联系电话只能包含数字、空格和 + ( ) -，最多 40 位";
    return;
  }
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    settings.value = await saveSupport(props.user.id, settings.value);
    settingsBaseline.value = JSON.stringify(settings.value);
    contactConflict.value = false;
    notice.value = "会员权益和联系方式已更新";
  } catch (cause) {
    contactConflict.value = cause instanceof ApiError && cause.status === 409;
    error.value = message(cause);
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
    <UTabs
      v-model="tab"
      :items="[
        { label: '小程序反馈', value: 'feedback' },
        { label: '会员与联系设置', value: 'support' },
      ]"
      :content="false"
    />
    <UButton
      v-if="contactConflict"
      label="载入最新并保留我的修改"
      @click="loadSettings(true)"
    /><UAlert v-if="error" :title="error" color="error" class="notice" /><UAlert
      v-if="notice"
      :title="notice"
      color="success"
      class="notice"
    />
    <template v-if="tab === 'feedback'"
      ><div class="section-toolbar">
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
              <td colspan="6">
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
    /></template>
    <form
      v-else-if="settings"
      class="field-stack support-settings"
      @submit.prevent="saveContact"
    >
      <UFormField label="会员权益说明"
        ><UTextarea
          :model-value="settings?.benefits"
          @update:model-value="updateContact('benefits', $event)"
          :rows="5"
          :maxlength="2000"
          class="w-full" /></UFormField
      ><UFormField label="客服微信号"
        ><UInput
          :model-value="settings?.wechat"
          @update:model-value="updateContact('wechat', $event)"
          maxlength="80"
          class="w-full" /></UFormField
      ><UFormField label="联系电话"
        ><UInput
          :model-value="settings?.phone"
          @update:model-value="updateContact('phone', $event)"
          maxlength="40"
          class="w-full" /></UFormField
      ><UFormField label="联系邮箱"
        ><UInput
          :model-value="settings?.email"
          @update:model-value="updateContact('email', $event)"
          type="email"
          maxlength="120"
          class="w-full" /></UFormField
      ><UFormField label="客服二维码地址"
        ><UInput
          :model-value="settings?.qr_url"
          @update:model-value="updateContact('qr_url', $event)"
          maxlength="500"
          placeholder="https://... 或本地可访问地址"
          class="w-full" /></UFormField
      ><UFormField label="服务时间"
        ><UInput
          :model-value="settings?.hours"
          @update:model-value="updateContact('hours', $event)"
          maxlength="120"
          placeholder="例如：工作日 9:00-18:00"
          class="w-full"
      /></UFormField>
      <p class="text-sm text-muted">
        联系方式可以留空；配置二维码地址后，小程序会员页会直接展示二维码。
      </p>
      <UButton type="submit" label="保存服务信息" :loading="busy" />
    </form>
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
          @submit.prevent="save"
        >
          <div class="feedback-original">
            <strong
              >{{ selected.nickname || selected.username }} ·
              {{ kindLabels[selected.kind] }}</strong
            >
            <p>{{ selected.body }}</p>
            <p v-if="selected.paper_title">
              关联资料：{{ selected.paper_title }}
            </p>
            <UButton
              v-if="selected.catalog_id"
              label="查看关联资料"
              variant="outline"
              @click="inspect"
            />
          </div>
          <UFormField label="处理状态"
            ><USelect
              v-model="selected.status"
              :items="statusOptions" /></UFormField
          ><UFormField label="回复用户"
            ><UTextarea
              v-model="selected.reply"
              :maxlength="2000"
              :rows="4"
              class="w-full"
              placeholder="这段回复会显示在用户的小程序中" /></UFormField
          ><UFormField label="内部处理备注"
            ><UTextarea
              v-model="selected.internal_note"
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
          @click="closeFeedback" /><UButton
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
.support-settings {
  max-width: 640px;
  margin-top: 24px;
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
