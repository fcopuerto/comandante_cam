import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useWsStore } from '@/store/wsStore'
import { useToast } from '@/components/ui/use-toast'
import { ToastAction } from '@/components/ui/toast'
import type { AlertEvent } from '@/types'

export default function NotificationToast() {
  const { subscribe } = useWsStore()
  const { toast } = useToast()
  const navigate = useNavigate()

  useEffect(() => {
    const unsub = subscribe('alert', (payload) => {
      const alert = payload as AlertEvent
      toast({
        title: `${alert.camera_name} — ${alert.rule_triggered}`,
        description: `Severity: ${alert.severity}`,
        duration: alert.severity === 'critical' ? Infinity : 5000,
        variant: ['critical', 'high'].includes(alert.severity) ? 'destructive' : 'default',
        action: (
          <ToastAction altText="View alert" onClick={() => navigate('/alerts')}>
            View
          </ToastAction>
        ),
      })
    })
    return unsub
  }, [subscribe, toast, navigate])

  return null
}
