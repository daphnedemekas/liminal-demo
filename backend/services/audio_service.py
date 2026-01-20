"""ElevenLabs text-to-speech service."""
import os
from typing import Optional
from pathlib import Path
import tempfile
import uuid
from elevenlabs.client import ElevenLabs


class AudioService:
    """Handles text-to-speech conversion using ElevenLabs."""

    def __init__(self, api_key: Optional[str] = None, voice_id: Optional[str] = None):
        # Directory to store temporary audio files (always set, even if audio is disabled)
        self.audio_dir = Path(tempfile.gettempdir()) / "liminal_audio"
        self.audio_dir.mkdir(exist_ok=True)
        
        # Debug: Check environment variables
        env_key = os.getenv("ELEVENLABS_API_KEY")
        print(f"[Audio] DEBUG: Checking for ELEVENLABS_API_KEY in environment...")
        print(f"[Audio] DEBUG: Key found: {bool(env_key)}")
        if env_key:
            print(f"[Audio] DEBUG: Key length: {len(env_key)}")
            print(f"[Audio] DEBUG: Key starts with: {env_key[:10]}...")
        
        self.api_key = api_key or env_key
        if not self.api_key:
            # Audio service disabled if no API key
            self.client = None
            print("[Audio] WARNING: ELEVENLABS_API_KEY not found in environment. Audio features will be disabled.")
            print(f"[Audio] DEBUG: All env vars containing 'ELEVEN': {[k for k in os.environ.keys() if 'ELEVEN' in k.upper()]}")
            # Set default values even when disabled
            self.voice_id = voice_id or "c4NIULtANlpduSDihsKJ"
            self.model = "eleven_turbo_v2"
            return

        print(f"[Audio] ElevenLabs API key loaded: {self.api_key[:10]}...")
        self.client = ElevenLabs(api_key=self.api_key)

        # Default to a natural conversational voice
        # You can change this to any ElevenLabs voice ID
        self.voice_id = voice_id or "c4NIULtANlpduSDihsKJ"  # Custom voice
        self.model = "eleven_turbo_v2"  # Fast model for real-time feel

    def text_to_speech(self, text: str) -> Path:
        """
        Convert text to speech and save to a temporary file.

        Args:
            text: The text to convert to speech

        Returns:
            Path to the audio file
        """
        if not self.client:
            raise ValueError("Audio service not available (ELEVENLABS_API_KEY not set)")
        print(f"[Audio] TTS called with {len(text)} chars: {text[:50]}...")
        try:
            # Generate audio using the new SDK API
            print(f"[Audio] Calling ElevenLabs API with voice_id={self.voice_id}, model={self.model}")
            audio_generator = self.client.text_to_speech.convert(
                text=text,
                voice_id=self.voice_id,
                model_id=self.model,
                output_format="mp3_44100_128"
            )

            # Save to temporary file
            audio_path = self.audio_dir / f"audio_{uuid.uuid4().hex[:8]}.mp3"
            
            # Write audio chunks to file
            bytes_written = 0
            with open(audio_path, 'wb') as f:
                for chunk in audio_generator:
                    f.write(chunk)
                    bytes_written += len(chunk)
            
            print(f"[Audio] TTS SUCCESS: {bytes_written} bytes written to {audio_path}")
            return audio_path

        except Exception as e:
            print(f"[Audio] TTS ERROR: {e}")
            import traceback
            traceback.print_exc()
            raise

    def text_to_speech_stream(self, text: str):
        """
        Convert text to speech and return streaming audio.

        Args:
            text: The text to convert to speech

        Returns:
            Generator yielding audio chunks
        """
        if not self.client:
            raise ValueError("Audio service not available (ELEVENLABS_API_KEY not set)")
        try:
            audio_stream = self.client.text_to_speech.convert(
                text=text,
                voice_id=self.voice_id,
                model_id=self.model,
                output_format="mp3_44100_128"
            )
            return audio_stream

        except Exception as e:
            print(f"Error generating streaming audio: {e}")
            raise

    def cleanup_old_files(self, max_age_seconds: int = 3600):
        """Remove audio files older than max_age_seconds."""
        import time
        now = time.time()

        for audio_file in self.audio_dir.glob("audio_*.mp3"):
            if now - audio_file.stat().st_mtime > max_age_seconds:
                audio_file.unlink()


# Global audio service instance
_audio_service: Optional[AudioService] = None


def get_audio_service() -> AudioService:
    """Get or create the global audio service instance."""
    global _audio_service
    if _audio_service is None:
        _audio_service = AudioService()
    return _audio_service
