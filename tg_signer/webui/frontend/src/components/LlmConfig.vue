<template>
  <el-card shadow="never">
    <el-form label-width="140px" style="max-width: 640px">
      <el-form-item label="OPENAI_API_KEY">
        <el-input v-model="apiKey" type="password" show-password />
      </el-form-item>
      <el-form-item label="OPENAI_BASE_URL">
        <el-input v-model="baseUrl" placeholder="例如 https://api.openai.com/v1" />
      </el-form-item>
      <el-form-item label="OPENAI_MODEL">
        <el-input v-model="model" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="save">保存</el-button>
        <el-button @click="testConn">测试连通性</el-button>
        <span class="hint">{{ hint }}</span>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const apiKey = ref('')
const baseUrl = ref('')
const model = ref('')
const hint = ref('')

async function refresh() {
  const { data } = await api.get('/api/llm-config')
  apiKey.value = data.config.api_key || ''
  baseUrl.value = data.config.base_url || ''
  model.value = data.config.model || ''
  hint.value = data.has_env
    ? '当前运行时优先使用环境变量配置'
    : '已加载本地配置'
}

async function save() {
  if (!apiKey.value.trim()) {
    ElMessage.warning('API Key 不能为空')
    return
  }
  try {
    await api.post('/api/llm-config', {
      api_key: apiKey.value.trim(),
      base_url: baseUrl.value,
      model: model.value,
    })
    ElMessage.success('已保存')
    refresh()
  } catch (error) {
    ElMessage.error(errMsg(error))
  }
}

async function testConn() {
  if (!apiKey.value.trim()) {
    ElMessage.warning('API Key 不能为空')
    return
  }
  try {
    const { data } = await api.post('/api/llm-config/test', {
      api_key: apiKey.value.trim(),
      base_url: baseUrl.value,
      model: model.value,
    })
    ElMessage[data.ok ? 'success' : 'error'](data.message)
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

