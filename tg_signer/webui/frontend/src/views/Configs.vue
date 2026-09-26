<template>
  <div class="configs-shell">
    <div class="configs-intro">
      <div>
        <span class="section-label">配置中心</span>
        <p class="section-caption">选择配置类型，开始编辑 JSON、运行模板或维护模型连接。</p>
      </div>
      <el-tag type="info" effect="light" round>JSON 配置</el-tag>
    </div>
    <el-tabs v-model="activeTab" class="config-tabs">
    <el-tab-pane label="Signer" name="signer">
      <div class="config-tab-intro">
        <el-button type="primary" plain size="small" @click="wizardVisible = true">
          交互式配置向导
        </el-button>
        <span class="hint">通过分步表单快速创建签到配置</span>
      </div>
      <ConfigEditor
        kind="signer"
        :prefill-chat="prefillChat('signer')"
        :prefill-title="prefillTitle"
        :prefill-username="prefillUsername"
        @applied="clearPrefill"
      />
    </el-tab-pane>
    <el-tab-pane label="Automation" name="automation">
      <ConfigEditor
        kind="automation"
        :prefill-chat="prefillChat('automation')"
        :prefill-title="prefillTitle"
        :prefill-username="prefillUsername"
        @applied="clearPrefill"
      />
    </el-tab-pane>
    <el-tab-pane label="大模型" name="llm">
      <LlmConfig />
    </el-tab-pane>
    </el-tabs>
  </div>

  <SignerWizard v-model:visible="wizardVisible" />
</template>

<script setup>
import { ref, computed, watch } from 'vue'
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

const prefillTitle = computed(() => route.query.title || '')
const prefillUsername = computed(() => route.query.username || '')

function prefillChat(kind) {
  return route.query.kind === kind ? route.query.chat || '' : ''
}

function clearPrefill() {
  if (route.query.chat) router.replace({ query: {} })
}
</script>

<style scoped>
.configs-intro {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 20px;
}
.section-label {
  display: block;
  margin-bottom: 5px;
  color: var(--ts-ink);
  font-size: 16px;
  font-weight: 700;
}
.section-caption {
  margin: 0;
  color: var(--ts-muted);
  font-size: 13px;
}
.config-tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}
.config-tab-intro {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

@media (max-width: 600px) {
  .configs-intro {
    align-items: flex-start;
    flex-direction: column;
  }

  .config-tab-intro {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
