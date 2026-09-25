<template>
  <el-container style="height: 100%">
    <el-aside width="210px" class="aside">
      <div class="brand">🤖 tg-signer</div>
      <el-menu :default-active="active" router class="side-menu">
        <el-menu-item index="/configs">
          <el-icon><Setting /></el-icon><span>配置管理</span>
        </el-menu-item>
        <el-menu-item index="/run">
          <el-icon><VideoPlay /></el-icon><span>统一运行</span>
        </el-menu-item>
        <el-menu-item index="/accounts">
          <el-icon><User /></el-icon><span>账号管理</span>
        </el-menu-item>
        <el-menu-item index="/chats">
          <el-icon><ChatDotRound /></el-icon><span>群组 / 频道</span>
        </el-menu-item>
        <el-menu-item index="/users">
          <el-icon><Avatar /></el-icon><span>用户信息</span>
        </el-menu-item>
        <el-menu-item index="/records">
          <el-icon><Tickets /></el-icon><span>签到记录</span>
        </el-menu-item>
        <el-menu-item index="/logs">
          <el-icon><Document /></el-icon><span>日志</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Tools /></el-icon><span>基础设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="page-title">{{ title }}</span>
        <el-tag
          v-if="!authRequired"
          size="small"
          type="info"
          class="auth-tag"
        >未启用授权码</el-tag>
        <span style="flex: 1"></span>
        <span class="hint workdir" :title="'工作目录：' + workdir">
          工作目录：{{ workdir || '加载中…' }}
        </span>
        <el-button v-if="authRequired" text @click="doLogout">
          <el-icon style="margin-right: 4px"><SwitchButton /></el-icon>退出登录
        </el-button>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Setting,
  VideoPlay,
  User,
  ChatDotRound,
  Avatar,
  Tickets,
  Document,
  Tools,
  SwitchButton,
} from '@element-plus/icons-vue'
import { logout } from '../api'
import api from '../api'

const route = useRoute()
const router = useRouter()
const workdir = ref('')
const authRequired = ref(true)

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

async function refreshState() {
  try {
    const { data } = await api.get('/api/state')
    workdir.value = data.workdir
    authRequired.value = data.auth_required
  } catch (error) {
    /* 瞬时错误忽略 */
  }
}

function doLogout() {
  logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}

onMounted(refreshState)
// 切换页面时同步工作目录（基础设置页可能修改它）
watch(() => route.name, refreshState)
</script>

<style scoped>
.aside {
  background: #fff;
  border-right: 1px solid #e6e6e6;
}
.brand {
  height: 56px;
  line-height: 56px;
  padding: 0 16px;
  font-size: 17px;
  font-weight: 600;
  border-bottom: 1px solid #f0f0f0;
  white-space: nowrap;
}
.side-menu {
  border-right: none;
}
.header {
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  gap: 12px;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
}
.auth-tag {
  flex-shrink: 0;
}
.workdir {
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.main {
  background: #f5f7fa;
}
</style>
