"""ElevenLabs text-to-speech service."""

import os
import re
import time
import uuid
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AudioService:
    """Handles text-to-speech conversion using ElevenLabs."""

    def __init__(self, api_key: Optional[str] = None, voice_id: Optional[str] = None):
        self.audio_dir = Path(tempfile.gettempdir()) / "envisage_audio"
        self.audio_dir.mkdir(exist_ok=True)

        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        self.voice_id = voice_id or "c4NIULtANlpduSDihsKJ"
        self.model = "eleven_turbo_v2"

        if not self.api_key:
            self.client = None
            logger.info("ELEVENLABS_API_KEY not set — TTS disabled")
            return

        from elevenlabs.client import ElevenLabs
        self.client = ElevenLabs(api_key=self.api_key)
        logger.info("ElevenLabs TTS enabled")

    @property
    def available(self) -> bool:
        return self.client is not None

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove markdown formatting so TTS doesn't read asterisks, hashes, etc."""
        text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
        text = re.sub(r'_{1,3}(.+?)_{1,3}', r'\1', text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
        return text.strip()

    def text_to_speech(self, text: str) -> Path:
        """Convert text to speech and save to a temporary MP3 file."""
        if not self.client:
            raise ValueError("TTS not available (ELEVENLABS_API_KEY not set)")

        text = self._strip_markdown(text)
        audio_generator = self.client.text_to_speech.convert(
            text=text,
            voice_id=self.voice_id,
            model_id=self.model,
            output_format="mp3_44100_128",
        )

        audio_path = self.audio_dir / f"audio_{uuid.uuid4().hex[:8]}.mp3"
        with open(audio_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)

        return audio_path

    def cleanup_old_files(self, max_age_seconds: int = 3600):
        """Remove audio files older than max_age_seconds."""
        now = time.time()
        for audio_file in self.audio_dir.glob("audio_*.mp3"):
            if now - audio_file.stat().st_mtime > max_age_seconds:
                audio_file.unlink()


_audio_service: Optional[AudioService] = None


def get_audio_service() -> AudioService:
    global _audio_service
    if _audio_service is None:
        _audio_service = AudioService()
    return _audio_service
