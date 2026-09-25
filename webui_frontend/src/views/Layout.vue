<template>
  <el-container style="height: 100%">
    <el-aside width="200px" style="background: #fff">
      <div class="brand">tg-signer</div>
      <el-menu :default-active="active" router>
        <el-menu-item index="/configs">配置管理</el-menu-item>
        <el-menu-item index="/run">统一运行</el-menu-item>
        <el-menu-item index="/accounts">账号管理</el-menu-item>
        <el-menu-item index="/chats">群组 / 频道</el-menu-item>
        <el-menu-item index="/users">用户信息</el-menu-item>
        <el-menu-item index="/records">签到记录</el-menu-item>
        <el-menu-item index="/logs">日志</el-menu-item>
        <el-menu-item index="/settings">基础设置</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span>{{ title }}</span>
        <span style="flex: 1"></span>
        <el-button text @click="doLogout">退出登录</el-button>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { logout } from '../api'

const route = useRoute()
const router = useRouter()
const titles = {
  configs: '配置管理',
  run: '统一运行',
  accounts: '账号管理',
  chats: '群组 / 频道',
  users: '用户信息',
  records: '签到记录',
  logs: '日志',
  settings: '基础设置',
}
const active = computed(() => '/' + (route.name || 'configs'))
const title = computed(() => titles[route.name] || 'tg-signer WebUI')

function doLogout() {
  logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}
</script>

<style scoped>
.brand {
  height: 56px;
  line-height: 56px;
  text-align: center;
  font-size: 18px;
  font-weight: 600;
  border-bottom: 1px solid #eee;
}
.header {
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  font-size: 16px;
  font-weight: 500;
}
</style>

