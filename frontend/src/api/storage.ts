import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'

export interface StorageTarget {
  id: string
  name: string
  target_type: 'nfs' | 'smb' | 'local'
  host: string | null
  export_path: string
  mount_point: string
  mount_options: string | null
  is_active: boolean
  created_at: string
  mounted: boolean
  writable: boolean
  total_bytes: number | null
  used_bytes: number | null
  free_bytes: number | null
  usage_percent: number | null
  fstab_line: string
}

export interface StorageTargetCreate {
  name: string
  target_type: 'nfs' | 'smb' | 'local'
  host?: string
  export_path: string
  mount_point: string
  mount_options?: string
}

const KEY = ['storage', 'targets']

export function useStorageTargets() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api.get<StorageTarget[]>('/storage/targets').then((r) => r.data),
    refetchInterval: 30_000,
  })
}

export function useCreateStorageTarget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: StorageTargetCreate) =>
      api.post<StorageTarget>('/storage/targets', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteStorageTarget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/storage/targets/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useActivateStorageTarget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.post<StorageTarget>(`/storage/targets/${id}/activate`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1e12) return `${(bytes / 1e12).toFixed(1)} TB`
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`
  return `${bytes} B`
}
