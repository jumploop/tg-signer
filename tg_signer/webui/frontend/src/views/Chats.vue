<template>
  <el-card shadow="never" class="chats-card">
    <div class="chats-intro">
      <div>
        <span class="section-label">对话资源</span>
        <p class="section-caption">从已登录账号读取群组和频道，快速复制 ID 或填入配置。</p>
      </div>
      <el-tag type="info" effect="light" round>{{ chats.length }} 个对话</el-tag>
    </div>
    <div class="chats-controls">
      <el-select v-model="account" placeholder="选择账号（需已登录）" class="account-select">
        <el-option v-for="a in accounts" :key="a.account" :label="a.account" :value="a.account" />
      </el-select>
      <el-button type="primary" :loading="loading" @click="fetchLive">
        实时获取最近 50 个对话
      </el-button>
      <el-button :loading="cacheLoading" @click="refreshCache">读取缓存</el-button>
    </div>
    <div
      class="status-line"
      :class="{ 'is-empty': !statusText }"
      role="status"
      aria-live="polite"
    >
      <span class="status-dot" />
      <span>{{ statusText || '尚未读取对话数据' }}</span>
    </div>
    <div class="table-heading">
      <span>群组 / 频道</span>
      <span class="table-heading__meta">支持复制到 Signer 或 Automation</span>
    </div>
    <el-table v-loading="loading || cacheLoading" :data="chats" max-height="560" class="chats-table">
      <el-table-column prop="id" label="ID" width="140" />
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="type" label="类型" width="120" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" @click="copyId(row.id)">复制ID</el-button>
          <el-dropdown size="small" @command="(cmd) => applyToConfig(cmd, row)">
            <el-button size="small" type="primary" plain>复制到配置</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="signer">填入 Signer（签到）</el-dropdown-item>
                <el-dropdown-item command="automation">填入 Automation（自动化）</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty
          description="暂无群组/频道数据：请在「账号管理」登录账号，或选择账号后点「实时获取最近 50 个对话」写入缓存，再用「读取缓存」查看"
          :image-size="60"
        />
      </template>
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import api, { asArray, copyText } from '../api'

const router = useRouter()
const accounts = ref([])
const account = ref('')
const chats = ref([])
const loading = ref(false)
const cacheLoading = ref(false)
const statusText = ref('')

async function refreshAccounts() {
  try {
    const { data } = await api.get('/api/accounts')
    accounts.value = asArray(data)
  } catch (error) {
    statusText.value = '账号列表加载失败，请确认 WebUI 服务正常运行。'
  }
}

async function refreshCache() {
  cacheLoading.value = true
  try {
    const { data } = await api.get('/api/chats')
    chats.value = asArray(data)
    if (chats.value.length) {
      statusText.value = `已读取缓存，共 ${chats.value.length} 个群组/频道`
      ElMessage.success(`已读取缓存，共 ${chats.value.length} 个群组/频道`)
    } else {
      statusText.value =
        '缓存为空：还没有账号缓存。请先在「账号管理」登录账号，或点「实时获取」写入缓存。'
      ElMessage.warning('缓存为空，请先登录账号或实时获取最近对话')
    }
  } catch (error) {
    statusText.value = '缓存读取失败，请稍后重试。'
    ElMessage.error('读取缓存失败: ' + errMsg(error))
  } finally {
    cacheLoading.value = false
  }
}

async function fetchLive() {
  if (!account.value) {
    ElMessage.warning('请选择账号')
    return
  }
  loading.value = true
  try {
    const { data } = await api.post('/api/chats/fetch', {
      account: account.value,
    })
    ElMessage[data.ok ? 'success' : 'error'](data.message)
    if (data.ok) {
      chats.value = asArray(data.chats)
      statusText.value = `实时获取 ${chats.value.length} 个对话`
    }
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    loading.value = false
  }
}

async function copyId(id) {
  try {
    await copyText(id)
    ElMessage.success('已复制: ' + id)
  } catch (error) {
    ElMessage.warning('复制失败，请手动复制')
  }
}

function chatValue(row) {
  return row.username ? '@' + row.username : String(row.id)
}

function applyToConfig(target, row) {
  const value = chatValue(row)
  const label = target === 'signer' ? 'Signer（签到）' : 'Automation（自动化）'
  router.push({
    name: 'configs',
    query: { kind: target, chat: value, title: row.title || '' },
  })
  ElMessage.info(`正在前往配置管理页，将 ${value} 填入 ${label} 配置`)
}

function errMsg(error) {
  return (
    (error.response && error.response.data && error.response.data.detail) ||
    error.message
  )
}

onMounted(() => {
  refreshAccounts()
  refreshCache()
})
</script>

<style scoped>
.chats-intro,
.table-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}
.chats-intro {
  margin-bottom: 20px;
}
.section-label {
  display: block;
  margin-bottom: 5px;
  color: var(--ts-ink);
  font-size: 16px;
  font-weight: 700;
}
.section-caption {
  margin: 0;
  color: var(--ts-muted);
  font-size: 13px;
}
.chats-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.account-select {
  width: 240px;
}
.status-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  margin-bottom: 22px;
  padding: 8px 11px;
  border: 1px solid #D9E7FA;
  border-radius: 9px;
  background: #F5F9FF;
  color: #47617F;
  font-size: 12px;
}
.status-line.is-empty {
  border-color: var(--ts-line);
  background: #FAFCFF;
  color: var(--ts-muted);
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ts-sky);
  box-shadow: 0 0 0 3px rgba(37, 105, 208, 0.12);
}
.status-line.is-empty .status-dot {
  background: var(--ts-faint);
  box-shadow: none;
}
.table-heading {
  margin-bottom: 12px;
  color: var(--ts-ink);
  font-size: 14px;
  font-weight: 700;
}
.table-heading__meta {
  color: var(--ts-muted);
  font-size: 12px;
  font-weight: 400;
}

@media (max-width: 600px) {
  .chats-intro,
  .table-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .chats-controls > * {
    width: 100% !important;
  }
}
</style>
