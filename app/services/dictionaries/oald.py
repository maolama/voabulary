from .base import BaseDictionary
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

class OALD9Dictionary(BaseDictionary):
    """Specialized Oxford 9 Handler & Extractor."""

    def __init__(self, db_path, name, color):
        super().__init__(db_path, name, color)
        self.display_name = 'Oxford Advanced Learners 9'

    def finalize_html(self, soup, word, word_id=None, pinned_ids=None):
        if pinned_ids is None:
            pinned_ids = []
            
        global_style = soup.new_tag("link", attrs={"rel": "stylesheet", "type": "text/css", "href": "/static/css/global_dict.css"})
        soup.insert(0, global_style)

        # TTS Button Logic (Existing)
        for ex in soup.find_all('span', class_='x'):
            sentence_text = ex.get_text(strip=True)
            if not sentence_text: continue
            clean_sentence = sentence_text.replace('~', word).replace("'", "\\'").replace('"', '&quot;')

            speaker_btn = soup.new_tag("button", attrs={
                "class": "oald-custom-tts ml-1", 
                "onclick": f"if(window.parent.playTTSAudio) {{ window.parent.playTTSAudio('{clean_sentence}'); }} else {{ window.playTTSAudio('{clean_sentence}'); }}",
                "type": "button"
            })
            svg_html = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="pointer-events: none;"><path d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>'
            speaker_btn.append(BeautifulSoup(svg_html, 'html.parser'))
            ex.append(speaker_btn)

        # --- HIERARCHICAL MARKING LOGIC ---
        entries = soup.find_all('div', class_='entry')
        
        for entry_idx, entry in enumerate(entries):
            pos_tag = entry.find('span', class_='pos')
            pos_label = pos_tag.get_text(strip=True).lower() if pos_tag else f"entry{entry_idx}"
            senses = entry.find_all('li', class_='sn-g')
            
            for sense_idx, sn in enumerate(senses):
                unique_sense_id = f"oald-{pos_label}-{sense_idx + 1}"
                sn['id'] = unique_sense_id
                
                # --- NEW: Initial state check ---
                is_pinned = unique_sense_id in pinned_ids
                btn_text = "✅ Pinned" if is_pinned else "📌 Mark"
                btn_bg = "#bbf7d0" if is_pinned else "#e0e7ff"
                btn_color = "#166534" if is_pinned else "#4338ca"
                
                mark_btn = soup.new_tag("button", attrs={
                    "class": "mark-sense-btn",
                    "style": f"float: right; font-size: 11px; padding: 2px 6px; background: {btn_bg}; color: {btn_color}; border-radius: 4px; border: none; cursor: pointer; margin-left: 8px;",
                    "onclick": f"if(window.parent.saveSense) window.parent.saveSense({word_id or 'null'}, '{self.name}', this.parentElement.outerHTML, this, '{unique_sense_id}')"
                })
                mark_btn.string = btn_text
                sn.insert(0, mark_btn)
        
        return str(soup)

    # ==========================================
    # SEMANTIC HIERARCHICAL EXTRACTOR
    # ==========================================
    def extract_features(self, html):
        """Extracts features in a strict hierarchical format: POS -> Senses -> Defs/Ex."""
        result = []
        if not html: return result
            
        soup = BeautifulSoup(html, 'html.parser')

        entries = soup.find_all('div', class_='entry')
        for entry in entries:
            # 1. Get POS
            pos_tag = entry.find('span', class_='pos')
            pos = pos_tag.get_text(strip=True).lower() if pos_tag else "unknown"
            
            # 2. Get Phonetics for this specific entry
            uk_prons = [p.get_text(strip=True).replace('/', '').strip() for p in entry.select('.phons_br .phon')]
            us_prons = [p.get_text(strip=True).replace('/', '').strip() for p in entry.select('.phons_n_am .phon')]
            
            pos_block = {
                "partOfSpeech": pos,
                "ukPronunciation": f"/{uk_prons[0]}/" if uk_prons else "",
                "usPronunciation": f"/{us_prons[0]}/" if us_prons else "",
                "meanings": [],
                "idioms": []
            }

            # 3. Extract Senses (Meanings)
            senses = entry.find_all('li', class_='sn-g')
            for sn in senses:
                # Prevent extracting idioms masquerading as standard definitions
                if sn.find_parent('span', class_='idm-gs'): continue
                
                def_tag = sn.find('span', class_='def')
                definition = def_tag.get_text(strip=True) if def_tag else ""
                
                # Get examples tied to THIS specific meaning
                examples = []
                for x in sn.find_all('span', class_='x'):
                    if not x.find_parent('span', attrs={'otitle': 'Extra examples'}):
                        examples.append(x.get_text(strip=True))
                
                if definition:
                    pos_block["meanings"].append({
                        "definition": definition,
                        "examples": examples
                    })

            # 4. Extract Idioms tied to this POS
            idioms = entry.find_all('span', class_='idm')
            for idm in idioms:
                pos_block["idioms"].append(idm.get_text(strip=True))

            result.append(pos_block)
            
        return result

    # ==========================================
    # 1. CORE LEXICAL & PHONETIC
    # ==========================================
    def _get_headwords(self, soup):
        # We strip out the <span class="hm"> (homograph number) so 'tear1' becomes 'tear'
        results = []
        for h2 in soup.find_all('h2', class_='h'):
            text = h2.find(text=True, recursive=False)
            if text: results.append(text.strip())
        return list(set(results))

    def _get_homograph_index(self, soup):
        return [hm.get_text(strip=True) for hm in soup.find_all('span', class_='hm')]

    def _get_syllabification(self, soup):
        return [] # OALD9 doesn't explicitly mark syllables

    def _get_pos(self, soup):
        return list(set([pos.get_text(strip=True) for pos in soup.find_all('span', class_='pos')]))

    def _get_ipa(self, soup):
        results = {"UK": [], "US": []}
        for pron in soup.find_all('span', class_='pron-g'):
            geo = pron.get('geo')
            phon = pron.find('span', class_='phon')
            if phon:
                ipa = phon.get_text(strip=True).replace('BrE', '').replace('NAmE', '').replace('/', '').strip()
                if geo == 'br' and ipa not in results["UK"]: results["UK"].append(ipa)
                if geo == 'n_am' and ipa not in results["US"]: results["US"].append(ipa)
        return results

    def _get_audio_links(self, soup):
        results = {"UK": [], "US": []}
        for a in soup.find_all('a', class_='sound'):
            href = a.get('href', '').replace('sound://', '')
            if not href: continue
            if 'pron-uk' in a.get('class', []) and href not in results["UK"]: results["UK"].append(href)
            if 'pron-us' in a.get('class', []) and href not in results["US"]: results["US"].append(href)
        return results

    # ==========================================
    # 2. DEFINITION & SENSE HIERARCHY
    # ==========================================
    def _get_signposts(self, soup):
        # OALD9 uses <span class="shcut"> (Shortcut) for signposts, e.g. "written account"
        return [sc.get_text(strip=True) for sc in soup.find_all('span', class_='shcut')]

    def _get_definitions(self, soup):
        results = []
        for d in soup.find_all('span', class_='def'):
            # CRITICAL: Prevent extracting definitions that belong to idioms or synonyms!
            if d.find_parent('span', class_='idm-gs') or d.find_parent('span', attrs={'otitle': 'Synonyms'}):
                continue
            results.append(d.get_text(strip=True))
        return results

    def _get_phrases_idioms(self, soup):
        return [idm.get_text(strip=True) for idm in soup.find_all('span', class_='idm')]

    def _get_phrasal_verbs(self, soup):
        # E.g. "tear apart"
        results = []
        for pv_box in soup.find_all('span', class_='pv-gs'):
            for xw in pv_box.find_all('span', class_='xw'):
                results.append(xw.get_text(separator=' ', strip=True))
        return results

    # ==========================================
    # 3. EXAMPLES & CONTEXT
    # ==========================================
    def _get_examples(self, soup):
        results = []
        for x in soup.find_all('span', class_='x'):
            # Filter out Extra Examples, Idiom Examples, and Synonym Examples
            if x.find_parent('span', attrs={'otitle': 'Extra examples'}) or \
               x.find_parent('span', class_='idm-gs') or \
               x.find_parent('span', attrs={'otitle': 'Synonyms'}):
                continue
            results.append(x.get_text(strip=True))
        return results

    def _get_extra_examples(self, soup):
        results = []
        extra_box = soup.find('span', attrs={'otitle': 'Extra examples'})
        if extra_box:
            results = [x.get_text(strip=True) for x in extra_box.find_all('span', class_='x')]
        return results

    def _get_inline_glosses(self, soup):
        # Captures inline explanations like (= to leave the ship)
        return [gl.get_text(strip=True) for gl in soup.find_all('span', class_='gl')]

    def _get_images(self, soup):
        results = []
        for img in soup.find_all('img'):
            src = img.get('src')
            # OALD9 uses tracking images sometimes, so we ensure it's a real media image
            if src and '/media/' in src and src not in results:
                results.append(src)
        return results

    # ==========================================
    # 4. GRAMMAR & SYNTAX
    # ==========================================
    def _get_grammar_codes(self, soup):
        # Gets [uncountable], [transitive], etc.
        codes = [g.get_text(strip=True).strip('[]') for g in soup.find_all('span', class_='gram')]
        # Gets sentence constructions like "bear somebody something"
        constructs = [cf.get_text(separator=' ', strip=True) for cf in soup.find_all('span', class_='cf')]
        return list(set(codes + constructs))

    def _get_inflections(self, soup):
        results = []
        # 1. Grab standard Verb Forms
        vp_box = soup.find('span', attrs={'otitle': 'Verb Forms'})
        if vp_box:
            for vp in vp_box.find_all('span', class_='vp'):
                full = vp.get_text(separator=' ', strip=True)
                prefix = vp.find('span', class_='prefix')
                if prefix:
                    full = full.replace(prefix.get_text(strip=True), '').strip()
                if full: results.append(full)
        
        # 2. Grab Noun plurals and Adjective comparatives (like mice, heavier)
        for inf in soup.find_all('span', class_='if'):
            results.append(inf.get_text(strip=True))
            
        return list(set(results))

    def _get_verb_tables(self, soup):
        return [] # OALD9 doesn't use Longman-style conjugation tables

    # ==========================================
    # 5. SEMANTIC LINKS
    # ==========================================
    def _get_synonyms(self, soup):
        results = []
        
        # 1. Inline Synonyms
        for syn_block in soup.find_all('span', class_='xr-gs'):
            pref = syn_block.find('span', class_='prefix')
            if pref and 'synonym' in pref.get_text().lower():
                xh = syn_block.find('span', class_='xh')
                if xh: results.append(xh.get_text(strip=True))
                
        # 2. Synonym Popups (OALD stores them inside an 'inline' span)
        for box in soup.find_all('span', attrs={'otitle': 'Synonyms'}):
            inline_block = box.find('span', class_='inline')
            if inline_block:
                for li in inline_block.find_all(['span', 'li'], class_='li'):
                    results.append(li.get_text(strip=True))

        # 3. Wordfinder Popups
        for box in soup.find_all('span', attrs={'otitle': 'Wordfinder'}):
            for xh in box.find_all('span', class_='xh'):
                results.append(xh.get_text(strip=True))
                
        return list(set(results))

    def _get_antonyms(self, soup):
        results = []
        for opp_block in soup.find_all('span', class_='xr-gs'):
            pref = opp_block.find('span', class_='prefix')
            if pref and 'opposite' in pref.get_text().lower():
                xh = opp_block.find('span', class_='xh')
                if xh: results.append(xh.get_text(strip=True))
        return list(set(results))

    def _get_collocations(self, soup):
        results = []
        collo_box = soup.find('span', attrs={'otitle': 'Collocations'})
        if collo_box:
            for item in collo_box.find_all('span', class_='li'):
                results.append(item.get_text(separator=' ', strip=True))
        return results

    def _get_derivatives(self, soup):
        return [] # Run-ons are mostly absent in OALD9 entries

    def _get_cross_references(self, soup):
        results = []
        for ref in soup.find_all('span', class_='xr-gs'):
            pref = ref.find('span', class_='prefix')
            if pref and 'see also' in pref.get_text().lower():
                link = ref.find('a', class_='Ref')
                if link: results.append(link.get_text(strip=True))
        return results

    # ==========================================
    # 6. META-DATA & USAGE
    # ==========================================
    def _get_style_labels(self, soup):
        # Includes things like (formal), (informal), (figurative)
        labels = [lbl.get_text(strip=True).strip('()') for lbl in soup.find_all('span', class_='reg')]
        geo = [g.get_text(strip=True).strip('()') for g in soup.find_all('span', class_='geo')]
        return list(set(labels + geo))

    def _get_topic_labels(self, soup):
        # E.g. "physics", "computing"
        topics = [subj.get_text(strip=True) for subj in soup.find_all('span', class_='subj')]
        return topics

    def _get_frequency_tags(self, soup):
        tags = []
        if soup.find('a', class_='oxford3000'): tags.append("Oxford 3000")
        if soup.find('a', class_='academic'): tags.append("AWL")
        return tags

    def _get_cefr_levels(self, soup):
        return [] # OALD9 doesn't explicitly tag CEFR in this HTML dump

    def _get_etymology(self, soup):
        origin_box = soup.find('span', attrs={'otitle': 'Word Origin'})
        if origin_box:
            body = origin_box.find('span', class_='body')
            if body:
                return body.get_text(separator=' ', strip=True)
        return None