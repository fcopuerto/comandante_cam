import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff, Lock, Mail, Shield } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useAuthStore } from '@/store/authStore'
import type { AxiosError } from 'axios'

const DEV_USER = {
  id: 'dev-1', email: 'admin@nvr.local', full_name: 'Admin User',
  role: 'admin', is_active: true, mfa_enabled: false, last_login: null, created_at: '',
}

const schema = z.object({
  email: z.string().email('Invalid email'),
  password: z.string().min(1, 'Password is required'),
  mfa_code: z.string().optional(),
  remember_device: z.boolean().optional(),
})
type FormData = z.infer<typeof schema>

interface LoginError {
  detail: string
  lockout_seconds?: number
  requires_mfa?: boolean
}

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((s) => s.login)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  const [showPassword, setShowPassword] = useState(false)
  const [requiresMfa, setRequiresMfa] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lockoutUntil, setLockoutUntil] = useState<number | null>(null)
  const [countdown, setCountdown] = useState(0)

  const updateUser = useAuthStore((s) => s.updateUser)

  const from = (location.state as { from?: string })?.from ?? '/'

  const demoLogin = () => {
    updateUser(DEV_USER)
    useAuthStore.setState({ user: DEV_USER, accessToken: 'dev-token', isAuthenticated: true })
    navigate(from, { replace: true })
  }

  useEffect(() => {
    if (isAuthenticated) navigate(from, { replace: true })
  }, [isAuthenticated, navigate, from])

  useEffect(() => {
    if (!lockoutUntil) return
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((lockoutUntil - Date.now()) / 1000))
      setCountdown(remaining)
      if (remaining === 0) setLockoutUntil(null)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [lockoutUntil])

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const onSubmit = async (data: FormData) => {
    setError(null)
    try {
      await login(data)
      navigate(from, { replace: true })
    } catch (err) {
      const axiosErr = err as AxiosError<LoginError>
      const detail = axiosErr.response?.data?.detail ?? 'Invalid credentials'
      const lockoutSecs = axiosErr.response?.data?.lockout_seconds
      const mfaRequired = axiosErr.response?.data?.requires_mfa

      if (lockoutSecs) {
        setLockoutUntil(Date.now() + lockoutSecs * 1000)
        setError(`Account temporarily locked. Try again in ${lockoutSecs}s.`)
      } else if (mfaRequired) {
        setRequiresMfa(true)
        setError(null)
      } else {
        setError(detail)
      }
    }
  }

  const isLocked = lockoutUntil !== null && countdown > 0

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="flex flex-col items-center space-y-2">
          <div className="rounded-full bg-primary p-3">
            <Shield className="h-8 w-8 text-primary-foreground" />
          </div>
          <h1 className="text-2xl font-bold">NVR Pro</h1>
          <p className="text-sm text-muted-foreground">Enterprise Video Surveillance</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Sign in</CardTitle>
            <CardDescription>Enter your credentials to access the system</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
              {error && (
                <Alert variant="destructive" role="alert" aria-live="assertive">
                  <AlertDescription>
                    {error}
                    {isLocked && ` Try again in ${countdown}s.`}
                  </AlertDescription>
                </Alert>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    className="pl-9"
                    aria-describedby={errors.email ? 'email-error' : undefined}
                    {...register('email')}
                  />
                </div>
                {errors.email && (
                  <p id="email-error" className="text-sm text-destructive">{errors.email.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    className="pl-9 pr-10"
                    aria-describedby={errors.password ? 'password-error' : undefined}
                    {...register('password')}
                  />
                  <button
                    type="button"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    onClick={() => setShowPassword((v) => !v)}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {errors.password && (
                  <p id="password-error" className="text-sm text-destructive">{errors.password.message}</p>
                )}
              </div>

              {requiresMfa && (
                <div className="space-y-2">
                  <Label htmlFor="mfa_code">Authenticator code</Label>
                  <Input
                    id="mfa_code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    placeholder="000000"
                    autoFocus
                    aria-label="MFA code"
                    {...register('mfa_code')}
                  />
                </div>
              )}

              <div className="flex items-center space-x-2">
                <input
                  id="remember_device"
                  type="checkbox"
                  className="h-4 w-4 rounded border-input"
                  {...register('remember_device')}
                />
                <Label htmlFor="remember_device" className="font-normal cursor-pointer">
                  Remember this device
                </Label>
              </div>

              <Button
                type="submit"
                className="w-full"
                disabled={isSubmitting || isLocked}
                aria-busy={isSubmitting}
              >
                {isSubmitting ? 'Signing in…' : isLocked ? `Locked (${countdown}s)` : 'Sign in'}
              </Button>

              {import.meta.env.DEV && (
                <Button type="button" variant="outline" className="w-full" onClick={demoLogin}>
                  Demo login (dev only)
                </Button>
              )}
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
