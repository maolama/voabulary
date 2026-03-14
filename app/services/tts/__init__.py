from .registry import tts_manager
from .piper_provider import PiperProvider
from .silero_provider import SileroProvider
from .kokoro_provider import KokoroProvider # NEW

# Append our classes to the registry list!
tts_manager.register(PiperProvider())
tts_manager.register(SileroProvider())
tts_manager.register(KokoroProvider())    # NEW
