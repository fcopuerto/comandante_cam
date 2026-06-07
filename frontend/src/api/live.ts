import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import type { StreamInfo } from '@/types'

export function useStreamUrl(cameraId: string) {
  return useQuery({
    queryKey: ['stream', cameraId],
    queryFn: () => api.get<StreamInfo>(`/live/${cameraId}/stream-url`).then((r) => r.data),
    enabled: !!cameraId,
    refetchInterval: 10_000,
  })
}

export function useActiveStreams() {
  return useQuery({
    queryKey: ['streams', 'active'],
    queryFn: () => api.get<StreamInfo[]>('/live/active').then((r) => r.data),
    refetchInterval: 30_000,
  })
}
