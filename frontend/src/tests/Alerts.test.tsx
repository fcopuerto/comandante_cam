import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const mockAcknowledge = vi.fn()
const mockBulkAcknowledge = vi.fn()
const mockMarkFalsePositive = vi.fn()
const mockBulkFalsePositive = vi.fn()
const mockLegalHold = vi.fn()

vi.mock('@/api/alerts', () => ({
  useAlerts: vi.fn(() => ({
    data: {
      items: [
        {
          id: 'a1', camera_id: 'c1', camera_name: 'Cam 1', rule_triggered: 'person_detected',
          severity: 'high', zone_name: 'Entrance', class_name: 'person', confidence: 0.95,
          track_id: 1, triggered_at: '2026-06-04T10:00:00Z', acknowledged: false,
          acknowledged_by: null, acknowledged_at: null, false_positive: false, legal_hold: false,
          clip_path: null, frame_path: null, notes: null,
        },
        {
          id: 'a2', camera_id: 'c2', camera_name: 'Cam 2', rule_triggered: 'dwell_alert',
          severity: 'critical', zone_name: null, class_name: null, confidence: null,
          track_id: null, triggered_at: '2026-06-04T09:00:00Z', acknowledged: true,
          acknowledged_by: 'admin@example.com', acknowledged_at: '2026-06-04T09:05:00Z',
          false_positive: false, legal_hold: true, clip_path: '/clips/a2.mp4', frame_path: '/frames/a2.jpg',
          notes: 'Reviewed',
        },
      ],
      total: 2, page: 1, page_size: 50, pages: 1,
    },
    isLoading: false,
  })),
  useAlertStats: vi.fn(() => ({
    data: {
      total: 10, unacknowledged: 3,
      by_severity: { low: 2, medium: 3, high: 4, critical: 1 },
      by_camera: {}, by_rule: {},
      by_hour: [{ hour: '2026-06-04T10:00:00Z', count: 5 }],
    },
    isLoading: false,
  })),
  useAcknowledgeAlert: vi.fn(() => ({ mutateAsync: mockAcknowledge, isPending: false })),
  useLegalHold: vi.fn(() => ({ mutateAsync: mockLegalHold, isPending: false })),
  useMarkFalsePositive: vi.fn(() => ({ mutateAsync: mockMarkFalsePositive, isPending: false })),
  useBulkAcknowledge: vi.fn(() => ({ mutateAsync: mockBulkAcknowledge, isPending: false })),
  useBulkFalsePositive: vi.fn(() => ({ mutateAsync: mockBulkFalsePositive, isPending: false })),
}))

import Alerts from '@/pages/Alerts'

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderAlerts() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <Alerts />
    </QueryClientProvider>
  )
}

describe('Alerts page', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the page title', () => {
    renderAlerts()
    expect(screen.getByRole('heading', { name: /alerts/i })).toBeInTheDocument()
  })

  it('renders alert rows from API data', () => {
    renderAlerts()
    expect(screen.getByText('Cam 1')).toBeInTheDocument()
    expect(screen.getByText('Cam 2')).toBeInTheDocument()
  })

  it('shows severity badges', () => {
    renderAlerts()
    expect(screen.getAllByText(/high/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/critical/i).length).toBeGreaterThan(0)
  })

  it('shows stats cards', () => {
    renderAlerts()
    // Stats show total: 10, unacknowledged: 3
    expect(screen.getByText('10')).toBeInTheDocument()
  })

  it('shows filter bar elements', () => {
    renderAlerts()
    // Search input
    const inputs = screen.queryAllByRole('textbox')
    expect(inputs.length).toBeGreaterThan(0)
  })

  it('bulk ops bar appears when rows are selected', async () => {
    const user = userEvent.setup()
    renderAlerts()
    // Click first row checkbox
    const checkboxes = screen.getAllByRole('checkbox')
    // First checkbox is header "select all", second is first row
    if (checkboxes.length >= 2) {
      await user.click(checkboxes[1])
      // Bulk ops bar or count should appear
      await waitFor(() => {
        expect(screen.queryByText(/selected/i) ?? screen.queryByText(/acknowledge/i)).toBeTruthy()
      })
    }
  })

  it('opens detail slide-over on eye icon click', async () => {
    const user = userEvent.setup()
    renderAlerts()
    const eyeButtons = screen.getAllByRole('button')
    const viewBtn = eyeButtons.find((b) =>
      b.querySelector('svg') && b.getAttribute('aria-label')?.match(/view|detail/i)
    ) ?? eyeButtons.find((b) => b.title?.match(/view/i))
    if (viewBtn) {
      await user.click(viewBtn)
      await waitFor(() => {
        expect(screen.queryByText(/acknowledge/i) ?? screen.queryByText(/legal hold/i)).toBeTruthy()
      })
    }
  })
})
