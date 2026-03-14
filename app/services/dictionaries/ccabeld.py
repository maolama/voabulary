from .base import BaseDictionary
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

class CCABELDDictionary(BaseDictionary):
    """
    Specialized Extractor for Collins COBUILD Advanced Learner's Dictionary.
    Famous for full-sentence definitions and unique HTML-based phonetic stress (underlines).
    """

    def __init__(self, db_path, name, color):
        super().__init__(db_path, name, color)
        self.display_name = "Collins COBUILD Advanced"

    def finalize_html(self, soup, word, word_id=None, pinned_ids=None):
        # 1. Inject global CSS
        global_style = soup.new_tag("link", attrs={"rel": "stylesheet", "type": "text/css", "href": "/static/css/global_dict.css"})
        soup.insert(0, global_style)

        # 2. Inject TTS Buttons
        # CCABELD puts examples inside <q> tags with a leading " ⇒ "
        for q in soup.find_all('q'):
            text = q.get_text(strip=True)
            if '⇒' in text:
                clean_sentence = text.replace('⇒', '').strip()
                clean_sentence = clean_sentence.replace("'", "\\'").replace('"', '&quot;')

                speaker_btn = soup.new_tag("button", attrs={
                    "class": "ccabeld-custom-tts ml-1", 
                    "onclick": f"if(window.parent.playTTSAudio) {{ window.parent.playTTSAudio('{clean_sentence}'); }} else {{ window.playTTSAudio('{clean_sentence}'); }}",
                    "type": "button"
                })
                svg_html = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="pointer-events: none;"><path d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>'
                speaker_btn.append(BeautifulSoup(svg_html, 'html.parser'))
                q.append(speaker_btn)

        return str(soup)

    # ==========================================
    # 1. CORE LEXICAL & PHONETIC
    # ==========================================
    def _get_headwords(self, soup):
        results = []
        # CCABELD uses <h1 class="orth"> or <h2 class="orth">
        for header in soup.find_all(['h1', 'h2'], class_='orth'):
            # Clone to avoid destroying the original HTML
            h_clone = BeautifulSoup(str(header), 'html.parser').find(['h1', 'h2'])
            # Remove the frequency dots and homograph numbers
            for span in h_clone.find_all('span'): span.decompose()
            for sup in h_clone.find_all('sup'): sup.decompose()
            results.append(h_clone.get_text(strip=True))
        return list(set([r for r in results if r]))

    def _get_homograph_index(self, soup):
        # E.g. "tear (crying)" vs "tear (damaging)"
        results = []
        for hom in soup.find_all('span', class_='lbl misc'):
            text = hom.get_text(strip=True).strip('()')
            results.append(f"Context: {text}")
        return results

    def _get_syllabification(self, soup):
        return []

    def _get_pos(self, soup):
        # E.g. "1. countable noun" -> strip the numbers
        results = []
        for pos in soup.find_all('span', class_='pos'):
            text = pos.get_text(strip=True)
            text = re.sub(r'^\d+\.\s*', '', text) # Remove leading numbers like "1. "
            if text: results.append(text)
        return list(set(results))

    def _get_ipa(self, soup):
        # IMPORTANT: CCABELD uses <span class="underline"> to indicate stress!
        # We must convert <u>æ</u> to ˈæ
        results = {"UK": [], "US": []}
        
        for pron in soup.find_all('span', class_='pron'):
            pron_clone = BeautifulSoup(str(pron), 'html.parser').find('span', class_='pron')
            
            # Translate underlined vowels into standard IPA stress marks
            for u in pron_clone.find_all('span', class_='underline'):
                u.replace_with(f"ˈ{u.get_text()}")
                
            # Check for US label
            geo = pron_clone.find('span', class_='geo')
            is_us = geo and 'US' in geo.get_text()
            
            # Clean up the output
            if geo: geo.decompose()
            for audio in pron_clone.find_all('a'): audio.decompose()
            
            ipa = pron_clone.get_text(strip=True).strip('() /;')
            if not ipa: continue
            
            if is_us:
                if ipa not in results["US"]: results["US"].append(ipa)
            else:
                if ipa not in results["UK"]: results["UK"].append(ipa)
                
        return results

    def _get_audio_links(self, soup):
        # CCABELD has amazing audio coverage, down to the inflections!
        results = {"UK": [], "US": []}
        for a in soup.find_all('a', class_='audio_play_button'):
            href = a.get('href', '').replace('sound://', '')
            if not href: continue
            if 'us/' in href.lower() or 'ame/' in href.lower():
                results["US"].append(href)
            else:
                results["UK"].append(href)
        return {"UK": list(set(results["UK"])), "US": list(set(results["US"]))}

    # ==========================================
    # 2. DEFINITION & SENSE HIERARCHY
    # ==========================================
    def _get_signposts(self, soup):
        return [] # Usually handled via homograph context in CCABELD

    def _get_definitions(self, soup):
        # The famous COBUILD full-sentence definitions
        results = []
        for d in soup.find_all('span', class_='def'):
            text = d.get_text(separator=' ', strip=True)
            if text: results.append(text)
        return results

    def _get_phrases_idioms(self, soup):
        results = []
        # Usually found under a "See [Phrase]" cross-reference block
        for re_block in soup.find_all('div', class_='re'):
            for a in re_block.find_all('a'):
                results.append(a.get_text(strip=True))
        return list(set(results))

    def _get_phrasal_verbs(self, soup):
        return [] # Merged with phrases in CCABELD

    # ==========================================
    # 3. EXAMPLES & CONTEXT
    # ==========================================
    def _get_examples(self, soup):
        results = []
        for q in soup.find_all('q'):
            text = q.get_text(strip=True).replace('⇒', '').strip()
            if text: results.append(text)
        return results

    def _get_extra_examples(self, soup):
        return []

    def _get_inline_glosses(self, soup):
        return []

    def _get_images(self, soup):
        return []

    # ==========================================
    # 4. GRAMMAR & SYNTAX
    # ==========================================
    def _get_grammar_codes(self, soup):
        # Beautifully formatted syntax codes like [V n] or [+ of]
        results = []
        for syntax in soup.find_all('span', class_='syntax'):
            results.append(syntax.get_text(strip=True))
        return list(set(results))

    def _get_inflections(self, soup):
        results = []
        for infl in soup.find_all('span', class_='infl'):
            text = infl.get_text(strip=True).strip(',')
            if text: results.append(text)
        return list(set(results))

    def _get_verb_tables(self, soup):
        return []

    # ==========================================
    # 5. SEMANTIC LINKS
    # ==========================================
    def _get_synonyms(self, soup):
        return [] # Synonyms are fairly rare in CCABELD's core HTML structure

    def _get_antonyms(self, soup):
        return []

    def _get_collocations(self, soup):
        return []

    def _get_derivatives(self, soup):
        results = []
        # Marked as <span class="drv">, e.g., -bearing, heaviness
        for drv in soup.find_all('span', class_='drv'):
            results.append(drv.get_text(strip=True))
        return list(set(results))

    def _get_cross_references(self, soup):
        results = []
        for xr in soup.find_all('span', class_='xr_ref'):
            results.append(xr.get_text(strip=True))
        return list(set(results))

    # ==========================================
    # 6. META-DATA & USAGE
    # ==========================================
    def _get_style_labels(self, soup):
        # E.g., disapproval, literary, formal
        labels = []
        for lbl in soup.find_all('span', class_=['pragmatics', 'register', 'geo']):
            labels.append(lbl.get_text(strip=True))
        return list(set(labels))

    def _get_topic_labels(self, soup):
        # E.g., business, technical
        return [lbl.get_text(strip=True) for lbl in soup.find_all('span', class_='subj')]

    def _get_frequency_tags(self, soup):
        tags = []
        # 1. Visual Band (●●○)
        h1 = soup.find('h1', class_='orth')
        if h1:
            circles = h1.find('span')
            if circles and '●' in circles.get_text():
                tags.append(circles.get_text(strip=True))
                
        # 2. Textual Commonness Description
        commonness_div = soup.find('div', class_='commonness')
        if commonness_div:
            img_div = commonness_div.find('div', attrs={'data-band': True})
            if img_div:
                title = img_div.get('title', '')
                # Extract just the first summary sentence (e.g. "Very Common.")
                if title: tags.append(title.split('.')[0] + ".")
                
        return tags

    def _get_cefr_levels(self, soup):
        return []

    def _get_etymology(self, soup):
        return None