import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel,
  getFilteredRowModel, useReactTable, type SortingState,
} from '@tanstack/react-table'
import { Search, PlusCircle, Scan, MoreHorizontal, ArrowUpDown, CheckSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useCameras, useDiscoverCameras, useSyncTime, useUpdateCamera } from '@/api/cameras'
import type { Camera, DiscoveredCamera } from '@/types'

const colHelper = createColumnHelper<Camera>()

function StatusBadge({ status }: { status: Camera['status'] }) {
  return (
    <Badge variant={status === 'online' ? 'default' : status === 'error' ? 'destructive' : 'secondary'} className="text-xs">
      {status}
    </Badge>
  )
}

function RecordingBadge({ mode }: { mode: Camera['recording_mode'] }) {
  const colors: Record<Camera['recording_mode'], string> = {
    continuous: 'bg-blue-100 text-blue-700',
    motion: 'bg-amber-100 text-amber-700',
    scheduled: 'bg-purple-100 text-purple-700',
    off: 'bg-gray-100 text-gray-500',
  }
  return <span className={`text-xs px-1.5 py-0.5 rounded-full ${colors[mode]}`}>{mode}</span>
}

export default function Cameras() {
  const navigate = useNavigate()
  const [sorting, setSorting] = useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [rowSelection, setRowSelection] = useState<Record<string, boolean>>({})
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [subnet, setSubnet] = useState('')
  const [scanProgress, setScanProgress] = useState(0)

  const { data, isLoading } = useCameras({ page_size: 100 })
  const { mutateAsync: discover, isPending: discovering, data: discovered } = useDiscoverCameras()

  useEffect(() => {
    if (!discovering) { setScanProgress(0); return }
    setScanProgress(0)
    const start = Date.now()
    const SCAN_MS = 5000
    const id = setInterval(() => {
      setScanProgress(Math.min(92, ((Date.now() - start) / SCAN_MS) * 100))
    }, 120)
    return () => clearInterval(id)
  }, [discovering])
  const { mutateAsync: syncTime } = useSyncTime()
  const { mutateAsync: updateCamera } = useUpdateCamera()

  const columns = [
    colHelper.display({
      id: 'select',
      header: ({ table }) => (
        <input
          type="checkbox"
          checked={table.getIsAllRowsSelected()}
          onChange={table.getToggleAllRowsSelectedHandler()}
          className="rounded"
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={row.getIsSelected()}
          onChange={row.getToggleSelectedHandler()}
          className="rounded"
        />
      ),
      size: 40,
    }),
    colHelper.accessor('name', {
      header: ({ column }) => (
        <Button variant="ghost" size="sm" className="h-7 -ml-2" onClick={() => column.toggleSorting()}>
          Name <ArrowUpDown className="ml-1 h-3.5 w-3.5" />
        </Button>
      ),
      cell: (info) => (
        <button
          className="font-medium hover:underline text-left"
          onClick={() => navigate(`/cameras/${info.row.original.id}`)}
        >
          {info.getValue()}
        </button>
      ),
    }),
    colHelper.accessor('zone_location', { header: 'Location', cell: (info) => info.getValue() ?? '—' }),
    colHelper.accessor('status', {
      header: 'Status',
      cell: (info) => <StatusBadge status={info.getValue()} />,
    }),
    colHelper.accessor('recording_mode', {
      header: 'Recording',
      cell: (info) => <RecordingBadge mode={info.getValue()} />,
    }),
    colHelper.accessor('resolution_main', {
      header: 'Resolution',
      cell: (info) => info.getValue() ?? '—',
    }),
    colHelper.accessor('retention_days', {
      header: 'Retention',
      cell: (info) => `${info.getValue()}d`,
    }),
    colHelper.accessor('updated_at', {
      header: 'Last seen',
      cell: (info) => new Date(info.getValue()).toLocaleString(),
    }),
    colHelper.display({
      id: 'actions',
      cell: ({ row }) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => navigate(`/cameras/${row.original.id}`)}>
              View details
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate(`/live?camera=${row.original.id}`)}>
              View live
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => syncTime(row.original.id)}>
              Sync time
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
      size: 48,
    }),
  ]

  const table = useReactTable({
    data: data?.items ?? [],
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

  const selectedIds = Object.keys(rowSelection)
    .filter((k) => rowSelection[k])
    .map((k) => data?.items[Number(k)]?.id)
    .filter(Boolean) as string[]

  const handleBulkMode = async (mode: Camera['recording_mode']) => {
    await Promise.all(selectedIds.map((id) => updateCamera({ id, recording_mode: mode })))
    setRowSelection({})
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Cameras</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setDiscoverOpen(true)}>
            <Scan className="h-4 w-4 mr-1.5" /> Discover
          </Button>
          <Button size="sm" onClick={() => navigate('/cameras/new')}>
            <PlusCircle className="h-4 w-4 mr-1.5" /> Add camera
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder="Search cameras…"
            className="pl-9"
          />
        </div>
        {selectedIds.length > 0 && (
          <div className="flex items-center gap-2 ml-2">
            <CheckSquare className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">{selectedIds.length} selected</span>
            <Button size="sm" variant="outline" onClick={() => handleBulkMode('continuous')}>Enable recording</Button>
            <Button size="sm" variant="outline" onClick={() => handleBulkMode('off')}>Disable recording</Button>
            <Button size="sm" variant="outline" onClick={async () => { await Promise.all(selectedIds.map(id => syncTime(id))); setRowSelection({}) }}>
              Sync time
            </Button>
          </div>
        )}
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead key={h.id} style={{ width: h.getSize() !== 150 ? h.getSize() : undefined }}>
                    {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <TableRow key={i}>
                  {columns.map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-5 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : table.getRowModel().rows.length > 0 ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} data-state={row.getIsSelected() ? 'selected' : undefined}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center py-8 text-muted-foreground">
                  No cameras found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Discover cameras sheet */}
      <Sheet open={discoverOpen} onOpenChange={setDiscoverOpen}>
        <SheetContent className="w-[520px] sm:max-w-[520px]">
          <SheetHeader>
            <SheetTitle>Discover cameras</SheetTitle>
          </SheetHeader>
          <div className="mt-4 space-y-4">
            <div className="flex gap-2">
              <Input
                value={subnet}
                onChange={(e) => setSubnet(e.target.value)}
                placeholder="192.168.1.0/24"
                className="flex-1"
              />
              <Button onClick={() => discover(subnet)} disabled={discovering || !subnet}>
                {discovering ? 'Scanning…' : 'Scan'}
              </Button>
            </div>

            {discovering && (
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Scanning network…</span>
                  <span>{Math.round(scanProgress)}%</span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all duration-150"
                    style={{ width: `${scanProgress}%` }}
                  />
                </div>
                <p className="text-xs text-muted-foreground">WS-Discovery scan in progress — this takes ~5 s</p>
              </div>
            )}

            {!discovering && discovered && discovered.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-4">No cameras found on {subnet}</p>
            )}

            {!discovering && discovered && discovered.length > 0 && (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>IP</TableHead>
                      <TableHead>Manufacturer / Model</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(discovered as DiscoveredCamera[]).map((cam) => (
                      <TableRow key={`${cam.ip}:${cam.port}`}>
                        <TableCell className="font-mono text-xs">{cam.ip}:{cam.port}</TableCell>
                        <TableCell className="text-xs">
                          {[cam.manufacturer, cam.model].filter(Boolean).join(' ') || '—'}
                        </TableCell>
                        <TableCell>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs"
                            onClick={() => { setDiscoverOpen(false); navigate(`/cameras/new?ip=${cam.ip}&port=${cam.port}`) }}
                          >
                            Add
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
