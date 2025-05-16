from flask import Flask, jsonify, request, render_template
import os
from transcribe import AssemblyAITranscriber
from werkzeug.utils import secure_filename
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'flac', 'mp4', 'webm'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_analysis_result(raw_result):
    """Format the raw analysis result into a more user-friendly structure."""
    try:
        return {
            'text': raw_result.get('text', ''),
            'scores': {
                'structure': raw_result.get('structure_score', 0),
                'persuasion': raw_result.get('persuasion_score', 0),
                'clarity': raw_result.get('clarity_score', 0),
                'engagement': raw_result.get('engagement_score', 0),
                'overall': raw_result.get('overall_score', 0)
            },
            'feedback': raw_result.get('feedback', []),
            'duration': raw_result.get('audio_duration', 0)
        }
    except Exception as e:
        logger.error(f"Error formatting result: {str(e)}")
        return raw_result

@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "version": "1.0.0",
        "service": "speech-analysis"
    })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_audio():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "error": f"File type not allowed. Supported formats: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        logger.info(f"Processing file: {filename}")
        file.save(filepath)
        
        try:
            transcriber = AssemblyAITranscriber()
            upload_url = transcriber.upload_file(filepath)
            raw_result = transcriber.transcribe(upload_url)
            formatted_result = format_analysis_result(raw_result)
            
            logger.info(f"Successfully analyzed file: {filename}")
            return jsonify(formatted_result)
            
        except Exception as e:
            logger.error(f"Error processing file {filename}: {str(e)}")
            return jsonify({"error": "Error processing audio file. Please try again."}), 500
        
        finally:
            # Clean up the uploaded file
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Cleaned up file: {filename}")
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 