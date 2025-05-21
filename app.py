from flask import Flask, jsonify, request, render_template, redirect, url_for, session, send_from_directory
import os
from transcribe import AssemblyAITranscriber
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
from datetime import datetime, timedelta

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
    return render_template('index.html', is_index=True)

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
        expiry=datetime.utcnow() + timedelta(minutes=expiration_minutes)
    )
    url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
    return url

@app.route('/analyze', methods=['POST'])
@login_required
def analyze_audio():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No se ha subido ningún archivo"}), 400
        
        file = request.files['file']
        logger.info(f"Archivo recibido: {file.filename}, tipo: {file.content_type}, tamaño: {getattr(file, 'content_length', 'desconocido')}")
        if file.filename == '':
            return jsonify({"error": "No se ha seleccionado ningún archivo"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "error": f"Tipo de archivo no permitido. Formatos soportados: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Crear carpeta por usuario
        user_folder = os.path.join('user_uploads', current_user.email)
        os.makedirs(user_folder, exist_ok=True)
        
        # Nombre único para el archivo
        unique_filename = f"{int(time.time())}_{filename}"
        user_file_path = os.path.join(user_folder, unique_filename)
        
        # Guardar el archivo en la carpeta de uploads primero
        file.save(filepath)
        logger.info(f"Intentando guardar archivo en: {filepath}")
        logger.info(f"¿Existe el archivo después de guardar? {os.path.exists(filepath)}")
        
        # Validar si el archivo está vacío
        if os.path.getsize(filepath) == 0:
            logger.error(f"El archivo {filepath} está vacío.")
            return jsonify({"error": "El archivo grabado está vacío. Por favor, asegúrate de grabar audio y vuelve a intentarlo."}), 400
        
        # Guardar copia en la carpeta del usuario
        with open(filepath, 'rb') as src, open(user_file_path, 'wb') as dst:
            dst.write(src.read())
        logger.info(f"Copia guardada en: {user_file_path}")
        
        # Subir a Azure Blob Storage en vez de guardar localmente
        blob_name = f"{current_user.email}/{filename}"
        upload_success = upload_file_to_azure(filepath, blob_name)
        if not upload_success:
            return jsonify({"error": "No se pudo subir el archivo a Azure Blob Storage"}), 500
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Archivo local eliminado tras subir a Azure: {filename}")
        
        # PROCESAMIENTO: primero intenta con SAS URL, si falla descarga local
        sas_url = get_azure_blob_sas_url(blob_name)
        try:
            transcriber = AssemblyAITranscriber()
            upload_url = transcriber.upload_file(sas_url)
            raw_result = transcriber.transcribe(upload_url)
        except Exception as e:
            print(f"Fallo usando SAS URL, intentando descarga local: {e}")
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                local_temp_path = tmp.name
            download_success = download_file_from_azure(blob_name, local_temp_path)
            if not download_success:
                return jsonify({"error": "No se pudo descargar el archivo de Azure Blob Storage"}), 500
            transcriber = AssemblyAITranscriber()
            upload_url = transcriber.upload_file(local_temp_path)
            raw_result = transcriber.transcribe(upload_url)
            if os.path.exists(local_temp_path):
                os.remove(local_temp_path)
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
    archivos = []
    if os.path.exists(user_folder):
        archivos = [f for f in os.listdir(user_folder) if os.path.isfile(os.path.join(user_folder, f))]
    return render_template('mis_archivos.html', archivos=archivos)

@app.route('/descargar/<filename>')
@login_required
def descargar_archivo(filename):
    user_folder = os.path.join('user_uploads', current_user.email)
    # Seguridad: solo permite descargar archivos de tu carpeta
    file_path = os.path.join(user_folder, filename)
    if not os.path.exists(file_path):
        return "Archivo no encontrado", 404
    return send_from_directory(user_folder, filename, as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port) 