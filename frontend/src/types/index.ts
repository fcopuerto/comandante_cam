export type CameraStatus = 'online' | 'offline' | 'error' | 'recording' | 'unauthorized' | 'unknown'

export interface DiscoveredCamera {
  ip: string
  port: number
  xaddrs: string[]
  manufacturer: string | null
  model: string | null
}
export type DeviceType = 'camera' | 'raspberry_pi' | 'display' | 'switch' | 'other'

export interface Equipment {
  id: string
  name: string
  ip_address: string
  ssh_port: number
  ssh_user: string
  has_ssh_password: boolean
  ssh_key_path: string | null
  device_type: DeviceType
  location: string | null
  notes: string | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export interface EquipmentCreate {
  name: string
  ip_address: string
  ssh_port?: number
  ssh_user?: string
  ssh_password?: string
  ssh_key_path?: string
  device_type?: DeviceType
  location?: string
  notes?: string
}

export type RecordingMode = 'continuous' | 'motion' | 'scheduled' | 'disabled'
export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical'
export type SegmentType = 'continuous' | 'motion' | 'event'

export interface Camera {
  id: string
  name: string
  description: string | null
  ip_address: string
  onvif_port: number
  rtsp_main_url: string | null
  rtsp_sub_url: string | null
  zone_location: string | null
  group_id: string | null
  status: CameraStatus
  recording_mode: RecordingMode
  ptz_enabled: boolean
  resolution_main: string | null
  fps: number
  bitrate_kbps: number
  retention_days: number
  manufacturer: string | null
  model: string | null
  notes: string | null
  detection_enabled: boolean
  tags: string[]
  created_at: string
  updated_at: string
}

export interface AlertEvent {
  id: string
  camera_id: string
  camera_name: string
  rule_triggered: string
  severity: AlertSeverity
  zone_name: string | null
  class_name: string | null
  confidence: number | null
  track_id: number | null
  triggered_at: string
  acknowledged: boolean
  acknowledged_by: string | null
  acknowledged_at: string | null
  false_positive: boolean
  legal_hold: boolean
  clip_path: string | null
  frame_path: string | null
  notes: string | null
}

export interface AlertStats {
  total: number
  unacknowledged: number
  by_severity: Record<AlertSeverity, number>
  by_camera: Record<string, number>
  by_rule: Record<string, number>
  by_hour: Array<{ hour: string; count: number }>
}

export interface User {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  mfa_enabled: boolean
  last_login: string | null
  created_at: string
}

export interface RecordingSegment {
  id: string
  camera_id: string
  started_at: string
  ended_at: string | null
  segment_type: SegmentType
  file_path: string
  size_bytes: number
  duration_s: number | null
}

export interface RecordingExport {
  id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress_percent: number
  file_path: string | null
  file_size_bytes: number | null
  sha256: string | null
  download_url: string | null
  created_at: string
  expires_at: string | null
}

export interface SystemHealth {
  database: boolean
  redis: boolean
  celery: boolean
  detection: boolean
  storage_warning: boolean
  storage_critical: boolean
}

export interface StorageStatus {
  total_bytes: number
  used_bytes: number
  free_bytes: number
  usage_percent: number
  per_camera: Array<{
    camera_id: string
    camera_name: string
    used_bytes: number
  }>
}

export interface SystemEvent {
  id: string
  level: 'info' | 'warning' | 'error' | 'critical'
  message: string
  details: Record<string, unknown> | null
  created_at: string
}

export interface StreamInfo {
  camera_id: string
  camera_name: string
  hls_url: string
  status: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface Zone {
  id?: string
  name: string
  polygon: number[][]
  restricted: boolean
  working_hours_start: string | null
  working_hours_end: string | null
  dwell_threshold_s: number | null
  is_privacy_mask: boolean
  enabled: boolean
  color: string
}

export interface ScheduleSlot {
  day: number
  hour: number
  mode: RecordingMode
}

export interface PtzPreset {
  id: string
  name: string
}

export interface CameraStats {
  recording_hours: Array<{ date: string; hours: number }>
  storage_used: Array<{ date: string; bytes: number }>
  alert_frequency: Array<{ hour: number; count: number }>
}

export type CameraSlot = {
  id: string
  cameraId: string | null
  cameraName?: string
}

export interface ApiError {
  detail: string
  request_id?: string
}

export interface Role {
  id: string
  name: string
  permissions: string[]
  is_system: boolean
}

export interface UserSession {
  id: string
  user_id: string
  ip_address: string
  user_agent: string
  created_at: string
  last_used_at: string
  is_current: boolean
}

export interface CameraPermission {
  camera_id: string
  camera_name: string
  can_view: boolean
  can_control_ptz: boolean
  can_export: boolean
}

export interface AuditEntry {
  id: string
  actor_id: string | null
  actor_email: string | null
  action: string
  resource_type: string
  resource_id: string | null
  detail: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}

export interface Building {
  id: string
  name: string
  description: string | null
  address: string | null
  created_at: string
  updated_at: string | null
  floor_count: number
}

export interface Floor {
  id: string
  building_id: string
  name: string
  level: number
  has_image: boolean
  created_at: string
  updated_at: string | null
}

export interface PlacementCamera {
  id: string
  name: string
  location: string
  status: CameraStatus | 'recording' | 'unauthorized' | 'unknown'
  ip_address: string
}

export interface CameraPlacement {
  id: string
  floor_id: string
  camera_id: string
  x: number
  y: number
  rotation: number
  created_at: string
  camera: PlacementCamera
}
