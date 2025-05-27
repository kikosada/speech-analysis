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

@app.route('/login')
def login():
    user_type = request.args.get('user_type', 'asesor')
    session['user_type'] = user_type
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
    return redirect(url_for('asesor'))

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
        
        company_name = session.get('empresa', '').strip()
        if not company_name:
            return jsonify({"error": "Por favor, selecciona la empresa antes de grabar o subir un archivo."}), 400
        
        file = request.files['file']
        logger.info(f"Archivo recibido: {file.filename}, tipo: {file.content_type}, tamaño: {getattr(file, 'content_length', 'desconocido')}")
        if file.filename == '':
            return jsonify({"error": "No se ha seleccionado ningún archivo"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "error": f"Tipo de archivo no permitido. Formatos soportados: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        # Normalizar el nombre de la empresa para el nombre del archivo y rutas
        empresa_slug = normaliza_empresa(company_name)
        filename = secure_filename(file.filename)
        unique_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        filename_unique = f"recording_{empresa_slug}_{unique_id}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename_unique)
        
        # Crear carpeta por usuario y empresa (normalizada)
        user_folder = os.path.join('user_uploads', current_user.email)
        company_folder = os.path.join(user_folder, empresa_slug)
        os.makedirs(company_folder, exist_ok=True)
        
        # Nombre único para el archivo
        user_file_path = os.path.join(company_folder, filename_unique)
        
        # Guardar el archivo en la carpeta de uploads primero
        file.save(filepath)
        logger.info(f"Intentando guardar archivo en: {filepath}")
        logger.info(f"¿Existe el archivo después de guardar? {os.path.exists(filepath)}")
        
        # Validar si el archivo está vacío
        if os.path.getsize(filepath) == 0:
            logger.error(f"El archivo {filepath} está vacío.")
            return jsonify({"error": "El archivo grabado está vacío. Por favor, asegúrate de grabar audio y vuelve a intentarlo."}), 400
        
        # Guardar copia en la carpeta del usuario/empresa
        with open(filepath, 'rb') as src, open(user_file_path, 'wb') as dst:
            dst.write(src.read())
        logger.info(f"Copia guardada en: {user_file_path}")
        
        # Subir a Azure Blob Storage con la nueva estructura (empresa normalizada)
        blob_name = f"{current_user.email}/{empresa_slug}/{filename_unique}"
        upload_success = upload_file_to_azure(filepath, blob_name)
        if not upload_success:
            return jsonify({"error": "No se pudo subir el archivo a Azure Blob Storage"}), 500
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Archivo local eliminado tras subir a Azure: {filename_unique}")
        
        # Extrae la extensión del blob_name
        ext = os.path.splitext(blob_name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            local_temp_path = tmp.name

        download_success = download_file_from_azure(blob_name, local_temp_path)
        if not download_success:
            return jsonify({"error": "No se pudo descargar el archivo de Azure Blob Storage"}), 500

        # Log de depuración: tamaño y tipo de archivo
        file_size = os.path.getsize(local_temp_path)
        file_type, _ = mimetypes.guess_type(local_temp_path)
        logger.info(f"Archivo descargado: {local_temp_path}, tamaño: {file_size} bytes, tipo: {file_type}")
        if file_size == 0:
            logger.error(f"El archivo descargado está vacío: {local_temp_path}")
            return jsonify({"error": "El archivo descargado está vacío o corrupto. Por favor, intenta de nuevo."}), 400

        # Validación de extensión
        ext = os.path.splitext(local_temp_path)[1].lower()
        if ext not in ['.webm', '.m4a', '.mp3', '.wav', '.flac', '.mp4']:
            logger.error(f"Extensión no permitida: {ext}")
            return jsonify({"error": f"Formato no soportado. Formatos válidos: .webm, .m4a, .mp3, .wav, .flac, .mp4"}), 400

        transcriber = Transcriber()
        raw_result = transcriber.transcribe(local_temp_path)
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
                filename_unique,
                user_file_path,
                request.remote_addr,
                datetime.now().isoformat()
            ])
        logger.info(f"Archivo analizado exitosamente: {filename_unique}")

        # Guardar score como txt
        puntuacion_path = os.path.join(company_folder, f"{empresa_slug}_puntuacion.txt")
        with open(puntuacion_path, 'w', encoding='utf-8') as f:
            f.write("Puntuaciones de la IA para la empresa: " + company_name + "\n\n")
            for key, value in formatted_result.get('scores', {}).items():
                f.write(f"{key.capitalize()}: {value}/10\n")
            f.write("\nPuntuación global: {}\n".format(formatted_result.get('scores', {}).get('overall', 'N/A')))

        # Guardar retroalimentación como txt
        retro_path = os.path.join(company_folder, f"{empresa_slug}_retroalimentacion.txt")
        with open(retro_path, 'w', encoding='utf-8') as f:
            f.write("Retroalimentación de la IA para la empresa: " + company_name + "\n\n")
            feedback = formatted_result.get('feedback', [])
            if feedback is None:
                feedback = []
            for item in feedback:
                f.write(f"- {item}\n")

        # Subir los txt a Azure Blob Storage en la misma carpeta (empresa normalizada)
        blob_puntuacion = f"{current_user.email}/{empresa_slug}/{empresa_slug}_puntuacion.txt"
        upload_file_to_azure(puntuacion_path, blob_puntuacion)
        blob_retro = f"{current_user.email}/{empresa_slug}/{empresa_slug}_retroalimentacion.txt"
        upload_file_to_azure(retro_path, blob_retro)

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    # Configuración para permitir archivos grandes y tiempos de espera más largos
    app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300  # 5 minutos
    app.run(host='0.0.0.0', port=port) 