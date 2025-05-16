from flask import Flask, jsonify, request, render_template
import os
from transcribe import AssemblyAITranscriber
from werkzeug.utils import secure_filename
import logging

app = Flask(__name__)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurar carpeta de subidas
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'flac', 'mp4', 'webm'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB tamaño máximo de archivo

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_analysis_result(raw_result):
    """Formatea el resultado del análisis en una estructura más amigable."""
    try:
        return {
            'text': raw_result.get('text', ''),
            'scores': {
                'clarity': raw_result.get('scores', {}).get('clarity', 0),
                'engagement': raw_result.get('scores', {}).get('engagement', 0),
                'persuasion': raw_result.get('scores', {}).get('persuasion', 0),
                'structure': raw_result.get('scores', {}).get('structure', 0),
                'overall': raw_result.get('scores', {}).get('overall', 0)
            },
            'feedback': raw_result.get('feedback', []),
            'duration': raw_result.get('audio_duration', 0)
        }
    except Exception as e:
        logger.error(f"Error al formatear el resultado: {str(e)}")
        return raw_result

@app.route('/health')
def health_check():
    return jsonify({
        "status": "saludable",
        "version": "1.0.0",
        "servicio": "analizador-presentaciones"
    })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_audio():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No se ha subido ningún archivo"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No se ha seleccionado ningún archivo"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "error": f"Tipo de archivo no permitido. Formatos soportados: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        logger.info(f"Procesando archivo: {filename}")
        file.save(filepath)
        
        try:
            transcriber = AssemblyAITranscriber()
            upload_url = transcriber.upload_file(filepath)
            raw_result = transcriber.transcribe(upload_url)
            formatted_result = format_analysis_result(raw_result)
            
            logger.info(f"Archivo analizado exitosamente: {filename}")
            return jsonify(formatted_result)
            
        except Exception as e:
            logger.error(f"Error al procesar el archivo {filename}: {str(e)}")
            return jsonify({"error": "Error al procesar el archivo de audio. Por favor, inténtalo de nuevo."}), 500
        
        finally:
            # Limpiar el archivo subido
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Archivo limpiado: {filename}")
    
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}")
        return jsonify({"error": "Ha ocurrido un error inesperado"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 