<template>
  <el-dialog
    :model-value="visible"
    title="交互式配置向导"
    width="680px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
    @open="initFromProps"
  >
    <el-steps :active="step" finish-status="success" align-center style="margin-bottom: 20px">
      <el-step title="基础设置" />
      <el-step title="签到任务" />
    </el-steps>

    <!-- Step 1: 基础设置 -->
    <el-form v-show="step === 0" label-width="120px" style="max-width: 560px">
      <el-form-item label="任务名称" required>
        <el-input v-model="taskName" placeholder="例如 my_sign" />
      </el-form-item>
      <el-form-item label="签到时间">
        <el-input v-model="signAt" placeholder="06:00:00 或 0 6 * * *" />
        <div class="hint">支持具体时间（06:00:00）或 Cron 表达式（0 6 * * *）</div>
      </el-form-item>
      <el-form-item label="随机延迟（秒）">
        <el-input-number v-model="randomSeconds" :min="0" :step="1" />
        <div class="hint" style="margin-left: 8px">在签到时间基础上追加随机延迟，0 表示不延迟</div>
      </el-form-item>
    </el-form>

    <!-- Step 2: 签到任务列表 -->
    <div v-show="step === 1">
      <div class="row">
        <span class="hint">已添加 {{ chats.length }} 个签到任务</span>
        <span style="flex: 1"></span>
        <el-button type="primary" size="small" @click="openTask(null)">添加任务</el-button>
      </div>
      <el-empty
        v-if="!chats.length"
        description="暂无任务，点击「添加任务」开始"
        :image-size="60"
      />
      <div v-else class="task-list">
        <el-card v-for="(chat, idx) in chats" :key="idx" shadow="hover" class="task-card">
          <div class="row">
            <span class="task-index">#{{ idx + 1 }}</span>
            <div class="task-info">
              <div class="task-title">{{ chat.chat_id }}</div>
              <div class="hint">
                {{ chat.name || '未命名' }}
                <template v-if="chat.message_thread_id"> · 话题 {{ chat.message_thread_id }}</template>
                <template v-if="chat.delete_after"> · 删后 {{ chat.delete_after }}s</template>
              </div>
              <div class="hint">{{ actionSummary(chat.actions) }}</div>
            </div>
            <span style="flex: 1"></span>
            <el-button size="small" @click="openTask(idx)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="removeTask(idx)">删除</el-button>
          </div>
        </el-card>
      </div>
    </div>

    <template #footer>
      <el-button v-if="step === 1" @click="step = 0">上一步</el-button>
      <el-button v-if="step === 0" type="primary" @click="step = 1">下一步</el-button>
      <template v-if="step === 1">
        <el-button @click="$emit('update:visible', false)">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAll">保存配置</el-button>
      </template>
    </template>

    <!-- 任务编辑对话框 -->
    <el-dialog
      v-model="taskDialogVisible"
      :title="taskIndex === null ? '添加签到任务' : '编辑签到任务'"
      width="560px"
      append-to-body
      :close-on-click-modal="false"
    >
      <el-form label-width="120px">
        <el-form-item label="Chat ID" required>
          <el-input v-model="draft.chatId" placeholder="整数 ID 或 @username" />
          <div class="hint">支持整数 chat_id（如 -1001234567890）或 @username</div>
        </el-form-item>
        <el-form-item label="任务名称">
          <el-input v-model="draft.name" placeholder="可选，便于识别" />
        </el-form-item>
        <el-form-item label="话题">
          <el-switch v-model="draft.threadEnabled" />
          <el-input-number
            v-model="draft.threadId"
            :min="0"
            :disabled="!draft.threadEnabled"
            style="width: 160px; margin-left: 8px"
          />
          <div class="hint" style="margin-left: 8px">
            {{ draft.threadEnabled ? '群组话题 message_thread_id' : '未启用群组话题' }}
          </div>
        </el-form-item>
        <el-form-item label="删除消息（秒）">
          <el-input-number
            v-model="draft.deleteAfter"
            :min="0"
            :step="1"
            clearable
            style="width: 160px"
          />
          <div class="hint" style="margin-left: 8px">发送后自动删除，留空表示不删除</div>
        </el-form-item>
        <el-form-item label="动作列表" required>
          <div class="action-editor">
            <div v-for="(act, ai) in draft.actions" :key="ai" class="action-row">
              <el-select v-model="act.type" style="width: 210px" @change="onActionTypeChange(act)">
                <el-option
                  v-for="opt in ACTION_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-input
                v-if="act.type === 'send_text'"
                v-model="act.text"
                placeholder="要发送的文本"
                style="width: 200px"
              />
              <el-input
                v-else-if="act.type === 'click_keyboard'"
                v-model="act.text"
                placeholder="要点击的按钮文本"
                style="width: 200px"
              />
              <el-select v-else-if="act.type === 'send_dice'" v-model="act.dice" style="width: 120px">
                <el-option v-for="d in DICE_OPTIONS" :key="d" :label="d" :value="d" />
              </el-select>
              <span
                v-else-if="act.type === 'choose_option_by_image'"
                class="hint"
              >自动识别图片并选择选项（需配置大模型）</span>
              <span
                v-else-if="act.type === 'reply_calculation'"
                class="hint"
              >自动回复消息中的计算题（需配置大模型）</span>
              <el-button type="danger" plain size="small" @click="removeAction(ai)">
                删除
              </el-button>
            </div>
            <el-button class="add-action" @click="addAction">添加动作</el-button>
          </div>
          <div class="hint">第一个动作必须是「发送普通文本」或「发送 Dice emoji」</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTask">确定</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const props = defineProps({
  visible: Boolean,
  initial: { type: Object, default: null }, // { name, payload }
})
const emit = defineEmits(['update:visible', 'saved'])

const ACTION_OPTIONS = [
  { value: 'send_text', label: '发送普通文本' },
  { value: 'send_dice', label: '发送 Dice emoji' },
  { value: 'click_keyboard', label: '根据文本点击键盘' },
  { value: 'choose_option_by_image', label: '根据图片选择选项' },
  { value: 'reply_calculation', label: '回复计算题' },
]
const DICE_OPTIONS = ['🎲', '🎯', '🏀', '⚽', '🎳', '🎰']
const ACTION_LABELS = {
  1: '发送文本',
  2: '发送骰子',
  3: '点击按钮',
  4: '图片选选项',
  5: '回复计算题',
}

const step = ref(0)
const taskName = ref('my_sign')
const signAt = ref('06:00:00')
const randomSeconds = ref(0)
const chats = ref([])
const saving = ref(false)

const taskDialogVisible = ref(false)
const taskIndex = ref(null)
const draft = ref(emptyDraft())

function emptyDraft() {
  return {
    chatId: '',
    name: '',
    threadEnabled: false,
    threadId: null,
    deleteAfter: null,
    actions: [{ type: 'send_text', text: '' }],
  }
}

function parseAction(action) {
  switch (action.action) {
    case 1:
      return { type: 'send_text', text: action.text || '' }
    case 2:
      return { type: 'send_dice', dice: action.dice || '🎲' }
    case 3:
      return { type: 'click_keyboard', text: action.text || '' }
    case 4:
      return { type: 'choose_option_by_image' }
    case 5:
      return { type: 'reply_calculation' }
    default:
      return { type: 'send_text', text: '' }
  }
}

function initFromProps() {
  step.value = 0
  const initial = props.initial
  if (initial && initial.payload && Array.isArray(initial.payload.chats)) {
    taskName.value = initial.name || 'my_sign'
    signAt.value = initial.payload.sign_at || '06:00:00'
    randomSeconds.value = initial.payload.random_seconds || 0
    chats.value = initial.payload.chats.map((chat) => ({
      chat_id: chat.chat_id,
      message_thread_id: chat.message_thread_id || null,
      name: chat.name || '',
      delete_after: chat.delete_after || null,
      actions: (chat.actions || []).map(parseAction),
    }))
  } else {
    taskName.value = 'my_sign'
    signAt.value = '06:00:00'
    randomSeconds.value = 0
    chats.value = []
  }
}

function actionSummary(actions) {
  if (!actions || !actions.length) return '无动作'
  return actions.map((a) => ACTION_LABELS[a.action] || '动作' + a.action).join(' → ')
}

function openTask(index) {
  taskIndex.value = index
  if (index === null) {
    draft.value = emptyDraft()
  } else {
    const chat = chats.value[index]
    draft.value = {
      chatId: String(chat.chat_id),
      name: chat.name || '',
      threadEnabled: Boolean(chat.message_thread_id),
      threadId: chat.message_thread_id || null,
      deleteAfter: chat.delete_after || null,
      actions: (chat.actions || []).map(parseAction),
    }
  }
  taskDialogVisible.value = true
}

function removeTask(index) {
  chats.value.splice(index, 1)
}

function addAction() {
  draft.value.actions.push({ type: 'send_text', text: '' })
}

function removeAction(index) {
  draft.value.actions.splice(index, 1)
}

function onActionTypeChange(act) {
  if (act.type === 'send_dice' && !act.dice) {
    act.dice = '🎲'
  }
  if (act.type === 'send_text' && !act.text) {
    act.text = ''
  }
  if (act.type === 'click_keyboard' && !act.text) {
    act.text = ''
  }
}

function parseChatId(raw) {
  const value = String(raw || '').trim()
  if (!value) throw new Error('Chat ID 不能为空')
  if (value.startsWith('@')) {
    if (value.length === 1) throw new Error('用户名不能为空')
    return value
  }
  const num = Number(value)
  if (!Number.isInteger(num)) throw new Error('Chat ID 必须是整数或 @用户名')
  return num
}

function toActionJSON(act) {
  switch (act.type) {
    case 'send_text':
      return { action: 1, text: (act.text || '').trim() }
    case 'send_dice':
      return { action: 2, dice: act.dice || '🎲' }
    case 'click_keyboard':
      return { action: 3, text: (act.text || '').trim() }
    case 'choose_option_by_image':
      return { action: 4 }
    case 'reply_calculation':
      return { action: 5 }
    default:
      throw new Error('未知动作类型')
  }
}

function validateTask() {
  let chatId
  try {
    chatId = parseChatId(draft.value.chatId)
  } catch (error) {
    throw new Error(error.message)
  }
  if (!draft.value.actions.length) {
    throw new Error('至少需要配置一个动作')
  }
  const first = draft.value.actions[0]
  if (first.type !== 'send_text' && first.type !== 'send_dice') {
    throw new Error('第一个动作必须是「发送普通文本」或「发送 Dice emoji」')
  }
  for (const act of draft.value.actions) {
    if (act.type === 'send_text' && !(act.text || '').trim()) {
      throw new Error('「发送普通文本」动作需要填写文本内容')
    }
    if (act.type === 'click_keyboard' && !(act.text || '').trim()) {
      throw new Error('「根据文本点击键盘」动作需要填写按钮文本')
    }
  }
  let threadId = null
  if (draft.value.threadEnabled) {
    if (draft.value.threadId === null || draft.value.threadId === undefined || draft.value.threadId === '') {
      throw new Error('启用话题后必须填写 message_thread_id')
    }
    threadId = Number(draft.value.threadId)
  }
  return {
    chat_id: chatId,
    message_thread_id: threadId,
    name: (draft.value.name || '').trim() || null,
    delete_after:
      draft.value.deleteAfter === null || draft.value.deleteAfter === undefined || draft.value.deleteAfter === ''
        ? null
        : Number(draft.value.deleteAfter),
    actions: draft.value.actions.map(toActionJSON),
  }
}

function saveTask() {
  try {
    const chat = validateTask()
    if (taskIndex.value === null) {
      chats.value.push(chat)
    } else {
      chats.value[taskIndex.value] = chat
    }
    taskDialogVisible.value = false
  } catch (error) {
    ElMessage.warning(error.message)
  }
}

async function saveAll() {
  const name = (taskName.value || '').trim()
  if (!name) {
    ElMessage.warning('任务名称不能为空')
    return
  }
  if (!chats.value.length) {
    ElMessage.warning('请至少添加一个签到任务')
    return
  }
  const payload = {
    chats: chats.value,
    sign_at: (signAt.value || '').trim(),
    random_seconds: Number(randomSeconds.value) || 0,
    sign_interval: 1,
  }
  saving.value = true
  try {
    const { data } = await api.post(
      `/api/configs/signer/${encodeURIComponent(name)}`,
      payload
    )
    ElMessage.success(`配置 ${data.name} 保存成功`)
    emit('saved', data.name)
    emit('update:visible', false)
  } catch (error) {
    const detail =
      (error.response && error.response.data && error.response.data.detail) ||
      error.message
    ElMessage.error('保存失败: ' + detail)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.task-card {
  margin-bottom: 0;
}
.task-index {
  font-weight: 600;
  color: #909399;
  width: 28px;
}
.task-info {
  flex: 1;
  min-width: 0;
}
.task-title {
  font-weight: 500;
}
.action-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.add-action {
  align-self: flex-start;
}
</style>
