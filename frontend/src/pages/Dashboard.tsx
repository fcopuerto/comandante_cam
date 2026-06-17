import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { PlusCircle, Video, Download, AlertTriangle, CheckCircle, XCircle, Minus } from 'lucide-react'
import { PieChart, Pie, Cell, Tooltip } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useSystemHealth, useStorageStatus } from '@/api/system'
import { useCameras } from '@/api/cameras'
import { useAlerts, useAlertStats } from '@/api/alerts'
import { useWsStore } from '@/store/wsStore'
import type { AlertEvent } from '@/types'
import { formatDistanceToNow } from 'date-fns'

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
}

const STORAGE_COLORS = ['#3b82f6', '#e5e7eb']

function HealthDot({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? 'bg-green-500' : 'bg-red-500'}`} />
  )
}

function ServiceStatus({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1.5">
        <HealthDot ok={ok} />
        <span className={`text-xs font-medium ${ok ? 'text-green-600' : 'text-red-600'}`}>
          {ok ? 'OK' : 'Error'}
        </span>
      </div>
    </div>
  )
}

function bytes(n: number): string {
  if (n >= 1e12) return `${(n / 1e12).toFixed(1)} TB`
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`
  return `${(n / 1e6).toFixed(0)} MB`
}

export default function Dashboard() {
  const navigate = useNavigate()
  const alertFeedRef = useRef<HTMLDivElement>(null)

  const { data: health, isLoading: healthLoading } = useSystemHealth()
  const { data: storage, isLoading: storageLoading } = useStorageStatus()
  const { data: cameras, isLoading: camerasLoading } = useCameras({ page_size: 100 })
  const { data: recentAlerts, isLoading: alertsLoading } = useAlerts({
    page_size: 10,
    acknowledged: false,
  })
  const { data: alertStats } = useAlertStats('24h')

  const subscribe = useWsStore((s) => s.subscribe)

  useEffect(() => {
    const unsub = subscribe('alert', (_payload) => {
      if (alertFeedRef.current) {
        alertFeedRef.current.scrollTop = 0
      }
    })
    return unsub
  }, [subscribe])

  const onlineCameras = cameras?.items.filter((c) => c.status === 'online' || c.status === 'recording').length ?? 0
  const totalCameras = cameras?.total ?? 0
  const recordingCameras = cameras?.items.filter((c) => c.recording_mode !== 'off').length ?? 0

  const storageData = storage
    ? [
        { name: 'Used', value: storage.used_bytes },
        { name: 'Free', value: storage.free_bytes },
      ]
    : []

  const severityData = alertStats
    ? Object.entries(alertStats.by_severity).map(([k, v]) => ({ name: k, value: v }))
    : []

  return (
    <div className="space-y-6" data-testid="dashboard">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate('/cameras/new')}>
            <PlusCircle className="h-4 w-4 mr-1.5" />
            Add camera
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate('/live')}>
            <Video className="h-4 w-4 mr-1.5" />
            View live
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate('/recordings')}>
            <Download className="h-4 w-4 mr-1.5" />
            Export clip
          </Button>
        </div>
      </div>

      {/* System health */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">System Health</CardTitle>
        </CardHeader>
        <CardContent>
          {healthLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-8" />)}
            </div>
          ) : health ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-0 divide-x">
              <ServiceStatus label="Database" ok={health.database} />
              <div className="pl-8"><ServiceStatus label="Redis" ok={health.redis} /></div>
              <div className="pl-8"><ServiceStatus label="Celery workers" ok={health.celery} /></div>
              <div className="pl-8"><ServiceStatus label="Detection" ok={health.detection} /></div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Unable to load health data</p>
          )}
          {health?.storage_critical && (
            <div className="mt-3 flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded p-2">
              <XCircle className="h-4 w-4" />
              Storage critical — recordings may stop
            </div>
          )}
          {health?.storage_warning && !health.storage_critical && (
            <div className="mt-3 flex items-center gap-2 text-sm text-amber-600 bg-amber-50 rounded p-2">
              <AlertTriangle className="h-4 w-4" />
              Storage warning — check retention settings
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Storage widget */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Storage</CardTitle>
          </CardHeader>
          <CardContent>
            {storageLoading ? (
              <Skeleton className="h-32" />
            ) : storage ? (
              <div className="flex items-center gap-4">
                <PieChart width={120} height={120}>
                  <Pie
                    data={storageData}
                    cx={60}
                    cy={60}
                    innerRadius={35}
                    outerRadius={55}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {storageData.map((_, i) => (
                      <Cell key={i} fill={STORAGE_COLORS[i]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => bytes(v)} />
                </PieChart>
                <div className="space-y-1 text-sm">
                  <div><span className="text-muted-foreground">Used: </span>{bytes(storage.used_bytes)}</div>
                  <div><span className="text-muted-foreground">Free: </span>{bytes(storage.free_bytes)}</div>
                  <div><span className="text-muted-foreground">Total: </span>{bytes(storage.total_bytes)}</div>
                  <div className="font-medium">{storage.usage_percent.toFixed(1)}% used</div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No storage data</p>
            )}
          </CardContent>
        </Card>

        {/* Camera status */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Cameras</CardTitle>
          </CardHeader>
          <CardContent>
            {camerasLoading ? (
              <Skeleton className="h-32" />
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-md bg-green-50 p-3 text-center">
                    <div className="text-2xl font-bold text-green-700">{onlineCameras}</div>
                    <div className="text-xs text-green-600">Online</div>
                  </div>
                  <div className="rounded-md bg-muted p-3 text-center">
                    <div className="text-2xl font-bold">{totalCameras - onlineCameras}</div>
                    <div className="text-xs text-muted-foreground">Offline</div>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>{recordingCameras} of {totalCameras} recording</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Alert summary */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Alert Summary (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            {!alertStats ? (
              <Skeleton className="h-32" />
            ) : (
              <div className="space-y-2">
                {severityData.length > 0 ? (
                  severityData.map(({ name, value }) => (
                    <div key={name} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <span
                          className="h-3 w-3 rounded-full"
                          style={{ backgroundColor: SEVERITY_COLORS[name] }}
                        />
                        <span className="capitalize">{name}</span>
                      </div>
                      <Badge variant={name === 'critical' ? 'destructive' : 'secondary'}>{value}</Badge>
                    </div>
                  ))
                ) : (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Minus className="h-4 w-4" />
                    No alerts in last 24h
                  </div>
                )}
                {alertStats.unacknowledged > 0 && (
                  <Button variant="outline" size="sm" className="w-full mt-2" onClick={() => navigate('/alerts')}>
                    {alertStats.unacknowledged} unacknowledged
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recording activity heatmap */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Recording Coverage — Today</CardTitle>
        </CardHeader>
        <CardContent>
          {camerasLoading ? (
            <Skeleton className="h-32" />
          ) : (
            <div className="overflow-x-auto">
              <div className="min-w-[600px]">
                {/* Hours header */}
                <div className="flex mb-1 pl-24">
                  {[0, 4, 8, 12, 16, 20].map((h) => (
                    <div key={h} className="flex-1 text-xs text-muted-foreground text-center">
                      {String(h).padStart(2, '0')}:00
                    </div>
                  ))}
                </div>
                {/* Camera rows */}
                <div className="space-y-1">
                  {(cameras?.items.slice(0, 8) ?? []).map((cam) => (
                    <div key={cam.id} className="flex items-center gap-2">
                      <div className="w-24 text-xs text-muted-foreground truncate text-right pr-2">
                        {cam.name}
                      </div>
                      <div className="flex-1 flex gap-px">
                        {Array.from({ length: 24 }).map((_, h) => (
                          <div
                            key={h}
                            className={`flex-1 h-5 rounded-sm ${
                              (cam.status === 'online' || cam.status === 'recording') && cam.recording_mode !== 'off'
                                ? 'bg-blue-400'
                                : 'bg-muted'
                            }`}
                            title={`${cam.name} ${String(h).padStart(2, '0')}:00`}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                  {(cameras?.total ?? 0) === 0 && (
                    <p className="text-sm text-muted-foreground py-4 text-center">
                      No cameras configured
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent alerts feed */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Recent Alerts</CardTitle>
        </CardHeader>
        <CardContent>
          <div
            ref={alertFeedRef}
            className="space-y-2 max-h-80 overflow-y-auto"
            aria-live="polite"
            aria-label="Recent alerts"
          >
            {alertsLoading ? (
              [...Array(4)].map((_, i) => <Skeleton key={i} className="h-12" />)
            ) : recentAlerts && recentAlerts.items.length > 0 ? (
              recentAlerts.items.map((alert: AlertEvent) => (
                <div
                  key={alert.id}
                  className="flex items-start justify-between p-3 rounded-md border cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() => navigate(`/alerts?id=${alert.id}`)}
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-full shrink-0"
                        style={{ backgroundColor: SEVERITY_COLORS[alert.severity] }}
                      />
                      <span className="text-sm font-medium">{alert.rule_triggered.replace(/_/g, ' ')}</span>
                      <Badge
                        variant={alert.severity === 'critical' ? 'destructive' : 'secondary'}
                        className="text-xs"
                      >
                        {alert.severity}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {alert.camera_name}{alert.zone_name ? ` · ${alert.zone_name}` : ''}
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap ml-4">
                    {formatDistanceToNow(new Date(alert.triggered_at), { addSuffix: true })}
                  </span>
                </div>
              ))
            ) : (
              <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                <CheckCircle className="h-4 w-4 mr-2 text-green-500" />
                No unacknowledged alerts
              </div>
            )}
          </div>
          {(recentAlerts?.total ?? 0) > 0 && (
            <Button variant="outline" size="sm" className="w-full mt-3" onClick={() => navigate('/alerts')}>
              View all alerts
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
