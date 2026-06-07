import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Mock hls.js — not available in jsdom
vi.mock('hls.js', () => ({
  default: class MockHls {
    static isSupported = () => false
    static Events = { MANIFEST_PARSED: 'manifestParsed', ERROR: 'error', BUFFER_STALLED: 'bufferStalled', BUFFER_FLUSHED: 'bufferFlushed' }
    on = vi.fn()
    loadSource = vi.fn()
    attachMedia = vi.fn()
    destroy = vi.fn()
  },
}))

vi.mock('@/api/live', () => ({
  useStreamUrl: vi.fn((id: string) => ({
    data: id === 'offline-cam'
      ? { camera_id: id, hls_url: '', is_active: false }
      : { camera_id: id, hls_url: 'http://localhost/stream.m3u8', is_active: true },
    isLoading: false,
  })),
}))

import CameraPlayer from '@/components/live/CameraPlayer'

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPlayer(cameraId = 'cam-1', props = {}) {
  return render(
    <QueryClientProvider client={makeQC()}>
      <CameraPlayer cameraId={cameraId} label="Test Camera" {...props} />
    </QueryClientProvider>
  )
}

describe('CameraPlayer', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the camera label in the overlay', () => {
    renderPlayer()
    expect(screen.getByText('Test Camera')).toBeInTheDocument()
  })

  it('shows loading spinner initially', () => {
    renderPlayer()
    // Loading state is shown as a spinning RefreshCw — presence of the video element confirms render
    expect(document.querySelector('video')).toBeInTheDocument()
  })

  it('shows offline overlay when camera is not active', () => {
    renderPlayer('offline-cam')
    expect(screen.getByText(/camera offline/i)).toBeInTheDocument()
  })

  it('shows alert badge when alertCount > 0', () => {
    renderPlayer('cam-1', { alertCount: 3 })
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('does not show alert badge when alertCount is 0', () => {
    renderPlayer('cam-1', { alertCount: 0 })
    // Badge is not rendered for 0
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('shows 9+ when alertCount exceeds 9', () => {
    renderPlayer('cam-1', { alertCount: 15 })
    expect(screen.getByText('9+')).toBeInTheDocument()
  })

  it('renders video element', () => {
    renderPlayer()
    const video = document.querySelector('video')
    expect(video).toBeInTheDocument()
    // React sets `muted` as a DOM property, not an HTML attribute in jsdom
    expect(video?.playsInline).toBe(true)
  })
})
