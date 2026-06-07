import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('hls.js', () => ({
  default: class MockHls {
    static isSupported = () => false
    static Events = { MANIFEST_PARSED: '', ERROR: '', BUFFER_STALLED: '', BUFFER_FLUSHED: '' }
    on = vi.fn()
    loadSource = vi.fn()
    attachMedia = vi.fn()
    destroy = vi.fn()
  },
}))

vi.mock('@/api/live', () => ({
  useStreamUrl: vi.fn(() => ({ data: { camera_id: 'c1', hls_url: '', is_active: false }, isLoading: false })),
}))

import CameraGrid from '@/components/live/CameraGrid'
import type { CameraSlot } from '@/types'

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function slots(cameraIds: (string | null)[]): CameraSlot[] {
  return cameraIds.map((cameraId, i) => ({ id: String(i), cameraId }))
}

function renderGrid(layout: 1 | 4 | 9 | 16, cells: CameraSlot[], props = {}) {
  return render(
    <QueryClientProvider client={makeQC()}>
      <CameraGrid layout={layout} cells={cells} {...props} />
    </QueryClientProvider>
  )
}

describe('CameraGrid', () => {
  it('renders 4 cells for 2×2 layout', () => {
    renderGrid(4, slots([null, null, null, null]))
    const addButtons = screen.getAllByText(/add camera/i)
    expect(addButtons).toHaveLength(4)
  })

  it('renders 1 cell for 1×1 layout', () => {
    renderGrid(1, slots([null]))
    expect(screen.getAllByText(/add camera/i)).toHaveLength(1)
  })

  it('renders 9 cells for 3×3 layout', () => {
    renderGrid(9, slots(Array(9).fill(null)))
    expect(screen.getAllByText(/add camera/i)).toHaveLength(9)
  })

  it('pads with empty cells if fewer cells than layout', () => {
    renderGrid(4, slots([null, null]))
    expect(screen.getAllByText(/add camera/i)).toHaveLength(4)
  })

  it('calls onCellClick when empty cell is clicked', async () => {
    const onCellClick = vi.fn()
    const { container } = renderGrid(4, slots([null, null, null, null]), { onCellClick })
    const cells = container.querySelectorAll('[class*="border-dashed"]')
    cells[0].dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(onCellClick).toHaveBeenCalledWith('0')
  })

  it('shows camera player (video element) when slot has cameraId', () => {
    renderGrid(4, slots(['cam-1', null, null, null]))
    expect(document.querySelector('video')).toBeInTheDocument()
  })
})
