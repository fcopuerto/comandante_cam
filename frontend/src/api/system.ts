import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { SystemHealth, StorageStatus, SystemEvent, PaginatedResponse } from '@/types'

export interface DetectionStatus {
  container_state: string
  healthy: boolean
  last_heartbeat: string | null
  heartbeat_age_seconds: number | null
  cameras_active: number | null
}

export function useSystemHealth() {
  return useQuery({
    queryKey: ['system', 'health'],
    queryFn: () => api.get<SystemHealth>('/system/health').then((r) => r.data),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })
}

export function useStorageStatus() {
  return useQuery({
    queryKey: ['system', 'storage'],
    queryFn: () => api.get<StorageStatus>('/system/storage').then((r) => r.data),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useDetectionStatus() {
  return useQuery({
    queryKey: ['system', 'detection'],
    queryFn: () => api.get<DetectionStatus>('/system/detection/status').then((r) => r.data),
    refetchInterval: 10_000,
    staleTime: 5_000,
  })
}

export function useRestartDetection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ status: string; container_name: string }>('/system/detection/restart').then((r) => r.data),
    onSuccess: () => {
      // Re-poll status after restart
      setTimeout(() => qc.invalidateQueries({ queryKey: ['system', 'detection'] }), 3_000)
    },
  })
}

export interface WorkerStatus {
  online: boolean
  worker_name: string | null
  active_tasks: number
  recording_count: number
  alert_consumer_running: boolean
  container_state: string
}

export function useWorkerStatus() {
  return useQuery({
    queryKey: ['system', 'workers'],
    queryFn: () => api.get<WorkerStatus>('/system/workers/status').then((r) => r.data),
    refetchInterval: 15_000,
    staleTime: 10_000,
  })
}

export function useRestartWorker() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ status: string; container_name: string }>('/system/workers/restart').then((r) => r.data),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ['system', 'workers'] }), 3_000)
    },
  })
}

export function useSystemEvents(page = 1) {
  return useQuery({
    queryKey: ['system', 'events', page],
    queryFn: () =>
      api.get<PaginatedResponse<SystemEvent>>('/system/events', { params: { page, page_size: 20 } }).then((r) => r.data),
  })
}
