<template>
  <el-card shadow="never">
    <el-form inline>
      <el-form-item label="类型">
        <el-select v-model="kind" style="width: 140px">
          <el-option label="signer" value="signer" />
          <el-option label="monitor" value="monitor" />
          <el-option label="automation" value="automation" />
        </el-select>
      </el-form-item>
      <el-form-item label="账号">
        <el-select v-model="account" placeholder="选择账号" style="width: 200px">
          <el-option
            v-for="a in accounts"
            :key="a.account"
            :label="a.account"
            :value="a.account"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="任务">
        <el-input
          v-model="tasksText"
          placeholder="任务名，多个用逗号分隔"
          style="width: 320px"
          clearable
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="start">启动</el-button>
        <el-button @click="stop">停止</el-button>
        <el-button type="danger" plain @click="shutdownAll">全部停止</el-button>
      </el-form-item>
    </el-form>
    <p class="hint">
      同一账号同类型任务共用一个子进程（共享 Client，避免 SQLite session
      文件锁冲突）。日志写入 &lt;workdir&gt;/logs/，可在“日志”页查看。
    </p>
    <el-table :data="rows" style="max-width: 520px">
      <el-table-column prop="key" label="进程" />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.running ? 'success' : 'info'">
            {{ row.running ? '运行中' : '已停止' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const kind = ref('signer')
const account = ref('')
const accounts = ref([])
const tasksText = ref('')
const tasks = ref({})
let timer = null

const rows = computed(() =>
  Object.entries(tasks.value).map(([key, running]) => ({ key, running }))
)

async function refresh() {
  try {
    const [runData, accData] = await Promise.all([
      api.get('/api/run'),
      api.get('/api/accounts'),
    ])
    tasks.value = runData.data.tasks || {}
    accounts.value = accData.data
  } catch (error) {
    /* 轮询期间忽略瞬时错误 */
  }
}

async function start() {
  const list = tasksText.value
    .split(/[,，]/)
    .map((task) => task.trim())
    .filter(Boolean)
  if (!account.value) {
    ElMessage.warning('请选择账号')
    return
  }
  if (!list.length) {
    ElMessage.warning('请输入至少一个任务名')
    return
  }
  try {
    const { data } = await api.post('/api/run/start', {
      kind: kind.value,
      tasks: list,
      account: account.value,
    })
    showMsg(data)
    refresh()
  } catch (error) {
    ElMessage.error(errMsg(error))
  }
}

async function stop() {
  if (!account.value) {
    ElMessage.warning('请选择账号')
    return
  }
  try {
    const { data } = await api.post('/api/run/stop', {
      kind: kind.value,
      account: account.value,
    })
    showMsg(data)
    refresh()
  } catch (error) {
    ElMessage.error(errMsg(error))
  }
}

async function shutdownAll() {
  try {
    const { data } = await api.post('/api/run/shutdown')
    ElMessage.success('已停止 ' + data.stopped.length + ' 个进程')
    refresh()
  } catch (error) {
    ElMessage.error(errMsg(error))
  }
}

function showMsg(data) {
  if (data.ok) {
    ElMessage.success(data.message)
  } else {
    ElMessage.warning(data.message)
  }
}

function errMsg(error) {
  return (
    (error.response && error.response.data && error.response.data.detail) ||
    error.message
  )
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

