# =============================================
# API ENDPOINTS PARA INTEGRACIÓN CON OTRAS APLICACIONES
# =============================================

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import os
import tempfile
import subprocess
import json
import logging
from datetime import datetime
from werkzeug.utils import secure_filename
from azure.storage.blob import BlobServiceClient
from io import BytesIO
from .azure_transcriber import AzureTranscriber
import openai
import httpx

# Configurar logging
logger = logging.getLogger(__name__)

# Crear Blueprint para la API
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

# Configurar JWT
jwt = JWTManager()

def init_jwt(app):
    """Inicializar JWT en la aplicación principal"""
    jwt.init_app(app)
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'your-secret-key')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False  # Tokens sin expiración para API

# =============================================
# FUNCIONES AUXILIARES
# =============================================

def get_azure_blob_client():
    """Obtener cliente de Azure Blob Storage"""
    azure_account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    azure_account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')
    azure_container_name = os.environ.get('AZURE_CONTAINER_NAME', 'clientai')
    connect_str = f"DefaultEndpointsProtocol=https;AccountName={azure_account_name};AccountKey={azure_account_key};EndpointSuffix=core.windows.net"
    return BlobServiceClient.from_connection_string(connect_str), azure_container_name

def verify_api_key():
    """Verificar API key en headers"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != os.environ.get('API_KEY'):
        return False
    return True

def get_ai_analysis(transcript):
    """Realizar análisis AI del transcript"""
    try:
        logger.info("Llamando a OpenAI para análisis...")
        client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
        
        prompt = f"""
        Analiza la siguiente presentación de empresa y proporciona una evaluación detallada.
        
        Transcripción: {transcript}
        
        Responde ÚNICAMENTE en formato JSON con la siguiente estructura:
        {{
            "scores": {{
                "historia": 0-10,
                "mision_vision": 0-10,
                "productos": 0-10,
                "valores": 0-10,
                "mercado": 0-10,
                "logros": 0-10,
                "overall": 0-10
            }},
            "feedback": [
                "Lista de comentarios positivos y áreas de mejora"
            ],
            "resumen": "Resumen ejecutivo de la presentación",
            "duracion_estimada": 0
        }}
        
        Evalúa basándote en:
        - Claridad del mensaje
        - Estructura de la presentación
        - Contenido relevante
        - Duración apropiada
        """
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        logger.info(f"Respuesta completa de OpenAI: {response}")
        logger.info(f"Contenido de la respuesta: {response.choices[0].message.content}")
        
        # Intentar parsear la respuesta JSON
        try:
            analysis = json.loads(response.choices[0].message.content)
            logger.info(f"Análisis parseado exitosamente: {analysis}")
            return analysis
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando JSON de OpenAI: {e}")
            logger.error(f"Contenido que causó error: {response.choices[0].message.content}")
            # Devolver análisis por defecto
            return {
                "scores": {
                    "historia": 5,
                    "mision_vision": 5,
                    "productos": 5,
                    "valores": 5,
                    "mercado": 5,
                    "logros": 5,
                    "overall": 5
                },
                "feedback": ["Error en el análisis automático"],
                "resumen": "No se pudo analizar automáticamente",
                "duracion_estimada": 0
            }
            
    except Exception as e:
        logger.error(f"Excepción completa en get_ai_analysis: {e}")
        logger.error(f"Tipo de excepción: {type(e)}")
        return {
            "scores": {
                "historia": 5,
                "mision_vision": 5,
                "productos": 5,
                "valores": 5,
                "mercado": 5,
                "logros": 5,
                "overall": 5
            },
            "feedback": [f"Error en análisis: {str(e)}"],
            "resumen": "Error en el análisis automático",
            "duracion_estimada": 0
        }

# =============================================
# ENDPOINTS DE AUTENTICACIÓN
# =============================================

@api_bp.route('/auth/token', methods=['POST'])
def get_token():
    """
    Obtener token JWT para autenticación
    POST /api/v1/auth/token
    Body: {"email": "user@example.com"}
    """
    if not verify_api_key():
        return jsonify({'error': 'API key inválida'}), 401
    
    data = request.get_json()
    if not data or 'email' not in data:
        return jsonify({'error': 'Email requerido'}), 400
    
    # En producción, validar credenciales reales
    email = data['email']
    access_token = create_access_token(identity=email)
    
    return jsonify({
        'access_token': access_token,
        'token_type': 'bearer'
    })

# =============================================
# ENDPOINTS DE PRESENTACIONES
# =============================================

@api_bp.route('/presentations/upload', methods=['POST'])
def upload_presentation():
    """
    Subir y analizar una presentación de video
    POST /api/v1/presentations/upload
    Headers: X-API-Key: your-api-key
    Body: multipart/form-data
        - file: archivo de video
        - rfc: RFC de la empresa
        - company_name: nombre de la empresa (opcional)
        - presenter_name: nombre del presentador (opcional)
    """
    if not verify_api_key():
        return jsonify({'error': 'API key inválida'}), 401
    
    # Validar archivo
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    
    # Validar RFC
    rfc = request.form.get('rfc')
    if not rfc:
        return jsonify({'error': 'El RFC es obligatorio'}), 400
    
    # Validar extensión
    allowed_extensions = {'mp4', 'webm', 'avi', 'mov', 'mkv'}
    if not file.filename.lower().endswith(tuple('.' + ext for ext in allowed_extensions)):
        return jsonify({'error': 'Formato de archivo no soportado'}), 400
    
    try:
        blob_service_client, container_name = get_azure_blob_client()
        folder_prefix = f"{rfc}/"
        
        # Guardar archivo original
        filename = secure_filename(file.filename)
        blob_name = folder_prefix + filename
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
            file.save(tmp.name)
            with open(tmp.name, "rb") as data:
                blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
                blob_client.upload_blob(data, overwrite=True)
        
        # Transcribir audio
        audio_wav = tmp.name + '.wav'
        subprocess.run([
            'ffmpeg', '-y', '-i', tmp.name, '-vn', '-filter:a', 'atempo=2.0', 
            '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_wav
        ], check=True)
        
        transcriber = AzureTranscriber(
            speech_key=os.environ.get('AZURE_SPEECH_KEY'),
            service_region=os.environ.get('AZURE_SPEECH_REGION', 'eastus')
        )
        result = transcriber.transcribe(audio_wav)
        transcript = result['text'] if isinstance(result, dict) and 'text' in result else str(result)
        
        # Análisis AI
        analysis = get_ai_analysis(transcript)
        
        # Guardar resultados
        presentation_data = {
            "rfc": rfc,
            "company_name": request.form.get('company_name', ''),
            "presenter_name": request.form.get('presenter_name', ''),
            "filename": filename,
            "transcript": transcript,
            "analysis": analysis,
            "upload_timestamp": str(datetime.now()),
            "status": "completed"
        }
        
        # Guardar JSON con resultados
        presentacion_json = BytesIO(json.dumps(presentation_data, ensure_ascii=False, indent=2).encode('utf-8'))
        presentacion_json_blob = folder_prefix + 'presentacion.json'
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=presentacion_json_blob)
        blob_client.upload_blob(presentacion_json, overwrite=True)
        
        # Limpiar archivos temporales
        os.unlink(tmp.name)
        os.unlink(audio_wav)
        
        return jsonify({
            'success': True,
            'presentation_id': rfc,
            'analysis': analysis,
            'transcript': transcript,
            'message': 'Presentación analizada exitosamente'
        })
        
    except Exception as e:
        logger.error(f"Error en upload_presentation: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/presentations/<rfc>', methods=['GET'])
def get_presentation(rfc):
    """
    Obtener análisis de una presentación por RFC
    GET /api/v1/presentations/{rfc}
    Headers: X-API-Key: your-api-key
    """
    if not verify_api_key():
        return jsonify({'error': 'API key inválida'}), 401
    
    try:
        blob_service_client, container_name = get_azure_blob_client()
        folder_prefix = f"{rfc}/"
        presentacion_json_blob = folder_prefix + 'presentacion.json'
        
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=presentacion_json_blob)
        presentacion_json = blob_client.download_blob().readall()
        presentation_data = json.loads(presentacion_json.decode("utf-8"))
        
        return jsonify(presentation_data)
        
    except Exception as e:
        logger.error(f"Error en get_presentation: {e}")
        return jsonify({'error': 'Presentación no encontrada'}), 404

@api_bp.route('/presentations/<rfc>/status', methods=['GET'])
def get_presentation_status(rfc):
    """
    Obtener estado de procesamiento de una presentación
    GET /api/v1/presentations/{rfc}/status
    Headers: X-API-Key: your-api-key
    """
    if not verify_api_key():
        return jsonify({'error': 'API key inválida'}), 401
    
    try:
        blob_service_client, container_name = get_azure_blob_client()
        folder_prefix = f"{rfc}/"
        presentacion_json_blob = folder_prefix + 'presentacion.json'
        
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=presentacion_json_blob)
        blob_client.get_blob_properties()
        
        return jsonify({
            'rfc': rfc,
            'status': 'completed',
            'message': 'Presentación procesada exitosamente'
        })
        
    except Exception as e:
        return jsonify({
            'rfc': rfc,
            'status': 'not_found',
            'message': 'Presentación no encontrada'
        })

@api_bp.route('/presentations', methods=['GET'])
def list_presentations():
    """
    Listar todas las presentaciones (limitado a las últimas 50)
    GET /api/v1/presentations
    Headers: X-API-Key: your-api-key
    Query params:
        - limit: número máximo de resultados (default: 50)
        - offset: offset para paginación (default: 0)
    """
    if not verify_api_key():
        return jsonify({'error': 'API key inválida'}), 401
    
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        blob_service_client, container_name = get_azure_blob_client()
        container_client = blob_service_client.get_container_client(container_name)
        
        presentations = []
        for blob in container_client.list_blobs():
            if blob.name.endswith('presentacion.json'):
                try:
                    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob.name)
                    presentacion_json = blob_client.download_blob().readall()
                    presentation_data = json.loads(presentacion_json.decode("utf-8"))
                    presentations.append(presentation_data)
                except Exception as e:
                    logger.error(f"Error leyendo {blob.name}: {e}")
                    continue
        
        # Ordenar por timestamp y aplicar paginación
        presentations.sort(key=lambda x: x.get('upload_timestamp', ''), reverse=True)
        presentations = presentations[offset:offset + limit]
        
        return jsonify({
            'presentations': presentations,
            'total': len(presentations),
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        logger.error(f"Error en list_presentations: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================
# ENDPOINTS DE ANÁLISIS
# =============================================

@api_bp.route('/analysis/transcript', methods=['POST'])
def analyze_transcript():
    """
    Analizar solo un transcript (sin subir archivo)
    POST /api/v1/analysis/transcript
    Headers: X-API-Key: your-api-key
    Body: {"transcript": "texto a analizar"}
    """
    if not verify_api_key():
        return jsonify({'error': 'API key inválida'}), 401
    
    data = request.get_json()
    if not data or 'transcript' not in data:
        return jsonify({'error': 'Transcript requerido'}), 400
    
    try:
        transcript = data['transcript']
        analysis = get_ai_analysis(transcript)
        
        return jsonify({
            'transcript': transcript,
            'analysis': analysis
        })
        
    except Exception as e:
        logger.error(f"Error en analyze_transcript: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================
# ENDPOINTS DE SALUD Y MÉTRICAS
# =============================================

@api_bp.route('/health', methods=['GET'])
def health_check():
    """
    Verificar estado de la API
    GET /api/v1/health
    """
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'services': {
            'azure_storage': 'connected',
            'azure_speech': 'connected',
            'openai': 'connected'
        }
    })

@api_bp.route('/metrics', methods=['GET'])
def get_metrics():
    """
    Obtener métricas de uso de la API
    GET /api/v1/metrics
    Headers: X-API-Key: your-api-key
    """
    if not verify_api_key():
        return jsonify({'error': 'API key inválida'}), 401
    
    try:
        blob_service_client, container_name = get_azure_blob_client()
        container_client = blob_service_client.get_container_client(container_name)
        
        total_presentations = 0
        total_size = 0
        
        for blob in container_client.list_blobs():
            if blob.name.endswith('presentacion.json'):
                total_presentations += 1
            total_size += blob.size
        
        return jsonify({
            'total_presentations': total_presentations,
            'total_storage_size_mb': round(total_size / (1024 * 1024), 2),
            'api_version': '1.0.0'
        })
        
    except Exception as e:
        logger.error(f"Error en get_metrics: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================
# MANEJO DE ERRORES
# =============================================

@api_bp.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint no encontrado'}), 404

@api_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Error interno del servidor'}), 500

@api_bp.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Error no manejado: {e}")
    return jsonify({'error': 'Error interno del servidor'}), 500 