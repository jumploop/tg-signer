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
