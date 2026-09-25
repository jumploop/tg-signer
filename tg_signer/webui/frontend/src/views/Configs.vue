<template>
  <el-tabs v-model="activeTab">
    <el-tab-pane label="Signer" name="signer">
      <div class="row" style="margin-bottom: 8px">
        <el-button type="primary" plain size="small" @click="wizardVisible = true">
          交互式配置向导
        </el-button>
        <span class="hint">通过分步表单快速创建签到配置</span>
      </div>
      <ConfigEditor kind="signer" />
    </el-tab-pane>
    <el-tab-pane label="Monitor" name="monitor">
      <ConfigEditor kind="monitor" />
    </el-tab-pane>
    <el-tab-pane label="大模型" name="llm">
      <LlmConfig />
    </el-tab-pane>
  </el-tabs>

  <SignerWizard v-model:visible="wizardVisible" />
</template>

<script setup>
import { ref } from 'vue'
import ConfigEditor from '../components/ConfigEditor.vue'
import LlmConfig from '../components/LlmConfig.vue'
import SignerWizard from '../components/SignerWizard.vue'

const activeTab = ref('signer')
const wizardVisible = ref(false)
</script>
