<template>
  <el-tabs v-model="activeTab">
    <el-tab-pane label="Signer" name="signer">
      <div class="row" style="margin-bottom: 8px">
        <el-button type="primary" plain size="small" @click="wizardVisible = true">
          交互式配置向导
        </el-button>
        <span class="hint">通过分步表单快速创建签到配置</span>
      </div>
      <ConfigEditor kind="signer" :prefill-chat="prefillFor('signer')" @applied="clearPrefill" />
    </el-tab-pane>
    <el-tab-pane label="Automation" name="automation">
      <ConfigEditor kind="automation" :prefill-chat="prefillFor('automation')" @applied="clearPrefill" />
    </el-tab-pane>
    <el-tab-pane label="大模型" name="llm">
      <LlmConfig />
    </el-tab-pane>
  </el-tabs>

  <SignerWizard v-model:visible="wizardVisible" />
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ConfigEditor from '../components/ConfigEditor.vue'
import LlmConfig from '../components/LlmConfig.vue'
import SignerWizard from '../components/SignerWizard.vue'

const route = useRoute()
const router = useRouter()
const activeTab = ref('signer')
const wizardVisible = ref(false)

const TAB_KINDS = ['signer', 'automation', 'llm']

watch(
  () => route.query.kind,
  (kind) => {
    if (TAB_KINDS.includes(kind)) activeTab.value = kind
  },
  { immediate: true }
)

function prefillFor(kind) {
  return route.query.kind === kind ? route.query.chat || '' : ''
}

function clearPrefill() {
  if (route.query.chat) router.replace({ query: {} })
}
</script>
