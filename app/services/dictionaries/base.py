import sqlite3
import re
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class BaseDictionary:
    """
    Generic blueprint for all dictionaries.
    Handles HTML standardization and enforces the data extraction contract.
    """
    def __init__(self, db_path, name, color):
        self.db_path = db_path
        self.name = name
        self.color = color

    def process_html(self, html, word, word_id=None, pinned_ids=None):
        if not html: return ""
        soup = BeautifulSoup(html, 'html.parser')
        
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href')
            if href and not href.startswith(('http', '/')):
                link['href'] = f"/entry/{self.name}/{href}"
                
        for tag, attr in [('img', 'src'), ('script', 'src'), ('source', 'src')]:
            for node in soup.find_all(tag):
                val = node.get(attr)
                if val and not val.startswith(('http', '/', 'data:', 'javascript:')):
                    node[attr] = f"/{val}"

        for a in soup.find_all('a', href=re.compile(r'^sound://', re.I)):
            sound_file = a['href'].replace('sound://', '')
            if not sound_file.startswith('/'):
                sound_file = f"/{sound_file}"
            a['href'] = "javascript:void(0);"
            a['onclick'] = f"new Audio('{sound_file}').play();"

        return self.finalize_html(soup, word, word_id, pinned_ids)

    def finalize_html(self, soup, word, word_id=None, pinned_ids=None):
        return str(soup)

    # ==========================================
    # DATA EXTRACTION CONTRACT
    # ==========================================
    
    def extract_features(self, html):
        """
        Master function to extract ALL available features.
        Upgraded to dynamically build the modernized Hierarchical POS Block format (List of Dicts).
        This ensures dictionaries that do not override this method natively support the Dojo.
        """
        if not html: return []
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. Gather all the flat data using the specific dictionary's helpers
        pos_list = self._get_pos(soup)
        primary_pos = pos_list[0] if pos_list else "unknown"

        ipas = self._get_ipa(soup) or {"UK": [], "US": []}
        uk_pron = f"/{ipas['UK'][0]}/" if ipas.get('UK') else ""
        us_pron = f"/{ipas['US'][0]}/" if ipas.get('US') else ""

        definitions = self._get_definitions(soup) or []
        examples = self._get_examples(soup) or []
        idioms = (self._get_phrases_idioms(soup) or []) + (self._get_phrasal_verbs(soup) or [])

        # 2. Package it into the modern semantic block format
        meanings = []
        if definitions:
            for i, d in enumerate(definitions):
                # Best-effort linear pairing of definitions to examples for older HTML structures
                ex = [examples[i]] if i < len(examples) else []
                meanings.append({
                    "definition": d,
                    "examples": ex
                })
        elif examples:
            meanings.append({
                "definition": "See examples for context.",
                "examples": examples
            })

        pos_block = {
            "partOfSpeech": primary_pos,
            "ukPronunciation": uk_pron,
            "usPronunciation": us_pron,
            "meanings": meanings,
            "idioms": list(set(idioms))
        }

        return [pos_block]

    # --- Abstract methods: Children MUST override these ---
    def _get_headwords(self, soup): return []
    def _get_homograph_index(self, soup): return []
    def _get_syllabification(self, soup): return []
    def _get_pos(self, soup): return []
    def _get_ipa(self, soup): return {}
    def _get_audio_links(self, soup): return {}
    def _get_signposts(self, soup): return []
    def _get_definitions(self, soup): return []
    def _get_phrases_idioms(self, soup): return []
    def _get_phrasal_verbs(self, soup): return []
    def _get_examples(self, soup): return []
    def _get_extra_examples(self, soup): return []
    def _get_inline_glosses(self, soup): return []
    def _get_images(self, soup): return []
    def _get_grammar_codes(self, soup): return []
    def _get_inflections(self, soup): return []
    def _get_verb_tables(self, soup): return []
    def _get_synonyms(self, soup): return []
    def _get_antonyms(self, soup): return []
    def _get_collocations(self, soup): return []
    def _get_derivatives(self, soup): return []
    def _get_cross_references(self, soup): return []
    def _get_style_labels(self, soup): return []
    def _get_topic_labels(self, soup): return []
    def _get_frequency_tags(self, soup): return []
    def _get_cefr_levels(self, soup): return []
    def _get_etymology(self, soup): return None