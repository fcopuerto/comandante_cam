import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/store/authStore', () => ({
  useAuthStore: vi.fn((selector) =>
    selector({
      user: { id: '1', email: 'admin@nvr.local', full_name: 'Admin User', role: 'admin', is_active: true, mfa_enabled: false, last_login: null, created_at: '' },
      accessToken: 'tok',
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshToken: vi.fn(),
      updateUser: vi.fn(),
    })
  ),
}))

vi.mock('@/store/wsStore', () => ({
  useWsStore: vi.fn((selector) => {
    const store = { status: 'connected', connect: vi.fn(), disconnect: vi.fn(), subscribe: vi.fn(() => vi.fn()) }
    return typeof selector === 'function' ? selector(store) : store
  }),
}))

vi.mock('@/api/alerts', () => ({
  useAlerts: vi.fn(() => ({ data: { items: [], total: 0 }, isLoading: false })),
}))

vi.mock('@/api/system', () => ({
  useSystemEvents: vi.fn(() => ({ data: { items: [], total: 0 }, isLoading: false })),
  useSystemHealth: vi.fn(() => ({
    data: { database: true, redis: true, celery: true, detection: true, storage_warning: false, storage_critical: false },
    isLoading: false,
  })),
  useStorageStatus: vi.fn(() => ({ data: null, isLoading: false })),
}))

import Layout from '@/components/shared/Layout'
import { useAuthStore } from '@/store/authStore'
import { useWsStore } from '@/store/wsStore'

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderLayout(userOverrides = {}) {
  const baseUser = {
    id: '1', email: 'admin@nvr.local', full_name: 'Admin User',
    role: 'admin', is_active: true, mfa_enabled: false, last_login: null, created_at: '',
    ...userOverrides,
  }
  vi.mocked(useAuthStore).mockImplementation((selector: Parameters<typeof useAuthStore>[0]) =>
    selector({
      user: baseUser,
      accessToken: 'tok',
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshToken: vi.fn(),
      updateUser: vi.fn(),
    })
  )
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter initialEntries={['/']}>
        <Layout />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('Layout', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders main navigation links', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /live view/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /recordings/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /alerts/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /cameras/i })).toBeInTheDocument()
  })

  it('shows Users link for admin', () => {
    renderLayout({ role: 'admin' })
    expect(screen.getByRole('link', { name: /users/i })).toBeInTheDocument()
  })

  it('hides Users link for non-admin', () => {
    renderLayout({ role: 'operator' })
    expect(screen.queryByRole('link', { name: /users/i })).not.toBeInTheDocument()
  })

  it('shows connected WS indicator when status is connected', () => {
    vi.mocked(useWsStore).mockImplementation((selector) => {
      const store = { status: 'connected' as const, connect: vi.fn(), disconnect: vi.fn(), subscribe: vi.fn(() => vi.fn()) }
      return typeof selector === 'function' ? selector(store) : store
    })
    renderLayout()
    expect(screen.getByText(/connected/i)).toBeInTheDocument()
  })

  it('shows reconnecting indicator when status is reconnecting', () => {
    vi.mocked(useWsStore).mockImplementation((selector) => {
      const store = { status: 'reconnecting' as const, connect: vi.fn(), disconnect: vi.fn(), subscribe: vi.fn(() => vi.fn()) }
      return typeof selector === 'function' ? selector(store) : store
    })
    renderLayout()
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument()
  })

  it('shows user name in top bar', () => {
    renderLayout({ full_name: 'Jane Smith' })
    expect(screen.getByText('Jane Smith')).toBeInTheDocument()
  })
})
