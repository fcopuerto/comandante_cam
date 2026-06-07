import { useState, useEffect, useCallback } from 'react'
import { LayoutGrid, Save, Maximize, Minimize } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import CameraGrid from '@/components/live/CameraGrid'
import CameraPicker from '@/components/live/CameraPicker'
import { useWsStore } from '@/store/wsStore'
import { useCameras } from '@/api/cameras'
import api from '@/lib/api'
import type { Camera, CameraSlot } from '@/types'

type Layout = 1 | 4 | 9 | 16
const LAYOUTS: Layout[] = [1, 4, 9, 16]

function makeSlots(count: number): CameraSlot[] {
  return Array.from({ length: count }, (_, i) => ({ id: String(i), cameraId: null }))
}

export default function LiveView() {
  const [layout, setLayout] = useState<Layout>(4)
  const [cells, setCells] = useState<CameraSlot[]>(makeSlots(4))
  const [alertCounts, setAlertCounts] = useState<Record<string, number>>({})
  const [fullscreenId, setFullscreenId] = useState<string | null>(null)

  const subscribe = useWsStore((s) => s.subscribe)
  const { data: camerasData } = useCameras({ page_size: 100 })

  useEffect(() => {
    const unsubStatus = subscribe('camera_status', (payload) => {
      const p = payload as { camera_id: string; status: string }
      setCells((prev) => [...prev])
      void p
    })
    const unsubAlert = subscribe('alert', (payload) => {
      const p = payload as { camera_id: string }
      setAlertCounts((prev) => ({ ...prev, [p.camera_id]: (prev[p.camera_id] ?? 0) + 1 }))
    })
    return () => { unsubStatus(); unsubAlert() }
  }, [subscribe])

  useEffect(() => {
    setCells(makeSlots(layout))
    setAlertCounts({})
  }, [layout])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFullscreenId(null)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const activeCameraIds = new Set(cells.map((c) => c.cameraId).filter(Boolean) as string[])

  const handleAddCamera = useCallback((camera: Camera) => {
    setCells((prev) => {
      const emptyIdx = prev.findIndex((c) => !c.cameraId)
      if (emptyIdx === -1) return prev
      return prev.map((c, i) => i === emptyIdx ? { ...c, cameraId: camera.id, cameraName: camera.name } : c)
    })
  }, [])

  const handleRemoveCamera = useCallback((cameraId: string) => {
    setCells((prev) => prev.map((c) => c.cameraId === cameraId ? { ...c, cameraId: null } : c))
  }, [])

  const handleSwap = useCallback((fromId: string, toId: string) => {
    setCells((prev) => {
      const next = [...prev]
      const fromIdx = next.findIndex((c) => c.id === fromId)
      const toIdx = next.findIndex((c) => c.id === toId)
      if (fromIdx === -1 || toIdx === -1) return prev
      const fromCam = next[fromIdx].cameraId
      const fromName = next[fromIdx].cameraName
      next[fromIdx] = { ...next[fromIdx], cameraId: next[toIdx].cameraId, cameraName: next[toIdx].cameraName }
      next[toIdx] = { ...next[toIdx], cameraId: fromCam, cameraName: fromName }
      return next
    })
  }, [])

  const handleSaveLayout = async () => {
    try {
      await api.patch('/auth/me', {
        preferences: { live_layout: layout, live_cells: cells },
      })
    } catch {
      // non-critical
    }
  }

  const groups: string[] = []

  const applyGroupPreset = (group: string) => {
    const cams = (camerasData?.items ?? []).filter((c) => c.group_id === group)
    const newCells = makeSlots(layout)
    cams.slice(0, layout).forEach((cam, i) => { newCells[i].cameraId = cam.id; newCells[i].cameraName = cam.name })
    setCells(newCells)
  }

  if (fullscreenId) {
    const slot = cells.find((c) => c.cameraId === fullscreenId)
    if (slot?.cameraId) {
      return (
        <div className="fixed inset-0 bg-black z-50 flex flex-col">
          <div className="flex justify-end p-2">
            <Button variant="ghost" size="icon" className="text-white" onClick={() => setFullscreenId(null)}>
              <Minimize className="h-5 w-5" />
            </Button>
          </div>
          <div className="flex-1 p-2">
            <div className="h-full" />
          </div>
        </div>
      )
    }
  }

  return (
    <div className="flex h-full -m-6 overflow-hidden">
      <CameraPicker
        activeCameraIds={activeCameraIds}
        onAdd={handleAddCamera}
        onRemove={handleRemoveCamera}
      />

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-2 border-b bg-card">
          <LayoutGrid className="h-4 w-4 text-muted-foreground" />
          <div className="flex gap-1">
            {LAYOUTS.map((l) => (
              <Tooltip key={l}>
                <TooltipTrigger asChild>
                  <Button
                    size="sm"
                    variant={layout === l ? 'default' : 'outline'}
                    className="h-7 w-10 text-xs"
                    onClick={() => setLayout(l)}
                  >
                    {l === 1 ? '1×1' : l === 4 ? '2×2' : l === 9 ? '3×3' : '4×4'}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{l} camera{l !== 1 ? 's' : ''}</TooltipContent>
              </Tooltip>
            ))}
          </div>

          {groups.length > 0 && (
            <>
              <div className="h-4 w-px bg-border mx-1" />
              {groups.slice(0, 4).map((g) => (
                <Button key={g} size="sm" variant="ghost" className="h-7 text-xs" onClick={() => applyGroupPreset(g!)}>
                  {g}
                </Button>
              ))}
            </>
          )}

          <div className="ml-auto flex items-center gap-2">
            <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={handleSaveLayout}>
              <Save className="h-3.5 w-3.5" /> Save layout
            </Button>
            <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => setFullscreenId(cells.find((c) => c.cameraId)?.cameraId ?? null)}>
              <Maximize className="h-3.5 w-3.5" /> Fullscreen
            </Button>
          </div>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-auto p-2">
          <CameraGrid
            layout={layout}
            cells={cells}
            alertCounts={alertCounts}
            onSwap={handleSwap}
            onFullscreen={setFullscreenId}
          />
        </div>
      </div>
    </div>
  )
}
