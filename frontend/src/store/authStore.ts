import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import api, { configureApiInterceptors } from '@/lib/api'
import type { User } from '@/types'

interface LoginCredentials {
  email: string
  password: string
  mfa_code?: string
  remember_device?: boolean
}

interface AuthState {
  user: User | null
  accessToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (credentials: LoginCredentials) => Promise<void>
  logout: () => Promise<void>
  refreshToken: () => Promise<string>
  updateUser: (updates: Partial<User>) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (credentials) => {
        set({ isLoading: true })
        try {
          const { data } = await api.post<{ access_token: string; user: User }>(
            '/auth/login',
            credentials
          )
          set({
            accessToken: data.access_token,
            user: data.user,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (err) {
          set({ isLoading: false })
          throw err
        }
      },

      logout: async () => {
        try {
          await api.post('/auth/logout')
        } catch {
          // proceed regardless
        }
        set({ user: null, accessToken: null, isAuthenticated: false })
      },

      refreshToken: async () => {
        const { data } = await api.post<{ access_token: string }>('/auth/refresh')
        set({ accessToken: data.access_token, isAuthenticated: true })
        return data.access_token
      },

      updateUser: (updates) => {
        const current = get().user
        if (current) set({ user: { ...current, ...updates } })
      },
    }),
    {
      name: 'nvr-auth',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

// Wire up axios interceptors once the store is created
configureApiInterceptors({
  getToken: () => useAuthStore.getState().accessToken,
  onRefresh: () => useAuthStore.getState().refreshToken(),
  onLogout: () => useAuthStore.getState().logout(),
})
