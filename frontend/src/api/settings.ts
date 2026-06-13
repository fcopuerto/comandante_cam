import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'

export interface AppSettings {
  retention_days_default: number
  session_timeout_minutes: number
  mfa_enforcement: boolean
  watermark_exports: boolean
  max_export_size_gb: number
  storage_warning_threshold: number
  storage_critical_threshold: number
  smtp_host: string
  smtp_port: number
  smtp_starttls: boolean
  smtp_user: string
  smtp_password: string
  smtp_from: string
}

export interface PurgePreview {
  days: number
  bytes_freed: number
  segments_deleted: number
}

const SETTINGS_KEY = 'settings'

export function useSettings() {
  return useQuery({
    queryKey: [SETTINGS_KEY],
    queryFn: () => api.get<AppSettings>('/system/settings').then((r) => r.data),
    staleTime: 60_000,
  })
}

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<AppSettings>) =>
      api.patch<AppSettings>('/system/settings', data).then((r) => r.data),
    onSuccess: (settings) => qc.setQueryData([SETTINGS_KEY], settings),
  })
}

export function usePurgePreview(cameraId: string | null, days: number) {
  return useQuery({
    queryKey: ['purge-preview', cameraId, days],
    queryFn: () =>
      api
        .get<PurgePreview>('/recordings/purge-preview', {
          params: { camera_id: cameraId, days },
        })
        .then((r) => r.data),
    enabled: days > 0,
    staleTime: 10_000,
  })
}

export function useRequestPurge() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ cameraId, days }: { cameraId: string | null; days: number }) =>
      api.post('/recordings/purge', { camera_id: cameraId, days }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['system', 'storage'] })
      qc.invalidateQueries({ queryKey: ['segments'] })
    },
  })
}

export function useCancelExport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (exportId: string) =>
      api.delete(`/recordings/exports/${exportId}`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['export'] }),
  })
}

export function useStorageTrend() {
  return useQuery({
    queryKey: ['system', 'storage-trend'],
    queryFn: () =>
      api
        .get<Array<{ date: string; total_bytes: number; by_camera: Record<string, number> }>>(
          '/system/storage/trend'
        )
        .then((r) => r.data),
    staleTime: 300_000,
  })
}
