"""ElevenLabs text-to-speech service."""
import os
from typing import Optional
from pathlib import Path
import tempfile
from elevenlabs.client import ElevenLabs
from elevenlabs import save


class AudioService:
    """Handles text-to-speech conversion using ElevenLabs."""

    def __init__(self, api_key: Optional[str] = None, voice_id: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY not found in environment")

        self.client = ElevenLabs(api_key=self.api_key)

        # Default to a natural conversational voice
        # You can change this to any ElevenLabs voice ID
        self.voice_id = voice_id or "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
        self.model = "eleven_turbo_v2"  # Fast model for real-time feel

        # Directory to store temporary audio files
        self.audio_dir = Path(tempfile.gettempdir()) / "liminal_audio"
        self.audio_dir.mkdir(exist_ok=True)

    def text_to_speech(self, text: str) -> Path:
        """
        Convert text to speech and save to a temporary file.

        Args:
            text: The text to convert to speech

        Returns:
            Path to the audio file
        """
        try:
            # Generate audio
            audio = self.client.generate(
                text=text,
                voice=self.voice_id,
                model=self.model
            )

            # Save to temporary file
            timestamp = int(Path(tempfile.mktemp()).name.split('tmp')[-1] or 0)
            audio_path = self.audio_dir / f"audio_{timestamp}.mp3"

            save(audio, str(audio_path))

            return audio_path

        except Exception as e:
            print(f"Error generating audio: {e}")
            raise

    def text_to_speech_stream(self, text: str):
        """
        Convert text to speech and return streaming audio.

        Args:
            text: The text to convert to speech

        Returns:
            Generator yielding audio chunks
        """
        try:
            audio_stream = self.client.generate(
                text=text,
                voice=self.voice_id,
                model=self.model,
                stream=True
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
