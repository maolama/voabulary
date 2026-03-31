import os
import sqlite3
import itertools
import urllib.parse
import re
import random
import math
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

            color = next(self.color_cycle)
            upper_name = dict_name.upper()
            
            if "OALD" in upper_name:
                handler = OALD9Dictionary(db_path, dict_name, color)
            elif "MACMILLAN" in upper_name:
                handler = MacmillanDictionary(db_path, dict_name, color)
            elif "CALD" in upper_name:
                handler = CALD4Dictionary(db_path, dict_name, color)
            elif "CCABELD" in upper_name or "COLLINS" in upper_name:
                handler = CCABELDDictionary(db_path, dict_name, color)
            elif "LONGMAN" in upper_name or "LAAD" in upper_name:
                handler = LAAD3Dictionary(db_path, dict_name, color)
            elif "MWALED" in upper_name or "MERRIAM" in upper_name:
                handler = MwaledDictionary(db_path, dict_name, color)
            else:
                handler = BaseDictionary(db_path, dict_name, color)

            self.active_dictionaries[dict_name] = handler
            
            if files['css']:
                self.css_paths[dict_name] = files['css']
            if files['js']: 
                self.js_paths[dict_name] = files['js']
            self.apply_config()

    def _build_database(self, dict_name, db_path, mdx_path, mdd_path):
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
        handler = self.active_dictionaries.get(dict_name)
        if not handler: return None
        try:
            conn = sqlite3.connect(handler.db_path)
            c = conn.cursor()
            c.execute("SELECT html FROM entries WHERE word = ? LIMIT 1", (word,))
            row = c.fetchone()
            conn.close()
            if row:
                return handler.process_html(row[0], word, word_id=word_id, pinned_ids=pinned_ids)
        except Exception as e:
            logger.error(f"Error retrieving HTML from {dict_name}: {e}")
        return None

    def search_word(self, query):
        matched_dicts = []
        if not query: return matched_dicts

        for dict_name, handler in self.active_dictionaries.items():
            if not getattr(handler, 'enabled', True): continue
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
        if not prefix or len(prefix) < 2: return []
        suggestions = set()
        search_term = f"{prefix}%"
        for dict_name, handler in self.active_dictionaries.items():
            if not getattr(handler, 'enabled', True): continue
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
    
    # NEW: Exponential Decay Softmax AND Similarity Grouping Mechanisms added!
    def get_short_definition(self, query, allowed_dicts=None, use_softmax=True):
        """
        Collects definitions, assigns probability weights based on usage frequency (rank and POS),
        and selects randomly using either Softmax probability or Similarity Grouping.
        """
        if not query: return "No short definition available."
        
        logger.debug(f"[*] [DEF SEARCH] Looking for smart weighted definition for: '{query}' (Mode: {'Softmax' if use_softmax else 'Similarity'})")
        
        # List to hold tuples: (definition_text, pos_index, meaning_index, dictionary_name)
        collected_defs = [] 
        
        for dict_name, handler in self.active_dictionaries.items():
            if not getattr(handler, 'enabled', True): continue
            if allowed_dicts and not any(d.lower() in dict_name.lower() for d in allowed_dicts):
                continue

            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT html FROM entries WHERE word = ? LIMIT 1", (query,))
                row = c.fetchone()
                conn.close()
                
                if row:
                    features = handler.extract_features(row[0])
                    
                    # Store definitions alongside their strict hierarchy indices
                    if isinstance(features, list):
                        for p_idx, block in enumerate(features):
                            for m_idx, meaning in enumerate(block.get('meanings', [])):
                                if meaning.get('definition'):
                                    collected_defs.append((meaning['definition'], p_idx, m_idx, dict_name))
                    elif isinstance(features, dict):
                        defs = features.get('definitions', [])
                        for m_idx, d in enumerate(defs):
                            # Older dicts don't have POS blocks, assume primary POS (0)
                            collected_defs.append((d, 0, m_idx, dict_name))
                            
            except Exception as e:
                logger.error(f"[-] [DEF ERROR] Error getting short definition from {dict_name}: {e}")
                
        if not collected_defs:
            return "No short definition available."

        clean_text = ""

        if use_softmax:
            # MECHANISM 1: Softmax with POS-aware Exponential Decay
            # Formula: Base Score = 5 - (meaning_index) - (2 * pos_index)
            # This creates a massive drop-off for secondary POS blocks!
            scores = []
            for cdef in collected_defs:
                text, p_idx, m_idx, source = cdef
                raw_score = max(0.0, 5.0 - m_idx - (2.0 * p_idx))
                scores.append(raw_score)

            # Apply Softmax (e^score / sum(e^scores)) to convert into valid probabilities
            exp_scores = [math.exp(s) for s in scores]
            sum_exp = sum(exp_scores)
            probabilities = [e / sum_exp for e in exp_scores]

            # Select based on the generated probability distribution
            population = [c[0] for c in collected_defs]
            clean_text = random.choices(population, weights=probabilities, k=1)[0]
            
            logger.debug(f"[+] [DEF FOUND] Softmax Selection Applied. Formed {len(collected_defs)} probabilities.")

        else:
            # MECHANISM 2: Similarity Grouping & Consolidation
            # Groups definitions describing the exact same concept across multiple dictionaries
            clusters = [] 

            for cdef in collected_defs:
                text, p_idx, m_idx, source = cdef
                matched = False

                for cluster in clusters:
                    # Compare using our Jaccard similarity function
                    if self._calculate_similarity(text, cluster['rep_text']) > 0.20:
                        cluster['members'].append(cdef)
                        # Boost cluster score. More dicts agreeing = massively higher weight!
                        cluster['score'] += max(0.5, 5.0 - m_idx - (2.0 * p_idx))
                        matched = True
                        break

                if not matched:
                    # Create new cluster
                    clusters.append({
                        'rep_text': text,
                        'members': [cdef],
                        'score': max(0.5, 5.0 - m_idx - (2.0 * p_idx))
                    })

            # Select a cluster based on the combined cluster scores
            cluster_weights = [c['score'] for c in clusters]
            winning_cluster = random.choices(clusters, weights=cluster_weights, k=1)[0]

            # Pick the representative text of the winning cluster
            clean_text = winning_cluster['rep_text']
            
            logger.debug(f"[+] [DEF FOUND] Similarity Grouping Applied. Condensed into {len(clusters)} clusters.")

        # Final UI cleanup
        if len(clean_text) > 150:
            clean_text = clean_text[:147] + "..."
            
        logger.info(f"[+] [DEF FOUND] Selected definition: {clean_text[:50]}...")
        return clean_text

    def has_audio(self, query):
        search_term = f"/{query}.%" 
        for dict_name, handler in self.active_dictionaries.items():
            if not getattr(handler, 'enabled', True): continue
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
        if not text1 or not text2: return 0.0
        words1 = set(re.findall(r'\b\w{3,}\b', text1.lower()))
        words2 = set(re.findall(r'\b\w{3,}\b', text2.lower()))
        if not words1 or not words2: return 0.0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union)

    def get_aggregated_features(self, query, allowed_dicts=None):
        """Aggregates hierarchical semantic features from updated dictionaries."""
        if not query: return None
        master_data = {}

        for dict_name, handler in self.active_dictionaries.items():
            if not getattr(handler, 'enabled', True): continue
            if allowed_dicts and not any(d.lower() in dict_name.lower() for d in allowed_dicts):
                continue

            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT html FROM entries WHERE word = ? LIMIT 1", (query,))
                row = c.fetchone()
                conn.close()

                if row:
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

                        if not master_data[pos]['ukPronunciation'] and block.get('ukPronunciation'):
                            master_data[pos]['ukPronunciation'] = block.get('ukPronunciation')
                        if not master_data[pos]['usPronunciation'] and block.get('usPronunciation'):
                            master_data[pos]['usPronunciation'] = block.get('usPronunciation')

                        for idiom in block.get('idioms', []):
                            if idiom not in [i['text'] for i in master_data[pos]['idioms']]:
                                master_data[pos]['idioms'].append({'text': idiom, 'source': source_name, 'color': color})

                        for sense in block.get('meanings', []):
                            new_def = sense['definition']
                            matched = False
                            
                            for existing_meaning in master_data[pos]['meanings']:
                                sim_score = self._calculate_similarity(new_def, existing_meaning['primary_def'])
                                
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

        return {
            "word": query,
            "pos_blocks": list(master_data.values())
        }

    def get_word_relations(self, query):
        """Extracts, normalizes, and deduplicates synonyms and antonyms from all active dictionaries."""
        if not query: return {"synonyms": [], "antonyms": []}
        
        synonyms = set()
        antonyms = set()
        
        for dict_name, handler in self.active_dictionaries.items():
            if not getattr(handler, 'enabled', True): continue
            
            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT html FROM entries WHERE word = ? LIMIT 1", (query,))
                row = c.fetchone()
                conn.close()
                
                if row:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(row[0], 'html.parser')
                    
                    raw_syns = handler._get_synonyms(soup)
                    raw_ants = handler._get_antonyms(soup)
                    
                    for word_list, target_set in [(raw_syns, synonyms), (raw_ants, antonyms)]:
                        for item in word_list:
                            # FIX: Split ONLY by commas or slashes, preserving spaces for phrases!
                            for sub_item in re.split(r'[,/]', item):
                                # Strip out weird dictionary tags, keep letters and spaces
                                clean_item = re.sub(r'[^a-zA-Z\s-]', '', sub_item).strip().lower()
                                
                                # Ensure we don't accidentally list the word itself as its own synonym!
                                if clean_item and clean_item != query.lower() and len(clean_item) > 1:
                                    target_set.add(clean_item)
                                    
            except Exception as e:
                logger.error(f"Error getting relations from {dict_name}: {e}")
                
        return {
            "synonyms": sorted(list(synonyms)),
            "antonyms": sorted(list(antonyms))
        }
    
    def get_config(self):
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
        import json, os
        config_path = os.path.join('dict', 'dict_config.json') 
        with open(config_path, 'w') as f:
            json.dump(new_config, f, indent=4)
        self.apply_config()

    def apply_config(self):
        import json, os
        config_path = os.path.join('dict', 'dict_config.json')
        if not os.path.exists(config_path):
            for handler in self.active_dictionaries.values():
                handler.enabled = True
            return

        with open(config_path, 'r') as f:
            saved_config = json.load(f)

        reordered_dicts = {}
        for item in saved_config:
            name = item['name']
            if name in self.active_dictionaries:
                handler = self.active_dictionaries[name]
                handler.color = item.get('color', handler.color)
                handler.enabled = item.get('enabled', True)
                reordered_dicts[name] = handler
                
        for name, handler in self.active_dictionaries.items():
            if name not in reordered_dicts:
                handler.enabled = True
                reordered_dicts[name] = handler

        self.active_dictionaries = reordered_dicts

    def get_native_audio(self, query, allowed_dicts=None):
        if not query: return {"UK": None, "US": None}
        logger.debug(f"[*] [AUDIO SEARCH] Looking for native audio for: '{query}'")
        
        for dict_name, handler in self.active_dictionaries.items():
            if not getattr(handler, 'enabled', True): continue
            if allowed_dicts and not any(d.lower() in dict_name.lower() for d in allowed_dicts):
                continue

            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT html FROM entries WHERE word = ? COLLATE NOCASE LIMIT 1", (query,))
                row = c.fetchone()
                conn.close()
                
                if row:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(row[0], 'html.parser')
                    links = handler._get_audio_links(soup)
                    
                    if links.get("UK") or links.get("US"):
                        logger.debug(f"[+] [AUDIO FOUND] HTML Extractor ({dict_name}) found: {links}")
                        uk = links.get("UK", [])
                        us = links.get("US", [])
                        return {
                            "UK": f"/{uk[0].lstrip('/')}" if uk else None,
                            "US": f"/{us[0].lstrip('/')}" if us else None
                        }
            except Exception as e:
                logger.error(f"[-] [AUDIO ERROR] HTML Extraction failed in {dict_name}: {e}")
                
        logger.debug(f"[!] [AUDIO FALLBACK] HTML extractor failed. Trying precise media search for '{query}'...")
        try:
            search_term = f"%/{query}%"
            for dict_name, handler in self.active_dictionaries.items():
                if allowed_dicts and not any(d.lower() in dict_name.lower() for d in allowed_dicts):
                    continue

                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("""
                    SELECT filepath FROM media 
                    WHERE filepath LIKE ? AND (filepath LIKE '%.mp3' OR filepath LIKE '%.spx' OR filepath LIKE '%.wav')
                """, (search_term,))
                rows = c.fetchall()
                conn.close()
                
                if rows:
                    uk_file, us_file = None, None
                    for r in rows:
                        fp = r[0].lower()
                        filename = fp.split('/')[-1] 
                        
                        if filename.startswith(f"{query}.") or filename.startswith(f"{query}_") or filename.startswith(f"{query}1"):
                            if '_uk' in fp or '_gb' in fp or 'bre' in fp: 
                                uk_file = f"/{r[0].lstrip('/')}"
                            elif '_us' in fp or '_am' in fp or 'ame' in fp: 
                                us_file = f"/{r[0].lstrip('/')}"
                            elif not us_file:
                                us_file = f"/{r[0].lstrip('/')}"
                                
                    if uk_file or us_file:
                        logger.debug(f"[+] [AUDIO FOUND] Fuzzy Search ({dict_name}) matched: UK({uk_file}), US({us_file})")
                        return {"UK": uk_file, "US": us_file}
                        
        except Exception as e:
             logger.error(f"[-] [AUDIO ERROR] Fuzzy search failed: {e}")
            
        logger.warning(f"[-] [AUDIO MISSING] Could not find any native audio for '{query}'.")
        return {"UK": None, "US": None}