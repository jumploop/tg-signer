<template>
  <el-card shadow="never">
    <div class="row">
      <span class="hint">已发现 {{ accounts.length }} 个账号</span>
      <span style="flex: 1"></span>
      <el-button type="primary" @click="openLogin">登录新账号</el-button>
    </div>
    <el-table :data="accounts">
      <el-table-column prop="account" label="账号" min-width="140" />
      <el-table-column label="会话类型" width="240">
        <template #default="{ row }">
          <el-tag
            v-for="k in row.kind"
            :key="k"
            size="small"
            class="kind-tag"
            :type="k === 'session' ? 'success' : 'warning'"
          >
            {{ k === 'session' ? 'Session 文件' : 'Session String' }}
          </el-tag>
          <span v-if="!row.kind || !row.kind.length" class="hint">未知</span>
        </template>
      </el-table-column>
      <el-table-column label="Session 文件" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.session_file ? row.session_file.split(/[\\/]/).pop() : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" @click="check(row.account)">检查</el-button>
          <el-button size="small" type="danger" plain @click="doLogout(row.account)">
            登出并删除
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无账号，点击「登录新账号」开始" :image-size="60" />
      </template>
    </el-table>

    <el-dialog
      v-model="loginVisible"
      title="登录 Telegram 账号"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-steps :active="loginStep" finish-status="success" simple style="margin-bottom: 16px">
        <el-step title="发送验证码" />
        <el-step title="完成登录" />
      </el-steps>
      <el-form label-width="90px">
        <el-form-item label="账号名">
          <el-input
            v-model="loginAccount"
            placeholder="例如 my_account，对应 session 文件名"
          />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input
            v-model="phone"
            placeholder="+8613800138000"
            @keyup.enter="sendCode"
          />
        </el-form-item>
        <el-form-item>
          <el-button :loading="sending" @click="sendCode">发送验证码</el-button>
          <span class="hint" style="margin-left: 8px">
            {{ codeSent ? '验证码已发送，请查收 Telegram' : '发送成功后输入验证码并完成登录' }}
          </span>
        </el-form-item>
        <el-form-item label="验证码">
          <el-input
            ref="codeInput"
            v-model="code"
            :disabled="!codeSent"
            placeholder="Telegram 下发的登录验证码"
            @keyup.enter="complete"
          />
        </el-form-item>
        <el-form-item label="两步密码">
          <el-input
            v-model="password"
            type="password"
            show-password
            placeholder="如启用两步验证再填"
            @keyup.enter="complete"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="completing"
            :disabled="!codeSent"
            @click="complete"
          >完成登录</el-button>
          <span class="hint" style="margin-left: 8px">{{ loginStatus }}</span>
        </el-form-item>
      </el-form>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const accounts = ref([])
const loginVisible = ref(false)
const loginAccount = ref('')
const phone = ref('')
const code = ref('')
const password = ref('')
const loginStatus = ref('')
const sending = ref(false)
const completing = ref(false)
const codeSent = ref(false)
const loginStep = ref(0)
const codeInput = ref(null)

async function refresh() {
  const { data } = await api.get('/api/accounts')
  accounts.value = data
}

function openLogin() {
  loginAccount.value = ''
  phone.value = ''
  code.value = ''
  password.value = ''
  loginStatus.value = ''
  codeSent.value = false
  loginStep.value = 0
  loginVisible.value = true
}

async function sendCode() {
  if (!loginAccount.value.trim() || !phone.value.trim()) {
    ElMessage.warning('请填写账号名与手机号')
    return
  }
  sending.value = true
  try {
    const { data } = await api.post('/api/accounts/send-code', {
      account: loginAccount.value.trim(),
      phone: phone.value.trim(),
    })
    loginStatus.value = data.message
    if (data.result === 'error') {
      ElMessage.error(data.message)
    } else {
      ElMessage.success(data.message)
      codeSent.value = true
      loginStep.value = 1
      nextTick(() => {
        codeInput.value && codeInput.value.focus()
      })
    }
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    sending.value = false
  }
}

async function complete() {
  if (!code.value.trim()) {
    ElMessage.warning('请填写验证码')
    return
  }
  completing.value = true
  try {
    const { data } = await api.post('/api/accounts/complete-login', {
      account: loginAccount.value.trim(),
      code: code.value.trim(),
      password: password.value.trim() || null,
    })
    loginStatus.value = data.message
    if (data.result === 'password_needed') {
      ElMessage.info('需要两步验证密码，请填写后再次点击完成登录')
    } else if (data.result === 'ok') {
      ElMessage.success('登录成功')
      loginVisible.value = false
      refresh()
    } else {
      ElMessage.error(data.message)
    }
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    completing.value = false
  }
}

async function check(accountName) {
  const { data } = await api.get(
    `/api/accounts/${encodeURIComponent(accountName)}/authorized`
  )
  ElMessage[data.ok ? 'success' : 'warning'](data.message)
}

async function doLogout(accountName) {
  try {
    await ElMessageBox.confirm(
      `确认登出并删除 ${accountName} 的 Session 文件？`,
      '提示',
      { type: 'warning' }
    )
  } catch (error) {
    return
  }
  try {
    const { data } = await api.post('/api/accounts/logout', {
      account: accountName,
    })
    ElMessage.success(data.message)
    refresh()
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

<style scoped>
.kind-tag {
  margin-right: 4px;
}
</style>
