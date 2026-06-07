import { useInfiniteQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import type { AuditEntry, PaginatedResponse } from '@/types'

interface AuditFilters {
  actor_id?: string
  action?: string
  resource_type?: string
  started_after?: string
  started_before?: string
  page_size?: number
}

export function useAuditLog(filters: AuditFilters = {}) {
  return useInfiniteQuery({
    queryKey: ['audit', filters],
    queryFn: ({ pageParam = 1 }) =>
      api
        .get<PaginatedResponse<AuditEntry>>('/audit', {
          params: { ...filters, page: pageParam, page_size: filters.page_size ?? 50 },
        })
        .then((r) => r.data),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page < last.pages ? last.page + 1 : undefined,
  })
}
