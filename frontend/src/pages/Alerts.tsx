import { useState, useMemo, useCallback, useTransition } from 'react'
import { format } from 'date-fns'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type RowSelectionState,
} from '@tanstack/react-table'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Eye, CheckCircle, Flag, ChevronUp, ChevronDown, ChevronsUpDown, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/components/ui/use-toast'
import {
  useAlerts,
  useAlertStats,
  useAcknowledgeAlert,
  useLegalHold,
  useMarkFalsePositive,
  useBulkAcknowledge,
  useBulkFalsePositive,
} from '@/api/alerts'
import type { AlertEvent } from '@/types'

type Severity = 'low' | 'medium' | 'high' | 'critical'
type AckFilter = 'all' | 'unacknowledged' | 'acknowledged'
type StatPeriod = '24h' | '7d' | '30d'

const severityColors: Record<Severity, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-amber-500',
  low: 'bg-blue-500',
}

const chartColors: Record<Severity, string> = {
  low: '#3b82f6',
  medium: '#f59e0b',
  high: '#f97316',
  critical: '#ef4444',
}

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge className={`${severityColors[severity]} text-white text-xs capitalize`}>
      {severity}
    </Badge>
  )
}

const ackSchema = z.object({ notes: z.string().optional() })
type AckForm = z.infer<typeof ackSchema>

function AlertDetailSheet({
  alert,
  open,
  onOpenChange,
}: {
  alert: AlertEvent | null
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const { toast } = useToast()
  const acknowledgeAlert = useAcknowledgeAlert()
  const legalHold = useLegalHold()
  const markFalsePositive = useMarkFalsePositive()

  const { register, handleSubmit, reset } = useForm<AckForm>({
    resolver: zodResolver(ackSchema),
  })

  const onAcknowledge = async (data: AckForm) => {
    if (!alert) return
    try {
      await acknowledgeAlert.mutateAsync({ id: alert.id, notes: data.notes })
      toast({ title: 'Alert acknowledged' })
      reset()
    } catch {
      toast({ title: 'Failed to acknowledge', variant: 'destructive' })
    }
  }

  const handleLegalHold = async (hold: boolean) => {
    if (!alert) return
    try {
      await legalHold.mutateAsync({ id: alert.id, hold })
      toast({ title: hold ? 'Legal hold applied' : 'Legal hold removed' })
    } catch {
      toast({ title: 'Failed to update legal hold', variant: 'destructive' })
    }
  }

  const handleFalsePositive = async (value: boolean) => {
    if (!alert) return
    try {
      await markFalsePositive.mutateAsync({ id: alert.id, value })
      toast({ title: value ? 'Marked as false positive' : 'False positive removed' })
    } catch {
      toast({ title: 'Failed to update', variant: 'destructive' })
    }
  }

  if (!alert) return null

  const metaRows: Array<[string, string | number | boolean | null]> = [
    ['Severity', alert.severity],
    ['Camera', alert.camera_name],
    ['Rule', alert.rule_triggered],
    ['Zone', alert.zone_name ?? '—'],
    ['Class', alert.class_name ?? '—'],
    ['Confidence', alert.confidence != null ? `${(alert.confidence * 100).toFixed(1)}%` : '—'],
    ['Track ID', alert.track_id ?? '—'],
    ['Time', format(new Date(alert.triggered_at), 'MMM d, yyyy HH:mm:ss')],
    ['Acknowledged', alert.acknowledged ? `Yes — ${alert.acknowledged_by ?? ''}` : 'No'],
    ['Legal Hold', alert.legal_hold ? 'Yes' : 'No'],
    ['False Positive', alert.false_positive ? 'Yes' : 'No'],
    ['Notes', alert.notes ?? '—'],
  ]

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[480px] sm:w-[540px] flex flex-col gap-4 overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            Alert Detail
            <SeverityBadge severity={alert.severity} />
          </SheetTitle>
        </SheetHeader>

        {alert.frame_path && (
          <div className="relative">
            <img
              src={`/api/alerts/${alert.id}/frame`}
              alt="Alert frame"
              className="w-full rounded"
            />
            <div
              className="absolute border-2 border-red-500"
              style={{ top: '35%', left: '35%', width: '30%', height: '30%' }}
            />
          </div>
        )}

        <div className="rounded-md border overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {metaRows.map(([key, val]) => (
                <tr key={key} className="border-b last:border-0">
                  <td className="py-1.5 px-3 font-medium text-muted-foreground w-36 bg-muted/30">
                    {key}
                  </td>
                  <td className="py-1.5 px-3 break-words">{String(val)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {alert.clip_path && (
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1 uppercase tracking-wide">
              Clip
            </p>
            <video
              src={`/api/alerts/${alert.id}/clip`}
              controls
              className="w-full rounded"
            />
          </div>
        )}

        {!alert.acknowledged && (
          <>
            <Separator />
            <form onSubmit={handleSubmit(onAcknowledge)} className="space-y-3">
              <p className="text-sm font-medium">Acknowledge Alert</p>
              <div className="space-y-1">
                <Label htmlFor="ack-notes">Notes (optional)</Label>
                <Input
                  id="ack-notes"
                  placeholder="Add a note…"
                  {...register('notes')}
                />
              </div>
              <Button
                type="submit"
                size="sm"
                disabled={acknowledgeAlert.isPending}
                className="w-full"
              >
                {acknowledgeAlert.isPending ? 'Acknowledging…' : 'Acknowledge'}
              </Button>
            </form>
          </>
        )}

        <Separator />

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label htmlFor="legal-hold-toggle" className="text-sm">
              Legal Hold
            </Label>
            <Switch
              id="legal-hold-toggle"
              checked={alert.legal_hold}
              onCheckedChange={handleLegalHold}
              disabled={legalHold.isPending}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="false-positive-toggle" className="text-sm">
              False Positive
            </Label>
            <Switch
              id="false-positive-toggle"
              checked={alert.false_positive}
              onCheckedChange={handleFalsePositive}
              disabled={markFalsePositive.isPending}
            />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

const columnHelper = createColumnHelper<AlertEvent>()

export default function Alerts() {
  const { toast } = useToast()

  const [cameraFilter, setCameraFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState<Severity[]>([])
  const [ruleFilter, setRuleFilter] = useState('')
  const [ackFilter, setAckFilter] = useState<AckFilter>('all')
  const [startedAfter, setStartedAfter] = useState('')
  const [startedBefore, setStartedBefore] = useState('')
  const [globalFilter, setGlobalFilter] = useState('')
  const [sorting, setSorting] = useState<SortingState>([{ id: 'triggered_at', desc: true }])
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [statPeriod, setStatPeriod] = useState<StatPeriod>('24h')
  const [detailAlert, setDetailAlert] = useState<AlertEvent | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)

  // Applied filters only change when user clicks Search — prevents re-querying on every keystroke
  const [appliedFilters, setAppliedFilters] = useState<Record<string, unknown>>({})
  const [isPending, startTransition] = useTransition()

  const pendingFilters = useMemo(() => {
    const f: Record<string, unknown> = {}
    if (cameraFilter) f.camera_id = cameraFilter
    if (severityFilter.length === 1) f.severity = severityFilter[0]
    if (ruleFilter) f.rule = ruleFilter
    if (ackFilter === 'unacknowledged') f.acknowledged = false
    if (ackFilter === 'acknowledged') f.acknowledged = true
    if (startedAfter) f.started_after = new Date(startedAfter).toISOString()
    if (startedBefore) f.started_before = new Date(startedBefore + 'T23:59:59').toISOString()
    return f
  }, [cameraFilter, severityFilter, ackFilter, ruleFilter, startedAfter, startedBefore])

  const handleSearch = () => startTransition(() => setAppliedFilters(pendingFilters))

  const { data: alertsData, isLoading: alertsLoading } = useAlerts(appliedFilters)
  const { data: stats, isLoading: statsLoading } = useAlertStats(statPeriod)

  const acknowledgeAlert = useAcknowledgeAlert()
  const markFalsePositive = useMarkFalsePositive()
  const bulkAcknowledge = useBulkAcknowledge()
  const bulkFalsePositive = useBulkFalsePositive()

  const alerts = alertsData?.items ?? []

  const handleClearFilters = () => {
    setCameraFilter('')
    setSeverityFilter([])
    setRuleFilter('')
    setAckFilter('all')
    setStartedAfter('')
    setStartedBefore('')
    setAppliedFilters({})
  }

  const toggleSeverity = (s: Severity) => {
    setSeverityFilter((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    )
  }

  const openDetail = useCallback((alert: AlertEvent) => {
    setDetailAlert(alert)
    setSheetOpen(true)
  }, [])

  const handleQuickAcknowledge = async (alert: AlertEvent) => {
    try {
      await acknowledgeAlert.mutateAsync({ id: alert.id })
      toast({ title: 'Alert acknowledged' })
    } catch {
      toast({ title: 'Failed to acknowledge', variant: 'destructive' })
    }
  }

  const handleQuickFalsePositive = async (alert: AlertEvent) => {
    try {
      await markFalsePositive.mutateAsync({ id: alert.id, value: true })
      toast({ title: 'Marked as false positive' })
    } catch {
      toast({ title: 'Failed to update', variant: 'destructive' })
    }
  }

  const selectedIds = useMemo(
    () =>
      Object.keys(rowSelection)
        .filter((k) => rowSelection[k])
        .map((k) => alerts[Number(k)]?.id)
        .filter(Boolean) as string[],
    [rowSelection, alerts]
  )

  const handleBulkAcknowledge = async () => {
    if (selectedIds.length === 0) return
    try {
      await bulkAcknowledge.mutateAsync(selectedIds)
      setRowSelection({})
      toast({ title: `${selectedIds.length} alerts acknowledged` })
    } catch {
      toast({ title: 'Bulk acknowledge failed', variant: 'destructive' })
    }
  }

  const handleBulkFalsePositive = async () => {
    if (selectedIds.length === 0) return
    try {
      await bulkFalsePositive.mutateAsync({ ids: selectedIds, value: true })
      setRowSelection({})
      toast({ title: `${selectedIds.length} alerts marked as false positive` })
    } catch {
      toast({ title: 'Bulk update failed', variant: 'destructive' })
    }
  }

  const handleExportCSV = () => {
    const params = new URLSearchParams({ format: 'csv' })
    if (cameraFilter) params.set('camera_id', cameraFilter)
    if (severityFilter.length === 1) params.set('severity', severityFilter[0])
    if (ruleFilter) params.set('rule', ruleFilter)
    if (ackFilter === 'unacknowledged') params.set('acknowledged', 'false')
    if (ackFilter === 'acknowledged') params.set('acknowledged', 'true')
    if (startedAfter) params.set('started_after', startedAfter)
    if (startedBefore) params.set('started_before', startedBefore)
    const a = document.createElement('a')
    a.href = `/api/alerts?${params.toString()}`
    a.download = 'alerts.csv'
    a.click()
  }

  const highCriticalCount = stats
    ? (stats.by_severity.high ?? 0) + (stats.by_severity.critical ?? 0)
    : 0

  const falsePositiveCount = alerts.filter((a) => a.false_positive).length

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'select',
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllRowsSelected()}
            onChange={table.getToggleAllRowsSelectedHandler()}
            className="accent-indigo-600"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            className="accent-indigo-600"
          />
        ),
        enableSorting: false,
      }),
      columnHelper.accessor('severity', {
        header: 'Severity',
        cell: (info) => <SeverityBadge severity={info.getValue()} />,
      }),
      columnHelper.accessor('camera_name', {
        header: 'Camera',
        cell: (info) => <span className="text-sm">{info.getValue()}</span>,
      }),
      columnHelper.accessor('rule_triggered', {
        header: 'Rule',
        cell: (info) => <span className="text-sm truncate max-w-[160px] block">{info.getValue()}</span>,
      }),
      columnHelper.accessor('zone_name', {
        header: 'Zone',
        cell: (info) => (
          <span className="text-sm text-muted-foreground">{info.getValue() ?? '—'}</span>
        ),
      }),
      columnHelper.accessor('triggered_at', {
        header: 'Time',
        cell: (info) => (
          <span className="text-sm tabular-nums whitespace-nowrap">
            {format(new Date(info.getValue()), 'MMM d, HH:mm:ss')}
          </span>
        ),
      }),
      columnHelper.accessor('acknowledged', {
        header: 'Acknowledged',
        cell: (info) =>
          info.getValue() ? (
            <Badge variant="outline" className="text-xs text-green-600 border-green-600">
              Yes
            </Badge>
          ) : (
            <Badge variant="outline" className="text-xs text-muted-foreground">
              No
            </Badge>
          ),
      }),
      columnHelper.display({
        id: 'actions',
        header: 'Actions',
        cell: ({ row }) => {
          const alert = row.original
          return (
            <div className="flex items-center gap-1">
              <button
                onClick={() => openDetail(alert)}
                className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
                title="View details"
              >
                <Eye className="h-4 w-4" />
              </button>
              {!alert.acknowledged && (
                <button
                  onClick={() => handleQuickAcknowledge(alert)}
                  className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-green-600"
                  title="Acknowledge"
                >
                  <CheckCircle className="h-4 w-4" />
                </button>
              )}
              <button
                onClick={() => handleQuickFalsePositive(alert)}
                className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-amber-500"
                title="Mark false positive"
              >
                <Flag className="h-4 w-4" />
              </button>
            </div>
          )
        },
        enableSorting: false,
      }),
    ],
    [openDetail]
  )

  const table = useReactTable({
    data: alerts,
    columns,
    state: { sorting, globalFilter, rowSelection },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    enableRowSelection: true,
  })

  const severities: Severity[] = ['low', 'medium', 'high', 'critical']

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Alerts</h1>
      </div>

      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="space-y-1 min-w-[160px]">
              <Label className="text-xs">Camera</Label>
              <Input
                placeholder="Filter by camera…"
                value={cameraFilter}
                onChange={(e) => setCameraFilter(e.target.value)}
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Severity</Label>
              <div className="flex items-center gap-1">
                {severities.map((s) => (
                  <button
                    key={s}
                    onClick={() => toggleSeverity(s)}
                    className={`px-2 py-1 rounded text-xs font-medium border transition-colors ${
                      severityFilter.includes(s)
                        ? `${severityColors[s]} text-white border-transparent`
                        : 'border-border text-muted-foreground hover:border-foreground'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1 min-w-[160px]">
              <Label className="text-xs">Rule</Label>
              <Input
                placeholder="Filter by rule…"
                value={ruleFilter}
                onChange={(e) => setRuleFilter(e.target.value)}
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Status</Label>
              <div className="flex items-center gap-1">
                {(['all', 'unacknowledged', 'acknowledged'] as AckFilter[]).map((opt) => (
                  <button
                    key={opt}
                    onClick={() => setAckFilter(opt)}
                    className={`px-2 py-1 rounded text-xs border transition-colors capitalize ${
                      ackFilter === opt
                        ? 'bg-foreground text-background border-transparent'
                        : 'border-border text-muted-foreground hover:border-foreground'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">From (date)</Label>
              <Input
                type="date"
                value={startedAfter}
                onChange={(e) => setStartedAfter(e.target.value)}
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">To (date)</Label>
              <Input
                type="date"
                value={startedBefore}
                onChange={(e) => setStartedBefore(e.target.value)}
                className="h-8 text-sm"
              />
            </div>

            <div className="flex items-end gap-2">
              <Button size="sm" onClick={handleSearch} disabled={isPending} className="h-8">
                Search
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClearFilters}
                className="h-8 gap-1.5 text-muted-foreground"
              >
                <X className="h-3.5 w-3.5" />
                Clear
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Statistics</p>
          <Tabs value={statPeriod} onValueChange={(v) => setStatPeriod(v as StatPeriod)}>
            <TabsList className="h-7 text-xs">
              <TabsTrigger value="24h" className="text-xs px-2 py-1">24h</TabsTrigger>
              <TabsTrigger value="7d" className="text-xs px-2 py-1">7d</TabsTrigger>
              <TabsTrigger value="30d" className="text-xs px-2 py-1">30d</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {statsLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-20" />
            ))
          ) : (
            <>
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs text-muted-foreground font-normal">Total</CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3">
                  <p className="text-2xl font-bold tabular-nums">{stats?.total ?? 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs text-muted-foreground font-normal">Unacknowledged</CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3">
                  <p className="text-2xl font-bold tabular-nums text-amber-500">
                    {stats?.unacknowledged ?? 0}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs text-muted-foreground font-normal">High + Critical</CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3">
                  <p className="text-2xl font-bold tabular-nums text-red-500">{highCriticalCount}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs text-muted-foreground font-normal">False Positives</CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3">
                  <p className="text-2xl font-bold tabular-nums text-muted-foreground">
                    {falsePositiveCount}
                  </p>
                </CardContent>
              </Card>
            </>
          )}
        </div>

        {!statsLoading && stats && stats.by_hour.length > 0 && (
          <Card>
            <CardContent className="pt-4 pb-2">
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={stats.by_hour}>
                  <XAxis
                    dataKey="hour"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v) => {
                      try {
                        return format(new Date(v), 'HH:mm')
                      } catch {
                        return v
                      }
                    }}
                  />
                  <YAxis tick={{ fontSize: 10 }} width={28} allowDecimals={false} />
                  <Tooltip
                    labelFormatter={(v) => {
                      try {
                        return format(new Date(v as string), 'MMM d HH:mm')
                      } catch {
                        return String(v)
                      }
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke={chartColors.critical}
                    fill={chartColors.critical}
                    fillOpacity={0.15}
                    strokeWidth={1.5}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>

      <div className="flex items-center justify-between gap-3">
        <Input
          placeholder="Search alerts…"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="h-8 text-sm max-w-xs"
        />
        {selectedIds.length > 0 && (
          <div className="flex items-center gap-2 rounded-md border px-3 py-1.5 bg-muted/40">
            <span className="text-sm text-muted-foreground">{selectedIds.length} selected</span>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleBulkAcknowledge}
              disabled={bulkAcknowledge.isPending}
            >
              Acknowledge selected
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleBulkFalsePositive}
              disabled={bulkFalsePositive.isPending}
            >
              Mark false positive
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleExportCSV}
            >
              Export CSV
            </Button>
          </div>
        )}
        {selectedIds.length === 0 && (
          <Button
            size="sm"
            variant="outline"
            className="h-8 text-xs"
            onClick={handleExportCSV}
          >
            Export CSV
          </Button>
        )}
      </div>

      <div className="rounded-md border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => (
                    <th
                      key={header.id}
                      className="px-3 py-2 text-left text-xs font-medium text-muted-foreground whitespace-nowrap"
                    >
                      {header.isPlaceholder ? null : (
                        <div
                          className={
                            header.column.getCanSort()
                              ? 'flex items-center gap-1 cursor-pointer select-none hover:text-foreground'
                              : ''
                          }
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {header.column.getCanSort() && (
                            <span className="ml-0.5">
                              {header.column.getIsSorted() === 'asc' ? (
                                <ChevronUp className="h-3 w-3" />
                              ) : header.column.getIsSorted() === 'desc' ? (
                                <ChevronDown className="h-3 w-3" />
                              ) : (
                                <ChevronsUpDown className="h-3 w-3 opacity-40" />
                              )}
                            </span>
                          )}
                        </div>
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {alertsLoading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} className="border-t">
                    {columns.map((_, j) => (
                      <td key={j} className="px-3 py-2">
                        <Skeleton className="h-5 w-full" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : table.getRowModel().rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="px-3 py-8 text-center text-sm text-muted-foreground"
                  >
                    No alerts found.
                  </td>
                </tr>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    className={`border-t hover:bg-accent/40 transition-colors ${
                      row.getIsSelected() ? 'bg-accent/60' : ''
                    }`}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <AlertDetailSheet
        alert={detailAlert}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </div>
  )
}
