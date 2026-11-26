<template>
  <el-card shadow="never">
    <div class="ts-intro">
      <div>
        <span class="ts-section-label">账号会话</span>
        <p class="ts-section-caption">管理已登录的 Telegram 会话，检查授权状态或添加新账号。</p>
      </div>
      <el-button type="primary" @click="openLogin">登录新账号</el-button>
    </div>
    <div class="account-metrics">
      <div class="account-metric">
        <span class="ts-metric-value">{{ accounts.length }}</span>
        <span class="ts-metric-label">已发现账号</span>
      </div>
      <div class="account-metric">
        <span class="ts-metric-value">{{ sessionCount }}</span>
        <span class="ts-metric-label">可用会话</span>
      </div>
      <div class="account-metric">
        <span class="ts-metric-value ts-metric-value--muted">本地</span>
        <span class="ts-metric-label">凭据存储</span>
      </div>
    </div>
    <el-table v-loading="loading" :data="accounts">
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
          <span class="session-file">
            {{ row.session_file ? row.session_file.split(/[\\/]/).pop() : '—' }}
          </span>
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
      <el-radio-group v-model="loginMode" class="login-mode" @change="onModeChange">
        <el-radio-button value="code">验证码登录</el-radio-button>
        <el-radio-button value="qr">二维码登录</el-radio-button>
      </el-radio-group>

      <template v-if="loginMode === 'code'">
        <el-steps
          :active="loginStep"
          finish-status="success"
          simple
          style="margin-bottom: 16px"
        >
          <el-step title="发送验证码" />
          <el-step title="完成登录" />
        </el-steps>
        <div class="ts-callout dialog-callout">
          <el-icon><InfoFilled /></el-icon>
          <span>
            验证码可能发送到已登录设备的 Telegram、短信或电话；未收到可点「重新发送」。
          </span>
        </div>
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
              {{ codeSent ? '验证码已发送，请按提示查收' : '发送成功后输入验证码并完成登录' }}
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
          <el-form-item v-if="codeSent">
            <el-button
              text
              type="primary"
              :loading="resending"
              :disabled="resendIn > 0"
              @click="resendCode"
            >
              {{ resendIn > 0 ? `重新发送（${resendIn}s）` : '没收到？重新发送' }}
            </el-button>
            <span v-if="deliveryLabel" class="hint" style="margin-left: 8px">
              本次通过{{ deliveryLabel }}发送
            </span>
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
      </template>

      <template v-else>
        <div class="ts-callout dialog-callout">
          <el-icon><InfoFilled /></el-icon>
          <span>
            用<strong>已登录该账号</strong>的 Telegram 扫码即可登录，不需要短信或验证码。
            手机端路径：设置 → 隐私和安全 → 设备 → 扫描二维码。
          </span>
        </div>
        <el-form label-width="90px">
          <el-form-item label="账号名">
            <el-input
              v-model="loginAccount"
              placeholder="例如 my_account，对应 session 文件名"
              @keyup.enter="startQr"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="qrStarting" @click="startQr">
              生成二维码
            </el-button>
            <span class="hint" style="margin-left: 8px">{{ qrHint }}</span>
          </el-form-item>
        </el-form>
        <div v-if="qrSvg" class="qr-box">
          <div class="qr-image" v-html="qrSvg"></div>
          <div class="qr-meta">
            <p>{{ qrMessage }}</p>
            <p class="hint">二维码 {{ qrExpires }} 秒后自动刷新，请尽快扫描</p>
          </div>
        </div>
        <div v-else-if="qrUrl" class="hint qr-fallback">
          二维码渲染不可用，可在 Telegram 内打开：
          <code>{{ qrUrl }}</code>
        </div>
        <el-form v-if="qrState === 'password_needed'" label-width="90px">
          <el-form-item label="两步密码">
            <el-input
              v-model="password"
              type="password"
              show-password
              placeholder="该账号启用了两步验证"
              @keyup.enter="submitQrPassword"
            />
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              :loading="qrSubmitting"
              @click="submitQrPassword"
            >完成登录</el-button>
          </el-form-item>
        </el-form>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import api, { errMsg, useList } from '../api'

const {
  list: accounts,
  loading,
  refresh,
} = useList('/api/accounts', '账号列表加载失败')
const sessionCount = computed(() =>
  accounts.value.filter((account) => account.kind && account.kind.length).length
)
const loginVisible = ref(false)
const loginMode = ref('code')
const loginAccount = ref('')
const phone = ref('')
const code = ref('')
const password = ref('')
const loginStatus = ref('')
const sending = ref(false)
const resending = ref(false)
const completing = ref(false)
const codeSent = ref(false)
const loginStep = ref(0)
const codeInput = ref(null)
const resendIn = ref(0)
const deliveryLabel = ref('')
const qrStarting = ref(false)
const qrSubmitting = ref(false)
const qrState = ref('idle')
const qrSvg = ref('')
const qrUrl = ref('')
const qrMessage = ref('')
const qrExpires = ref(0)
const qrHint = ref('生成后用手机 Telegram 扫码')
let resendTimer = null
let qrTimer = null

function stopResendTimer() {
  if (resendTimer) {
    clearInterval(resendTimer)
    resendTimer = null
  }
}

function startResendCountdown(seconds) {
  stopResendTimer()
  resendIn.value = Math.max(0, Number(seconds) || 0)
  if (!resendIn.value) return
  resendTimer = setInterval(() => {
    resendIn.value -= 1
    if (resendIn.value <= 0) {
      resendIn.value = 0
      stopResendTimer()
    }
  }, 1000)
}

function openLogin() {
  loginAccount.value = ''
  phone.value = ''
  code.value = ''
  password.value = ''
  loginStatus.value = ''
  codeSent.value = false
  loginStep.value = 0
  resendIn.value = 0
  deliveryLabel.value = ''
  loginMode.value = 'code'
  resetQr()
  stopResendTimer()
  loginVisible.value = true
}

function resetQr() {
  stopQrPoll()
  qrState.value = 'idle'
  qrSvg.value = ''
  qrUrl.value = ''
  qrMessage.value = ''
  qrExpires.value = 0
  qrHint.value = '生成后用手机 Telegram 扫码'
}

function stopQrPoll() {
  if (qrTimer) {
    clearInterval(qrTimer)
    qrTimer = null
  }
}

function startQrPoll() {
  stopQrPoll()
  qrTimer = setInterval(pollQr, 2000)
}

function applyQr(data) {
  qrState.value = data.state || 'idle'
  qrSvg.value = data.svg || ''
  qrUrl.value = data.url || ''
  qrMessage.value = data.message || ''
  qrExpires.value = Number(data.expires_in) || 0
  if (qrState.value === 'ok') {
    stopQrPoll()
    ElMessage.success(qrMessage.value || '登录成功')
    loginVisible.value = false
    refresh()
  } else if (qrState.value === 'error') {
    stopQrPoll()
    qrHint.value = '生成失败'
    ElMessage.error(qrMessage.value || '二维码登录失败')
  } else if (qrState.value === 'idle') {
    stopQrPoll()
    qrHint.value = '登录会话已失效，请重新生成'
  }
}

async function pollQr() {
  const accountName = loginAccount.value.trim()
  if (!accountName) {
    stopQrPoll()
    return
  }
  try {
    const { data } = await api.get('/api/accounts/qr-status', {
      params: { account: accountName },
    })
    applyQr(data)
  } catch (error) {
    stopQrPoll()
    ElMessage.error(errMsg(error))
  }
}

async function startQr() {
  if (!loginAccount.value.trim()) {
    ElMessage.warning('请填写账号名')
    return
  }
  qrStarting.value = true
  qrHint.value = '正在生成二维码…'
  try {
    const { data } = await api.post('/api/accounts/qr-start', {
      account: loginAccount.value.trim(),
    })
    if (data.result === 'ok') {
      qrHint.value = '等待扫码'
      applyQr(data)
      startQrPoll()
    } else {
      qrHint.value = '未生成二维码'
      ElMessage.warning(data.message)
    }
  } catch (error) {
    qrHint.value = '生成失败'
    ElMessage.error(errMsg(error))
  } finally {
    qrStarting.value = false
  }
}

async function submitQrPassword() {
  if (!password.value.trim()) {
    ElMessage.warning('请填写两步验证密码')
    return
  }
  qrSubmitting.value = true
  try {
    const { data } = await api.post('/api/accounts/qr-password', {
      account: loginAccount.value.trim(),
      password: password.value.trim(),
    })
    if (data.result === 'ok') {
      stopQrPoll()
      ElMessage.success(data.message || '登录成功')
      loginVisible.value = false
      refresh()
    } else {
      ElMessage.error(data.message)
    }
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    qrSubmitting.value = false
  }
}

function onModeChange() {
  if (loginMode.value !== 'qr') {
    resetQr()
  }
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
    deliveryLabel.value = data.delivery_label || ''
    if (data.result === 'ok') {
      ElMessage.success(data.message)
      codeSent.value = true
      loginStep.value = 1
      startResendCountdown(data.resend_after)
      nextTick(() => {
        codeInput.value && codeInput.value.focus()
      })
    } else if (data.result === 'already') {
      codeSent.value = false
      loginStep.value = 0
      ElMessage.warning(data.message)
    } else {
      codeSent.value = false
      loginStep.value = 0
      ElMessage.error(data.message)
    }
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    sending.value = false
  }
}

async function resendCode() {
  if (resending.value || resendIn.value > 0) return
  resending.value = true
  try {
    const { data } = await api.post('/api/accounts/resend-code', {
      account: loginAccount.value.trim(),
    })
    loginStatus.value = data.message
    deliveryLabel.value = data.delivery_label || ''
    startResendCountdown(data.resend_after)
    if (data.result === 'ok') {
      ElMessage.success(data.message)
      codeSent.value = true
      nextTick(() => {
        codeInput.value && codeInput.value.focus()
      })
    } else {
      ElMessage.error(data.message)
    }
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    resending.value = false
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

watch(loginVisible, (visible) => {
  if (!visible) {
    stopResendTimer()
    stopQrPoll()
  }
})

onMounted(refresh)
onUnmounted(() => {
  stopResendTimer()
  stopQrPoll()
})
</script>

<style scoped>
.login-mode {
  margin-bottom: 16px;
}
.account-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 22px;
}
.account-metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border: 1px solid var(--ts-line);
  border-radius: 12px;
  background: #FAFCFF;
}
.session-file {
  color: var(--ts-ink-2);
  font-family: var(--el-font-family-mono);
  font-size: 12px;
}
.dialog-callout {
  margin: -2px 0 18px;
}
.qr-box {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 14px;
  margin-bottom: 16px;
  border: 1px solid var(--ts-line);
  border-radius: 12px;
  background: #FAFCFF;
}
.qr-image {
  flex: none;
  line-height: 0;
}
.qr-image :deep(svg) {
  width: 180px;
  height: 180px;
}
.qr-meta {
  min-width: 0;
}
.qr-meta p {
  margin: 0 0 8px;
  line-height: 1.5;
}
.qr-fallback {
  display: block;
  margin-bottom: 16px;
  word-break: break-all;
}
.kind-tag {
  margin-right: 4px;
}

@media (max-width: 600px) {
  .account-metrics {
    grid-template-columns: 1fr;
  }
  .qr-box {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
