<template>
  <section class="page" data-module="alarm">
    <header class="page-head">
      <div>
        <h2>报警中心管理</h2>
        <p class="page-desc">维护报警事件，围绕报警编号、报警类型、报警等级、触发点位做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记报警事件</button>
        <button class="btn" type="button" @click="exportRows">导出报警中心清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>报警编号</span>
        <input v-model="filters.keyword" placeholder="按报警编号检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ String(row.status ?? '—') }}</td>
          <td class="row-actions">
            <button
              v-for="action in allowedActions(String(row.status))"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!allowedActions(String(row.status)).length" class="text-muted">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无符合条件的报警事件</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条报警中心记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/alarm'
// 「报警状态」是示例数据里的占位字段，真实状态统一以后端 status 为准，单独成列展示。
const columns = ["报警编号", "报警类型", "报警等级", "触发点位", "触发时间", "确认人员", "处置措施"]
const statuses = ["待确认", "已确认", "已处置", "已忽略"]
// 状态流转口径与后端一致：
// 待确认可确认/处置/忽略；已确认可处置/忽略；已处置、已忽略为终态，不再提供动作。
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  "待确认": ["确认报警", "处置报警", "忽略报警"],
  "已确认": ["处置报警", "忽略报警"],
  "已处置": [],
  "已忽略": [],
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })
const stats = ref([
  { label: '今日报警', value: 0 },
  { label: '待确认报警', value: 0 },
  { label: '高等级报警', value: 0 },
])

function allowedActions(status: string): string[] {
  return ACTIONS_BY_STATUS[status] ?? []
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '报警事件登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '报警中心动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '报警中心操作失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = (await response.json()) as Record<string, number>
    stats.value = [
      { label: '今日报警', value: Number(payload.today ?? 0) },
      { label: '待确认报警', value: Number(payload.unconfirmed ?? 0) },
      { label: '高等级报警', value: Number(payload.high_level ?? 0) },
    ]
  } catch {
    // 统计卡片读取失败不影响列表，保留上次数值即可。
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword.trim()) {
    query.set('keyword', filters.value.keyword.trim())
  }
  if (filters.value.status) {
    query.set('status', filters.value.status)
  }
  try {
    const suffix = query.toString()
    const response = await request(suffix ? `${ENDPOINT}?${suffix}` : ENDPOINT)
    if (!response.ok) {
      throw new Error('报警事件列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '报警中心列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
