from .base import BaseDictionary
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

class MwaledDictionary(BaseDictionary):
    """
    Specialized Extractor for Merriam-Webster's Advanced Learner's Dictionary.
    Famous for its American context, rigid semantic classes (vi_content, def_text), 
    and bracketed inline glosses inside examples.
    """

    def __init__(self, db_path, name, color):
        super().__init__(db_path, name, color)
        self.display_name = "Merriam-Webster Advanced"

    def finalize_html(self, soup, word, word_id=None, pinned_ids=None):
        # 1. Inject global CSS
        global_style = soup.new_tag("link", attrs={"rel": "stylesheet", "type": "text/css", "href": "/static/css/global_dict.css"})
        soup.insert(0, global_style)

        # 2. Inject TTS Buttons next to Verbal Illustrations (vi_content)
        for vi in soup.find_all('div', class_='vi_content'):
            text = vi.get_text(strip=True)
            if not text: continue
            
            # Remove the bracketed inline glosses from the audio playback text
            clean_sentence = re.sub(r'\[=.*?\]', '', text)
            clean_sentence = clean_sentence.replace('~', word).replace("'", "\\'").replace('"', '&quot;').strip()

            speaker_btn = soup.new_tag("button", attrs={
                "class": "mwaled-custom-tts ml-1", 
                "onclick": f"if(window.parent.playTTSAudio) {{ window.parent.playTTSAudio('{clean_sentence}'); }} else {{ window.playTTSAudio('{clean_sentence}'); }}",
                "type": "button"
            })
            # Using a teal color for MWALED's SVG button
            svg_html = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0d9488" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="pointer-events: none;"><path d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>'
            speaker_btn.append(BeautifulSoup(svg_html, 'html.parser'))
            vi.append(speaker_btn)

        return str(soup)

    # Helper function to remove duplicates (crucial for MWALED due to mobile/desktop HTML duplication)
    def _dedupe(self, lst):
        return list(dict.fromkeys(lst))

    # ==========================================
    # 1. CORE LEXICAL & PHONETIC
    # ==========================================
    def _get_headwords(self, soup):
        results = []
        for hw in soup.find_all('span', class_='hw_txt'):
            # Remove homograph numbers like <sup>1</sup> before getting text
            clone = BeautifulSoup(str(hw), 'html.parser').find('span')
            for sup in clone.find_all('sup', class_='homograph'):
                sup.decompose()
            results.append(clone.get_text(strip=True))
        return self._dedupe(results)

    def _get_homograph_index(self, soup):
        return self._dedupe([sup.get_text(strip=True) for sup in soup.find_all('sup', class_='homograph')])

    def _get_syllabification(self, soup):
        # MWALED hides syllabification in the data-word attribute of the audio play button! (e.g. "aban*don*ment")
        results = []
        for a in soup.find_all('a', class_='play_pron', attrs={'data-word': True}):
            word_data = a.get('data-word', '')
            if '*' in word_data:
                results.append(word_data.replace('*', '·'))
        return self._dedupe(results)

    def _get_pos(self, soup):
        # Uses class="fl" (functional label)
        return self._dedupe([fl.get_text(strip=True) for fl in soup.find_all(['span', 'div'], class_='fl')])

    def _get_ipa(self, soup):
        results = []
        for hpron in soup.find_all('span', class_='hpron_word'):
            clone = BeautifulSoup(str(hpron), 'html.parser').find('span')
            # Fix MWALED's weird stress mark wrapper <span class="smark">ˈ</span>
            for smark in clone.find_all('span', class_='smark'):
                smark.replace_with(smark.get_text())
            results.append(clone.get_text(strip=True).replace('/', '').strip())
        # MWALED is an American dictionary; default to US
        return {"UK": [], "US": self._dedupe(results)}

    def _get_audio_links(self, soup):
        results = []
        for a in soup.find_all('a', class_='play_pron'):
            href = a.get('href', '').replace('sound://', '')
            if href: results.append(href)
        return {"UK": [], "US": self._dedupe(results)}

    # ==========================================
    # 2. DEFINITION & SENSE HIERARCHY
    # ==========================================
    def _get_signposts(self, soup):
        # MWALED occasionally uses <span class="sd"> for sense dividers / signposts
        return self._dedupe([sd.get_text(strip=True) for sd in soup.find_all('span', class_='sd')])

    def _get_definitions(self, soup):
        return self._dedupe([d.get_text(strip=True) for d in soup.find_all('span', class_='def_text')])

    def _get_phrases_idioms(self, soup):
        # "Defined Run-Ons" (dre) often contain idioms
        return self._dedupe([dre.get_text(strip=True) for dre in soup.find_all(['h2', 'span'], class_='dre')])

    def _get_phrasal_verbs(self, soup):
        # MWALED generally mixes phrasal verbs into the 'dre' class or makes them separate entries entirely.
        return []

    # ==========================================
    # 3. EXAMPLES & CONTEXT
    # ==========================================
    def _get_examples(self, soup):
        # "Verbal Illustrations"
        return self._dedupe([vi.get_text(separator=' ', strip=True) for vi in soup.find_all('div', class_='vi_content')])

    def _get_extra_examples(self, soup):
        return [] # MWALED groups all examples tightly inside specific senses

    def _get_inline_glosses(self, soup):
        # MWALED is famous for inserting bracketed glosses inside examples: [=to sell their stock]
        results = []
        for vi in soup.find_all('div', class_='vi_content'):
            text = vi.get_text(separator=' ', strip=True)
            # Find all text matching [=something]
            matches = re.findall(r'\[=(.*?)\]', text)
            results.extend(matches)
        return self._dedupe(results)

    def _get_images(self, soup):
        results = []
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src and 'star' not in src: results.append(src)
        return self._dedupe(results)

    # ==========================================
    # 4. GRAMMAR & SYNTAX
    # ==========================================
    def _get_grammar_codes(self, soup):
        # Uses classes: gram, wsgram, sgram
        return self._dedupe([g.get_text(strip=True).strip('[]') for g in soup.find_all('span', class_=['gram', 'wsgram', 'sgram'])])

    def _get_inflections(self, soup):
        results = []
        for i_text in soup.find_all('span', class_='i_text'):
            results.append(i_text.get_text(strip=True).strip(';,'))
        return self._dedupe(results)

    def _get_verb_tables(self, soup):
        return [] # MWALED lacks giant grid verb tables

    # ==========================================
    # 5. SEMANTIC LINKS
    # ==========================================
    def _get_synonyms(self, soup):
        results = []
        # Looks for synonym/cross-reference tags
        for syn in soup.find_all(['span', 'a'], class_=['syn', 'sx', 'dxt']):
            results.append(syn.get_text(strip=True))
        return self._dedupe(results)

    def _get_antonyms(self, soup):
        return self._dedupe([ant.get_text(strip=True) for ant in soup.find_all('span', class_='ant')])

    def _get_collocations(self, soup):
        # Collocations are usually highlighted via <em class="mw_spm_it"> within examples
        return [] 

    def _get_derivatives(self, soup):
        # "Undefined Run-Ons" (ure)
        results = []
        for ure in soup.find_all(['h2', 'span'], class_='ure'):
            results.append(ure.get_text(strip=True).replace('—', '').strip())
        return self._dedupe(results)

    def _get_cross_references(self, soup):
        results = []
        for a in soup.find_all('a', class_='otherwords'):
            results.append(a.get_text(strip=True))
        return self._dedupe(results)

    # ==========================================
    # 6. META-DATA & USAGE
    # ==========================================
    def _get_style_labels(self, soup):
        # Includes things like 'informal', 'literary'
        return self._dedupe([sl.get_text(strip=True) for sl in soup.find_all('span', class_=['sl', 'slb'])])

    def _get_topic_labels(self, soup):
        return [] # MWALED usually merges topic labels into the standard 'sl' style label

    def _get_frequency_tags(self, soup):
        return []

    def _get_cefr_levels(self, soup):
        return []

    def _get_etymology(self, soup):
        return None