import { useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { format } from 'date-fns'
import { ChevronDown, ChevronUp, Download, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuditLog } from '@/api/audit'
import type { AuditEntry } from '@/types'

const RESOURCE_TYPES = [
  'user',
  'camera',
  'recording',
  'alert',
  'zone',
  'session',
  'system',
]

interface Filters {
  actor_email?: string
  action?: string
  resource_type?: string
  started_after?: string
  started_before?: string
}

function JsonDiffRow({ entry }: { entry: AuditEntry }) {
  const [expanded, setExpanded] = useState(false)

  if (!entry.detail) return null

  const hasDiff =
    typeof entry.detail === 'object' &&
    'before' in entry.detail &&
    'after' in entry.detail

  return (
    <div className="mt-1">
      <button
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        {expanded ? 'Hide detail' : 'Show detail'}
      </button>
      {expanded && (
        <div className="mt-1.5">
          {hasDiff ? (
            <div className="flex gap-2">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-muted-foreground mb-0.5">Before</p>
                <pre className="text-xs bg-red-50 dark:bg-red-950/30 p-2 rounded font-mono overflow-auto max-h-40 border border-red-100">
                  {JSON.stringify(entry.detail.before, null, 2)}
                </pre>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-muted-foreground mb-0.5">After</p>
                <pre className="text-xs bg-green-50 dark:bg-green-950/30 p-2 rounded font-mono overflow-auto max-h-40 border border-green-100">
                  {JSON.stringify(entry.detail.after, null, 2)}
                </pre>
              </div>
            </div>
          ) : (
            <pre className="text-xs bg-muted p-2 rounded font-mono overflow-auto max-h-40">
              {JSON.stringify(entry.detail, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

function buildCsvUrl(filters: Filters): string {
  const params = new URLSearchParams()
  params.set('format', 'csv')
  if (filters.actor_email) params.set('actor_email', filters.actor_email)
  if (filters.action) params.set('action', filters.action)
  if (filters.resource_type) params.set('resource_type', filters.resource_type)
  if (filters.started_after) params.set('started_after', filters.started_after)
  if (filters.started_before) params.set('started_before', filters.started_before)
  return `/api/audit?${params.toString()}`
}

export default function AuditLog() {
  const [filters, setFilters] = useState<Filters>({})
  const [draftFilters, setDraftFilters] = useState<Filters>({})

  const parentRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useAuditLog(filters)

  const rows: AuditEntry[] = data?.pages.flatMap((p) => p.items) ?? []
  const totalCount = data?.pages[0]?.total ?? 0

  const virtualizer = useVirtualizer({
    count: rows.length + (hasNextPage ? 1 : 0),
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48,
    overscan: 10,
  })

  const virtualItems = virtualizer.getVirtualItems()

  const lastItem = virtualItems[virtualItems.length - 1]
  if (lastItem && lastItem.index >= rows.length && hasNextPage && !isFetchingNextPage) {
    fetchNextPage()
  }

  const applyFilters = () => {
    const cleaned: Filters = {}
    if (draftFilters.actor_email?.trim()) cleaned.actor_email = draftFilters.actor_email.trim()
    if (draftFilters.action?.trim()) cleaned.action = draftFilters.action.trim()
    if (draftFilters.resource_type) cleaned.resource_type = draftFilters.resource_type
    if (draftFilters.started_after) cleaned.started_after = draftFilters.started_after
    if (draftFilters.started_before) cleaned.started_before = draftFilters.started_before
    setFilters(cleaned)
  }

  const clearFilters = () => {
    setDraftFilters({})
    setFilters({})
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Audit Log</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {totalCount.toLocaleString()} entries
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => window.open(buildCsvUrl(filters))}
        >
          <Download className="h-4 w-4 mr-1.5" />
          Export CSV
        </Button>
      </div>

      <div className="rounded-md border p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Actor email</Label>
            <Input
              placeholder="user@example.com"
              value={draftFilters.actor_email ?? ''}
              onChange={(e) =>
                setDraftFilters((f) => ({ ...f, actor_email: e.target.value }))
              }
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Action</Label>
            <Input
              placeholder="e.g. login, config_change"
              value={draftFilters.action ?? ''}
              onChange={(e) =>
                setDraftFilters((f) => ({ ...f, action: e.target.value }))
              }
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Resource type</Label>
            <Select
              value={draftFilters.resource_type ?? 'all'}
              onValueChange={(v) =>
                setDraftFilters((f) => ({
                  ...f,
                  resource_type: v === 'all' ? undefined : v,
                }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="All types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                {RESOURCE_TYPES.map((rt) => (
                  <SelectItem key={rt} value={rt}>
                    {rt}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">After</Label>
            <Input
              type="datetime-local"
              value={draftFilters.started_after ?? ''}
              onChange={(e) =>
                setDraftFilters((f) => ({ ...f, started_after: e.target.value || undefined }))
              }
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Before</Label>
            <Input
              type="datetime-local"
              value={draftFilters.started_before ?? ''}
              onChange={(e) =>
                setDraftFilters((f) => ({ ...f, started_before: e.target.value || undefined }))
              }
            />
          </div>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={applyFilters}>
            Apply filters
          </Button>
          <Button size="sm" variant="outline" onClick={clearFilters}>
            <X className="h-3.5 w-3.5 mr-1" />
            Clear
          </Button>
        </div>
      </div>

      <div className="rounded-md border overflow-hidden">
        <div className="grid grid-cols-[140px_1fr_1fr_1fr_100px] bg-muted/50 border-b px-3 py-2 text-xs font-medium text-muted-foreground">
          <div>Time</div>
          <div>Actor</div>
          <div>Action</div>
          <div>Resource</div>
          <div>IP</div>
        </div>

        {isLoading ? (
          <div className="space-y-px">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="px-3 py-2">
                <Skeleton className="h-8 w-full" />
              </div>
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            No audit entries match your filters
          </div>
        ) : (
          <div
            ref={parentRef}
            style={{ height: 600, overflowY: 'auto' }}
          >
            <div
              style={{
                height: virtualizer.getTotalSize(),
                width: '100%',
                position: 'relative',
              }}
            >
              {virtualItems.map((virtualRow) => {
                const isSentinel = virtualRow.index >= rows.length

                return (
                  <div
                    key={virtualRow.key}
                    data-index={virtualRow.index}
                    ref={virtualizer.measureElement}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    {isSentinel ? (
                      <div className="px-3 py-2 text-xs text-muted-foreground text-center">
                        {isFetchingNextPage ? 'Loading more…' : ''}
                      </div>
                    ) : (
                      <AuditRow entry={rows[virtualRow.index]} />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  const hasExpandable =
    entry.action === 'config_change' && entry.detail !== null

  return (
    <div className="border-b last:border-b-0 px-3 py-2 hover:bg-muted/30 transition-colors">
      <div className="grid grid-cols-[140px_1fr_1fr_1fr_100px] items-start gap-x-2 text-sm">
        <div className="text-xs text-muted-foreground font-mono leading-5">
          {format(new Date(entry.created_at), 'MMM d, yyyy HH:mm:ss')}
        </div>
        <div className="truncate leading-5" title={entry.actor_email ?? undefined}>
          {entry.actor_email ?? (
            <span className="text-muted-foreground italic">System</span>
          )}
        </div>
        <div className="font-mono text-xs leading-5 truncate">{entry.action}</div>
        <div className="text-xs text-muted-foreground leading-5 truncate">
          {entry.resource_type}
          {entry.resource_id ? (
            <span className="text-foreground">/{entry.resource_id}</span>
          ) : null}
        </div>
        <div className="font-mono text-xs text-muted-foreground leading-5 truncate">
          {entry.ip_address ?? '—'}
        </div>
      </div>
      {hasExpandable && <JsonDiffRow entry={entry} />}
    </div>
  )
}
