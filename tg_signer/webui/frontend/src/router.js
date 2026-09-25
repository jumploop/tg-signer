import { createRouter, createWebHashHistory } from 'vue-router'
import { checkAuth, hasToken } from './api'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue') },
  {
    path: '/',
    component: () => import('./views/Layout.vue'),
    children: [
      { path: '', redirect: '/configs' },
      { path: 'configs', name: 'configs', component: () => import('./views/Configs.vue') },
      { path: 'run', name: 'run', component: () => import('./views/Run.vue') },
      { path: 'accounts', name: 'accounts', component: () => import('./views/Accounts.vue') },
      { path: 'users', name: 'users', component: () => import('./views/Users.vue') },
      { path: 'records', name: 'records', component: () => import('./views/Records.vue') },
      { path: 'logs', name: 'logs', component: () => import('./views/Logs.vue') },
      { path: 'chats', name: 'chats', component: () => import('./views/Chats.vue') },
      { path: 'settings', name: 'settings', component: () => import('./views/Settings.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (to.name === 'login') return true
  const status = await checkAuth()
  if (status.required && !hasToken()) {
    return { name: 'login' }
  }
  return true
})

export default router

