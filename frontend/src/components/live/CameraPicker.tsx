import { useState } from 'react'
import { Search, ChevronLeft, ChevronRight, Check, Wifi, WifiOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useCameras } from '@/api/cameras'
import type { Camera } from '@/types'

interface Props {
  activeCameraIds: Set<string>
  onAdd: (camera: Camera) => void
  onRemove: (cameraId: string) => void
}

export default function CameraPicker({ activeCameraIds, onAdd, onRemove }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [search, setSearch] = useState('')
  const [onlineOnly, setOnlineOnly] = useState(false)

  const { data, isLoading } = useCameras({ page_size: 100 })

  const cameras = (data?.items ?? []).filter((c) => {
    const matchesSearch =
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      (c.zone_location ?? '').toLowerCase().includes(search.toLowerCase())
    const matchesOnline = !onlineOnly || c.status === 'online' || c.status === 'recording'
    return matchesSearch && matchesOnline
  })

  const groups = cameras.reduce<Record<string, Camera[]>>((acc, cam) => {
    const key = 'All cameras'
    if (!acc[key]) acc[key] = []
    acc[key].push(cam)
    return acc
  }, {})

  const handleClick = (cam: Camera) => {
    if (activeCameraIds.has(cam.id)) {
      onRemove(cam.id)
    } else {
      onAdd(cam)
    }
  }

  if (collapsed) {
    return (
      <div className="flex flex-col items-center w-10 border-r bg-card py-2 gap-2">
        <button
          className="p-1 rounded hover:bg-muted"
          onClick={() => setCollapsed(false)}
          aria-label="Expand camera picker"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <div className="w-56 flex flex-col border-r bg-card" data-testid="camera-picker">
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <span className="text-sm font-medium">Cameras</span>
        <button
          className="p-1 rounded hover:bg-muted"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse camera picker"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      <div className="px-3 py-2 space-y-2 border-b">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search cameras…"
            className="pl-7 h-8 text-xs"
          />
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="online-only"
            checked={onlineOnly}
            onCheckedChange={setOnlineOnly}
            className="scale-75"
          />
          <Label htmlFor="online-only" className="text-xs font-normal cursor-pointer">Online only</Label>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {isLoading ? (
          <div className="px-3 space-y-2 py-2">
            {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-9" />)}
          </div>
        ) : (
          Object.entries(groups).map(([groupName, cams]) => (
            <div key={groupName}>
              <div className="px-3 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {groupName}
              </div>
              {cams.map((cam) => {
                const inGrid = activeCameraIds.has(cam.id)
                return (
                  <button
                    key={cam.id}
                    className={cn(
                      'w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors',
                      inGrid && 'bg-muted/30'
                    )}
                    onClick={() => handleClick(cam)}
                  >
                    {cam.status === 'online'
                      ? <Wifi className="h-3.5 w-3.5 text-green-500 shrink-0" />
                      : <WifiOff className="h-3.5 w-3.5 text-muted-foreground shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate">{cam.name}</div>
                      <div className="text-xs text-muted-foreground truncate">{cam.zone_location ?? ''}</div>
                    </div>
                    {inGrid && <Check className="h-3.5 w-3.5 text-primary shrink-0" />}
                  </button>
                )
              })}
            </div>
          ))
        )}
        {!isLoading && cameras.length === 0 && (
          <p className="px-3 py-4 text-xs text-muted-foreground text-center">No cameras found</p>
        )}
      </div>
    </div>
  )
}
