import { useState, useCallback, useRef, useEffect } from 'react'
import { getApiBaseUrl } from '../config'

interface UseAudioReturn {
  isAudioMode: boolean
  isRecording: boolean
  isPlaying: boolean
  toggleAudioMode: () => void
  startRecording: () => Promise<void>
  stopRecording: () => Promise<string | null>
  playAudio: (audioUrl: string) => Promise<void>
}

export function useAudio(): UseAudioReturn {
  const [isAudioMode, setIsAudioMode] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const currentAudioRef = useRef<HTMLAudioElement | null>(null)

  // Cleanup effect to prevent memory leaks
  useEffect(() => {
    return () => {
      // Cleanup on unmount
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current.src = ''  // Clear source to release memory
        currentAudioRef.current = null
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
        mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop())
      }
    }
  }, [])

  const toggleAudioMode = useCallback(() => {
    setIsAudioMode(prev => !prev)
  }, [])

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)

      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.start()
      mediaRecorderRef.current = mediaRecorder
      setIsRecording(true)
    } catch (error) {
      console.error('Error starting recording:', error)
      alert('Could not access microphone. Please check permissions.')
    }
  }, [])

  const stopRecording = useCallback(async (): Promise<string | null> => {
    return new Promise((resolve) => {
      const mediaRecorder = mediaRecorderRef.current

      if (!mediaRecorder || mediaRecorder.state === 'inactive') {
        resolve(null)
        return
      }

      mediaRecorder.onstop = () => {
        // If we later want to ship recorded audio to a backend STT service, we'd build a Blob here.
        // For now, we rely on the browser Web Speech API, so we don't need to construct it.

        // Stop all tracks
        mediaRecorder.stream.getTracks().forEach(track => track.stop())

        setIsRecording(false)
        mediaRecorderRef.current = null

        // For now, we'll use Web Speech API instead of sending audio blob
        // If you want to send audio to Whisper API, you would:
        // 1. Convert audioBlob to base64 or form data
        // 2. Send to your backend
        // 3. Backend forwards to Whisper API
        // 4. Return transcript

        resolve(null)
      }

      mediaRecorder.stop()
    })
  }, [])

  const playAudio = useCallback(async (audioUrl: string) => {
    try {
      console.log('[Audio] Attempting to play:', audioUrl)
      
      // Stop any currently playing audio
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current = null
      }

      // Build full URL if relative
      const fullUrl = audioUrl.startsWith('http')
        ? audioUrl
        : `${getApiBaseUrl()}${audioUrl}`
      
      console.log('[Audio] Full URL:', fullUrl)

      // Create and play new audio
      const audio = new Audio(fullUrl)
      currentAudioRef.current = audio

      // Set up event handlers BEFORE playing
      audio.onended = () => {
        console.log('[Audio] Playback ended')
        currentAudioRef.current = null
        setIsPlaying(false)
      }

      audio.onerror = (e) => {
        console.error('[Audio] Playback error:', e)
        setIsPlaying(false)
      }

      audio.oncanplay = () => {
        console.log('[Audio] Audio can play, duration:', audio.duration)
      }

      setIsPlaying(true)
      
      // Wait for audio to be ready
      await audio.play()
      console.log('[Audio] Play started successfully')

    } catch (error) {
      console.error('[Audio] Error playing audio:', error)
      setIsPlaying(false)
    }
  }, [])

  return {
    isAudioMode,
    isRecording,
    isPlaying,
    toggleAudioMode,
    startRecording,
    stopRecording,
    playAudio,
  }
}
