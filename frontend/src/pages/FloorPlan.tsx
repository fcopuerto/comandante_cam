import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import {
  Building2,
  Camera,
  ChevronDown,
  ChevronRight,
  ImagePlus,
  Layers,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useToast } from '@/components/ui/use-toast'
import { useCameras } from '@/api/cameras'
import {
  floorImageUrl,
  useBuildings,
  useCreateBuilding,
  useCreateFloor,
  useCreatePlacement,
  useDeleteBuilding,
  useDeleteFloor,
  useDeletePlacement,
  useFloors,
  usePlacements,
  useUpdateBuilding,
  useUpdateFloor,
  useUpdatePlacement,
  useUploadFloorImage,
} from '@/api/floor_plan'
import api from '@/lib/api'
import type { Building, Camera as CameraType, CameraPlacement, Floor } from '@/types'
import CameraPlayer from '@/components/live/CameraPlayer'

// ── Status color helpers ──────────────────────────────────────────────────────

function statusColor(status: string): string {
  switch (status) {
    case 'recording': return '#22c55e'
    case 'online': return '#3b82f6'
    case 'offline': return '#ef4444'
    case 'error': return '#dc2626'
    case 'unauthorized': return '#eab308'
    default: return '#9ca3af'
  }
}

function statusRing(status: string): string {
  switch (status) {
    case 'recording': return 'ring-green-500'
    case 'online': return 'ring-blue-500'
    case 'offline': return 'ring-red-500'
    case 'error': return 'ring-red-600'
    case 'unauthorized': return 'ring-yellow-500'
    default: return 'ring-gray-400'
  }
}

// ── Building/Floor tree ───────────────────────────────────────────────────────

interface TreeProps {
  selectedFloorId: string | null
  onSelectFloor: (floorId: string, buildingId: string) => void
}

function BuildingTree({ selectedFloorId, onSelectFloor }: TreeProps) {
  const { data: buildings = [], isLoading } = useBuildings()
  const { mutateAsync: createBuilding } = useCreateBuilding()
  const { mutateAsync: deleteBuilding } = useDeleteBuilding()
  const { mutateAsync: updateBuilding } = useUpdateBuilding()
  const { toast } = useToast()

  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [showAddBuilding, setShowAddBuilding] = useState(false)
  const [editBuilding, setEditBuilding] = useState<Building | null>(null)
  const [newBuildingName, setNewBuildingName] = useState('')

  const toggle = (id: string) => setExpanded((p) => ({ ...p, [id]: !p[id] }))

  const handleAddBuilding = async () => {
    if (!newBuildingName.trim()) return
    try {
      const b = await createBuilding({ name: newBuildingName.trim() })
      setExpanded((p) => ({ ...p, [b.id]: true }))
      setShowAddBuilding(false)
      setNewBuildingName('')
    } catch {
      toast({ title: 'Error creating building', variant: 'destructive' })
    }
  }

  const handleUpdateBuilding = async () => {
    if (!editBuilding || !newBuildingName.trim()) return
    try {
      await updateBuilding({ id: editBuilding.id, name: newBuildingName.trim() })
      setEditBuilding(null)
      setNewBuildingName('')
    } catch {
      toast({ title: 'Error updating building', variant: 'destructive' })
    }
  }

  const handleDeleteBuilding = async (b: Building) => {
    if (!confirm(`Delete building "${b.name}" and all its floors?`)) return
    try {
      await deleteBuilding(b.id)
    } catch {
      toast({ title: 'Error deleting building', variant: 'destructive' })
    }
  }

  if (isLoading) return <div className="p-4 space-y-2"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /></div>

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <span className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Buildings</span>
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setNewBuildingName(''); setShowAddBuilding(true) }}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {buildings.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-8">No buildings yet.<br />Add one to get started.</p>
        )}
        {buildings.map((b) => (
          <BuildingItem
            key={b.id}
            building={b}
            expanded={!!expanded[b.id]}
            onToggle={() => toggle(b.id)}
            onEdit={() => { setEditBuilding(b); setNewBuildingName(b.name); }}
            onDelete={() => handleDeleteBuilding(b)}
            selectedFloorId={selectedFloorId}
            onSelectFloor={onSelectFloor}
          />
        ))}
      </div>

      {/* Add building dialog */}
      <Dialog open={showAddBuilding} onOpenChange={setShowAddBuilding}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Add Building</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input
              value={newBuildingName}
              onChange={(e) => setNewBuildingName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAddBuilding()}
              placeholder="e.g. Main Office"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddBuilding(false)}>Cancel</Button>
            <Button onClick={handleAddBuilding} disabled={!newBuildingName.trim()}>Add</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit building dialog */}
      <Dialog open={!!editBuilding} onOpenChange={(o) => !o && setEditBuilding(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Rename Building</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input
              value={newBuildingName}
              onChange={(e) => setNewBuildingName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleUpdateBuilding()}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditBuilding(null)}>Cancel</Button>
            <Button onClick={handleUpdateBuilding} disabled={!newBuildingName.trim()}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

interface BuildingItemProps {
  building: Building
  expanded: boolean
  onToggle: () => void
  onEdit: () => void
  onDelete: () => void
  selectedFloorId: string | null
  onSelectFloor: (floorId: string, buildingId: string) => void
}

function BuildingItem({ building, expanded, onToggle, onEdit, onDelete, selectedFloorId, onSelectFloor }: BuildingItemProps) {
  const { data: floors = [] } = useFloors(expanded ? building.id : null)
  const { mutateAsync: createFloor } = useCreateFloor()
  const { mutateAsync: deleteFloor } = useDeleteFloor()
  const { mutateAsync: updateFloor } = useUpdateFloor()
  const { toast } = useToast()

  const [showAddFloor, setShowAddFloor] = useState(false)
  const [editFloor, setEditFloor] = useState<Floor | null>(null)
  const [floorName, setFloorName] = useState('')
  const [floorLevel, setFloorLevel] = useState(0)

  const handleAddFloor = async () => {
    if (!floorName.trim()) return
    try {
      const f = await createFloor({ buildingId: building.id, name: floorName.trim(), level: floorLevel })
      onSelectFloor(f.id, building.id)
      setShowAddFloor(false)
      setFloorName('')
      setFloorLevel(0)
    } catch {
      toast({ title: 'Error creating floor', variant: 'destructive' })
    }
  }

  const handleUpdateFloor = async () => {
    if (!editFloor || !floorName.trim()) return
    try {
      await updateFloor({ id: editFloor.id, buildingId: building.id, name: floorName.trim(), level: floorLevel })
      setEditFloor(null)
    } catch {
      toast({ title: 'Error updating floor', variant: 'destructive' })
    }
  }

  const handleDeleteFloor = async (f: Floor) => {
    if (!confirm(`Delete floor "${f.name}"?`)) return
    try {
      await deleteFloor({ id: f.id, buildingId: building.id })
    } catch {
      toast({ title: 'Error deleting floor', variant: 'destructive' })
    }
  }

  return (
    <div>
      <div className="flex items-center gap-1 rounded-md hover:bg-accent group px-1 py-1">
        <button className="flex items-center gap-1.5 flex-1 text-left text-sm font-medium" onClick={onToggle}>
          {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
          <Building2 className="h-3.5 w-3.5 shrink-0 text-primary" />
          <span className="truncate">{building.name}</span>
          <Badge variant="outline" className="ml-auto text-xs h-4 px-1">{building.floor_count}</Badge>
        </button>
        <div className="hidden group-hover:flex items-center gap-0.5">
          <Button size="icon" variant="ghost" className="h-5 w-5" onClick={onEdit}><Pencil className="h-3 w-3" /></Button>
          <Button size="icon" variant="ghost" className="h-5 w-5 text-destructive" onClick={onDelete}><Trash2 className="h-3 w-3" /></Button>
        </div>
      </div>

      {expanded && (
        <div className="ml-4 border-l pl-2 space-y-0.5 mt-0.5">
          {floors.map((f) => (
            <div
              key={f.id}
              className={`flex items-center gap-1 rounded-md px-2 py-1 cursor-pointer group text-sm ${selectedFloorId === f.id ? 'bg-primary text-primary-foreground' : 'hover:bg-accent text-muted-foreground'}`}
              onClick={() => onSelectFloor(f.id, building.id)}
            >
              <Layers className="h-3.5 w-3.5 shrink-0" />
              <span className="flex-1 truncate">{f.name}</span>
              <span className="text-xs opacity-60">{f.level >= 0 ? `L${f.level}` : `B${Math.abs(f.level)}`}</span>
              {f.has_image && <span className="text-xs opacity-60">🗺</span>}
              <div className={`hidden group-hover:flex items-center gap-0.5 ${selectedFloorId === f.id ? 'text-primary-foreground' : ''}`}>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-5 w-5"
                  onClick={(e) => { e.stopPropagation(); setEditFloor(f); setFloorName(f.name); setFloorLevel(f.level) }}
                >
                  <Pencil className="h-3 w-3" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-5 w-5 text-destructive"
                  onClick={(e) => { e.stopPropagation(); handleDeleteFloor(f) }}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </div>
          ))}
          <button
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1 w-full rounded-md hover:bg-accent"
            onClick={() => { setFloorName(''); setFloorLevel(floors.length); setShowAddFloor(true) }}
          >
            <Plus className="h-3 w-3" /> Add floor
          </button>
        </div>
      )}

      <FloorFormDialog
        open={showAddFloor}
        title="Add Floor"
        name={floorName}
        level={floorLevel}
        onNameChange={setFloorName}
        onLevelChange={setFloorLevel}
        onConfirm={handleAddFloor}
        onCancel={() => setShowAddFloor(false)}
      />
      <FloorFormDialog
        open={!!editFloor}
        title="Edit Floor"
        name={floorName}
        level={floorLevel}
        onNameChange={setFloorName}
        onLevelChange={setFloorLevel}
        onConfirm={handleUpdateFloor}
        onCancel={() => setEditFloor(null)}
      />
    </div>
  )
}

interface FloorFormDialogProps {
  open: boolean
  title: string
  name: string
  level: number
  onNameChange: (v: string) => void
  onLevelChange: (v: number) => void
  onConfirm: () => void
  onCancel: () => void
}

function FloorFormDialog({ open, title, name, level, onNameChange, onLevelChange, onConfirm, onCancel }: FloorFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Floor Name</Label>
            <Input value={name} onChange={(e) => onNameChange(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && onConfirm()} placeholder="e.g. Ground Floor" autoFocus />
          </div>
          <div>
            <Label>Level (0 = ground, −1 = basement, 1 = first floor…)</Label>
            <Input type="number" value={level} onChange={(e) => onLevelChange(parseInt(e.target.value) || 0)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
          <Button onClick={onConfirm} disabled={!name.trim()}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Camera list (unplaced) ────────────────────────────────────────────────────

interface CameraListProps {
  placedCameraIds: Set<string>
  onPlace: (camera: CameraType) => void
}

function UnplacedCameraList({ placedCameraIds, onPlace }: CameraListProps) {
  const { data: camerasPage, isLoading } = useCameras({ page_size: 100 })
  const cameras = camerasPage?.items ?? []
  const [search, setSearch] = useState('')

  const unplaced = cameras.filter(
    (c) => !placedCameraIds.has(c.id) && c.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b">
        <span className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Cameras</span>
        <p className="text-xs text-muted-foreground mt-0.5">Click to place on floor</p>
      </div>
      <div className="px-3 py-2 border-b">
        <Input
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-7 text-xs"
        />
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading && <Skeleton className="h-8 w-full" />}
        {!isLoading && unplaced.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-6">
            {cameras.length === 0 ? 'No cameras found.' : 'All cameras are placed.'}
          </p>
        )}
        {unplaced.map((cam) => (
          <button
            key={cam.id}
            className="flex items-center gap-2 w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent transition-colors"
            onClick={() => onPlace(cam)}
          >
            <span
              className="h-2.5 w-2.5 rounded-full shrink-0"
              style={{ backgroundColor: statusColor(cam.status) }}
            />
            <span className="flex-1 truncate font-medium">{cam.name}</span>
            <Plus className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Floor canvas ──────────────────────────────────────────────────────────────

interface CanvasProps {
  floorId: string
  placements: CameraPlacement[]
  onDeletePlacement: (id: string) => void
  onUpdatePlacement: (id: string, x: number, y: number) => void
  onClickCamera: (placement: CameraPlacement) => void
}

function FloorCanvas({
  floorId,
  placements,
  onDeletePlacement,
  onUpdatePlacement,
  onClickCamera,
}: CanvasProps) {
  const { mutateAsync: uploadImage } = useUploadFloorImage()
  const { toast } = useToast()

  const [zoom, setZoom] = useState(1)
  const [imageTs, setImageTs] = useState(Date.now())
  const containerRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const draggingRef = useRef<{ placementId: string; startX: number; startY: number; origX: number; origY: number } | null>(null)
  const [dragPos, setDragPos] = useState<Record<string, { x: number; y: number }>>({})
  const [currentFloor, setCurrentFloor] = useState<Floor | null>(null)

  useEffect(() => {
    if (!floorId) return
    api.get(`/floor-plan/floors/${floorId}`).then((r) => setCurrentFloor(r.data))
  }, [floorId, imageTs])

  const handleUpload = async (file: File) => {
    if (!currentFloor) return
    try {
      await uploadImage({ floorId, buildingId: currentFloor.building_id, file })
      setImageTs(Date.now())
      toast({ title: 'Floor plan uploaded' })
    } catch {
      toast({ title: 'Upload failed', variant: 'destructive' })
    }
  }

  const getRelativePos = (e: React.PointerEvent): { x: number; y: number } | null => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return null
    return {
      x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)),
    }
  }

  const onPointerDown = (e: React.PointerEvent, placementId: string, origX: number, origY: number) => {
    e.preventDefault()
    e.stopPropagation()
    const pos = getRelativePos(e)
    if (!pos) return
    draggingRef.current = { placementId, startX: pos.x, startY: pos.y, origX, origY }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!draggingRef.current) return
    const pos = getRelativePos(e)
    if (!pos) return
    const { placementId, startX, startY, origX, origY } = draggingRef.current
    const dx = pos.x - startX
    const dy = pos.y - startY
    setDragPos((prev) => ({
      ...prev,
      [placementId]: {
        x: Math.max(0.02, Math.min(0.98, origX + dx)),
        y: Math.max(0.02, Math.min(0.98, origY + dy)),
      },
    }))
  }

  const onPointerUp = (_e: React.PointerEvent) => {
    if (!draggingRef.current) return
    const { placementId } = draggingRef.current
    draggingRef.current = null
    const pos = dragPos[placementId]
    if (pos) {
      onUpdatePlacement(placementId, pos.x, pos.y)
    }
  }

  const imageUrl = currentFloor?.has_image ? `${floorImageUrl(floorId)}?t=${imageTs}` : null

  return (
    <div className="flex flex-col h-full bg-muted/30">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b bg-card">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="icon" variant="outline" className="h-7 w-7" onClick={() => setZoom((z) => Math.min(3, z + 0.25))}>
                <ZoomIn className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Zoom in</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="icon" variant="outline" className="h-7 w-7" onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}>
                <ZoomOut className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Zoom out</TooltipContent>
          </Tooltip>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setZoom(1)}>
            <RotateCcw className="h-3 w-3 mr-1" />{Math.round(zoom * 100)}%
          </Button>
          <div className="ml-auto">
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => fileInputRef.current?.click()}>
              <ImagePlus className="h-3.5 w-3.5 mr-1" />
              {imageUrl ? 'Replace image' : 'Upload floor plan'}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); e.target.value = '' }}
            />
          </div>
        </TooltipProvider>
      </div>

      {/* Canvas area */}
      <div className="flex-1 overflow-auto p-4">
        <div
          ref={containerRef}
          className="relative mx-auto border rounded-lg overflow-hidden bg-white shadow-sm"
          style={{
            width: `${100 * zoom}%`,
            maxWidth: `${1200 * zoom}px`,
            aspectRatio: '16/9',
          }}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          {imageUrl ? (
            <img
              src={imageUrl}
              alt="Floor plan"
              className="absolute inset-0 w-full h-full object-cover select-none pointer-events-none"
              draggable={false}
            />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground gap-3">
              <ImagePlus className="h-12 w-12 opacity-30" />
              <p className="text-sm">Upload a floor plan image to get started</p>
              <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()}>
                <ImagePlus className="h-4 w-4 mr-1.5" /> Upload Image
              </Button>
            </div>
          )}

          {/* Camera icons */}
          {placements.map((p) => {
            const pos = dragPos[p.id] ?? { x: p.x, y: p.y }
            const color = statusColor(p.camera.status)
            const ring = statusRing(p.camera.status)
            return (
              <CameraIcon
                key={p.id}
                placement={p}
                x={pos.x}
                y={pos.y}
                color={color}
                ringClass={ring}
                onPointerDown={(e) => onPointerDown(e, p.id, pos.x, pos.y)}
                onClick={() => onClickCamera(p)}
                onDelete={() => onDeletePlacement(p.id)}
              />
            )
          })}
        </div>
      </div>
    </div>
  )
}

interface CameraIconProps {
  placement: CameraPlacement
  x: number
  y: number
  color: string
  ringClass: string
  onPointerDown: (e: React.PointerEvent) => void
  onClick: () => void
  onDelete: () => void
}

function CameraIcon({ placement, x, y, color, ringClass, onPointerDown, onClick, onDelete }: CameraIconProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <div
      className="absolute -translate-x-1/2 -translate-y-1/2 group"
      style={{ left: `${x * 100}%`, top: `${y * 100}%`, zIndex: hovered ? 20 : 10 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Camera icon button */}
      <button
        className={`flex items-center justify-center w-9 h-9 rounded-full bg-white shadow-md ring-2 ${ringClass} cursor-grab active:cursor-grabbing transition-transform hover:scale-110`}
        style={{ touchAction: 'none' }}
        onPointerDown={onPointerDown}
        onClick={(e) => { e.stopPropagation(); onClick() }}
        title={placement.camera.name}
      >
        <Camera className="h-4 w-4" style={{ color }} />
      </button>

      {/* Status dot */}
      <span
        className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-1 ring-white"
        style={{ backgroundColor: color }}
      />

      {/* Delete button */}
      {hovered && (
        <button
          className="absolute -top-2 -right-2 h-4 w-4 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center shadow hover:bg-red-700"
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <X className="h-2.5 w-2.5" />
        </button>
      )}

      {/* Tooltip label */}
      {hovered && (
        <div className="absolute -bottom-7 left-1/2 -translate-x-1/2 bg-black/75 text-white text-xs rounded px-1.5 py-0.5 whitespace-nowrap pointer-events-none">
          {placement.camera.name}
        </div>
      )}
    </div>
  )
}

// ── Live view popup ───────────────────────────────────────────────────────────

interface LivePopupProps {
  placement: CameraPlacement | null
  onClose: () => void
}

function LiveViewPopup({ placement, onClose }: LivePopupProps) {
  return (
    <Dialog open={!!placement} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl p-0 overflow-hidden">
        <DialogHeader className="px-4 py-3 border-b">
          <DialogTitle className="flex items-center gap-2">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: placement ? statusColor(placement.camera.status) : '#9ca3af' }}
            />
            {placement?.camera.name}
            {placement?.camera.location && (
              <span className="text-muted-foreground text-sm font-normal">— {placement.camera.location}</span>
            )}
          </DialogTitle>
        </DialogHeader>
        {placement && (
          <div className="aspect-video">
            <CameraPlayer
              cameraId={placement.camera_id}
              label={placement.camera.name}
              location={placement.camera.location}
              className="w-full h-full"
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-4">
      <Building2 className="h-16 w-16 opacity-20" />
      <div className="text-center">
        <p className="font-medium">Select a floor to start</p>
        <p className="text-sm mt-1">Add a building and floor using the panel on the left,<br />then upload a floor plan image and place your cameras.</p>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FloorPlanPage() {
  const [selectedFloorId, setSelectedFloorId] = useState<string | null>(null)
  const [selectedBuildingId, setSelectedBuildingId] = useState<string | null>(null)
  const [livePopup, setLivePopup] = useState<CameraPlacement | null>(null)
  const { toast } = useToast()

  const { data: placements = [] } = usePlacements(selectedFloorId)
  const { mutateAsync: createPlacement } = useCreatePlacement()
  const { mutateAsync: updatePlacement } = useUpdatePlacement()
  const { mutateAsync: deletePlacement } = useDeletePlacement()

  const placedIds = new Set(placements.map((p) => p.camera_id))

  const handleSelectFloor = (floorId: string, buildingId: string) => {
    setSelectedFloorId(floorId)
    setSelectedBuildingId(buildingId)
  }

  const handlePlaceCamera = useCallback(
    async (cam: CameraType) => {
      if (!selectedFloorId) return
      try {
        await createPlacement({ floorId: selectedFloorId, cameraId: cam.id, x: 0.5, y: 0.5, rotation: 0 })
      } catch (err: unknown) {
        const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Error placing camera'
        toast({ title: msg, variant: 'destructive' })
      }
    },
    [selectedFloorId, createPlacement, toast]
  )

  const handleUpdatePlacement = useCallback(
    async (id: string, x: number, y: number) => {
      if (!selectedFloorId) return
      try {
        await updatePlacement({ id, floorId: selectedFloorId, x, y })
      } catch {
        toast({ title: 'Error saving position', variant: 'destructive' })
      }
    },
    [selectedFloorId, updatePlacement, toast]
  )

  const handleDeletePlacement = useCallback(
    async (id: string) => {
      if (!selectedFloorId) return
      try {
        await deletePlacement({ id, floorId: selectedFloorId })
      } catch {
        toast({ title: 'Error removing camera', variant: 'destructive' })
      }
    },
    [selectedFloorId, deletePlacement, toast]
  )

  return (
    <TooltipProvider>
      <div className="flex h-[calc(100vh-8rem)] -m-6 overflow-hidden">
        {/* Left: building tree */}
        <aside className="w-60 border-r bg-card flex flex-col shrink-0">
          <BuildingTree selectedFloorId={selectedFloorId} onSelectFloor={handleSelectFloor} />
        </aside>

        {/* Center: canvas */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {selectedFloorId && selectedBuildingId ? (
            <FloorCanvas
              floorId={selectedFloorId}
              placements={placements}
              onDeletePlacement={handleDeletePlacement}
              onUpdatePlacement={handleUpdatePlacement}
              onClickCamera={setLivePopup}
            />
          ) : (
            <EmptyState />
          )}
        </div>

        {/* Right: unplaced cameras */}
        <aside className="w-52 border-l bg-card flex flex-col shrink-0">
          {selectedFloorId ? (
            <UnplacedCameraList placedCameraIds={placedIds} onPlace={handlePlaceCamera} />
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-xs text-center px-3">
              Select a floor to manage camera placements
            </div>
          )}
        </aside>
      </div>

      <LiveViewPopup placement={livePopup} onClose={() => setLivePopup(null)} />
    </TooltipProvider>
  )
}
