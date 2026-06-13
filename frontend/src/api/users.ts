import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { User, Role, UserSession, CameraPermission, PaginatedResponse } from '@/types'

const USERS_KEY = 'users'

interface UserFilters {
  page?: number
  page_size?: number
  role?: string
  is_active?: boolean
}

export function useUsers(filters: UserFilters = {}) {
  return useQuery({
    queryKey: [USERS_KEY, filters],
    queryFn: () =>
      api.get<PaginatedResponse<User>>('/users', { params: filters }).then((r) => r.data),
  })
}

export function useUser(id: string) {
  return useQuery({
    queryKey: [USERS_KEY, id],
    queryFn: () => api.get<User>(`/users/${id}`).then((r) => r.data),
    enabled: !!id,
  })
}

export function useCreateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { email: string; full_name: string; role: string; password: string }) =>
      api.post<User>('/users', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [USERS_KEY] }),
  })
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<User> & { id: string }) =>
      api.patch<User>(`/users/${id}`, data).then((r) => r.data),
    onSuccess: (user) => {
      qc.invalidateQueries({ queryKey: [USERS_KEY] })
      qc.setQueryData([USERS_KEY, user.id], user)
    },
  })
}

export function useDeactivateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.post(`/users/${id}/deactivate`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [USERS_KEY] }),
  })
}

export function useDeleteUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/users/${id}`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [USERS_KEY] }),
  })
}

export function useInviteUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { email: string; full_name: string; role: string }) =>
      api.post<User>('/users/invite', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [USERS_KEY] }),
  })
}

export function useRoles() {
  return useQuery({
    queryKey: [USERS_KEY, 'roles'],
    queryFn: () => api.get<Role[]>('/roles').then((r) => r.data),
    staleTime: 300_000,
  })
}

export function useUserSessions(userId: string) {
  return useQuery({
    queryKey: [USERS_KEY, userId, 'sessions'],
    queryFn: () => api.get<UserSession[]>(`/users/${userId}/sessions`).then((r) => r.data),
    enabled: !!userId,
  })
}

export function useRevokeSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, sessionId }: { userId: string; sessionId: string }) =>
      api.delete(`/users/${userId}/sessions/${sessionId}`).then((r) => r.data),
    onSuccess: (_data, { userId }) =>
      qc.invalidateQueries({ queryKey: [USERS_KEY, userId, 'sessions'] }),
  })
}

export function useCameraPermissions(userId: string) {
  return useQuery({
    queryKey: [USERS_KEY, userId, 'camera-permissions'],
    queryFn: () =>
      api.get<CameraPermission[]>(`/users/${userId}/camera-permissions`).then((r) => r.data),
    enabled: !!userId,
  })
}

export function useUpdateCameraPermission() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      userId,
      cameraId,
      ...data
    }: { userId: string; cameraId: string } & Partial<Omit<CameraPermission, 'camera_id' | 'camera_name'>>) =>
      api.put(`/users/${userId}/camera-permissions/${cameraId}`, data).then((r) => r.data),
    onSuccess: (_data, { userId }) =>
      qc.invalidateQueries({ queryKey: [USERS_KEY, userId, 'camera-permissions'] }),
  })
}
