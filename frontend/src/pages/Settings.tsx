import { useState } from 'react'
import { ADDONS, useAddonStore } from '@/store/addonStore'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { format } from 'date-fns'
import {
  Mail,
  Webhook,
  MessageSquare,
  Phone,
  Pencil,
  Trash2,
  Plus,
  Copy,
  CheckCircle2,
  XCircle,
  RefreshCw,
  CircleCheck,
  CircleX,
  CircleDot,
  HardDrive,
  Plug,
  Send,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Slider } from '@/components/ui/slider'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { useSettings, useUpdateSettings } from '@/api/settings'
import {
  useNotificationChannels,
  useCreateChannel,
  useUpdateChannel,
  useDeleteChannel,
  useTestChannel,
  type NotificationChannel,
} from '@/api/notifications'
import { useApiKeys, useCreateApiKey, useRevokeApiKey, type ApiKeyCreated } from '@/api/apikeys'
import { useSystemHealth, useDetectionStatus, useRestartDetection, useWorkerStatus, useRestartWorker } from '@/api/system'
import { useStorageTargets, useCreateStorageTarget, useDeleteStorageTarget, useActivateStorageTarget, formatBytes, type StorageTargetCreate } from '@/api/storage'

const ALL_PERMISSIONS = [
  'cameras:read',
  'cameras:write',
  'recordings:read',
  'recordings:export',
  'alerts:read',
  'alerts:write',
  'users:read',
  'system:read',
]

function channelIcon(type: NotificationChannel['type']) {
  switch (type) {
    case 'email': return <Mail className="h-4 w-4" />
    case 'webhook': return <Webhook className="h-4 w-4" />
    case 'slack':
    case 'telegram': return <MessageSquare className="h-4 w-4" />
    case 'sms': return <Phone className="h-4 w-4" />
  }
}

const generalSchema = z.object({
  retention_days_default: z.coerce.number().min(1).max(365),
  max_export_size_gb: z.coerce.number().min(1),
  watermark_exports: z.boolean(),
})
type GeneralFormData = z.infer<typeof generalSchema>

const smtpSchema = z.object({
  smtp_host: z.string().min(1, 'SMTP host is required'),
  smtp_port: z.coerce.number().min(1).max(65535),
  smtp_starttls: z.boolean(),
  smtp_user: z.string(),
  smtp_password: z.string(),
  smtp_from: z.string().email('Must be a valid email'),
})
type SmtpFormData = z.infer<typeof smtpSchema>

function SmtpSection() {
  const { toast } = useToast()
  const { data: settings, isLoading } = useSettings()
  const { mutateAsync: updateSettings, isPending } = useUpdateSettings()
  const [testing, setTesting] = useState(false)
  const [testEmail, setTestEmail] = useState('')

  const { register, handleSubmit, control, getValues, formState: { errors } } = useForm<SmtpFormData>({
    resolver: zodResolver(smtpSchema),
    values: settings
      ? {
          smtp_host: settings.smtp_host ?? '',
          smtp_port: settings.smtp_port ?? 587,
          smtp_starttls: settings.smtp_starttls ?? true,
          smtp_user: settings.smtp_user ?? '',
          smtp_password: settings.smtp_password ?? '',
          smtp_from: settings.smtp_from ?? '',
        }
      : undefined,
  })

  const onSubmit = async (data: SmtpFormData) => {
    try {
      await updateSettings(data)
      toast({ title: 'SMTP settings saved' })
    } catch {
      toast({ title: 'Failed to save SMTP settings', variant: 'destructive' })
    }
  }

  const handleTest = async () => {
    if (!testEmail) {
      toast({ title: 'Enter a test email address', variant: 'destructive' })
      return
    }
    setTesting(true)
    try {
      await import('@/lib/api').then(({ default: api }) =>
        api.post('/system/smtp/test', { to: testEmail })
      )
      toast({ title: 'Test email sent', description: `Check ${testEmail}` })
    } catch (e: any) {
      toast({ title: 'Test failed', description: e?.response?.data?.detail ?? 'Check SMTP settings', variant: 'destructive' })
    } finally {
      setTesting(false)
    }
  }

  if (isLoading) return <Skeleton className="h-48 w-full max-w-md" />

  return (
    <div className="space-y-4 max-w-md">
      <div className="flex items-center gap-2">
        <Mail className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">SMTP / Email</h3>
      </div>
      <p className="text-xs text-muted-foreground">
        Used for invite emails and alert notifications. For Gmail, use an App Password (not your account password).
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2 space-y-1.5">
            <Label>SMTP host</Label>
            <Input placeholder="smtp.gmail.com" {...register('smtp_host')} />
            {errors.smtp_host && <p className="text-xs text-destructive">{errors.smtp_host.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label>Port</Label>
            <Input type="number" {...register('smtp_port')} />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <Label>STARTTLS</Label>
          <Controller
            name="smtp_starttls"
            control={control}
            render={({ field }) => (
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            )}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Username</Label>
          <Input placeholder="you@gmail.com" {...register('smtp_user')} />
        </div>
        <div className="space-y-1.5">
          <Label>Password / App password</Label>
          <Input type="password" placeholder="••••••••••••••••" {...register('smtp_password')} />
        </div>
        <div className="space-y-1.5">
          <Label>From address</Label>
          <Input type="email" placeholder="noreply@example.com" {...register('smtp_from')} />
          {errors.smtp_from && <p className="text-xs text-destructive">{errors.smtp_from.message}</p>}
        </div>
        <Button type="submit" disabled={isPending}>
          {isPending ? 'Saving…' : 'Save SMTP settings'}
        </Button>
      </form>
      <div className="pt-2 border-t space-y-2">
        <Label className="text-xs text-muted-foreground">Send a test email</Label>
        <div className="flex gap-2">
          <Input
            type="email"
            placeholder="recipient@example.com"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            className="flex-1"
          />
          <Button type="button" size="sm" variant="outline" onClick={handleTest} disabled={testing} className="gap-1.5 shrink-0">
            <Send className="h-3.5 w-3.5" />
            {testing ? 'Sending…' : 'Test'}
          </Button>
        </div>
      </div>
    </div>
  )
}

function GeneralTab() {
  const { toast } = useToast()
  const { data: settings, isLoading } = useSettings()
  const { mutateAsync: updateSettings, isPending } = useUpdateSettings()

  const { register, handleSubmit, control, formState: { errors } } = useForm<GeneralFormData>({
    resolver: zodResolver(generalSchema),
    values: settings
      ? {
          retention_days_default: settings.retention_days_default,
          max_export_size_gb: settings.max_export_size_gb,
          watermark_exports: settings.watermark_exports,
        }
      : undefined,
  })

  const onSubmit = async (data: GeneralFormData) => {
    try {
      await updateSettings(data)
      toast({ title: 'Settings saved' })
    } catch {
      toast({ title: 'Failed to save settings', variant: 'destructive' })
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-12" />)}
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 max-w-md">
        <div className="space-y-1.5">
          <Label htmlFor="retention_days">Default retention days</Label>
          <Input
            id="retention_days"
            type="number"
            min={1}
            max={365}
            {...register('retention_days_default')}
          />
          {errors.retention_days_default && (
            <p className="text-xs text-destructive">{errors.retention_days_default.message}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="max_export_size">Max export size (GB)</Label>
          <Input
            id="max_export_size"
            type="number"
            min={1}
            {...register('max_export_size_gb')}
          />
          {errors.max_export_size_gb && (
            <p className="text-xs text-destructive">{errors.max_export_size_gb.message}</p>
          )}
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="watermark_exports">Watermark exports</Label>
          <Controller
            name="watermark_exports"
            control={control}
            render={({ field }) => (
              <Switch
                id="watermark_exports"
                checked={field.value}
                onCheckedChange={field.onChange}
              />
            )}
          />
        </div>
        <Button type="submit" disabled={isPending}>
          {isPending ? 'Saving…' : 'Save changes'}
        </Button>
      </form>

      <Separator />

      <SmtpSection />
    </div>
  )
}

const TARGET_TYPE_LABELS: Record<string, string> = { nfs: 'NFS', smb: 'SMB', local: 'Local' }

function AddTargetDialog({ onClose }: { onClose: () => void }) {
  const { toast } = useToast()
  const { mutateAsync: create, isPending } = useCreateStorageTarget()
  const [form, setForm] = useState<StorageTargetCreate>({
    name: '',
    target_type: 'nfs',
    host: '',
    export_path: '',
    mount_point: '',
    mount_options: '',
  })

  const handleSubmit = async () => {
    if (!form.name || !form.export_path || !form.mount_point) {
      toast({ title: 'Name, export path and mount point are required', variant: 'destructive' })
      return
    }
    try {
      await create({
        ...form,
        host: form.host || undefined,
        mount_options: form.mount_options || undefined,
      })
      toast({ title: 'Storage target added' })
      onClose()
    } catch (e: any) {
      toast({ title: 'Failed to add target', description: e?.response?.data?.detail, variant: 'destructive' })
    }
  }

  const f = (k: keyof StorageTargetCreate) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }))

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add storage target</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input placeholder="Primary NAS" value={form.name} onChange={f('name')} />
          </div>
          <div className="space-y-1.5">
            <Label>Type</Label>
            <div className="flex gap-2">
              {(['nfs', 'smb', 'local'] as const).map((t) => (
                <Button
                  key={t}
                  size="sm"
                  variant={form.target_type === t ? 'default' : 'outline'}
                  onClick={() => setForm((p) => ({ ...p, target_type: t }))}
                >
                  {TARGET_TYPE_LABELS[t]}
                </Button>
              ))}
            </div>
          </div>
          {form.target_type !== 'local' && (
            <div className="space-y-1.5">
              <Label>Host / IP</Label>
              <Input placeholder="192.168.1.232" value={form.host} onChange={f('host')} />
            </div>
          )}
          <div className="space-y-1.5">
            <Label>{form.target_type === 'local' ? 'Source path' : 'Export path'}</Label>
            <Input placeholder="/data" value={form.export_path} onChange={f('export_path')} />
          </div>
          <div className="space-y-1.5">
            <Label>Mount point</Label>
            <Input placeholder="/data" value={form.mount_point} onChange={f('mount_point')} />
          </div>
          <div className="space-y-1.5">
            <Label>Mount options <span className="text-muted-foreground">(optional)</span></Label>
            <Input
              placeholder={form.target_type === 'nfs' ? 'rw,async,hard,intr' : form.target_type === 'smb' ? 'vers=3.0,credentials=/etc/samba/creds' : ''}
              value={form.mount_options}
              onChange={f('mount_options')}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending ? 'Adding…' : 'Add target'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function StorageTargetCard({ target }: { target: ReturnType<typeof useStorageTargets>['data'] extends (infer T)[] | undefined ? T : never }) {
  const { toast } = useToast()
  const { mutateAsync: activate, isPending: activating } = useActivateStorageTarget()
  const { mutateAsync: remove, isPending: removing } = useDeleteStorageTarget()
  const [showFstab, setShowFstab] = useState(false)

  const handleActivate = async () => {
    try {
      await activate(target.id)
      toast({ title: `"${target.name}" is now the active recording target` })
    } catch (e: any) {
      toast({ title: 'Cannot activate', description: e?.response?.data?.detail, variant: 'destructive' })
    }
  }

  const handleDelete = async () => {
    try {
      await remove(target.id)
      toast({ title: 'Storage target removed' })
    } catch (e: any) {
      toast({ title: 'Cannot remove', description: e?.response?.data?.detail, variant: 'destructive' })
    }
  }

  const usePct = target.usage_percent ?? 0
  const barColor = usePct >= 90 ? 'bg-destructive' : usePct >= 75 ? 'bg-amber-500' : 'bg-green-500'

  return (
    <div className={`rounded-lg border p-4 space-y-3 ${target.is_active ? 'border-primary' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <HardDrive className="h-4 w-4 text-muted-foreground shrink-0" />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium truncate">{target.name}</span>
              <Badge variant="outline" className="text-xs shrink-0">{TARGET_TYPE_LABELS[target.target_type]}</Badge>
              {target.is_active && <Badge className="text-xs shrink-0 bg-primary">Active</Badge>}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 truncate">
              {target.host ? `${target.host}:${target.export_path}` : target.export_path} → {target.mount_point}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {target.mounted ? (
            <Badge variant="outline" className="text-green-600 border-green-600 text-xs">{target.writable ? 'Mounted' : 'Read-only'}</Badge>
          ) : (
            <Badge variant="destructive" className="text-xs">Not mounted</Badge>
          )}
        </div>
      </div>

      {target.mounted && target.total_bytes && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{formatBytes(target.used_bytes ?? 0)} used</span>
            <span>{formatBytes(target.free_bytes ?? 0)} free of {formatBytes(target.total_bytes)}</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div className={`h-full rounded-full ${barColor}`} style={{ width: `${usePct}%` }} />
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        {!target.is_active && (
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={handleActivate} disabled={activating || !target.mounted}>
            <Plug className="h-3 w-3" />
            {activating ? 'Activating…' : 'Set active'}
          </Button>
        )}
        <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={() => setShowFstab((p) => !p)}>
          {showFstab ? 'Hide' : 'Show'} fstab line
        </Button>
        {!target.is_active && (
          <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive hover:text-destructive gap-1 ml-auto" onClick={handleDelete} disabled={removing}>
            <Trash2 className="h-3 w-3" />
            Remove
          </Button>
        )}
      </div>

      {showFstab && (
        <div className="rounded bg-muted px-3 py-2 flex items-center gap-2">
          <code className="text-xs flex-1 break-all">{target.fstab_line}</code>
          <Button size="icon" variant="ghost" className="h-6 w-6 shrink-0" onClick={() => { navigator.clipboard.writeText(target.fstab_line); toast({ title: 'Copied' }) }}>
            <Copy className="h-3 w-3" />
          </Button>
        </div>
      )}
    </div>
  )
}

function StorageTab() {
  const { toast } = useToast()
  const { data: settings, isLoading } = useSettings()
  const { mutateAsync: updateSettings, isPending } = useUpdateSettings()
  const { data: targets, isLoading: targetsLoading } = useStorageTargets()
  const [showAdd, setShowAdd] = useState(false)

  const [warning, setWarning] = useState<number | null>(null)
  const [critical, setCritical] = useState<number | null>(null)

  const warningVal = warning ?? (settings?.storage_warning_threshold ?? 75)
  const criticalVal = critical ?? (settings?.storage_critical_threshold ?? 90)

  const handleSave = async () => {
    if (criticalVal <= warningVal) {
      toast({ title: 'Critical threshold must be greater than warning threshold', variant: 'destructive' })
      return
    }
    try {
      await updateSettings({
        storage_warning_threshold: warningVal,
        storage_critical_threshold: criticalVal,
      })
      toast({ title: 'Storage thresholds saved' })
    } catch {
      toast({ title: 'Failed to save thresholds', variant: 'destructive' })
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(2)].map((_, i) => <Skeleton key={i} className="h-16" />)}
      </div>
    )
  }

  return (
    <div className="space-y-8 max-w-lg">
      {/* Storage targets */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Storage targets</h3>
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1.5" onClick={() => setShowAdd(true)}>
            <Plus className="h-3.5 w-3.5" /> Add target
          </Button>
        </div>
        {targetsLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : targets && targets.length > 0 ? (
          <div className="space-y-3">
            {targets.map((t) => <StorageTargetCard key={t.id} target={t} />)}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            No storage targets configured. Add one to track where recordings are stored.
          </div>
        )}
      </div>

      <Separator />

      {/* Alert thresholds */}
      <div className="space-y-6 max-w-md">
        <h3 className="text-sm font-semibold">Alert thresholds</h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label>Storage warning threshold</Label>
            <span className="text-sm font-semibold tabular-nums">{warningVal}%</span>
          </div>
          <Slider min={50} max={95} step={1} value={[warningVal]} onValueChange={([v]) => setWarning(v)} />
          <p className="text-xs text-muted-foreground">Alert when storage exceeds this level.</p>
        </div>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label>Storage critical threshold</Label>
            <span className="text-sm font-semibold tabular-nums">{criticalVal}%</span>
          </div>
          <Slider min={60} max={99} step={1} value={[criticalVal]} onValueChange={([v]) => setCritical(v)} />
          <p className="text-xs text-muted-foreground">
            Trigger emergency purge / critical alerts at this level. Must be above warning threshold.
          </p>
        </div>
        {criticalVal <= warningVal && (
          <p className="text-xs text-destructive">Critical threshold must be greater than the warning threshold.</p>
        )}
        <Button onClick={handleSave} disabled={isPending || criticalVal <= warningVal}>
          {isPending ? 'Saving…' : 'Save changes'}
        </Button>
      </div>

      {showAdd && <AddTargetDialog onClose={() => setShowAdd(false)} />}
    </div>
  )
}

const emailSchema = z.object({
  to_address: z.string().email(),
  smtp_host: z.string().min(1),
  smtp_port: z.coerce.number().min(1).max(65535),
  from_address: z.string().email(),
})
const webhookSchema = z.object({
  url: z.string().url(),
  secret: z.string().optional(),
})
const slackSchema = z.object({
  webhook_url: z.string().url(),
  channel: z.string().min(1),
})
const telegramSchema = z.object({
  bot_token: z.string().min(1),
  chat_id: z.string().min(1),
})
const smsSchema = z.object({
  to_number: z.string().min(1),
  provider: z.literal('twilio'),
})

type ChannelType = NotificationChannel['type']

function channelLabel(type: ChannelType): string {
  switch (type) {
    case 'email': return 'Email'
    case 'webhook': return 'Webhook'
    case 'slack': return 'Slack'
    case 'telegram': return 'Telegram'
    case 'sms': return 'SMS'
  }
}

function ChannelConfigForm({
  type,
  defaultValues,
  onSubmit,
  isPending,
}: {
  type: ChannelType
  defaultValues?: Record<string, unknown>
  onSubmit: (config: Record<string, unknown>) => void
  isPending: boolean
}) {
  if (type === 'email') {
    const form = useForm<z.infer<typeof emailSchema>>({
      resolver: zodResolver(emailSchema),
      defaultValues: defaultValues as z.infer<typeof emailSchema>,
    })
    return (
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
        <div className="space-y-1.5">
          <Label>To address</Label>
          <Input type="email" {...form.register('to_address')} />
          {form.formState.errors.to_address && (
            <p className="text-xs text-destructive">{form.formState.errors.to_address.message}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label>SMTP host</Label>
          <Input {...form.register('smtp_host')} />
        </div>
        <div className="space-y-1.5">
          <Label>SMTP port</Label>
          <Input type="number" {...form.register('smtp_port')} />
        </div>
        <div className="space-y-1.5">
          <Label>From address</Label>
          <Input type="email" {...form.register('from_address')} />
          {form.formState.errors.from_address && (
            <p className="text-xs text-destructive">{form.formState.errors.from_address.message}</p>
          )}
        </div>
        <Button type="submit" disabled={isPending} className="w-full">
          {isPending ? 'Saving…' : 'Save'}
        </Button>
      </form>
    )
  }

  if (type === 'webhook') {
    const form = useForm<z.infer<typeof webhookSchema>>({
      resolver: zodResolver(webhookSchema),
      defaultValues: defaultValues as z.infer<typeof webhookSchema>,
    })
    return (
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
        <div className="space-y-1.5">
          <Label>URL</Label>
          <Input type="url" {...form.register('url')} />
          {form.formState.errors.url && (
            <p className="text-xs text-destructive">{form.formState.errors.url.message}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label>Secret (optional)</Label>
          <Input {...form.register('secret')} />
        </div>
        <Button type="submit" disabled={isPending} className="w-full">
          {isPending ? 'Saving…' : 'Save'}
        </Button>
      </form>
    )
  }

  if (type === 'slack') {
    const form = useForm<z.infer<typeof slackSchema>>({
      resolver: zodResolver(slackSchema),
      defaultValues: defaultValues as z.infer<typeof slackSchema>,
    })
    return (
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
        <div className="space-y-1.5">
          <Label>Webhook URL</Label>
          <Input type="url" {...form.register('webhook_url')} />
          {form.formState.errors.webhook_url && (
            <p className="text-xs text-destructive">{form.formState.errors.webhook_url.message}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label>Channel</Label>
          <Input placeholder="#alerts" {...form.register('channel')} />
        </div>
        <Button type="submit" disabled={isPending} className="w-full">
          {isPending ? 'Saving…' : 'Save'}
        </Button>
      </form>
    )
  }

  if (type === 'telegram') {
    const form = useForm<z.infer<typeof telegramSchema>>({
      resolver: zodResolver(telegramSchema),
      defaultValues: defaultValues as z.infer<typeof telegramSchema>,
    })
    return (
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
        <div className="space-y-1.5">
          <Label>Bot token</Label>
          <Input {...form.register('bot_token')} />
        </div>
        <div className="space-y-1.5">
          <Label>Chat ID</Label>
          <Input {...form.register('chat_id')} />
        </div>
        <Button type="submit" disabled={isPending} className="w-full">
          {isPending ? 'Saving…' : 'Save'}
        </Button>
      </form>
    )
  }

  const form = useForm<z.infer<typeof smsSchema>>({
    resolver: zodResolver(smsSchema),
    defaultValues: (defaultValues as z.infer<typeof smsSchema>) ?? { provider: 'twilio' },
  })
  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
      <div className="space-y-1.5">
        <Label>Phone number</Label>
        <Input placeholder="+15551234567" {...form.register('to_number')} />
      </div>
      <div className="space-y-1.5">
        <Label>Provider</Label>
        <Input value="twilio" readOnly className="bg-muted" {...form.register('provider')} />
      </div>
      <Button type="submit" disabled={isPending} className="w-full">
        {isPending ? 'Saving…' : 'Save'}
      </Button>
    </form>
  )
}

function AddChannelDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const { toast } = useToast()
  const { mutateAsync: createChannel, isPending } = useCreateChannel()
  const [step, setStep] = useState<1 | 2>(1)
  const [selectedType, setSelectedType] = useState<ChannelType | null>(null)
  const [channelName, setChannelName] = useState('')

  const reset = () => {
    setStep(1)
    setSelectedType(null)
    setChannelName('')
  }

  const handleClose = (v: boolean) => {
    if (!v) reset()
    onOpenChange(v)
  }

  const handleConfigSubmit = async (config: Record<string, unknown>) => {
    if (!selectedType || !channelName.trim()) return
    try {
      await createChannel({ type: selectedType, name: channelName, enabled: true, config })
      toast({ title: 'Channel created' })
      handleClose(false)
    } catch {
      toast({ title: 'Failed to create channel', variant: 'destructive' })
    }
  }

  const types: ChannelType[] = ['email', 'webhook', 'slack', 'telegram', 'sms']

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>
            {step === 1 ? 'Add notification channel' : `Configure ${channelLabel(selectedType!)} channel`}
          </DialogTitle>
        </DialogHeader>

        {step === 1 && (
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-5 gap-2">
              {types.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setSelectedType(t)}
                  className={`flex flex-col items-center gap-1.5 rounded-lg border p-3 text-xs font-medium transition-colors hover:bg-accent ${
                    selectedType === t ? 'border-primary bg-accent' : 'border-border'
                  }`}
                >
                  {channelIcon(t)}
                  {channelLabel(t)}
                </button>
              ))}
            </div>
            <div className="space-y-1.5">
              <Label>Channel name</Label>
              <Input
                value={channelName}
                onChange={(e) => setChannelName(e.target.value)}
                placeholder="e.g. Ops alerts"
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => handleClose(false)}>
                Cancel
              </Button>
              <Button
                disabled={!selectedType || !channelName.trim()}
                onClick={() => setStep(2)}
              >
                Next
              </Button>
            </DialogFooter>
          </div>
        )}

        {step === 2 && selectedType && (
          <div className="py-2">
            <ChannelConfigForm
              type={selectedType}
              onSubmit={handleConfigSubmit}
              isPending={isPending}
            />
            <Button
              variant="ghost"
              size="sm"
              className="mt-3 w-full"
              onClick={() => setStep(1)}
            >
              Back
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function EditChannelSheet({
  channel,
  open,
  onOpenChange,
}: {
  channel: NotificationChannel | null
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const { toast } = useToast()
  const { mutateAsync: updateChannel, isPending } = useUpdateChannel()

  if (!channel) return null

  const handleSubmit = async (config: Record<string, unknown>) => {
    try {
      await updateChannel({ id: channel.id, config })
      toast({ title: 'Channel updated' })
      onOpenChange(false)
    } catch {
      toast({ title: 'Failed to update channel', variant: 'destructive' })
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[400px] sm:max-w-[400px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {channelIcon(channel.type)}
            Edit {channel.name}
          </SheetTitle>
        </SheetHeader>
        <div className="mt-6">
          <ChannelConfigForm
            type={channel.type}
            defaultValues={channel.config as Record<string, unknown>}
            onSubmit={handleSubmit}
            isPending={isPending}
          />
        </div>
      </SheetContent>
    </Sheet>
  )
}

function ChannelRow({ channel }: { channel: NotificationChannel }) {
  const { toast } = useToast()
  const { mutateAsync: updateChannel } = useUpdateChannel()
  const { mutateAsync: deleteChannel, isPending: deleting } = useDeleteChannel()
  const { mutateAsync: testChannel, isPending: testing } = useTestChannel()
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)

  const handleToggle = async (enabled: boolean) => {
    try {
      await updateChannel({ id: channel.id, enabled })
    } catch {
      toast({ title: 'Failed to update channel', variant: 'destructive' })
    }
  }

  const handleTest = async () => {
    setTestResult(null)
    try {
      const result = await testChannel(channel.id)
      setTestResult(result)
    } catch {
      setTestResult({ success: false, message: 'Test failed' })
    }
  }

  const handleDelete = async () => {
    try {
      await deleteChannel(channel.id)
      toast({ title: 'Channel deleted' })
      setDeleteOpen(false)
    } catch {
      toast({ title: 'Failed to delete channel', variant: 'destructive' })
    }
  }

  return (
    <>
      <div className="flex items-center gap-3 rounded-lg border p-3">
        <span className="text-muted-foreground">{channelIcon(channel.type)}</span>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-sm truncate">{channel.name}</p>
          <p className="text-xs text-muted-foreground capitalize">{channel.type}</p>
        </div>
        {testResult && (
          <span
            className={`flex items-center gap-1 text-xs ${
              testResult.success ? 'text-green-600' : 'text-destructive'
            }`}
          >
            {testResult.success ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              <XCircle className="h-3.5 w-3.5" />
            )}
            {testResult.message}
          </span>
        )}
        <Switch checked={channel.enabled} onCheckedChange={handleToggle} />
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={handleTest}
          disabled={testing}
        >
          {testing ? 'Testing…' : 'Test'}
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          onClick={() => setEditOpen(true)}
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7 text-destructive hover:text-destructive"
          onClick={() => setDeleteOpen(true)}
          disabled={deleting}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      <EditChannelSheet
        channel={channel}
        open={editOpen}
        onOpenChange={setEditOpen}
      />

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Delete channel</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete <strong>{channel.name}</strong>? This cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function NotificationsTab() {
  const [addOpen, setAddOpen] = useState(false)
  const { data: channels, isLoading } = useNotificationChannels()

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-muted-foreground">Notification channels</h2>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="h-4 w-4 mr-1.5" />
          Add channel
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-16" />)}
        </div>
      ) : !channels?.length ? (
        <div className="rounded-lg border border-dashed p-8 text-center">
          <p className="text-sm text-muted-foreground">No notification channels configured.</p>
          <Button size="sm" variant="outline" className="mt-3" onClick={() => setAddOpen(true)}>
            Add your first channel
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {channels.map((ch) => (
            <ChannelRow key={ch.id} channel={ch} />
          ))}
        </div>
      )}

      <AddChannelDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  )
}

function SecurityTab() {
  const { toast } = useToast()
  const { data: settings, isLoading } = useSettings()
  const { mutateAsync: updateSettings, isPending } = useUpdateSettings()
  const { data: health } = useSystemHealth()

  const [timeout, setTimeout_] = useState<string>('')
  const [mfa, setMfa] = useState<boolean | null>(null)

  const timeoutVal = timeout !== '' ? timeout : String(settings?.session_timeout_minutes ?? '')
  const mfaVal = mfa !== null ? mfa : (settings?.mfa_enforcement ?? false)

  const healthyCount = health
    ? [health.database, health.redis, health.celery, health.detection].filter(Boolean).length
    : 0

  const handleSaveTimeout = async () => {
    const parsed = parseInt(timeoutVal, 10)
    if (isNaN(parsed) || parsed < 5 || parsed > 10080) {
      toast({ title: 'Timeout must be between 5 and 10080 minutes', variant: 'destructive' })
      return
    }
    try {
      await updateSettings({ session_timeout_minutes: parsed })
      toast({ title: 'Session timeout saved' })
    } catch {
      toast({ title: 'Failed to save', variant: 'destructive' })
    }
  }

  const handleMfaToggle = async (val: boolean) => {
    setMfa(val)
    try {
      await updateSettings({ mfa_enforcement: val })
      toast({ title: val ? 'MFA enforcement enabled' : 'MFA enforcement disabled' })
    } catch {
      setMfa(!val)
      toast({ title: 'Failed to update MFA enforcement', variant: 'destructive' })
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-12" />)}
      </div>
    )
  }

  return (
    <div className="space-y-8 max-w-md">
      <div className="space-y-3">
        <Label htmlFor="session_timeout">Session timeout (minutes)</Label>
        <div className="flex gap-2">
          <Input
            id="session_timeout"
            type="number"
            min={5}
            max={10080}
            value={timeoutVal}
            onChange={(e) => setTimeout_(e.target.value)}
            className="max-w-[160px]"
          />
          <Button onClick={handleSaveTimeout} disabled={isPending} variant="outline">
            Save
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">Range: 5 minutes to 7 days (10080 minutes).</p>
      </div>

      <Separator />

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <Label>MFA enforcement</Label>
            <p className="text-xs text-muted-foreground mt-0.5">
              Require MFA for all users (24h grace period)
            </p>
          </div>
          <Switch checked={mfaVal} onCheckedChange={handleMfaToggle} />
        </div>
      </div>

      <Separator />

      <div className="space-y-2">
        <Label>Active sessions</Label>
        <div className="rounded-lg border p-4 space-y-1">
          <p className="text-sm">
            <span className="font-semibold">{healthyCount} / 4</span> services healthy
          </p>
          <p className="text-xs text-muted-foreground">
            Manage individual user sessions on the{' '}
            <span className="font-medium">Users</span> page.
          </p>
        </div>
      </div>
    </div>
  )
}

function BackupTab() {
  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>Backup configuration</CardTitle>
        <CardDescription>
          Automated configuration backup and restore is not yet available.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          This feature is planned for a future release. Manual backups can be performed by
          exporting the database directly.
        </p>
      </CardContent>
    </Card>
  )
}

const apiKeySchema = z.object({
  name: z.string().min(1, 'Name is required'),
  permissions: z.array(z.string()).min(1, 'Select at least one permission'),
  expires_at: z.string().optional(),
})
type ApiKeyFormData = z.infer<typeof apiKeySchema>

function CreateApiKeyDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreated: (key: ApiKeyCreated) => void
}) {
  const { toast } = useToast()
  const { mutateAsync: createApiKey, isPending } = useCreateApiKey()

  const { register, handleSubmit, control, reset, formState: { errors } } = useForm<ApiKeyFormData>({
    resolver: zodResolver(apiKeySchema),
    defaultValues: { name: '', permissions: [], expires_at: '' },
  })

  const onSubmit = async (data: ApiKeyFormData) => {
    try {
      const created = await createApiKey({
        name: data.name,
        permissions: data.permissions,
        ...(data.expires_at ? { expires_at: data.expires_at } : {}),
      })
      reset()
      onOpenChange(false)
      onCreated(created)
    } catch {
      toast({ title: 'Failed to create API key', variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Create API key</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input placeholder="e.g. CI pipeline" {...register('name')} />
            {errors.name && (
              <p className="text-xs text-destructive">{errors.name.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label>Permissions</Label>
            <div className="grid grid-cols-2 gap-2">
              <Controller
                name="permissions"
                control={control}
                render={({ field }) => (
                  <>
                    {ALL_PERMISSIONS.map((perm) => (
                      <label key={perm} className="flex items-center gap-2 cursor-pointer text-sm">
                        <input
                          type="checkbox"
                          className="rounded border-border"
                          checked={field.value.includes(perm)}
                          onChange={(e) => {
                            const next = e.target.checked
                              ? [...field.value, perm]
                              : field.value.filter((p) => p !== perm)
                            field.onChange(next)
                          }}
                        />
                        <code className="text-xs">{perm}</code>
                      </label>
                    ))}
                  </>
                )}
              />
            </div>
            {errors.permissions && (
              <p className="text-xs text-destructive">{errors.permissions.message}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label>Expires at (optional)</Label>
            <Input type="datetime-local" {...register('expires_at')} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Creating…' : 'Create key'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function CreatedKeyDialog({
  keyValue,
  open,
  onOpenChange,
}: {
  keyValue: string
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const { toast } = useToast()

  const handleCopy = () => {
    navigator.clipboard.writeText(keyValue)
    toast({ title: 'Copied to clipboard' })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>API key created</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <p className="text-sm text-muted-foreground">
            This key will only be shown once. Copy it now and store it securely.
          </p>
          <code className="block bg-muted p-3 rounded font-mono text-sm break-all select-all">
            {keyValue}
          </code>
          <Button onClick={handleCopy} className="w-full" variant="outline">
            <Copy className="h-4 w-4 mr-2" />
            Copy to clipboard
          </Button>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RevokeKeyDialog({
  keyId,
  keyName,
  open,
  onOpenChange,
}: {
  keyId: string
  keyName: string
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const { toast } = useToast()
  const { mutateAsync: revokeApiKey, isPending } = useRevokeApiKey()

  const handleRevoke = async () => {
    try {
      await revokeApiKey(keyId)
      toast({ title: 'API key revoked' })
      onOpenChange(false)
    } catch {
      toast({ title: 'Failed to revoke key', variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Revoke API key</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Are you sure you want to revoke <strong>{keyName}</strong>? Any integrations using this
          key will stop working immediately.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleRevoke} disabled={isPending}>
            {isPending ? 'Revoking…' : 'Revoke key'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ApiKeysTab() {
  const { data: keys, isLoading } = useApiKeys()
  const [createOpen, setCreateOpen] = useState(false)
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null)
  const [revokeTarget, setRevokeTarget] = useState<{ id: string; name: string } | null>(null)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-muted-foreground">API keys</h2>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-1.5" />
          Create key
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Prefix</TableHead>
              <TableHead>Permissions</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Last used</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead className="w-20"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              [...Array(4)].map((_, i) => (
                <TableRow key={i}>
                  {[...Array(7)].map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : !keys?.length ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                  No API keys yet
                </TableCell>
              </TableRow>
            ) : (
              keys.map((key) => (
                <TableRow key={key.id}>
                  <TableCell className="font-medium">{key.name}</TableCell>
                  <TableCell>
                    <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">
                      {key.prefix}
                    </code>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {key.permissions.map((p) => (
                        <Badge key={p} variant="outline" className="text-xs font-normal">
                          {p}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {format(new Date(key.created_at), 'MMM d, yyyy')}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {key.last_used_at
                      ? format(new Date(key.last_used_at), 'MMM d, yyyy')
                      : <span className="text-muted-foreground">Never</span>}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {key.expires_at
                      ? format(new Date(key.expires_at), 'MMM d, yyyy')
                      : <span className="text-muted-foreground">Never</span>}
                  </TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs text-destructive hover:text-destructive border-destructive/40 hover:border-destructive"
                      onClick={() => setRevokeTarget({ id: key.id, name: key.name })}
                    >
                      Revoke
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <CreateApiKeyDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(created) => setCreatedKey(created)}
      />

      {createdKey && (
        <CreatedKeyDialog
          keyValue={createdKey.key}
          open={!!createdKey}
          onOpenChange={(v) => { if (!v) setCreatedKey(null) }}
        />
      )}

      {revokeTarget && (
        <RevokeKeyDialog
          keyId={revokeTarget.id}
          keyName={revokeTarget.name}
          open={!!revokeTarget}
          onOpenChange={(v) => { if (!v) setRevokeTarget(null) }}
        />
      )}
    </div>
  )
}

function AboutTab() {
  return (
    <div className="space-y-4 max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>NVR Pro</CardTitle>
          <CardDescription>Self-hosted enterprise network video recorder</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Version</span>
            <span className="font-mono font-medium">1.0.0</span>
          </div>
          <Separator />
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Build date</span>
            <span>{new Date().toLocaleDateString()}</span>
          </div>
          <Separator />
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Cameras</span>
            <span className="text-muted-foreground">—</span>
          </div>
          <Separator />
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Recordings</span>
            <span className="text-muted-foreground">—</span>
          </div>
          <Separator />
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Source</span>
            <a
              href="#"
              className="text-primary underline-offset-4 hover:underline opacity-50 pointer-events-none"
              aria-disabled="true"
            >
              GitHub repository
            </a>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function AddonsTab() {
  const { isEnabled, enable, disable } = useAddonStore()
  return (
    <div className="space-y-4 max-w-2xl">
      <p className="text-sm text-muted-foreground">
        Add-ons extend NVR Pro with optional features. Enabled add-ons appear in the sidebar.
      </p>
      {ADDONS.map((addon) => {
        const on = isEnabled(addon.id)
        return (
          <div key={addon.id} className="flex items-start justify-between gap-4 rounded-lg border p-4">
            <div>
              <p className="font-medium">{addon.name}</p>
              <p className="text-sm text-muted-foreground mt-0.5">{addon.description}</p>
            </div>
            <button
              role="switch"
              aria-checked={on}
              onClick={() => on ? disable(addon.id) : enable(addon.id)}
              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${on ? 'bg-primary' : 'bg-input'}`}
            >
              <span className={`pointer-events-none block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-transform ${on ? 'translate-x-5' : 'translate-x-0'}`} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

function ServicesTab() {
  const { toast } = useToast()
  const { data: status, isLoading, dataUpdatedAt } = useDetectionStatus()
  const { data: health } = useSystemHealth()
  const { mutateAsync: restart, isPending: restarting } = useRestartDetection()
  const { data: workerStatus, isLoading: workerLoading } = useWorkerStatus()
  const { mutateAsync: restartWorker, isPending: workerRestarting } = useRestartWorker()

  const handleRestartWorker = async () => {
    try {
      const result = await restartWorker()
      toast({ title: 'Celery worker restarting', description: result.container_name })
    } catch {
      toast({ title: 'Restart failed', description: 'Could not restart the worker container. Check that the Docker socket is mounted.', variant: 'destructive' })
    }
  }

  const handleRestart = async () => {
    try {
      const result = await restart()
      toast({ title: `Detection service restarting`, description: result.container_name })
    } catch {
      toast({ title: 'Restart failed', description: 'Could not restart the detection container. Check that the Docker socket is mounted.', variant: 'destructive' })
    }
  }

  const effectivelyHealthy = status?.container_state === 'running' && status?.healthy
  const runningNoHeartbeat = status?.container_state === 'running' && !status?.healthy

  const stateColor = () => {
    if (effectivelyHealthy) return 'text-green-600'
    if (runningNoHeartbeat) return 'text-amber-500'
    if (status?.container_state === 'exited' || status?.container_state === 'stopped') return 'text-destructive'
    return 'text-muted-foreground'
  }

  const stateIcon = () => {
    if (effectivelyHealthy) return <CircleCheck className="h-4 w-4 text-green-600" />
    if (runningNoHeartbeat) return <CircleDot className="h-4 w-4 text-amber-500" />
    if (status?.container_state === 'exited' || status?.container_state === 'stopped') return <CircleX className="h-4 w-4 text-destructive" />
    return <CircleDot className="h-4 w-4 text-muted-foreground" />
  }

  const stateLabel = () => {
    if (effectivelyHealthy) return 'Running & healthy'
    if (runningNoHeartbeat) return 'Running — no heartbeat'
    return status?.container_state ?? 'Unknown'
  }

  const services = [
    { label: 'Database', ok: health?.database },
    { label: 'Redis', ok: health?.redis },
    { label: 'Celery worker', ok: health?.celery },
  ]

  return (
    <div className="space-y-6 max-w-lg">
      {/* Infrastructure health */}
      <div>
        <h3 className="text-sm font-semibold mb-3">Infrastructure</h3>
        <div className="rounded-lg border divide-y">
          {services.map(({ label, ok }) => (
            <div key={label} className="flex items-center justify-between px-4 py-3">
              <span className="text-sm">{label}</span>
              {ok == null ? (
                <Skeleton className="h-5 w-16" />
              ) : ok ? (
                <Badge variant="outline" className="text-green-600 border-green-600 text-xs">Healthy</Badge>
              ) : (
                <Badge variant="destructive" className="text-xs">Down</Badge>
              )}
            </div>
          ))}
        </div>
      </div>

      <Separator />

      {/* Celery worker */}
      <div>
        <h3 className="text-sm font-semibold mb-3">Celery worker</h3>
        {workerLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <div className="rounded-lg border p-4 space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-2 flex-1">
                <div className="flex items-center gap-2">
                  {workerStatus?.online ? (
                    <CircleCheck className="h-4 w-4 text-green-600" />
                  ) : workerStatus?.container_state === 'running' ? (
                    <CircleDot className="h-4 w-4 text-amber-500" />
                  ) : (
                    <CircleX className="h-4 w-4 text-destructive" />
                  )}
                  <span className={`text-sm font-medium ${workerStatus?.online ? 'text-green-600' : workerStatus?.container_state === 'running' ? 'text-amber-500' : 'text-destructive'}`}>
                    {workerStatus?.online ? 'Online' : workerStatus?.container_state === 'running' ? 'Starting…' : (workerStatus?.container_state ?? 'Offline')}
                  </span>
                </div>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>
                    Cameras recording:{' '}
                    <span className="font-medium text-foreground">{workerStatus?.recording_count ?? '—'}</span>
                  </p>
                  <p>
                    Active tasks:{' '}
                    <span className="font-medium text-foreground">{workerStatus?.active_tasks ?? '—'}</span>
                  </p>
                  <p>
                    Alert consumer:{' '}
                    {workerStatus?.alert_consumer_running ? (
                      <span className="text-green-600 font-medium">running</span>
                    ) : (
                      <span className="text-destructive font-medium">not running</span>
                    )}
                  </p>
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={handleRestartWorker}
                disabled={workerRestarting}
                className="gap-1.5 shrink-0"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${workerRestarting ? 'animate-spin' : ''}`} />
                {workerRestarting ? 'Restarting…' : workerStatus?.container_state === 'running' ? 'Restart' : 'Start'}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground border-t pt-3">
              Status refreshes every 15 seconds via Celery inspect.
            </p>
          </div>
        )}
      </div>

      <Separator />

      {/* Detection service */}
      <div>
        <h3 className="text-sm font-semibold mb-3">Detection service</h3>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <div className="rounded-lg border p-4 space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-2 flex-1">
                <div className="flex items-center gap-2">
                  {stateIcon()}
                  <span className={`text-sm font-medium ${stateColor()}`}>
                    {stateLabel()}
                  </span>
                </div>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>
                    Cameras active:{' '}
                    <span className="font-medium text-foreground">
                      {status?.cameras_active ?? '—'}
                    </span>
                  </p>
                  <p>
                    Health check:{' '}
                    {status?.healthy ? (
                      <span className="text-green-600 font-medium">passing</span>
                    ) : (
                      <span className="text-destructive font-medium">not reachable</span>
                    )}
                  </p>
                  {dataUpdatedAt > 0 && (
                    <p>Polled: {new Date(dataUpdatedAt).toLocaleTimeString()}</p>
                  )}
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={handleRestart}
                disabled={restarting}
                className="gap-1.5 shrink-0"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${restarting ? 'animate-spin' : ''}`} />
                {restarting ? 'Restarting…' : status?.container_state === 'running' ? 'Restart' : 'Start'}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground border-t pt-3">
              Status refreshes every 10 seconds. A healthy detection service sends a heartbeat to Redis every ~30 s.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Settings() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Settings</h1>
      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="storage">Storage</TabsTrigger>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="backup">Backup</TabsTrigger>
          <TabsTrigger value="apikeys">API Keys</TabsTrigger>
          <TabsTrigger value="addons">Add-ons</TabsTrigger>
          <TabsTrigger value="about">About</TabsTrigger>
        </TabsList>
        <TabsContent value="general" className="mt-6">
          <GeneralTab />
        </TabsContent>
        <TabsContent value="storage" className="mt-6">
          <StorageTab />
        </TabsContent>
        <TabsContent value="services" className="mt-6">
          <ServicesTab />
        </TabsContent>
        <TabsContent value="notifications" className="mt-6">
          <NotificationsTab />
        </TabsContent>
        <TabsContent value="security" className="mt-6">
          <SecurityTab />
        </TabsContent>
        <TabsContent value="backup" className="mt-6">
          <BackupTab />
        </TabsContent>
        <TabsContent value="apikeys" className="mt-6">
          <ApiKeysTab />
        </TabsContent>
        <TabsContent value="addons" className="mt-6">
          <AddonsTab />
        </TabsContent>
        <TabsContent value="about" className="mt-6">
          <AboutTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
