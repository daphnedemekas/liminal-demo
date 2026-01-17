import { useState, useCallback, useRef, useEffect } from 'react'

// Type for Web Speech API (not in TypeScript by default)
interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList
}

interface SpeechRecognitionResultList {
  length: number
  item(index: number): SpeechRecognitionResult
  [index: number]: SpeechRecognitionResult
}

interface SpeechRecognitionResult {
  length: number
  item(index: number): SpeechRecognitionAlternative
  [index: number]: SpeechRecognitionAlternative
  isFinal: boolean
}

interface SpeechRecognitionAlternative {
  transcript: string
  confidence: number
}

interface SpeechRecognitionType {
  new (): SpeechRecognition
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean
  interimResults: boolean
  lang: string
  start(): void
  stop(): void
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onerror: ((event: Event) => void) | null
  onend: (() => void) | null
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionType
    webkitSpeechRecognition?: SpeechRecognitionType
  }
}

interface UseSpeechRecognitionReturn {
  isListening: boolean
  transcript: string
  startListening: () => void
  stopListening: () => void
  isSupported: boolean
  resetTranscript: () => void
}

export function useSpeechRecognition(): UseSpeechRecognitionReturn {
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null)

  // Check if browser supports speech recognition
  const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition
  const isSupported = !!SpeechRecognitionAPI

  // Initialize recognition in useEffect to avoid memory leaks
  useEffect(() => {
    if (!isSupported || recognitionRef.current) return

    const recognition = new SpeechRecognitionAPI()
    recognition.continuous = true  // Keep listening continuously
    recognition.interimResults = true  // Show interim results as user speaks
    recognition.lang = 'en-US'

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      // Accumulate all results (interim + final)
      let fullTranscript = ''
      for (let i = 0; i < event.results.length; i++) {
        fullTranscript += event.results[i][0].transcript
      }
      setTranscript(fullTranscript)
    }

    recognition.onerror = (event: Event) => {
      console.error('Speech recognition error:', event)
      setIsListening(false)
    }

    recognition.onend = () => {
      setIsListening(false)
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
      }
    }

    recognitionRef.current = recognition

    // Cleanup on unmount
    return () => {
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
      }
      if (recognitionRef.current) {
        recognitionRef.current.stop()
      }
    }
  }, [isSupported])

  const startListening = useCallback(() => {
    if (recognitionRef.current && !isListening) {
      setTranscript('')
      recognitionRef.current.start()
      setIsListening(true)
    }
  }, [isListening])

  const stopListening = useCallback(() => {
    if (recognitionRef.current && isListening) {
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
      }
      recognitionRef.current.stop()
    }
  }, [isListening])

  const resetTranscript = useCallback(() => {
    setTranscript('')
  }, [])

  return {
    isListening,
    transcript,
    startListening,
    stopListening,
    isSupported,
    resetTranscript,
  }
}
