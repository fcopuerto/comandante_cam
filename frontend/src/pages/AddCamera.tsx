import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowLeft, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { useCreateCamera, useTestConnectionData } from '@/api/cameras'
import { usePageTitle } from '@/hooks/usePageTitle'

const schema = z.object({
  name: z.string().min(1, 'Name is required'),
  ip_address: z.string().min(1, 'IP address or hostname is required').regex(/^[a-zA-Z0-9.\-:[\]]+$/, 'Invalid IP address or hostname'),
  onvif_port: z.coerce.number().int().min(1).max(65535, 'Port must be 1–65535'),
  rtsp_main_url: z.string().optional(),
  username: z.string().optional(),
  password: z.string().optional(),
  zone_location: z.string().optional(),
  recording_mode: z.enum(['continuous', 'motion', 'scheduled', 'off']),
  retention_days: z.coerce.number().int().min(1).max(365, 'Must be 1–365 days'),
})

type FormValues = z.infer<typeof schema>

// v2
export default function AddCamera() {
  usePageTitle('Add Camera')
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { toast } = useToast()

  const prefillIp = searchParams.get('ip') ?? ''

  const { register, handleSubmit, watch, setValue, formState: { errors, isDirty } } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      ip_address: prefillIp,
      onvif_port: 80,
      recording_mode: 'continuous',
      retention_days: 30,
    },
  })

  useEffect(() => {
    const handleUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) e.preventDefault()
    }
    window.addEventListener('beforeunload', handleUnload)
    return () => window.removeEventListener('beforeunload', handleUnload)
  }, [isDirty])

  const { mutateAsync: createCamera, isPending: creating } = useCreateCamera()
  const { mutate: testConn, isPending: testing, data: testResult, reset: resetTest } = useTestConnectionData()

  const watchedIp = watch('ip_address')
  const watchedPort = watch('onvif_port')
  const watchedUsername = watch('username')
  const watchedPassword = watch('password')

  const handleTest = () => {
    resetTest()
    testConn({ ip_address: watchedIp, port: watchedPort, username: watchedUsername ?? '', password: watchedPassword ?? '' })
  }

  const onSubmit = async (values: FormValues) => {
    try {
      const cam = await createCamera(values)
      toast({ title: 'Camera added', description: `${values.name} was added successfully.` })
      navigate(`/cameras/${cam.id}`)
    } catch {
      toast({ title: 'Failed to add camera', variant: 'destructive' })
    }
  }

  const canTest = watchedIp && watchedPort

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/cameras')} aria-label="Back to cameras">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold">Add Camera</h1>
          <p className="text-sm text-muted-foreground">Connect a new ONVIF or RTSP camera</p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Connection */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Connection</CardTitle>
            <CardDescription>Network address and ONVIF credentials</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="ip_address">IP Address / Hostname</Label>
                <Input id="ip_address" placeholder="192.168.1.100 or ipvmdemo.dyndns.org" {...register('ip_address')} />
                {errors.ip_address && <p className="text-xs text-destructive">{errors.ip_address.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="onvif_port">Port</Label>
                <Input id="onvif_port" type="number" placeholder="80" {...register('onvif_port')} />
                {errors.onvif_port && <p className="text-xs text-destructive">{errors.onvif_port.message}</p>}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="username">ONVIF Username <span className="text-muted-foreground font-normal">(optional)</span></Label>
                <Input id="username" placeholder="Leave empty for anonymous" autoComplete="off" {...register('username')} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">ONVIF Password <span className="text-muted-foreground font-normal">(optional)</span></Label>
                <Input id="password" type="password" autoComplete="new-password" {...register('password')} />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="rtsp_main_url">RTSP URL <span className="text-muted-foreground font-normal">(optional — skip ONVIF and use this URL directly)</span></Label>
              <Input id="rtsp_main_url" placeholder="rtsp://user:pass@hostname:port/path" {...register('rtsp_main_url')} />
            </div>

            <div className="flex items-center gap-3 pt-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!canTest || testing}
                onClick={handleTest}
              >
                {testing && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
                Test connection
              </Button>
              {testResult && (
                <div className="flex items-center gap-3 text-sm">
                  <span className={`flex items-center gap-1 ${testResult.onvif ? 'text-green-600' : 'text-destructive'}`}>
                    {testResult.onvif ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                    ONVIF
                  </span>
                  <span className={`flex items-center gap-1 ${testResult.rtsp ? 'text-green-600' : 'text-destructive'}`}>
                    {testResult.rtsp ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                    RTSP
                  </span>
                  {testResult.error && <span className="text-destructive text-xs">{testResult.error}</span>}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Identity */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Identity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="name">Camera Name</Label>
              <Input id="name" placeholder="Front entrance" {...register('name')} />
              {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="zone_location">Location <span className="text-muted-foreground font-normal">(optional)</span></Label>
              <Input id="zone_location" placeholder="Building A, Floor 1" {...register('zone_location')} />
            </div>
          </CardContent>
        </Card>

        {/* Recording */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recording</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Recording mode</Label>
                <Select
                  defaultValue="continuous"
                  onValueChange={(v) => setValue('recording_mode', v as FormValues['recording_mode'])}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="continuous">Continuous</SelectItem>
                    <SelectItem value="motion">Motion only</SelectItem>
                    <SelectItem value="scheduled">Scheduled</SelectItem>
                    <SelectItem value="off">Disabled</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="retention_days">Retention (days)</Label>
                <Input id="retention_days" type="number" placeholder="30" {...register('retention_days')} />
                {errors.retention_days && <p className="text-xs text-destructive">{errors.retention_days.message}</p>}
              </div>
            </div>
            <p className="text-xs text-muted-foreground">FPS and PTZ capabilities are detected automatically from the camera via ONVIF.</p>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => navigate('/cameras')}>
            Cancel
          </Button>
          <Button type="submit" disabled={creating}>
            {creating && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
            Add camera
          </Button>
        </div>
      </form>
    </div>
  )
}
