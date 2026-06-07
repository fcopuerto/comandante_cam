import { useState, useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Video, Film, Bell, Camera, Users, Settings,
  ChevronLeft, ChevronRight, LogOut, User, Monitor, HardDrive, Server, Building2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useAuthStore } from '@/store/authStore'
import { useWsStore } from '@/store/wsStore'
import { useAddonStore } from '@/store/addonStore'
import { useAlerts } from '@/api/alerts'
import { useSystemEvents } from '@/api/system'
import SystemHealthBar from '@/components/shared/SystemHealthBar'

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', exact: true },
  { to: '/live', icon: Video, label: 'Live View' },
  { to: '/recordings', icon: Film, label: 'Recordings' },
  { to: '/alerts', icon: Bell, label: 'Alerts' },
  { to: '/cameras', icon: Camera, label: 'Cameras' },
  { to: '/users', icon: Users, label: 'Users', adminOnly: true },
  { to: '/audit', icon: Film, label: 'Audit Log', adminOnly: true },
  { to: '/settings', icon: Settings, label: 'Settings', adminOnly: true },
]

function WsIndicator() {
  const status = useWsStore((s) => s.status)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className={cn('h-2 w-2 rounded-full', {
            'bg-green-500': status === 'connected',
            'bg-amber-500 animate-pulse': status === 'reconnecting' || status === 'connecting',
            'bg-red-500': status === 'disconnected',
          })} />
          <span className="hidden lg:inline capitalize">{status}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent>Live events: {status}</TooltipContent>
    </Tooltip>
  )
}

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const accessToken = useAuthStore((s) => s.accessToken)
  const wsConnect = useWsStore((s) => s.connect)
  const wsDisconnect = useWsStore((s) => s.disconnect)
  const navigate = useNavigate()

  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'
  const equipmentEnabled = useAddonStore((s) => s.isEnabled('equipment-inventory'))
  const floorPlanEnabled = useAddonStore((s) => s.isEnabled('floor-plan'))

  const { data: unacknowledgedAlerts } = useAlerts({ acknowledged: false, page_size: 1 })
  const { data: systemEvents } = useSystemEvents()

  const unreadCount = unacknowledgedAlerts?.total ?? 0
  const warningEvents = systemEvents?.items.filter((e) => e.level === 'warning' || e.level === 'error' || e.level === 'critical') ?? []

  useEffect(() => {
    if (accessToken) wsConnect(accessToken)
    return () => wsDisconnect()
  }, [accessToken, wsConnect, wsDisconnect])

  const handleLogout = async () => {
    wsDisconnect()
    await logout()
    navigate('/login')
  }

  const initials = user?.full_name
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase() ?? '?'

  return (
    <TooltipProvider>
      <div className="flex h-screen bg-background">
        {/* Sidebar */}
        <aside className={cn(
          'flex flex-col border-r bg-card transition-all duration-200',
          collapsed ? 'w-16' : 'w-56'
        )}>
          {/* Logo */}
          <div className={cn('flex h-14 items-center border-b px-3', collapsed ? 'justify-center' : 'justify-between')}>
            {!collapsed && (
              <div className="flex items-center gap-2">
                <Monitor className="h-5 w-5 text-primary" />
                <span className="font-semibold text-sm">NVR Pro</span>
              </div>
            )}
            {collapsed && <Monitor className="h-5 w-5 text-primary" />}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setCollapsed((v) => !v)}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            </Button>
          </div>

          {/* Nav items */}
          <nav className="flex-1 space-y-1 p-2 overflow-y-auto" aria-label="Main navigation">
            {NAV_ITEMS.map(({ to, icon: Icon, label, exact, adminOnly }) => {
              if (adminOnly && !isAdmin) return null
              return (
                <Tooltip key={to} delayDuration={0}>
                  <TooltipTrigger asChild>
                    <NavLink
                      to={to}
                      end={exact}
                      className={({ isActive }) => cn(
                        'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                        collapsed && 'justify-center px-2'
                      )}
                      aria-label={label}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span>{label}</span>}
                      {!collapsed && label === 'Alerts' && unreadCount > 0 && (
                        <Badge variant="destructive" className="ml-auto text-xs h-5 px-1.5">
                          {unreadCount > 99 ? '99+' : unreadCount}
                        </Badge>
                      )}
                      {collapsed && label === 'Alerts' && unreadCount > 0 && (
                        <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-destructive" />
                      )}
                    </NavLink>
                  </TooltipTrigger>
                  {collapsed && <TooltipContent side="right">{label}</TooltipContent>}
                </Tooltip>
              )
            })}
            {equipmentEnabled && (
              <Tooltip delayDuration={0}>
                <TooltipTrigger asChild>
                  <NavLink
                    to="/equipment"
                    className={({ isActive }) => cn(
                      'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                      collapsed && 'justify-center px-2'
                    )}
                    aria-label="Equipment"
                  >
                    <Server className="h-4 w-4 shrink-0" />
                    {!collapsed && <span>Inventory</span>}
                  </NavLink>
                </TooltipTrigger>
                {collapsed && <TooltipContent side="right">Inventory</TooltipContent>}
              </Tooltip>
            )}
            {floorPlanEnabled && (
              <Tooltip delayDuration={0}>
                <TooltipTrigger asChild>
                  <NavLink
                    to="/floor-plan"
                    className={({ isActive }) => cn(
                      'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                      collapsed && 'justify-center px-2'
                    )}
                    aria-label="Floor Plan"
                  >
                    <Building2 className="h-4 w-4 shrink-0" />
                    {!collapsed && <span>Floor Plan</span>}
                  </NavLink>
                </TooltipTrigger>
                {collapsed && <TooltipContent side="right">Floor Plan</TooltipContent>}
              </Tooltip>
            )}
          </nav>

          {/* Storage shortcut */}
          {!collapsed && (
            <>
              <Separator />
              <div className="p-2">
                <NavLink
                  to="/storage"
                  className={({ isActive }) => cn(
                    'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                  )}
                >
                  <HardDrive className="h-4 w-4" />
                  <span>Storage</span>
                </NavLink>
              </div>
            </>
          )}
        </aside>

        {/* Main area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Top bar */}
          <header className="flex h-14 items-center justify-between border-b bg-card px-4">
            {warningEvents.length > 0 && (
              <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded-md px-3 py-1">
                <Bell className="h-4 w-4" />
                <span>{warningEvents[0].message}</span>
              </div>
            )}
            {warningEvents.length === 0 && <div />}

            <div className="flex items-center gap-4">
              <SystemHealthBar />
              <WsIndicator />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="flex items-center gap-2 h-9 px-2">
                    <Avatar className="h-7 w-7">
                      <AvatarFallback className="text-xs">{initials}</AvatarFallback>
                    </Avatar>
                    <span className="hidden md:inline text-sm">{user?.full_name}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuLabel className="font-normal">
                    <div className="flex flex-col space-y-1">
                      <p className="text-sm font-medium">{user?.full_name}</p>
                      <p className="text-xs text-muted-foreground">{user?.email}</p>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate('/profile')}>
                    <User className="mr-2 h-4 w-4" />
                    Profile
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate('/sessions')}>
                    <Monitor className="mr-2 h-4 w-4" />
                    Sessions
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive">
                    <LogOut className="mr-2 h-4 w-4" />
                    Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </header>

          {/* Page content */}
          <main className="flex-1 overflow-y-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </TooltipProvider>
  )
}
