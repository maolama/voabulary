import csv
import re
import io
from datetime import datetime
from ..models import SavedWord
from ..extensions import db, logger

class GoogleSheetImporter:
    """Adapts the 24-column Google Sheets export into the Vocab Empire database."""

    @staticmethod
    def clean_list_block(text):
        """Removes '--- POS ---' headers and '• ' bullets, returning a clean list of strings."""
        if not text:
            return []
            
        cleaned = []
        for line in text.split('\n'):
            line = line.strip()
            # Skip headers like "--- NOUN ---"
            if re.match(r'^---.+---$', line):
                continue
            # Remove the bullet point
            if line.startswith('•'):
                line = line.lstrip('• ').strip()
            if line:
                cleaned.append(line)
        return cleaned

    @staticmethod
    def extract_pronunciation(text):
        """Extracts '/ipa/' from strings like 'noun:/ipa/' or returns empty if 'pos:—'"""
        if not text or text == '—':
            return ""
        if ':' in text:
            val = text.split(':', 1)[-1].strip()
            return "" if val == '—' else val
        return text.strip()

    @staticmethod
    def process_csv(file_stream):
        """Reads a CSV exported from the legacy Google Apps Script tool."""
        
        # CRITICAL FIX: Use io.StringIO to preserve internal newlines inside CSV cells!
        content = file_stream.read().decode('utf-8')
        stream = io.StringIO(content, newline=None)
        reader = csv.reader(stream)
        
        next(reader, None) # Skip headers
        
        success_count = 0
        failed_words = []

        for row in reader:
            if len(row) < 24:
                continue
                
            word_text = row[0].strip().lower()
            if not word_text:
                continue
                
            # 1. Check if word already exists in our DB
            word_obj = SavedWord.query.filter_by(word=word_text).first()
            if not word_obj:
                word_obj = SavedWord(word=word_text)
                db.session.add(word_obj)

            # 2. Map SRS Data (if valid)
            try:
                if row[17]:
                    date_str = row[17].split(' ')[0] 
                    if '-' in date_str:
                        word_obj.next_review_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    else:
                        word_obj.next_review_date = datetime.strptime(date_str, '%m/%d/%Y').date()
            except Exception as e:
                logger.warning(f"Could not parse date for {word_text}: {row[17]}")

            if row[20].isdigit():
                word_obj.repetitions = int(row[20])
                word_obj.total_reviews = int(row[20])

            # 3. REVERSE-ENGINEER THE GOOGLE SCRIPT FORMATTING
            # The Apps Script separated different parts of speech using '\n\n'
            pos_list = [p.strip() for p in row[6].split(',')] if row[6] else ["mixed"]
            
            trans_blocks = row[1].split('\n\n')
            defs_blocks = row[2].split('\n\n')
            def_exs_blocks = row[3].split('\n\n')
            
            gen_ex_en_blocks = row[4].split('\n\n')
            gen_ex_per_blocks = row[5].split('\n\n')
            
            syn_blocks = row[7].split('\n\n')
            ant_blocks = row[8].split('\n\n')
            note_blocks = row[9].split('\n\n')
            word_fam_blocks = row[10].split('\n\n')
            
            # Prons were separated by single newlines, not double
            uk_prons = [p for p in row[13].split('\n') if p]
            us_prons = [p for p in row[14].split('\n') if p]

            custom_data = []

            # Iterate over however many Parts of Speech this word has
            for i in range(len(pos_list)):
                pos = pos_list[i]

                # Extract and clean Pronunciations
                uk_pron = GoogleSheetImporter.extract_pronunciation(uk_prons[i]) if i < len(uk_prons) else ""
                us_pron = GoogleSheetImporter.extract_pronunciation(us_prons[i]) if i < len(us_prons) else ""

                # Extract and clean bullet point lists
                defs = GoogleSheetImporter.clean_list_block(defs_blocks[i]) if i < len(defs_blocks) else []
                exs = GoogleSheetImporter.clean_list_block(def_exs_blocks[i]) if i < len(def_exs_blocks) else []
                trans = GoogleSheetImporter.clean_list_block(trans_blocks[i]) if i < len(trans_blocks) else []

                # Build Meanings Array by pairing definitions with their respective examples
                meanings = []
                for j in range(max(len(defs), len(exs), len(trans))):
                    meanings.append({
                        "definition": defs[j] if j < len(defs) else "",
                        "example": exs[j] if j < len(exs) else "",
                        "translation": trans[j] if j < len(trans) else "",
                        "mnemonic": ""
                    })

                # Build General Examples Array by pairing English/Persian line by line
                gen_en = GoogleSheetImporter.clean_list_block(gen_ex_en_blocks[i]) if i < len(gen_ex_en_blocks) else []
                gen_per = GoogleSheetImporter.clean_list_block(gen_ex_per_blocks[i]) if i < len(gen_ex_per_blocks) else []
                
                general_examples = []
                for j in range(max(len(gen_en), len(gen_per))):
                    general_examples.append({
                        "example": gen_en[j] if j < len(gen_en) else "",
                        "translation": gen_per[j] if j < len(gen_per) else ""
                    })

                # Synonyms, Antonyms, Notes
                syns = GoogleSheetImporter.clean_list_block(syn_blocks[i]) if i < len(syn_blocks) else []
                ants = GoogleSheetImporter.clean_list_block(ant_blocks[i]) if i < len(ant_blocks) else []
                notes = GoogleSheetImporter.clean_list_block(note_blocks[i]) if i < len(note_blocks) else []

                # Build Word Family (Parsing "faster (adjective)" into its JSON parts)
                wf_cleaned = GoogleSheetImporter.clean_list_block(word_fam_blocks[i]) if i < len(word_fam_blocks) else []
                word_family = []
                for item in wf_cleaned:
                    match = re.match(r'^(.+?)\s*\((.+?)\)$', item)
                    if match:
                        word_family.append({"word": match.group(1).strip(), "pos": match.group(2).strip()})
                    else:
                        word_family.append({"word": item, "pos": ""})

                # Assemble the pristine JSON object for this specific Part of Speech
                pos_obj = {
                    "partOfSpeech": pos,
                    "ukPronunciation": uk_pron,
                    "usPronunciation": us_pron,
                    "meanings": meanings,
                    "generalExamples": general_examples,
                    "synonyms": syns,
                    "antonyms": ants,
                    "collocations": [],
                    "notes": notes,
                    "wordFamily": word_family
                }
                custom_data.append(pos_obj)

            # Save the fully structured JSON array to the database
            word_obj.custom_data = custom_data
            success_count += 1
            
        db.session.commit()
        return success_count, failed_words