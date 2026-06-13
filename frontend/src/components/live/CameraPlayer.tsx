import { useEffect, useRef, useState, useCallback } from 'react'
import Hls from 'hls.js'
import { Maximize2, Camera, Zap, AlertTriangle, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useStreamUrl } from '@/api/live'
import { useCamera } from '@/api/cameras'

type PlayerStatus = 'loading' | 'buffering' | 'playing' | 'offline' | 'error'

interface Props {
  cameraId: string
  label: string
  location?: string
  alertCount?: number
  ptzEnabled?: boolean
  onFullscreen?: () => void
  onSnapshot?: () => void
  className?: string
}

const RETRY_DELAYS = [2000, 3000, 4000, 5000, 6000, 8000]

export default function CameraPlayer({
  cameraId, label, location, alertCount = 0, ptzEnabled = false,
  onFullscreen, onSnapshot, className,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<Hls | null>(null)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [status, setStatus] = useState<PlayerStatus>('loading')
  const [showControls, setShowControls] = useState(false)

  const { data: streamInfo } = useStreamUrl(cameraId)
  const { data: cameraData } = useCamera(cameraId)

  const destroyHls = useCallback(() => {
    if (hlsRef.current) {
      hlsRef.current.destroy()
      hlsRef.current = null
    }
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }, [])

  const initPlayer = useCallback((url: string) => {
    const video = videoRef.current
    if (!video) return
    destroyHls()

    if (Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true, lowLatencyMode: true })
      hlsRef.current = hls
      hls.loadSource(url)
      hls.attachMedia(video)

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => setStatus('error'))
      })

      video.addEventListener('waiting', () => setStatus('buffering'))
      hls.on(Hls.Events.BUFFER_FLUSHED, () => setStatus('playing'))

      hls.on(Hls.Events.ERROR, (_, data) => {
        if (!data.fatal) return
        const attempt = retryCountRef.current
        if (attempt < RETRY_DELAYS.length) {
          retryCountRef.current++
          setStatus('buffering')
          retryTimerRef.current = setTimeout(() => initPlayer(url), RETRY_DELAYS[attempt])
        } else {
          setStatus('error')
          retryCountRef.current = 0
        }
      })
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url
      video.play().catch(() => setStatus('error'))
    } else {
      setStatus('error')
    }
  }, [destroyHls])

  useEffect(() => {
    if (!streamInfo) return
    retryCountRef.current = 0
    initPlayer(streamInfo.hls_url)
    return destroyHls
  }, [streamInfo, initPlayer, destroyHls])

  const handleRetry = () => {
    retryCountRef.current = 0
    setStatus('loading')
    if (streamInfo?.hls_url) initPlayer(streamInfo.hls_url)
  }

  return (
    <div
      className={cn(
        'relative bg-black overflow-hidden rounded-md group',
        status === 'error' && 'ring-2 ring-destructive',
        className
      )}
      onMouseEnter={() => setShowControls(true)}
      onMouseLeave={() => setShowControls(false)}
    >
      {/* Video element */}
      <video
        ref={videoRef}
        className="w-full h-full object-cover"
        muted
        playsInline
        onPlaying={() => setStatus('playing')}
        onWaiting={() => setStatus('buffering')}
        onStalled={() => setStatus('buffering')}
      />

      {/* Loading / buffering overlay */}
      {(status === 'loading' || status === 'buffering') && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/60">
          <RefreshCw className="h-8 w-8 text-white animate-spin" />
        </div>
      )}

      {/* Offline overlay */}
      {status === 'offline' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-900 text-gray-400 gap-2">
          <WifiOff className="h-10 w-10" />
          <span className="text-sm font-medium">{label}</span>
          <span className="text-xs">Camera offline</span>
        </div>
      )}

      {/* Error overlay */}
      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-900 text-red-400 gap-2">
          <AlertTriangle className="h-10 w-10" />
          <span className="text-sm">Stream error</span>
          <Button size="sm" variant="outline" onClick={handleRetry} className="mt-1 h-7 text-xs">
            <RefreshCw className="h-3 w-3 mr-1" /> Retry
          </Button>
        </div>
      )}

      {/* REC badge — hidden while controls overlay is shown */}
      {cameraData?.status === 'recording' && !showControls && (
        <div className="absolute top-2 left-2 z-10">
          <Badge className="text-xs h-5 px-1.5 bg-red-600 text-white animate-pulse border-0">
            ● REC
          </Badge>
        </div>
      )}

      {/* Alert badge */}
      {alertCount > 0 && (
        <div className="absolute top-2 right-2 z-10">
          <Badge variant="destructive" className="text-xs h-5 px-1.5">
            {alertCount > 9 ? '9+' : alertCount}
          </Badge>
        </div>
      )}

      {/* Camera name / location overlay */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-2 pb-1.5 pt-4">
        <div className="flex items-center gap-1.5">
          <span className={cn('h-2 w-2 rounded-full shrink-0', {
            'bg-green-400': status === 'playing',
            'bg-yellow-400 animate-pulse': status === 'buffering' || status === 'loading',
            'bg-gray-400': status === 'offline',
            'bg-red-400': status === 'error',
          })} />
          <span className="text-white text-xs font-medium truncate">{label}</span>
          {location && <span className="text-white/60 text-xs truncate">{location}</span>}
        </div>
      </div>

      {/* Controls overlay */}
      {showControls && status === 'playing' && (
        <div className="absolute top-2 left-2 flex gap-1 z-10">
          {onFullscreen && (
            <Button size="icon" variant="secondary" className="h-7 w-7 opacity-80" onClick={onFullscreen}>
              <Maximize2 className="h-3.5 w-3.5" />
            </Button>
          )}
          {onSnapshot && (
            <Button size="icon" variant="secondary" className="h-7 w-7 opacity-80" onClick={onSnapshot}>
              <Camera className="h-3.5 w-3.5" />
            </Button>
          )}
          {ptzEnabled && (
            <Button size="icon" variant="secondary" className="h-7 w-7 opacity-80">
              <Zap className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      )}

      {/* Online indicator when not showing controls */}
      {status === 'playing' && !showControls && (
        <div className="absolute top-2 left-2 z-10">
          <Wifi className="h-3.5 w-3.5 text-green-400 opacity-70" />
        </div>
      )}
    </div>
  )
}
