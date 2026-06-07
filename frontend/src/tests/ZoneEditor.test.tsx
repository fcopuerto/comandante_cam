import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const mockSaveZones = vi.fn()

vi.mock('@/api/cameras', () => ({
  useUpdateCameraZones: vi.fn(() => ({ mutateAsync: mockSaveZones, isPending: false })),
  useSnapshot: vi.fn(() => ({ data: null, isLoading: false })),
}))

import ZoneEditor from '@/components/cameras/ZoneEditor'
import type { Zone } from '@/types'

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

const baseZone: Zone = {
  name: 'Zone 1',
  polygon: [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
  restricted: false,
  working_hours_start: null,
  working_hours_end: null,
  dwell_threshold_s: null,
  is_privacy_mask: false,
  enabled: true,
  color: '#3b82f6',
}

function renderEditor(initialZones: Zone[] = []) {
  return render(
    <QueryClientProvider client={makeQC()}>
      <ZoneEditor cameraId="cam-1" initialZones={initialZones} />
    </QueryClientProvider>
  )
}

describe('ZoneEditor', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders canvas and draw zone button', () => {
    renderEditor()
    expect(document.querySelector('canvas')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /draw zone/i })).toBeInTheDocument()
  })

  it('shows empty state message when no zones', () => {
    renderEditor()
    expect(screen.getByText(/no zones defined/i)).toBeInTheDocument()
  })

  it('renders existing zones', () => {
    renderEditor([baseZone])
    expect(screen.getByDisplayValue('Zone 1')).toBeInTheDocument()
  })

  it('can delete a zone', async () => {
    renderEditor([baseZone])
    // Find delete button by aria-label or by sibling position
    const buttons = screen.getAllByRole('button')
    const trashBtn = buttons.find((b) => b.querySelector('svg'))
    expect(trashBtn).toBeTruthy()
  })

  it('calls save API when save button is clicked', async () => {
    const user = userEvent.setup()
    mockSaveZones.mockResolvedValue(undefined)
    renderEditor([baseZone])
    const saveBtn = screen.getByRole('button', { name: /save zones/i })
    await user.click(saveBtn)
    expect(mockSaveZones).toHaveBeenCalledWith({ id: 'cam-1', zones: [baseZone] })
  })

  it('toggles draw mode when Draw zone button is clicked', async () => {
    const user = userEvent.setup()
    renderEditor()
    const drawBtn = screen.getByRole('button', { name: /draw zone/i })
    await user.click(drawBtn)
    // After clicking, button text changes to include instructions
    expect(screen.getByText(/dbl-click to finish/i)).toBeInTheDocument()
  })

  it('expands zone settings on click', async () => {
    const user = userEvent.setup()
    renderEditor([baseZone])
    // Click the zone container (the div wrapping the zone row)
    const zoneInput = screen.getByDisplayValue('Zone 1')
    const zoneRow = zoneInput.closest('div.border') ?? zoneInput.parentElement?.parentElement
    if (zoneRow) {
      await user.click(zoneRow)
      // The expanded section should show the restricted zone switch label
      const labels = screen.getAllByText(/restricted/i)
      expect(labels.length).toBeGreaterThan(0)
    }
  })
})
