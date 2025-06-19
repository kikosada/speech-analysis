import os
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import requests
import time

# Cargar variables de entorno desde text.env (Actualización de credenciales Azure - 2024)
load_dotenv('text.env')

app = Flask(__name__, static_folder='public', static_url_path='')

# --- Configuración de Azure AI Video Indexer ---
SUBSCRIPTION_KEY = os.getenv("VIDEO_INDEXER_SUBSCRIPTION_KEY")
ACCOUNT_ID = os.getenv("VIDEO_INDEXER_ACCOUNT_ID")
LOCATION = os.getenv("VIDEO_INDEXER_LOCATION") # e.g., 'eastus', 'trial'

if not all([SUBSCRIPTION_KEY, ACCOUNT_ID, LOCATION]):
    print("Error: Faltan variables de entorno requeridas. Revisa tu archivo .env.")
    exit(1)

BASE_AUTH_URL = f"https://api.videoindexer.ai/Auth/{LOCATION}/Accounts/{ACCOUNT_ID}"
BASE_API_URL = f"https://api.videoindexer.ai/{LOCATION}/Accounts/{ACCOUNT_ID}"

# Helper para obtener un access token de Video Indexer

def get_access_token():
    try:
        response = requests.get(
            f"{BASE_AUTH_URL}/AccessToken?allowEdit=true",
            headers={
                'Ocp-Apim-Subscription-Key': SUBSCRIPTION_KEY
            }
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error obteniendo access token: {e}")
        raise Exception("No se pudo obtener el access token de Video Indexer.")

# --- Endpoints API para el frontend ---

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/index-video', methods=['POST'])
def index_video():
    data = request.get_json()
    video_url = data.get('videoUrl')
    video_name = data.get('videoName')

    if not video_url or not video_name:
        return jsonify({"error": "videoUrl y videoName son requeridos."}), 400

    try:
        access_token = get_access_token()
        params = {
            'name': video_name,
            'videoUrl': video_url,
            'privacy': 'Private',
            'indexingPreset': 'Advanced',
            'language': 'es-ES' # Cambia a 'en-US' si tu video es en inglés
        }
        upload_response = requests.post(
            f"{BASE_API_URL}/Videos",
            params=params,
            headers={
                'Authorization': f'Bearer {access_token}'
            }
        )
        upload_response.raise_for_status()
        response_data = upload_response.json()
        return jsonify({
            "videoId": response_data.get('id'),
            "status": response_data.get('state'),
            "message": "Video subido e indexado."
        })
    except Exception as e:
        print(f"Error indexando video: {e}")
        return jsonify({"error": f"No se pudo iniciar el indexado: {e}"}), 500

@app.route('/api/video-status/<video_id>', methods=['GET'])
def get_video_status(video_id):
    try:
        access_token = get_access_token()
        status_response = requests.get(
            f"{BASE_API_URL}/Videos/{video_id}/Index",
            params={
                'accessToken': access_token,
                'language': 'es-ES'
            }
        )
        status_response.raise_for_status()
        response_data = status_response.json()
        return jsonify({
            "videoId": video_id,
            "state": response_data.get('state'),
            "duration": response_data.get('durationInSeconds')
        })
    except Exception as e:
        print(f"Error consultando estado: {e}")
        return jsonify({"error": f"No se pudo consultar el estado: {e}"}), 500

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
        return jsonify(insights_data)
    except Exception as e:
        print(f"Error obteniendo insights: {e}")
        return jsonify({"error": f"No se pudo obtener insights: {e}"}), 500

if __name__ == '__main__':
    app.run(debug=os.getenv("FLASK_DEBUG") == "True", port=os.getenv("PORT", 5000)) 