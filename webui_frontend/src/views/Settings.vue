<template>
  <el-card shadow="never">
    <el-form label-width="120px" style="max-width: 640px">
      <el-form-item label="工作目录">
        <el-input v-model="workdir" />
      </el-form-item>
      <el-form-item label="主日志路径">
        <el-input :model-value="logPath" readonly />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="apply">应用并刷新</el-button>
        <el-button @click="refresh">重新加载</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const workdir = ref('')
const logPath = ref('')

async function refresh() {
  const { data } = await api.get('/api/state')
  workdir.value = data.workdir
  logPath.value = data.log_path
}

async function apply() {
  if (!workdir.value.trim()) {
    ElMessage.warning('工作目录不能为空')
    return
  }
  try {
    const { data } = await api.post('/api/state', {
      workdir: workdir.value.trim(),
    })
    workdir.value = data.workdir
    logPath.value = data.log_path
    ElMessage.success('已切换工作目录')
  } catch (error) {
    ElMessage.error(errMsg(error))
  }
}

function errMsg(error) {
  return (
    (error.response && error.response.data && error.response.data.detail) ||
    error.message
  )
}

onMounted(refresh)
</script>

