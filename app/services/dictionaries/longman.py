from .base import BaseDictionary
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

class LAAD3Dictionary(BaseDictionary):
    """
    Specialized Extractor for Longman Advanced American Dictionary 3rd Edition.
    Famous for its hidden popups (.at-link), extreme granularity in frequency tags (S1/W1), 
    and explicit grammatical frames.
    """

    def __init__(self, db_path, name, color):
        super().__init__(db_path, name, color)
        self.display_name = "Longman Advanced American"

    def finalize_html(self, soup, word, word_id=None, pinned_ids=None):
        # 1. Inject global CSS
        global_style = soup.new_tag("link", attrs={"rel": "stylesheet", "type": "text/css", "href": "/static/css/global_dict.css"})
        soup.insert(0, global_style)

        # 2. Inject TTS Buttons
        # LAAD3 uses <span class="example"> or <span class="example display">
        for ex in soup.find_all('span', class_=re.compile(r'^example')):
            # The example span usually contains the audio button first, then the text
            # We want to extract just the text for our custom TTS player
            text_nodes = ex.find_all(text=True, recursive=False)
            text = "".join(text_nodes).strip()
            
            if text:
                clean_sentence = text.replace('~', word).replace("'", "\\'").replace('"', '&quot;')

                speaker_btn = soup.new_tag("button", attrs={
                    "class": "laad-custom-tts ml-1", 
                    "onclick": f"if(window.parent.playTTSAudio) {{ window.parent.playTTSAudio('{clean_sentence}'); }} else {{ window.playTTSAudio('{clean_sentence}'); }}",
                    "type": "button"
                })
                svg_html = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="pointer-events: none;"><path d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>'
                speaker_btn.append(BeautifulSoup(svg_html, 'html.parser'))
                ex.append(speaker_btn)

        return str(soup)

    # Helper function to remove duplicates while preserving order
    def _dedupe(self, lst):
        return list(dict.fromkeys(lst))

    # ==========================================
    # 1. CORE LEXICAL & PHONETIC
    # ==========================================
    def _get_headwords(self, soup):
        return self._dedupe([hw.get_text(strip=True) for hw in soup.find_all('span', class_='hwd')])

    def _get_homograph_index(self, soup):
        return self._dedupe([h.get_text(strip=True) for h in soup.find_all('span', class_='homnum')])

    def _get_syllabification(self, soup):
        # LAAD3 is brilliant: it uses <span class="hs0"></span> to silently mark syllable breaks!
        # e.g., a<span class="hs0"></span>ban<span class="hs0"></span>don
        results = []
        for hyph in soup.find_all('span', class_='hyphenation'):
            clone = BeautifulSoup(str(hyph), 'html.parser').find('span')
            # Replace the hidden syllable markers with a visible dot
            for hs in clone.find_all('span', class_=re.compile(r'^hs')):
                hs.replace_with('·')
            # Remove the homograph numbers (like the '1' in abandon1)
            for sup in clone.find_all('sup'):
                sup.decompose()
            
            text = clone.get_text(strip=True)
            if '·' in text:
                results.append(text)
        return self._dedupe(results)

    def _get_pos(self, soup):
        return self._dedupe([p.get_text(strip=True) for p in soup.find_all('span', class_='pos')])

    def _get_ipa(self, soup):
        # LAAD is an American dictionary, so almost all proncodes are US.
        ipas = [p.get_text(strip=True) for p in soup.find_all('span', class_='pron')]
        return {"UK": [], "US": self._dedupe(ipas)}

    def _get_audio_links(self, soup):
        results = {"UK": [], "US": []}
        for a in soup.find_all('a', class_='jp-play'):
            href = a.get('href', '').replace('sound://', '')
            if href:
                # LAAD audio paths often contain 'ame/' indicating American English
                results["US"].append(href)
        return {"UK": [], "US": self._dedupe(results["US"])}

    # ==========================================
    # 2. DEFINITION & SENSE HIERARCHY
    # ==========================================
    def _get_signposts(self, soup):
        # LAAD3 uses <span class="signpost"> for things like "PAST ACTIVITIES"
        return self._dedupe([s.get_text(strip=True) for s in soup.find_all('span', class_='signpost')])

    def _get_definitions(self, soup):
        results = []
        for d in soup.find_all('span', class_='def'):
            # Ignore definitions that are just explaining synonyms inside the Thesaurus popup!
            if not d.find_parent('div', class_='at-link'):
                results.append(d.get_text(strip=True))
        return self._dedupe(results)

    def _get_phrases_idioms(self, soup):
        # Housed in <span class="lexunit">
        return self._dedupe([p.get_text(strip=True) for p in soup.find_all('span', class_='lexunit')])

    def _get_phrasal_verbs(self, soup):
        # Housed in <span class="phrvbentry"> -> <span class="phrvbhwd">
        return self._dedupe([pv.get_text(separator='', strip=True) for pv in soup.find_all('span', class_='phrvbhwd')])

    # ==========================================
    # 3. EXAMPLES & CONTEXT
    # ==========================================
    def _get_examples(self, soup):
        results = []
        for ex in soup.find_all('span', class_=re.compile(r'^example')):
            # We don't want to extract the audio button HTML, just the text
            text_nodes = ex.find_all(text=True, recursive=False)
            text = "".join(text_nodes).strip()
            if text: results.append(text)
        return self._dedupe(results)

    def _get_extra_examples(self, soup):
        return [] # LAAD3 integrates all examples directly or puts them in popups

    def _get_inline_glosses(self, soup):
        # e.g., <span class="gloss"> (=stay awake when I want to be asleep)
        glosses = [g.get_text(strip=True).strip('(=) ') for g in soup.find_all('span', class_=['gloss', 'collgloss'])]
        return self._dedupe(glosses)

    def _get_images(self, soup):
        results = []
        for img in soup.find_all('img'):
            src = img.get('src', '')
            # Filter out UI icons
            if src and 'spkr' not in src and src not in results:
                results.append(src)
        return results

    # ==========================================
    # 4. GRAMMAR & SYNTAX
    # ==========================================
    def _get_grammar_codes(self, soup):
        # e.g., [transitive], and grammatical constructions like "focus on something"
        codes = [g.get_text(strip=True).strip('[]') for g in soup.find_all('span', class_='gram')]
        props = [p.get_text(strip=True) for p in soup.find_all('span', class_=['propform', 'propformprep'])]
        return self._dedupe(codes + props)

    def _get_inflections(self, soup):
        # E.g., "(past tense tore, past participle torn)"
        # Sometimes in <span class="inflections"> or <span class="verb_form">
        results = []
        for inf in soup.find_all('span', class_='inflections'):
            results.append(inf.get_text(strip=True).strip('()'))
        return self._dedupe(results)

    def _get_verb_tables(self, soup):
        # LAAD3 has full HTML tables showing all conjugations!
        results = []
        for table in soup.find_all('table'):
            # Convert the raw HTML table into a clean string or just save the raw HTML
            results.append(str(table)) 
        return self._dedupe(results)

    # ==========================================
    # 5. SEMANTIC LINKS
    # ==========================================
    def _get_synonyms(self, soup):
        results = []
        # 1. Inline Synonyms: <span class="synopp">SYN</span> document
        for syn in soup.find_all('span', class_='syn'):
            clean = syn.get_text(strip=True).replace('SYN', '').strip()
            if clean: results.append(clean)
            
        # 2. Thesaurus Popup entries: <span class="exp display">cancel</span>
        for exp in soup.find_all('span', class_='exp'):
            results.append(exp.get_text(strip=True))
            
        return self._dedupe(results)

    def _get_antonyms(self, soup):
        results = []
        for opp in soup.find_all('span', class_='opp'):
            clean = opp.get_text(strip=True).replace('OPP', '').strip()
            if clean: results.append(clean)
        return self._dedupe(results)

    def _get_collocations(self, soup):
        # Highly structured in the .at-link popups: <span class="colloc collo">
        results = [c.get_text(strip=True) for c in soup.find_all('span', class_=['colloc', 'collo'])]
        return self._dedupe(results)

    def _get_derivatives(self, soup):
        # Found in <span class="runon"><span class="deriv">—abandonment</span>
        return self._dedupe([d.get_text(strip=True).replace('—', '') for d in soup.find_all('span', class_='deriv')])

    def _get_cross_references(self, soup):
        # E.g., → see also track record
        results = []
        for xr in soup.find_all('span', class_='crossref'):
            a = xr.find('a')
            if a: results.append(a.get_text(strip=True))
        return self._dedupe(results)

    # ==========================================
    # 6. META-DATA & USAGE
    # ==========================================
    def _get_style_labels(self, soup):
        # E.g., formal, informal, disapproving
        return self._dedupe([r.get_text(strip=True) for r in soup.find_all('span', class_='registerlab')])

    def _get_topic_labels(self, soup):
        # E.g., computers, science, economics
        return self._dedupe([t.get_text(strip=True).strip(',') for t in soup.find_all('span', class_='topic') if t.get_text(strip=True) != ','])

    def _get_frequency_tags(self, soup):
        # Captures visual stars (●●○), spoken/written frequency (S1, W2), and Academic Word List (AWL)
        tags = []
        for tag in soup.find_all('span', class_=['level', 'freq', 'ac']):
            tags.append(tag.get_text(strip=True))
        return self._dedupe(tags)

    def _get_cefr_levels(self, soup):
        return [] # LAAD3 uses S1/W1 frequency instead of CEFR levels

    def _get_etymology(self, soup):
        # Housed in the popup <div class="etymology">
        etym = soup.find('div', class_='etymology')
        if etym:
            return etym.get_text(separator=' ', strip=True).replace('Origin:', '').strip()
        return None