<template>
  <el-card shadow="never">
    <el-form inline>
      <el-form-item label="类型">
        <el-select v-model="kind" style="width: 160px">
          <el-option label="Signer（签到）" value="signer" />
          <el-option label="Monitor（监控）" value="monitor" />
          <el-option label="Automation（自动化）" value="automation" />
        </el-select>
      </el-form-item>
      <el-form-item label="账号">
        <el-select
          v-model="account"
          placeholder="选择账号"
          style="width: 200px"
          filterable
        >
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
        <el-button type="primary" :loading="starting" @click="start">启动</el-button>
        <el-button :loading="stopping" @click="stop">停止当前</el-button>
        <el-button type="danger" plain @click="shutdownAll">全部停止</el-button>
      </el-form-item>
    </el-form>
    <p class="hint">
      同一账号同类型任务共用一个子进程（共享 Client，避免 SQLite session
      文件锁冲突）。日志写入 &lt;workdir&gt;/logs/，可在「日志」页查看。
    </p>
    <el-table :data="rows">
      <el-table-column label="类型" width="180">
        <template #default="{ row }">{{ kindLabel(row.kind) }}</template>
      </el-table-column>
      <el-table-column prop="account" label="账号" width="200" />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.running ? 'success' : 'info'">
            {{ row.running ? '运行中' : '已停止' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" :disabled="!row.running" @click="stopRow(row)">
            停止
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无运行中的进程" :image-size="60" />
      </template>
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
const starting = ref(false)
const stopping = ref(false)
let timer = null

const KIND_LABELS = {
  signer: 'Signer（签到）',
  monitor: 'Monitor（监控）',
  automation: 'Automation（自动化）',
}

const rows = computed(() =>
  Object.entries(tasks.value).map(([key, running]) => {
    const [k, acc] = key.split(':')
    return { key, kind: k, account: acc || key, running }
  })
)

function kindLabel(k) {
  return KIND_LABELS[k] || k
}

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
  starting.value = true
  try {
    const { data } = await api.post('/api/run/start', {
      kind: kind.value,
      tasks: list,
      account: account.value,
    })
    showMsg(data)
    if (data.ok) {
      tasksText.value = ''
    }
    refresh()
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    starting.value = false
  }
}

async function stop() {
  if (!account.value) {
    ElMessage.warning('请选择账号')
    return
  }
  stopping.value = true
  try {
    const { data } = await api.post('/api/run/stop', {
      kind: kind.value,
      account: account.value,
    })
    showMsg(data)
    refresh()
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    stopping.value = false
  }
}

async function stopRow(row) {
  try {
    const { data } = await api.post('/api/run/stop', {
      kind: row.kind,
      account: row.account,
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
