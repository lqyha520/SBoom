<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as api from '../api'
import type { AdminFeedback, AdminStats, AdminUser, UserInfo } from '../api'
import UserTemplatesDialog from './UserTemplatesDialog.vue'

const props = defineProps<{ user: UserInfo }>()
const emit = defineEmits<{ (e: 'logout'): void }>()

const tab = ref<'overview' | 'llm' | 'users' | 'feedback' | 'logs'>('overview')
const stats = ref<AdminStats | null>(null)
const users = ref<AdminUser[]>([])
const query = ref('')
const msg = ref({ text: '', ok: true })
const flashTimer = ref(0)

// 模型配置
const llm = ref({ baseUrl: '', model: '', apiKey: '', timeout: 60 })
const llmHasKey = ref(false)
const llmMsg = ref({ text: '', ok: true })
const llmBusy = ref<'save' | 'test' | 'clear' | ''>('')

const newUser = ref({ username: '', password: '', role: 'user' })
const creating = ref(false)

const logs = ref('')
const logLines = ref(200)
const logLoading = ref(false)

// 用户反馈
const feedbacks = ref<AdminFeedback[]>([])
const fbOobOnly = ref(false)
const fbLoading = ref(false)

// 查看用户模板
const tplUser = ref<AdminUser | null>(null)

function flash(text: string, ok = true) {
  msg.value = { text, ok }
  clearTimeout(flashTimer.value)
  flashTimer.value = window.setTimeout(() => { msg.value = { text: '', ok: true } }, 3500)
}

async function loadStats() {
  stats.value = await api.fetchAdminStats()
}
async function loadUsers() {
  users.value = await api.fetchAdminUsers(query.value.trim())
}
async function refreshAll() {
  try { await Promise.all([loadStats(), loadUsers()]) }
  catch (e: any) { flash(e?.message || '加载失败', false) }
}

function switchTab(t: 'overview' | 'llm' | 'users' | 'feedback' | 'logs') {
  tab.value = t
  if (t === 'logs') loadLogs()
  if (t === 'llm') loadLlmConfig()
  if (t === 'feedback') loadFeedbacks()
}

/* ── 全局模型配置 ── */
async function loadLlmConfig() {
  try {
    const c = await api.fetchLlmConfig()
    llm.value = { baseUrl: c.baseUrl, model: c.model, apiKey: '', timeout: c.timeout || 60 }
    llmHasKey.value = c.hasKey
  } catch (e: any) {
    llmMsg.value = { text: '配置加载失败：' + (e?.message || e), ok: false }
  }
}

async function saveLlm() {
  if (llmBusy.value) return
  llmBusy.value = 'save'
  llmMsg.value = { text: '', ok: true }
  try {
    const r = await api.saveLlmConfig({
      baseUrl: llm.value.baseUrl.trim(),
      model: llm.value.model.trim(),
      apiKey: llm.value.apiKey.trim(),
      timeout: Number(llm.value.timeout) || 60,
    })
    llmHasKey.value = r.hasKey
    llm.value.apiKey = '' // 密钥已存服务端，表单不保留
    llmMsg.value = { text: r.message || '已保存', ok: true }
    await loadStats()
  } catch (e: any) {
    llmMsg.value = { text: '保存失败：' + (e?.message || e), ok: false }
  } finally {
    llmBusy.value = ''
  }
}

async function testLlmConn() {
  if (llmBusy.value) return
  llmBusy.value = 'test'
  llmMsg.value = { text: '', ok: true }
  try {
    const d = await api.testLlm({
      baseUrl: llm.value.baseUrl.trim(),
      model: llm.value.model.trim(),
      apiKey: llm.value.apiKey.trim(), // 空串则后端用已保存密钥
      timeout: Number(llm.value.timeout) || 60,
    })
    llmMsg.value = { text: '连接成功！模型回复：' + d.reply, ok: true }
  } catch (e: any) {
    llmMsg.value = { text: '连接失败：' + (e?.message || e), ok: false }
  } finally {
    llmBusy.value = ''
  }
}

/** 清除全局模型配置（含密钥）：换服务商/密钥疑似泄露时使用 */
async function clearLlm() {
  if (llmBusy.value) return
  if (!confirm('确定清除全局模型配置吗？已保存的密钥将被删除，全体用户将无法生成题目，需要重新配置。')) return
  llmBusy.value = 'clear'
  llmMsg.value = { text: '', ok: true }
  try {
    await api.clearLlmConfig()
    llmHasKey.value = false
    llmMsg.value = { text: '已清除模型配置', ok: true }
    await loadStats()
  } catch (e: any) {
    llmMsg.value = { text: '清除失败：' + (e?.message || e), ok: false }
  } finally {
    llmBusy.value = ''
  }
}

async function createUser() {
  const u = newUser.value.username.trim()
  const p = newUser.value.password
  if (!u || !p) { flash('请填写用户名和密码', false); return }
  if (p.length < 6) { flash('密码至少 6 位', false); return }
  creating.value = true
  try {
    await api.adminCreateUser({ username: u, password: p, role: newUser.value.role })
    flash(`用户「${u}」已创建`)
    newUser.value = { username: '', password: '', role: 'user' }
    await Promise.all([loadUsers(), loadStats()])
  } catch (e: any) {
    flash(e?.message || '创建失败', false)
  } finally {
    creating.value = false
  }
}

async function resetPassword(u: AdminUser) {
  const p = window.prompt(`为「${u.username}」设置新密码（至少 6 位）：`)
  if (p == null) return
  if (p.length < 6) { flash('密码至少 6 位', false); return }
  try {
    await api.adminUpdateUser(u.id, { password: p })
    flash(`已重置「${u.username}」的密码`)
  } catch (e: any) { flash(e?.message || '操作失败', false) }
}

async function toggleActive(u: AdminUser) {
  const to = !u.is_active
  if (to === false && !window.confirm(`确定禁用「${u.username}」？其会话将立即失效。`)) return
  try {
    await api.adminUpdateUser(u.id, { is_active: to })
    await Promise.all([loadUsers(), loadStats()])
  } catch (e: any) { flash(e?.message || '操作失败', false) }
}

async function toggleRole(u: AdminUser) {
  const to = u.role === 'admin' ? 'user' : 'admin'
  if (!window.confirm(`确定将「${u.username}」${to === 'admin' ? '提升为管理员' : '降级为普通用户'}？`)) return
  try {
    await api.adminUpdateUser(u.id, { role: to })
    await Promise.all([loadUsers(), loadStats()])
  } catch (e: any) { flash(e?.message || '操作失败', false) }
}

async function removeUser(u: AdminUser) {
  if (!window.confirm(`确定删除用户「${u.username}」？其模板与模型配置将一并删除，不可恢复。`)) return
  try {
    await api.adminDeleteUser(u.id)
    flash(`已删除用户「${u.username}」`)
    await Promise.all([loadUsers(), loadStats()])
  } catch (e: any) { flash(e?.message || '删除失败', false) }
}

async function loadLogs() {
  logLoading.value = true
  try {
    logs.value = await api.fetchAdminLogs(logLines.value)
  } catch (e: any) {
    logs.value = '日志加载失败：' + (e?.message || e)
  } finally {
    logLoading.value = false
  }
}

async function loadFeedbacks() {
  fbLoading.value = true
  try {
    feedbacks.value = await api.fetchAdminFeedbacks(200, fbOobOnly.value)
  } catch (e: any) {
    flash(e?.message || '反馈加载失败', false)
  } finally {
    fbLoading.value = false
  }
}

async function doLogout() {
  await api.logout()
  emit('logout')
}

onMounted(refreshAll)
</script>

<template>
  <div class="admin-page">
    <header class="admin-topbar">
      <div class="admin-brand">
        <span class="admin-logo">🛠</span>
        <div>
          <div class="admin-title">后台管理</div>
          <div class="admin-sub">管理员：{{ props.user.username }}</div>
        </div>
      </div>
      <div style="margin-left:auto; display:flex; gap:8px; align-items:center;">
        <div v-if="msg.text" class="admin-msg" :class="msg.ok ? 'ok' : 'err'">{{ msg.text }}</div>
        <button class="btn mini" @click="refreshAll">↻ 刷新</button>
        <a class="btn mini" href="/" target="_self">出题工作台 ↗</a>
        <button class="btn mini" @click="doLogout">退出登录</button>
      </div>
    </header>

    <nav class="admin-tabs">
      <button :class="{ on: tab === 'overview' }" @click="switchTab('overview')">📊 概览</button>
      <button :class="{ on: tab === 'llm' }" @click="switchTab('llm')">⚙ 模型配置</button>
      <button :class="{ on: tab === 'users' }" @click="switchTab('users')">👥 用户管理</button>
      <button :class="{ on: tab === 'feedback' }" @click="switchTab('feedback')">💬 用户反馈</button>
      <button :class="{ on: tab === 'logs' }" @click="switchTab('logs')">📄 系统日志</button>
    </nav>

    <main class="admin-body">
      <!-- 概览 -->
      <section v-if="tab === 'overview' && stats" class="tab-pane">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-num">{{ stats.users }}</div>
            <div class="stat-label">注册用户</div>
            <div class="stat-extra">{{ stats.activeUsers }} 启用 · {{ stats.admins }} 管理员</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">{{ stats.templates }}</div>
            <div class="stat-label">用户模板</div>
            <div class="stat-extra">跨设备同步存储</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">{{ stats.llmConfigured ? '✓' : '—' }}</div>
            <div class="stat-label">全局模型服务</div>
            <div class="stat-extra">{{ stats.llmConfigured ? '后台已配置' : '未配置，前往「模型配置」' }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">{{ stats.feedbacks }}</div>
            <div class="stat-label">用户反馈</div>
            <div class="stat-extra">{{ stats.feedbacksOob }} 条超纲反馈</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">✓</div>
            <div class="stat-label">题目生成策略</div>
            <div class="stat-extra">每次生成实时调用 LLM，不读缓存</div>
          </div>
        </div>

        <div class="panel-row">
          <div class="admin-panel">
            <h4>服务信息</h4>
            <dl class="kv">
              <dt>版本</dt><dd>v{{ stats.server.version }}</dd>
              <dt>全局兜底模型</dt><dd>{{ stats.server.model }}</dd>
              <dt>密钥加密</dt><dd>{{ stats.server.encryption }}</dd>
            </dl>
          </div>
        </div>
      </section>

      <!-- 模型配置 -->
      <section v-else-if="tab === 'llm'" class="tab-pane">
        <div class="admin-panel llm-panel">
          <h4>全局模型配置 <span class="llm-key-state">{{ llmHasKey ? '🔐 密钥已配置' : '⚠️ 未配置密钥' }}</span></h4>
          <p class="panel-desc">
            此处配置的模型服务对<b>全体用户</b>生效：所有账号的题目生成共用这一份配置。
            密钥加密存储在服务端，不会下发给任何前端。用户端无需也无法自行配置模型。
          </p>
          <div class="llm-form">
            <div class="llm-field">
              <label>接口地址（OpenAI 兼容）</label>
              <input v-model="llm.baseUrl" class="input" placeholder="https://api.deepseek.com" />
            </div>
            <div class="llm-field">
              <label>模型</label>
              <input v-model="llm.model" class="input" placeholder="deepseek-chat" />
            </div>
            <div class="llm-field">
              <label>密钥</label>
              <input v-model="llm.apiKey" class="input" type="password" placeholder="sk-...（已保存过可留空）" />
            </div>
            <div class="llm-field" style="max-width:140px;">
              <label>超时（秒）</label>
              <input v-model.number="llm.timeout" class="input" type="number" min="10" max="600" />
            </div>
          </div>
          <div v-if="llmMsg.text" class="llm-msg" :class="llmMsg.ok ? 'ok' : 'err'">{{ llmMsg.text }}</div>
          <div class="llm-actions">
            <button class="btn" :disabled="!!llmBusy" @click="testLlmConn">
              {{ llmBusy === 'test' ? '测试中…' : '🔌 测试连接' }}
            </button>
            <button class="btn primary" :disabled="!!llmBusy" @click="saveLlm">
              {{ llmBusy === 'save' ? '保存中…' : '💾 保存并全局生效' }}
            </button>
            <button v-if="llmHasKey || llm.baseUrl || llm.model" class="btn danger" :disabled="!!llmBusy" @click="clearLlm">
              {{ llmBusy === 'clear' ? '清除中…' : '🗑 清除配置' }}
            </button>
          </div>
        </div>
      </section>

      <!-- 用户管理 -->
      <section v-else-if="tab === 'users'" class="tab-pane">
        <div class="admin-panel create-panel">
          <h4>创建用户</h4>
          <div class="create-form">
            <input v-model="newUser.username" class="input" placeholder="用户名（2-32 位）" />
            <input v-model="newUser.password" class="input" type="password" placeholder="密码（至少 6 位）" @keyup.enter="createUser" />
            <select v-model="newUser.role" class="input">
              <option value="user">普通用户</option>
              <option value="admin">管理员</option>
            </select>
            <button class="btn primary" :disabled="creating" @click="createUser">{{ creating ? '创建中…' : '＋ 创建' }}</button>
          </div>
        </div>

        <div class="admin-panel">
          <div class="users-toolbar">
            <h4 style="margin:0;">用户列表（{{ users.length }}）</h4>
            <input v-model="query" class="input" placeholder="🔍 搜索用户名" style="width:200px;" @keyup.enter="loadUsers" />
            <button class="btn mini" @click="loadUsers">搜索</button>
          </div>
          <table class="users-table">
            <thead>
              <tr>
                <th>ID</th><th>用户名</th><th>角色</th><th>状态</th>
                <th>模板</th><th>注册时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.id" :class="{ off: !u.is_active }">
                <td>{{ u.id }}</td>
                <td class="uname">{{ u.username }}<span v-if="u.id === props.user.id" class="self-mark">（我）</span></td>
                <td><span class="badge" :class="u.role">{{ u.role === 'admin' ? '管理员' : '用户' }}</span></td>
                <td><span class="badge" :class="u.is_active ? 'on' : 'off'">{{ u.is_active ? '启用' : '禁用' }}</span></td>
                <td>{{ u.template_count }}</td>
                <td class="ctime">{{ u.created_at }}</td>
                <td class="ops">
                  <button class="btn mini" @click="tplUser = u">📄 模板{{ u.template_count ? `(${u.template_count})` : '' }}</button>
                  <button class="btn mini" @click="resetPassword(u)">🔑 改密</button>
                  <button class="btn mini" @click="toggleRole(u)">{{ u.role === 'admin' ? '↓ 降级' : '↑ 升管理员' }}</button>
                  <button class="btn mini" @click="toggleActive(u)">{{ u.is_active ? '⛔ 禁用' : '✅ 启用' }}</button>
                  <button class="btn mini danger" @click="removeUser(u)">🗑 删除</button>
                </td>
              </tr>
              <tr v-if="!users.length">
                <td colspan="7" class="empty">（暂无用户{{ query ? '，试试清空搜索词' : '' }}）</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 用户反馈 -->
      <section v-else-if="tab === 'feedback'" class="tab-pane">
        <div class="admin-panel">
          <div class="users-toolbar">
            <h4 style="margin:0;">用户反馈（{{ feedbacks.length }}）</h4>
            <label style="font-size:13px; color:#5c6880; display:flex; align-items:center; gap:4px; cursor:pointer;">
              <input type="checkbox" v-model="fbOobOnly" @change="loadFeedbacks" /> 只看超纲反馈
            </label>
            <button class="btn mini" :disabled="fbLoading" @click="loadFeedbacks">{{ fbLoading ? '加载中…' : '↻ 刷新' }}</button>
          </div>
          <table class="users-table">
            <thead>
              <tr>
                <th>ID</th><th>用户</th><th>类型</th><th>游戏/试卷 ID</th><th>反馈内容</th><th>时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in feedbacks" :key="f.id">
                <td>{{ f.id }}</td>
                <td class="uname">{{ f.username || `u${f.user_id}` }}</td>
                <td><span class="badge" :class="f.is_oob ? 'off' : 'user'">{{ f.is_oob ? '超纲' : '一般' }}</span></td>
                <td class="ctime">{{ f.game_id }}</td>
                <td class="fb-comment">{{ f.comment || '—' }}</td>
                <td class="ctime">{{ f.created_at }}</td>
              </tr>
              <tr v-if="!feedbacks.length">
                <td colspan="6" class="empty">（暂无反馈{{ fbOobOnly ? '，试试取消「只看超纲」' : '' }}）</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 日志 -->
      <section v-else class="tab-pane">
        <div class="admin-panel">
          <div class="users-toolbar">
            <h4 style="margin:0;">server.log（尾部 {{ logLines }} 行）</h4>
            <select v-model.number="logLines" class="input" style="width:110px;" @change="loadLogs">
              <option :value="100">100 行</option>
              <option :value="200">200 行</option>
              <option :value="500">500 行</option>
              <option :value="1000">1000 行</option>
            </select>
            <button class="btn mini" :disabled="logLoading" @click="loadLogs">{{ logLoading ? '加载中…' : '↻ 刷新' }}</button>
          </div>
          <pre class="log-view">{{ logs || '点击「刷新」加载日志' }}</pre>
        </div>
      </section>
    </main>

    <!-- 查看用户模板弹窗 -->
    <UserTemplatesDialog :user="tplUser" @close="tplUser = null" />
  </div>
</template>

<style scoped>
.admin-page {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: #f3f5fa;
  overflow: hidden;
}
.admin-topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e6eaf3;
}
.admin-brand { display: flex; align-items: center; gap: 10px; }
.admin-logo { font-size: 26px; }
.admin-title { font-weight: 700; font-size: 16px; color: #22314f; }
.admin-sub { font-size: 12px; color: #7b869e; }
.admin-msg { font-size: 13px; padding: 5px 12px; border-radius: 999px; }
.admin-msg.ok { background: #e8f7ee; color: #1e8e5a; }
.admin-msg.err { background: #fdecec; color: #c0392b; }

.admin-tabs {
  display: flex;
  gap: 4px;
  padding: 10px 24px 0;
  background: #fff;
  border-bottom: 1px solid #e6eaf3;
}
.admin-tabs button {
  border: 0;
  background: transparent;
  padding: 8px 16px;
  font-size: 14px;
  color: #6b7690;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}
.admin-tabs button.on { color: #4b6ef5; font-weight: 600; border-bottom-color: #4b6ef5; }

.admin-body { flex: 1; overflow: auto; padding: 20px 24px; }
.tab-pane { display: flex; flex-direction: column; gap: 16px; max-width: 1100px; }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; }
.stat-card {
  background: #fff;
  border-radius: 14px;
  padding: 18px 20px;
  box-shadow: 0 2px 10px rgba(30, 42, 80, 0.06);
}
.stat-num { font-size: 30px; font-weight: 700; color: #22314f; }
.stat-unit { font-size: 15px; color: #97a1b7; font-weight: 500; }
.stat-label { font-size: 13px; color: #5c6880; margin-top: 4px; }
.stat-extra { font-size: 12px; color: #97a1b7; margin-top: 6px; }

.panel-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 800px) { .panel-row { grid-template-columns: 1fr; } }

.admin-panel {
  background: #fff;
  border-radius: 14px;
  padding: 18px 20px;
  box-shadow: 0 2px 10px rgba(30, 42, 80, 0.06);
}
.admin-panel h4 { margin: 0 0 12px; font-size: 15px; color: #22314f; }
.panel-desc { font-size: 13px; color: #7b869e; line-height: 1.7; margin: 0 0 12px; }
.kv { display: grid; grid-template-columns: 110px 1fr; gap: 8px 12px; margin: 0; font-size: 13px; }
.kv dt { color: #7b869e; }
.kv dd { margin: 0; color: #2c3550; }

.create-form { display: flex; gap: 10px; flex-wrap: wrap; }
.create-form .input { width: auto; flex: 1; min-width: 150px; }

.users-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }

.users-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.users-table th {
  text-align: left;
  color: #7b869e;
  font-weight: 600;
  padding: 8px 10px;
  border-bottom: 1px solid #e6eaf3;
  white-space: nowrap;
}
.users-table td { padding: 9px 10px; border-bottom: 1px solid #f0f2f8; vertical-align: middle; }
.users-table tr.off td { color: #a5adc0; }
.users-table tr.off .uname { text-decoration: line-through; }
.uname { font-weight: 600; color: #2c3550; }
.self-mark { color: #97a1b7; font-weight: 400; font-size: 12px; }
.ctime { color: #97a1b7; white-space: nowrap; }
.ops { white-space: nowrap; }
.ops .btn { margin-right: 4px; margin-bottom: 2px; }
.empty { text-align: center; color: #a5adc0; padding: 28px 0 !important; }
.fb-comment { max-width: 360px; word-break: break-all; color: #2c3550; }

.badge { display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 999px; }
.badge.admin { background: #ede9fe; color: #6d28d9; }
.badge.user { background: #eef1f9; color: #5c6880; }
.badge.on { background: #e8f7ee; color: #1e8e5a; }
.badge.off { background: #fdecec; color: #c0392b; }

.btn.danger { color: #c0392b; border-color: #f3c1bd; }
.btn.danger:hover { background: #fdecec; }

/* ── 模型配置 ── */
.llm-panel { max-width: 640px; }
.llm-key-state {
  font-size: 12px;
  font-weight: 400;
  color: #7b869e;
  background: #eef1f9;
  padding: 3px 10px;
  border-radius: 999px;
  margin-left: 8px;
}
.llm-form { display: flex; flex-wrap: wrap; gap: 12px; margin: 14px 0; }
.llm-field { flex: 1; min-width: 220px; }
.llm-field label { display: block; font-size: 12px; color: #5c6880; margin-bottom: 6px; }
.llm-msg { font-size: 13px; padding: 8px 12px; border-radius: 8px; margin-bottom: 12px; }
.llm-msg.ok { background: #e8f7ee; color: #1e8e5a; }
.llm-msg.err { background: #fdecec; color: #c0392b; }
.llm-actions { display: flex; gap: 10px; }

.log-view {
  background: #1e2433;
  color: #c9d4ea;
  border-radius: 10px;
  padding: 14px 16px;
  font-size: 12px;
  line-height: 1.6;
  max-height: calc(100vh - 240px);
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
