import { useState, useMemo } from 'react'
import { format } from 'date-fns'
import { X, Download, FileText, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Calendar } from '@/components/ui/calendar'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/use-toast'
import { useAuthStore } from '@/store/authStore'
import { useCameras } from '@/api/cameras'
import { useTimeline, useCalendar, useCreateExport, useExportStatus } from '@/api/recordings'
import Timeline from '@/components/recordings/Timeline'
import RecordingPlayer from '@/components/recordings/RecordingPlayer'
import MultiCameraPlayer from '@/components/recordings/MultiCameraPlayer'
import type { RecordingSegment } from '@/types'

type ViewMode = 'single' | 'multi'

interface ExportRange {
  id: string
  cameraId: string
  cameraName: string
  start: string
  end: string
}

function toYMD(date: Date): string {
  return format(date, 'yyyy-MM-dd')
}

function toYYYYMM(date: Date): string {
  return format(date, 'yyyy-MM')
}

function formatTimestamp(iso: string): string {
  return format(new Date(iso), 'HH:mm:ss')
}

function durationBetween(start: string, end: string): string {
  const secs = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000)
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export default function Recordings() {
  const today = new Date()
  const [selectedDate, setSelectedDate] = useState<Date>(today)
  const [viewMode, setViewMode] = useState<ViewMode>('single')
  const [singleCameraId, setSingleCameraId] = useState<string | null>(null)
  const [multiCameraIds, setMultiCameraIds] = useState<Set<string>>(new Set())
  const [playerSrc, setPlayerSrc] = useState<string | null>(null)
  const [activeSegment, setActiveSegment] = useState<RecordingSegment | null>(null)
  const [exportRanges, setExportRanges] = useState<ExportRange[]>([])
  const [pendingExportId, setPendingExportId] = useState<string | null>(null)
  const [watermark, setWatermark] = useState(false)
  const [exportPassword, setExportPassword] = useState('')
  const [sheetOpen, setSheetOpen] = useState(false)

  const { toast } = useToast()
  const createExport = useCreateExport()
  const exportStatus = useExportStatus(pendingExportId)

  const dateStr = toYMD(selectedDate)
  const monthStr = toYYYYMM(selectedDate)

  const { data: camerasData, isLoading: camerasLoading } = useCameras()
  const cameras = camerasData?.items ?? []

  const activeCameraId = viewMode === 'single' ? (singleCameraId ?? cameras[0]?.id ?? null) : null

  const { data: calendarDates } = useCalendar(activeCameraId ?? cameras[0]?.id ?? '', monthStr)

  const recordingDates = useMemo<Set<string>>(() => {
    return new Set(calendarDates ?? [])
  }, [calendarDates])

  const { data: segments, isLoading: segmentsLoading } = useTimeline({
    camera_id: activeCameraId ?? '',
    date: dateStr,
  })

  const handleDateSelect = (date: Date | undefined) => {
    if (date) setSelectedDate(date)
  }

  const handleSingleCameraSelect = (id: string) => {
    setSingleCameraId(id)
    setPlayerSrc(null)
  }

  const handleMultiCameraToggle = (id: string) => {
    setMultiCameraIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else if (next.size < 4) {
        next.add(id)
      }
      return next
    })
  }

  const handleSegmentClick = (segment: RecordingSegment) => {
    const token = useAuthStore.getState().accessToken ?? ''
    setPlayerSrc(`/api/v1/recordings/segments/${segment.id}/stream?token=${token}`)
    setActiveSegment(segment)
  }

  const handleSelectionChange = (range: { start: string; end: string } | null) => {
    if (!range || !activeCameraId) return
    const cam = cameras.find((c) => c.id === activeCameraId)
    if (!cam) return
    const id = `${activeCameraId}-${range.start}`
    setExportRanges((prev) => {
      if (prev.some((r) => r.id === id)) return prev
      return [...prev, { id, cameraId: activeCameraId, cameraName: cam.name, start: range.start, end: range.end }]
    })
  }

  const handleAddToExport = (range: { start: number; end: number }) => {
    if (!activeCameraId || !activeSegment) return
    const cam = cameras.find((c) => c.id === activeCameraId)
    if (!cam) return
    const segmentStartMs = new Date(activeSegment.started_at).getTime()
    const start = new Date(segmentStartMs + range.start * 1000).toISOString()
    const end = new Date(segmentStartMs + range.end * 1000).toISOString()
    const id = `${activeCameraId}-${start}`
    setExportRanges((prev) => {
      if (prev.some((r) => r.id === id)) return prev
      return [...prev, { id, cameraId: activeCameraId, cameraName: cam.name, start, end }]
    })
  }

  const handleRemoveRange = (id: string) => {
    setExportRanges((prev) => prev.filter((r) => r.id !== id))
  }

  const handleExport = async () => {
    if (exportRanges.length === 0) return
    const first = exportRanges[0]
    try {
      const result = await createExport.mutateAsync({
        camera_id: first.cameraId,
        started_at: first.start,
        ended_at: first.end,
        watermark,
        password: exportPassword || undefined,
      })
      setPendingExportId(result.id)
      toast({ title: 'Export started', description: 'Your export is being processed.' })
    } catch {
      toast({ title: 'Export failed', description: 'Could not start the export.', variant: 'destructive' })
    }
  }

  const multiCameraSlots = useMemo(() => {
    if (viewMode !== 'multi') return []
    const selectedIds = Array.from(multiCameraIds).slice(0, 4)
    return selectedIds.map((id) => {
      const cam = cameras.find((c) => c.id === id)
      return {
        id,
        name: cam?.name ?? id,
        src: null as string | null,
      }
    })
  }, [viewMode, multiCameraIds, cameras])

  const exportInProgress =
    exportStatus.data?.status === 'pending' || exportStatus.data?.status === 'processing'

  const exportComplete = exportStatus.data?.status === 'completed'

  const modifierDates = useMemo(
    () => ({
      hasRecording: (date: Date) => recordingDates.has(toYMD(date)),
    }),
    [recordingDates]
  )

  return (
    <div className="flex h-full min-h-0 gap-0">
      <aside className="w-72 shrink-0 flex flex-col gap-4 border-r border-border p-4 overflow-y-auto">
        <div>
          <h2 className="text-sm font-semibold mb-2">Date</h2>
          <Calendar
            mode="single"
            selected={selectedDate}
            onSelect={handleDateSelect}
            modifiers={modifierDates}
            modifiersClassNames={{
              hasRecording: 'ring-1 ring-inset ring-indigo-400 rounded-md',
            }}
            className="rounded-md border p-0"
          />
        </div>

        <Separator />

        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold">Cameras</h2>
            <div className="flex items-center gap-1 text-xs">
              <button
                onClick={() => setViewMode('single')}
                className={viewMode === 'single' ? 'text-foreground font-medium' : 'text-muted-foreground'}
              >
                Single
              </button>
              <span className="text-muted-foreground">/</span>
              <button
                onClick={() => setViewMode('multi')}
                className={viewMode === 'multi' ? 'text-foreground font-medium' : 'text-muted-foreground'}
              >
                Multi
              </button>
            </div>
          </div>

          {camerasLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : (
            <ul className="space-y-1">
              {cameras.map((cam) => {
                if (viewMode === 'single') {
                  const checked = (singleCameraId ?? cameras[0]?.id) === cam.id
                  return (
                    <li key={cam.id}>
                      <label className="flex items-center gap-2 cursor-pointer rounded px-2 py-1.5 hover:bg-accent">
                        <input
                          type="radio"
                          name="single-camera"
                          checked={checked}
                          onChange={() => handleSingleCameraSelect(cam.id)}
                          className="accent-indigo-600"
                        />
                        <span className="text-sm truncate flex-1">{cam.name}</span>
                        <Badge
                          variant={cam.status === 'online' ? 'default' : 'secondary'}
                          className="text-[10px] px-1 py-0"
                        >
                          {cam.status}
                        </Badge>
                      </label>
                    </li>
                  )
                }
                const checked = multiCameraIds.has(cam.id)
                const disabled = !checked && multiCameraIds.size >= 4
                return (
                  <li key={cam.id}>
                    <label
                      className={cn(
                        'flex items-center gap-2 cursor-pointer rounded px-2 py-1.5 hover:bg-accent',
                        disabled && 'opacity-50 cursor-not-allowed'
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={() => handleMultiCameraToggle(cam.id)}
                        className="accent-indigo-600"
                      />
                      <span className="text-sm truncate flex-1">{cam.name}</span>
                      <Badge
                        variant={cam.status === 'online' ? 'default' : 'secondary'}
                        className="text-[10px] px-1 py-0"
                      >
                        {cam.status}
                      </Badge>
                    </label>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </aside>

      <main className="flex flex-1 min-w-0 flex-col gap-4 p-4 overflow-y-auto">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">
            Recordings — {format(selectedDate, 'MMMM d, yyyy')}
          </h1>
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetTrigger asChild>
              <Button size="sm" variant="outline" className="gap-1.5">
                <Download className="h-4 w-4" />
                Export
                {exportRanges.length > 0 && (
                  <Badge variant="secondary" className="ml-1 text-xs px-1.5 py-0">
                    {exportRanges.length}
                  </Badge>
                )}
                <ChevronRight className="h-3.5 w-3.5 ml-auto" />
              </Button>
            </SheetTrigger>
            <SheetContent className="w-96 flex flex-col gap-4 overflow-y-auto">
              <SheetHeader>
                <SheetTitle>Export</SheetTitle>
              </SheetHeader>

              {exportRanges.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Select a range on the timeline or use the player's Export button to add clips.
                </p>
              ) : (
                <ul className="space-y-2">
                  {exportRanges.map((r) => (
                    <li key={r.id} className="flex items-start gap-2 rounded-md border p-2 text-sm">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium truncate">{r.cameraName}</p>
                        <p className="text-muted-foreground text-xs">
                          {formatTimestamp(r.start)} – {formatTimestamp(r.end)}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {durationBetween(r.start, r.end)}
                        </p>
                      </div>
                      <button
                        onClick={() => handleRemoveRange(r.id)}
                        className="text-muted-foreground hover:text-destructive shrink-0 mt-0.5"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <Separator />

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label htmlFor="watermark-toggle" className="text-sm">
                    Watermark
                  </Label>
                  <Switch
                    id="watermark-toggle"
                    checked={watermark}
                    onCheckedChange={setWatermark}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="export-password" className="text-sm">
                    Password (optional)
                  </Label>
                  <Input
                    id="export-password"
                    type="password"
                    placeholder="Leave blank for no password"
                    value={exportPassword}
                    onChange={(e) => setExportPassword(e.target.value)}
                  />
                </div>
              </div>

              <Button
                onClick={handleExport}
                disabled={exportRanges.length === 0 || createExport.isPending || exportInProgress}
                className="w-full"
              >
                {createExport.isPending ? 'Starting…' : 'Export'}
              </Button>

              {(exportInProgress || exportComplete || exportStatus.data?.status === 'failed') && (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Export status</p>

                    {exportInProgress && (
                      <div className="space-y-1">
                        <Progress value={exportStatus.data?.progress_percent ?? 0} className="h-2" />
                        <p className="text-xs text-muted-foreground">
                          {exportStatus.data?.progress_percent ?? 0}% complete
                        </p>
                      </div>
                    )}

                    {exportComplete && exportStatus.data && (
                      <div className="space-y-2">
                        {exportStatus.data.download_url && (
                          <Button asChild size="sm" variant="outline" className="w-full gap-1.5">
                            <a href={exportStatus.data.download_url} download>
                              <Download className="h-4 w-4" />
                              Download
                            </a>
                          </Button>
                        )}
                        {exportStatus.data.sha256 && (
                          <div className="rounded-md bg-muted p-2 space-y-0.5">
                            <p className="text-xs text-muted-foreground flex items-center gap-1">
                              <FileText className="h-3 w-3" />
                              SHA-256
                            </p>
                            <p className="text-[10px] font-mono break-all">
                              {exportStatus.data.sha256}
                            </p>
                          </div>
                        )}
                        {exportStatus.data.expires_at && (
                          <p className="text-xs text-amber-600">
                            Expires {format(new Date(exportStatus.data.expires_at), 'MMM d, yyyy HH:mm')}
                          </p>
                        )}
                      </div>
                    )}

                    {exportStatus.data?.status === 'failed' && (
                      <p className="text-sm text-destructive">Export failed. Please try again.</p>
                    )}
                  </div>
                </>
              )}
            </SheetContent>
          </Sheet>
        </div>

        {viewMode === 'single' && activeCameraId && (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
              Timeline
            </p>
            {segmentsLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <Timeline
                segments={segments ?? []}
                date={dateStr}
                onSelectionChange={handleSelectionChange}
                onSegmentClick={handleSegmentClick}
              />
            )}
          </div>
        )}

        <div className="flex-1 min-h-0">
          {viewMode === 'single' ? (
            <RecordingPlayer
              src={playerSrc}
              onAddToExport={handleAddToExport}
              className="h-full min-h-[320px]"
            />
          ) : (
            <MultiCameraPlayer
              cameras={multiCameraSlots}
              date={dateStr}
            />
          )}
        </div>
      </main>
    </div>
  )
}

