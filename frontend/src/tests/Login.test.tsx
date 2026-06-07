import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

// Must mock stores/api before importing component
vi.mock('@/store/authStore', () => ({
  useAuthStore: vi.fn((selector) =>
    selector({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshToken: vi.fn(),
      updateUser: vi.fn(),
    })
  ),
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const original = await importOriginal<typeof import('react-router-dom')>()
  return { ...original, useNavigate: () => vi.fn() }
})

import Login from '@/pages/Login'
import { useAuthStore } from '@/store/authStore'

function renderLogin(loginFn = vi.fn()) {
  vi.mocked(useAuthStore).mockImplementation((selector: Parameters<typeof useAuthStore>[0]) =>
    selector({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isLoading: false,
      login: loginFn,
      logout: vi.fn(),
      refreshToken: vi.fn(),
      updateUser: vi.fn(),
    })
  )
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

describe('Login', () => {
  const user = userEvent.setup()

  beforeEach(() => { vi.clearAllMocks() })

  it('renders email and password fields', () => {
    renderLogin()
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('shows validation errors for empty submit', async () => {
    renderLogin()
    await user.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => {
      expect(screen.getByText(/invalid email/i)).toBeInTheDocument()
    })
  })

  it('calls login with credentials on valid submit', async () => {
    const loginFn = vi.fn().mockResolvedValue(undefined)
    renderLogin(loginFn)

    await user.type(screen.getByLabelText(/email/i), 'admin@example.com')
    await user.type(screen.getByLabelText('Password'),'secret123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(loginFn).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'admin@example.com', password: 'secret123' })
      )
    })
  })

  it('shows generic error on invalid credentials', async () => {
    const loginFn = vi.fn().mockRejectedValue({
      response: { data: { detail: 'Invalid credentials' } },
    })
    renderLogin(loginFn)

    await user.type(screen.getByLabelText(/email/i), 'admin@example.com')
    await user.type(screen.getByLabelText('Password'),'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/invalid credentials/i)
    })
  })

  it('shows MFA field after server signals requires_mfa', async () => {
    const loginFn = vi.fn().mockRejectedValue({
      response: { data: { detail: 'MFA required', requires_mfa: true } },
    })
    renderLogin(loginFn)

    await user.type(screen.getByLabelText(/email/i), 'admin@example.com')
    await user.type(screen.getByLabelText('Password'),'password')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByLabelText(/authenticator code/i)).toBeInTheDocument()
    })
  })

  it('shows lockout countdown when account is locked', async () => {
    const loginFn = vi.fn().mockRejectedValue({
      response: { data: { detail: 'Too many attempts', lockout_seconds: 900 } },
    })
    renderLogin(loginFn)

    await user.type(screen.getByLabelText(/email/i), 'admin@example.com')
    await user.type(screen.getByLabelText('Password'),'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /locked/i })).toBeDisabled()
    })
  })

  it('toggles password visibility', async () => {
    renderLogin()
    const passwordField = screen.getByLabelText('Password')
    expect(passwordField).toHaveAttribute('type', 'password')

    await user.click(screen.getByLabelText(/show password/i))
    expect(passwordField).toHaveAttribute('type', 'text')

    await user.click(screen.getByLabelText(/hide password/i))
    expect(passwordField).toHaveAttribute('type', 'password')
  })
})
