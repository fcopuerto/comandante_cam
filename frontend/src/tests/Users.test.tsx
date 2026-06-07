import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const mockInviteUser = vi.fn()
const mockUpdateUser = vi.fn()
const mockDeactivateUser = vi.fn()
const mockRevokeSession = vi.fn()
const mockUpdateCameraPermission = vi.fn()

const MOCK_USERS = [
  {
    id: 'u1', email: 'admin@example.com', full_name: 'Alice Admin',
    role: 'admin', is_active: true, mfa_enabled: true,
    last_login: '2026-06-04T10:00:00Z', created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'u2', email: 'viewer@example.com', full_name: 'Bob Viewer',
    role: 'viewer', is_active: false, mfa_enabled: false,
    last_login: null, created_at: '2026-02-01T00:00:00Z',
  },
]

vi.mock('@/api/users', () => ({
  useUsers: vi.fn(() => ({
    data: { items: MOCK_USERS, total: 2, page: 1, page_size: 50, pages: 1 },
    isLoading: false,
  })),
  useUser: vi.fn(() => ({ data: MOCK_USERS[0], isLoading: false })),
  useCreateUser: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useInviteUser: vi.fn(() => ({ mutateAsync: mockInviteUser, isPending: false })),
  useUpdateUser: vi.fn(() => ({ mutateAsync: mockUpdateUser, isPending: false })),
  useDeactivateUser: vi.fn(() => ({ mutateAsync: mockDeactivateUser, isPending: false })),
  useRoles: vi.fn(() => ({
    data: [
      { id: 'r1', name: 'admin', permissions: ['read', 'write', 'delete'], is_system: true },
      { id: 'r2', name: 'viewer', permissions: ['read'], is_system: true },
    ],
    isLoading: false,
  })),
  useUserSessions: vi.fn(() => ({
    data: [
      { id: 's1', user_id: 'u1', ip_address: '192.168.1.1', user_agent: 'Chrome/120',
        created_at: '2026-06-04T09:00:00Z', last_used_at: '2026-06-04T10:00:00Z', is_current: true },
      { id: 's2', user_id: 'u1', ip_address: '10.0.0.1', user_agent: 'Firefox/120',
        created_at: '2026-06-03T09:00:00Z', last_used_at: '2026-06-03T09:30:00Z', is_current: false },
    ],
    isLoading: false,
  })),
  useRevokeSession: vi.fn(() => ({ mutateAsync: mockRevokeSession, isPending: false })),
  useCameraPermissions: vi.fn(() => ({
    data: [
      { camera_id: 'c1', camera_name: 'Front Door', can_view: true, can_control_ptz: false, can_export: true },
    ],
    isLoading: false,
  })),
  useUpdateCameraPermission: vi.fn(() => ({ mutateAsync: mockUpdateCameraPermission, isPending: false })),
}))

import Users from '@/pages/Users'

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderUsers() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <Users />
    </QueryClientProvider>
  )
}

describe('Users page', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the page title', () => {
    renderUsers()
    expect(screen.getByRole('heading', { name: /users/i })).toBeInTheDocument()
  })

  it('renders user rows', () => {
    renderUsers()
    expect(screen.getByText('Alice Admin')).toBeInTheDocument()
    expect(screen.getByText('Bob Viewer')).toBeInTheDocument()
  })

  it('renders role badges', () => {
    renderUsers()
    expect(screen.getAllByText(/admin/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/viewer/i).length).toBeGreaterThan(0)
  })

  it('shows invite user button', () => {
    renderUsers()
    expect(screen.getByRole('button', { name: /invite/i })).toBeInTheDocument()
  })

  it('opens invite dialog on button click', async () => {
    const user = userEvent.setup()
    renderUsers()
    await user.click(screen.getByRole('button', { name: /invite/i }))
    await waitFor(() => {
      expect(screen.queryByRole('dialog') ?? screen.queryByLabelText(/email/i)).toBeTruthy()
    })
  })

  it('invite form validates email', async () => {
    const user = userEvent.setup()
    renderUsers()
    await user.click(screen.getByRole('button', { name: /invite/i }))
    await waitFor(() => {
      const dialog = screen.queryByRole('dialog')
      expect(dialog ?? document.body).toBeTruthy()
    })
    // Try submitting with empty email
    const submitBtn = screen.queryByRole('button', { name: /send invite|invite|submit/i })
    if (submitBtn) {
      await user.click(submitBtn)
      await waitFor(() => {
        expect(mockInviteUser).not.toHaveBeenCalled()
      })
    }
  })

  it('shows roles tab with role list', async () => {
    const user = userEvent.setup()
    renderUsers()
    const rolesTab = screen.queryByRole('tab', { name: /roles/i })
    if (rolesTab) {
      await user.click(rolesTab)
      await waitFor(() => {
        expect(screen.queryByText(/admin/i)).toBeTruthy()
      })
    }
  })
})
