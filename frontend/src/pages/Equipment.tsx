import { useState } from 'react'
import { Monitor, Server, Tv, Router, HelpCircle, Terminal, Pencil, Trash2, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { useEquipment, useCreateEquipment, useUpdateEquipment, useDeleteEquipment } from '@/api/equipment'
import SSHTerminal from '@/components/equipment/SSHTerminal'
import type { Equipment, EquipmentCreate, DeviceType } from '@/types'

const DEVICE_ICONS: Record<DeviceType, React.ReactNode> = {
  camera: <Monitor className="h-5 w-5" />,
  raspberry_pi: <Server className="h-5 w-5" />,
  display: <Tv className="h-5 w-5" />,
  switch: <Router className="h-5 w-5" />,
  other: <HelpCircle className="h-5 w-5" />,
}

const DEVICE_LABELS: Record<DeviceType, string> = {
  camera: 'Camera',
  raspberry_pi: 'Raspberry Pi',
  display: 'Display',
  switch: 'Switch',
  other: 'Other',
}

const DEFAULT_FORM: EquipmentCreate = {
  name: '',
  ip_address: '',
  ssh_port: 22,
  ssh_user: 'pi',
  ssh_password: '',
  ssh_key_path: '',
  device_type: 'raspberry_pi',
  location: '',
  notes: '',
}

export default function EquipmentPage() {
  const { data: items = [], isLoading } = useEquipment()
  const { mutateAsync: create, isPending: creating } = useCreateEquipment()
  const { mutateAsync: update, isPending: updating } = useUpdateEquipment()
  const { mutateAsync: remove } = useDeleteEquipment()

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Equipment | null>(null)
  const [form, setForm] = useState<EquipmentCreate>(DEFAULT_FORM)
  const [deleteTarget, setDeleteTarget] = useState<Equipment | null>(null)
  const [terminalTarget, setTerminalTarget] = useState<Equipment | null>(null)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState<string | null>(null)

  const openCreate = () => {
    setEditing(null)
    setForm(DEFAULT_FORM)
    setError(null)
    setFormOpen(true)
  }

  const openEdit = (eq: Equipment) => {
    setEditing(eq)
    setForm({
      name: eq.name,
      ip_address: eq.ip_address,
      ssh_port: eq.ssh_port,
      ssh_user: eq.ssh_user,
      ssh_password: '',
      ssh_key_path: eq.ssh_key_path ?? '',
      device_type: eq.device_type as DeviceType,
      location: eq.location ?? '',
      notes: eq.notes ?? '',
    })
    setError(null)
    setFormOpen(true)
  }

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.ip_address.trim()) {
      setError('Name and IP address are required.')
      return
    }
    try {
      const payload: EquipmentCreate = {
        ...form,
        ssh_password: form.ssh_password || undefined,
        ssh_key_path: form.ssh_key_path || undefined,
        location: form.location || undefined,
        notes: form.notes || undefined,
      }
      if (editing) {
        await update({ id: editing.id, ...payload })
      } else {
        await create(payload)
      }
      setFormOpen(false)
    } catch {
      setError('Failed to save equipment.')
    }
  }

  const filtered = items.filter(
    (eq) =>
      eq.name.toLowerCase().includes(filter.toLowerCase()) ||
      eq.ip_address.includes(filter) ||
      (eq.location ?? '').toLowerCase().includes(filter.toLowerCase())
  )

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Equipment Inventory</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            All devices in this NVR installation
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1.5" /> Add device
        </Button>
      </div>

      <Input
        placeholder="Filter by name, IP or location…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="max-w-sm"
      />

      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      )}

      {!isLoading && filtered.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <Server className="h-10 w-10 mx-auto mb-3 opacity-30" />
          <p>No devices yet. Add your first device above.</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((eq) => (
          <Card key={eq.id} className={!eq.is_active ? 'opacity-50' : ''}>
            <CardContent className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <button
                    title={`Open SSH terminal for ${eq.name}`}
                    onClick={() => setTerminalTarget(eq)}
                    className="p-2 rounded-md bg-muted hover:bg-primary hover:text-primary-foreground transition-colors"
                  >
                    {DEVICE_ICONS[eq.device_type as DeviceType] ?? DEVICE_ICONS.other}
                  </button>
                  <div>
                    <p className="font-medium leading-tight">{eq.name}</p>
                    <p className="text-xs text-muted-foreground font-mono">{eq.ip_address}:{eq.ssh_port}</p>
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => openEdit(eq)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => setDeleteTarget(eq)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              <div className="flex flex-wrap gap-1.5 text-xs">
                <Badge variant="secondary">{DEVICE_LABELS[eq.device_type as DeviceType] ?? eq.device_type}</Badge>
                {eq.location && <Badge variant="outline">{eq.location}</Badge>}
                {!eq.is_active && <Badge variant="destructive">Inactive</Badge>}
              </div>

              <Button
                size="sm"
                variant="outline"
                className="w-full h-8 text-xs gap-1.5"
                onClick={() => setTerminalTarget(eq)}
              >
                <Terminal className="h-3.5 w-3.5" /> SSH Terminal
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Add / Edit dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit device' : 'Add device'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2 space-y-1">
                <Label>Name</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Living room Pi" />
              </div>
              <div className="space-y-1">
                <Label>IP address</Label>
                <Input value={form.ip_address} onChange={(e) => setForm({ ...form, ip_address: e.target.value })} placeholder="192.168.1.50" />
              </div>
              <div className="space-y-1">
                <Label>SSH port</Label>
                <Input type="number" value={form.ssh_port} onChange={(e) => setForm({ ...form, ssh_port: Number(e.target.value) })} />
              </div>
              <div className="space-y-1">
                <Label>SSH user</Label>
                <Input value={form.ssh_user} onChange={(e) => setForm({ ...form, ssh_user: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label>Type</Label>
                <Select value={form.device_type} onValueChange={(v) => setForm({ ...form, device_type: v as DeviceType })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(DEVICE_LABELS).map(([v, l]) => (
                      <SelectItem key={v} value={v}>{l}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>SSH password {editing?.has_ssh_password ? '(leave blank to keep)' : ''}</Label>
                <Input type="password" value={form.ssh_password} onChange={(e) => setForm({ ...form, ssh_password: e.target.value })} placeholder="••••••" />
              </div>
              <div className="col-span-2 space-y-1">
                <Label>SSH key path (on server)</Label>
                <Input value={form.ssh_key_path} onChange={(e) => setForm({ ...form, ssh_key_path: e.target.value })} placeholder="/run/secrets/id_rsa" />
              </div>
              <div className="space-y-1">
                <Label>Location</Label>
                <Input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Living room" />
              </div>
              <div className="col-span-2 space-y-1">
                <Label>Notes</Label>
                <textarea
                  value={form.notes ?? ''}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setForm({ ...form, notes: e.target.value })}
                  rows={2}
                  className="flex min-h-[60px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmit} disabled={creating || updating}>
              {editing ? 'Save' : 'Add device'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={!!deleteTarget} onOpenChange={(open: boolean) => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete {deleteTarget?.name}?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">This cannot be undone.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={async () => { if (deleteTarget) { await remove(deleteTarget.id); setDeleteTarget(null) } }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* SSH Terminal dialog */}
      <Dialog open={!!terminalTarget} onOpenChange={(open: boolean) => !open && setTerminalTarget(null)}>
        <DialogContent className="max-w-4xl h-[600px] flex flex-col p-0">
          <DialogHeader className="px-4 pt-4 pb-2 border-b">
            <DialogTitle className="flex items-center gap-2 text-sm font-medium">
              <Terminal className="h-4 w-4" />
              {terminalTarget?.name} — {terminalTarget?.ip_address}
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-hidden">
            {terminalTarget && <SSHTerminal equipmentId={terminalTarget.id} />}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
