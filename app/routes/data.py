import csv
import io
from flask import Blueprint, request, render_template, render_template_string, jsonify, send_file, Response
from ..models import SavedWord, Tag
from ..extensions import db, logger
from ..services.gamification import GamificationService
from app import dict_service

# Note: This is usually registered in your app factory with url_prefix='/data'
bp = Blueprint('data', __name__)

@bp.route('/data-manager', methods=['GET'])
def data_manager_page():
    return render_template('data_manager.html')

# ============================================================
# HELPER: SHARED IMPORT LOGIC
# ============================================================
def process_imported_items(items):
    """
    Takes a list of tuples: [(word_text, tags_text), ...]
    Cleans, validates against dictionaries, adds tags, and saves.
    """
    success_count = 0
    failed_words = []

    for word_text, tags_text in items:
        word_text = word_text.strip().lower()
        if not word_text: 
            continue

        # 1. Check if already in DB
        if SavedWord.query.filter_by(word=word_text).first():
            continue

        # 2. Check if word exists in offline dictionaries
        dict_results = dict_service.search_word(word_text)
        if not dict_results:
            failed_words.append(word_text)
            continue

        # 3. Create the word
        new_word = SavedWord(word=word_text)

        # 4. Handle tags (if provided)
        if tags_text:
            tag_names = [t.strip().lower() for t in tags_text.split(',')]
            for t_name in tag_names:
                if not t_name: continue
                tag_obj = Tag.query.filter_by(name=t_name).first()
                if not tag_obj:
                    tag_obj = Tag(name=t_name)
                    db.session.add(tag_obj)
                new_word.tags.append(tag_obj)

        # 5. Save and Log
        db.session.add(new_word)
        GamificationService.log_activity('word_added')
        success_count += 1

    db.session.commit()
    return success_count, failed_words

def render_import_result(success_count, failed_words):
    """Generates the HTML response for HTMX after an import."""
    failed_html = ""
    if failed_words:
        failed_list = ", ".join(failed_words[:10])
        more = "..." if len(failed_words) > 10 else ""
        failed_html = f"""
        <div class="mt-2 text-xs text-rose-600 bg-rose-50 p-3 rounded-lg border border-rose-100">
            <b>{len(failed_words)} skipped (not in dict):</b> {failed_list}{more}
        </div>
        """
        
    return f"""
    <div class="p-4 bg-emerald-50 text-emerald-800 rounded-xl font-medium border border-emerald-200 shadow-sm transition-all">
        ✅ Successfully imported <b>{success_count}</b> new words!
        {failed_html}
    </div>
    """

# ============================================================
# IMPORT ROUTES
# ============================================================

@bp.route('/import-text', methods=['POST'])
def import_text():
    """Handles manual text entry (Method 1)"""
    text = request.form.get('words_text', '')
    raw_lines = text.replace(',', '\n').split('\n')
    
    items = [(line, "") for line in raw_lines]
    
    success_count, failed_words = process_imported_items(items)
    return render_import_result(success_count, failed_words)


@bp.route('/import-file', methods=['POST'])
def import_file():
    """Handles TXT (Method 2) and CSV (Method 3) uploads"""
    if 'file' not in request.files:
        return '<div class="p-4 bg-rose-50 text-rose-800 rounded-xl">❌ No file uploaded</div>', 400
        
    file = request.files['file']
    if file.filename == '':
        return '<div class="p-4 bg-rose-50 text-rose-800 rounded-xl">❌ No file selected</div>', 400

    items = []
    try:
        content = file.stream.read().decode("UTF8")
        
        if file.filename.lower().endswith('.csv'):
            stream = io.StringIO(content, newline=None)
            csv_input = csv.reader(stream)
            for row in csv_input:
                if row and row[0].strip():
                    tags = row[1] if len(row) > 1 else ""
                    items.append((row[0], tags))
        else:
            raw_lines = content.split('\n')
            items = [(line, "") for line in raw_lines]
            
        success_count, failed_words = process_imported_items(items)
        return render_import_result(success_count, failed_words)
        
    except Exception as e:
        logger.error(f"File import error: {e}")
        return f'<div class="p-4 bg-rose-50 text-rose-800 rounded-xl">❌ Error processing file.</div>'

# ============================================================
# EXPORT ROUTES
# ============================================================

@bp.route('/export-raw', methods=['GET'])
def export_raw():
    """Returns a copy-pasteable HTML text area for HTMX swapping (Method 1)"""
    words = SavedWord.query.order_by(SavedWord.word).all()
    word_list = "\n".join([w.word for w in words])
    
    html_snippet = '''
    <div class="relative mt-2 animate-fade-in">
        <textarea id="export-textarea" class="w-full p-4 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none text-slate-700 font-mono text-sm shadow-inner" rows="8" readonly>{{ word_list }}</textarea>
        <button id="copy-btn" onclick="window.copyToClipboard('export-textarea')" class="absolute top-4 right-4 bg-white hover:bg-slate-100 text-slate-700 text-xs font-bold py-1.5 px-3 rounded-lg shadow border border-slate-200 transition">
            📋 Copy
        </button>
    </div>
    '''
    return render_template_string(html_snippet, word_list=word_list)


@bp.route('/export-txt', methods=['GET'])
def export_txt():
    """Generates a downloadable .txt file of just the words (Method 2)"""
    words = SavedWord.query.order_by(SavedWord.word).all()
    content = "\n".join([w.word for w in words])
    
    return Response(
        content, 
        mimetype="text/plain", 
        headers={"Content-disposition": "attachment; filename=empire_words_backup.txt"}
    )


@bp.route('/export-csv')
def export_csv():
    """Generates a downloadable .csv file with full SRS and Dojo statistics"""
    words = SavedWord.query.order_by(SavedWord.word).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # NEW: Added our Dojo stats to the header!
    writer.writerow([
        'Word', 'Next Review', 'Interval', 'Repetitions', 
        'Ease Factor', 'Tags', 'Spelling Streak', 
        'Dictation Streak', 'Avg Typing Ms'
    ])
    
    for w in words:
        tags = ", ".join([t.name for t in w.tags])
        review_date = w.next_review_date.strftime('%Y-%m-%d') if w.next_review_date else ''
        ease = round(w.ease_factor, 2) if w.ease_factor else 2.5
        
        # safely grab our new columns just in case
        s_streak = getattr(w, 'spelling_streak', 0)
        d_streak = getattr(w, 'dictation_streak', 0)
        typing_ms = round(getattr(w, 'avg_typing_fluidity', 0) or 0, 2)
        
        writer.writerow([
            w.word, review_date, w.interval, w.repetitions, 
            ease, tags, s_streak, d_streak, typing_ms
        ])
        
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='empire_full_backup.csv'
    )