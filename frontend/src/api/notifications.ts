import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'

export interface NotificationChannel {
  id: string
  type: 'email' | 'webhook' | 'slack' | 'telegram' | 'sms'
  name: string
  enabled: boolean
  config: Record<string, unknown>
  created_at: string
}

const KEY = 'notification-channels'

export function useNotificationChannels() {
  return useQuery({
    queryKey: [KEY],
    queryFn: () => api.get<NotificationChannel[]>('/notifications/channels').then((r) => r.data),
  })
}

export function useCreateChannel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Omit<NotificationChannel, 'id' | 'created_at'>) =>
      api.post<NotificationChannel>('/notifications/channels', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUpdateChannel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<NotificationChannel> & { id: string }) =>
      api.patch<NotificationChannel>(`/notifications/channels/${id}`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useDeleteChannel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/notifications/channels/${id}`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useTestChannel() {
  return useMutation({
    mutationFn: (id: string) =>
      api.post<{ success: boolean; message: string }>(`/notifications/channels/${id}/test`).then((r) => r.data),
  })
}
