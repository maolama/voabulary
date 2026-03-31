from flask import Blueprint, request, jsonify
from ..models import SavedWord
from ..services.review import DojoEngine, QuestionBuilder, DojoGrader
from ..services.review.config import DojoConfig # NEW: Import the config manager
from ..extensions import db

bp = Blueprint('review_api', __name__)

@bp.route('/session/info', methods=['GET'])
def get_session_info():
    """
    Feeds the Dojo Start Screen with the total words due and the user's default limit.
    """
    try:
        from datetime import date
        today = date.today()
        total_due = SavedWord.query.filter(SavedWord.next_review_date <= today).count()
        config_data = DojoConfig.get_config()
        
        return jsonify({
            "status": "success",
            "data": {
                "total_due": total_due,
                "default_limit": config_data.get("default_session_words", 7)
            }
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route('/session', methods=['GET'])
def get_session_queue():
    """
    Fetches the daily review queue based on the requested limit.
    """
    try:
        # Default to 7 if no limit is passed, but the frontend will usually pass the slider value!
        limit = request.args.get('limit', 7, type=int)
        session_data = DojoEngine.generate_session(max_words=limit)
        
        return jsonify({
            "status": "success",
            "data": session_data
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route('/question/<int:word_id>', methods=['GET'])
def get_question_payload(word_id):
    """
    Fetches the specific puzzle (blanks, typos, context) for a word and mode.
    """
    try:
        mode = request.args.get('mode')
        encounter_index = request.args.get('encounter', 0, type=int)
        if not mode:
            return jsonify({"status": "error", "message": "Mode parameter is required"}), 400
            
        word_obj = SavedWord.query.get_or_404(word_id)
        payload = QuestionBuilder.build_payload(word_obj, mode, encounter_index)
        
        return jsonify({
            "status": "success",
            "data": payload
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route('/grade', methods=['POST'])
def submit_grade():
    """Receives the user's answer, adjusts Mastery Level, and FSRS intervals."""
    try:
        data = request.json
        if not data or 'word_id' not in data or 'is_correct' not in data or 'mode' not in data:
            return jsonify({"status": "error", "message": "Missing required fields"}), 400
            
        word_obj = SavedWord.query.get_or_404(data['word_id'])
        
        result = DojoGrader.grade_answer(
            word_obj=word_obj,
            is_correct=data['is_correct'],
            mode=data['mode'],
            typing_time_ms=data.get('typing_time_ms'),
            # NEW: Pass the flag to the grader (default to True just in case)
            is_last_encounter=data.get('is_last_encounter', True)
        )
        
        return jsonify({
            "status": "success",
            "data": result
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    

# ... (Keep all your existing routes in review.py) ...

@bp.route('/config', methods=['GET'])
def get_dojo_config():
    """Fetches the current user's Dojo Mastery Matrix."""
    try:
        config_data = DojoConfig.get_config()
        return jsonify({"status": "success", "data": config_data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/config', methods=['POST'])
def update_dojo_config():
    """Saves a new Dojo Mastery Matrix."""
    try:
        new_config = request.json
        if not new_config or 'phases' not in new_config:
            return jsonify({"status": "error", "message": "Invalid config data"}), 400
            
        DojoConfig.save_config(new_config)
        return jsonify({"status": "success", "message": "Matrix updated!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/config/reset', methods=['POST'])
def reset_dojo_config():
    """Resets the matrix back to the sensible defaults."""
    try:
        DojoConfig.reset_to_default()
        return jsonify({"status": "success", "data": DojoConfig.get_config()}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500