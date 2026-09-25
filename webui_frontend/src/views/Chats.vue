<template>
  <el-card shadow="never">
    <div class="row">
      <el-select v-model="account" placeholder="选择账号（需已登录）" style="width: 220px">
        <el-option v-for="a in accounts" :key="a.account" :label="a.account" :value="a.account" />
      </el-select>
      <el-button type="primary" :loading="loading" @click="fetchLive">
        实时获取最近 50 个对话
      </el-button>
      <el-button @click="refreshCache">读取缓存</el-button>
    </div>
    <p class="hint">{{ statusText }}</p>
    <el-table :data="chats" max-height="560">
      <el-table-column prop="id" label="ID" width="140" />
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="type" label="类型" width="120" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button size="small" @click="copyId(row.id)">复制ID</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const accounts = ref([])
const account = ref('')
const chats = ref([])
const loading = ref(false)
const statusText = ref('')

async function refreshAccounts() {
  const { data } = await api.get('/api/accounts')
  accounts.value = data
}

async function refreshCache() {
  const { data } = await api.get('/api/chats')
  chats.value = data
  statusText.value = `已读取缓存，共 ${data.length} 个群组/频道`
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
      chats.value = data.chats
      statusText.value = `实时获取 ${data.chats.length} 个对话`
    }
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    loading.value = false
  }
}

async function copyId(id) {
  try {
    await navigator.clipboard.writeText(String(id))
    ElMessage.success('已复制: ' + id)
  } catch (error) {
    ElMessage.warning('复制失败，请手动复制')
  }
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

