<template>
  <el-card shadow="never">
    <div class="row">
      <el-select v-model="selected" placeholder="选择已有配置" style="width: 260px">
        <el-option v-for="n in names" :key="n" :label="n" :value="n" />
      </el-select>
      <el-input v-model="name" placeholder="配置名称" style="width: 200px" clearable />
      <el-button @click="loadTemplate">模板</el-button>
      <el-button type="primary" @click="save">保存</el-button>
      <el-button type="danger" plain @click="remove">删除</el-button>
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
import { ref, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const props = defineProps({ kind: String })
const names = ref([])
const selected = ref(null)
const name = ref('')
const jsonText = ref('')
const hint = ref('')

async function refresh() {
  const { data } = await api.get(`/api/configs/${props.kind}`)
  names.value = data.names
}

async function loadRaw(target) {
  if (!target) return
  const { data } = await api.get(
    `/api/configs/${props.kind}/${encodeURIComponent(target)}`
  )
  name.value = data.name
  jsonText.value = JSON.stringify(data.payload, null, 2)
  hint.value = data.updated_from_old
    ? '该配置已自动迁移为当前结构（保存时将写入新格式）。路径: ' + data.path
    : '路径: ' + data.path
}

function loadTemplate() {
  api.get(`/api/configs/${props.kind}/template`).then(({ data }) => {
    jsonText.value = JSON.stringify(data.payload, null, 2)
    name.value = ''
    hint.value = '已加载模板，填写名称后保存。'
    ElMessage.success('已填充模板')
  }).catch((error) => ElMessage.error(errMsg(error)))
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
  if (!target) {
    ElMessage.warning('请填写配置名称')
    return
  }
  try {
    const { data } = await api.post(
      `/api/configs/${props.kind}/${encodeURIComponent(target)}`,
      payload
    )
    ElMessage.success('保存成功')
    name.value = data.name
    selected.value = data.name
    hint.value = '路径: ' + data.path
    await refresh()
  } catch (error) {
    ElMessage.error(errMsg(error))
  }
}

async function remove() {
  const target = (name.value || selected.value || '').trim()
  if (!target) {
    ElMessage.warning('请选择要删除的配置')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除配置 ${target}？删除后不可恢复。`,
      '提示',
      { type: 'warning' }
    )
  } catch (error) {
    return
  }
  try {
    await api.delete(
      `/api/configs/${props.kind}/${encodeURIComponent(target)}`
    )
    ElMessage.success('已删除')
    name.value = ''
    selected.value = null
    jsonText.value = ''
    hint.value = ''
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

watch(selected, (value) => loadRaw(value))
onMounted(() => {
  refresh()
})
</script>

