import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { Equipment, EquipmentCreate } from '@/types'

const KEY = 'equipment'

export function useEquipment() {
  return useQuery<Equipment[]>({
    queryKey: [KEY],
    queryFn: () => api.get<Equipment[]>('/equipment').then((r) => r.data),
  })
}

export function useCreateEquipment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: EquipmentCreate) =>
      api.post<Equipment>('/equipment', body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUpdateEquipment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<EquipmentCreate> & { id: string }) =>
      api.patch<Equipment>(`/equipment/${id}`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useDeleteEquipment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/equipment/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}
