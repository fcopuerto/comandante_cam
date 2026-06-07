import { useCallback } from 'react'
import {
  DndContext, DragEndEvent, DragOverlay,
  PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import { useDraggable, useDroppable } from '@dnd-kit/core'
import { Plus } from 'lucide-react'
import { cn } from '@/lib/utils'
import CameraPlayer from '@/components/live/CameraPlayer'
import type { CameraSlot } from '@/types'

type Layout = 1 | 4 | 9 | 16

interface Props {
  layout: Layout
  cells: CameraSlot[]
  alertCounts?: Record<string, number>
  onCellClick?: (slotId: string) => void
  onSwap?: (fromId: string, toId: string) => void
  onFullscreen?: (cameraId: string) => void
}

const GRID_COLS: Record<Layout, string> = {
  1: 'grid-cols-1',
  4: 'grid-cols-2',
  9: 'grid-cols-3',
  16: 'grid-cols-4',
}

function DroppableCell({
  slot, alertCount, onCellClick, onFullscreen,
}: {
  slot: CameraSlot
  alertCount: number
  onCellClick?: (id: string) => void
  onFullscreen?: (cameraId: string) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: slot.id })

  if (!slot.cameraId) {
    return (
      <div
        ref={setNodeRef}
        className={cn(
          'aspect-video border-2 border-dashed border-muted-foreground/30 rounded-md flex items-center justify-center cursor-pointer hover:border-primary/50 hover:bg-muted/20 transition-colors',
          isOver && 'border-primary bg-primary/5'
        )}
        onClick={() => onCellClick?.(slot.id)}
      >
        <div className="flex flex-col items-center gap-1 text-muted-foreground/50">
          <Plus className="h-6 w-6" />
          <span className="text-xs">Add camera</span>
        </div>
      </div>
    )
  }

  return (
    <DraggableCell slotId={slot.id} isOver={isOver} dropRef={setNodeRef}>
      <CameraPlayer
        cameraId={slot.cameraId}
        label={slot.cameraName ?? slot.cameraId}
        alertCount={alertCount}
        className="aspect-video w-full"
        onFullscreen={onFullscreen ? () => onFullscreen(slot.cameraId!) : undefined}
      />
    </DraggableCell>
  )
}

function DraggableCell({
  slotId, isOver, dropRef, children,
}: {
  slotId: string
  isOver: boolean
  dropRef: (node: HTMLElement | null) => void
  children: React.ReactNode
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: slotId })

  const ref = useCallback((node: HTMLElement | null) => {
    setNodeRef(node)
    dropRef(node)
  }, [setNodeRef, dropRef])

  return (
    <div
      ref={ref}
      className={cn(
        'relative rounded-md touch-none',
        isDragging && 'opacity-40',
        isOver && 'ring-2 ring-primary'
      )}
      {...listeners}
      {...attributes}
    >
      {children}
    </div>
  )
}

export default function CameraGrid({ layout, cells, alertCounts = {}, onCellClick, onSwap, onFullscreen }: Props) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }))

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (over && active.id !== over.id) {
      onSwap?.(String(active.id), String(over.id))
    }
  }

  const paddedCells = [...cells]
  while (paddedCells.length < layout) {
    paddedCells.push({ id: `empty-${paddedCells.length}`, cameraId: null })
  }

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div className={cn('grid gap-1', GRID_COLS[layout])}>
        {paddedCells.slice(0, layout).map((slot) => (
          <DroppableCell
            key={slot.id}
            slot={slot}
            alertCount={slot.cameraId ? (alertCounts[slot.cameraId] ?? 0) : 0}
            onCellClick={onCellClick}
            onFullscreen={onFullscreen}
          />
        ))}
      </div>
      <DragOverlay />
    </DndContext>
  )
}
