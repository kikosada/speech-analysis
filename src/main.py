# =============================================
# VERSIÓN: 2024-06-19 - Actualización de credenciales Azure Storage y Video Indexer
# =============================================
# 1. IMPORTS Y CONFIGURACIÓN INICIAL
# =============================================
from flask import Flask, jsonify, request, render_template, redirect, url_for, session, send_from_directory
import os
from .app.transcribe import AssemblyAITranscriber as Transcriber
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
from .app.azure_transcriber import AzureTranscriber
import subprocess
import json

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
    error_msg = f"Faltan las siguientes variables de entorno requeridas: {', '.join(missing_vars)}"
    logger.error(error_msg)
    raise ValueError(error_msg)

app = Flask(__name__,
    template_folder='templates',
    static_folder='static'
)
app.secret_key = os.environ.get("SECRET_KEY", "supersecret")
oauth = OAuth(app)

# Configurar carpeta de subidas
UPLOAD_FOLDER = 'data/uploads'
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

# =============================================
# 4. FUNCIONES DE UTILIDAD
# =============================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_analysis_result(raw_result):
    """Formatea el resultado del análisis en una estructura más amigable."""
    try:
        return {
            'text': raw_result.get('text', ''),
            'scores': {
                'historia': raw_result.get('scores', {}).get('historia', 0),
                'mision_vision': raw_result.get('scores', {}).get('mision_vision', 0),
                'productos': raw_result.get('scores', {}).get('productos', 0),
                'valores': raw_result.get('scores', {}).get('valores', 0),
                'mercado': raw_result.get('scores', {}).get('mercado', 0),
                'logros': raw_result.get('scores', {}).get('logros', 0),
                'overall': raw_result.get('scores', {}).get('overall', 0)
            },
            'feedback': raw_result.get('feedback', []),
            'duration': raw_result.get('audio_duration', 0)
        }
    except Exception as e:
        logger.error(f"Error al formatear el resultado: {str(e)}")
        return raw_result

def normaliza_empresa(nombre):
    nombre = nombre.strip().lower()
    nombre = ''.join(
        c for c in unicodedata.normalize('NFD', nombre)
        if unicodedata.category(c) != 'Mn'
    )
    return secure_filename(nombre)

# =============================================
# 5. FUNCIONES DE AZURE
# =============================================
def upload_file_to_azure(file_path, blob_name, container_name=None):
    account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    if not container_name:
        container_name = os.environ.get('AZURE_CONTAINER_NAME')
    
    if not all([account_name, account_key, container_name]):
        error_msg = "Faltan variables de entorno de Azure Storage"
        logger.error(f"{error_msg}. account_name: {bool(account_name)}, account_key: {bool(account_key)}, container_name: {bool(container_name)}")
        raise ValueError(error_msg)
    
    logger.info(f"Conectando a Azure Storage. Account: {account_name}, Container: {container_name}")
    connect_str = f"DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net"
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        
        logger.info(f"Archivo '{file_path}' subido exitosamente a Azure como '{blob_name}' en '{container_name}'")
        return True
    except Exception as e:
        logger.error(f"Error subiendo archivo a Azure: {str(e)}")
        raise

def download_file_from_azure(blob_name, local_path, container_name=None):
    account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    if not container_name:
        container_name = os.environ.get('AZURE_CONTAINER_NAME', 'archivos-miapp-kiko')
    connect_str = f"DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net"
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    with open(local_path, "wb") as f:
        data = blob_client.download_blob()
        f.write(data.readall())
    print(f"Archivo descargado de Azure: {blob_name} -> {local_path}")
    return True

def get_azure_blob_sas_url(blob_name, expiration_minutes=60, container_name=None):
    account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    if not container_name:
        container_name = os.environ.get('AZURE_CONTAINER_NAME', 'archivos-miapp-kiko')
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes)
    )
    url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
    return url

# =============================================
# 6. RUTAS DE AUTENTICACIÓN
# =============================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login-asesor')
def login_asesor_page():
    return render_template('login_asesor.html')

@app.route('/login-cliente')
def login_cliente_page():
    return render_template('login_cliente.html')

@app.route('/login-asesor/google')
def login_asesor_google():
    session['tipo_login'] = 'asesor'
    redirect_uri = url_for('auth_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login-cliente/google')
def login_cliente_google():
    session['tipo_login'] = 'cliente'
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
    tipo = session.pop('tipo_login', 'asesor')
    if tipo == 'cliente':
        return redirect(url_for('cliente'))
    else:
        return redirect(url_for('empresa'))

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
# 8. RUTAS DE ANÁLISIS Y ARCHIVOS (RFC OBLIGATORIO)
# =============================================
@app.route('/analyze', methods=['POST'])
@login_required
def analyze():
    rfc = request.form.get('rfc', '').strip().upper()
    if not rfc:
        return jsonify({'error': 'El RFC es obligatorio'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    if not file:
        return jsonify({'error': 'Archivo inválido'}), 400

    folder_prefix = f"{rfc}/"
    try:
        filename = secure_filename(file.filename)
        blob_name = folder_prefix + filename
        azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
        azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
        azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'archivos-miapp-kiko')
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
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

        # Calificación automática simple
        score = 1
        texto = transcript.lower()
        if any(pal in texto for pal in ['empresa', 'negocio', 'compañía']): score += 2
        if any(pal in texto for pal in ['servicio', 'producto', 'ofrecemos', 'vendemos']): score += 2
        if any(pal in texto for pal in ['mision', 'visión', 'valores']): score += 2
        if len(transcript.split()) > 30: score += 2
        if score > 10: score = 10

        # Guardar transcripción y score como JSON
        from io import BytesIO
        presentacion_json = BytesIO(json.dumps({"score": score, "transcripcion": transcript}, ensure_ascii=False, indent=2).encode('utf-8'))
        presentacion_json_blob = folder_prefix + 'presentacion.json'
        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=presentacion_json_blob)
        blob_client.upload_blob(presentacion_json, overwrite=True)

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
    rfc = request.args.get('rfc', '').strip().upper()
    if not rfc:
        return jsonify({'error': 'El RFC es obligatorio'}), 400
    # Aquí deberías listar archivos en Azure bajo el folder del RFC
    return jsonify([])

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
@app.route('/asesor')
@login_required
def asesor():
    if not session.get('empresa'):
        return redirect(url_for('empresa'))
    return render_template('asesor.html')

@app.route('/cliente')
@login_required
def cliente():
    return render_template('cliente.html')

@app.route('/empresa', methods=['GET', 'POST'])
@login_required
def empresa():
    if request.method == 'POST':
        nombre_empresa = request.form.get('empresa', '').strip()
        if not nombre_empresa:
            return render_template('empresa.html', error='Por favor ingresa el nombre de la empresa')
        session['empresa'] = nombre_empresa
        return redirect(url_for('asesor'))
    return render_template('empresa.html')

@app.route('/cliente_upload', methods=['POST'])
@login_required
def cliente_upload():
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

# Configurar API_KEY en Render
os.environ['API_KEY'] = 'la_clave_secreta_de_kiko'

app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    # Configuración para permitir archivos grandes y tiempos de espera más largos
    app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300  # 5 minutos
    app.run(host='0.0.0.0', port=port) 