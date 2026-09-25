<template>
  <el-card shadow="never">
    <div class="row">
      <el-select
        v-model="selected"
        placeholder="选择已有配置"
        style="width: 260px"
        filterable
        clearable
        @clear="newConfig"
      >
        <el-option v-for="n in names" :key="n" :label="n" :value="n" />
      </el-select>
      <el-input
        v-model="name"
        placeholder="配置名称"
        style="width: 200px"
        clearable
        :disabled="editing"
      />
      <el-button @click="newConfig">新建</el-button>
      <el-button @click="fillTemplate">填充模板</el-button>
      <span style="flex: 1"></span>
      <el-button type="primary" :loading="saving" @click="save">
        {{ editing ? '保存修改' : '保存' }}
      </el-button>
      <el-button type="danger" plain :disabled="!editing" @click="remove">
        删除
      </el-button>
      <el-button @click="refresh">刷新</el-button>
    </div>
    <p class="hint">{{ hint }}</p>
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
import api from '../api'

const props = defineProps({ kind: String })

const names = ref([])
const selected = ref(null)
const name = ref('')
const jsonText = ref('')
const hint = ref('')
const saving = ref(false)

const editing = computed(() => selected.value !== null && selected.value !== '')

async function refresh() {
  const { data } = await api.get(`/api/configs/${props.kind}`)
  names.value = data.names
  if (!editing.value && names.value.length === 0) {
    hint.value = '暂无配置。填写名称后粘贴 JSON，或点击「填充模板」「新建」开始。'
  }
}

async function loadRaw(target) {
  if (!target) return
  const { data } = await api.get(
    `/api/configs/${props.kind}/${encodeURIComponent(target)}`
  )
  name.value = data.name
  selected.value = data.name
  jsonText.value = JSON.stringify(data.payload, null, 2)
  hint.value = data.updated_from_old
    ? '该配置已自动迁移为当前结构（保存时将写入新格式）。路径: ' + data.path
    : `正在编辑: ${data.name}。路径: ${data.path}`
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

watch(selected, (value) => {
  if (value) loadRaw(value)
})

onMounted(refresh)
</script>
