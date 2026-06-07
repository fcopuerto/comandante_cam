import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { AlertEvent, AlertStats, PaginatedResponse } from '@/types'

const ALERTS_KEY = 'alerts'

interface AlertFilters {
  page?: number
  page_size?: number
  camera_id?: string
  severity?: string
  rule?: string
  acknowledged?: boolean
  false_positive?: boolean
  started_after?: string
  started_before?: string
}

export function useAlerts(filters: AlertFilters = {}) {
  return useQuery({
    queryKey: [ALERTS_KEY, filters],
    queryFn: () =>
      api.get<PaginatedResponse<AlertEvent>>('/alerts', { params: filters }).then((r) => r.data),
  })
}

export function useAlertStats(period: '24h' | '7d' | '30d' = '24h') {
  return useQuery({
    queryKey: [ALERTS_KEY, 'stats', period],
    queryFn: () => api.get<AlertStats>('/alerts/stats', { params: { period } }).then((r) => r.data),
    staleTime: 60_000,
  })
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, notes }: { id: string; notes?: string }) =>
      api.patch<AlertEvent>(`/alerts/${id}/acknowledge`, { notes }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ALERTS_KEY] }),
  })
}

export function useLegalHold() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, hold }: { id: string; hold: boolean }) =>
      api.patch<AlertEvent>(`/alerts/${id}/legal-hold`, { legal_hold: hold }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ALERTS_KEY] }),
  })
}

export function useMarkFalsePositive() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, value }: { id: string; value: boolean }) =>
      api.patch<AlertEvent>(`/alerts/${id}/false-positive`, { false_positive: value }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ALERTS_KEY] }),
  })
}

export function useBulkAcknowledge() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) =>
      api.post('/alerts/bulk-acknowledge', { ids }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ALERTS_KEY] }),
  })
}

export function useBulkFalsePositive() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ids, value }: { ids: string[]; value: boolean }) =>
      api.post('/alerts/bulk-false-positive', { ids, value }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ALERTS_KEY] }),
  })
}
