from abc import ABC, abstractmethod

class TTSProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """A unique string identifying this engine (e.g., 'piper', 'silero')"""
        pass

    @abstractmethod
    def get_voices(self) -> list:
        """Returns a list of dicts: [{'id': 'voice1', 'name': 'US Female', 'lang': 'en-US'}]"""
        pass

    @abstractmethod
    def generate_audio(self, text: str, voice_id: str, output_path: str) -> bool:
        """Generates the audio and saves it to output_path. Returns True if successful."""
        pass