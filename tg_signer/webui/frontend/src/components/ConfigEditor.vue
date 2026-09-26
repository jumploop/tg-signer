<template>
  <el-card v-loading="loading" shadow="never" class="config-editor">
    <div class="editor-toolbar">
      <div class="toolbar-fields">
      <el-select
        v-model="selected"
        placeholder="选择已有配置"
        class="config-select"
        filterable
        clearable
        @clear="newConfig"
      >
        <el-option v-for="n in names" :key="n" :label="n" :value="n" />
      </el-select>
      <el-input
        v-model="name"
        placeholder="配置名称"
        class="config-name"
        clearable
        :disabled="editing"
      />
      <el-button @click="newConfig">新建</el-button>
      <el-button @click="fillTemplate">填充模板</el-button>
      </div>
      <div class="toolbar-actions">
      <el-button type="primary" :loading="saving" @click="save">
        {{ editing ? '保存修改' : '保存' }}
      </el-button>
      <el-button type="danger" plain :disabled="!editing" @click="remove">
        删除
      </el-button>
      <el-button :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </div>
    <div class="editor-status">
      <div>
        <span class="section-label">{{ kindLabel }}</span>
        <p class="hint">{{ hint }}</p>
      </div>
      <el-tag :type="editing ? 'primary' : 'info'" effect="light" round>
        {{ editing ? '编辑中' : '新建模式' }}
      </el-tag>
    </div>
    <div class="code-heading">
      <span>JSON 配置</span>
      <span class="hint">保存前会自动校验 JSON 格式</span>
    </div>
    <el-input
      v-model="jsonText"
      type="textarea"
      :rows="20"
      class="editor mono"
      placeholder="{}"
    />
  </el-card>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { asArray } from '../api'

const props = defineProps({
  kind: String,
  prefillChat: String,
  prefillTitle: String,
  prefillUsername: String,
})
const emit = defineEmits(['applied'])

const names = ref([])
const selected = ref(null)
const name = ref('')
const jsonText = ref('')
const hint = ref('')
const saving = ref(false)
const loading = ref(false)

const editing = computed(() => selected.value !== null && selected.value !== '')
const kindLabel = computed(() =>
  props.kind === 'signer' ? 'Signer 签到配置' : 'Automation 自动化配置'
)

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get(`/api/configs/${props.kind}`)
    names.value = asArray(data.names)
    if (!editing.value && names.value.length === 0) {
      hint.value = '暂无配置。填写名称后粘贴 JSON，或点击「填充模板」「新建」开始。'
    }
  } catch (error) {
    hint.value = '配置列表加载失败，请确认 WebUI 服务正常运行。'
  } finally {
    loading.value = false
  }
}

async function loadRaw(target) {
  if (!target) return
  try {
    const { data } = await api.get(
      `/api/configs/${props.kind}/${encodeURIComponent(target)}`
    )
    name.value = data.name
    selected.value = data.name
    jsonText.value = JSON.stringify(data.payload, null, 2)
    hint.value = data.updated_from_old
      ? '该配置已自动迁移为当前结构（保存时将写入新格式）。路径: ' + data.path
      : `正在编辑: ${data.name}。路径: ${data.path}`
  } catch (error) {
    ElMessage.error('配置加载失败: ' + errMsg(error))
  }
}

function newConfig() {
  // 保留当前编辑器内容，方便「另存为」：清除选择与名称即进入新建模式
  selected.value = null
  name.value = ''
  hint.value = names.value.length
    ? '新建配置：填写名称并编辑 JSON（可点击「填充模板」）。'
    : '暂无配置。填写名称后粘贴 JSON，或点击「填充模板」开始。'
}

async function fillTemplate() {
  if (jsonText.value.trim() && jsonText.value !== '{}') {
    try {
      await ElMessageBox.confirm(
        '填充模板将覆盖当前编辑器内容，是否继续？',
        '提示',
        { type: 'warning', confirmButtonText: '覆盖', cancelButtonText: '取消' }
      )
    } catch (error) {
      return
    }
  }
  try {
    const { data } = await api.get(`/api/configs/${props.kind}/template`)
    jsonText.value = JSON.stringify(data.payload, null, 2)
    hint.value = editing.value || name.value.trim()
      ? '已填充模板（可继续编辑）。'
      : '已填充模板，填写配置名称后保存。'
    ElMessage.success('已填充模板')
  } catch (error) {
    ElMessage.error(errMsg(error))
  }
}

function parseJson() {
  try {
    return JSON.parse(jsonText.value)
  } catch (error) {
    ElMessage.error('JSON 格式错误: ' + error.message)
    return null
  }
}

async function save() {
  const payload = parseJson()
  if (payload === null) return
  const target = (name.value || '').trim()
  if (!editing.value && !target) {
    ElMessage.warning('请填写配置名称')
    return
  }
  saving.value = true
  try {
    const saveName = editing.value ? selected.value : target
    const { data } = await api.post(
      `/api/configs/${props.kind}/${encodeURIComponent(saveName)}`,
      payload
    )
    ElMessage.success(editing.value ? '修改已保存' : `配置 ${data.name} 已创建`)
    name.value = data.name
    selected.value = data.name
    hint.value = '路径: ' + data.path
    await refresh()
  } catch (error) {
    ElMessage.error(errMsg(error))
  } finally {
    saving.value = false
  }
}

async function remove() {
  const target = selected.value
  if (!target) return
  try {
    await ElMessageBox.confirm(
      `确认删除配置 ${target}？删除后不可恢复。`,
      '提示',
      { type: 'warning', confirmButtonText: '删除' }
    )
  } catch (error) {
    return
  }
  try {
    await api.delete(`/api/configs/${props.kind}/${encodeURIComponent(target)}`)
    ElMessage.success('已删除')
    newConfig()
    await refresh()
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

function fillChatId(payload, chat) {
  if (props.kind === 'signer') {
    if (!Array.isArray(payload.chats) || !payload.chats.length) return null
    payload.chats[0].chat_id = toChatValue(chat)
    return 'chats[0].chat_id'
  }
  if (props.kind === 'automation') {
    const rule = Array.isArray(payload.rules) ? payload.rules[0] : null
    if (!rule || !Array.isArray(rule.triggers) || !rule.triggers.length) return null
    const trigger = rule.triggers[0]
    if (!trigger.params || typeof trigger.params !== 'object') trigger.params = {}
    trigger.params.chat_id = toChatValue(chat)
    // 过滤器同样锁定该群，避免其他群的消息也命中这条规则
    if (rule.filters && typeof rule.filters === 'object') {
      rule.filters.chat_id = toChatValue(chat)
    }
    return 'rules[0].triggers[0].params.chat_id'
  }
  return null
}

// 数字 ID 必须写成 JSON 数字。automation 的 _match_chat 只对 int 做数字比较,
// 字符串 "-1001234567890" 会被当作 @username 分支,规则将永不命中。
function toChatValue(raw) {
  const text = String(raw).trim()
  return /^-?\d+$/.test(text) ? Number(text) : text
}

// Signer 任务名优先用群组标题，其次用用户名；同时给一个随机的签到延迟。
// 只在新建时填：模板里的「示例任务」/random_seconds:0 是占位值需要替换，
// 而编辑已有配置时不能抹掉用户自己填的群组名和延迟（与 suggestName 同理）。
function fillSignerExtras(payload) {
  if (props.kind !== 'signer' || editing.value) return null
  const chat = Array.isArray(payload.chats) ? payload.chats[0] : null
  if (!chat) return null
  const label = (props.prefillTitle || props.prefillUsername || '').trim()
  if (label) chat.name = label
  payload.random_seconds = 100 + Math.floor(Math.random() * 901)
  return label
}

async function applyPrefill(chat) {
  let payload
  const current = jsonText.value.trim()
  if (!current || current === '{}') {
    try {
      const { data } = await api.get(`/api/configs/${props.kind}/template`)
      payload = data.payload
    } catch (error) {
      ElMessage.error(errMsg(error))
      return
    }
  } else {
    try {
      payload = JSON.parse(current)
    } catch (error) {
      ElMessage.error('JSON 格式错误，无法填入: ' + error.message)
      return
    }
  }
  const field = fillChatId(payload, chat)
  if (!field) {
    ElMessage.warning('当前 JSON 结构中没有可填入的 chat_id 字段，请手动编辑')
    return
  }
  const label = fillSignerExtras(payload)
  jsonText.value = JSON.stringify(payload, null, 2)
  await suggestName(chat)
  const extra = label ? `，任务名 = ${label}` : ''
  hint.value = `已填入 ${field} = ${chat}${extra}，确认后点「保存」。`
  ElMessage.success(`已填入 ${field}: ${chat}${extra}`)
  emit('applied')
}

// 新建模式下自动生成配置名；已在编辑或用户已填名时保持原样。
async function suggestName(chat) {
  if (editing.value || name.value.trim()) return
  try {
    const { data } = await api.get(`/api/configs/${props.kind}/suggest-name`, {
      params: {
        chat_id: chat,
        title: props.prefillTitle || '',
        username: props.prefillUsername || '',
      },
    })
    name.value = data.name
  } catch (error) {
    ElMessage.warning('自动生成配置名失败，请手动填写')
  }
}

watch(selected, (value) => {
  if (value) loadRaw(value)
})

watch(
  () => props.prefillChat,
  (chat) => {
    if (chat) applyPrefill(String(chat))
  },
  { immediate: true }
)

onMounted(refresh)
</script>

<style scoped>
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
}
.toolbar-fields,
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.config-select {
  width: 250px;
}
.config-name {
  width: 190px;
}
.editor-status,
.code-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}
.editor-status {
  align-items: flex-start;
  margin-bottom: 22px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--ts-line);
}
.section-label {
  display: block;
  margin-bottom: 5px;
  color: var(--ts-ink);
  font-size: 15px;
  font-weight: 700;
}
.editor-status .hint {
  margin: 0;
}
.code-heading {
  margin-bottom: 10px;
  color: var(--ts-ink-2);
  font-size: 13px;
  font-weight: 700;
}
.config-editor :deep(.el-textarea__inner) {
  min-height: 460px !important;
  line-height: 1.65;
  padding: 16px;
  resize: vertical;
}

@media (max-width: 900px) {
  .editor-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-actions {
    width: 100%;
  }
}

@media (max-width: 600px) {
  .toolbar-fields,
  .toolbar-actions {
    width: 100%;
  }

  .toolbar-fields > *,
  .toolbar-actions > * {
    flex: 1 1 auto;
  }

  .config-select,
  .config-name {
    width: 100%;
  }

  .editor-status,
  .code-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
