from .base import TTSProvider
from ...extensions import logger

class TTSManager:
    def __init__(self):
        self._providers = {}

    def register(self, provider: TTSProvider):
        self._providers[provider.provider_id] = provider
        logger.info(f"Registered TTS Provider: {provider.provider_id}")

    def get_all_voices(self):
        """Aggregates voices from all registered Python providers."""
        all_voices = []
        for p_id, provider in self._providers.items():
            try:
                voices = provider.get_voices()
                for v in voices:
                    v['provider'] = p_id
                    all_voices.append(v)
            except Exception as e:
                logger.error(f"Error getting voices from {p_id}: {e}")
        return all_voices

    def generate(self, text: str, provider_id: str, voice_id: str, output_path: str):
        provider = self._providers.get(provider_id)
        if not provider:
            logger.error(f"Provider {provider_id} not found.")
            return False
        return provider.generate_audio(text, voice_id, output_path)

# Global instance
tts_manager = TTSManager()