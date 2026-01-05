'use client'

import { useRef, useEffect, useState, forwardRef, useImperativeHandle } from 'react'
import { Play, Pause, Volume2, VolumeX, Maximize, SkipBack, SkipForward } from 'lucide-react'
import { formatTimestamp } from '@/lib/utils'

// HLS.js type declarations
declare global {
  interface Window {
    Hls: any
  }
}

interface VideoPlayerProps {
  src: string
  poster?: string
  onTimeUpdate?: (currentTime: number) => void
}

export interface VideoPlayerRef {
  seekTo: (time: number) => void
  getCurrentTime: () => number
}

export const VideoPlayer = forwardRef<VideoPlayerRef, VideoPlayerProps>(
  ({ src, poster, onTimeUpdate }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const [isPlaying, setIsPlaying] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(0)
    const [volume, setVolume] = useState(1)
    const [isMuted, setIsMuted] = useState(false)
    const [isFullscreen, setIsFullscreen] = useState(false)
    const [showControls, setShowControls] = useState(true)
    const [isHLS, setIsHLS] = useState(false)

    // Expose methods to parent
    useImperativeHandle(ref, () => ({
      seekTo: (time: number) => {
        if (videoRef.current) {
          videoRef.current.currentTime = time
        }
      },
      getCurrentTime: () => videoRef.current?.currentTime || 0,
    }))

    // Determine if this is an HLS stream or YouTube
    useEffect(() => {
      if (src.includes('youtube.com') || src.includes('youtu.be')) {
        setIsHLS(false)
      } else if (src.includes('.m3u8')) {
        setIsHLS(true)
      }
    }, [src])

    // Initialize HLS.js for .m3u8 streams
    useEffect(() => {
      if (!isHLS || !videoRef.current) return

      let hls: any = null

      const initHLS = async () => {
        // Dynamically import HLS.js
        if (typeof window !== 'undefined' && !window.Hls) {
          const script = document.createElement('script')
          script.src = 'https://cdn.jsdelivr.net/npm/hls.js@latest'
          script.async = true
          await new Promise((resolve) => {
            script.onload = resolve
            document.head.appendChild(script)
          })
        }

        if (window.Hls && window.Hls.isSupported()) {
          hls = new window.Hls()
          hls.loadSource(src)
          hls.attachMedia(videoRef.current)
        } else if (videoRef.current?.canPlayType('application/vnd.apple.mpegurl')) {
          // Native HLS support (Safari)
          videoRef.current.src = src
        }
      }

      initHLS()

      return () => {
        if (hls) {
          hls.destroy()
        }
      }
    }, [src, isHLS])

    // Video event handlers
    useEffect(() => {
      const video = videoRef.current
      if (!video) return

      const handleTimeUpdate = () => {
        setCurrentTime(video.currentTime)
        onTimeUpdate?.(video.currentTime)
      }

      const handleLoadedMetadata = () => {
        setDuration(video.duration)
      }

      const handlePlay = () => setIsPlaying(true)
      const handlePause = () => setIsPlaying(false)

      video.addEventListener('timeupdate', handleTimeUpdate)
      video.addEventListener('loadedmetadata', handleLoadedMetadata)
      video.addEventListener('play', handlePlay)
      video.addEventListener('pause', handlePause)

      return () => {
        video.removeEventListener('timeupdate', handleTimeUpdate)
        video.removeEventListener('loadedmetadata', handleLoadedMetadata)
        video.removeEventListener('play', handlePlay)
        video.removeEventListener('pause', handlePause)
      }
    }, [onTimeUpdate])

    // Auto-hide controls
    useEffect(() => {
      let timeout: NodeJS.Timeout
      const handleMouseMove = () => {
        setShowControls(true)
        clearTimeout(timeout)
        if (isPlaying) {
          timeout = setTimeout(() => setShowControls(false), 3000)
        }
      }

      const container = containerRef.current
      container?.addEventListener('mousemove', handleMouseMove)
      container?.addEventListener('mouseleave', () => isPlaying && setShowControls(false))
      container?.addEventListener('mouseenter', () => setShowControls(true))

      return () => {
        container?.removeEventListener('mousemove', handleMouseMove)
        clearTimeout(timeout)
      }
    }, [isPlaying])

    const togglePlay = () => {
      if (videoRef.current) {
        if (isPlaying) {
          videoRef.current.pause()
        } else {
          videoRef.current.play()
        }
      }
    }

    const toggleMute = () => {
      if (videoRef.current) {
        videoRef.current.muted = !isMuted
        setIsMuted(!isMuted)
      }
    }

    const toggleFullscreen = () => {
      if (!containerRef.current) return

      if (!isFullscreen) {
        containerRef.current.requestFullscreen()
      } else {
        document.exitFullscreen()
      }
      setIsFullscreen(!isFullscreen)
    }

    const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
      const time = parseFloat(e.target.value)
      if (videoRef.current) {
        videoRef.current.currentTime = time
        setCurrentTime(time)
      }
    }

    const skip = (seconds: number) => {
      if (videoRef.current) {
        videoRef.current.currentTime += seconds
      }
    }

    // For YouTube, render an iframe
    if (src.includes('youtube.com') || src.includes('youtu.be')) {
      const videoId = extractYouTubeId(src)
      return (
        <div className="aspect-video bg-black rounded-lg overflow-hidden">
          <iframe
            src={`https://www.youtube.com/embed/${videoId}?enablejsapi=1`}
            className="w-full h-full"
            allowFullScreen
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          />
        </div>
      )
    }

    // For HLS or direct video
    return (
      <div
        ref={containerRef}
        className="relative aspect-video bg-black rounded-lg overflow-hidden group"
      >
        <video
          ref={videoRef}
          className="w-full h-full"
          poster={poster}
          onClick={togglePlay}
        />

        {/* Controls overlay */}
        <div
          className={`absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent transition-opacity ${
            showControls ? 'opacity-100' : 'opacity-0'
          }`}
        >
          {/* Center play button */}
          <button
            onClick={togglePlay}
            className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-16 w-16 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center transition-transform hover:scale-110 ${
              isPlaying ? 'opacity-0' : 'opacity-100'
            }`}
          >
            <Play className="h-8 w-8 text-white ml-1" />
          </button>

          {/* Bottom controls */}
          <div className="absolute bottom-0 left-0 right-0 p-4">
            {/* Progress bar */}
            <input
              type="range"
              min={0}
              max={duration || 100}
              value={currentTime}
              onChange={handleSeek}
              className="w-full h-1 mb-4 bg-white/30 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white"
            />

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <button
                  onClick={togglePlay}
                  className="text-white hover:text-blue-400 transition-colors"
                >
                  {isPlaying ? (
                    <Pause className="h-5 w-5" />
                  ) : (
                    <Play className="h-5 w-5" />
                  )}
                </button>

                <button
                  onClick={() => skip(-10)}
                  className="text-white hover:text-blue-400 transition-colors"
                >
                  <SkipBack className="h-5 w-5" />
                </button>

                <button
                  onClick={() => skip(10)}
                  className="text-white hover:text-blue-400 transition-colors"
                >
                  <SkipForward className="h-5 w-5" />
                </button>

                <button
                  onClick={toggleMute}
                  className="text-white hover:text-blue-400 transition-colors"
                >
                  {isMuted ? (
                    <VolumeX className="h-5 w-5" />
                  ) : (
                    <Volume2 className="h-5 w-5" />
                  )}
                </button>

                <span className="text-white text-sm">
                  {formatTimestamp(currentTime)} / {formatTimestamp(duration)}
                </span>
              </div>

              <button
                onClick={toggleFullscreen}
                className="text-white hover:text-blue-400 transition-colors"
              >
                <Maximize className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }
)

VideoPlayer.displayName = 'VideoPlayer'

function extractYouTubeId(url: string): string {
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&?/]+)/,
  ]

  for (const pattern of patterns) {
    const match = url.match(pattern)
    if (match) return match[1]
  }

  return ''
}
