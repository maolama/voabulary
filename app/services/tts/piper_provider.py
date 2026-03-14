import os
import subprocess
from .base import TTSProvider
from ...extensions import logger

class PiperProvider(TTSProvider):
    def __init__(self):
        self._voice_paths = {}
        self._voices_list = []
        self._scan_models()

    @property
    def provider_id(self):
        return "piper"

    def _scan_models(self):
        self._voice_paths.clear()
        self._voices_list.clear()

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        piper_dir = os.path.join(base_dir, 'tts_models', 'piper')

        if not os.path.exists(piper_dir):
            return

        for root, dirs, files in os.walk(piper_dir):
            for file in files:
                if file.endswith('.onnx'):
                    model_path = os.path.join(root, file)
                    config_path = model_path + '.json'
                    
                    if not os.path.exists(config_path):
                        continue

                    voice_id = file[:-5] 
                    parts = voice_id.split('-')
                    lang = parts[0] if len(parts) > 0 else 'en-US'
                    html_lang = lang.replace('_', '-') 
                    person = parts[1] if len(parts) > 1 else 'unknown'
                    quality = parts[2] if len(parts) > 2 else 'standard'
                    
                    display_name = f"Piper: {person.capitalize()} ({html_lang}, {quality})"
                    self._voice_paths[voice_id] = model_path
                    self._voices_list.append({
                        'id': voice_id,
                        'name': display_name,
                        'lang': html_lang
                    })

    def get_voices(self):
        self._scan_models()
        return self._voices_list

    def generate_audio(self, text, voice_id, output_path):
        if voice_id not in self._voice_paths:
            logger.error(f"Piper model not found for voice_id: {voice_id}")
            return False
            
        model_path = self._voice_paths[voice_id]
        
        try:
            # Safely pipe the string into Piper bypassing the Windows shell
            process = subprocess.run(
                ['piper', '--model', model_path, '--output_file', output_path],
                input=text,
                text=True,
                encoding='utf-8',
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            
            if process.returncode != 0:
                logger.error(f"Piper CLI Error: {process.stderr}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Piper Execution Failed: {e}")
            return False