import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Wifi, WifiOff, AlertTriangle } from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar,
} from 'recharts'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'

import CameraForm from '@/components/cameras/CameraForm'
import ZoneEditor from '@/components/cameras/ZoneEditor'
import { useCamera, useCameraStats, useCameraZones } from '@/api/cameras'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const HOURS = Array.from({ length: 24 }, (_, i) => i)

function WeeklyScheduleGrid({ schedule, onChange }: {
  schedule: boolean[][]
  onChange: (schedule: boolean[][]) => void
}) {
  const [dragging, setDragging] = useState(false)
  const [fillValue, setFillValue] = useState(true)

  const toggle = (day: number, hour: number) => {
    const next = schedule.map((d) => [...d])
    const newVal = !next[day][hour]
    next[day][hour] = newVal
    setFillValue(newVal)
    onChange(next)
  }

  const fill = (day: number, hour: number) => {
    if (!dragging) return
    const next = schedule.map((d) => [...d])
    next[day][hour] = fillValue
    onChange(next)
  }

  return (
    <div className="overflow-x-auto" onMouseUp={() => setDragging(false)}>
      <div className="min-w-[600px]">
        <div className="flex">
          <div className="w-10" />
          {DAYS.map((d) => (
            <div key={d} className="flex-1 text-center text-xs font-medium text-muted-foreground py-1">{d}</div>
          ))}
        </div>
        {HOURS.map((h) => (
          <div key={h} className="flex items-center">
            <div className="w-10 text-xs text-muted-foreground text-right pr-2">{String(h).padStart(2, '0')}</div>
            {DAYS.map((_, d) => (
              <div
                key={d}
                className={`flex-1 h-5 m-px rounded-sm cursor-pointer select-none transition-colors ${schedule[d]?.[h] ? 'bg-primary' : 'bg-muted hover:bg-muted-foreground/20'}`}
                onMouseDown={() => { setDragging(true); toggle(d, h) }}
                onMouseEnter={() => fill(d, h)}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function CameraDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [schedule, setSchedule] = useState<boolean[][]>(
    Array.from({ length: 7 }, () => Array(24).fill(false))
  )

  const { data: camera, isLoading } = useCamera(id!)
  const { data: stats } = useCameraStats(id!)
  const { data: zonesData } = useCameraZones(id!)

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (!camera) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <AlertTriangle className="h-10 w-10 text-muted-foreground" />
        <p className="text-muted-foreground">Camera not found</p>
        <Button variant="outline" onClick={() => navigate('/cameras')}>Back to cameras</Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/cameras')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-xl font-bold">{camera.name}</h1>
          <p className="text-sm text-muted-foreground">{camera.zone_location ?? ''}</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {camera.status === 'online'
            ? <Wifi className="h-4 w-4 text-green-500" />
            : <WifiOff className="h-4 w-4 text-muted-foreground" />}
          <Badge variant={camera.status === 'online' ? 'default' : 'secondary'}>{camera.status}</Badge>
          <Button size="sm" onClick={() => navigate(`/live?camera=${camera.id}`)}>View live</Button>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
          <TabsTrigger value="schedule">Schedule</TabsTrigger>
          <TabsTrigger value="detection">Detection</TabsTrigger>
          {camera.ptz_enabled && <TabsTrigger value="ptz">PTZ</TabsTrigger>}
          <TabsTrigger value="permissions">Permissions</TabsTrigger>
          <TabsTrigger value="stats">Stats</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview" className="mt-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-1"><CardTitle className="text-sm text-muted-foreground">Status</CardTitle></CardHeader>
              <CardContent><Badge variant={camera.status === 'online' ? 'default' : 'secondary'} className="capitalize">{camera.status}</Badge></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-1"><CardTitle className="text-sm text-muted-foreground">Recording</CardTitle></CardHeader>
              <CardContent><span className="text-sm capitalize">{camera.recording_mode}</span></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-1"><CardTitle className="text-sm text-muted-foreground">Resolution</CardTitle></CardHeader>
              <CardContent><span className="text-sm">{camera.resolution_main ?? '—'}</span></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-1"><CardTitle className="text-sm text-muted-foreground">Retention</CardTitle></CardHeader>
              <CardContent><span className="text-sm">{camera.retention_days} days</span></CardContent>
            </Card>
          </div>
          <Card className="mt-4">
            <CardHeader className="pb-2"><CardTitle className="text-sm">Connection</CardTitle></CardHeader>
            <CardContent className="text-sm space-y-1">
              <div className="flex gap-4">
                <span className="text-muted-foreground w-24">IP Address</span>
                <span className="font-mono">{camera.ip_address}:{camera.onvif_port}</span>
              </div>
              <div className="flex gap-4">
                <span className="text-muted-foreground w-24">Last seen</span>
                <span>{new Date(camera.updated_at).toLocaleString()}</span>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Settings */}
        <TabsContent value="settings" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              <CameraForm camera={camera} />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Schedule */}
        <TabsContent value="schedule" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recording Schedule</CardTitle>
              <p className="text-sm text-muted-foreground">Click or drag to set active recording hours</p>
            </CardHeader>
            <CardContent>
              <WeeklyScheduleGrid schedule={schedule} onChange={setSchedule} />
              <div className="flex justify-end mt-4">
                <Button size="sm">Save schedule</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Detection */}
        <TabsContent value="detection" className="mt-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Detection Zones</CardTitle>
                <div className="flex items-center gap-2">
                  <Switch id="det-enabled" defaultChecked />
                  <Label htmlFor="det-enabled" className="font-normal">Enable detection</Label>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <ZoneEditor cameraId={camera.id} initialZones={zonesData?.zones} />
            </CardContent>
          </Card>
        </TabsContent>

        {/* PTZ */}
        {camera.ptz_enabled && (
          <TabsContent value="ptz" className="mt-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex flex-col items-center gap-6">
                  <div className="grid grid-cols-3 gap-2 w-32">
                    <div />
                    <Button variant="outline" size="icon">▲</Button>
                    <div />
                    <Button variant="outline" size="icon">◀</Button>
                    <Button variant="outline" size="icon">⏺</Button>
                    <Button variant="outline" size="icon">▶</Button>
                    <div />
                    <Button variant="outline" size="icon">▼</Button>
                    <div />
                  </div>
                  <div className="text-sm text-muted-foreground">PTZ controls — connect to camera to use</div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}

        {/* Permissions */}
        <TabsContent value="permissions" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Camera permissions matrix — managed in user settings.</p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Stats */}
        <TabsContent value="stats" className="mt-4">
          <div className="space-y-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Recording hours (last 30 days)</CardTitle></CardHeader>
              <CardContent>
                {stats?.recording_hours ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <AreaChart data={stats.recording_hours}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d) => d.slice(5)} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Area type="monotone" dataKey="hours" stroke="#3b82f6" fill="#3b82f633" />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : <Skeleton className="h-44" />}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Alert frequency by hour</CardTitle></CardHeader>
              <CardContent>
                {stats?.alert_frequency ? (
                  <ResponsiveContainer width="100%" height={140}>
                    <BarChart data={stats.alert_frequency}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="hour" tick={{ fontSize: 10 }} tickFormatter={(h) => `${h}h`} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#ef4444" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : <Skeleton className="h-32" />}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
