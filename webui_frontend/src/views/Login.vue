<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 style="margin-top: 0">tg-signer WebUI</h2>
      <p class="hint">本服务启用了授权码，请输入环境变量
        <code>TG_SIGNER_GUI_AUTHCODE</code> 对应的授权码。</p>
      <el-input
        v-model="code"
        type="password"
        show-password
        placeholder="授权码"
        @keyup.enter="submit"
      />
      <el-button type="primary" style="margin-top: 12px; width: 100%" @click="submit">
        登录
      </el-button>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api'

const router = useRouter()
const code = ref('')

async function submit() {
  if (!code.value) {
    ElMessage.warning('请输入授权码')
    return
  }
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
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  width: 360px;
  padding: 12px 8px;
}
.hint {
  font-size: 13px;
  color: #666;
}
</style>

