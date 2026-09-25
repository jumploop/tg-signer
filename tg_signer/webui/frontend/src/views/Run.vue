<template>
  <el-card shadow="never" class="run-card">
    <div class="run-intro">
      <div>
        <span class="section-label">启动控制</span>
        <p class="section-caption">选择账号和任务范围，集中启动或停止后台进程。</p>
      </div>
      <el-tag :type="runningCount ? 'success' : 'info'" effect="light" round>
        {{ runningCount ? `${runningCount} 个进程运行中` : '当前无运行进程' }}
      </el-tag>
    </div>
    <el-form inline class="run-form">
      <el-form-item label="类型">
        <el-select v-model="kind" class="kind-select">
          <el-option label="Signer（签到）" value="signer" />
          <el-option label="Automation（自动化）" value="automation" />
        </el-select>
      </el-form-item>
      <el-form-item label="账号">
        <el-select
          v-model="account"
          placeholder="选择账号"
          class="account-select"
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
        <el-checkbox
          :model-value="allSelected"
          :indeterminate="someSelected"
          :disabled="!taskNames.length"
          @change="toggleSelectAll"
        >
          全选
        </el-checkbox>
        <el-select
          v-model="selectedTasks"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          placeholder="从配置列表选择任务（可多选）"
          class="task-select"
          :loading="loadingTasks"
        >
          <el-option
            v-for="name in taskNames"
            :key="name"
            :label="name"
            :value="name"
          />
        </el-select>
        <span class="selection-count">
          已选择 {{ selectedTasks.length }} 个任务
        </span>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="starting" @click="start">启动</el-button>
        <el-button :loading="stopping" @click="stop">停止当前</el-button>
        <el-button type="danger" plain @click="shutdownAll">全部停止</el-button>
      </el-form-item>
    </el-form>
    <div class="run-note">
      <el-icon><InfoFilled /></el-icon>
      <span>
      同一账号同类型的多个任务会合并到一个子进程运行（共享 Client，避免 SQLite
      session 文件锁冲突），请一次性选择全部任务后启动；日志写入
      &lt;workdir&gt;/logs/，可在「日志」页查看。
      </span>
    </div>
    <div class="table-heading">
      <span>运行中的进程</span>
      <span class="table-heading__meta">每 5 秒自动刷新</span>
    </div>
    <el-table :data="rows">
      <el-table-column label="类型" width="180">
        <template #default="{ row }">{{ kindLabel(row.kind) }}</template>
      </el-table-column>
      <el-table-column prop="account" label="账号" width="200" />
      <el-table-column label="任务" min-width="220">
        <template #default="{ row }">
          <template v-if="row.tasks.length">
            <el-tag
              v-for="name in row.tasks"
              :key="name"
              size="small"
              type="info"
              class="task-tag"
            >
              {{ name }}
            </el-tag>
          </template>
          <span v-else class="hint">-</span>
        </template>
      </el-table-column>
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
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import api from '../api'

const kind = ref('signer')
const account = ref('')
const accounts = ref([])
const taskNames = ref([])
const selectedTasks = ref([])
const loadingTasks = ref(false)
const tasks = ref({})
const taskNamesByKey = ref({})
const starting = ref(false)
const stopping = ref(false)
let timer = null

const KIND_LABELS = {
  signer: 'Signer（签到）',
  automation: 'Automation（自动化）',
}

const rows = computed(() =>
  Object.entries(tasks.value).map(([key, running]) => {
    const [k, acc] = key.split(':')
    return {
      key,
      kind: k,
      account: acc || key,
      running,
      tasks: taskNamesByKey.value[key] || [],
    }
  })
)
const runningCount = computed(() => rows.value.filter((row) => row.running).length)

const allSelected = computed(
  () => taskNames.value.length > 0 && selectedTasks.value.length === taskNames.value.length
)
const someSelected = computed(
  () => selectedTasks.value.length > 0 && selectedTasks.value.length < taskNames.value.length
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
    taskNamesByKey.value = runData.data.task_names || {}
    accounts.value = accData.data
  } catch (error) {
    /* 轮询期间忽略瞬时错误 */
  }
}

function toggleSelectAll(checked) {
  selectedTasks.value = checked ? [...taskNames.value] : []
}

async function loadTasks() {
  loadingTasks.value = true
  try {
    const { data } = await api.get(`/api/configs/${kind.value}`)
    taskNames.value = data.names || []
  } catch (error) {
    taskNames.value = []
  } finally {
    loadingTasks.value = false
  }
}

watch(kind, () => {
  selectedTasks.value = []
  loadTasks()
})

async function start() {
  if (!account.value) {
    ElMessage.warning('请选择账号')
    return
  }
  if (!selectedTasks.value.length) {
    ElMessage.warning('请选择至少一个任务')
    return
  }
  starting.value = true
  try {
    const { data } = await api.post('/api/run/start', {
      kind: kind.value,
      tasks: selectedTasks.value,
      account: account.value,
    })
    showMsg(data)
    if (data.ok) {
      selectedTasks.value = []
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
  loadTasks()
  timer = setInterval(refresh, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.run-intro,
.table-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}
.run-intro {
  margin-bottom: 22px;
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
.run-form {
  display: grid;
  grid-template-columns: minmax(150px, 0.8fr) minmax(190px, 1fr) minmax(420px, 2fr) auto;
  align-items: end;
  gap: 14px;
  margin: 0 -10px;
}
.run-form :deep(.el-form-item) {
  min-width: 0;
  margin: 0 10px;
}
.run-form :deep(.el-form-item__label) {
  padding-bottom: 7px;
  color: var(--ts-muted);
  font-size: 12px;
  font-weight: 600;
}
.run-form :deep(.el-form-item:last-child) {
  display: flex;
  gap: 8px;
  margin-right: 0;
}
.kind-select,
.account-select {
  width: 100%;
}
.task-select {
  width: 100%;
}
.selection-count {
  display: inline-block;
  margin-top: 8px;
  color: var(--ts-muted);
  font-size: 12px;
  white-space: nowrap;
}
.run-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 4px 0 26px;
  padding: 12px 14px;
  border: 1px solid #D9E7FA;
  border-radius: 10px;
  background: #F5F9FF;
  color: #47617F;
  font-size: 12px;
  line-height: 1.6;
}
.run-note .el-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--ts-sky);
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
.task-tag {
  margin: 2px 4px 2px 0;
}

@media (max-width: 980px) {
  .run-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .run-form :deep(.el-form-item:last-child) {
    grid-column: 1 / -1;
  }
}

@media (max-width: 600px) {
  .run-intro,
  .table-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .run-form {
    display: block;
  }
  .run-form :deep(.el-form-item),
  .run-form :deep(.el-form-item:last-child) {
    display: block;
    margin: 0 0 14px;
  }
  .run-form :deep(.el-form-item:last-child) {
    display: flex;
    flex-wrap: wrap;
  }
}
</style>
