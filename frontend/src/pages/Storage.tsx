import { useState } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'
import { useQuery } from '@tanstack/react-query'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { format, formatDistanceToNow } from 'date-fns'
import { HardDrive, Trash2, X, ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Slider } from '@/components/ui/slider'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip as UITooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useToast } from '@/components/ui/use-toast'
import { useStorageStatus } from '@/api/system'
import { usePurgePreview, useRequestPurge, useCancelExport, useStorageTrend } from '@/api/settings'
import api from '@/lib/api'
import type { StorageStatus, RecordingExport } from '@/types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number): string {
  if (bytes >= 1e12) return `${(bytes / 1e12).toFixed(1)} TB`
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${(bytes / 1e3).toFixed(1)} KB`
}

function formatGB(bytes: number): string {
  return `${(bytes / 1e9).toFixed(1)} GB`
}

// ---------------------------------------------------------------------------
// Per-camera row type
// ---------------------------------------------------------------------------

interface CameraStorageRow {
  camera_id: string
  camera_name: string
  used_bytes: number
  pct: number
  retention_days: number
}

// ---------------------------------------------------------------------------
// Sort icon helper
// ---------------------------------------------------------------------------

function SortIcon({ isSorted }: { isSorted: false | 'asc' | 'desc' }) {
  if (isSorted === 'asc') return <ChevronUp className="h-3.5 w-3.5 ml-1 inline-block" />
  if (isSorted === 'desc') return <ChevronDown className="h-3.5 w-3.5 ml-1 inline-block" />
  return <ChevronsUpDown className="h-3.5 w-3.5 ml-1 inline-block text-muted-foreground/50" />
}

// ---------------------------------------------------------------------------
// Per-camera table
// ---------------------------------------------------------------------------

const colHelper = createColumnHelper<CameraStorageRow>()

function CameraStorageTable({
  data,
  isLoading,
  totalBytes,
}: {
  data: StorageStatus['per_camera']
  isLoading: boolean
  totalBytes: number
}) {
  const { toast } = useToast()
  const [sorting, setSorting] = useState<SortingState>([{ id: 'used_bytes', desc: true }])
  // local retention state: camera_id -> days string
  const [retention, setRetention] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})

  const rows: CameraStorageRow[] = data.map((cam) => ({
    camera_id: cam.camera_id,
    camera_name: cam.camera_name,
    used_bytes: cam.used_bytes,
    pct: totalBytes > 0 ? (cam.used_bytes / totalBytes) * 100 : 0,
    retention_days: 30, // default; overridden by local state once edited
  }))

  const columns = [
    colHelper.accessor('camera_name', {
      header: 'Camera',
      cell: (info) => <span className="font-medium">{info.getValue()}</span>,
    }),
    colHelper.accessor('used_bytes', {
      header: ({ column }) => (
        <button
          className="flex items-center"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
        >
          Used storage
          <SortIcon isSorted={column.getIsSorted()} />
        </button>
      ),
      cell: (info) => formatBytes(info.getValue()),
    }),
    colHelper.accessor('pct', {
      header: '% of total',
      cell: (info) => (
        <div className="flex items-center gap-2">
          <Progress value={info.getValue()} className="h-1.5 w-16" />
          <span className="text-xs tabular-nums">{info.getValue().toFixed(1)}%</span>
        </div>
      ),
    }),
    colHelper.display({
      id: 'retention',
      header: 'Retention (days)',
      cell: ({ row }) => {
        const cameraId = row.original.camera_id
        const value = retention[cameraId] ?? '30'
        return (
          <Input
            type="number"
            min={1}
            max={3650}
            className="w-20 h-7 text-sm"
            value={value}
            onChange={(e) => setRetention((prev) => ({ ...prev, [cameraId]: e.target.value }))}
          />
        )
      },
    }),
    colHelper.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => {
        const cameraId = row.original.camera_id
        const days = parseInt(retention[cameraId] ?? '30', 10)
        const isSaving = saving[cameraId] ?? false

        const handleSave = async () => {
          if (isNaN(days) || days < 1) return
          setSaving((prev) => ({ ...prev, [cameraId]: true }))
          try {
            await api.patch(`/cameras/${cameraId}`, { retention_days: days })
            toast({ title: 'Retention updated', description: `Camera set to retain ${days} days.` })
          } catch {
            toast({ title: 'Failed to update retention', variant: 'destructive' })
          } finally {
            setSaving((prev) => ({ ...prev, [cameraId]: false }))
          }
        }

        return (
          <Button size="sm" className="h-7 text-xs" disabled={isSaving} onClick={handleSave}>
            {isSaving ? 'Saving…' : 'Save'}
          </Button>
        )
      },
    }),
  ]

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id}>
              {hg.headers.map((h) => (
                <TableHead key={h.id}>
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {isLoading ? (
            [...Array(4)].map((_, i) => (
              <TableRow key={i}>
                {columns.map((_, j) => (
                  <TableCell key={j}>
                    <Skeleton className="h-8 w-full" />
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : table.getRowModel().rows.length > 0 ? (
            table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="py-8 text-center text-muted-foreground">
                No camera storage data
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Donut chart + legend
// ---------------------------------------------------------------------------

function StorageDonut({ usedBytes, freeBytes }: { usedBytes: number; freeBytes: number }) {
  const donutData = [
    { name: 'Used', value: usedBytes },
    { name: 'Free', value: freeBytes },
  ]

  return (
    <div className="flex flex-col items-center gap-3">
      <PieChart width={160} height={160}>
        <Pie
          cx={80}
          cy={80}
          innerRadius={45}
          outerRadius={70}
          data={donutData}
          dataKey="value"
          strokeWidth={0}
        >
          <Cell fill="#3b82f6" />
          <Cell fill="#e5e7eb" />
        </Pie>
      </PieChart>
      <div className="flex gap-4 text-sm text-muted-foreground">
        <span>
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-blue-500 mr-1.5" />
          Used {formatGB(usedBytes)}
        </span>
        <span>
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-gray-200 mr-1.5" />
          Free {formatGB(freeBytes)}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Purge panel
// ---------------------------------------------------------------------------

function PurgePanel() {
  const { toast } = useToast()
  const [purgeDays, setPurgeDays] = useState(30)

  const { data: purgePreview } = usePurgePreview(null, purgeDays)
  const { mutateAsync: requestPurge, isPending: purging } = useRequestPurge()

  const handlePurge = async () => {
    if (
      !window.confirm(
        `Permanently delete recordings older than ${purgeDays} days? This cannot be undone.`
      )
    )
      return
    try {
      await requestPurge({ cameraId: null, days: purgeDays })
      toast({
        title: 'Purge started',
        description: `Removing recordings older than ${purgeDays} days.`,
      })
    } catch {
      toast({ title: 'Purge failed', variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label className="text-sm font-medium">Purge old recordings</Label>
        <Slider
          min={1}
          max={365}
          step={1}
          value={[purgeDays]}
          onValueChange={([v]) => setPurgeDays(v)}
          className="mt-1"
        />
        <p className="text-xs text-muted-foreground leading-relaxed">
          Retain last <span className="font-medium text-foreground">{purgeDays} days</span>
          {' — '}
          frees{' '}
          <span className="font-medium text-foreground">
            {formatBytes(purgePreview?.bytes_freed ?? 0)}
          </span>{' '}
          ({purgePreview?.segments_deleted ?? 0} segments)
        </p>
      </div>
      <Button
        variant="destructive"
        size="sm"
        className="w-full"
        disabled={purging}
        onClick={handlePurge}
      >
        <Trash2 className="h-3.5 w-3.5 mr-1.5" />
        {purging ? 'Purging…' : 'Purge now'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Trend chart
// ---------------------------------------------------------------------------

function TrendChart() {
  const { data: trendData, isLoading: trendLoading } = useStorageTrend()

  const chartData = (trendData ?? []).map((point) => ({
    date: point.date,
    total_bytes: point.total_bytes,
    label: format(new Date(point.date), 'MMM d'),
  }))

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <HardDrive className="h-4 w-4 text-muted-foreground" />
          30-day trend
        </CardTitle>
      </CardHeader>
      <CardContent>
        {trendLoading ? (
          <Skeleton className="h-[200px] w-full" />
        ) : chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
              <defs>
                <linearGradient id="storageGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tickFormatter={(v: number) => formatGB(v)}
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={60}
              />
              <Tooltip
                formatter={(value: number) => [formatBytes(value), 'Total storage']}
                labelFormatter={(label) => label}
                contentStyle={{ fontSize: 12 }}
              />
              <Area
                type="monotone"
                dataKey="total_bytes"
                stroke="#3b82f6"
                strokeWidth={2}
                fill="url(#storageGradient)"
                dot={false}
                activeDot={{ r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
            No trend data available
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Exports status badge
// ---------------------------------------------------------------------------

function ExportStatusBadge({ status }: { status: RecordingExport['status'] }) {
  const map: Record<RecordingExport['status'], { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
    pending: { label: 'Pending', variant: 'secondary' },
    processing: { label: 'Processing', variant: 'default' },
    completed: { label: 'Completed', variant: 'outline' },
    failed: { label: 'Failed', variant: 'destructive' },
  }
  const { label, variant } = map[status] ?? { label: status, variant: 'outline' }
  return <Badge variant={variant} className="text-xs capitalize">{label}</Badge>
}

// ---------------------------------------------------------------------------
// Pending exports section
// ---------------------------------------------------------------------------

function PendingExports() {
  const { toast } = useToast()
  const { mutateAsync: cancelExport, isPending: cancelling } = useCancelExport()

  const { data: exports, isLoading } = useQuery({
    queryKey: ['exports', 'pending'],
    queryFn: () =>
      api
        .get<RecordingExport[]>('/recordings/exports', {
          params: { status: 'pending,processing' },
        })
        .then((r) => r.data),
    refetchInterval: 5_000,
  })

  const handleCancel = async (exportId: string) => {
    try {
      await cancelExport(exportId)
      toast({ title: 'Export cancelled' })
    } catch {
      toast({ title: 'Failed to cancel export', variant: 'destructive' })
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Pending exports</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(2)].map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : exports && exports.length > 0 ? (
          <div className="space-y-2">
            {exports.map((exp) => (
              <div
                key={exp.id}
                className="flex items-center gap-3 rounded-md border p-3"
              >
                <div className="min-w-0 flex-1 space-y-1.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(exp.created_at), { addSuffix: true })}
                    </span>
                    <ExportStatusBadge status={exp.status} />
                  </div>
                  <Progress
                    value={exp.progress_percent}
                    className="h-1.5"
                  />
                  <p className="text-xs text-muted-foreground tabular-nums">
                    {exp.progress_percent}%
                  </p>
                </div>
                <TooltipProvider delayDuration={300}>
                  <UITooltip>
                    <TooltipTrigger asChild>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
                        disabled={cancelling}
                        onClick={() => handleCancel(exp.id)}
                      >
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Cancel export</TooltipContent>
                  </UITooltip>
                </TooltipProvider>
              </div>
            ))}
          </div>
        ) : (
          <p className="py-4 text-center text-sm text-muted-foreground">No pending exports</p>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Storage() {
  const { data: storageStatus, isLoading, dataUpdatedAt } = useStorageStatus()

  const lastUpdated = dataUpdatedAt
    ? formatDistanceToNow(new Date(dataUpdatedAt), { addSuffix: true })
    : null

  const total = storageStatus?.total_bytes ?? 0
  const used = storageStatus?.used_bytes ?? 0
  const free = storageStatus?.free_bytes ?? 0
  const usagePct = storageStatus?.usage_percent ?? 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Storage</h1>
          {lastUpdated && (
            <p className="text-sm text-muted-foreground mt-0.5">Updated {lastUpdated}</p>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-7 w-24" />
            ) : (
              <p className="text-2xl font-bold">{formatBytes(total)}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Used</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {isLoading ? (
              <>
                <Skeleton className="h-7 w-24" />
                <Skeleton className="h-2 w-full" />
              </>
            ) : (
              <>
                <p className="text-2xl font-bold">{formatBytes(used)}</p>
                <Progress value={usagePct} className="h-2" />
                <p className="text-xs text-muted-foreground">{usagePct.toFixed(1)}% used</p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Free</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-7 w-24" />
            ) : (
              <p className="text-2xl font-bold">{formatBytes(free)}</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: per-camera table (~60%) */}
        <div className="lg:col-span-3 space-y-2">
          <h2 className="text-sm font-semibold">Per-camera storage</h2>
          <CameraStorageTable
            data={storageStatus?.per_camera ?? []}
            isLoading={isLoading}
            totalBytes={total}
          />
        </div>

        {/* Right: donut + purge (~40%) */}
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Disk usage</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex justify-center py-4">
                  <Skeleton className="h-[160px] w-[160px] rounded-full" />
                </div>
              ) : (
                <StorageDonut usedBytes={used} freeBytes={free} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Manage recordings</CardTitle>
            </CardHeader>
            <CardContent>
              <PurgePanel />
            </CardContent>
          </Card>
        </div>
      </div>

      <Separator />

      {/* Trend chart */}
      <TrendChart />

      {/* Pending exports */}
      <PendingExports />
    </div>
  )
}
