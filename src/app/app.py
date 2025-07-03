# =============================================
# VERSIÓN: 2024-06-19 - Actualización de credenciales Azure Storage y Video Indexer
# =============================================
# 1. IMPORTS Y CONFIGURACIÓN INICIAL
# =============================================
import os
from flask import Flask, jsonify, request, render_template, redirect, url_for, session, send_from_directory, send_file
from .transcribe import AssemblyAITranscriber as Transcriber
from werkzeug.utils import secure_filename
import logging
from authlib.integrations.flask_client import OAuth
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import csv
import datetime
import time
import boto3
import tempfile
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta, timezone
import mimetypes
import uuid
import unicodedata
from .azure_transcriber import AzureTranscriber
import subprocess
import json
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_session import Session
from sqlalchemy import create_engine
from flask_sqlalchemy import SQLAlchemy
import threading
import requests
import shutil
from io import BytesIO
import random
import openai
import httpx

# Importar la nueva API
from .api import api_bp, init_jwt

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verificar variables de entorno requeridas
required_vars = [
    'AZURE_STORAGE_ACCOUNT_NAME',
    'AZURE_STORAGE_ACCOUNT_KEY',
    'AZURE_CONTAINER_NAME',
    'VIDEO_INDEXER_SUBSCRIPTION_KEY',
    'VIDEO_INDEXER_ACCOUNT_ID',
    'VIDEO_INDEXER_LOCATION'
]

missing_vars = [var for var in required_vars if not os.environ.get(var)]
if missing_vars:
    error_msg = f"Faltan las siguientes variables de entorno: {', '.join(missing_vars)}"
    logger.error(error_msg)
    raise ValueError(error_msg)

# --- Configuración de Azure AI Video Indexer ---
SUBSCRIPTION_KEY = os.environ.get("VIDEO_INDEXER_SUBSCRIPTION_KEY")
ACCOUNT_ID = os.environ.get("VIDEO_INDEXER_ACCOUNT_ID")
LOCATION = os.environ.get("VIDEO_INDEXER_LOCATION")

BASE_AUTH_URL = f"https://api.videoindexer.ai/Auth/{LOCATION}/Accounts/{ACCOUNT_ID}"
BASE_API_URL = f"https://api.videoindexer.ai/{LOCATION}/Accounts/{ACCOUNT_ID}"

app = Flask(__name__,
    template_folder='../templates',
    static_folder='../static'
)
app.secret_key = os.environ.get("SECRET_KEY", "supersecret")
oauth = OAuth(app)

# Inicializar JWT y registrar la API
init_jwt(app)
app.register_blueprint(api_bp)

# Configurar carpeta de subidas
UPLOAD_FOLDER = 'src/data/uploads'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'flac', 'mp4', 'webm'}
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB tamaño máximo de archivo

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =============================================
# 2. CONFIGURACIÓN DE GOOGLE OAUTH
# =============================================
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

# =============================================
# 3. CONFIGURACIÓN DE LOGIN
# =============================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_cliente_page'
login_manager.session_protection = None  # Desactivar protección de sesión para pruebas

class User(UserMixin):
    def __init__(self, id_, name, email):
        self.id = str(id_)
        self.name = name
        self.email = email

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f'<User {self.email}>'

@login_manager.user_loader
def load_user(user_id):
    # Reconstruir el usuario desde la sesión
    email = session.get('email')
    name = session.get('name', '')
    if email:
        return User(id_=user_id, name=name, email=email)
    return None

# Configuración de sesión en PostgreSQL
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgressql_vd60_user:oUDjiUxscSeoTWlygkNf6SmYTTYcw8T6@dpg-d14719buibrs73e0ch1g-a.virginia-postgres.render.com/postgressql_vd60'
db = SQLAlchemy(app)
app.config['SESSION_SQLALCHEMY'] = db
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
Session(app)

@app.before_request
def make_session_permanent():
    session.permanent = True
    print('Sesión actual:', dict(session))
    if current_user.is_authenticated:
        print('Usuario autenticado en before_request:', current_user)
        print('ID del usuario:', current_user.get_id())

@app.route('/login-cliente')
def login_cliente_page():
    print('Entrando a login_cliente_page')
    print('Usuario actual:', current_user)
    print('¿Está autenticado?:', current_user.is_authenticated)
    print('Sesión actual:', dict(session))
    
    if current_user.is_authenticated:
        print('Usuario autenticado, redirigiendo a /cliente')
        return redirect(url_for('cliente'))
    
    next_page = request.args.get('next')
    if next_page:
        session['next'] = next_page
        print('Guardando página siguiente:', next_page)
    
    print('Usuario no autenticado, mostrando página de login')
    return render_template('login_cliente.html')

@app.route('/login-cliente/google')
def login_cliente_google():
    print('Iniciando login con Google')
    session['tipo_login'] = 'cliente'
    redirect_uri = url_for('auth_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth_callback():
    print('Callback de autenticación iniciado')
    token = google.authorize_access_token()
    userinfo = token['userinfo']
    print('Información del usuario recibida:', userinfo)
    
    user_id = str(userinfo['sub'])
    user = User(
        id_=user_id,
        name=userinfo.get('name', ''),
        email=userinfo['email']
    )
    
    # Iniciar sesión
    login_user(user, remember=True, duration=timedelta(days=1))
    
    # Guardar información en la sesión
    session['email'] = user.email
    session['user_id'] = user_id
    session['name'] = user.name
    session['authenticated'] = True
    
    print('Usuario autenticado después de login_user:', current_user.is_authenticated)
    print('ID del usuario actual:', current_user.get_id())
    print('Sesión después de login:', dict(session))
    
    # Redirigir a la página siguiente o a /cliente
    next_page = session.pop('next', None)
    if next_page:
        print('Redirigiendo a página siguiente:', next_page)
        return redirect(next_page)
    
    print('Redirigiendo a /cliente')
    return redirect(url_for('cliente'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('index'))

# =============================================
# 7. ENDPOINT DE HEALTH CHECK
# =============================================
@app.route('/health')
def health_check():
    return jsonify({
        "status": "saludable",
        "version": "1.0.0",
        "servicio": "analizador-presentaciones"
    })

# =============================================
# 8. RUTAS DE ANÁLISIS Y ARCHIVOS
# =============================================
@app.route('/analyze', methods=['POST'])
@login_required
def analyze():
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    if not file:
        return jsonify({'error': 'Archivo inválido'}), 400

    # Crear carpeta para el usuario si no existe
    folder_prefix = f"{current_user.email}/"
    try:
        # Guardar el archivo en Azure Blob Storage
        filename = secure_filename(file.filename)
        blob_name = folder_prefix + filename
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
            file.save(tmp.name)
            with open(tmp.name, "rb") as data:
                blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=blob_name)
                blob_client.upload_blob(data, overwrite=True)

        # Transcribir el video
        audio_wav = tmp.name + '.wav'
        subprocess.run([
            'ffmpeg', '-y', '-i', tmp.name, '-vn', '-filter:a', 'atempo=2.0', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_wav
        ], check=True)
        transcriber = AzureTranscriber(
            speech_key=os.environ.get('AZURE_SPEECH_KEY'),
            service_region=os.environ.get('AZURE_SPEECH_REGION', 'eastus')
        )
        result = transcriber.transcribe(audio_wav)
        transcript = result['text'] if isinstance(result, dict) and 'text' in result else str(result)
        print('TRANSCRIPCIÓN COMPLETA:', transcript)

        # Calificación automática simple (puedes mejorar la rúbrica después)
        score = 1
        texto = transcript.lower()
        if any(pal in texto for pal in ['empresa', 'negocio', 'compañía']): score += 2
        if any(pal in texto for pal in ['servicio', 'producto', 'ofrecemos', 'vendemos']): score += 2
        if any(pal in texto for pal in ['mision', 'visión', 'valores']): score += 2
        if len(transcript.split()) > 30: score += 2
        if score > 10: score = 10

        # Guardar transcripción y score como JSON
        import json
        from io import BytesIO
        presentacion_json = BytesIO(json.dumps({"score": score, "transcripcion": transcript}, ensure_ascii=False, indent=2).encode('utf-8'))
        presentacion_json_blob = folder_prefix + 'presentacion.json'
        print(f"Intentando guardar {presentacion_json_blob} en Azure para {folder_prefix}")
        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=presentacion_json_blob)
        blob_client.upload_blob(presentacion_json, overwrite=True)
        print(f"¡Guardado exitoso de {presentacion_json_blob} en Azure para {folder_prefix}")

        # Analizar el video (aquí va tu lógica de análisis)
        # Por ahora, devolvemos un resultado de ejemplo
        return jsonify({
            'text': transcript,
            'scores': {
                'historia': 8,
                'mision_vision': 7,
                'productos': 9,
                'valores': 8,
                'mercado': 7,
                'logros': 8,
                'overall': 8
            },
            'feedback': [
                'Mencionaste el nombre de la empresa.',
                'Explicaste a qué se dedica.',
                'Hablaste de productos/servicios.',
                'Mencionaste misión, visión o valores.',
                'Hablaste de logros o historia.',
                'Duración adecuada.'
            ],
            'duration': 120
        })
    except Exception as e:
        logger.error(f"Error en /analyze: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================
# 9. RUTAS DE ARCHIVOS
# =============================================
@app.route('/api/mis-archivos')
@login_required
def api_mis_archivos():
    user_folder = os.path.join('user_uploads', current_user.email)
    if not os.path.exists(user_folder):
        return jsonify([])
    archivos = [f for f in os.listdir(user_folder) if os.path.isfile(os.path.join(user_folder, f))]
    return jsonify(archivos)

@app.route('/mis-archivos')
@login_required
def mis_archivos():
    user_folder = os.path.join('user_uploads', current_user.email)
    empresas = {}
    if os.path.exists(user_folder):
        for empresa in os.listdir(user_folder):
            empresa_path = os.path.join(user_folder, empresa)
            if os.path.isdir(empresa_path):
                archivos = [f for f in os.listdir(empresa_path) if os.path.isfile(os.path.join(empresa_path, f))]
                empresas[empresa] = archivos
    return render_template('mis_archivos.html', empresas=empresas)

@app.route('/descargar/<rfc>/<filename>')
def descargar_archivo(rfc, filename):
    try:
        from azure.storage.blob import BlobServiceClient
        import io
        azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
        azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
        azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        blob_name = f"{rfc}/{filename}"
        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=blob_name)
        blob_data = blob_client.download_blob().readall()
        return send_file(
            io.BytesIO(blob_data),
            download_name=filename,
            as_attachment=False,
            mimetype='video/webm' if filename.endswith('.webm') else None
        )
    except Exception as e:
        logger.error(f"Error descargando archivo de Azure: {e}")
        return "Archivo no encontrado", 404



# ==========(no se necesitan ahorita) ==========
# @app.route('/login-asesor')
# def login_asesor_page():
#     if current_user.is_authenticated and session.get('tipo_login') == 'cliente':
#         return redirect(url_for('cliente'))
#     return render_template('login_asesor.html')

# @app.route('/login-asesor/google')
# def login_asesor_google():
#     session['tipo_login'] = 'asesor'
#     redirect_uri = url_for('auth_callback', _external=True)
#     return google.authorize_redirect(redirect_uri)

# @app.route('/asesor')
# @login_required
# def asesor():
#     if session.get('tipo_login') == 'cliente':
#         return redirect(url_for('cliente'))
#     if not session.get('empresa'):
#         return redirect(url_for('empresa'))
#     return render_template('asesor.html')

# @app.route('/empresa', methods=['GET', 'POST'])
# @login_required
# def empresa():
#     if request.method == 'POST':
#         nombre_empresa = request.form.get('empresa', '').strip()
#         if not nombre_empresa:
#             return render_template('empresa.html', error='Por favor ingresa el nombre de la empresa')
#         session['empresa'] = nombre_empresa
#         return redirect(url_for('asesor'))
#     return render_template('empresa.html')

@app.route('/cliente')
@login_required
def cliente():
    print('Entrando a /cliente')
    print('Usuario actual:', current_user)
    print('¿Está autenticado?:', current_user.is_authenticated)
    print('Sesión actual:', dict(session))
    # Siempre mostrar el wizard de 5 pasos
    return render_template('cliente.html', rfc=session.get('rfc'))

# --- Lógica de Azure Video Indexer ---
VIDEO_INDEXER_SUBSCRIPTION_KEY = os.getenv("VIDEO_INDEXER_SUBSCRIPTION_KEY")
VIDEO_INDEXER_ACCOUNT_ID = os.getenv("VIDEO_INDEXER_ACCOUNT_ID")
VIDEO_INDEXER_LOCATION = os.getenv("VIDEO_INDEXER_LOCATION", 'trial') # 'trial' es un buen default

BASE_AUTH_URL = f"https://api.videoindexer.ai/Auth/{VIDEO_INDEXER_LOCATION}/Accounts/{VIDEO_INDEXER_ACCOUNT_ID}"
BASE_API_URL = f"https://api.videoindexer.ai/{VIDEO_INDEXER_LOCATION}/Accounts/{VIDEO_INDEXER_ACCOUNT_ID}"

def get_video_indexer_access_token():
    """Obtiene un token de acceso para la API de Video Indexer."""
    if not all([VIDEO_INDEXER_SUBSCRIPTION_KEY, VIDEO_INDEXER_ACCOUNT_ID]):
        logger.error("Faltan las variables de entorno de Video Indexer.")
        return None
    try:
        response = requests.get(
            f"{BASE_AUTH_URL}/AccessToken?allowEdit=true",
            headers={'Ocp-Apim-Subscription-Key': VIDEO_INDEXER_SUBSCRIPTION_KEY}
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"Error obteniendo access token de Video Indexer: {e}")
        return None

def indexar_workspace_en_azure(video_url, video_name):
    try:
        if not all([VIDEO_INDEXER_SUBSCRIPTION_KEY, VIDEO_INDEXER_ACCOUNT_ID]):
             logger.warning("Video Indexer no configurado, omitiendo indexación de workspace.")
             return None

        access_token = get_video_indexer_access_token()
        if not access_token:
            return None # El error ya fue loggeado en la función de token

        params = {
            'name': video_name,
            'videoUrl': video_url,
            'privacy': 'Private',
            'indexingPreset': 'Advanced',
            'language': 'es-ES'
        }
        upload_response = requests.post(
            f"{BASE_API_URL}/Videos",
            params=params,
            headers={'Authorization': f'Bearer {access_token}'}
        )
        upload_response.raise_for_status()
        response_data = upload_response.json()
        logger.info(f"Video Indexer respondió con: {response_data}")
        return response_data.get('id')

    except Exception as e:
        logger.error(f"Error al indexar workspace en Azure Video Indexer: {e}")
        return None

@app.route('/cliente_upload', methods=['POST'])
@login_required
def cliente_upload():
    print('Entrando a cliente_upload')
    print('Usuario actual:', current_user)
    print('¿Está autenticado?:', current_user.is_authenticated)
    print('Sesión actual:', dict(session))

    # Validar variables de entorno de Azure
    azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
    
    if not azure_account_name or not azure_account_key:
        print('Error: Variables de entorno de Azure Storage no configuradas')
        return jsonify({"error": "Configuración de Azure Storage incompleta"}), 500
    
    try:
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    except Exception as e:
        print(f'Error conectando a Azure Storage: {e}')
        return jsonify({"error": "Error de conexión con Azure Storage"}), 500

    try:
        rfc = session.get('rfc')
        print('RFC en sesión:', rfc)
        if not rfc:
            print('Error: RFC no encontrado en sesión. Sesión completa:', dict(session))
            return jsonify({"error": "No se encontró el RFC en la sesión. Por favor, completa el paso 1 primero."}), 400

        # Procesar el video (aceptar 'video' o 'main_video')
        video = request.files.get('video') or request.files.get('main_video')
        print('Archivos recibidos:', list(request.files.keys()))
        print('Video encontrado:', video is not None)
        if not video:
            return jsonify({"error": "No se envió ningún archivo de video"}), 400
        if video.filename == '':
            return jsonify({"error": "No se seleccionó ningún archivo"}), 400

        filename = secure_filename(video.filename)
        video_blob_name = f"{rfc}/{filename}"
        video_blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=video_blob_name)
        
        try:
            video_blob_client.upload_blob(video, overwrite=True)
            print(f"Video guardado exitosamente en: {video_blob_name}")
        except Exception as e:
            print(f'Error subiendo video a Azure: {e}')
            return jsonify({"error": f"Error al subir el video: {str(e)}"}), 500

        # Si es workspace.webm, extraer frames para análisis AI
        if filename == 'workspace.webm':
            import tempfile
            import subprocess
            frames_dir = tempfile.mkdtemp(prefix='frames_')
            try:
                # Descargar el archivo temporalmente
                with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp_video:
                    video_blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=video_blob_name)
                    video_data = video_blob_client.download_blob()
                    video_data.readinto(tmp_video)
                    tmp_video_path = tmp_video.name
                # Extraer 1 frame cada 2 segundos
                os.makedirs(frames_dir, exist_ok=True)
                cmd = [
                    'ffmpeg', '-i', tmp_video_path,
                    '-vf', 'fps=0.5',
                    os.path.join(frames_dir, 'frame_%03d.jpg')
                ]
                subprocess.run(cmd, check=True)
                print(f"Frames extraídos en: {frames_dir}")
                # Aquí puedes agregar el análisis con OpenAI cuando esté listo
            except Exception as e:
                print(f"Error extrayendo frames de workspace.webm: {e}")

        # Solo procesar y transcribir si el archivo es 'presentacion.webm'
        if filename == 'presentacion.webm':
            # Crear status.json con estado 'processing'
            status_blob = f"{rfc}/status.json"
            status_data = BytesIO(json.dumps({"status": "processing"}, ensure_ascii=False).encode('utf-8'))
            status_blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=status_blob)
            status_blob_client.upload_blob(status_data, overwrite=True)

            # Procesamiento asíncrono en thread
            def procesar_video_async(rfc, filename):
                try:
                    azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
                    azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
                    azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
                    connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
                    blob_service_client = BlobServiceClient.from_connection_string(connect_str)

                    # Descargar el video
                    video_blob_name = f"{rfc}/{filename}"
                    video_blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=video_blob_name)
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
                        video_data = video_blob_client.download_blob()
                        video_data.readinto(tmp)
                        
                        # Extraer audio
                        audio_wav = tmp.name + '.wav'
                        subprocess.run([
                            'ffmpeg', '-y', '-i', tmp.name, '-vn', '-filter:a', 'atempo=2.0', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_wav
                        ], check=True)
                        
                        # Transcribir
                        transcriber = AzureTranscriber(
                            speech_key=os.environ.get('AZURE_SPEECH_KEY'),
                            service_region=os.environ.get('AZURE_SPEECH_REGION', 'eastus')
                        )
                        result = transcriber.transcribe(audio_wav)
                        transcript = result['text'] if isinstance(result, dict) and 'text' in result else str(result)
                        print('TRANSCRIPCIÓN COMPLETA:', transcript)

                        # Análisis con IA
                        analysis_results = get_ai_analysis(transcript)

                        if not analysis_results:
                            raise Exception("El análisis con IA falló y no devolvió resultados.")

                        analysis_results["transcripcion"] = transcript

                        # Subir presentacion.json
                        results_json = BytesIO(json.dumps(analysis_results, ensure_ascii=False, indent=2).encode('utf-8'))
                        presentacion_json_blob = f"{rfc}/presentacion.json"
                        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=presentacion_json_blob)
                        blob_client.upload_blob(results_json, overwrite=True)

                        # Actualizar status.json
                        status_data = BytesIO(json.dumps({"status": "done"}, ensure_ascii=False).encode('utf-8'))
                        status_blob = f"{rfc}/status.json"
                        status_blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=status_blob)
                        status_blob_client.upload_blob(status_data, overwrite=True)

                except Exception as e:
                    logger.error(f"Error en procesar_video_async: {e}")
                    error_data = BytesIO(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False).encode('utf-8'))
                    status_blob = f"{rfc}/status.json"
                    status_blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=status_blob)
                    status_blob_client.upload_blob(error_data, overwrite=True)

            thread = threading.Thread(target=procesar_video_async, args=(rfc, filename))
            thread.start()
            return jsonify({"success": True, "message": "Video subido correctamente. El análisis estará listo en unos minutos."})
        else:
            # Si no es presentacion.webm, solo se sube el video sin procesar
            return jsonify({"success": True, "message": "Video subido correctamente."})

    except Exception as e:
        print('Error en cliente_upload:', str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/cliente_datos', methods=['POST'])
@login_required
def cliente_datos():
    print('Entrando a cliente_datos')
    print('Usuario actual:', current_user)
    print('¿Está autenticado?:', current_user.is_authenticated)
    print('Sesión actual antes de guardar:', dict(session))
    try:
        azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
        azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
        azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)

        datos = request.get_json()
        print('Datos recibidos:', datos)
        rfc = datos.get('rfc')
        if not rfc:
            return jsonify({"error": "El RFC es obligatorio"}), 400
        
        # Guardar RFC en la sesión
        session['rfc'] = rfc
        session.modified = True  # Forzar la persistencia de la sesión
        print('RFC guardado en sesión:', rfc)
        print('Sesión después de guardar RFC:', dict(session))
        
        # Guardar datos.json en la carpeta del RFC (sobrescribir con toda la info final)
        folder_prefix = f"{rfc}/"
        blob_name = folder_prefix + 'datos.json'
        # No es necesario cambiar nada más, los nuevos campos ya llegan en datos
        datos_bytes = BytesIO(json.dumps(datos, ensure_ascii=False, indent=2).encode('utf-8'))
        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=blob_name)
        blob_client.upload_blob(datos_bytes, overwrite=True)
        print(f"datos.json actualizado en carpeta RFC: {blob_name}")
        return jsonify({"success": True})
    except Exception as e:
        print('Excepción en cliente_datos:', e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/cliente/upload', methods=['POST'])
def api_cliente_upload():
    from azure.storage.blob import BlobServiceClient
    azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
    connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    # Verificar API key
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != os.environ.get('API_KEY'):
        return jsonify({'error': 'API key inválida'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    if not file:
        return jsonify({'error': 'Archivo inválido'}), 400

    # Verificar RFC
    rfc = request.form.get('rfc')
    if not rfc:
        return jsonify({'error': 'El RFC es obligatorio'}), 400

    folder_prefix = f"{rfc}/"
    try:
        # Guardar el archivo en Azure Blob Storage
        filename = secure_filename(file.filename)
        blob_name = folder_prefix + filename
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
            file.save(tmp.name)
            with open(tmp.name, "rb") as data:
                blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=blob_name)
                blob_client.upload_blob(data, overwrite=True)

        # Transcribir el video
        audio_wav = tmp.name + '.wav'
        subprocess.run([
            'ffmpeg', '-y', '-i', tmp.name, '-vn', '-filter:a', 'atempo=2.0', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_wav
        ], check=True)
        transcriber = AzureTranscriber(
            speech_key=os.environ.get('AZURE_SPEECH_KEY'),
            service_region=os.environ.get('AZURE_SPEECH_REGION', 'eastus')
        )
        result = transcriber.transcribe(audio_wav)
        transcript = result['text'] if isinstance(result, dict) and 'text' in result else str(result)
        print('TRANSCRIPCIÓN COMPLETA:', transcript)

        # Análisis con IA (GPT)
        analysis_results = get_ai_analysis(transcript)
        analysis_results["transcripcion"] = transcript

        # Guardar análisis como JSON
        presentacion_json = BytesIO(json.dumps(analysis_results, ensure_ascii=False, indent=2).encode('utf-8'))
        presentacion_json_blob = folder_prefix + 'presentacion.json'
        print(f"Intentando guardar {presentacion_json_blob} en Azure para {folder_prefix}")
        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=presentacion_json_blob)
        blob_client.upload_blob(presentacion_json, overwrite=True)
        print(f"¡Guardado exitoso de {presentacion_json_blob} en Azure para {folder_prefix}")

        return jsonify(analysis_results)
    except Exception as e:
        logger.error(f"Error en /api/cliente/upload: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cliente/analysis/<rfc>', methods=['GET'])
def api_cliente_analysis(rfc):
    from azure.storage.blob import BlobServiceClient
    azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
    connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    # Verificar API key
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != os.environ.get('API_KEY'):
        return jsonify({'error': 'API key inválida'}), 401

    try:
        folder_prefix = f"{rfc}/"
        presentacion_json_blob = folder_prefix + 'presentacion.json'
        print(f"Intentando leer {presentacion_json_blob} del contenedor {azure_container_name}")
        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=presentacion_json_blob)
        try:
            presentacion_json = blob_client.download_blob().readall()
            print("Contenido recibido del blob:", presentacion_json)
            presentacion_data = json.loads(presentacion_json.decode("utf-8"))
            # Leer datos.json
            datos_blob_name = folder_prefix + 'datos.json'
            datos_blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=datos_blob_name)
            try:
                datos_json = datos_blob_client.download_blob().readall()
                datos_data = json.loads(datos_json.decode("utf-8"))
            except Exception as e:
                print("No se encontró datos.json o error al leerlo:", e)
                datos_data = None
            # Combinar y devolver
            presentacion_data['datos'] = datos_data
            return jsonify(presentacion_data)
        except Exception as e:
            print("Error al decodificar o cargar el JSON:", e)
            return jsonify({'error': 'No se encontró el análisis para este RFC'}), 404
    except Exception as e:
        logger.error(f"Error en /api/cliente/analysis/{rfc}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cliente/me', methods=['GET'])
@login_required
def api_cliente_me():
    return jsonify({
        'id': current_user.get_id(),
        'name': current_user.name,
        'email': current_user.email
    })

@app.route('/api/cliente/status/<rfc>', methods=['GET'])
def api_cliente_status(rfc):
    from azure.storage.blob import BlobServiceClient
    azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
    connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    status_blob = f"{rfc}/status.json"
    try:
        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=status_blob)
        status_json = blob_client.download_blob().readall()
        import json
        status_data = json.loads(status_json.decode("utf-8"))
        return jsonify(status_data)
    except Exception as e:
        return jsonify({"status": "not_found", "error": str(e)})

@app.route('/debug_session')
@login_required
def debug_session():
    """Endpoint para debug de la sesión"""
    return jsonify({
        'session_data': dict(session),
        'user_id': current_user.get_id() if current_user.is_authenticated else None,
        'rfc_in_session': session.get('rfc'),
        'authenticated': current_user.is_authenticated
    })

@app.route('/cliente_status')
@login_required
def cliente_status():
    try:
        rfc = request.args.get('rfc')
        if not rfc:
            return jsonify({"error": "RFC no proporcionado"}), 400

        azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
        azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
        azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)

        # Verificar si existe el archivo de resultados
        results_blob = f"{rfc}/resultados_video_final.webm.json"
        try:
            blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=results_blob)
            blob_client.get_blob_properties()
            return jsonify({"status": "done"})
        except Exception as e:
            # Verificar si hay error
            error_blob = f"{rfc}/error_video_final.webm.json"
            try:
                blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=error_blob)
                blob_client.get_blob_properties()
                error_data = json.loads(blob_client.download_blob().readall().decode('utf-8'))
                return jsonify({"status": "error", "error": error_data.get('error', 'Error desconocido')})
            except Exception:
                # Si no hay ni resultados ni error, está en proceso
                return jsonify({"status": "processing"})

    except Exception as e:
        logger.error(f"Error en cliente_status: {e}")
        return jsonify({"error": str(e)}), 500

# Configurar API_KEY en Render
os.environ['API_KEY'] = 'la_clave_secreta_de_kiko'

# Configuración JWT
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', app.secret_key)
jwt = JWTManager(app)

# Endpoint para obtener un JWT tras login exitoso
@app.route('/api/token', methods=['POST'])
def api_token():
    # Espera un email en el body (en producción deberías validar con OAuth o password)
    data = request.get_json()
    email = data.get('email')
    name = data.get('name', '')
    user_id = data.get('user_id', '')
    if not email:
        return jsonify({'msg': 'Email requerido'}), 400
    # Aquí podrías validar el usuario contra tu base de datos
    access_token = create_access_token(identity={
        'user_id': user_id,
        'email': email,
        'name': name
    })
    return jsonify(access_token=access_token)

# Ejemplo de endpoint protegido con JWT
@app.route('/api/cliente/me-jwt', methods=['GET'])
@jwt_required()
def api_cliente_me_jwt():
    identity = get_jwt_identity()
    return jsonify(identity)

@app.route('/')
def index():
    print('Entrando a /')
    if current_user.is_authenticated:
        print('Usuario autenticado en /')
        print('RFC en sesión:', session.get('rfc'))
        return redirect(url_for('cliente'))
    return redirect(url_for('login_cliente_page'))

def get_ai_analysis(transcript):
    if not transcript or not transcript.strip():
        logger.warning("La transcripción llegó vacía. Devolviendo análisis por defecto de 'sin audio'.")
        return {
            "score": 0,
            "scores": {
                "claridad_mision": 0,
                "comprension_problema": 0,
                "conocimiento_mercado": 0,
                "solidez_producto": 0
            },
            "feedback": {
                "claridad_mision": "No se detectó audio o la transcripción está vacía.",
                "comprension_problema": "No se detectó audio o la transcripción está vacía.",
                "conocimiento_mercado": "No se detectó audio o la transcripción está vacía.",
                "solidez_producto": "No se detectó audio o la transcripción está vacía."
            },
            "resumen_general": "No se pudo realizar el análisis porque no se detectó audio en la presentación."
        }

    try:
        logger.info(f"Iniciando análisis de IA con el modelo: gpt-4o-mini")
        logger.info(f"Transcripción enviada a OpenAI: {transcript}")
        client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            http_client=httpx.Client(proxies="") # Solución para el error de proxy en Render
        )
        
        system_prompt = """
        Eres un analista de negocios experto de Crediclub. Tu tarea es evaluar la presentación de un emprendedor que busca financiamiento.
        Analiza la transcripción proporcionada y califica de 0 a 10 los siguientes cuatro criterios. Sé estricto y objetivo.
        Además de la calificación numérica, proporciona una justificación breve y constructiva para cada criterio.
        Finalmente, calcula un score general promediando las cuatro calificaciones.

        CRITERIOS DE EVALUACIÓN:
        1.  **Claridad de la Misión y Visión (claridad_mision):** ¿El emprendedor explica claramente el propósito y las metas a largo plazo de su empresa? No basta con mencionar las palabras "misión" o "visión".
        2.  **Comprensión del Problema (comprension_problema):** ¿Describe de forma convincente el problema que su negocio resuelve para los clientes?
        3.  **Conocimiento del Mercado (conocimiento_mercado):** ¿Demuestra entender quiénes son sus clientes, su tamaño de mercado y quién es su competencia?
        4.  **Solidez del Producto/Servicio (solidez_producto):** ¿La descripción de lo que ofrece es clara, concreta y atractiva?

        La transcripción del usuario es:
        "{transcript}"

        Devuelve tu análisis únicamente en formato JSON, sin texto adicional antes o después. La estructura debe ser la siguiente:
        {{
          "scores": {{
            "claridad_mision": <calificación_numerica>,
            "comprension_problema": <calificación_numerica>,
            "conocimiento_mercado": <calificación_numerica>,
            "solidez_producto": <calificación_numerica>
          }},
          "feedback": {{
            "claridad_mision": "<justificación>",
            "comprension_problema": "<justificación>",
            "conocimiento_mercado": "<justificación>",
            "solidez_producto": "<justificación>"
          }}
        }}
        """

        logger.info("Llamando a OpenAI...")
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt.format(transcript=transcript)}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            raw_content = response.choices[0].message.content
            logger.info(f"Respuesta cruda de OpenAI: {raw_content}")
        except Exception as e:
            logger.error(f"Excepción al llamar a OpenAI: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Si la respuesta tiene algún contenido, loguéalo
            try:
                logger.error(f"Respuesta de OpenAI (objeto): {response}")
            except Exception:
                logger.error("No se pudo acceder al objeto de respuesta de OpenAI.")
            raise  # Re-lanzar la excepción para que el flujo de error siga igual
        try:
            # Intentar encontrar y parsear el JSON de la respuesta
            json_start = raw_content.find('{')
            json_end = raw_content.rfind('}')
            if json_start != -1 and json_end != -1:
                json_string = raw_content[json_start:json_end+1]
                analysis_data = json.loads(json_string)
            else:
                raise ValueError("No se encontró un objeto JSON válido en la respuesta.")
        except (json.JSONDecodeError, ValueError) as json_error:
            logger.error(f"Error al parsear JSON de OpenAI. Error: {json_error}")
            logger.error(f"Respuesta completa de OpenAI: {raw_content}")
            # Intentar limpiar la respuesta y parsear de nuevo
            try:
                # Eliminar posibles bloques de código markdown y texto extra
                cleaned_content = raw_content
                # Quitar bloque ```json ... ```
                if '```json' in cleaned_content:
                    start = cleaned_content.find('```json') + 7
                    end = cleaned_content.find('```', start)
                    if end != -1:
                        cleaned_content = cleaned_content[start:end]
                elif '```' in cleaned_content:
                    start = cleaned_content.find('```') + 3
                    end = cleaned_content.find('```', start)
                    if end != -1:
                        cleaned_content = cleaned_content[start:end]
                # Quitar líneas antes del primer '{' y después del último '}'
                json_start = cleaned_content.find('{')
                json_end = cleaned_content.rfind('}')
                if json_start != -1 and json_end != -1:
                    cleaned_content = cleaned_content[json_start:json_end+1]
                cleaned_content = cleaned_content.strip()
                logger.info(f"Intentando parsear contenido limpio: {cleaned_content}")
                analysis_data = json.loads(cleaned_content)
                logger.info("JSON parseado exitosamente después de limpieza")
            except (json.JSONDecodeError, ValueError) as second_error:
                logger.error(f"Error en segundo intento de parsing: {second_error}")
                logger.error(f"Contenido limpio: {cleaned_content}")
                raise # Re-lanzar la excepción para que sea capturada por el bloque superior
        # Calcular score promedio y añadir resumen
        scores = analysis_data.get("scores", {})
        total_score = sum(scores.values())
        num_scores = len(scores)
        average_score = round(total_score / num_scores, 1) if num_scores > 0 else 0
        analysis_data["score"] = average_score
        resumen_parts = [f"- {key.replace('_', ' ').title()}: {value}" for key, value in analysis_data.get("feedback", {}).items()]
        analysis_data["resumen_general"] = "\n".join(resumen_parts)
        logger.info(f"Análisis IA final: {analysis_data}")
        return analysis_data
    except Exception as e:
        logger.error(f"Error en el análisis con OpenAI: {e}")
        return None

@app.route('/cliente_score', methods=['GET'])
def cliente_score():
    try:
        # Obtener el RFC del usuario actual
        user_email = getattr(current_user, 'email', None) or session.get('email', 'default')
        rfc = session.get('rfc')
        
        if not rfc:
            return jsonify({"error": "RFC no encontrado"}), 404

        # Obtener presentacion.json
        azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
        azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
        azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)

        presentacion_blob = f"{rfc}/presentacion.json"
        try:
            blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=presentacion_blob)
            presentacion_json = blob_client.download_blob().readall()
            presentacion_data = json.loads(presentacion_json.decode("utf-8"))
            
            score = presentacion_data.get('score', 0)
            mensaje = ""
            
            if score >= 8:
                mensaje = "¡Felicidades! Tu presentación fue excelente y demuestra un profundo conocimiento de tu negocio. Nuestro equipo se pondrá en contacto contigo muy pronto para discutir las excelentes oportunidades de colaboración."
            elif score >= 6:
                mensaje = "¡Muy buena presentación! Tienes una base sólida y comunicas bien tus ideas. Pronto te contactaremos para explorar con más detalle las posibilidades de colaboración."
            elif score >= 4:
                mensaje = "Gracias por tu presentación. Se notan los fundamentos de tu idea de negocio. Hemos identificado algunas áreas que se pueden fortalecer y te contactaremos para platicar sobre cómo podemos apoyarte."
            else:
                mensaje = "Gracias por tu presentación. Para poder evaluar mejor tu propuesta, te recomendamos estructurar con más claridad tus ideas sobre el problema que resuelves y tu mercado. Nuestro equipo se pondrá en contacto contigo."

            return jsonify({
                "score": score,
                "mensaje": mensaje,
                "detalles": presentacion_data.get('feedback', {}),
                "scores": presentacion_data.get('scores', {})
            })
        except Exception as e:
            logger.error(f"Error obteniendo presentacion.json: {e}")
            return jsonify({
                "error": "No se pudo procesar tu presentación. Por favor, intenta nuevamente."
            }), 500

    except Exception as e:
        logger.error(f"Error en cliente_score: {e}")
        return jsonify({"error": str(e)}), 500

def evaluar_workspace_visual(insights_json):
    score = 0
    feedback = []
    insights = insights_json.get('videos', [{}])[0].get('insights', {})

    # --- GENTE ---
    faces = insights.get('faces', [])
    if len(faces) >= 2:
        score += 2
        feedback.append("Se detectan al menos 2 personas en el workspace.")
    elif len(faces) == 1:
        score += 1
        feedback.append("Se detecta una persona en el workspace.")

    # --- PRODUCTIVIDAD ---
    objetos = set(obj.get('objectType', '').lower() for obj in insights.get('objects', []))
    if 'computer' in objetos or 'laptop' in objetos or 'desk' in objetos or 'whiteboard' in objetos:
        score += 2
        feedback.append("Se detectan objetos asociados a productividad (computadora, escritorio, pizarrón, etc.).")

    # --- LIMPIEZA ---
    # No se puede inferir directamente, pero si hay pocos objetos y el escritorio está despejado, se puede asumir orden
    if 'desk' in objetos and len(objetos) <= 5:
        score += 1
        feedback.append("El espacio parece ordenado (pocos objetos detectados en el escritorio).")

    # --- TIPO DE INMUEBLE ---
    tipo_inmueble = "No identificado"
    if 'desk' in objetos or 'computer' in objetos or 'laptop' in objetos:
        tipo_inmueble = "Oficina en edificio corporativo u oficina en casa"
    elif 'whiteboard' in objetos:
        tipo_inmueble = "Espacio de Co-working o sala de juntas"
    elif 'shelf' in objetos or 'box' in objetos:
        tipo_inmueble = "Bodega o nave industrial"
    elif 'counter' in objetos or 'cash register' in objetos:
        tipo_inmueble = "Local comercial a pie de calle"
    else:
        tipo_inmueble = "Otro (no identificado automáticamente)"
    feedback.append(f"Tipo de inmueble detectado: {tipo_inmueble}")

    return score, feedback, tipo_inmueble

@app.route('/api/video-insights/<video_id>', methods=['GET'])
def get_video_insights(video_id):
    try:
        access_token = get_access_token()
        insights_response = requests.get(
            f"{BASE_API_URL}/Videos/{video_id}/Index",
            params={
                'accessToken': access_token,
                'language': 'es-ES',
                'includeBreakdowns': 'true',
                'includeSpeechTranscript': 'true',
                'includeFace': 'true',
                'includeKeywords': 'true',
                'includeSentiment': 'true',
                'includeTextualContent': 'true',
                'includeTopics': 'true',
                'includeSpeakers': 'true',
            }
        )
        insights_response.raise_for_status()
        insights_data = insights_response.json()
        
        # Evaluar el workspace basado en la rúbrica visual
        score, feedback, tipo_inmueble = evaluar_workspace_visual(insights_data)
        
        # Añadir el score y feedback al resultado
        insights_data['workspace_score'] = score
        insights_data['workspace_feedback'] = feedback
        insights_data['tipo_inmueble'] = tipo_inmueble
        
        # Guardar el resultado en un archivo JSON en Azure Blob Storage
        workspace_json = BytesIO(json.dumps(insights_data, ensure_ascii=False, indent=2).encode('utf-8'))
        workspace_json_blob = f"{video_id}/workspace.json"
        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=workspace_json_blob)
        blob_client.upload_blob(workspace_json, overwrite=True)
        
        return jsonify(insights_data)
    except Exception as e:
        print(f"Error obteniendo insights: {e}")
        return jsonify({"error": f"No se pudo obtener insights: {e}"}), 500

@app.route('/cliente_upload_chunk', methods=['POST'])
def cliente_upload_chunk():
    try:
        # Obtener información del chunk
        chunk_number = int(request.form.get('chunk_number'))
        total_chunks = int(request.form.get('total_chunks'))
        file_id = request.form.get('file_id')
        rfc = request.form.get('rfc')
        
        if not all([chunk_number, total_chunks, file_id, rfc]):
            return jsonify({"error": "Faltan parámetros requeridos"}), 400

        # Configurar Azure Blob Storage
        azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
        azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
        azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)

        # Guardar el chunk en un archivo temporal
        chunk = request.files.get('chunk')
        if not chunk:
            return jsonify({"error": "No se recibió el chunk"}), 400

        temp_dir = f"temp_chunks/{file_id}"
        os.makedirs(temp_dir, exist_ok=True)
        chunk_path = f"{temp_dir}/chunk_{chunk_number}"
        
        chunk.save(chunk_path)

        # Si es el último chunk, unir todos los chunks y procesar
        if chunk_number == total_chunks - 1:
            final_path = f"{temp_dir}/final_video.webm"
            with open(final_path, 'wb') as final_file:
                for i in range(total_chunks):
                    chunk_file_path = f"{temp_dir}/chunk_{i}"
                    with open(chunk_file_path, 'rb') as chunk_file:
                        final_file.write(chunk_file.read())

            # Subir el video completo a Azure
            video_blob_name = f"{rfc}/video_final.webm"
            video_blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=video_blob_name)
            
            with open(final_path, 'rb') as final_video:
                video_blob_client.upload_blob(final_video, overwrite=True)

            # Iniciar procesamiento asíncrono
            thread = threading.Thread(target=procesar_video_async, args=(rfc, "video_final.webm"))
            thread.start()

            # Limpiar archivos temporales
            import shutil
            shutil.rmtree(temp_dir)

            return jsonify({
                "success": True,
                "message": "Video subido y procesamiento iniciado",
                "video_id": file_id
            })
        
        return jsonify({
            "success": True,
            "message": f"Chunk {chunk_number + 1} de {total_chunks} recibido"
        })

    except Exception as e:
        logger.error(f"Error en cliente_upload_chunk: {e}")
        return jsonify({"error": str(e)}), 500

#==============================================
# ASESOR
#==============================================
@app.route('/asesor', methods=['GET', 'POST'])
def asesor_dashboard():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == 'crediclub2025':  # Contraseña simple
            session['asesor_authenticated'] = True
            return redirect('/asesor')
        else:
            return render_template('asesor.html', error='Contraseña incorrecta')
    
    # Si ya está autenticado, mostrar dashboard
    if session.get('asesor_authenticated'):
        try:
            # Obtener todos los candidatos desde Azure
            azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
            azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
            azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
            connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
            blob_service_client = BlobServiceClient.from_connection_string(connect_str)
            
            # Listar todos los blobs (carpetas RFC)
            container_client = blob_service_client.get_container_client(azure_container_name)
            blobs = container_client.list_blobs()
            
            candidatos = []
            for blob in blobs:
                if blob.name.endswith('/datos.json'):
                    rfc = blob.name.split('/')[0]
                    try:
                        # Obtener datos del candidato
                        datos_blob = blob_service_client.get_blob_client(container=azure_container_name, blob=blob.name)
                        datos_json = datos_blob.download_blob().readall()
                        datos = json.loads(datos_json.decode("utf-8"))
                        
                        # Obtener análisis si existe
                        presentacion_blob = f"{rfc}/presentacion.json"
                        try:
                            presentacion_client = blob_service_client.get_blob_client(container=azure_container_name, blob=presentacion_blob)
                            presentacion_json = presentacion_client.download_blob().readall()
                            presentacion = json.loads(presentacion_json.decode("utf-8"))
                            score = presentacion.get('score', 0)
                        except:
                            score = 0
                        
                        candidatos.append({
                            'rfc': rfc,
                            'nombre': datos.get('nombreCompleto', 'N/A'),
                            'empresa': datos.get('nombreEmpresa', 'N/A'),
                            'telefono': datos.get('telefono', 'N/A'),
                            'score': score,
                            'fecha': blob.last_modified.strftime('%d/%m/%Y %H:%M') if blob.last_modified else 'N/A'
                        })
                    except Exception as e:
                        logger.error(f"Error procesando candidato {rfc}: {e}")
                        continue
            
            # Ordenar por fecha (más recientes primero)
            candidatos.sort(key=lambda x: x['fecha'], reverse=True)
            
            return render_template('asesor.html', candidatos=candidatos, authenticated=True)
            
        except Exception as e:
            logger.error(f"Error en dashboard asesor: {e}")
            return render_template('asesor.html', error='Error al cargar los datos', authenticated=True)
    
    # Mostrar formulario de login
    return render_template('asesor.html', authenticated=False)

@app.route('/asesor/logout')
def asesor_logout():
    session.pop('asesor_authenticated', None)
    return redirect('/asesor')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    # Configuración para permitir archivos grandes y tiempos de espera más largos
    app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300  # 5 minutos
    app.run(host='0.0.0.0', port=port) 