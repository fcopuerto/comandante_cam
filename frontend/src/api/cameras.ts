import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { Camera, DiscoveredCamera, PaginatedResponse } from '@/types'

const CAMERAS_KEY = 'cameras'

interface CameraFilters {
  page?: number
  page_size?: number
  status?: string
  group?: string
}

export function useCameras(filters: CameraFilters = {}) {
  return useQuery({
    queryKey: [CAMERAS_KEY, filters],
    queryFn: () => api.get<PaginatedResponse<Camera>>('/cameras', { params: filters }).then((r) => r.data),
  })
}

export function useCamera(id: string) {
  return useQuery({
    queryKey: [CAMERAS_KEY, id],
    queryFn: () => api.get<Camera>(`/cameras/${id}`).then((r) => r.data),
    enabled: !!id,
  })
}

export function useCreateCamera() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Camera>) => api.post<Camera>('/cameras', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [CAMERAS_KEY] }),
  })
}

export function useUpdateCamera() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<Camera> & { id: string }) =>
      api.patch<Camera>(`/cameras/${id}`, data).then((r) => r.data),
    onSuccess: (cam) => {
      qc.invalidateQueries({ queryKey: [CAMERAS_KEY] })
      qc.setQueryData([CAMERAS_KEY, cam.id], cam)
    },
  })
}

export function useDiscoverCameras() {
  return useMutation({
    mutationFn: (subnet: string) =>
      api.post<DiscoveredCamera[]>('/cameras/discover', { subnet }).then((r) => r.data),
  })
}

export function useTestConnection() {
  return useMutation({
    mutationFn: (id: string) =>
      api.post<{ onvif: boolean; rtsp: boolean; error?: string }>(`/cameras/${id}/test-connection`).then((r) => r.data),
  })
}

export function useTestConnectionData() {
  return useMutation({
    mutationFn: (data: { ip_address: string; port: number; username: string; password: string }) =>
      api.post<{ onvif: boolean; rtsp: boolean; error?: string }>('/cameras/test-connection', data).then((r) => r.data),
  })
}

export function useSyncTime() {
  return useMutation({
    mutationFn: (id: string) => api.post(`/cameras/${id}/sync-time`).then((r) => r.data),
  })
}

export function useCameraZones(id: string) {
  return useQuery({
    queryKey: [CAMERAS_KEY, id, 'zones'],
    queryFn: () => api.get<import('@/types').Zone[]>(`/cameras/${id}/zones`).then((r) => ({ zones: r.data })),
    enabled: !!id,
  })
}

export function useUpdateCameraZones() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, zones }: { id: string; zones: import('@/types').Zone[] }) =>
      api.put(`/cameras/${id}/zones`, { zones }).then((r) => r.data),
    onSuccess: (_data, { id }) => qc.invalidateQueries({ queryKey: [CAMERAS_KEY, id, 'zones'] }),
  })
}

export function useCameraStats(id: string) {
  return useQuery({
    queryKey: [CAMERAS_KEY, id, 'stats'],
    queryFn: () => api.get<import('@/types').CameraStats>(`/cameras/${id}/stats`).then((r) => r.data),
    enabled: !!id,
  })
}

export function useSnapshot(id: string) {
  return useQuery({
    queryKey: [CAMERAS_KEY, id, 'snapshot'],
    queryFn: () =>
      api
        .get(`/cameras/${id}/snapshot`, { responseType: 'blob' })
        .then((r) => ({ url: URL.createObjectURL(r.data as Blob) })),
    enabled: !!id,
    staleTime: 30_000,
    gcTime: 60_000,
  })
}
