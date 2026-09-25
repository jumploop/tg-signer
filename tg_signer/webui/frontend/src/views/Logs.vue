<template>
  <el-card shadow="never">
    <div class="row">
      <el-select v-model="selected" placeholder="选择日志文件" style="width: 460px">
        <el-option v-for="file in files" :key="file" :label="file" :value="file" />
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
    />
  </el-card>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const files = ref([])
const selected = ref('')
const limit = ref(200)
const autoRefresh = ref(false)
const content = ref('')
let timer = null

async function refreshFiles() {
  const { data } = await api.get('/api/logs/files')
  files.value = data.files
  if (!selected.value && data.files.length) {
    selected.value = data.files[data.files.length - 1]
  }
}

async function refresh() {
  const params = { limit: limit.value }
  if (selected.value) params.path = selected.value
  const { data } = await api.get('/api/logs', { params })
  content.value = data.lines.join('\n')
}

async function copyLog() {
  try {
    await navigator.clipboard.writeText(content.value)
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
  refreshFiles()
  refresh()
})
onUnmounted(() => clearInterval(timer))
</script>
