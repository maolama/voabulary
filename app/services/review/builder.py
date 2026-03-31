import random
import re
import sqlite3
import logging
from bs4 import BeautifulSoup
from ...models import SavedWord, SavedSense
from ...extensions import db
from app import dict_service 

logger = logging.getLogger(__name__)

class QuestionBuilder:
    """Constructs the specific JSON payload needed for the frontend UI based on the mode."""
    
    # NEW: We restrict Dojo scraping entirely to these three ultra-high-quality dictionaries
    DOJO_DICTS = ['cald4', 'oald9', 'longman']

    @staticmethod
    def _get_active_dojo_dicts():
        """Returns the whitelist dictionaries that are actually enabled. Failsafes if all are disabled."""
        active = []
        for dict_name, handler in dict_service.active_dictionaries.items():
            if getattr(handler, 'enabled', True) and any(d.lower() in dict_name.lower() for d in QuestionBuilder.DOJO_DICTS):
                active.append(dict_name)
        
        if not active:
            logger.warning("[!] All Top 3 Dojo dictionaries are disabled! Falling back to the failsafe whitelist.")
            return QuestionBuilder.DOJO_DICTS
        return active

    @staticmethod
    def build_payload(word_obj: SavedWord, mode: str, encounter_index: int = 0) -> dict:
        logger.info(f"[*] Building payload for '{word_obj.word}' [Mode: {mode}] [Encounter: {encounter_index}]")
        
        active_dicts = QuestionBuilder._get_active_dojo_dicts()
        audio_data = dict_service.get_native_audio(word_obj.word, allowed_dicts=active_dicts)
        
        # NEW: Route definition requests through our smart Priority/Pinned logic
        raw_target_def = QuestionBuilder._get_best_definition(word_obj.word, word_obj.id, encounter_index)
        masked_target_def = QuestionBuilder._mask_text(raw_target_def, word_obj.word)
        
        payload = {
            'word_id': word_obj.id,
            'target_word': word_obj.word,
            'target_answer': word_obj.word, 
            'mode': mode,
            'native_uk': audio_data.get('UK'), 
            'native_us': audio_data.get('US'), 
            'tts_url': f'/api/tts/{word_obj.word}' 
        }

        # ==========================================
        # PHASE 1 MODES (RECOGNITION)
        # ==========================================
        
        if mode in ['word_to_def', 'audio_to_def']:
            distractors = QuestionBuilder._get_smart_distractors(word_obj.word, 3)
            options = [d['masked_def'] for d in distractors] + [masked_target_def]
            random.shuffle(options)
            
            payload['options'] = options
            payload['target_answer'] = masked_target_def
            payload['display_text'] = word_obj.word if mode == 'word_to_def' else "🔊 Listen to the audio..."

        elif mode == 'def_to_word':
            distractors = QuestionBuilder._get_smart_distractors(word_obj.word, 3)
            options = [d['word'] for d in distractors] + [word_obj.word]
            random.shuffle(options)
            
            payload['options'] = options
            payload['context_html'] = f'<div class="text-xl font-bold text-slate-700 italic text-center">"{masked_target_def}"</div>'

        elif mode == 'true_false_sort':
            is_true = random.choice([True, False])
            if is_true:
                shown_def = masked_target_def
            else:
                distractors = QuestionBuilder._get_smart_distractors(word_obj.word, 1)
                shown_def = distractors[0]['masked_def']

            payload['display_text'] = word_obj.word
            payload['context_html'] = f'<div class="text-xl italic text-slate-600 text-center">"{shown_def}"</div>'
            payload['options'] = ['TRUE', 'FALSE']
            payload['target_answer'] = 'TRUE' if is_true else 'FALSE'

        elif mode == 'collocation_match':
            collocations = QuestionBuilder._get_collocations(word_obj.word)
            
            if not collocations:
                logger.info(f"[!] No collocations found for '{word_obj.word}'. Falling back to word_to_def.")
                payload['mode'] = 'word_to_def'
                return QuestionBuilder.build_payload(word_obj, 'word_to_def', encounter_index)
                
            raw_collocation = random.choice(collocations)
            masked_phrase = QuestionBuilder._mask_text(raw_collocation, word_obj.word)
            
            distractors = QuestionBuilder._get_smart_distractors(word_obj.word, 3)
            options = [d['word'] for d in distractors] + [word_obj.word]
            random.shuffle(options)
            
            payload['display_text'] = f"... {masked_phrase}"
            payload['options'] = options
            payload['target_answer'] = word_obj.word

        # ==========================================
        # PHASE 2 & 3 MODES (RECALL & TYPING)
        # ==========================================

        elif mode == 'vowel_void':
            vowels = "aeiouAEIOU"
            payload['display_text'] = "".join(['_' if char in vowels else char for char in word_obj.word])

        elif mode == 'typo_trap':
            options = QuestionBuilder._generate_typos(word_obj.word)
            options.append(word_obj.word)
            random.shuffle(options)
            payload['options'] = options

        elif mode in ['cloze_hybrid', 'verb_conjugation', 'proofreader']:
            best_ex = QuestionBuilder._get_best_example(word_obj.word, word_obj.id, encounter_index)
            if best_ex:
                raw_html = f'<span class="text-lg text-slate-700 leading-relaxed">{best_ex}</span>'
            else:
                raw_html = "No context found. Define the word:"
                
            payload['context_html'] = QuestionBuilder._mask_word_in_html(raw_html, word_obj.word, mode)
            
            if mode == 'cloze_hybrid':
                distractors = QuestionBuilder._get_smart_distractors(word_obj.word, 3)
                options = [d['word'] for d in distractors] + [word_obj.word]
                random.shuffle(options)
                payload['options'] = options

        return payload

    # ==========================================
    # HELPERS & SCRAPERS
    # ==========================================

    @staticmethod
    def _get_best_definition(word: str, word_id: int, encounter_index: int) -> str:
        """
        PRIORITY 1: Uses explicit user-pinned definitions.
        PRIORITY 2: Falls back to Weighted Smart Selection from dictionaries.
        """
        pinned_senses = SavedSense.query.filter_by(word_id=word_id).all()
        
        if pinned_senses:
            logger.debug(f"[+] Found {len(pinned_senses)} pinned senses for '{word}'. Using Pin Priority.")
            pinned_defs = []
            for sense in pinned_senses:
                if sense.html_content:
                    soup = BeautifulSoup(sense.html_content, 'html.parser')
                    # Find the text: OALD9 usually uses 'def', CALD4 'definition', etc.
                    def_tag = soup.find('span', class_='def') or soup.find(class_='definition') or soup.find(class_='def_text')
                    if def_tag:
                        pinned_defs.append(def_tag.get_text(strip=True))
                    else:
                        # Fallback: Scrape the raw text if tags miss
                        pinned_defs.append(soup.get_text(separator=' ', strip=True))
            
            if pinned_defs:
                # Cycle safely through the available pins
                clean_text = pinned_defs[encounter_index % len(pinned_defs)]
                logger.info(f"[+] [DEF PINNED] Selected user-pinned definition: {clean_text[:50]}...")
                return clean_text
        
        logger.debug(f"[*] No pins found for '{word}'. Delegating to dictionary weighting.")
        return dict_service.get_short_definition(word, allowed_dicts=QuestionBuilder._get_active_dojo_dicts())

    @staticmethod
    def _mask_text(text: str, word: str) -> str:
        if not text or text == "No short definition available.": 
            return text
        pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
        return pattern.sub('______', text)

    @staticmethod
    def _get_smart_distractors(target_word: str, count: int = 3) -> list:
        # 1. BUILD THE SEMANTIC FIREWALL (BANLIST)
        banned_words = set([target_word.lower()])
        
        # Add auto-extracted synonyms
        auto_rels = dict_service.get_word_relations(target_word)
        banned_words.update(auto_rels['synonyms'])
        
        # Add manually pinned synonyms
        target_obj = SavedWord.query.filter_by(word=target_word).first()
        if target_obj:
            for s in target_obj.manual_synonyms:
                banned_words.add(s.synonym.lower())

        # 2. SELECT DISTRACTORS
        all_words = SavedWord.query.all()
        random.shuffle(all_words)
        
        valid_distractors = []
        target_prefix = target_word[:4].lower() 
        
        for w in all_words:
            if len(valid_distractors) >= count: break
            
            # THE FIREWALL: Skip if it's the target word, a known synonym, or shares a prefix
            if w.word.lower() in banned_words or target_prefix in w.word.lower():
                continue
                
            w_def = dict_service.get_short_definition(w.word, allowed_dicts=QuestionBuilder._get_active_dojo_dicts())
            if w_def and w_def != "No short definition available.":
                if target_prefix not in w_def.lower(): 
                    valid_distractors.append({
                        'word': w.word, 
                        'masked_def': QuestionBuilder._mask_text(w_def, w.word)
                    })
                
        failsafe_counter = 1
        while len(valid_distractors) < count:
            valid_distractors.append({
                'word': f"random_word_{random.randint(10,99)}_{failsafe_counter}", 
                'masked_def': f"A concept entirely unrelated to the current context ({failsafe_counter})."
            })
            failsafe_counter += 1
            
        return valid_distractors

    @staticmethod
    def _get_collocations(word: str) -> list:
        collocations = []
        
        active_dojo_dicts = QuestionBuilder._get_active_dojo_dicts()
        for dict_name, handler in dict_service.active_dictionaries.items():
            # NEW: Only extract collocations from our active Top 3 Whitelist
            if not any(d.lower() in dict_name.lower() for d in active_dojo_dicts):
                continue
                
            try:
                conn = sqlite3.connect(handler.db_path)
                c = conn.cursor()
                c.execute("SELECT html FROM entries WHERE word = ? COLLATE NOCASE LIMIT 1", (word,))
                row = c.fetchone()
                conn.close()
                
                if row:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(row[0], 'html.parser')
                    colls = handler._get_collocations(soup)
                    collocations.extend(colls)
            except Exception:
                continue
                
        valid_colls = []
        pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
        for c in set(collocations):
            if pattern.search(c):
                valid_colls.append(c.strip())
                
        return valid_colls

    @staticmethod
    def _get_best_example(word: str, word_id: int, encounter_index: int) -> str:
        # NEW: Ensure example sentences are only pulled from the Top 3
        aggregated_data = dict_service.get_aggregated_features(word, allowed_dicts=QuestionBuilder._get_active_dojo_dicts())
        all_examples = []

        if aggregated_data and aggregated_data.get('pos_blocks'):
            for block in aggregated_data['pos_blocks']:
                for meaning in block.get('meanings', []):
                    for ex in meaning.get('examples', []):
                        ex_text = ex.get('text') if isinstance(ex, dict) else ex
                        if ex_text:
                            all_examples.append(re.sub(r'\s+', ' ', ex_text).strip())

        if not all_examples: return None

        pinned_senses = SavedSense.query.filter_by(word_id=word_id).all()
        pinned_text = ""
        if pinned_senses:
            for s in pinned_senses:
                if s.html_content:
                    pinned_text += " " + re.sub(r'<[^>]+>', ' ', s.html_content)
        pinned_text = re.sub(r'\s+', ' ', pinned_text).strip().lower()

        scored_examples = []
        word_pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)

        for ex in set(all_examples): 
            occurrences = len(word_pattern.findall(ex))
            if occurrences == 0: continue
                
            score = 0
            if occurrences == 1: score += 20 
            else: score -= 5 

            if not re.search(r'\(\s*=', ex): score += 10
            else: score -= 10 

            if pinned_text and ex[:25].lower() in pinned_text: score += 50 
            
            scored_examples.append((score, ex))

        if not scored_examples: return None

        scored_examples.sort(key=lambda x: (-x[0], x[1]))
        return scored_examples[encounter_index % len(scored_examples)][1]

    @staticmethod
    def _mask_word_in_html(html_str: str, target_word: str, mode: str) -> str:
        if not html_str or html_str == "No context found. Define the word:": return html_str

        if mode == 'cloze_hybrid':
            replacement = r'<span class="px-3 py-0.5 mx-1 bg-slate-200 text-slate-400 font-mono font-bold rounded-md tracking-widest">______</span>'
        elif mode == 'proofreader':
            typos = QuestionBuilder._generate_typos(target_word)
            typo = typos[0] if typos else target_word + "x"
            replacement = rf'<span class="font-bold text-rose-600 underline decoration-wavy decoration-rose-400">{typo}</span>'
        elif mode == 'verb_conjugation':
            replacement = rf'<span class="px-2 py-0.5 mx-1 bg-indigo-50 text-indigo-600 border border-indigo-200 font-mono font-bold rounded shadow-inner text-sm">[ Verb: {target_word} ]</span>'
        else:
            return html_str

        pattern = re.compile(r'\b' + re.escape(target_word) + r'\b(?![^<]*>)', re.IGNORECASE)
        return pattern.sub(replacement, html_str)

    @staticmethod
    def _generate_typos(word: str) -> list:
        typos = set()
        vowels = "aeiou"
        for i in range(len(word)):
            if i < len(word) - 1:
                typos.add(word[:i] + word[i+1] + word[i] + word[i+2:])
            typos.add(word[:i] + word[i+1:])
            if word[i] in vowels:
                wrong_vowel = random.choice([v for v in vowels if v != word[i]])
                typos.add(word[:i] + wrong_vowel + word[i+1:])
        valid_typos = [t for t in list(typos) if t != word and len(t) > 2]
        return random.sample(valid_typos, min(3, len(valid_typos)))