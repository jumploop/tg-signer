<template>
  <el-card shadow="never" class="users-card">
    <div class="users-intro">
      <div>
        <span class="section-label">用户信息</span>
        <p class="section-caption">查看本地缓存的账户资料与最近对话，不触发 Telegram 网络请求。</p>
      </div>
      <el-button :loading="loading" @click="refresh">刷新</el-button>
    </div>
    <div class="users-note">
      <el-icon><InfoFilled /></el-icon>
      <span>数据来源：当前工作目录下的 <code>users/*/me.json</code> 与最近对话缓存。</span>
    </div>
    <div class="table-heading">
      <span>已缓存账户</span>
      <span class="table-heading__meta">{{ users.length }} 个账户</span>
    </div>
    <el-table v-loading="loading" :data="users" class="users-table">
      <el-table-column prop="user_id" label="User ID" width="140" />
      <el-table-column label="名称">
        <template #default="{ row }">
          <div class="user-cell">
            <span class="user-avatar">{{ userInitial(row) }}</span>
            <span>{{ row.data.first_name || row.data.username || '-' }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="最新对话数" width="120">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.latest_chats.length }} 个</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" @click="showChats(row)">查看对话</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无用户信息（读取 users/*/me.json）" :image-size="60" />
      </template>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="'对话列表 - ' + (currentUser?.data.first_name || currentUser?.user_id)"
      width="640px"
      class="user-dialog"
    >
      <el-table :data="currentChats" max-height="400">
        <el-table-column prop="id" label="ID" width="140" />
        <el-table-column prop="title" label="标题" />
        <el-table-column prop="type" label="类型" width="120" />
        <el-table-column prop="username" label="用户名" />
      </el-table>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import api, { asArray } from '../api'

const users = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const currentUser = ref(null)
const currentChats = computed(() => currentUser.value?.latest_chats || [])

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get('/api/users')
    users.value = asArray(data)
  } catch (error) {
    ElMessage.error('用户信息加载失败: ' + errMsg(error))
  } finally {
    loading.value = false
  }
}

function showChats(row) {
  currentUser.value = row
  dialogVisible.value = true
}

function userInitial(row) {
  const name = row.data.first_name || row.data.username || String(row.user_id)
  return name.slice(0, 1).toUpperCase()
}

function errMsg(error) {
  return (
    (error.response && error.response.data && error.response.data.detail) ||
    error.message
  )
}

onMounted(refresh)
</script>

<style scoped>
.users-intro,
.table-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}
.users-intro {
  margin-bottom: 14px;
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
.users-note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
  padding: 11px 13px;
  border: 1px solid #D9E7FA;
  border-radius: 10px;
  background: #F5F9FF;
  color: #47617F;
  font-size: 12px;
}
.users-note .el-icon {
  color: var(--ts-sky);
}
.users-note code {
  font-family: var(--el-font-family-mono);
  font-size: 11px;
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
.user-cell {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-weight: 600;
}
.user-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  background: var(--ts-sky-soft);
  color: var(--ts-sky);
  font-size: 12px;
  font-weight: 800;
}

@media (max-width: 600px) {
  .users-intro,
  .table-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .users-note {
    align-items: flex-start;
  }
}
</style>
