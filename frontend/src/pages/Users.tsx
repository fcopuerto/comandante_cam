import { useState } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'
import { Search, Pencil, UserX } from 'lucide-react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { format } from 'date-fns'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { useToast } from '@/components/ui/use-toast'
import {
  useUsers,
  useInviteUser,
  useUpdateUser,
  useDeactivateUser,
  useRoles,
  useUserSessions,
  useRevokeSession,
  useCameraPermissions,
  useUpdateCameraPermission,
} from '@/api/users'
import { useAuthStore } from '@/store/authStore'
import type { User, CameraPermission } from '@/types'

const inviteSchema = z.object({
  email: z.string().email(),
  full_name: z.string().min(2),
  role: z.string().min(1),
})
type InviteFormData = z.infer<typeof inviteSchema>

const colHelper = createColumnHelper<User>()

function roleBadgeClass(role: string): string {
  switch (role) {
    case 'superadmin': return 'bg-red-100 text-red-700 border-red-200'
    case 'admin': return 'bg-purple-100 text-purple-700 border-purple-200'
    case 'operator': return 'bg-blue-100 text-blue-700 border-blue-200'
    default: return 'bg-gray-100 text-gray-600 border-gray-200'
  }
}

function UserInitials({ name }: { name: string }) {
  const initials = name
    .split(' ')
    .map((p) => p[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
  return (
    <Avatar className="h-8 w-8">
      <AvatarFallback className="text-xs">{initials}</AvatarFallback>
    </Avatar>
  )
}

function InviteUserDialog({
  open,
  onOpenChange,
  roles,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  roles: Array<{ id: string; name: string }>
}) {
  const { toast } = useToast()
  const { mutateAsync: invite, isPending } = useInviteUser()
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<InviteFormData>({ resolver: zodResolver(inviteSchema) })

  const onSubmit = async (data: InviteFormData) => {
    await invite(data)
    toast({ title: 'Invitation sent', description: `${data.email} has been invited.` })
    reset()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>Invite User</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <Label htmlFor="invite-email">Email</Label>
            <Input id="invite-email" type="email" {...register('email')} />
            {errors.email && (
              <p className="text-xs text-destructive">{errors.email.message}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="invite-name">Full name</Label>
            <Input id="invite-name" {...register('full_name')} />
            {errors.full_name && (
              <p className="text-xs text-destructive">{errors.full_name.message}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label>Role</Label>
            <Controller
              name="role"
              control={control}
              render={({ field }) => (
                <Select onValueChange={field.onChange} value={field.value}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select role" />
                  </SelectTrigger>
                  <SelectContent>
                    {roles.map((r) => (
                      <SelectItem key={r.id} value={r.name}>
                        {r.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.role && (
              <p className="text-xs text-destructive">{errors.role.message}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Sending…' : 'Send invite'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ProfileTab({ user }: { user: User }) {
  const { toast } = useToast()
  const { data: rolesData } = useRoles()
  const { mutateAsync: updateUser, isPending: saving } = useUpdateUser()
  const { mutateAsync: deactivateUser, isPending: deactivating } = useDeactivateUser()
  const currentUser = useAuthStore((s) => s.user)

  const [fullName, setFullName] = useState(user.full_name)
  const [role, setRole] = useState(user.role)
  const [isActive, setIsActive] = useState(user.is_active)

  const handleSave = async () => {
    await updateUser({ id: user.id, full_name: fullName, role, is_active: isActive })
    toast({ title: 'User updated' })
  }

  const handleDeactivate = async () => {
    if (!window.confirm(`Deactivate ${user.full_name}? They will lose access immediately.`)) return
    await deactivateUser(user.id)
    toast({ title: 'User deactivated' })
  }

  return (
    <div className="space-y-4 pt-2">
      <div className="space-y-1.5">
        <Label>Full name</Label>
        <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label>Role</Label>
        <Select value={role} onValueChange={setRole}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(rolesData ?? []).map((r) => (
              <SelectItem key={r.id} value={r.name}>
                {r.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center justify-between">
        <Label>Active</Label>
        <Switch checked={isActive} onCheckedChange={setIsActive} />
      </div>
      <Separator />
      <div className="flex items-center justify-between">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save changes'}
        </Button>
        {user.is_active && user.id !== currentUser?.id && (
          <Button
            variant="destructive"
            onClick={handleDeactivate}
            disabled={deactivating}
          >
            <UserX className="h-4 w-4 mr-1.5" />
            Deactivate user
          </Button>
        )}
      </div>
    </div>
  )
}

function SessionsTab({ user }: { user: User }) {
  const { data: sessions, isLoading } = useUserSessions(user.id)
  const { mutateAsync: revokeSession, isPending: revoking } = useRevokeSession()
  const { toast } = useToast()

  const handleRevoke = async (sessionId: string) => {
    await revokeSession({ userId: user.id, sessionId })
    toast({ title: 'Session revoked' })
  }

  if (isLoading) {
    return (
      <div className="space-y-2 pt-2">
        {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-14" />)}
      </div>
    )
  }

  if (!sessions?.length) {
    return <p className="text-sm text-muted-foreground pt-4 text-center">No active sessions</p>
  }

  return (
    <div className="space-y-2 pt-2">
      {sessions.map((s) => (
        <div key={s.id} className="rounded-md border p-3 space-y-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 space-y-0.5">
              <div className="flex items-center gap-2">
                <span className="text-sm font-mono text-muted-foreground">{s.ip_address}</span>
                {s.is_current && (
                  <Badge className="text-xs h-5">Current session</Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground truncate">{s.user_agent}</p>
              <p className="text-xs text-muted-foreground">
                Last used: {format(new Date(s.last_used_at), 'MMM d, yyyy HH:mm')}
              </p>
            </div>
            {!s.is_current && (
              <Button
                size="sm"
                variant="outline"
                className="shrink-0 h-7 text-xs"
                onClick={() => handleRevoke(s.id)}
                disabled={revoking}
              >
                Revoke
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function CameraPermissionsTab({ user }: { user: User }) {
  const { data: permissions, isLoading } = useCameraPermissions(user.id)
  const { mutateAsync: updatePerm } = useUpdateCameraPermission()

  const handleToggle = (
    perm: CameraPermission,
    field: keyof Pick<CameraPermission, 'can_view' | 'can_control_ptz' | 'can_export'>,
    value: boolean,
  ) => {
    updatePerm({ userId: user.id, cameraId: perm.camera_id, [field]: value })
  }

  if (isLoading) {
    return (
      <div className="space-y-2 pt-2">
        {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-10" />)}
      </div>
    )
  }

  if (!permissions?.length) {
    return <p className="text-sm text-muted-foreground pt-4 text-center">No cameras configured</p>
  }

  return (
    <div className="pt-2 rounded-md border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Camera</TableHead>
            <TableHead className="text-center w-16">View</TableHead>
            <TableHead className="text-center w-16">PTZ</TableHead>
            <TableHead className="text-center w-16">Export</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {permissions.map((perm) => (
            <TableRow key={perm.camera_id}>
              <TableCell className="font-medium">{perm.camera_name}</TableCell>
              <TableCell className="text-center">
                <Switch
                  checked={perm.can_view}
                  onCheckedChange={(v) => handleToggle(perm, 'can_view', v)}
                />
              </TableCell>
              <TableCell className="text-center">
                <Switch
                  checked={perm.can_control_ptz}
                  onCheckedChange={(v) => handleToggle(perm, 'can_control_ptz', v)}
                />
              </TableCell>
              <TableCell className="text-center">
                <Switch
                  checked={perm.can_export}
                  onCheckedChange={(v) => handleToggle(perm, 'can_export', v)}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function UserDetailSheet({
  user,
  open,
  onOpenChange,
}: {
  user: User | null
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  if (!user) return null

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[520px] sm:max-w-[520px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-3">
            <UserInitials name={user.full_name} />
            {user.full_name}
          </SheetTitle>
        </SheetHeader>
        <div className="mt-4">
          <Tabs defaultValue="profile">
            <TabsList className="w-full">
              <TabsTrigger value="profile" className="flex-1">Profile</TabsTrigger>
              <TabsTrigger value="sessions" className="flex-1">Sessions</TabsTrigger>
              <TabsTrigger value="permissions" className="flex-1">Camera Permissions</TabsTrigger>
            </TabsList>
            <TabsContent value="profile">
              <ProfileTab user={user} />
            </TabsContent>
            <TabsContent value="sessions">
              <SessionsTab user={user} />
            </TabsContent>
            <TabsContent value="permissions">
              <CameraPermissionsTab user={user} />
            </TabsContent>
          </Tabs>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function UsersTab() {
  const [sorting, setSorting] = useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [roleFilter, setRoleFilter] = useState<string>('all')
  const [activeFilter, setActiveFilter] = useState<'all' | 'active'>('active')
  const [inviteOpen, setInviteOpen] = useState(false)
  const [detailUser, setDetailUser] = useState<User | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)

  const currentUser = useAuthStore((s) => s.user)
  const { toast } = useToast()

  const { data: rolesData } = useRoles()
  const { data, isLoading } = useUsers({
    page_size: 100,
    ...(roleFilter !== 'all' ? { role: roleFilter } : {}),
    ...(activeFilter === 'active' ? { is_active: true } : {}),
  })
  const { mutateAsync: deactivateUser } = useDeactivateUser()

  const handleDeactivate = async (user: User) => {
    if (!window.confirm(`Deactivate ${user.full_name}? They will lose access immediately.`)) return
    await deactivateUser(user.id)
    toast({ title: 'User deactivated' })
  }

  const handleOpenDetail = (user: User) => {
    setDetailUser(user)
    setSheetOpen(true)
  }

  const columns = [
    colHelper.display({
      id: 'avatar',
      header: '',
      cell: ({ row }) => <UserInitials name={row.original.full_name} />,
      size: 48,
    }),
    colHelper.accessor('full_name', {
      header: 'Name',
      cell: (info) => (
        <div>
          <p className="font-medium leading-tight">{info.getValue()}</p>
          <p className="text-xs text-muted-foreground">{info.row.original.email}</p>
        </div>
      ),
    }),
    colHelper.accessor('role', {
      header: 'Role',
      cell: (info) => (
        <span
          className={`text-xs px-2 py-0.5 rounded-full border font-medium ${roleBadgeClass(info.getValue())}`}
        >
          {info.getValue()}
        </span>
      ),
    }),
    colHelper.accessor('is_active', {
      header: 'Status',
      cell: (info) => (
        <Badge variant={info.getValue() ? 'default' : 'secondary'} className="text-xs">
          {info.getValue() ? 'Active' : 'Inactive'}
        </Badge>
      ),
    }),
    colHelper.accessor('mfa_enabled', {
      header: 'MFA',
      cell: (info) => (
        <span className={`text-xs ${info.getValue() ? 'text-green-600' : 'text-muted-foreground'}`}>
          {info.getValue() ? 'Enabled' : 'Off'}
        </span>
      ),
    }),
    colHelper.accessor('last_login', {
      header: 'Last login',
      cell: (info) =>
        info.getValue() ? (
          <span className="text-sm">{format(new Date(info.getValue()!), 'MMM d, yyyy HH:mm')}</span>
        ) : (
          <span className="text-muted-foreground text-sm">Never</span>
        ),
    }),
    colHelper.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => {
        const user = row.original
        return (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => handleOpenDetail(user)}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            {user.is_active && user.id !== currentUser?.id && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-destructive hover:text-destructive"
                onClick={() => handleDeactivate(user)}
              >
                <UserX className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        )
      },
      size: 72,
    }),
  ]

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder="Search users…"
            className="pl-9"
          />
        </div>
        <Select value={roleFilter} onValueChange={setRoleFilter}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Role" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All roles</SelectItem>
            {(rolesData ?? []).map((r) => (
              <SelectItem key={r.id} value={r.name}>
                {r.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2">
          <Switch
            id="active-filter"
            checked={activeFilter === 'active'}
            onCheckedChange={(v) => setActiveFilter(v ? 'active' : 'all')}
          />
          <Label htmlFor="active-filter" className="text-sm cursor-pointer">
            Active only
          </Label>
        </div>
        <Button size="sm" onClick={() => setInviteOpen(true)} className="ml-auto">
          Invite User
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead
                    key={h.id}
                    style={{ width: h.getSize() !== 150 ? h.getSize() : undefined }}
                  >
                    {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading ? (
              [...Array(6)].map((_, i) => (
                <TableRow key={i}>
                  {columns.map((_, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-5 w-full" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : table.getRowModel().rows.length > 0 ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="text-center py-8 text-muted-foreground"
                >
                  No users found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <InviteUserDialog
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        roles={rolesData ?? []}
      />
      <UserDetailSheet
        user={detailUser}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </div>
  )
}

function RolesTab() {
  const { data: roles, isLoading } = useRoles()

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-36" />)}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {(roles ?? []).map((role) => (
          <Card key={role.id}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-base">
                <span className={`px-2 py-0.5 rounded-full border text-sm font-medium ${roleBadgeClass(role.name)}`}>
                  {role.name}
                </span>
                {role.is_system && (
                  <span className="text-xs text-muted-foreground font-normal">System role</span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {role.permissions.map((perm) => (
                  <Badge key={perm} variant="outline" className="text-xs font-normal">
                    {perm}
                  </Badge>
                ))}
                {role.permissions.length === 0 && (
                  <span className="text-xs text-muted-foreground">No permissions</span>
                )}
              </div>
              {!role.is_system && (
                <>
                  <Separator />
                  <p className="text-xs text-muted-foreground">Role editing coming soon</p>
                </>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

export default function Users() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Users</h1>
      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="roles">Roles</TabsTrigger>
        </TabsList>
        <TabsContent value="users" className="mt-4">
          <UsersTab />
        </TabsContent>
        <TabsContent value="roles" className="mt-4">
          <RolesTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
