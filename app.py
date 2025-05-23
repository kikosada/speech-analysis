from flask import Flask, jsonify, request, render_template, redirect, url_for, session, send_from_directory
import os
from transcriber_azure import AzureTranscriber as Transcriber
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
import subprocess
from celery import Celery

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecret")
oauth = OAuth(app)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurar carpeta de subidas
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'flac', 'mp4', 'webm'}
MAX_CONTENT_LENGTH = 512 * 1024 * 1024  # 512MB tamaño máximo de archivo

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
    if current_user.is_authenticated and not session.get('empresa'):
        return redirect(url_for('empresa'))
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
    nombre = nombre.replace(' ', '')  # Elimina todos los espacios internos
    nombre = secure_filename(nombre)
    nombre = nombre.replace('_', '')  # Elimina guiones bajos que secure_filename podría agregar
    return nombre

def extrae_audio(video_path, audio_path):
    """Extrae el audio de un video y lo guarda como .wav mono 16kHz."""
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path, "-ar", "16000", "-ac", "1", "-f", "wav", audio_path
    ], check=True)

# Configuración de Celery para tareas asíncronas
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
celery = Celery(app.name, broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

# Tarea asíncrona para transcribir y analizar el audio
@celery.task(bind=True)
def async_transcribe_and_analyze(self, params):
    """
    Tarea asíncrona que maneja la transcripción y análisis del audio.
    Se ejecuta en segundo plano para no bloquear la aplicación.
    
    Args:
        params (dict): Diccionario con todos los parámetros necesarios:
            - transcriber_input_path: Ruta al archivo de audio
            - azure_blob_sas_url: URL del blob en Azure (si aplica)
            - ext: Extensión del archivo
            - company_folder: Carpeta de la empresa
            - empresa_slug: Nombre normalizado de la empresa
            - company_name: Nombre original de la empresa
            - current_user_email: Email del usuario
            - blob_puntuacion: Nombre del blob para la puntuación
            - blob_retro: Nombre del blob para la retroalimentación
            - puntuacion_path: Ruta local para guardar la puntuación
            - retro_path: Ruta local para guardar la retroalimentación
            - PROVIDER: Proveedor de transcripción (azure/assemblyai)
    """
    try:
        # Desempaquetar parámetros
        transcriber_input_path = params['transcriber_input_path']
        azure_blob_sas_url = params.get('azure_blob_sas_url')
        ext = params['ext']
        company_folder = params['company_folder']
        empresa_slug = params['empresa_slug']
        company_name = params['company_name']
        current_user_email = params['current_user_email']
        blob_puntuacion = params['blob_puntuacion']
        blob_retro = params['blob_retro']
        puntuacion_path = params['puntuacion_path']
        retro_path = params['retro_path']
        PROVIDER = params['PROVIDER']

        # Realizar la transcripción usando el proveedor configurado
        transcriber = Transcriber()
        if PROVIDER == "azure":
            raw_result = transcriber.transcribe(transcriber_input_path, audio_url=azure_blob_sas_url)
        else:
            raw_result = transcriber.transcribe(transcriber_input_path)

        # Formatear el resultado para el frontend
        formatted_result = format_analysis_result(raw_result)
        formatted_result['uploaded_by'] = current_user_email

        # Guardar la puntuación en un archivo de texto
        with open(puntuacion_path, 'w', encoding='utf-8') as f:
            f.write("Puntuaciones de la IA para la empresa: " + company_name + "\n\n")
            for key, value in formatted_result.get('scores', {}).items():
                f.write(f"{key.capitalize()}: {value}/10\n")
            f.write("\nPuntuación global: {}\n".format(formatted_result.get('scores', {}).get('overall', 'N/A')))

        # Guardar la retroalimentación en un archivo de texto
        with open(retro_path, 'w', encoding='utf-8') as f:
            f.write("Retroalimentación de la IA para la empresa: " + company_name + "\n\n")
            for item in formatted_result.get('feedback', []):
                f.write(f"- {item}\n")

        # Subir los archivos de texto a Azure Blob Storage
        upload_file_to_azure(puntuacion_path, blob_puntuacion)
        upload_file_to_azure(retro_path, blob_retro)

        return formatted_result
    except Exception as e:
        return {'error': str(e)}

@app.route('/analyze', methods=['POST'])
@login_required
def analyze_audio():
    """
    Endpoint para analizar un archivo de audio.
    Maneja la subida del archivo, su procesamiento y lanza la tarea asíncrona.
    """
    try:
        # Validar que se haya subido un archivo
        if 'file' not in request.files:
            return jsonify({"error": "No se ha subido ningún archivo"}), 400

        # Validar que se haya seleccionado una empresa
        company_name = session.get('empresa', '').strip()
        if not company_name:
            return jsonify({"error": "Por favor, selecciona la empresa antes de grabar o subir un archivo."}), 400

        # Obtener y validar el archivo
        file = request.files['file']
        logger.info(f"Archivo recibido: {file.filename}, tipo: {file.content_type}, tamaño: {getattr(file, 'content_length', 'desconocido')}")
        if file.filename == '':
            return jsonify({"error": "No se ha seleccionado ningún archivo"}), 400
        if not allowed_file(file.filename):
            return jsonify({
                "error": f"Tipo de archivo no permitido. Formatos soportados: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400

        # Preparar nombres de archivo y rutas
        empresa_slug = normaliza_empresa(company_name)
        filename = secure_filename(file.filename)
        unique_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        filename_unique = f"recording_{empresa_slug}_{unique_id}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename_unique)

        # Crear estructura de carpetas
        user_folder = os.path.join('user_uploads', current_user.email)
        company_folder = os.path.join(user_folder, empresa_slug)
        os.makedirs(company_folder, exist_ok=True)
        user_file_path = os.path.join(company_folder, filename_unique)

        # Guardar el archivo localmente
        file.save(filepath)
        logger.info(f"Intentando guardar archivo en: {filepath}")
        logger.info(f"¿Existe el archivo después de guardar? {os.path.exists(filepath)}")

        # Validar que el archivo no esté vacío
        if os.path.getsize(filepath) == 0:
            logger.error(f"El archivo {filepath} está vacío.")
            return jsonify({"error": "El archivo grabado está vacío. Por favor, asegúrate de grabar audio y vuelve a intentarlo."}), 400

        # Guardar copia en la carpeta del usuario
        with open(filepath, 'rb') as src, open(user_file_path, 'wb') as dst:
            dst.write(src.read())
        logger.info(f"Copia guardada en: {user_file_path}")

        # Subir a Azure Blob Storage
        blob_name = f"{current_user.email}/{empresa_slug}/{filename_unique}"
        upload_success = upload_file_to_azure(filepath, blob_name)
        if not upload_success:
            return jsonify({"error": "No se pudo subir el archivo a Azure Blob Storage"}), 500

        # Limpiar archivo local después de subir
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Archivo local eliminado tras subir a Azure: {filename_unique}")

        # Generar URL SAS para Azure
        azure_blob_sas_url = get_azure_blob_sas_url(blob_name)

        # Preparar archivo temporal para procesamiento
        ext = os.path.splitext(blob_name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            local_temp_path = tmp.name

        # Descargar archivo de Azure para procesamiento
        download_success = download_file_from_azure(blob_name, local_temp_path)
        if not download_success:
            return jsonify({"error": "No se pudo descargar el archivo de Azure Blob Storage"}), 500

        # Validar archivo descargado
        file_size = os.path.getsize(local_temp_path)
        file_type, _ = mimetypes.guess_type(local_temp_path)
        logger.info(f"Archivo descargado: {local_temp_path}, tamaño: {file_size} bytes, tipo: {file_type}")
        if file_size == 0:
            logger.error(f"El archivo descargado está vacío: {local_temp_path}")
            return jsonify({"error": "El archivo descargado está vacío o corrupto. Por favor, intenta de nuevo."}), 400

        # Procesar el archivo según su tipo
        ext = os.path.splitext(local_temp_path)[1].lower()
        if ext in ['.webm', '.mp4']:
            # Extraer audio si es video
            audio_temp_path = local_temp_path + '.wav'
            extrae_audio(local_temp_path, audio_temp_path)
            transcriber_input_path = audio_temp_path
        elif ext in ['.wav', '.mp3', '.m4a', '.flac']:
            transcriber_input_path = local_temp_path
        else:
            logger.error(f"Extensión no permitida: {ext}")
            return jsonify({"error": f"Formato no soportado. Formatos válidos: .webm, .m4a, .mp3, .wav, .flac, .mp4"}), 400

        # Preparar parámetros para la tarea asíncrona
        PROVIDER = os.environ.get("TRANSCRIBER_PROVIDER", "azure")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        puntuacion_path = os.path.join(company_folder, f"{empresa_slug}_puntuacion_{timestamp}.txt")
        retro_path = os.path.join(company_folder, f"{empresa_slug}_retroalimentacion_{timestamp}.txt")
        blob_puntuacion = f"{current_user.email}/{empresa_slug}/{empresa_slug}_puntuacion_{timestamp}.txt"
        blob_retro = f"{current_user.email}/{empresa_slug}/{empresa_slug}_retroalimentacion_{timestamp}.txt"

        # Crear diccionario de parámetros para la tarea
        params = {
            'transcriber_input_path': transcriber_input_path,
            'azure_blob_sas_url': azure_blob_sas_url,
            'ext': ext,
            'company_folder': company_folder,
            'empresa_slug': empresa_slug,
            'company_name': company_name,
            'current_user_email': current_user.email,
            'blob_puntuacion': blob_puntuacion,
            'blob_retro': blob_retro,
            'puntuacion_path': puntuacion_path,
            'retro_path': retro_path,
            'PROVIDER': PROVIDER
        }

        # Lanzar tarea asíncrona y devolver ID
        task = async_transcribe_and_analyze.apply_async(args=[params])
        return jsonify({'task_id': task.id}), 202

    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}")
        return jsonify({"error": "Ha ocurrido un error inesperado"}), 500

@app.route('/analyze/status/<task_id>', methods=['GET'])
def analyze_status(task_id):
    """
    Endpoint para consultar el estado de una tarea de análisis.
    
    Args:
        task_id: ID de la tarea a consultar
    
    Returns:
        JSON con el estado actual de la tarea y su resultado si está completa
    """
    task = async_transcribe_and_analyze.AsyncResult(task_id)
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Pendiente, esperando a ser procesada.'
        }
    elif task.state == 'STARTED':
        response = {
            'state': task.state,
            'status': 'Procesando...'
        }
    elif task.state == 'SUCCESS':
        response = {
            'state': task.state,
            'status': 'Completada',
            'result': task.result
        }
    elif task.state == 'FAILURE':
        response = {
            'state': task.state,
            'status': 'Fallida',
            'error': str(task.info)
        }
    else:
        response = {
            'state': task.state,
            'status': str(task.info)
        }
    return jsonify(response)

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
        return redirect(url_for('index'))
    return render_template('empresa.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port) 