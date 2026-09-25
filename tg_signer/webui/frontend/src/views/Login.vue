<template>
  <div class="login-wrap">
    <div class="login-panel">
      <div class="login-brand">
        <span class="brand-badge"><el-icon><Promotion /></el-icon></span>
        <span class="login-eyebrow">PRIVATE CONSOLE</span>
        <h1>tg-signer</h1>
        <p>安全进入你的 Telegram 自动化工作台</p>
      </div>
      <el-input
        v-model="code"
        type="password"
        show-password
        placeholder="授权码"
        size="large"
        aria-label="授权码"
        @keyup.enter="submit"
      />
      <el-button
        type="primary"
        size="large"
        class="login-btn"
        :loading="loading"
        @click="submit"
      >
        登录
      </el-button>
      <p class="login-hint">
        本服务启用了授权码，请输入环境变量
        <code>TG_SIGNER_GUI_AUTHCODE</code> 对应的授权码
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Promotion } from '@element-plus/icons-vue'
import { login, checkAuth } from '../api'

const router = useRouter()
const code = ref('')
const loading = ref(false)

async function submit() {
  if (loading.value) return
  if (!code.value) {
    ElMessage.warning('请输入授权码')
    return
  }
  loading.value = true
  try {
    const data = await login(code.value)
    if (data.ok) {
      ElMessage.success('登录成功')
      router.push('/')
    } else {
      ElMessage.error(data.message || '授权码错误')
    }
  } catch (error) {
    const detail = error.response && error.response.data && error.response.data.detail
    ElMessage.error(detail || '登录失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const status = await checkAuth()
    if (!status.required) {
      ElMessage.info('本服务未启用授权码，无需登录')
      router.push('/')
    }
  } catch (error) {
    /* 忽略瞬时错误 */
  }
})
</script>

<style scoped>
.login-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(900px 460px at 12% 0%, rgba(37, 105, 208, 0.16), transparent 62%),
    radial-gradient(760px 420px at 92% 100%, rgba(13, 27, 42, 0.1), transparent 58%),
    var(--ts-surface);
}
.login-panel {
  width: min(420px, calc(100vw - 32px));
  padding: 44px 40px 32px;
  background: var(--ts-card);
  border: 1px solid var(--ts-line);
  border-radius: 20px;
  box-shadow: 0 22px 60px rgba(15, 31, 51, 0.1);
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.login-brand {
  margin-bottom: 10px;
}
.brand-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  border-radius: 14px;
  background: var(--ts-navy);
  color: #8DBBFF;
  font-size: 24px;
  margin-bottom: 14px;
}
.login-eyebrow {
  display: block;
  margin-bottom: 6px;
  color: var(--ts-sky);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 1.5px;
}
.login-brand h1 {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  color: var(--ts-ink);
  letter-spacing: -0.5px;
}
.login-brand p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--ts-muted);
}
.login-btn {
  width: 100%;
}
.login-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--ts-muted);
  line-height: 1.6;
}
.login-hint code {
  font-family: var(--el-font-family-mono);
  font-size: 11px;
  background: var(--ts-surface);
  border: 1px solid var(--ts-line);
  border-radius: 4px;
  padding: 1px 5px;
}

@media (max-width: 480px) {
  .login-panel {
    padding: 34px 24px 26px;
  }
}
</style>
