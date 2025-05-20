from flask import Flask, jsonify, request, render_template, redirect, url_for, session
import os
from transcribe import AssemblyAITranscriber
from werkzeug.utils import secure_filename
import logging
from authlib.integrations.flask_client import OAuth
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import csv
import datetime
import time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecret")
oauth = OAuth(app)

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

# Configuración de Google OAuth
app.config['GOOGLE_CLIENT_ID'] = os.environ.get("GOOGLE_CLIENT_ID")
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get("GOOGLE_CLIENT_SECRET")
app.config['GOOGLE_DISCOVERY_URL'] = "https://accounts.google.com/.well-known/openid-configuration"

google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url=app.config['GOOGLE_DISCOVERY_URL'],
    client_kwargs={
        'scope': 'openid email profile'
    }
)

login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id_, name, email):
        self.id = id_
        self.name = name
        self.email = email

    def get_id(self):
        return self.id

users = {}

@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)

@app.route('/login')
def login():
    redirect_uri = url_for('auth_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth_callback():
    token = google.authorize_access_token()
    userinfo = token['userinfo']
    user = User(
        id_=userinfo['sub'],
        name=userinfo.get('name', ''),
        email=userinfo['email']
    )
    users[user.id] = user
    login_user(user)
    session['email'] = user.email
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('index'))

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
@login_required
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
        # Crear carpeta por usuario
        user_folder = os.path.join('user_uploads', current_user.email)
        os.makedirs(user_folder, exist_ok=True)
        # Nombre único para el archivo
        unique_filename = f"{int(time.time())}_{filename}"
        user_file_path = os.path.join(user_folder, unique_filename)
        # Guardar copia del archivo subido
        file.save(user_file_path)
        
        try:
            transcriber = AssemblyAITranscriber()
            upload_url = transcriber.upload_file(filepath)
            raw_result = transcriber.transcribe(upload_url)
            formatted_result = format_analysis_result(raw_result)
            formatted_result['uploaded_by'] = current_user.email
            # Guardar registro en CSV
            log_path = os.path.join(os.getcwd(), 'uploads_log.csv')
            with open(log_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    current_user.email,
                    filename,
                    user_file_path,
                    request.remote_addr,
                    datetime.datetime.now().isoformat()
                ])
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

@app.context_processor
def inject_user():
    return dict(current_user=current_user)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port) 