import os
from .base import TTSProvider
from ...extensions import logger

class SileroProvider(TTSProvider):
    def __init__(self):
        self.model = None
        self._voices_cache = []

    @property
    def provider_id(self):
        return "silero"

    def _load_model(self):
        """Loads the PyTorch model into RAM only when needed."""
        if self.model is None:
            try:
                import torch
                # Explicitly use CPU to ensure high compatibility on standard laptops/servers
                device = torch.device('cpu')
                
                # trust_repo=True fixes the PyTorch GitHub download block
                self.model, _ = torch.hub.load(
                    repo_or_dir='snakers4/silero-models',
                    model='silero_tts',
                    language='en',
                    speaker='v3_en',
                    trust_repo=True 
                )
                self.model.to(device)
                return True # Fixes the silent failure bug!
            except ImportError as e:
                logger.warning(f"Silero missing dependency: {e}")
                return False
            except Exception as e:
                logger.error(f"Failed to load Silero: {e}")
                return False
        return True # Fixes the cached model failure bug!

    def get_voices(self):
        """Dynamically asks the PyTorch model for all its embedded speakers."""
        if self._voices_cache:
            return self._voices_cache
            
        if not self._load_model():
            return []
            
        try:
            # The v3_en model contains 118 speakers natively ('en_0' to 'en_117')
            for speaker in self.model.speakers:
                # Make the names look pretty in the UI dropdown
                speaker_num = speaker.replace('en_', '')
                self._voices_cache.append({
                    'id': speaker,
                    'name': f"Silero: Speaker {speaker_num}",
                    'lang': 'en-US'
                })
            return self._voices_cache
        except Exception as e:
            logger.error(f"Failed to dynamically fetch Silero speakers: {e}")
            return []

    def generate_audio(self, text, voice_id, output_path):
        """Generates the speech and saves it safely bypassing torchaudio bugs."""
        if not self._load_model(): 
            return False
            
        try:
            # We use soundfile instead of torchaudio.save to bypass the missing torchcodec C++ library error
            import soundfile as sf 
            
            # Synthesize at 48,000 Hz (v3_en's maximum native quality)
            audio = self.model.apply_tts(text=text, speaker=voice_id, sample_rate=48000)
            
            # Convert the PyTorch tensor down to a standard 1D Numpy array
            audio_numpy = audio.squeeze().cpu().numpy()
            
            # Save it to the cache
            sf.write(output_path, audio_numpy, 48000)
            return True
        except Exception as e:
            logger.error(f"Silero TTS Failed: {e}")
            return False