import json
import os
from flask import current_app

class DojoConfig:
    """Manages the user's custom Dojo settings and Mastery Matrix."""
    
    DEFAULT_CONFIG = {
        "default_session_words": 7,
        "phases": {
            # Phase 1: Pure Recognition (Planting)
            "1": { 
                "word_to_def": 1, "def_to_word": 1, "audio_to_def": 1, 
                "true_false_sort": 1, "collocation_match": 1, "cloze_hybrid": 1, 
                "audio_dictation": 0, "typo_trap": 0, "vowel_void": 0, 
                "proofreader": 0, "blindfolded": 0, "verb_conjugation": 0 
            },
            # Phase 2: Scaffolded Recall (Watering)
            "2": { 
                "typo_trap": 1, "audio_dictation": 1, "cloze_hybrid": 1, "vowel_void": 1, 
                "word_to_def": 0, "def_to_word": 0, "audio_to_def": 0, "true_false_sort": 0, "collocation_match": 0,
                "proofreader": 0, "blindfolded": 0, "verb_conjugation": 0 
            },
            # Phase 3: Absolute Mastery (Forging)
            "3": { 
                "proofreader": 1, "blindfolded": 1, "verb_conjugation": 1, 
                "audio_dictation": 0, "cloze_hybrid": 0, "typo_trap": 0, "vowel_void": 0,
                "word_to_def": 0, "def_to_word": 0, "audio_to_def": 0, "true_false_sort": 0, "collocation_match": 0
            }
        }
    }

    @staticmethod
    def get_filepath():
        # Saves in your root/data folder alongside user_data.db
        base_dir = os.path.dirname(current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
        return os.path.join(base_dir, 'dojo_config.json')

    @classmethod
    def get_config(cls):
        path = cls.get_filepath()
        if not os.path.exists(path):
            cls.reset_to_default()
            return cls.DEFAULT_CONFIG
            
        try:
            with open(path, 'r') as f:
                user_config = json.load(f)
                
            # AUTO-HEALER: Merge any missing new modes into the old user config
            needs_save = False
            for phase, modes in cls.DEFAULT_CONFIG["phases"].items():
                # If a whole phase is missing somehow
                if phase not in user_config["phases"]:
                    user_config["phases"][phase] = modes
                    needs_save = True
                else:
                    # Check for missing individual modes
                    for mode, default_val in modes.items():
                        if mode not in user_config["phases"][phase]:
                            user_config["phases"][phase][mode] = default_val
                            needs_save = True
                            
            # Save the seamlessly upgraded config back to disk
            if needs_save:
                cls.save_config(user_config)
                
            return user_config
            
        except Exception:
            return cls.DEFAULT_CONFIG

    @classmethod
    def save_config(cls, new_config):
        path = cls.get_filepath()
        with open(path, 'w') as f:
            json.dump(new_config, f, indent=4)

    @classmethod
    def reset_to_default(cls):
        cls.save_config(cls.DEFAULT_CONFIG)