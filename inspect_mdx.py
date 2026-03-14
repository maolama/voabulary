# import sqlite3
# import os

# def inspect_specific_word(db_path, word):
#     if not os.path.exists(db_path):
#         print(f"Error: Database not found at {db_path}")
#         return

#     conn = sqlite3.connect(db_path)
#     c = conn.cursor()
    
#     # Using your exact table/column names: entries (word, html)
#     c.execute("SELECT html FROM entries WHERE word = ? LIMIT 1", (word,))
#     row = c.fetchone()
#     conn.close()

#     if row:
#         print(f"\n[ RAW HTML FOR: {word} ]")
#         print("=" * 60)
#         print(row[0]) 
#         print("=" * 60)
#     else:
#         print(f"Word '{word}' not found in this database.")

# if __name__ == "__main__":
#     # Path to your OALD9 database
#     DB_PATH = "dict/MacmillanEnEn/MacmillanEnEn.db" 
#     inspect_specific_word(DB_PATH, "abandon")
    

import sqlite3
import os
import json

# The 6 specific dictionaries we are targeting
DICTIONARIES = [
    "CCABELD",
    "OALD9EnEn",
    "CALD4",
    "mwaled",
    "MacmillanEnEn",
    "LongmanAdvancedAmericanDictionary3thEnEn"
]

# Our 10 tricky words + abandon
WORDS_TO_TEST = [
    "abandon", "record", "tear", "lie", "café", 
    "mouse", "bear", "heavy", "focus"
]

def export_dictionary_samples(dict_base_path):
    # Create an output directory so we don't clutter your root folder
    output_dir = "sample_jsons"
    os.makedirs(output_dir, exist_ok=True)

    for dict_name in DICTIONARIES:
        # Assuming your folder structure is dict/DictName/DictName.db
        db_path = os.path.join(dict_base_path, dict_name, f"{dict_name}.db")
        
        if not os.path.exists(db_path):
            print(f"[-] Skipping {dict_name}: Database not found at {db_path}")
            continue

        print(f"[*] Processing {dict_name}...")
        dict_data = {}
        
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            for word in WORDS_TO_TEST:
                # We query the database. Since you used COLLATE NOCASE when creating it, 
                # this will safely handle capitalization.
                c.execute("SELECT html FROM entries WHERE word = ? LIMIT 1", (word,))
                row = c.fetchone()
                
                if row:
                    dict_data[word] = row[0]
                else:
                    # Note: "café" or "ain't" might not exist depending on the dictionary
                    dict_data[word] = None
                    print(f"    [!] Word '{word}' not found in {dict_name}.")
            
            conn.close()
            
            # Save the gathered HTML to a JSON file
            output_file = os.path.join(output_dir, f"{dict_name}_samples.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(dict_data, f, ensure_ascii=False, indent=4)
                
            print(f"[+] Successfully saved {dict_name} data to {output_file}\n")
            
        except Exception as e:
            print(f"Error processing {dict_name}: {e}")

if __name__ == "__main__":
    # Your base dictionary directory
    DICT_BASE_FOLDER = "dict" 
    export_dictionary_samples(DICT_BASE_FOLDER)
    print("All extraction complete! Check the 'sample_jsons' folder.")