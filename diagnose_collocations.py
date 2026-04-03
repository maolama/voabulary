import os
import sqlite3

DB_PATH = os.path.join("data", "academic_corpus.db")

def run_diagnostics():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=================================================================")
    print(" 🔍 PHASE 1: DB STRUCTURAL HEALTH CHECK")
    print("=================================================================")
    
    # Check if head_word_id is actually populated
    cursor.execute("SELECT COUNT(*) as total FROM Word_Occurrences")
    total_occ = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as linked FROM Word_Occurrences WHERE head_word_id IS NOT NULL")
    linked_occ = cursor.fetchone()['linked']
    
    print(f"Total Word Occurrences : {total_occ:,}")
    print(f"Occurrences with Links : {linked_occ:,}")
    
    if linked_occ == 0:
        print("⚠️  WARNING: Your database has ZERO dependency links (head_word_id is empty).")
        print("    This is why the strict grammatical collocations are returning nothing!")
    else:
        print(f"✅ Dependency links found: {linked_occ / total_occ * 100:.1f}% coverage.")

    test_words = ["impact", "significant", "environment"]

    for word in test_words:
        print("\n=================================================================")
        print(f" 🧪 PHASE 2: TESTING COLLOCATIONS FOR '{word.upper()}'")
        print("=================================================================")
        
        # 1. STRICT DEPENDENCY QUERY (What we are currently using)
        strict_query = """
            SELECT v_other.lemma, wo_other.dependency_role, COUNT(*) as freq
            FROM Vocabulary v_target
            JOIN Word_Occurrences wo_target ON v_target.id = wo_target.word_id
            JOIN Word_Occurrences wo_other ON wo_target.sentence_id = wo_other.sentence_id
            JOIN Vocabulary v_other ON wo_other.word_id = v_other.id
            WHERE v_target.lemma = ? COLLATE NOCASE
              AND (wo_target.id = wo_other.head_word_id OR wo_target.head_word_id = wo_other.id)
              AND v_other.pos NOT IN ('PUNCT', 'SPACE', 'SYM', 'X', 'DET', 'CCONJ', 'SCONJ', 'ADP', 'PRON', 'PART', 'NUM')
              AND v_other.lemma != v_target.lemma
            GROUP BY v_other.lemma, wo_other.dependency_role
            ORDER BY freq DESC LIMIT 5
        """
        cursor.execute(strict_query, (word,))
        strict_results = cursor.fetchall()
        
        print("\n[A] Strict Grammatical Collocations (Current App Logic):")
        if not strict_results:
            print("    ❌ None found.")
        for r in strict_results:
            print(f"    - {r['lemma']} ({r['dependency_role']}) : {r['freq']} times")

        # 2. PROXIMITY QUERY (Words within +/- 2 positions in the same sentence)
        # This ignores head_word_id entirely and just looks at adjacency.
        loose_query = """
            SELECT v_other.lemma, v_other.pos, COUNT(*) as freq
            FROM Vocabulary v_target
            JOIN Word_Occurrences wo_target ON v_target.id = wo_target.word_id
            JOIN Word_Occurrences wo_other ON wo_target.sentence_id = wo_other.sentence_id
            JOIN Vocabulary v_other ON wo_other.word_id = v_other.id
            WHERE v_target.lemma = ? COLLATE NOCASE
              AND ABS(wo_target.id - wo_other.id) <= 2
              AND v_other.pos NOT IN ('PUNCT', 'SPACE', 'SYM', 'X', 'DET', 'CCONJ', 'SCONJ', 'ADP', 'PRON', 'PART', 'NUM')
              AND v_other.lemma != v_target.lemma
            GROUP BY v_other.lemma
            ORDER BY freq DESC LIMIT 5
        """
        cursor.execute(loose_query, (word,))
        loose_results = cursor.fetchall()

        print("\n[B] Proximity Collocations (Fallback Logic - +/- 2 words):")
        if not loose_results:
            print("    ❌ None found.")
        for r in loose_results:
            print(f"    - {r['lemma']} ({r['pos']}) : {r['freq']} times")

    conn.close()

if __name__ == "__main__":
    run_diagnostics()