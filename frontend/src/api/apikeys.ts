import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'

export interface ApiKey {
  id: string
  name: string
  prefix: string
  permissions: string[]
  created_at: string
  last_used_at: string | null
  expires_at: string | null
}

export interface ApiKeyCreated extends ApiKey {
  key: string
}

const KEY = 'api-keys'

export function useApiKeys() {
  return useQuery({
    queryKey: [KEY],
    queryFn: () => api.get<ApiKey[]>('/system/api-keys').then((r) => r.data),
  })
}

export function useCreateApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; permissions: string[]; expires_at?: string }) =>
      api.post<ApiKeyCreated>('/system/api-keys', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useRevokeApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/system/api-keys/${id}`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}
