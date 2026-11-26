<template>
  <el-card v-loading="loading" shadow="never">
    <div class="ts-intro">
      <div>
        <span class="ts-section-label">大模型连接</span>
        <p class="ts-section-caption">配置用于 AI 能力的 OpenAI 兼容接口，密钥仅保存在当前工作目录。</p>
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
        <el-input
          v-model="apiKey"
          type="password"
          show-password
          :placeholder="apiKeyPlaceholder"
        />
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
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api, { asObject, errMsg } from '../api'

const apiKey = ref('')
// 服务端只回掩码（如 ****abcd），绝不明文下发。这里单独存掩码、不回填进输入框：
// 回填会让人误以为框里是真实密钥，且 show-password 一开就是「****abcd」这种
// 看着像坏掉的值。改为留空 + 占位符说明，留空即「不修改」。
const apiKeyMask = ref('')
const baseUrl = ref('')
const model = ref('')
const hint = ref('')
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)

const apiKeyConfigured = computed(() => apiKeyMask.value.length > 0)
const apiKeyPlaceholder = computed(() =>
  apiKeyConfigured.value
    ? `已配置（${apiKeyMask.value}），留空表示不修改`
    : '请输入 API Key',
)

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get('/api/llm-config')
    const config = asObject(data.config)
    apiKeyMask.value = config.api_key || ''
    apiKey.value = ''
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

async function submitLlm(endpoint, busy, onSuccess) {
  const typed = apiKey.value.trim()
  if (!typed && !apiKeyConfigured.value) {
    ElMessage.warning('API Key 不能为空')
    return
  }
  busy.value = true
  try {
    const { data } = await api.post(endpoint, {
      api_key: typed,
      base_url: baseUrl.value,
      model: model.value,
    })
    onSuccess(data)
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    busy.value = false
  }
}

async function save() {
  await submitLlm('/api/llm-config', saving, () => {
    ElMessage.success('已保存')
    refresh()
  })
}

async function testConn() {
  await submitLlm('/api/llm-config/test', testing, ({ ok, message }) => {
    ElMessage[ok ? 'success' : 'error'](message)
  })
}

onMounted(refresh)
</script>

<style scoped>
.ts-intro {
  margin-bottom: 18px;
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
</style>
