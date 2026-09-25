<template>
  <el-container class="shell">
    <el-aside width="216px" class="aside">
      <div class="brand">
        <el-icon class="brand-icon"><Promotion /></el-icon>
        <span class="brand-name">tg-signer</span>
      </div>
      <p class="brand-sub">Telegram 自动化控制台</p>
      <el-menu :default-active="active" router class="side-menu">
        <el-menu-item index="/configs">
          <el-icon><Setting /></el-icon><span>配置管理</span>
        </el-menu-item>
        <el-menu-item index="/run">
          <el-icon><VideoPlay /></el-icon><span>任务运行</span>
        </el-menu-item>
        <el-menu-item index="/accounts">
          <el-icon><User /></el-icon><span>账号</span>
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
          <el-icon><Document /></el-icon><span>运行日志</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Tools /></el-icon><span>基础设置</span>
        </el-menu-item>
      </el-menu>
      <div class="aside-foot">
        <el-tag v-if="!authRequired" size="small" effect="plain" class="auth-tag">未启用授权码</el-tag>
        <el-button v-if="authRequired" text class="logout-btn" @click="doLogout">
          <el-icon style="margin-right: 4px"><SwitchButton /></el-icon>退出登录
        </el-button>
      </div>
    </el-aside>
    <el-container class="main-col">
      <el-header class="header" height="56px">
        <span class="page-title">{{ title }}</span>
        <span style="flex: 1"></span>
        <span class="workdir" :title="'工作目录：' + workdir">
          <el-icon class="wd-icon"><Folder /></el-icon>
          <span class="wd-text">{{ workdir || '加载中…' }}</span>
        </span>
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
  Folder,
  Promotion,
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
  run: '任务运行',
  accounts: '账号',
  chats: '群组 / 频道',
  users: '用户信息',
  records: '签到记录',
  logs: '运行日志',
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
.shell {
  height: 100%;
}
.aside {
  display: flex;
  flex-direction: column;
  background: var(--ts-navy);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 16px;
  color: #ffffff;
}
.brand-icon {
  font-size: 22px;
  color: #7FC7EE;
}
.brand-name {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.2px;
}
.brand-sub {
  margin: -2px 16px 10px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
}
.side-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  padding: 4px 8px;
}
.side-menu :deep(.el-menu-item) {
  height: 42px;
  line-height: 42px;
  margin-bottom: 2px;
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.68);
}
.side-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.06);
  color: #ffffff;
}
.side-menu :deep(.el-menu-item.is-active) {
  background: rgba(42, 159, 216, 0.22);
  color: #ffffff;
  font-weight: 600;
  box-shadow: inset 3px 0 0 var(--ts-sky);
}
.side-menu :deep(.el-menu-item .el-icon) {
  color: inherit;
}
.aside-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.logout-btn {
  color: rgba(255, 255, 255, 0.68);
}
.logout-btn:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.08);
}
.main-col {
  min-width: 0;
}
.header {
  display: flex;
  align-items: center;
  background: var(--ts-card);
  border-bottom: 1px solid var(--ts-line);
  gap: 12px;
  padding: 0 20px;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ts-ink);
}
.auth-tag {
  flex-shrink: 0;
}
.workdir {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 420px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--ts-surface);
  border: 1px solid var(--ts-line);
  color: var(--ts-muted);
  font-size: 12px;
}
.wd-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wd-icon {
  color: var(--ts-muted);
}
.main {
  background: var(--ts-surface);
  padding: 20px;
}
</style>
