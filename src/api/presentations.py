from flask import Blueprint, request, jsonify
from config import Config
from services.vision import analyze_workspace_video
import os
import tempfile

presentations_bp = Blueprint("presentations", __name__)

@presentations_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "version": "1.0.0"})

@presentations_bp.route("/presentations/upload", methods=["POST"])
def upload_presentation():
    # Validar API Key
    api_key = request.headers.get('X-API-Key')
    if api_key != Config.API_KEY:
        return jsonify({"error": "API key inválida"}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    file = request.files['file']
    filename = file.filename
    if not filename:
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400

    # Guardar archivo temporalmente
    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
        file.save(tmp.name)
        video_path = tmp.name

    # Si el archivo es workspace.webm, hacer análisis visual
    vision_summary = None
    if filename == 'workspace.webm':
        try:
            vision_summary = analyze_workspace_video(video_path)
        except Exception as e:
            vision_summary = [f"Error en análisis visual: {e}"]

    # Aquí iría el resto del análisis (transcripción, AI, etc.)
    # Para este ejemplo, solo devolvemos el vision_summary
    result = {
        "filename": filename,
        "vision_summary": vision_summary
    }
    # Eliminar archivo temporal
    os.unlink(video_path)
    return jsonify(result)
