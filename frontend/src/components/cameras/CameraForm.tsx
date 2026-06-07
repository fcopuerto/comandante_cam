import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { useUpdateCamera } from '@/api/cameras'
import { toast } from '@/components/ui/use-toast'
import type { Camera } from '@/types'

const schema = z.object({
  name: z.string().min(1, 'Name is required').max(100),
  description: z.string().optional(),
  zone_location: z.string().optional(),
  ip_address: z.string().regex(/^(\d{1,3}\.){3}\d{1,3}$/, 'Invalid IP address'),
  onvif_port: z.coerce.number().int().min(1).max(65535),
  username: z.string().optional(),
  password: z.string().optional(),
  recording_mode: z.enum(['continuous', 'motion', 'scheduled', 'disabled']),
  fps: z.coerce.number().int().min(1).max(60).optional(),
  bitrate_kbps: z.coerce.number().int().min(100).max(50000).optional(),
  retention_days: z.coerce.number().int().min(1).max(365),
  notes: z.string().optional(),
})

type FormData = z.infer<typeof schema>

interface Props {
  camera: Camera
  onSaved?: (camera: Camera) => void
}

export default function CameraForm({ camera, onSaved }: Props) {
  const {
    register, handleSubmit, setValue, watch, reset,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: camera.name,
      description: camera.description ?? '',
      zone_location: camera.zone_location ?? '',
      ip_address: camera.ip_address,
      onvif_port: camera.onvif_port,
      username: '',
      recording_mode: camera.recording_mode,
      fps: camera.fps ?? undefined,
      bitrate_kbps: camera.bitrate_kbps ?? undefined,
      retention_days: camera.retention_days,
      notes: camera.notes ?? '',
    },
  })

  const { mutateAsync: updateCamera } = useUpdateCamera()

  const onSubmit = async (data: FormData) => {
    try {
      const { username, password, fps, bitrate_kbps, ...rest } = data
      const payload = {
        ...rest,
        ...(username ? { username } : {}),
        ...(password ? { password } : {}),
        ...(fps ? { fps } : {}),
        ...(bitrate_kbps ? { bitrate_kbps } : {}),
      }
      const saved = await updateCamera({ id: camera.id, ...payload })
      reset(data)
      toast({ title: 'Camera updated' })
      onSaved?.(saved)
    } catch {
      toast({ variant: 'destructive', title: 'Save failed' })
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      {/* General */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">General</h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="name">Name *</Label>
            <Input id="name" {...register('name')} />
            {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="zone_location">Location</Label>
            <Input id="zone_location" placeholder="e.g. Building A, Floor 1" {...register('zone_location')} />
          </div>
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor="description">Description</Label>
            <Input id="description" {...register('description')} />
          </div>
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor="notes">Notes</Label>
            <Input id="notes" {...register('notes')} />
          </div>
        </div>
      </div>

      <Separator />

      {/* Connection */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Connection</h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="ip_address">IP Address *</Label>
            <Input id="ip_address" placeholder="192.168.1.100" {...register('ip_address')} />
            {errors.ip_address && <p className="text-xs text-destructive">{errors.ip_address.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="onvif_port">Port</Label>
            <Input id="onvif_port" type="number" {...register('onvif_port')} />
            {errors.onvif_port && <p className="text-xs text-destructive">{errors.onvif_port.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="username">ONVIF Username <span className="text-muted-foreground font-normal">(leave blank to keep)</span></Label>
            <Input id="username" autoComplete="off" {...register('username')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">ONVIF Password <span className="text-muted-foreground font-normal">(leave blank to keep)</span></Label>
            <Input id="password" type="password" autoComplete="new-password" {...register('password')} />
          </div>
        </div>
      </div>

      <Separator />

      {/* Recording */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Recording</h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label>Recording mode</Label>
            <Select
              value={watch('recording_mode')}
              onValueChange={(v) => setValue('recording_mode', v as FormData['recording_mode'], { shouldDirty: true })}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="continuous">Continuous</SelectItem>
                <SelectItem value="motion">Motion</SelectItem>
                <SelectItem value="scheduled">Scheduled</SelectItem>
                <SelectItem value="disabled">Disabled</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="retention_days">Retention (days)</Label>
            <Input id="retention_days" type="number" {...register('retention_days')} />
            {errors.retention_days && <p className="text-xs text-destructive">{errors.retention_days.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fps">FPS override <span className="text-muted-foreground font-normal">(optional)</span></Label>
            <Input id="fps" type="number" {...register('fps')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bitrate_kbps">Bitrate kbps <span className="text-muted-foreground font-normal">(optional)</span></Label>
            <Input id="bitrate_kbps" type="number" {...register('bitrate_kbps')} />
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={() => reset()} disabled={!isDirty}>
          Discard
        </Button>
        <Button type="submit" disabled={isSubmitting || !isDirty}>
          {isSubmitting && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
          Save changes
        </Button>
      </div>
    </form>
  )
}
