import axios from 'axios'
import router from './router'

const TOKEN_KEY = 'tg_signer_auth_token'

const api = axios.create({ baseURL: '/', timeout: 90000 })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      if (router.currentRoute.value.path !== '/login') {
        router.push('/login')
      }
    }
    return Promise.reject(error)
  }
)

// 后端不可用时，静态服务器可能把 HTML 回退页当作 200 响应返回。
// 这些守卫保证接口返回异常结构时页面不会因 .filter/.map 崩溃。
export function asArray(value) {
  return Array.isArray(value) ? value : []
}

export function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

export async function checkAuth() {
  try {
    const { data } = await api.get('/api/auth/status')
    return data
  } catch (error) {
    return { required: false, locked_until: 0 }
  }
}

export async function login(code) {
  const { data } = await api.post('/api/auth/login', { code })
  if (data.ok) {
    // 授权码即令牌：后端按 Bearer 头比对环境变量中的授权码。
    localStorage.setItem(TOKEN_KEY, code)
  }
  return data
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY)
}

export function hasToken() {
  return Boolean(localStorage.getItem(TOKEN_KEY))
}

export default api
