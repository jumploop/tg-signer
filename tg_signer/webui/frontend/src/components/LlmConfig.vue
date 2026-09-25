<template>
  <el-card v-loading="loading" shadow="never" class="llm-card">
    <div class="llm-intro">
      <div>
        <span class="section-label">大模型连接</span>
        <p class="section-caption">配置用于 AI 能力的 OpenAI 兼容接口，密钥仅保存在当前工作目录。</p>
      </div>
      <el-tag type="info" effect="light" round>OpenAI Compatible</el-tag>
    </div>
    <el-alert
      title="环境变量优先级更高"
      description="如果设置了 OPENAI_API_KEY、OPENAI_BASE_URL 或 OPENAI_MODEL，这里保存的配置将被运行时环境变量覆盖。"
      type="info"
      show-icon
      :closable="false"
      class="llm-alert"
    />
    <el-form label-width="140px" class="llm-form">
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
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
        <el-button :loading="testing" @click="testConn">测试连通性</el-button>
        <span class="hint">{{ hint }}</span>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api, { asObject } from '../api'

const apiKey = ref('')
const baseUrl = ref('')
const model = ref('')
const hint = ref('')
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get('/api/llm-config')
    const config = asObject(data.config)
    apiKey.value = config.api_key || ''
    baseUrl.value = config.base_url || ''
    model.value = config.model || ''
    hint.value = data.has_env
      ? '当前运行时优先使用环境变量配置'
      : '已加载本地配置'
  } catch (error) {
    hint.value = '模型配置加载失败，请确认 WebUI 服务正常运行。'
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!apiKey.value.trim()) {
    ElMessage.warning('API Key 不能为空')
    return
  }
  saving.value = true
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
  } finally {
    saving.value = false
  }
}

async function testConn() {
  if (!apiKey.value.trim()) {
    ElMessage.warning('API Key 不能为空')
    return
  }
  testing.value = true
  try {
    const { data } = await api.post('/api/llm-config/test', {
      api_key: apiKey.value.trim(),
      base_url: baseUrl.value,
      model: model.value,
    })
    ElMessage[data.ok ? 'success' : 'error'](data.message)
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    testing.value = false
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

<style scoped>
.llm-intro {
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
.llm-alert {
  margin-bottom: 24px;
}
.llm-form {
  max-width: 680px;
}
.llm-form :deep(.el-form-item__label) {
  color: var(--ts-muted);
  font-family: var(--el-font-family-mono);
  font-size: 12px;
  font-weight: 600;
}

@media (max-width: 600px) {
  .llm-intro {
    align-items: flex-start;
    flex-direction: column;
  }

  .llm-form :deep(.el-form-item) {
    display: block;
  }

  .llm-form :deep(.el-form-item__label) {
    display: block;
    width: auto !important;
    margin-bottom: 7px;
    text-align: left;
  }

  .llm-form :deep(.el-form-item__content) {
    margin-left: 0 !important;
  }
}
</style>
