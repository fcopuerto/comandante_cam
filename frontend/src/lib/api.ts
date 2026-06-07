import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

const BASE_URL = '/api/v1'

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

let _getToken: (() => string | null) | null = null
let _onRefresh: (() => Promise<string>) | null = null
let _onLogout: (() => void) | null = null

export function configureApiInterceptors(opts: {
  getToken: () => string | null
  onRefresh: () => Promise<string>
  onLogout: () => void
}) {
  _getToken = opts.getToken
  _onRefresh = opts.onRefresh
  _onLogout = opts.onLogout
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = _getToken?.()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let _refreshing: Promise<string> | null = null

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    const requestId = error.response?.headers?.['x-request-id'] as string | undefined
    if (requestId && error.response?.data && typeof error.response.data === 'object') {
      (error.response.data as Record<string, unknown>).request_id = requestId
    }

    if (error.response?.status === 401 && !original._retry && _onRefresh) {
      original._retry = true
      try {
        if (!_refreshing) {
          _refreshing = _onRefresh().finally(() => { _refreshing = null })
        }
        const newToken = await _refreshing
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      } catch {
        _onLogout?.()
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  }
)

export default api
