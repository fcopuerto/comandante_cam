import { useRef, useState, useEffect, useCallback } from 'react'
import { Play, Pause } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

interface MultiCameraPlayerProps {
  cameras: Array<{ id: string; name: string; src: string | null }>
  date: string
}

const SPEEDS = [0.5, 1, 2, 4] as const

function formatMMSS(seconds: number): string {
  const s = Math.floor(seconds)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export default function MultiCameraPlayer({ cameras, date: _date }: MultiCameraPlayerProps) {
  const slots = cameras.slice(0, 4)
  const videoRefs = useRef<Array<HTMLVideoElement | null>>([null, null, null, null])
  const isSeeking = useRef(false)

  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1)

  const gridClass =
    slots.length === 1
      ? 'grid-cols-1'
      : slots.length === 2
      ? 'grid-cols-2'
      : 'grid-cols-2'

  const setRef = useCallback((el: HTMLVideoElement | null, index: number) => {
    videoRefs.current[index] = el
  }, [])

  const getVideos = useCallback((): HTMLVideoElement[] => {
    return videoRefs.current.filter((v): v is HTMLVideoElement => v !== null)
  }, [])

  const handlePlayPause = useCallback(() => {
    const videos = getVideos()
    if (videos.length === 0) return
    if (isPlaying) {
      videos.forEach((v) => v.pause())
    } else {
      videos.forEach((v) => v.play().catch(() => {}))
    }
  }, [isPlaying, getVideos])

  const handleScrub = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const t = parseFloat(e.target.value)
      isSeeking.current = true
      setCurrentTime(t)
      getVideos().forEach((v) => {
        v.currentTime = t
      })
      isSeeking.current = false
    },
    [getVideos]
  )

  const handleSpeedChange = useCallback(
    (speed: number) => {
      setPlaybackRate(speed)
      getVideos().forEach((v) => {
        v.playbackRate = speed
      })
    },
    [getVideos]
  )

  const handleTimeUpdate = useCallback(
    (e: React.SyntheticEvent<HTMLVideoElement>) => {
      if (isSeeking.current) return
      const video = e.currentTarget
      setCurrentTime(video.currentTime)
    },
    []
  )

  const handleLoadedMetadata = useCallback(
    (index: number) => {
      if (index === 0) {
        const v = videoRefs.current[0]
        if (v) setDuration(v.duration)
      }
    },
    []
  )

  const handlePlay = useCallback(() => {
    setIsPlaying(true)
  }, [])

  const handlePause = useCallback(() => {
    const videos = getVideos()
    const anyPlaying = videos.some((v) => !v.paused)
    if (!anyPlaying) setIsPlaying(false)
  }, [getVideos])

  useEffect(() => {
    const videos = getVideos()
    videos.forEach((v) => {
      v.playbackRate = playbackRate
    })
  }, [playbackRate, getVideos])

  useEffect(() => {
    setIsPlaying(false)
    setCurrentTime(0)
    setDuration(0)
  }, [cameras])

  return (
    <div className="flex flex-col bg-black rounded-md overflow-hidden">
      <div className={cn('grid flex-1 min-h-0', gridClass, slots.length >= 3 && 'grid-rows-2')}>
        {slots.map((cam, index) => (
          <div key={cam.id} className="relative bg-black">
            {cam.src ? (
              <video
                ref={(el) => setRef(el, index)}
                src={cam.src}
                controls={false}
                className="w-full h-full object-contain"
                onPlay={handlePlay}
                onPause={handlePause}
                onTimeUpdate={handleTimeUpdate}
                onLoadedMetadata={() => handleLoadedMetadata(index)}
                onEnded={() => {
                  const videos = getVideos()
                  const anyPlaying = videos.some((v) => !v.paused)
                  if (!anyPlaying) setIsPlaying(false)
                }}
              />
            ) : (
              <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
                No clip
              </div>
            )}
            <span className="absolute top-2 left-2 px-1.5 py-0.5 text-xs text-white bg-black/60 rounded pointer-events-none">
              {cam.name}
            </span>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2 px-3 py-2 bg-gray-900">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-gray-300 shrink-0 w-24 text-center">
            {formatMMSS(currentTime)} / {formatMMSS(duration)}
          </span>
          <input
            type="range"
            min={0}
            max={duration || 0}
            step={0.033}
            value={currentTime}
            onChange={handleScrub}
            className="flex-1 h-1.5 appearance-none bg-gray-600 rounded-full accent-indigo-500 cursor-pointer"
          />
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 text-white hover:bg-gray-700"
            onClick={handlePlayPause}
            disabled={slots.every((c) => !c.src)}
          >
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </Button>

          <div className="flex items-center gap-1">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => handleSpeedChange(s)}
                disabled={slots.every((c) => !c.src)}
                className={cn(
                  'text-xs px-2 py-0.5 rounded font-mono transition-colors',
                  playbackRate === s
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:bg-gray-700 hover:text-white',
                  slots.every((c) => !c.src) && 'opacity-40 cursor-not-allowed'
                )}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
