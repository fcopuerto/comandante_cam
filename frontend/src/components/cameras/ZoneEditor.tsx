import { useRef, useEffect, useState, useCallback } from 'react'
import { Plus, Trash2, Save, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { useUpdateCameraZones, useSnapshot } from '@/api/cameras'
import { toast } from '@/components/ui/use-toast'
import type { Zone } from '@/types'

interface Props {
  cameraId: string
  initialZones?: Zone[]
}

type Point = [number, number]

const DEFAULT_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899']

function drawCanvas(
  ctx: CanvasRenderingContext2D,
  zones: Zone[],
  activeIdx: number | null,
  draft: Point[],
  w: number,
  h: number
) {
  ctx.clearRect(0, 0, w, h)

  // Draw completed zones
  zones.forEach((zone, i) => {
    if (zone.polygon.length < 2) return
    const pts = zone.polygon as Point[]
    ctx.beginPath()
    ctx.moveTo(pts[0][0] * w, pts[0][1] * h)
    pts.slice(1).forEach(([x, y]) => ctx.lineTo(x * w, y * h))
    ctx.closePath()
    ctx.fillStyle = zone.color + '33'
    ctx.fill()
    ctx.strokeStyle = i === activeIdx ? '#fff' : zone.color
    ctx.lineWidth = i === activeIdx ? 2 : 1.5
    ctx.stroke()

    // Vertices
    pts.forEach(([x, y]) => {
      ctx.beginPath()
      ctx.arc(x * w, y * h, 5, 0, Math.PI * 2)
      ctx.fillStyle = i === activeIdx ? '#fff' : zone.color
      ctx.fill()
    })

    // Label
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length * w
    const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length * h
    ctx.font = '11px sans-serif'
    ctx.fillStyle = '#fff'
    ctx.textAlign = 'center'
    ctx.fillText(zone.name, cx, cy)
  })

  // Draw draft polygon
  if (draft.length > 0) {
    ctx.beginPath()
    ctx.moveTo(draft[0][0] * w, draft[0][1] * h)
    draft.slice(1).forEach(([x, y]) => ctx.lineTo(x * w, y * h))
    ctx.strokeStyle = '#f59e0b'
    ctx.setLineDash([4, 4])
    ctx.lineWidth = 1.5
    ctx.stroke()
    ctx.setLineDash([])
    draft.forEach(([x, y]) => {
      ctx.beginPath()
      ctx.arc(x * w, y * h, 4, 0, Math.PI * 2)
      ctx.fillStyle = '#f59e0b'
      ctx.fill()
    })
  }
}

export default function ZoneEditor({ cameraId, initialZones = [] }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)

  const [zones, setZones] = useState<Zone[]>(initialZones)
  const [activeIdx, setActiveIdx] = useState<number | null>(null)
  const [draft, setDraft] = useState<Point[]>([])
  const [drawing, setDrawing] = useState(false)

  const { data: snapshot } = useSnapshot(cameraId)
  const { mutateAsync: saveZones, isPending: saving } = useUpdateCameraZones()

  const redraw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    if (imgRef.current?.complete) {
      ctx.drawImage(imgRef.current, 0, 0, canvas.width, canvas.height)
    } else {
      ctx.fillStyle = '#1e293b'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
    }
    drawCanvas(ctx, zones, activeIdx, draft, canvas.width, canvas.height)
  }, [zones, activeIdx, draft])

  useEffect(() => { redraw() }, [redraw])

  useEffect(() => {
    if (!snapshot?.url) return
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => { imgRef.current = img; redraw() }
    img.src = snapshot.url
  }, [snapshot?.url, redraw])

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawing) return
    const canvas = canvasRef.current!
    const rect = canvas.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    setDraft((prev) => [...prev, [x, y]])
  }

  const handleCanvasDblClick = () => {
    if (!drawing || draft.length < 3) return
    const color = DEFAULT_COLORS[zones.length % DEFAULT_COLORS.length]
    setZones((prev) => [
      ...prev,
      {
        name: `Zone ${prev.length + 1}`,
        polygon: draft,
        restricted: false,
        working_hours_start: null,
        working_hours_end: null,
        dwell_threshold_s: null,
        is_privacy_mask: false,
        enabled: true,
        color,
      },
    ])
    setDraft([])
    setDrawing(false)
    setActiveIdx(zones.length)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (activeIdx !== null) {
        setZones((prev) => prev.filter((_, i) => i !== activeIdx))
        setActiveIdx(null)
      } else if (drawing && draft.length > 0) {
        setDraft((prev) => prev.slice(0, -1))
      }
    }
    if (e.key === 'Escape') { setDraft([]); setDrawing(false) }
  }

  const handleSave = async () => {
    try {
      await saveZones({ id: cameraId, zones })
      toast({ title: 'Zones saved' })
    } catch {
      toast({ variant: 'destructive', title: 'Save failed' })
    }
  }

  return (
    <div className="space-y-4" onKeyDown={handleKeyDown} tabIndex={-1}>
      {/* Canvas */}
      <div className="relative rounded-md overflow-hidden border bg-slate-900">
        <canvas
          ref={canvasRef}
          width={640}
          height={360}
          className="w-full cursor-crosshair"
          onClick={handleCanvasClick}
          onDoubleClick={handleCanvasDblClick}
        />
        <div className="absolute top-2 right-2 flex gap-1">
          <Button
            size="sm"
            variant={drawing ? 'default' : 'secondary'}
            className="h-7 text-xs"
            onClick={() => { setDrawing((v) => !v); setDraft([]) }}
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            {drawing ? 'Click to place · Dbl-click to finish · Esc to cancel' : 'Draw zone'}
          </Button>
        </div>
      </div>

      {/* Zone list */}
      <div className="space-y-2">
        {zones.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-4">
            No zones defined. Click "Draw zone" to start.
          </p>
        )}
        {zones.map((zone, i) => (
          <div
            key={i}
            className={`border rounded-md p-3 space-y-3 cursor-pointer transition-colors ${activeIdx === i ? 'border-primary' : 'hover:border-muted-foreground/50'}`}
            onClick={() => setActiveIdx(i === activeIdx ? null : i)}
          >
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={zone.color}
                className="h-5 w-5 rounded cursor-pointer border-0"
                onChange={(e) => setZones((prev) => prev.map((z, j) => j === i ? { ...z, color: e.target.value } : z))}
                onClick={(e) => e.stopPropagation()}
              />
              <Input
                value={zone.name}
                className="h-7 text-sm flex-1"
                onChange={(e) => setZones((prev) => prev.map((z, j) => j === i ? { ...z, name: e.target.value } : z))}
                onClick={(e) => e.stopPropagation()}
              />
              {zone.restricted && <Badge variant="destructive" className="text-xs">Restricted</Badge>}
              {zone.is_privacy_mask && <Badge variant="secondary" className="text-xs">Privacy</Badge>}
              <Button
                size="icon" variant="ghost" className="h-7 w-7 text-muted-foreground hover:text-destructive"
                onClick={(e) => { e.stopPropagation(); setZones((prev) => prev.filter((_, j) => j !== i)); setActiveIdx(null) }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>

            {activeIdx === i && (
              <div className="grid grid-cols-2 gap-3 pt-1" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center gap-2">
                  <Switch
                    id={`restricted-${i}`}
                    checked={zone.restricted}
                    onCheckedChange={(v) => setZones((prev) => prev.map((z, j) => j === i ? { ...z, restricted: v } : z))}
                  />
                  <Label htmlFor={`restricted-${i}`} className="text-xs font-normal">Restricted zone</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Switch
                    id={`privacy-${i}`}
                    checked={zone.is_privacy_mask}
                    onCheckedChange={(v) => setZones((prev) => prev.map((z, j) => j === i ? { ...z, is_privacy_mask: v } : z))}
                  />
                  <Label htmlFor={`privacy-${i}`} className="text-xs font-normal">Privacy mask</Label>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Working hours start</Label>
                  <Input
                    type="time"
                    value={zone.working_hours_start ?? ''}
                    className="h-7 text-xs"
                    onChange={(e) => setZones((prev) => prev.map((z, j) => j === i ? { ...z, working_hours_start: e.target.value || null } : z))}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Working hours end</Label>
                  <Input
                    type="time"
                    value={zone.working_hours_end ?? ''}
                    className="h-7 text-xs"
                    onChange={(e) => setZones((prev) => prev.map((z, j) => j === i ? { ...z, working_hours_end: e.target.value || null } : z))}
                  />
                </div>
                <div className="space-y-1 col-span-2">
                  <Label className="text-xs">Dwell threshold (seconds, blank = none)</Label>
                  <Input
                    type="number"
                    min={0}
                    value={zone.dwell_threshold_s ?? ''}
                    className="h-7 text-xs"
                    placeholder="e.g. 30"
                    onChange={(e) => setZones((prev) => prev.map((z, j) => j === i ? { ...z, dwell_threshold_s: e.target.value ? Number(e.target.value) : null } : z))}
                  />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <Separator />

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving} size="sm">
          {saving ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Save className="h-4 w-4 mr-1.5" />}
          Save zones
        </Button>
      </div>
    </div>
  )
}
