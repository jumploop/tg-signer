<template>
  <el-card shadow="never">
    <div class="row">
      <el-select v-model="account" placeholder="选择账号（需已登录）" style="width: 220px">
        <el-option v-for="a in accounts" :key="a.account" :label="a.account" :value="a.account" />
      </el-select>
      <el-button type="primary" :loading="loading" @click="fetchLive">
        实时获取最近 50 个对话
      </el-button>
      <el-button :loading="cacheLoading" @click="refreshCache">读取缓存</el-button>
    </div>
    <p class="hint">{{ statusText }}</p>
    <el-table :data="chats" max-height="560">
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
import api from '../api'

const router = useRouter()
const accounts = ref([])
const account = ref('')
const chats = ref([])
const loading = ref(false)
const cacheLoading = ref(false)
const statusText = ref('')

async function refreshAccounts() {
  const { data } = await api.get('/api/accounts')
  accounts.value = data
}

async function refreshCache() {
  cacheLoading.value = true
  try {
    const { data } = await api.get('/api/chats')
    chats.value = data
    if (data.length) {
      statusText.value = `已读取缓存，共 ${data.length} 个群组/频道`
      ElMessage.success(`已读取缓存，共 ${data.length} 个群组/频道`)
    } else {
      statusText.value =
        '缓存为空：还没有账号缓存。请先在「账号管理」登录账号，或点「实时获取」写入缓存。'
      ElMessage.warning('缓存为空，请先登录账号或实时获取最近对话')
    }
  } catch (error) {
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

function chatValue(row) {
  return row.username ? '@' + row.username : String(row.id)
}

function applyToConfig(target, row) {
  const value = chatValue(row)
  const label = target === 'signer' ? 'Signer（签到）' : 'Automation（自动化）'
  router.push({ name: 'configs', query: { kind: target, chat: value } })
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
