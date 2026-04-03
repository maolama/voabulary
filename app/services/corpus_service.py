import os
import sqlite3
import logging
import re

logger = logging.getLogger(__name__)
DB_PATH = os.path.join("data", "academic_corpus.db")

def natural_sort_key(s):
    """
    Helper function for natural alphanumeric sorting.
    Ensures 'Exam 2' comes before 'Exam 10'.
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

class CorpusService:
    """Handles read-only queries to the external Academic Corpus database."""

    @staticmethod
    def get_connection():
        if not os.path.exists(DB_PATH):
            return None
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def get_filters():
        """Fetches available exam types for the filter dropdown."""
        conn = CorpusService.get_connection()
        if not conn: return []
        
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM ExamTypes")
        rows = cursor.fetchall()
        conn.close()
        
        # Apply Natural Sort
        exam_types = [{"id": r["id"], "name": r["name"]} for r in rows]
        exam_types.sort(key=lambda x: natural_sort_key(x["name"]))
        
        return exam_types

    @staticmethod
    def get_paginated_sentences(lemma: str, exam_type_id=None, exam_id=None, subject_id=None, page: int = 1, per_page: int = 10):
        """Fetches occurrences of a lemma, respecting all analytics filters."""
        conn = CorpusService.get_connection()
        if not conn: return None

        cursor = conn.cursor()
        
        base_query = """
            FROM Vocabulary v
            JOIN Word_Occurrences wo ON v.id = wo.word_id
            JOIN Sentences s ON wo.sentence_id = s.id
            JOIN Paragraphs p ON s.paragraph_id = p.id
            JOIN Sections sec ON p.section_id = sec.id
            LEFT JOIN Exam_Section_Map esm ON sec.id = esm.section_id
            LEFT JOIN Exams e ON esm.exam_id = e.id
            LEFT JOIN ExamTypes et ON e.exam_type_id = et.id
            WHERE v.lemma = ? COLLATE NOCASE
        """
        params = [lemma]

        if exam_type_id:
            base_query += " AND et.id = ?"
            params.append(exam_type_id)
        if exam_id:
            base_query += " AND e.id = ?"
            params.append(exam_id)
        if subject_id:
            base_query += " AND sec.subject_id = ?"
            params.append(subject_id)

        # Total Count
        cursor.execute(f"SELECT COUNT(DISTINCT s.id) {base_query}", params)
        total_items = cursor.fetchone()[0]

        # Paginated Data
        data_query = f"""
            SELECT s.id as sentence_id, s.raw_text, sec.id as section_id, sec.name as section_name, 
                   e.name as exam_name, et.name as exam_type, wo.original_format
            {base_query}
            GROUP BY s.id
            ORDER BY e.name, sec.name, p.block_order ASC, s.sentence_order ASC
            LIMIT ? OFFSET ?
        """
        params.extend([per_page, (page - 1) * per_page])
        
        cursor.execute(data_query, params)
        rows = cursor.fetchall()
        conn.close()

        sentences = []
        for r in rows:
            sentences.append({
                "id": r["sentence_id"],
                "section_id": r["section_id"],
                "text": r["raw_text"],
                "section": r["section_name"] or "Unknown Section",
                "exam": r["exam_name"] or "General Academic",
                "exam_type": r["exam_type"] or "Misc",
                "word_form": r["original_format"]
            })

        return {
            "sentences": sentences,
            "total_items": total_items,
            "total_pages": max(1, (total_items + per_page - 1) // per_page),
            "current_page": page
        }

    @staticmethod
    def get_passage(section_id: int):
        """Fetches the complete reading passage, grouped by paragraphs, with CEFR mapping."""
        conn = CorpusService.get_connection()
        if not conn: return None

        cursor = conn.cursor()
        cursor.execute("SELECT name, difficulty, full_text FROM Sections WHERE id = ?", (section_id,))
        sec = cursor.fetchone()
        
        if not sec: 
            conn.close()
            return None

        # 1. THE X-RAY ENGINE
        cursor.execute("""
            SELECT DISTINCT LOWER(wo.original_format) as word_form, v.cefr_level 
            FROM Vocabulary v
            JOIN Word_Occurrences wo ON v.id = wo.word_id
            JOIN Sentences s ON wo.sentence_id = s.id
            JOIN Paragraphs p ON s.paragraph_id = p.id
            WHERE p.section_id = ? AND v.cefr_level IS NOT NULL
        """, (section_id,))
        cefr_mapping = {row["word_form"]: row["cefr_level"] for row in cursor.fetchall()}

        # 2. THE HIGHLIGHT ENGINE (Now grouped by Paragraphs!)
        cursor.execute("""
            SELECT p.id as p_id, s.id as s_id, s.raw_text 
            FROM Paragraphs p
            LEFT JOIN Sentences s ON s.paragraph_id = p.id
            WHERE p.section_id = ?
            ORDER BY p.block_order ASC, s.sentence_order ASC
        """, (section_id,))
        
        rows = cursor.fetchall()
        conn.close()

        paragraphs = []
        current_p_id = None
        current_p = None

        for r in rows:
            if r["p_id"] != current_p_id:
                if current_p:
                    paragraphs.append(current_p)
                current_p_id = r["p_id"]
                current_p = {"id": current_p_id, "sentences": []}
            
            if r["s_id"]:
                current_p["sentences"].append({"id": r["s_id"], "text": r["raw_text"]})
                
        if current_p:
            paragraphs.append(current_p)

        return {
            "section_name": sec["name"],
            "difficulty": sec["difficulty"],
            "full_text": sec["full_text"],  # Add this back for the main Explorer!
            "cefr_mapping": cefr_mapping,
            "paragraphs": paragraphs        # Use grouped paragraphs instead of a flat list
        }
    
    @staticmethod
    def get_explorer_hierarchy():
        """Fetches the nested directory structure: ExamTypes -> Exams (Naturally Sorted)"""
        conn = CorpusService.get_connection()
        if not conn: return []
        
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name FROM ExamTypes")
        exam_types = [dict(row) for row in cursor.fetchall()]
        exam_types.sort(key=lambda x: natural_sort_key(x["name"]))
        
        cursor.execute("SELECT id, exam_type_id, name FROM Exams")
        exams = [dict(row) for row in cursor.fetchall()]
        exams.sort(key=lambda x: natural_sort_key(x["name"]))
        
        conn.close()

        hierarchy = []
        for et in exam_types:
            et_exams = [e for e in exams if e['exam_type_id'] == et['id']]
            hierarchy.append({
                "id": et["id"],
                "name": et["name"],
                "exams": et_exams
            })
        
        return hierarchy

    @staticmethod
    def get_explorer_sections(exam_id: int, page: int = 1, per_page: int = 20):
        """Fetches a paginated, naturally sorted list of sections for a specific exam."""
        conn = CorpusService.get_connection()
        if not conn: return None

        cursor = conn.cursor()
        
        # We fetch all matching sections first to sort them accurately in Python
        query = """
            SELECT s.id, s.name, s.difficulty
            FROM Sections s
            JOIN Exam_Section_Map esm ON s.id = esm.section_id
            WHERE esm.exam_id = ?
        """
        cursor.execute(query, (exam_id,))
        rows = cursor.fetchall()
        conn.close()

        # Build list and apply Natural Sort
        sections = [{"id": r["id"], "name": r["name"], "difficulty": r["difficulty"]} for r in rows]
        sections.sort(key=lambda x: natural_sort_key(x["name"]))

        # Calculate Python-side Pagination
        total_items = len(sections)
        total_pages = max(1, (total_items + per_page - 1) // per_page)
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_sections = sections[start_idx:end_idx]

        return {
            "sections": paginated_sections,
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page
        }
    
    @staticmethod
    def get_lemma(word_form: str):
        """Attempts to find the root lemma for a given word form using the corpus DB."""
        conn = CorpusService.get_connection()
        if not conn: return word_form

        cursor = conn.cursor()
        # Join Word_Occurrences with Vocabulary to find the lemma of the exact string
        cursor.execute("""
            SELECT v.lemma 
            FROM Vocabulary v 
            JOIN Word_Occurrences wo ON v.id = wo.word_id 
            WHERE wo.original_format = ? COLLATE NOCASE 
            LIMIT 1
        """, (word_form,))
        
        row = cursor.fetchone()
        conn.close()
        
        # Return the lemma if found, otherwise fallback to the exact word clicked
        if row and row['lemma']:
            return row['lemma']
        return word_form
    
    @staticmethod
    def get_analytics_filters():
        """Fetches available subjects along with the existing hierarchy for the Analytics tab."""
        conn = CorpusService.get_connection()
        if not conn: return []
        
        cursor = conn.cursor()
        
        # We already have exam types/exams from the hierarchy method, 
        # but now we need Subjects for the new filters!
        cursor.execute("SELECT id, name FROM Subjects ORDER BY name")
        rows = cursor.fetchall()
        subjects = [{"id": r["id"], "name": r["name"]} for r in rows]
        
        conn.close()
        return subjects

    @staticmethod
    def get_dynamic_frequencies(exam_type_id=None, exam_id=None, subject_id=None, page=1, per_page=50):
        """Calculates word frequencies dynamically, ignoring pre-computed fields to ensure 100% accuracy."""
        conn = CorpusService.get_connection()
        if not conn: return None
        cursor = conn.cursor()

        # BASE JOINS: Always needed to count words
        query_joins = """
            FROM Vocabulary v
            JOIN Word_Occurrences wo ON v.id = wo.word_id
        """
        
        # Determine if we need deep relational joins based on the applied filters
        needs_section_join = subject_id is not None
        needs_exam_join = exam_type_id is not None or exam_id is not None

        # Add Section & Paragraph tables if any filter is applied
        if needs_section_join or needs_exam_join:
            query_joins += """
                JOIN Sentences s ON wo.sentence_id = s.id
                JOIN Paragraphs p ON s.paragraph_id = p.id
                JOIN Sections sec ON p.section_id = sec.id
            """
            
        # Add Exam tables only if exam-specific filters are applied
        if needs_exam_join:
            query_joins += """
                JOIN Exam_Section_Map esm ON sec.id = esm.section_id
                JOIN Exams e ON esm.exam_id = e.id
                JOIN ExamTypes et ON e.exam_type_id = et.id
            """

        # Filter out punctuation and low-value grammar words
        where_clauses = ["v.pos NOT IN ('PUNCT', 'SYM', 'X', 'SPACE', 'DET', 'ADP', 'CCONJ', 'PRON')"]
        params = []

        if subject_id:
            where_clauses.append("sec.subject_id = ?")
            params.append(subject_id)
        if exam_type_id:
            where_clauses.append("et.id = ?")
            params.append(exam_type_id)
        if exam_id:
            where_clauses.append("e.id = ?")
            params.append(exam_id)

        where_sql = " WHERE " + " AND ".join(where_clauses)

        # 1. Get total unique words matching this filter
        count_query = f"SELECT COUNT(DISTINCT v.id) {query_joins} {where_sql}"
        cursor.execute(count_query, params)
        total_items = cursor.fetchone()[0]

        # 2. Get the actual frequencies sorted
        data_query = f"""
            SELECT v.id, v.lemma, v.pos, v.cefr_level, v.is_awl, COUNT(wo.id) as freq
            {query_joins}
            {where_sql}
            GROUP BY v.id
            ORDER BY freq DESC
            LIMIT ? OFFSET ?
        """
        
        paginate_params = params + [per_page, (page - 1) * per_page]
        cursor.execute(data_query, paginate_params)
        
        rows = cursor.fetchall()
        conn.close()

        words = [dict(r) for r in rows]
        return {
            "words": words,
            "total_items": total_items,
            "total_pages": max(1, (total_items + per_page - 1) // per_page),
            "current_page": page
        }

    @staticmethod
    def get_collocations(lemma: str, limit: int = 30):
        """
        Finds collocations based on lexical proximity (words appearing near each other).
        Fallback for databases without dependency head_word_id links.
        """
        conn = CorpusService.get_connection()
        if not conn: return []
        cursor = conn.cursor()

        # We use a window of 3 (current word + 2 before or 2 after)
        query = """
            SELECT 
                v_other.lemma as colloc_lemma, 
                v_other.pos as colloc_pos, 
                'Proximity' as dependency_role, 
                COUNT(*) as freq
            FROM Vocabulary v_target
            JOIN Word_Occurrences wo_target ON v_target.id = wo_target.word_id
            JOIN Word_Occurrences wo_other ON wo_target.sentence_id = wo_other.sentence_id
            JOIN Vocabulary v_other ON wo_other.word_id = v_other.id
            WHERE v_target.lemma = ? COLLATE NOCASE
              -- Distance logic: ensure words are close but not the same word
              AND ABS(wo_target.id - wo_other.id) BETWEEN 1 AND 3
              -- Filter structural noise
              AND v_other.pos NOT IN ('PUNCT', 'SPACE', 'SYM', 'X', 'DET', 'CCONJ', 'SCONJ', 'ADP', 'PRON', 'PART', 'NUM')
              AND v_other.lemma != v_target.lemma
            GROUP BY v_other.lemma
            ORDER BY freq DESC
            LIMIT ?
        """
        cursor.execute(query, (lemma, limit))
        rows = cursor.fetchall()
        conn.close()

        return [dict(r) for r in rows]