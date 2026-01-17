import { useState, useCallback, useRef } from 'react'

interface UseAudioReturn {
  isAudioMode: boolean
  isRecording: boolean
  toggleAudioMode: () => void
  startRecording: () => Promise<void>
  stopRecording: () => Promise<string | null>
  playAudio: (audioUrl: string) => Promise<void>
}

export function useAudio(): UseAudioReturn {
  const [isAudioMode, setIsAudioMode] = useState(false)
  const [isRecording, setIsRecording] = useState(false)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const currentAudioRef = useRef<HTMLAudioElement | null>(null)

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
      // Stop any currently playing audio
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current = null
      }

      // Create and play new audio
      const audio = new Audio(audioUrl)
      currentAudioRef.current = audio

      await audio.play()

      // Clean up after playback
      audio.onended = () => {
        currentAudioRef.current = null
      }
    } catch (error) {
      console.error('Error playing audio:', error)
    }
  }, [])

  return {
    isAudioMode,
    isRecording,
    toggleAudioMode,
    startRecording,
    stopRecording,
    playAudio,
  }
}
