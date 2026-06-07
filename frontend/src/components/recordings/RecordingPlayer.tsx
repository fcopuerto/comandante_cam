import { useRef, useState, useEffect, useCallback } from 'react'
import { Play, Pause, Maximize2, Minimize2, Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { AlertEvent } from '@/types'

interface RecordingPlayerProps {
  src: string | null
  alerts?: AlertEvent[]
  videoStartTime?: number
  onAddToExport?: (range: { start: number; end: number }) => void
  className?: string
}

const SPEEDS = [0.5, 1, 2, 4, 8] as const

function formatMMSS(seconds: number): string {
  const s = Math.floor(seconds)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export default function RecordingPlayer({
  src,
  alerts = [],
  videoStartTime = 0,
  onAddToExport,
  className,
}: RecordingPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const rafRef = useRef<number | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const syncTime = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    setCurrentTime(video.currentTime)
    if (!video.paused) {
      rafRef.current = requestAnimationFrame(syncTime)
    }
  }, [])

  const startRaf = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(syncTime)
  }, [syncTime])

  const stopRaf = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => stopRaf()
  }, [stopRaf])

  const handlePlay = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      video.play().catch(() => {})
    } else {
      video.pause()
    }
  }, [])

  const advanceFrame = useCallback((direction: 1 | -1) => {
    const video = videoRef.current
    if (!video) return
    video.pause()
    video.currentTime = Math.max(0, Math.min(video.currentTime + direction / 30, video.duration || 0))
    setCurrentTime(video.currentTime)
  }, [])

  const handleSpeedChange = useCallback((speed: number) => {
    const video = videoRef.current
    if (!video) return
    video.playbackRate = speed
    setPlaybackRate(speed)
  }, [])

  const handleScrub = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const video = videoRef.current
    if (!video) return
    const t = parseFloat(e.target.value)
    video.currentTime = t
    setCurrentTime(t)
  }, [])

  const handleFullscreen = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    if (!document.fullscreenElement) {
      el.requestFullscreen().catch(() => {})
    } else {
      document.exitFullscreen().catch(() => {})
    }
  }, [])

  const handleAddToExport = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    onAddToExport?.({ start: 0, end: video.duration })
  }, [onAddToExport])

  useEffect(() => {
    const onFsChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', onFsChange)
    return () => document.removeEventListener('fullscreenchange', onFsChange)
  }, [])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      if (e.code === 'Space') {
        e.preventDefault()
        handlePlay()
      }
      if (e.code === 'ArrowRight' && playbackRate === 1) {
        e.preventDefault()
        advanceFrame(1)
      }
      if (e.code === 'ArrowLeft' && playbackRate === 1) {
        e.preventDefault()
        advanceFrame(-1)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [handlePlay, advanceFrame, playbackRate])

  const alertMarkers = alerts.flatMap((alert) => {
    if (duration === 0) return []
    const offsetMs = new Date(alert.triggered_at).getTime() / 1000 - videoStartTime
    if (offsetMs < 0 || offsetMs > duration) return []
    return [{ id: alert.id, pct: (offsetMs / duration) * 100 }]
  })

  return (
    <div
      ref={containerRef}
      className={cn('flex flex-col bg-black rounded-md overflow-hidden', className)}
    >
      {/* Video */}
      <div className="relative flex-1 min-h-0 bg-black">
        {src ? (
          <video
            ref={videoRef}
            src={src}
            controls={false}
            className="w-full h-full object-contain"
            onPlay={() => { setIsPlaying(true); startRaf() }}
            onPause={() => { setIsPlaying(false); stopRaf(); syncTime() }}
            onEnded={() => { setIsPlaying(false); stopRaf(); syncTime() }}
            onLoadedMetadata={() => {
              const video = videoRef.current
              if (video) setDuration(video.duration)
            }}
            onTimeUpdate={() => {
              if (rafRef.current === null) setCurrentTime(videoRef.current?.currentTime ?? 0)
            }}
          />
        ) : (
          <div className="flex items-center justify-center h-48 text-muted-foreground text-sm">
            No clip selected
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex flex-col gap-2 px-3 py-2 bg-gray-900">
        {/* Scrubber row */}
        <div className="relative flex items-center gap-2">
          <span className="text-xs font-mono text-gray-300 shrink-0 w-24 text-center">
            {formatMMSS(currentTime)} / {formatMMSS(duration)}
          </span>

          <div className="relative flex-1 h-4 flex items-center">
            <input
              type="range"
              min={0}
              max={duration || 0}
              step={0.033}
              value={currentTime}
              onChange={handleScrub}
              className="w-full h-1.5 appearance-none bg-gray-600 rounded-full accent-indigo-500 cursor-pointer"
            />
            {/* Alert tick marks */}
            {alertMarkers.map((m) => (
              <div
                key={m.id}
                className="absolute top-0 w-0.5 h-4 bg-red-500 pointer-events-none"
                style={{ left: `${m.pct}%` }}
              />
            ))}
          </div>
        </div>

        {/* Button row */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Play / Pause */}
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 text-white hover:bg-gray-700"
            onClick={handlePlay}
            disabled={!src}
          >
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </Button>

          {/* Speed buttons */}
          <div className="flex items-center gap-1">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => handleSpeedChange(s)}
                disabled={!src}
                className={cn(
                  'text-xs px-2 py-0.5 rounded font-mono transition-colors',
                  playbackRate === s
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:bg-gray-700 hover:text-white',
                  !src && 'opacity-40 cursor-not-allowed'
                )}
              >
                {s}×
              </button>
            ))}
          </div>

          <div className="flex-1" />

          {/* Add to export */}
          {onAddToExport && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 gap-1 text-xs text-gray-300 hover:bg-gray-700 hover:text-white"
              onClick={handleAddToExport}
              disabled={!src || duration === 0}
            >
              <Download className="h-3.5 w-3.5" />
              Export
            </Button>
          )}

          {/* Fullscreen */}
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 text-gray-300 hover:bg-gray-700 hover:text-white"
            onClick={handleFullscreen}
            disabled={!src}
          >
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  )
}
