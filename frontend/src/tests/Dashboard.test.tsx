import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const mockHealth = {
  database: true, redis: true, celery: true, detection: true,
  storage_warning: false, storage_critical: false,
}

const mockStorage = {
  total_bytes: 2e12, used_bytes: 1e12, free_bytes: 1e12, usage_percent: 50,
  per_camera: [],
}

const mockCameras = {
  items: [
    { id: '1', name: 'Cam 1', status: 'online', recording_mode: 'continuous', location: 'Entry' },
    { id: '2', name: 'Cam 2', status: 'offline', recording_mode: 'disabled', location: 'Exit' },
  ],
  total: 2, page: 1, page_size: 100, pages: 1,
}

const mockAlerts = { items: [], total: 0, page: 1, page_size: 10, pages: 0 }

const mockAlertStats = {
  total: 3, unacknowledged: 1,
  by_severity: { critical: 1, high: 1, medium: 1, low: 0 },
  by_camera: {}, by_rule: {}, by_hour: [],
}

vi.mock('@/api/system', () => ({
  useSystemHealth: vi.fn(() => ({ data: mockHealth, isLoading: false, isError: false })),
  useStorageStatus: vi.fn(() => ({ data: mockStorage, isLoading: false, isError: false })),
  useSystemEvents: vi.fn(() => ({ data: { items: [], total: 0 }, isLoading: false })),
}))

vi.mock('@/api/cameras', () => ({
  useCameras: vi.fn(() => ({ data: mockCameras, isLoading: false, isError: false })),
}))

vi.mock('@/api/alerts', () => ({
  useAlerts: vi.fn(() => ({ data: mockAlerts, isLoading: false, isError: false })),
  useAlertStats: vi.fn(() => ({ data: mockAlertStats, isLoading: false, isError: false })),
}))

vi.mock('@/store/wsStore', () => ({
  useWsStore: vi.fn((selector) =>
    selector({ status: 'connected', connect: vi.fn(), disconnect: vi.fn(), subscribe: vi.fn(() => vi.fn()) })
  ),
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const original = await importOriginal<typeof import('react-router-dom')>()
  return { ...original, useNavigate: () => vi.fn() }
})

import Dashboard from '@/pages/Dashboard'
import { useSystemHealth, useStorageStatus } from '@/api/system'
import { useCameras } from '@/api/cameras'

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderDashboard() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('Dashboard', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders all main widgets', () => {
    renderDashboard()
    expect(screen.getByText(/system health/i)).toBeInTheDocument()
    expect(screen.getByText(/storage/i)).toBeInTheDocument()
    expect(screen.getByText(/cameras/i)).toBeInTheDocument()
    expect(screen.getByText(/alert summary/i)).toBeInTheDocument()
    expect(screen.getByText(/recent alerts/i)).toBeInTheDocument()
    expect(screen.getByText(/recording coverage/i)).toBeInTheDocument()
  })

  it('shows service health indicators', () => {
    renderDashboard()
    expect(screen.getByText('Database')).toBeInTheDocument()
    expect(screen.getByText('Redis')).toBeInTheDocument()
    expect(screen.getByText('Celery workers')).toBeInTheDocument()
    expect(screen.getByText('Detection')).toBeInTheDocument()
  })

  it('shows camera counts', () => {
    renderDashboard()
    // 1 online, 1 offline — both appear
    expect(screen.getByText('Online')).toBeInTheDocument()
    expect(screen.getByText('Offline')).toBeInTheDocument()
  })

  it('shows severity badges in alert summary', () => {
    renderDashboard()
    expect(screen.getByText(/critical/i)).toBeInTheDocument()
    expect(screen.getByText(/high/i)).toBeInTheDocument()
  })

  it('shows loading skeletons when data is loading', () => {
    vi.mocked(useSystemHealth).mockReturnValue({ data: undefined, isLoading: true } as ReturnType<typeof useSystemHealth>)
    vi.mocked(useStorageStatus).mockReturnValue({ data: undefined, isLoading: true } as ReturnType<typeof useStorageStatus>)
    vi.mocked(useCameras).mockReturnValue({ data: undefined, isLoading: true } as ReturnType<typeof useCameras>)
    renderDashboard()
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows no alerts message when alert feed is empty', () => {
    renderDashboard()
    expect(screen.getByText(/no unacknowledged alerts/i)).toBeInTheDocument()
  })

  it('shows storage critical warning when health reports critical', () => {
    vi.mocked(useSystemHealth).mockReturnValue({
      data: { ...mockHealth, storage_critical: true },
      isLoading: false,
    } as ReturnType<typeof useSystemHealth>)
    renderDashboard()
    expect(screen.getByText(/storage critical/i)).toBeInTheDocument()
  })
})
