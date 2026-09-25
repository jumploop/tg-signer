<template>
  <el-container class="shell">
    <el-aside
      id="app-navigation"
      width="232px"
      class="aside"
      :class="{ 'is-open': mobileNavOpen }"
      aria-label="主导航"
    >
      <div class="brand">
        <el-icon class="brand-icon"><Promotion /></el-icon>
        <span class="brand-name">tg-signer</span>
        <el-button
          class="aside-close"
          text
          aria-label="关闭导航"
          @click="mobileNavOpen = false"
        >
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
      <p class="brand-sub">Telegram 自动化工作台</p>
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
    <button
      v-if="mobileNavOpen"
      class="nav-overlay"
      aria-label="关闭导航"
      @click="mobileNavOpen = false"
    />
    <el-container class="main-col">
      <el-header class="header" height="72px">
        <el-button
          class="mobile-menu-btn"
          text
          aria-label="打开导航"
          :aria-expanded="mobileNavOpen"
          aria-controls="app-navigation"
          @click="mobileNavOpen = true"
        >
          <el-icon><Menu /></el-icon>
        </el-button>
        <span class="header-context">Workspace <span>/</span> {{ title }}</span>
        <span style="flex: 1"></span>
        <span class="workdir" :title="'工作目录：' + workdir">
          <el-icon class="wd-icon"><Folder /></el-icon>
          <span class="wd-text">{{ workdir || '加载中…' }}</span>
        </span>
      </el-header>
      <el-main class="main">
        <section class="page-intro" aria-labelledby="page-heading">
          <div>
            <span class="page-kicker">CONTROL CENTER</span>
            <h1 id="page-heading">{{ title }}</h1>
            <p>{{ description }}</p>
          </div>
          <div class="workspace-status" aria-live="polite">
            <span class="status-dot" :class="{ 'is-loading': !workdir }" />
            <span>{{ workdir ? '工作区就绪' : '正在连接工作区' }}</span>
          </div>
        </section>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
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
  Menu,
  Close,
} from '@element-plus/icons-vue'
import { logout } from '../api'
import api from '../api'

const route = useRoute()
const router = useRouter()
const workdir = ref('')
const authRequired = ref(true)
const mobileNavOpen = ref(false)

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
const description = computed(() => {
  const descriptions = {
    configs: '集中管理签到、自动化与模型配置，让每次变更都清晰可追溯。',
    run: '启动、停止并实时观察任务运行状态。',
    accounts: '管理 Telegram 登录会话与授权状态。',
    chats: '发现群组与频道，并将目标快速带入配置流程。',
    users: '查看已缓存的账户信息与最近对话。',
    records: '浏览签到历史，快速确认任务执行结果。',
    logs: '检索运行日志，快速定位异常与执行轨迹。',
    settings: '管理工作目录与 WebUI 的基础运行参数。',
  }
  return descriptions[route.name] || 'Telegram 自动化控制台'
})

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

function handleKeydown(event) {
  if (event.key === 'Escape' && mobileNavOpen.value) {
    mobileNavOpen.value = false
  }
}

onMounted(() => {
  refreshState()
  window.addEventListener('keydown', handleKeydown)
})
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
// 切换页面时同步工作目录（基础设置页可能修改它）
watch(
  () => route.name,
  () => {
    mobileNavOpen.value = false
    refreshState()
  }
)
</script>

<style scoped>
.shell {
  height: 100%;
  min-width: 0;
}
.aside {
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 20;
  background: var(--ts-navy);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 10px 0 30px rgba(13, 27, 42, 0.08);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 72px;
  padding: 0 18px;
  color: #ffffff;
}
.brand-icon {
  font-size: 22px;
  color: #7FC7EE;
}
.brand-name {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.2px;
}
.brand-sub {
  margin: -2px 18px 18px;
  font-size: 11px;
  letter-spacing: 0.4px;
  color: rgba(255, 255, 255, 0.5);
}
.side-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  padding: 4px 12px;
}
.side-menu :deep(.el-menu-item) {
  height: 44px;
  line-height: 44px;
  margin-bottom: 4px;
  border-radius: 10px;
  color: rgba(255, 255, 255, 0.7);
}
.side-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.08);
  color: #ffffff;
}
.side-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(37, 105, 208, 0.28), rgba(37, 105, 208, 0.12));
  color: #ffffff;
  font-weight: 600;
  box-shadow: inset 3px 0 0 #6DA6FA;
}
.side-menu :deep(.el-menu-item .el-icon) {
  color: inherit;
}
.aside-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.aside-close,
.mobile-menu-btn {
  display: none;
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
  gap: 14px;
  padding: 0 28px;
  box-shadow: 0 1px 0 rgba(15, 31, 51, 0.02);
}
.header-context {
  font-size: 13px;
  font-weight: 600;
  color: var(--ts-ink-2);
}
.header-context span {
  margin: 0 5px;
  color: var(--ts-faint);
}
.auth-tag {
  flex-shrink: 0;
}
.workdir {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 420px;
  padding: 6px 11px;
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
  padding: 30px 32px 44px;
  overflow: auto;
}
.page-intro {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  max-width: 1280px;
  margin: 0 auto 24px;
}
.page-kicker {
  display: block;
  margin-bottom: 7px;
  color: var(--ts-sky);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 1.5px;
}
.page-intro h1 {
  margin: 0;
  color: var(--ts-ink);
  font-size: clamp(24px, 3vw, 32px);
  font-weight: 750;
  letter-spacing: -0.8px;
  line-height: 1.15;
}
.page-intro p {
  max-width: 620px;
  margin: 9px 0 0;
  color: var(--ts-muted);
  font-size: 14px;
  line-height: 1.6;
}
.workspace-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 8px 12px;
  border: 1px solid var(--ts-line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: var(--ts-muted);
  font-size: 12px;
  box-shadow: 0 2px 8px rgba(15, 31, 51, 0.03);
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ts-mint);
  box-shadow: 0 0 0 4px rgba(15, 159, 120, 0.12);
}
.status-dot.is-loading {
  background: var(--el-color-warning);
  box-shadow: 0 0 0 4px rgba(230, 162, 60, 0.14);
}
.nav-overlay {
  display: none;
}

@media (max-width: 900px) {
  .aside {
    position: fixed;
    inset: 0 auto 0 0;
    width: 232px;
    transform: translateX(-100%);
    transition: transform 220ms ease;
  }
  .aside.is-open {
    transform: translateX(0);
  }
  .aside-close,
  .mobile-menu-btn {
    display: inline-flex;
  }
  .aside-close {
    margin-left: auto;
    color: rgba(255, 255, 255, 0.7);
  }
  .mobile-menu-btn {
    color: var(--ts-ink-2);
  }
  .nav-overlay {
    position: fixed;
    inset: 0;
    z-index: 15;
    display: block;
    border: 0;
    background: rgba(13, 27, 42, 0.38);
    backdrop-filter: blur(2px);
  }
  .header {
    padding: 0 20px;
  }
  .main {
    padding: 26px 20px 36px;
  }
}

@media (max-width: 600px) {
  .header-context {
    display: none;
  }
  .workdir {
    max-width: 190px;
  }
  .page-intro {
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
    margin-bottom: 20px;
  }
  .page-intro p {
    font-size: 13px;
  }
}
</style>
