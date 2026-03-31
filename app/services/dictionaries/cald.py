from .base import BaseDictionary
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

class CALD4Dictionary(BaseDictionary):
    """
    Specialized Extractor for Cambridge Advanced Learner's Dictionary 4th Ed.
    """

    def __init__(self, db_path, name, color):
        super().__init__(db_path, name, color)
        self.display_name = "Cambridge Advanced Learner's 4"

    def finalize_html(self, soup, word, word_id=None, pinned_ids=None):
        global_style = soup.new_tag("link", attrs={"rel": "stylesheet", "type": "text/css", "href": "/static/css/global_dict.css"})
        soup.insert(0, global_style)

        for font in soup.find_all('font', color='gray'):
            text = font.get_text(strip=True)
            if text.startswith('»'):
                clean_sentence = text.replace('»', '').replace('~', word).replace("'", "\\'").replace('"', '&quot;').strip()

                speaker_btn = soup.new_tag("button", attrs={
                    "class": "cald-custom-tts ml-1", 
                    "onclick": f"if(window.parent.playTTSAudio) {{ window.parent.playTTSAudio('{clean_sentence}'); }} else {{ window.playTTSAudio('{clean_sentence}'); }}",
                    "type": "button"
                })
                svg_html = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="pointer-events: none;"><path d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>'
                speaker_btn.append(BeautifulSoup(svg_html, 'html.parser'))
                font.append(speaker_btn)

        return str(soup)

    # ==========================================
    # SEMANTIC HIERARCHICAL EXTRACTOR
    # ==========================================
    def extract_features(self, html):
        """Extracts features in a strict hierarchical format for CALD."""
        result = []
        if not html: return result
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # CALD is tricky because it doesn't wrap entries in clean divs. 
        # We will simulate a single POS block based on the first POS found.
        
        # 1. Get POS (Teal background in CALD)
        pos = "unknown"
        for span in soup.find_all('span'):
            style = span.get('style', '')
            if 'background-color: #3F7373' in style or 'background-color:#3F7373' in style.replace(' ', ''):
                pos = span.get_text(strip=True).lower()
                break
                
        # 2. Get Phonetics
        text = soup.get_text(separator=' ')
        ipas = re.findall(r'/([^/]+)/', text)
        uk_pron = f"/{ipas[0].strip()}/" if len(ipas) >= 1 else ""
        us_pron = f"/{ipas[1].strip()}/" if len(ipas) >= 2 else ""
        
        pos_block = {
            "partOfSpeech": pos,
            "ukPronunciation": uk_pron,
            "usPronunciation": us_pron,
            "meanings": [],
            "idioms": []
        }

        # 3. Extract Definitions and Examples
        # In CALD, definitions start with ►. Examples follow them starting with »
        current_meaning = None
        is_extra_section = False
        
        for span in soup.find_all('span'):
            span_text = span.get_text(separator=' ', strip=True)
            
            # Detect boundaries where examples stop belonging to the definition
            if 'Extra Examples' in span_text or 'Word partners' in span_text or 'Collocations' in span_text:
                is_extra_section = True
                current_meaning = None
                continue
                
            if '►' in span_text:
                is_extra_section = False
                clean_def = re.sub(r'►\s*([A-C][1-2]|F0)?\s*', '', span_text).strip()
                if clean_def:
                    current_meaning = {"definition": clean_def, "examples": []}
                    pos_block["meanings"].append(current_meaning)
            
            elif span_text.startswith('»') and current_meaning and not is_extra_section:
                clean_ex = span_text.replace('»', '').strip()
                if clean_ex:
                    current_meaning["examples"].append(clean_ex)

        # 4. Extract Idioms (Dark Brown text)
        for font in soup.find_all('font'):
            style = font.get('style', '')
            if '#662C00' in style:
                pos_block["idioms"].append(font.get_text(strip=True))

        result.append(pos_block)
        return result

    # ==========================================
    # 1. CORE LEXICAL & PHONETIC
    # ==========================================
    def _get_headwords(self, soup):
        # CALD4 usually puts the headword in a large font: <font size="+1">
        results = [f.get_text(strip=True) for f in soup.find_all('font', size="+1")]
        return list(set([r for r in results if r]))

    def _get_homograph_index(self, soup):
        # CALD4 uses Crimson Roman Numerals for homographs: <font color="crimson"><b>Ⅰ</b></font>
        results = []
        for f in soup.find_all('font', color='crimson'):
            text = f.get_text(strip=True)
            # Match roman numerals like Ⅰ, Ⅱ, Ⅲ, Ⅳ, Ⅴ
            if re.match(r'^[Ⅰ-Ⅻ]+$', text): 
                results.append(f"Entry {text}")
        return results

    def _get_syllabification(self, soup):
        return [] # Not explicitly marked outside of IPA

    def _get_pos(self, soup):
        # CALD4 uses a specific inline style block for Parts of Speech
        results = []
        for span in soup.find_all('span'):
            style = span.get('style', '')
            if 'background-color: #3F7373' in style or 'background-color:#3F7373' in style.replace(' ', ''):
                results.append(span.get_text(strip=True).lower())
        return list(set(results))

    def _get_ipa(self, soup):
        # IPA is usually floating in the text nodes near the top, wrapped in / /
        results = {"UK": [], "US": []}
        text = soup.get_text(separator=' ')
        ipas = re.findall(r'/([^/]+)/', text)
        
        # CALD4 often lists UK first, then US after "aep" (American English Pronunciation)
        if len(ipas) >= 1: results["UK"].append(ipas[0].strip())
        if len(ipas) >= 2: results["US"].append(ipas[1].strip())
        return results

    def _get_audio_links(self, soup):
        results = {"UK": [], "US": []}
        for a in soup.find_all('a', href=re.compile(r'^sound://')):
            href = a.get('href').replace('sound://', '')
            img = a.find('img')
            if img:
                src = img.get('src', '').lower()
                if 'snd_uk' in src and href not in results["UK"]: results["UK"].append(href)
                elif 'snd_us' in src and href not in results["US"]: results["US"].append(href)
        return results

    # ==========================================
    # 2. DEFINITION & SENSE HIERARCHY
    # ==========================================
    def _get_signposts(self, soup):
        # Meaning groupings in CALD4 are Magenta/MediumVioletRed and capitalized: <font color="mediumvioletred"><b>(LEAVE)</b></font>
        results = []
        for f in soup.find_all('font', color='mediumvioletred'):
            text = f.get_text(strip=True).strip('()')
            if text: results.append(text)
        return list(set(results))

    def _get_definitions(self, soup):
        # Definitions immediately follow a '►' symbol.
        results = []
        for span in soup.find_all('span'):
            text = span.get_text(separator=' ', strip=True)
            if '►' in text:
                # Strip out the pointer and any CEFR tags (like B2, F0)
                clean_def = re.sub(r'►\s*([A-C][1-2]|F0)?\s*', '', text).strip()
                if clean_def: results.append(clean_def)
        return results

    def _get_phrases_idioms(self, soup):
        # Idioms are usually bold and dark brown: <font style="color:#662C00;...">
        results = []
        for font in soup.find_all('font'):
            style = font.get('style', '')
            if '#662C00' in style:
                results.append(font.get_text(strip=True))
        return results

    def _get_phrasal_verbs(self, soup):
        # Usually mixed into the idioms formatting in CALD4
        return []

    # ==========================================
    # 3. EXAMPLES & CONTEXT
    # ==========================================
    def _get_examples(self, soup):
        standard_ex = []
        is_extra_section = False
        
        for span in soup.find_all('span'):
            text = span.get_text(separator=' ', strip=True)
            
            # Detect section shifts
            if 'Extra Examples' in text:
                is_extra_section = True
                continue
            if 'Word partners' in text or 'Collocations' in text or 'Word Builder' in text:
                is_extra_section = False
                
            # Examples start with »
            if text.startswith('»'):
                clean = text.replace('»', '').strip()
                if not is_extra_section and clean:
                    standard_ex.append(clean)
                    
        return standard_ex

    def _get_extra_examples(self, soup):
        extra_ex = []
        is_extra_section = False
        
        for span in soup.find_all('span'):
            text = span.get_text(separator=' ', strip=True)
            
            if 'Extra Examples' in text:
                is_extra_section = True
                continue
            if 'Word partners' in text or 'Collocations' in text or 'Word Builder' in text:
                is_extra_section = False
                
            if text.startswith('»') and is_extra_section:
                extra_ex.append(text.replace('»', '').strip())
                
        return extra_ex

    def _get_inline_glosses(self, soup):
        # CALD4 uses Lime Green for inline glosses: <font color="limegreen">(= faster than before)</font>
        return [f.get_text(strip=True).strip('(=)') for f in soup.find_all('font', color='limegreen')]

    def _get_images(self, soup):
        # Exclude UI icons like 'snd_uk.png' or thumbnail buttons 'txbmouse.jpg'
        results = []
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src and not src.startswith('snd_') and not src.startswith('txb'):
                results.append(src)
        return list(set(results))

    # ==========================================
    # 4. GRAMMAR & SYNTAX
    # ==========================================
    def _get_grammar_codes(self, soup):
        # e.g., <font color="green">[T]</font> or <font color="green">[U]</font>
        results = []
        for font in soup.find_all('font', color='green'):
            text = font.get_text(strip=True)
            if text.startswith('[') and text.endswith(']'):
                results.append(text)
        return list(set(results))

    def _get_inflections(self, soup):
        # Midnight Blue is used for inflected forms like past tense or plurals: <font color="midnightblue"><b>tore</b></font>
        return [f.get_text(strip=True) for f in soup.find_all('font', color='midnightblue')]

    def _get_verb_tables(self, soup):
        return [] # CALD4 doesn't use conjugation grids

    # ==========================================
    # 5. SEMANTIC LINKS
    # ==========================================
    def _get_synonyms(self, soup):
        # FIX: CALD4's "synonyms" are actually SMART Thesaurus Categories (e.g. "Diets and dieting").
        # We return an empty list to prevent polluting the SRS database with full sentences.
        return []

    def _get_antonyms(self, soup):
        # CALD4 uses explicit bold "Opposite" tags, but they are rare.
        results = []
        for b in soup.find_all('b'):
            if b.get_text(strip=True).lower() == 'opposite':
                parent = b.find_parent()
                if parent:
                    urls = parent.find_all('span', class_='url')
                    for u in urls:
                        results.append(u.get_text(strip=True))
        return list(set(results))

    def _get_collocations(self, soup):
        # Collocations have a green sharp/hash <font color="green"><b>♯</b></font> or 'lu.'
        results = []
        for marker in soup.find_all('font', color='green'):
            text = marker.get_text(strip=True)
            if '♯' in text or 'lu.' in text:
                parent = marker.find_parent('span')
                if parent:
                    # Clean the bullet points and markers
                    clean = parent.get_text(separator='', strip=True).replace('lu.', '').replace('♯', '').strip(' -•')
                    if clean: results.append(clean)
        return results

    def _get_derivatives(self, soup):
        # Found in the Word Builder section, usually Navy Blue: <font color="navy"><b>record</b></font>
        return [f.get_text(strip=True) for f in soup.find_all('font', color='navy')]

    def _get_cross_references(self, soup):
        results = []
        # Looks for SEE ALSO, COMPARE links
        for a in soup.find_all('a', href=re.compile(r'^entry://')):
            # Ignore the thesaurus ones
            if not a.get('href').startswith('entry://↑'):
                parent = a.find_parent('span')
                if parent and ('SEE ALSO' in parent.get_text() or 'COMPARE' in parent.get_text() or 'see also' in parent.get_text()):
                    results.append(a.get_text(strip=True))
        return list(set(results))

    # ==========================================
    # 6. META-DATA & USAGE
    # ==========================================
    def _get_style_labels(self, soup):
        # CALD4 uses Indigo for register: <font color="indigo">LITERARY</font>
        return [f.get_text(strip=True) for f in soup.find_all('font', color='indigo')]

    def _get_topic_labels(self, soup):
        # Dark Violet for dialect/topic: <font color="darkviolet">SOUTH AFRICAN ENGLISH</font>
        return [f.get_text(strip=True) for f in soup.find_all('font', color='darkviolet')]

    def _get_frequency_tags(self, soup):
        return [] # Reflected purely by CEFR levels in CALD4

    def _get_cefr_levels(self, soup):
        # CALD4 tags levels in green, e.g., <font color="green"><b>B2</b></font>
        levels = []
        for font in soup.find_all('font', color='green'):
            text = font.get_text(strip=True)
            if re.match(r'^(A1|A2|B1|B2|C1|C2|F0)$', text):
                if text not in levels: levels.append(text)
        return levels

    def _get_etymology(self, soup):
        return None