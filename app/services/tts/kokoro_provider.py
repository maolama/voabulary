import os
from .base import TTSProvider
from ...extensions import logger

class KokoroProvider(TTSProvider):
    def __init__(self):
        self.kokoro = None
        self._voices_cache = []

    @property
    def provider_id(self):
        return "kokoro"

    def _get_paths(self):
        """Helper to safely get the paths to the new Kokoro V1.0 model files."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        kokoro_dir = os.path.join(base_dir, 'tts_models', 'kokoro')
        
        # POINT TO THE NEW V1.0 FILES!
        model_path = os.path.join(kokoro_dir, 'kokoro-v1.0.onnx')
        voices_path = os.path.join(kokoro_dir, 'voices-v1.0.bin')
        return model_path, voices_path

    def _load_model(self):
        """Loads the model into RAM only when requested the first time."""
        if self.kokoro is None:
            try:
                from kokoro_onnx import Kokoro
                model_path, voices_path = self._get_paths()

                if not os.path.exists(model_path) or not os.path.exists(voices_path):
                    logger.error(f"Kokoro files missing! Ensure {model_path} and {voices_path} exist.")
                    return False

                # The new kokoro-onnx package natively handles the .bin file securely
                self.kokoro = Kokoro(model_path, voices_path)
                return True
            except ImportError:
                logger.warning("kokoro-onnx not installed. Kokoro TTS disabled.")
                return False
            except Exception as e:
                logger.error(f"Failed to load Kokoro: {e}")
                return False
        return True

    def get_voices(self):
        """Supplies the 26 official voices baked into voices-v1.0.bin"""
        if self._voices_cache:
            return self._voices_cache

        # Master list of V1.0 voices
        voice_ids = [
            "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore", "af_nicole", "af_nova", 
            "af_river", "af_sarah", "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir", 
            "am_liam", "am_michael", "am_onyx", "am_puck", "bf_alice", "bf_emma", "bf_isabella", 
            "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis"
        ]

        dynamic_voices = []
        for vid in voice_ids:
            prefix = vid[:2].lower()
            name_part = vid[3:].replace('_', ' ').title() if len(vid) > 3 else vid
            
            # Deduce Language and Gender
            if prefix == 'af': desc, lang = 'US Female', 'en-US'
            elif prefix == 'am': desc, lang = 'US Male', 'en-US'
            elif prefix == 'bf': desc, lang = 'UK Female', 'en-GB'
            elif prefix == 'bm': desc, lang = 'UK Male', 'en-GB'
            else: desc, lang = prefix.upper(), 'en-US'

            dynamic_voices.append({
                'id': vid,
                'name': f"Kokoro: {name_part} ({desc})",
                'lang': lang
            })

        self._voices_cache = sorted(dynamic_voices, key=lambda k: k['name'])
        return self._voices_cache

    def generate_audio(self, text, voice_id, output_path):
        if not self._load_model():
            return False
            
        try:
            import soundfile as sf
            
            # Determine correct phonetics engine ('b' = British, 'a' = American)
            lang_param = "en-gb" if voice_id.startswith("b") else "en-us"
            
            # Generate the audio array
            samples, sample_rate = self.kokoro.create(
                text, voice=voice_id, speed=1.0, lang=lang_param
            )
            
            # Save it to the cache folder as a .wav file
            sf.write(output_path, samples, sample_rate)
            return True
        except Exception as e:
            logger.error(f"Kokoro TTS Failed: {e}")
            return False