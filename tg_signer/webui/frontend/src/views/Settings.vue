<template>
  <el-card shadow="never" class="settings-card">
    <div class="settings-intro">
      <span class="section-label">工作区设置</span>
      <p class="section-caption">调整 WebUI 使用的本地目录，配置和运行记录会跟随此目录读取。</p>
    </div>
    <el-alert
      title="切换工作目录不会自动迁移已有数据"
      description="应用前请确认目标目录存在，并了解其中的配置、日志和签到记录会重新从该目录读取。"
      type="info"
      show-icon
      :closable="false"
      class="settings-alert"
    />
    <el-form label-width="120px" class="settings-form">
      <el-form-item label="工作目录">
        <el-input v-model="workdir" />
      </el-form-item>
      <el-form-item label="主日志路径">
        <el-input :model-value="logPath" readonly />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="apply">应用并刷新</el-button>
        <el-button :loading="loading" @click="refresh">重新加载</el-button>
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
const loading = ref(false)
const saving = ref(false)

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get('/api/state')
    workdir.value = data.workdir
    logPath.value = data.log_path
  } catch (error) {
    ElMessage.error('设置加载失败: ' + errMsg(error))
  } finally {
    loading.value = false
  }
}

async function apply() {
  if (!workdir.value.trim()) {
    ElMessage.warning('工作目录不能为空')
    return
  }
  saving.value = true
  try {
    const { data } = await api.post('/api/state', {
      workdir: workdir.value.trim(),
    })
    workdir.value = data.workdir
    logPath.value = data.log_path
    ElMessage.success('已切换工作目录')
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    saving.value = false
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
.settings-intro {
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
  max-width: 620px;
  margin: 0;
  color: var(--ts-muted);
  font-size: 13px;
  line-height: 1.6;
}
.settings-alert {
  margin-bottom: 24px;
}
.settings-form {
  max-width: 680px;
}
.settings-form :deep(.el-form-item__label) {
  color: var(--ts-muted);
  font-weight: 600;
}

@media (max-width: 600px) {
  .settings-form :deep(.el-form-item) {
    display: block;
  }

  .settings-form :deep(.el-form-item__label) {
    display: block;
    width: auto !important;
    margin-bottom: 7px;
    text-align: left;
  }

  .settings-form :deep(.el-form-item__content) {
    margin-left: 0 !important;
  }
}
</style>
