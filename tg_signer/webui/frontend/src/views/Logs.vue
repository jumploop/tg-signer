<template>
  <el-card shadow="never" class="logs-card">
    <div class="logs-intro">
      <div>
        <span class="section-label">日志查看器</span>
        <p class="section-caption">按文件查看最近运行输出，支持自动刷新和复制当前内容。</p>
      </div>
      <el-tag :type="autoRefresh ? 'success' : 'info'" effect="light" round>
        {{ autoRefresh ? '自动刷新已开启' : '手动刷新' }}
      </el-tag>
    </div>
    <div class="logs-controls">
      <el-select v-model="selected" placeholder="选择日志文件" class="log-file-select">
        <el-option v-for="file in files" :key="file" :label="fileName(file)" :value="file" />
      </el-select>
      <el-input-number v-model="limit" :min="50" :max="2000" :step="50" />
      <el-switch v-model="autoRefresh" active-text="自动刷新(5s)" />
      <el-button @click="copyLog">复制日志</el-button>
      <el-button @click="refresh">刷新</el-button>
    </div>
    <el-input
      type="textarea"
      :rows="22"
      :model-value="content"
      readonly
      class="logbox mono"
      :placeholder="files.length ? '暂无日志内容' : '当前工作目录还没有日志文件'"
      aria-label="日志内容"
    />
  </el-card>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api, { asArray, copyText } from '../api'

const files = ref([])
const selected = ref('')
const limit = ref(200)
const autoRefresh = ref(false)
const content = ref('')
let timer = null

// 展示相对 logs/ 目录的路径（如 signer-demo/tg-signer.log）而不是纯文件名：
// 子目录日志和主日志都叫 tg-signer.log，只显示文件名分不清谁是谁。
function fileName(fullPath) {
  const parts = String(fullPath).split(/[\\/]/).filter(Boolean)
  const idx = parts.lastIndexOf('logs')
  const tail = idx >= 0 ? parts.slice(idx + 1) : parts.slice(-1)
  return tail.join('/') || fullPath
}

async function refreshFiles() {
  try {
    const { data } = await api.get('/api/logs/files')
    files.value = asArray(data.files)
    if (!selected.value && files.value.length) {
      // 后端已把「非空 + 最新」排在最前，第一个就是最值得先看的日志。
      selected.value = files.value[0]
    }
  } catch {
    files.value = []
  }
}

async function refresh() {
  const params = { limit: limit.value }
  if (selected.value) params.path = selected.value
  try {
    const { data } = await api.get('/api/logs', { params })
    content.value = asArray(data.lines).join('\n')
  } catch {
    content.value = ''
  }
}

async function copyLog() {
  try {
    await copyText(content.value)
    ElMessage.success('已复制日志')
  } catch (error) {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}

watch([selected, limit], refresh)
watch(autoRefresh, (value) => {
  clearInterval(timer)
  if (value) timer = setInterval(refresh, 5000)
})
onMounted(() => {
  // 必须串行：refreshFiles 结束后 watch([selected]) 会触发一次 refresh，
  // 若并发调用会多打一次请求，且首次内容可能来自尚未加载完的默认路径。
  refreshFiles().then(refresh)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.logs-intro {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
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
.logs-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.log-file-select {
  width: min(460px, 100%);
}
.logs-card :deep(.el-input-number) {
  width: 140px;
}
.logs-card :deep(.el-textarea__inner) {
  min-height: 480px !important;
  resize: vertical;
}

@media (max-width: 600px) {
  .logs-intro {
    align-items: flex-start;
    flex-direction: column;
  }

  .logs-controls > * {
    width: 100% !important;
  }

  .logs-controls :deep(.el-switch) {
    width: auto !important;
  }
}
</style>
