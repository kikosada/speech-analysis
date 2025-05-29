from flask import Flask, jsonify, request, render_template, redirect, url_for, session, send_from_directory
import os
from transcribe import AssemblyAITranscriber as Transcriber
from werkzeug.utils import secure_filename
import logging
from authlib.integrations.flask_client import OAuth
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import csv
import datetime
import time
import boto3
from botocore.exceptions import NoCredentialsError
import tempfile
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta, timezone
import mimetypes
import uuid
import unicodedata
from azure_transcriber import AzureTranscriber
import subprocess

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecret")
oauth = OAuth(app)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurar carpeta de subidas
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'flac', 'mp4', 'webm'}
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB tamaño máximo de archivo

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
login_manager.login_view = 'login_asesor_page'

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

@app.route('/health')
def health_check():
    return jsonify({
        "status": "saludable",
        "version": "1.0.0",
        "servicio": "analizador-presentaciones"
    })

@app.route('/asesor')
@login_required
def asesor():
    if not session.get('empresa'):
        return redirect(url_for('empresa'))
    return render_template('asesor.html')

@app.route('/cliente')
def cliente():
    return render_template('cliente.html')

def upload_file_to_azure(file_path, blob_name):
    account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    container_name = os.environ.get('AZURE_CONTAINER_NAME', 'archivos-miapp-kiko')
    connect_str = f"DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net"
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    with open(file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)
    print(f"Archivo '{file_path}' subido a Azure Blob Storage como '{blob_name}' en el contenedor '{container_name}'")
    return True

def download_file_from_azure(blob_name, local_path):
    account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    container_name = os.environ.get('AZURE_CONTAINER_NAME', 'archivos-miapp-kiko')
    connect_str = f"DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net"
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    with open(local_path, "wb") as f:
        data = blob_client.download_blob()
        f.write(data.readall())
    print(f"Archivo descargado de Azure: {blob_name} -> {local_path}")
    return True

def get_azure_blob_sas_url(blob_name, expiration_minutes=60):
    account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
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

def normaliza_empresa(nombre):
    nombre = nombre.strip().lower()
    nombre = ''.join(
        c for c in unicodedata.normalize('NFD', nombre)
        if unicodedata.category(c) != 'Mn'
    )
    return secure_filename(nombre)

@app.route('/analyze', methods=['POST'])
@login_required
def analyze_audio():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No se ha subido ningún archivo"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No se ha seleccionado ningún archivo"}), 400
        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            file.save(tmp.name)
            audio_path = tmp.name
        # Si es video, extraer audio a wav
        if ext in ['.mp4', '.webm', '.mov', '.mkv']:
            audio_wav = audio_path + '.wav'
            subprocess.run([
                'ffmpeg', '-y', '-i', audio_path, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_wav
            ], check=True)
            audio_path = audio_wav
        transcriber = AzureTranscriber(
            speech_key="8sTDtUGB6YcaENbMygEAbBx8KFb9JWJJqH21QvkeYT979zp6gBxUJQQJ99BEACYeBjFXJ3w3AAAYACOGdl81",
            service_region="eastus"
        )
        result = transcriber.transcribe(audio_path)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}")
        return jsonify({"error": "Ha ocurrido un error inesperado"}), 500

@app.context_processor
def inject_user():
    return dict(current_user=current_user)

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
def cliente_upload():
    try:
        # Configuración específica para el contenedor de clientes
        azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
        azure_account_key = os.environ.get('AZURE_CLIENTE_ACCOUNT_KEY')
        azure_container_name = os.environ.get('AZURE_CLIENTE_CONTAINER', 'clienteai')
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)

        uploaded = []
        for field in ['front_video', 'back_video']:
            file = request.files.get(field)
            if file:
                filename = secure_filename(file.filename)
                blob_name = f"{field}/" + filename
                with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
                    file.save(tmp.name)
                    with open(tmp.name, "rb") as data:
                        blob_client = blob_service_client.get_blob_client(container=azure_container_name, blob=blob_name)
                        blob_client.upload_blob(data, overwrite=True)
                uploaded.append(blob_name)
        if not uploaded:
            return jsonify({"error": "No se subió ningún video"}), 400
        return jsonify({"success": True, "uploaded": uploaded})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    # Configuración para permitir archivos grandes y tiempos de espera más largos
    app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300  # 5 minutos
    app.run(host='0.0.0.0', port=port) 