import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { Building, CameraPlacement, Floor } from '@/types'

// ── Buildings ─────────────────────────────────────────────────────────────────

export function useBuildings() {
  return useQuery<Building[]>({
    queryKey: ['buildings'],
    queryFn: () => api.get('/floor-plan/buildings').then((r) => r.data),
  })
}

export function useCreateBuilding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; description?: string; address?: string }) =>
      api.post<Building>('/floor-plan/buildings', body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['buildings'] }),
  })
}

export function useUpdateBuilding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; description?: string; address?: string }) =>
      api.patch<Building>(`/floor-plan/buildings/${id}`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['buildings'] }),
  })
}

export function useDeleteBuilding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/floor-plan/buildings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['buildings'] }),
  })
}

// ── Floors ────────────────────────────────────────────────────────────────────

export function useFloors(buildingId: string | null) {
  return useQuery<Floor[]>({
    queryKey: ['floors', buildingId],
    queryFn: () => api.get(`/floor-plan/buildings/${buildingId}/floors`).then((r) => r.data),
    enabled: !!buildingId,
  })
}

export function useCreateFloor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ buildingId, name, level }: { buildingId: string; name: string; level: number }) =>
      api.post<Floor>(`/floor-plan/buildings/${buildingId}/floors`, { name, level }).then((r) => r.data),
    onSuccess: (_data, vars) => qc.invalidateQueries({ queryKey: ['floors', vars.buildingId] }),
  })
}

export function useUpdateFloor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      buildingId,
      ...body
    }: { id: string; buildingId: string; name?: string; level?: number }) =>
      api.patch<Floor>(`/floor-plan/floors/${id}`, body).then((r) => r.data),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['floors', vars.buildingId] })
    },
  })
}

export function useDeleteFloor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, buildingId }: { id: string; buildingId: string }) =>
      api.delete(`/floor-plan/floors/${id}`).then(() => ({ buildingId })),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['floors', vars.buildingId] })
      qc.invalidateQueries({ queryKey: ['placements'] })
    },
  })
}

export function useUploadFloorImage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ floorId, file }: { floorId: string; buildingId: string; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      return api
        .post<Floor>(`/floor-plan/floors/${floorId}/image`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data)
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['floors', vars.buildingId] })
    },
  })
}

export function floorImageUrl(floorId: string) {
  return `/api/v1/floor-plan/floors/${floorId}/image`
}

// ── Placements ────────────────────────────────────────────────────────────────

export function usePlacements(floorId: string | null) {
  return useQuery<CameraPlacement[]>({
    queryKey: ['placements', floorId],
    queryFn: () => api.get(`/floor-plan/floors/${floorId}/placements`).then((r) => r.data),
    enabled: !!floorId,
    refetchInterval: 10000,
  })
}

export function useCreatePlacement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      floorId,
      cameraId,
      x,
      y,
      rotation,
    }: { floorId: string; cameraId: string; x: number; y: number; rotation: number }) =>
      api
        .post<CameraPlacement>(`/floor-plan/floors/${floorId}/placements`, {
          camera_id: cameraId,
          x,
          y,
          rotation,
        })
        .then((r) => r.data),
    onSuccess: (_data, vars) => qc.invalidateQueries({ queryKey: ['placements', vars.floorId] }),
  })
}

export function useUpdatePlacement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      x,
      y,
      rotation,
    }: { id: string; floorId: string; x?: number; y?: number; rotation?: number }) =>
      api
        .patch<CameraPlacement>(`/floor-plan/placements/${id}`, { x, y, rotation })
        .then((r) => r.data),
    onSuccess: (_data, vars) => qc.invalidateQueries({ queryKey: ['placements', vars.floorId] }),
  })
}

export function useDeletePlacement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, floorId }: { id: string; floorId: string }) =>
      api.delete(`/floor-plan/placements/${id}`).then(() => ({ floorId })),
    onSuccess: (_data, vars) => qc.invalidateQueries({ queryKey: ['placements', vars.floorId] }),
  })
}
