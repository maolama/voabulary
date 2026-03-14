import sqlite3
import re
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class BaseDictionary:
    """
    Generic blueprint for all dictionaries.
    Handles HTML standardization and enforces the 26-feature extraction contract.
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

        # Pass pinned_ids down to finalize_html
        return self.finalize_html(soup, word, word_id, pinned_ids)

    def finalize_html(self, soup, word, word_id=None, pinned_ids=None):
        # Default behavior does nothing with pins, just returns HTML
        return str(soup)

    # ==========================================
    # DATA EXTRACTION CONTRACTS (The 26-Feature Union)
    # ==========================================
    
    def extract_features(self, html):
        """Master function to extract ALL 26 available features."""
        if not html: return {}
        soup = BeautifulSoup(html, 'html.parser')
        
        return {
            "dict_name": self.name,
            
            # 1. Core Lexical & Phonetic
            "headwords": self._get_headwords(soup),
            "homograph_index": self._get_homograph_index(soup),
            "syllabification": self._get_syllabification(soup),
            "pos": self._get_pos(soup),
            "ipa": self._get_ipa(soup),
            "audio_links": self._get_audio_links(soup),

            # 2. Definition & Sense Hierarchy
            "signposts": self._get_signposts(soup),
            "definitions": self._get_definitions(soup),
            "phrases_idioms": self._get_phrases_idioms(soup),
            "phrasal_verbs": self._get_phrasal_verbs(soup),

            # 3. Example Sentences & Context
            "examples": self._get_examples(soup),
            "extra_examples": self._get_extra_examples(soup),
            "inline_glosses": self._get_inline_glosses(soup),
            "images": self._get_images(soup),

            # 4. Grammar & Syntax
            "grammar_codes": self._get_grammar_codes(soup),
            "inflections": self._get_inflections(soup),
            "verb_tables": self._get_verb_tables(soup),

            # 5. Semantic Links
            "synonyms_thesaurus": self._get_synonyms(soup),
            "antonyms": self._get_antonyms(soup),
            "collocations": self._get_collocations(soup),
            "derivatives": self._get_derivatives(soup),
            "cross_references": self._get_cross_references(soup),

            # 6. Meta-Data & Usage
            "style_labels": self._get_style_labels(soup),
            "topic_labels": self._get_topic_labels(soup),
            "frequency_tags": self._get_frequency_tags(soup),
            "etymology": self._get_etymology(soup)
        }

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