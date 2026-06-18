import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { RecordingSegment, RecordingExport, PaginatedResponse } from '@/types'

interface TimelineParams {
  camera_id: string
  date: string
}

interface SegmentsParams {
  camera_id: string
  started_after?: string
  started_before?: string
  segment_type?: string
  page?: number
  page_size?: number
}

interface BackendTimelineSegment {
  segment_id: string
  started_at: string
  ended_at: string | null
  duration_seconds: number | null
  segment_type: string | null
  file_size_bytes: number | null
}

interface BackendTimelineResponse {
  camera_id: string
  segments: BackendTimelineSegment[]
}

interface BackendCalendarDay {
  date: string
  has_recordings: boolean
}

interface BackendCalendarResponse {
  days: BackendCalendarDay[]
}

export function useTimeline(params: TimelineParams) {
  return useQuery({
    queryKey: ['timeline', params],
    queryFn: () =>
      api.get<BackendTimelineResponse>('/recordings/timeline', { params }).then((r) =>
        r.data.segments.map(
          (s): RecordingSegment => ({
            id: s.segment_id,
            camera_id: r.data.camera_id,
            started_at: s.started_at,
            ended_at: s.ended_at,
            segment_type: (s.segment_type ?? 'continuous') as RecordingSegment['segment_type'],
            file_path: '',
            size_bytes: s.file_size_bytes ?? 0,
            duration_s: s.duration_seconds,
          })
        )
      ),
    enabled: !!params.camera_id && !!params.date,
  })
}

export function useCalendar(cameraId: string, month: string) {
  return useQuery({
    queryKey: ['calendar', cameraId, month],
    queryFn: () =>
      api.get<BackendCalendarResponse>('/recordings/calendar', { params: { camera_id: cameraId, month } }).then(
        (r) => r.data.days.filter((d) => d.has_recordings).map((d) => String(d.date))
      ),
    enabled: !!cameraId && !!month,
  })
}

export function useSegments(params: SegmentsParams) {
  return useQuery({
    queryKey: ['segments', params],
    queryFn: () =>
      api.get<PaginatedResponse<RecordingSegment>>('/recordings/segments', { params }).then((r) => r.data),
    enabled: !!params.camera_id,
  })
}

export function useExportStatus(exportId: string | null) {
  return useQuery({
    queryKey: ['export', exportId],
    queryFn: () => api.get<RecordingExport>(`/exports/${exportId}`).then((r) => r.data),
    enabled: !!exportId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'processing' ? 2_000 : false
    },
  })
}

export function useCreateExport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: {
      camera_ids: string[]
      from_dt: string
      to_dt: string
      watermark?: boolean
      watermark_text?: string
      password_protected?: boolean
    }) => api.post<RecordingExport>('/exports', payload).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['export'] }),
  })
}
