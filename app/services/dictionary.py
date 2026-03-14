import os
import sqlite3
import itertools
import urllib.parse
import re
from readmdict import MDX, MDD
from ..extensions import logger
from bs4 import BeautifulSoup
import json

# Import all our specialized dictionary handlers
from .dictionaries.base import BaseDictionary
from .dictionaries.oald import OALD9Dictionary
from .dictionaries.macmillan import MacmillanDictionary
from .dictionaries.cald import CALD4Dictionary
from .dictionaries.ccabeld import CCABELDDictionary
from .dictionaries.longman import LAAD3Dictionary
from .dictionaries.mwaled import MwaledDictionary

# --- CONSTANTS ---
PASTEL_COLORS = [
    '#f4fafeb3', '#fdf6e3b3', '#f0fdf4b3', '#fff5f5b3', 
    '#f5f3ffb3', '#fdf2f8b3', '#f0f9ffb3', '#fffbebcf'
]

# ============================================================
# MAIN DICTIONARY SERVICE
# ============================================================

class DictionaryService:
    def __init__(self):
        self.active_dictionaries = {} 
        self.css_paths = {}
        self.js_paths = {} 
        self.color_cycle = itertools.cycle(PASTEL_COLORS)

    def initialize(self, dict_base_dir):
        """Scans dict/ folder, builds SQLite DBs if missing, and loads metadata."""
        if not os.path.exists(dict_base_dir):
            os.makedirs(dict_base_dir)
            logger.warning(f"Created '{dict_base_dir}'. Add your dictionary folders here.")
            return

        found_dicts = {}
        for root, dirs, files in os.walk(dict_base_dir):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                
                if ext not in ['.mdx', '.mdd', '.css', '.js']: 
                    continue
                
                rel_dir = os.path.relpath(root, dict_base_dir)
                dict_name = os.path.splitext(filename)[0] if rel_dir == '.' else rel_dir.replace(os.sep, '_')
                
                if dict_name not in found_dicts:
                    found_dicts[dict_name] = {'mdx': None, 'mdd': None, 'css': None, 'js': None, 'folder': root}
                
                filepath = os.path.join(root, filename)
                if ext == '.mdx': found_dicts[dict_name]['mdx'] = filepath
                elif ext == '.mdd': found_dicts[dict_name]['mdd'] = filepath
                elif ext == '.css': found_dicts[dict_name]['css'] = filepath
                elif ext == '.js': found_dicts[dict_name]['js'] = filepath 

        for dict_name, files in found_dicts.items():
            if not files['mdx']: 
                continue 
                
            db_path = os.path.join(files['folder'], f"{dict_name}.db")
            
            if not os.path.exists(db_path):
                self._build_database(dict_name, db_path, files['mdx'], files['mdd'])
            else:
                logger.info(f"Loaded existing database for '{dict_name}'.")

            # --- FACTORY: Assign the correct Handler Class ---
            color = next(self.color_cycle)
            upper_name = dict_name.upper()
            
            if "OALD" in upper_name:
                handler = OALD9Dictionary(db_path, dict_name, color)
                logger.info(f"Assigned specialized OALD handler to '{dict_name}'")
            elif "MACMILLAN" in upper_name:
                handler = MacmillanDictionary(db_path, dict_name, color)
                logger.info(f"Assigned specialized Macmillan handler to '{dict_name}'")
            elif "CALD" in upper_name:
                handler = CALD4Dictionary(db_path, dict_name, color)
                logger.info(f"Assigned specialized Cambridge handler to '{dict_name}'")
            elif "CCABELD" in upper_name or "COLLINS" in upper_name:
                handler = CCABELDDictionary(db_path, dict_name, color)
                logger.info(f"Assigned specialized Collins handler to '{dict_name}'")
            elif "LONGMAN" in upper_name or "LAAD" in upper_name:
                handler = LAAD3Dictionary(db_path, dict_name, color)
                logger.info(f"Assigned specialized Longman handler to '{dict_name}'")
            elif "MWALED" in upper_name or "MERRIAM" in upper_name:
                handler = MwaledDictionary(db_path, dict_name, color)
                logger.info(f"Assigned specialized Merriam-Webster handler to '{dict_name}'")
            else:
                handler = BaseDictionary(db_path, dict_name, color)
                logger.info(f"Assigned Base handler to '{dict_name}'")

            self.active_dictionaries[dict_name] = handler
            
            if files['css']:
                self.css_paths[dict_name] = files['css']
            if files['js']: 
                self.js_paths[dict_name] = files['js']

    def _build_database(self, dict_name, db_path, mdx_path, mdd_path):
        """Compiles MDX and MDD files into a fast SQLite database."""
        logger.info(f"Compiling '{dict_name}' into database...")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS entries (word TEXT COLLATE NOCASE, html TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS media (filepath TEXT COLLATE NOCASE, data BLOB)')
        
        if mdx_path and os.path.exists(mdx_path):
            mdx = MDX(mdx_path)
            c.executemany('INSERT INTO entries (word, html) VALUES (?, ?)', 
                          ((k.decode('utf-8'), v.decode('utf-8')) for k, v in mdx.items()))
            
        if mdd_path and os.path.exists(mdd_path):
            mdd = MDD(mdd_path)
            c.executemany('INSERT INTO media (filepath, data) VALUES (?, ?)',
                          ((k.decode('utf-8').replace('\\', '/').lower(), v) for k, v in mdd.items()))
                          
        c.execute('CREATE INDEX IF NOT EXISTS idx_word ON entries(word)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_filepath ON media(filepath)')
        conn.commit()
        conn.close()

    def get_full_html(self, dict_name, word, word_id=None, pinned_ids=None):
        """Standard polymorphic call: The Service doesn't care which class it uses."""
        handler = self.active_dictionaries.get(dict_name)
        if not handler: return None

        try:
            conn = sqlite3.connect(handler.db_path)
            c = conn.cursor()
            c.execute("SELECT html FROM entries WHERE word = ? LIMIT 1", (word,))
            row = c.fetchone()
            conn.close()

            if row:
                # FIXED: Added pinned_ids to kwargs
                return handler.process_html(row[0], word, word_id=word_id, pinned_ids=pinned_ids)
        except Exception as e:
            logger.error(f"Error retrieving HTML from {dict_name}: {e}")
        return None

    def search_word(self, query):
        """Queries databases and returns metadata for matched dictionaries."""
        matched_dicts = []
        if not query: return matched_dicts

        for dict_name, handler in self.active_dictionaries.items():
            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT 1 FROM entries WHERE word = ? LIMIT 1", (query,))
                match = c.fetchone()
                conn.close()
                
                if match:
                    matched_dicts.append({
                        'name': dict_name,
                        'color': handler.color,
                        'safe_query': urllib.parse.quote(query)
                    })
            except Exception as e:
                logger.error(f"Error searching in {dict_name}: {str(e)}")
        return matched_dicts

    def get_suggestions(self, prefix, limit=8):
        """Finds words starting with prefix across all dictionaries."""
        if not prefix or len(prefix) < 2: return []
        suggestions = set()
        search_term = f"{prefix}%"
        
        for dict_name, handler in self.active_dictionaries.items():
            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT word FROM entries WHERE word LIKE ? LIMIT ?", (search_term, limit))
                for row in c.fetchall():
                    suggestions.add(row[0])
                conn.close()
            except Exception as e:
                logger.error(f"Error getting suggestions: {str(e)}")
                
        return sorted(list(suggestions), key=lambda x: (len(x), x.lower()))[:limit]
    
    def get_short_definition(self, query):
        """Uses our new 26-feature extractors to get a clean, highly accurate short definition."""
        if not query: return None
        
        for dict_name, handler in self.active_dictionaries.items():
            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT html FROM entries WHERE word = ? LIMIT 1", (query,))
                row = c.fetchone()
                conn.close()
                
                if row:
                    # Pass the HTML through our extractor!
                    features = handler.extract_features(row[0])
                    
                    # Look for the definitions array
                    defs = features.get('definitions', [])
                    if defs and len(defs) > 0:
                        clean_text = defs[0]
                        # Truncate nicely if it's too long
                        if len(clean_text) > 150:
                            clean_text = clean_text[:147] + "..."
                        return clean_text
            except Exception as e:
                logger.error(f"Error getting short definition from {dict_name}: {e}")
                
        return "No short definition available."

    def has_audio(self, query):
        """Checks media table for matching audio files."""
        search_term = f"/{query}.%" 
        for dict_name, handler in self.active_dictionaries.items():
            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT filepath FROM media WHERE filepath LIKE ? AND "
                          "(filepath LIKE '%.mp3' OR filepath LIKE '%.spx' OR filepath LIKE '%.wav') LIMIT 1", 
                          (search_term,))
                row = c.fetchone()
                conn.close()
                if row: return row[0]
            except Exception:
                pass
        return None

    def _calculate_similarity(self, text1, text2):
        """Calculates Jaccard similarity between two strings to group similar definitions."""
        if not text1 or not text2: return 0.0
        words1 = set(re.findall(r'\b\w{3,}\b', text1.lower()))
        words2 = set(re.findall(r'\b\w{3,}\b', text2.lower()))
        if not words1 or not words2: return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union)

    def get_aggregated_features(self, query):
        """Aggregates hierarchical semantic features from updated dictionaries."""
        if not query: return None
        
        master_data = {} # Keyed by partOfSpeech

        for dict_name, handler in self.active_dictionaries.items():
            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT html FROM entries WHERE word = ? LIMIT 1", (query,))
                row = c.fetchone()
                conn.close()

                if row:
                    # Older dictionaries return flat dicts. Skip them until updated.
                    extracted_blocks = handler.extract_features(row[0])
                    if isinstance(extracted_blocks, dict): 
                        continue 
                    
                    source_name = getattr(handler, 'display_name', dict_name)
                    color = handler.color

                    for block in extracted_blocks:
                        pos = block.get('partOfSpeech', 'unknown')
                        if pos not in master_data:
                            master_data[pos] = {
                                "partOfSpeech": pos,
                                "ukPronunciation": block.get('ukPronunciation', ''),
                                "usPronunciation": block.get('usPronunciation', ''),
                                "meanings": [],
                                "idioms": []
                            }

                        # Fallback to grab pronunciation if first dict missed it
                        if not master_data[pos]['ukPronunciation'] and block.get('ukPronunciation'):
                            master_data[pos]['ukPronunciation'] = block.get('ukPronunciation')
                        if not master_data[pos]['usPronunciation'] and block.get('usPronunciation'):
                            master_data[pos]['usPronunciation'] = block.get('usPronunciation')

                        # Merge Idioms
                        for idiom in block.get('idioms', []):
                            if idiom not in [i['text'] for i in master_data[pos]['idioms']]:
                                master_data[pos]['idioms'].append({'text': idiom, 'source': source_name, 'color': color})

                        # SEMANTIC MERGING OF SENSES
                        for sense in block.get('meanings', []):
                            new_def = sense['definition']
                            matched = False
                            
                            for existing_meaning in master_data[pos]['meanings']:
                                sim_score = self._calculate_similarity(new_def, existing_meaning['primary_def'])
                                
                                # Threshold: >20% word overlap means they describe the same concept
                                if sim_score > 0.20:
                                    existing_meaning['all_definitions'].append({'text': new_def, 'source': source_name, 'color': color})
                                    for ex in sense['examples']:
                                        if ex not in [e['text'] for e in existing_meaning['examples']]:
                                            existing_meaning['examples'].append({'text': ex, 'source': source_name, 'color': color})
                                    matched = True
                                    break
                            
                            if not matched:
                                new_meaning_block = {
                                    'primary_def': new_def,
                                    'all_definitions': [{'text': new_def, 'source': source_name, 'color': color}],
                                    'examples': [{'text': ex, 'source': source_name, 'color': color} for ex in sense['examples']]
                                }
                                master_data[pos]['meanings'].append(new_meaning_block)

            except Exception as e:
                logger.error(f"Error aggregating semantic features from {dict_name}: {e}")

        # Return structured data ready for the UI
        return {
            "word": query,
            "pos_blocks": list(master_data.values())
        }

    # Add this to DictionaryService in dict_service.py
    def get_config(self):
        """Returns the current layout configuration for the frontend."""
        config = []
        for name, handler in self.active_dictionaries.items():
            config.append({
                "name": name,
                "display_name": getattr(handler, 'display_name', name),
                "color": handler.color,
                "enabled": getattr(handler, 'enabled', True)
            })
        return config

    def update_config(self, new_config):
        """Saves the new configuration to a JSON file and reorders the active dictionaries."""
        import json, os
        config_path = os.path.join('dict', 'dict_config.json') # Saves in your dict/ folder
        
        with open(config_path, 'w') as f:
            json.dump(new_config, f, indent=4)
            
        self.apply_config()

    def apply_config(self):
        """Applies the saved JSON config to the dictionaries (Order, Color, Enabled)."""
        import json, os
        config_path = os.path.join('dict', 'dict_config.json')
        
        if not os.path.exists(config_path):
            # If no config exists, default everyone to enabled
            for handler in self.active_dictionaries.values():
                handler.enabled = True
            return

        with open(config_path, 'r') as f:
            saved_config = json.load(f)

        # 1. Rebuild the dictionary to respect the new order
        reordered_dicts = {}
        
        # Add dictionaries in the order specified by the saved config
        for item in saved_config:
            name = item['name']
            if name in self.active_dictionaries:
                handler = self.active_dictionaries[name]
                handler.color = item.get('color', handler.color)
                handler.enabled = item.get('enabled', True)
                reordered_dicts[name] = handler
                
        # Append any new dictionaries that aren't in the config file yet
        for name, handler in self.active_dictionaries.items():
            if name not in reordered_dicts:
                handler.enabled = True
                reordered_dicts[name] = handler

        self.active_dictionaries = reordered_dicts