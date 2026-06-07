import { useRef, useState, useEffect, useCallback } from 'react'
import { cn } from '@/lib/utils'
import type { RecordingSegment, AlertEvent } from '@/types'

interface TimelineProps {
  segments: RecordingSegment[]
  alerts?: AlertEvent[]
  date: string
  onSelectionChange?: (range: { start: string; end: string } | null) => void
  onSegmentClick?: (segment: RecordingSegment) => void
}

interface TooltipState {
  segment: RecordingSegment
  x: number
  y: number
}

interface DragState {
  startPx: number
  endPx: number
  startFrac: number
  endFrac: number
}

const ZOOM_LEVELS = [24, 6, 1] as const

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  if (m > 0) return s > 0 ? `${m}m ${s}s` : `${m}m`
  return `${s}s`
}

function formatTime(date: Date): string {
  return date.toTimeString().slice(0, 5)
}

function fracToIso(frac: number, dayStart: Date, dayDuration: number): string {
  return new Date(dayStart.getTime() + frac * dayDuration).toISOString()
}

function selectionDuration(startFrac: number, endFrac: number, dayDuration: number): string {
  const secs = Math.abs(endFrac - startFrac) * dayDuration / 1000
  return formatDuration(secs)
}

const SEGMENT_COLORS: Record<string, string> = {
  continuous: 'bg-blue-500',
  motion: 'bg-amber-500',
  event: 'bg-green-500',
}

export default function Timeline({
  segments,
  alerts = [],
  date,
  onSelectionChange,
  onSegmentClick,
}: TimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const barRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [zoomIndex, setZoomIndex] = useState(0)
  const [viewStart, setViewStart] = useState(0)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [drag, setDrag] = useState<DragState | null>(null)
  const [selection, setSelection] = useState<{ startFrac: number; endFrac: number } | null>(null)
  const [cursorFrac, setCursorFrac] = useState<number | null>(null)
  const isDragging = useRef(false)

  const zoomHours = ZOOM_LEVELS[zoomIndex]

  const dayStart = new Date(`${date}T00:00:00`)
  const dayDuration = 24 * 3600 * 1000

  const viewFrac = zoomHours / 24
  const viewEnd = Math.min(viewStart + viewFrac, 1)
  const clampedViewStart = Math.max(0, Math.min(viewStart, 1 - viewFrac))

  const viewStartMs = dayStart.getTime() + clampedViewStart * dayDuration
  const viewEndMs = dayStart.getTime() + viewEnd * dayDuration

  const isToday = date === new Date().toISOString().slice(0, 10)
  const nowFrac = isToday
    ? (Date.now() - dayStart.getTime()) / dayDuration
    : -1

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      setWidth(entries[0].contentRect.width)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const fracToPixel = useCallback(
    (frac: number) => {
      return ((frac - clampedViewStart) / viewFrac) * width
    },
    [clampedViewStart, viewFrac, width]
  )

  const pixelToFrac = useCallback(
    (px: number) => {
      return clampedViewStart + (px / width) * viewFrac
    },
    [clampedViewStart, viewFrac, width]
  )

  const getBarClientOffset = useCallback((clientX: number): number => {
    const rect = barRef.current?.getBoundingClientRect()
    if (!rect) return 0
    return Math.max(0, Math.min(clientX - rect.left, rect.width))
  }, [])

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault()
      const dir = e.deltaY > 0 ? 1 : -1
      const nextZoom = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, zoomIndex + dir))
      if (nextZoom === zoomIndex) return

      const rect = barRef.current?.getBoundingClientRect()
      const pivotFrac = rect
        ? pixelToFrac(e.clientX - rect.left)
        : clampedViewStart + viewFrac / 2

      const nextViewFrac = ZOOM_LEVELS[nextZoom] / 24
      let nextStart = pivotFrac - nextViewFrac / 2
      nextStart = Math.max(0, Math.min(nextStart, 1 - nextViewFrac))

      const snapHour = Math.round(nextStart * 24)
      let snapped = snapHour / 24
      snapped = Math.max(0, Math.min(snapped, 1 - nextViewFrac))

      setZoomIndex(nextZoom)
      setViewStart(snapped)
    },
    [zoomIndex, pixelToFrac, clampedViewStart, viewFrac]
  )

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return
      const px = getBarClientOffset(e.clientX)
      const frac = pixelToFrac(px)
      isDragging.current = true
      setDrag({ startPx: px, endPx: px, startFrac: frac, endFrac: frac })
      setSelection(null)
      onSelectionChange?.(null)
    },
    [pixelToFrac, getBarClientOffset, onSelectionChange]
  )

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const px = getBarClientOffset(e.clientX)
      const frac = pixelToFrac(px)
      setCursorFrac(frac)

      if (isDragging.current && drag) {
        setDrag((d) => d ? { ...d, endPx: px, endFrac: frac } : d)
      }
    },
    [drag, pixelToFrac, getBarClientOffset]
  )

  const handleMouseUp = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging.current || !drag) return
      isDragging.current = false

      const px = getBarClientOffset(e.clientX)
      const frac = pixelToFrac(px)
      const finalDrag = { ...drag, endPx: px, endFrac: frac }

      const [lo, hi] = finalDrag.startFrac < frac
        ? [finalDrag.startFrac, frac]
        : [frac, finalDrag.startFrac]

      if (Math.abs(hi - lo) < 0.002) {
        const clickedSegment = segments.find((seg) => {
          const sStart = (new Date(seg.started_at).getTime() - dayStart.getTime()) / dayDuration
          const sEnd = seg.ended_at
            ? (new Date(seg.ended_at).getTime() - dayStart.getTime()) / dayDuration
            : sStart + (seg.duration_s ?? 0) / 86400
          return frac >= sStart && frac <= sEnd
        })
        if (clickedSegment) onSegmentClick?.(clickedSegment)
        setDrag(null)
        return
      }

      setSelection({ startFrac: lo, endFrac: hi })
      onSelectionChange?.({
        start: fracToIso(lo, dayStart, dayDuration),
        end: fracToIso(hi, dayStart, dayDuration),
      })
      setDrag(null)
    },
    [drag, pixelToFrac, getBarClientOffset, segments, dayStart, dayDuration, onSelectionChange, onSegmentClick]
  )

  const handleMouseLeave = useCallback(() => {
    setCursorFrac(null)
    if (isDragging.current && drag) {
      isDragging.current = false
      setDrag(null)
    }
    setTooltip(null)
  }, [drag])

  const handleSegmentHover = useCallback(
    (e: React.MouseEvent, segment: RecordingSegment) => {
      e.stopPropagation()
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      setTooltip({ segment, x: e.clientX - rect.left, y: e.clientY - rect.top })
    },
    []
  )

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelection(null)
        onSelectionChange?.(null)
      }
      if (e.key === 'Enter' && cursorFrac !== null) {
        const seg = segments.find((s) => {
          const sStart = (new Date(s.started_at).getTime() - dayStart.getTime()) / dayDuration
          const sEnd = s.ended_at
            ? (new Date(s.ended_at).getTime() - dayStart.getTime()) / dayDuration
            : sStart + (s.duration_s ?? 0) / 86400
          return cursorFrac >= sStart && cursorFrac <= sEnd
        })
        if (seg) onSegmentClick?.(seg)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [cursorFrac, segments, dayStart, dayDuration, onSelectionChange, onSegmentClick])

  const tickInterval = zoomHours === 1 ? 15 : zoomHours === 6 ? 60 : 60
  const tickCount = (zoomHours * 60) / tickInterval
  const ticks: number[] = []
  for (let i = 0; i <= tickCount; i++) {
    const frac = clampedViewStart + (i / tickCount) * viewFrac
    if (frac >= 0 && frac <= 1) ticks.push(frac)
  }

  const viewStartDate = new Date(viewStartMs)
  const viewEndDate = new Date(viewEndMs)
  const rangeLabel = `${formatTime(viewStartDate)} – ${formatTime(viewEndDate)}`

  const activeDrag = drag
    ? {
        lo: Math.min(drag.startFrac, drag.endFrac),
        hi: Math.max(drag.startFrac, drag.endFrac),
      }
    : null

  return (
    <div ref={containerRef} className="relative w-full select-none" onWheel={handleWheel}>
      <div className="flex items-center justify-between mb-1 px-0.5">
        <span className="text-xs text-muted-foreground font-mono">{rangeLabel}</span>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-2 rounded-sm bg-blue-500" /> Continuous
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-2 rounded-sm bg-amber-500" /> Motion
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-2 rounded-sm bg-green-500" /> Event
          </span>
          <span className="text-xs opacity-60">Scroll to zoom</span>
        </div>
      </div>

      {/* Timeline bar */}
      <div
        ref={barRef}
        className="relative h-10 bg-muted rounded cursor-crosshair overflow-hidden"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
      >
        {/* Segments */}
        {segments.map((seg) => {
          const sStart = (new Date(seg.started_at).getTime() - dayStart.getTime()) / dayDuration
          const sEnd = seg.ended_at
            ? (new Date(seg.ended_at).getTime() - dayStart.getTime()) / dayDuration
            : sStart + (seg.duration_s ?? 0) / 86400

          const left = fracToPixel(Math.max(sStart, clampedViewStart))
          const right = fracToPixel(Math.min(sEnd, clampedViewStart + viewFrac))
          const segWidth = right - left
          if (segWidth <= 0) return null

          const color = SEGMENT_COLORS[seg.segment_type] ?? 'bg-blue-500'
          return (
            <div
              key={seg.id}
              className={cn('absolute top-0 h-full opacity-80 hover:opacity-100 transition-opacity cursor-pointer', color)}
              style={{ left, width: segWidth }}
              onMouseEnter={(e) => handleSegmentHover(e, seg)}
              onMouseLeave={() => setTooltip(null)}
              onMouseMove={(e) => handleSegmentHover(e, seg)}
            />
          )
        })}

        {/* Alert markers */}
        {alerts.map((alert) => {
          const aFrac = (new Date(alert.triggered_at).getTime() - dayStart.getTime()) / dayDuration
          if (aFrac < clampedViewStart || aFrac > clampedViewStart + viewFrac) return null
          const px = fracToPixel(aFrac)
          return (
            <div
              key={alert.id}
              className="absolute top-0 flex flex-col items-center pointer-events-none"
              style={{ left: px - 5, width: 10 }}
            >
              <span className="text-red-500 text-[10px] leading-none">▾</span>
              <div className="w-px h-full bg-red-500 opacity-70" />
            </div>
          )
        })}

        {/* Now line */}
        {nowFrac >= clampedViewStart && nowFrac <= clampedViewStart + viewFrac && (
          <div
            className="absolute top-0 h-full w-px bg-red-500 z-10 pointer-events-none"
            style={{ left: fracToPixel(nowFrac) }}
          />
        )}

        {/* Active drag selection */}
        {activeDrag && width > 0 && (
          <div
            className="absolute top-0 h-full bg-indigo-400/30 border-x border-indigo-500 pointer-events-none"
            style={{
              left: fracToPixel(activeDrag.lo),
              width: fracToPixel(activeDrag.hi) - fracToPixel(activeDrag.lo),
            }}
          />
        )}

        {/* Committed selection */}
        {selection && !activeDrag && width > 0 && (
          <div
            className="absolute top-0 h-full bg-indigo-200/50 border-x border-indigo-400 pointer-events-none"
            style={{
              left: fracToPixel(selection.startFrac),
              width: fracToPixel(selection.endFrac) - fracToPixel(selection.startFrac),
            }}
          />
        )}
      </div>

      {/* Time axis */}
      <div className="relative h-5 mt-0.5">
        {ticks.map((frac, i) => {
          const px = fracToPixel(frac)
          const totalMinutes = Math.round(frac * 1440)
          const h = Math.floor(totalMinutes / 60)
          const m = totalMinutes % 60
          const label = zoomHours === 1
            ? `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
            : `${String(h).padStart(2, '0')}:00`
          return (
            <span
              key={i}
              className="absolute text-[10px] text-muted-foreground -translate-x-1/2 whitespace-nowrap"
              style={{ left: px }}
            >
              {label}
            </span>
          )
        })}
      </div>

      {/* Drag / selection duration label */}
      {activeDrag && activeDrag.hi > activeDrag.lo && (
        <div className="mt-1 text-xs text-indigo-600 font-medium">
          Selected: {selectionDuration(activeDrag.lo, activeDrag.hi, dayDuration)}
        </div>
      )}
      {selection && !activeDrag && (
        <div className="mt-1 text-xs text-indigo-600 font-medium">
          Selected: {selectionDuration(selection.startFrac, selection.endFrac, dayDuration)}
        </div>
      )}

      {/* Hover tooltip */}
      {tooltip && (
        <div
          className="absolute z-50 pointer-events-none bg-popover border border-border rounded-md shadow-md px-3 py-2 text-xs text-popover-foreground space-y-0.5"
          style={{
            left: Math.min(tooltip.x + 10, width - 180),
            top: tooltip.y - 70,
          }}
        >
          <div className="font-semibold capitalize">{tooltip.segment.segment_type}</div>
          <div className="text-muted-foreground">
            {formatTime(new Date(tooltip.segment.started_at))}
            {tooltip.segment.ended_at && (
              <> – {formatTime(new Date(tooltip.segment.ended_at))}</>
            )}
          </div>
          {tooltip.segment.duration_s != null && (
            <div>{formatDuration(tooltip.segment.duration_s)}</div>
          )}
          <div>{formatBytes(tooltip.segment.size_bytes)}</div>
        </div>
      )}
    </div>
  )
}
