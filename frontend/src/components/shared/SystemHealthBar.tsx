import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSystemHealth } from '@/api/system'
import { useWsStore } from '@/store/wsStore'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { SystemHealth } from '@/types'

const SERVICES: { key: keyof SystemHealth; label: string }[] = [
  { key: 'database', label: 'Database' },
  { key: 'redis', label: 'Cache' },
  { key: 'celery', label: 'Workers' },
  { key: 'detection', label: 'Detection' },
]

function DotColor({ healthy, isLoading }: { healthy: boolean; isLoading: boolean }) {
  if (isLoading) return <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-400 animate-pulse" />
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${healthy ? 'bg-green-500' : 'bg-red-500'}`}
    />
  )
}

function StorageBadge({ health }: { health: SystemHealth }) {
  if (health.storage_critical) {
    return <Badge variant="destructive">Critical</Badge>
  }
  if (health.storage_warning) {
    return <Badge className="bg-amber-400 text-amber-950 hover:bg-amber-400/80">Warning</Badge>
  }
  return <Badge className="bg-green-500 text-white hover:bg-green-500/80">OK</Badge>
}

export default function SystemHealthBar() {
  const { data: health, isLoading } = useSystemHealth()
  const { subscribe } = useWsStore()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const unsub = subscribe('system_event', (payload) => {
      const event = payload as { level?: string }
      if (event?.level === 'error' || event?.level === 'critical') {
        queryClient.invalidateQueries({ queryKey: ['system', 'health'] })
      }
    })
    return unsub
  }, [subscribe, queryClient])

  return (
    <TooltipProvider delayDuration={300}>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded px-2 py-1 hover:bg-muted/50 transition-colors"
      >
        {SERVICES.map(({ key, label }) => (
          <Tooltip key={key}>
            <TooltipTrigger asChild>
              <span className="flex items-center">
                <DotColor
                  healthy={health ? !!health[key] : false}
                  isLoading={isLoading}
                />
              </span>
            </TooltipTrigger>
            <TooltipContent>{label}</TooltipContent>
          </Tooltip>
        ))}
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>System Health</DialogTitle>
          </DialogHeader>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="py-2 text-left font-medium text-muted-foreground">Service</th>
                <th className="py-2 text-left font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody>
              {SERVICES.map(({ key, label }) => (
                <tr key={key} className="border-b last:border-0">
                  <td className="py-2">{label}</td>
                  <td className="py-2">
                    {isLoading ? (
                      <Badge className="bg-amber-400 text-amber-950">Checking</Badge>
                    ) : health?.[key] ? (
                      <Badge className="bg-green-500 text-white hover:bg-green-500/80">Healthy</Badge>
                    ) : (
                      <Badge variant="destructive">Down</Badge>
                    )}
                  </td>
                </tr>
              ))}
              <tr>
                <td className="py-2">Storage</td>
                <td className="py-2">
                  {health ? <StorageBadge health={health} /> : <Badge className="bg-amber-400 text-amber-950">Checking</Badge>}
                </td>
              </tr>
            </tbody>
          </table>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  )
}
