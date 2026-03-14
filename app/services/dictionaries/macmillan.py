from .base import BaseDictionary
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

class MacmillanDictionary(BaseDictionary):
    """
    Specialized Handler & Extractor for Macmillan Dictionaries.
    Famous for Star Ratings, Semantic Menus, and rich Thesaurus snippets.
    """

    def __init__(self, db_path, name, color):
        super().__init__(db_path, name, color)
        self.display_name = 'Macmillan Advanced Dictionary'

    def finalize_html(self, soup, word, word_id=None, pinned_ids=None):
        # 1. Fix the Macmillan .png -> .gif bug
        for img in soup.find_all('img'):
            src = img.get('src')
            if src in ['/Br.png', '/Am.png', '/br.png', '/am.png']:
                img['src'] = src.replace('.png', '.gif').replace('.PNG', '.gif')
                
        # 2. Could inject TTS buttons here if desired in the future
        
        return str(soup)

    # ==========================================
    # 1. CORE LEXICAL & PHONETIC
    # ==========================================
    def _get_headwords(self, soup):
        # Macmillan wraps the main word in <span class="base"> inside an h1
        results = []
        for h1 in soup.find_all('span', class_=lambda c: c and 'h1' in c):
            base = h1.find('span', class_='base')
            if base: results.append(base.get_text(strip=True))
        return list(set(results))

    def _get_homograph_index(self, soup):
        # Wraps homographs in <div class="homograph">
        blocks = soup.find_all('div', class_='homograph')
        return [f"Entry {i+1}" for i in range(len(blocks))] if len(blocks) > 1 else []

    def _get_syllabification(self, soup):
        return [] # Macmillan doesn't explicitly mark syllables in this HTML

    def _get_pos(self, soup):
        return list(set([p.get_text(strip=True) for p in soup.find_all('span', class_='part-of-speech-ctx')]))

    def _get_ipa(self, soup):
        results = {"UK": [], "US": []}
        for pron_block in soup.find_all('span', class_='prons'):
            ipa_span = pron_block.find('span', class_='pron')
            if ipa_span:
                # Clean up the slashes: / əˈbændən / -> əˈbændən
                ipa = ipa_span.get_text(strip=True).replace('/', '').strip()
                
                # Macmillan cleverly uses the image source to denote region!
                img = pron_block.find('img')
                if img and 'us_' in img.get('src', '').lower():
                    if ipa not in results["US"]: results["US"].append(ipa)
                else:
                    if ipa not in results["UK"]: results["UK"].append(ipa)
        return results

    def _get_audio_links(self, soup):
        results = {"UK": [], "US": []}
        for a in soup.find_all('a', class_='audio-play-button'):
            href = a.get('href', '').replace('sound://', '')
            if not href: continue
            
            # Again, check the embedded image to sort UK vs US audio
            img = a.find('img')
            if img and 'us_' in img.get('src', '').lower():
                if href not in results["US"]: results["US"].append(href)
            else:
                if href not in results["UK"]: results["UK"].append(href)
        return results

    # ==========================================
    # 2. DEFINITION & SENSE HIERARCHY
    # ==========================================
    def _get_signposts(self, soup):
        # Macmillan's superpower: The Meaning Menu
        results = []
        menu = soup.find('div', class_='menu')
        if menu:
            for li in menu.find_all('li'):
                text = li.get_text(strip=True)
                # Ignore the internal structural links like "+phrases"
                if text and not text.startswith('+'): 
                    results.append(text)
        return results

    def _get_definitions(self, soup):
        return [d.get_text(strip=True) for d in soup.find_all('span', class_='definition')]

    def _get_phrases_idioms(self, soup):
        results = []
        # 1. Look for explicit multiword headings
        for phr in soup.find_all('h2', class_='multiword'):
            results.append(phr.get_text(strip=True))
        # 2. Look for phrase cross-references
        for phr_link in soup.find_all('li', class_='phr-xref'):
            results.append(phr_link.get_text(strip=True))
        return list(set(results))

    def _get_phrasal_verbs(self, soup):
        results = []
        for pv in soup.find_all('div', class_='phrasalverb'):
            entry = pv.find('h2', class_='entry')
            if entry: results.append(entry.get_text(strip=True))
        return results

    # ==========================================
    # 3. EXAMPLES & CONTEXT
    # ==========================================
    def _get_examples(self, soup):
        # Macmillan uses clean <p class="example"> tags!
        return [p.get_text(separator=' ', strip=True) for p in soup.find_all('p', class_='example')]

    def _get_extra_examples(self, soup):
        return [] # Macmillan usually integrates all examples directly into senses

    def _get_inline_glosses(self, soup):
        return [] # Macmillan rarely uses inline glosses, preferring the Thesaurus boxes

    def _get_images(self, soup):
        results = []
        for img in soup.find_all('img'):
            src = img.get('src')
            # Filter out the UI icons (stars, audio buttons) to find real illustrations
            if src and 'star' not in src and 'pron' not in src and src not in results:
                results.append(src)
        return results

    # ==========================================
    # 4. GRAMMAR & SYNTAX
    # ==========================================
    def _get_grammar_codes(self, soup):
        # E.g. [transitive], [uncountable]
        codes = [g.get_text(strip=True).strip('[]') for g in soup.find_all('span', class_='syntax-coding')]
        return list(set(codes))

    def _get_inflections(self, soup):
        results = []
        for inf in soup.find_all('span', class_='inflection-entry'):
            results.append(inf.get_text(strip=True))
        return list(set(results))

    def _get_verb_tables(self, soup):
        # Macmillan builds literal HTML tables out of spans (span.table, span.tr, span.td)
        results = []
        for table in soup.find_all('span', class_='table'):
            rows = []
            for tr in table.find_all('span', class_='tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all('span', class_='td')]
                if cells: rows.append(" | ".join(cells))
            if rows: results.append("\n".join(rows))
        return results

    # ==========================================
    # 5. SEMANTIC LINKS
    # ==========================================
    def _get_synonyms(self, soup):
        results = []
        # Target the embedded Thesaurus boxes
        for syn_group in soup.find_all('span', class_='synonyms'):
            for a in syn_group.find_all('a'):
                results.append(a.get_text(strip=True))
        return list(set(results))

    def _get_antonyms(self, soup):
        return [] # Explicit antonym tags not heavily used in this HTML structure

    def _get_collocations(self, soup):
        # Macmillan has beautiful explicit collocation spans!
        return [c.get_text(strip=True) for c in soup.find_all('span', class_='one-collocate')]

    def _get_derivatives(self, soup):
        # Derivatives are housed in <div class="runon">
        results = []
        for runon in soup.find_all('div', class_='runon'):
            hw = runon.find('h2', class_='entry')
            if hw: results.append(hw.get_text(strip=True))
        return list(set(results))

    def _get_cross_references(self, soup):
        results = []
        for rel in soup.find_all('div', class_='relatedentries'):
            for a in rel.find_all('a'):
                results.append(a.get_text(strip=True))
        return list(set(results))

    # ==========================================
    # 6. META-DATA & USAGE
    # ==========================================
    def _get_style_labels(self, soup):
        # Captures pragmatics (informal) and dialect (mainly American)
        labels = [lbl.get_text(strip=True) for lbl in soup.find_all('span', class_=['style-level', 'dialect'])]
        return list(set(labels))

    def _get_topic_labels(self, soup):
        # Captures subjects like (physics), (computing)
        return [subj.get_text(strip=True) for subj in soup.find_all('span', class_='subject-area')]

    def _get_frequency_tags(self, soup):
        tags = []
        
        # 1. Calculate Star Rating (e.g., returns "★★★")
        star_blocks = soup.find_all('span', class_='stars-grp')
        for block in star_blocks:
            star_count = len(block.find_all('span', class_='icon-star'))
            if star_count > 0:
                tags.append("★" * star_count)
                
        # 2. Check for Redword status (Core Vocabulary)
        if soup.find('span', class_='redword'):
            tags.append("Core Vocabulary (Red Word)")
            
        return list(set(tags))

    def _get_cefr_levels(self, soup):
        return [] # Not explicitly tagged in this raw HTML

    def _get_etymology(self, soup):
        return None