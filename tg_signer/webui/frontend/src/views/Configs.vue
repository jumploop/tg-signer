<template>
  <el-tabs v-model="activeTab">
    <el-tab-pane label="Signer" name="signer">
      <ConfigEditor kind="signer" />
    </el-tab-pane>
    <el-tab-pane label="Monitor" name="monitor">
      <ConfigEditor kind="monitor" />
    </el-tab-pane>
    <el-tab-pane label="大模型" name="llm">
      <LlmConfig />
    </el-tab-pane>
  </el-tabs>
</template>

<script setup>
import { ref } from 'vue'
import ConfigEditor from '../components/ConfigEditor.vue'
import LlmConfig from '../components/LlmConfig.vue'

const activeTab = ref('signer')
</script>

