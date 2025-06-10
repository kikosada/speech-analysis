# =============================================
# 1. IMPORTS Y CONFIGURACIÓN INICIAL
# =============================================
from flask import Flask, jsonify, request, render_template, redirect, url_for, session, send_from_directory
import os
from app.transcribe import AssemblyAITranscriber as Transcriber
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
from app.azure_transcriber import AzureTranscriber
import subprocess
import json
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_session import Session
from sqlalchemy import create_engine
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__,
    template_folder='../templates',
    static_folder='../static'
)
app.secret_key = os.environ.get("SECRET_KEY", "supersecret")
oauth = OAuth(app)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    session.permanent = False
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
            'ffmpeg', '-y', '-i', tmp.name, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_wav
        ], check=True)
        transcriber = AzureTranscriber(
            speech_key=os.environ.get('AZURE_SPEECH_KEY'),
            service_region=os.environ.get('AZURE_SPEECH_REGION', 'eastus')
        )
        result = transcriber.transcribe(audio_wav)
        transcript = result['text'] if isinstance(result, dict) and 'text' in result else str(result)

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

@app.route('/descargar/<empresa>/<filename>')
@login_required
def descargar_archivo(empresa, filename):
    user_folder = os.path.join('user_uploads', current_user.email)
    empresa_path = os.path.join(user_folder, secure_filename(empresa))
    # Seguridad: solo permite descargar archivos de tu carpeta
    file_path = os.path.join(empresa_path, filename)
    if not os.path.exists(file_path):
        return "Archivo no encontrado", 404
    return send_from_directory(empresa_path, filename, as_attachment=True)

# =============================================
# 10. RUTAS DE ASESOR Y CLIENTE
# =============================================


# ========== RUTAS Y LÓGICA DE ASESOR (no se necesitan ahorita) ==========
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
    return render_template('cliente.html')

@app.route('/cliente_upload', methods=['POST'])
@login_required
def cliente_upload():
    print('Entrando a cliente_upload')
    print('Usuario actual:', current_user)
    print('¿Está autenticado?:', current_user.is_authenticated)
    print('Sesión actual:', dict(session))
    try:
        azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
        azure_account_key = os.environ.get('AZURE_CLIENTE_ACCOUNT_KEY')
        azure_container_name = os.environ.get('AZURE_CLIENTE_CONTAINER', 'clienteai')
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)

        # Obtener el RFC del usuario desde los datos guardados
        user_email = getattr(current_user, 'email', None) or session.get('email', 'default')
        datos_blob_name = f"{user_email}/datos.json"
        datos_blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=datos_blob_name)
        try:
            datos_json = datos_blob_client.download_blob().readall()
            datos_data = json.loads(datos_json.decode("utf-8"))
            rfc = datos_data.get('rfc')
            if not rfc:
                return jsonify({"error": "RFC no encontrado. Por favor, completa tus datos primero."}), 400
        except Exception as e:
            return jsonify({"error": "No se encontraron los datos del usuario. Por favor, completa tus datos primero."}), 400

        folder_prefix = f"{rfc}/"
        uploaded = []
        file = request.files.get('main_video')
        if file:
            filename = secure_filename(file.filename)
            blob_name = folder_prefix + filename
            with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
                file.save(tmp.name)
                with open(tmp.name, "rb") as data:
                    blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=blob_name)
                    blob_client.upload_blob(data, overwrite=True)
            uploaded.append(blob_name)
            # Si es presentacion.webm, transcribe y guarda como .txt
            if filename == 'presentacion.webm':
                try:
                    # Extraer audio a wav
                    audio_wav = tmp.name + '.wav'
                    subprocess.run([
                        'ffmpeg', '-y', '-i', tmp.name, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_wav
                    ], check=True)
                    transcriber = AzureTranscriber(
                        speech_key=os.environ.get('AZURE_SPEECH_KEY'),
                        service_region=os.environ.get('AZURE_SPEECH_REGION', 'eastus')
                    )
                    result = transcriber.transcribe(audio_wav)
                    transcript = result['text'] if isinstance(result, dict) and 'text' in result else str(result)
                    # Calificación automática simple (puedes mejorar la rúbrica después)
                    score = 1
                    texto = transcript.lower()
                    if any(pal in texto for pal in ['empresa', 'negocio', 'compañía']): score += 2
                    if any(pal in texto for pal in ['servicio', 'producto', 'ofrecemos', 'vendemos']): score += 2
                    if any(pal in texto for pal in ['mision', 'visión', 'valores']): score += 2
                    if len(transcript.split()) > 30: score += 2
                    if score > 10: score = 10
                    # Guardar la transcripción como .txt
                    from io import BytesIO
                    transcript_bytes = BytesIO(transcript.encode('utf-8'))
                    transcript_blob = folder_prefix + 'presentacion.txt'
                    blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=transcript_blob)
                    blob_client.upload_blob(transcript_bytes, overwrite=True)
                    # Guardar score y transcripción como .json
                    import json
                    presentacion_json = BytesIO(json.dumps({"score": score, "transcripcion": transcript}, ensure_ascii=False, indent=2).encode('utf-8'))
                    presentacion_json_blob = folder_prefix + 'presentacion.json'
                    blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=presentacion_json_blob)
                    blob_client.upload_blob(presentacion_json, overwrite=True)
                except Exception as e:
                    logger.error(f"Error transcribiendo presentacion.webm: {e}")
        if not uploaded:
            return jsonify({"error": "No se subió ningún video"}), 400
        return jsonify({"success": True, "uploaded": uploaded})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cliente_datos', methods=['POST'])
@login_required
def cliente_datos():
    try:
        azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
        azure_account_key = os.environ.get('AZURE_CLIENTE_ACCOUNT_KEY')
        azure_container_name = os.environ.get('AZURE_CLIENTE_CONTAINER', 'clienteai')
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)

        datos = request.get_json()
        rfc = datos.get('rfc')
        if not rfc:
            return jsonify({"error": "El RFC es obligatorio"}), 400
        
        # Guardar datos.json en la carpeta del RFC
        folder_prefix = f"{rfc}/"
        blob_name = folder_prefix + 'datos.json'
        import json
        from io import BytesIO
        datos_bytes = BytesIO(json.dumps(datos, ensure_ascii=False, indent=2).encode('utf-8'))
        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=blob_name)
        blob_client.upload_blob(datos_bytes, overwrite=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/cliente/upload', methods=['POST'])
def api_cliente_upload():
    from azure.storage.blob import BlobServiceClient
    azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    azure_account_key = os.environ.get('AZURE_CLIENTE_ACCOUNT_KEY')
    azure_container_name = os.environ.get('AZURE_CLIENTE_CONTAINER', 'clienteai')
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
            'ffmpeg', '-y', '-i', tmp.name, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_wav
        ], check=True)
        transcriber = AzureTranscriber(
            speech_key=os.environ.get('AZURE_SPEECH_KEY'),
            service_region=os.environ.get('AZURE_SPEECH_REGION', 'eastus')
        )
        result = transcriber.transcribe(audio_wav)
        transcript = result['text'] if isinstance(result, dict) and 'text' in result else str(result)

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
        logger.error(f"Error en /api/cliente/upload: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cliente/analysis/<rfc>', methods=['GET'])
def api_cliente_analysis(rfc):
    from azure.storage.blob import BlobServiceClient
    azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    azure_account_key = os.environ.get('AZURE_CLIENTE_ACCOUNT_KEY')
    azure_container_name = os.environ.get('AZURE_CLIENTE_CONTAINER', 'clienteai')
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
@login_required
def root_cliente():
    return cliente()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    # Configuración para permitir archivos grandes y tiempos de espera más largos
    app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300  # 5 minutos
    app.run(host='0.0.0.0', port=port) 