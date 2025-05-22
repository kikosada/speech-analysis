import os
import requests
from typing import Optional, Dict, Any
from transcriber_base import BaseTranscriber
from transcribe import analyze_sales_pitch

class AzureTranscriber(BaseTranscriber):
    def __init__(self, subscription_key: Optional[str] = None, region: Optional[str] = None):
        """
        Inicializa el transcriber de Azure Speech to Text.
        Args:
            subscription_key: Clave de suscripción de Azure (opcional, por defecto usa AZURE_SPEECH_KEY)
            region: Región de Azure (opcional, por defecto usa AZURE_SPEECH_REGION)
        """
        self.subscription_key = subscription_key or os.getenv('AZURE_SPEECH_KEY')
        self.region = region or os.getenv('AZURE_SPEECH_REGION')
        
        if not self.subscription_key or not self.region:
            raise ValueError(
                "Se requieren las credenciales de Azure Speech to Text. "
                "Configura las variables de entorno AZURE_SPEECH_KEY y AZURE_SPEECH_REGION, "
                "o pásalas como parámetros al constructor."
            )
        
        self.endpoint = f"https://{self.region}.api.cognitive.microsoft.com/speechtotext/v3.1/transcriptions"
        self.language = "es-ES"

    def transcribe(self, audio_path: str, **kwargs) -> Dict[str, Any]:
        """
        Transcribe el audio usando la API REST de Azure Speech to Text y analiza el pitch.
        Args:
            audio_path: Ruta local al archivo de audio (no se usa, se espera que ya esté en Azure Blob Storage)
        Returns:
            dict: Resultado de la transcripción y análisis
        """
        # Se espera que el audio ya esté en Azure Blob Storage y se tenga la URL SAS
        audio_url = kwargs.get('audio_url')
        if not audio_url:
            raise ValueError("Se requiere la URL SAS del blob de Azure (audio_url) para la transcripción.")

        # Configuración de la transcripción
        headers = {
            'Ocp-Apim-Subscription-Key': self.subscription_key,
            'Content-Type': 'application/json'
        }
        payload = {
            "contentUrls": [audio_url],
            "locale": self.language,
            "displayName": "Transcripción de audio",
            "diarizationEnabled": True,
            "properties": {
                "diarization": {
                    "speakers": 2  # Cambia este valor si esperas más de 2 hablantes
                },
                "wordLevelTimestampsEnabled": True
            }
        }
        # Crear la transcripción
        response = requests.post(self.endpoint, headers=headers, json=payload)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Error al crear la transcripción: {response.text}")
        transcription_url = response.headers.get('Location')
        if not transcription_url:
            raise RuntimeError("No se recibió la URL de la transcripción de Azure.")

        # Esperar a que la transcripción esté lista
        import time
        for _ in range(60):  # Espera hasta 5 minutos
            status_resp = requests.get(transcription_url, headers=headers)
            status_data = status_resp.json()
            if status_data.get('status') == 'Succeeded':
                break
            elif status_data.get('status') == 'Failed':
                raise RuntimeError(f"Transcripción fallida: {status_data}")
            time.sleep(5)
        else:
            raise RuntimeError("La transcripción tardó demasiado en completarse.")

        # Obtener el resultado de la transcripción
        results_urls = status_data['resultsUrls']
        transcript_url = results_urls.get('channel_0') or next(iter(results_urls.values()))
        transcript_resp = requests.get(transcript_url)
        transcript_json = transcript_resp.json()

        # Procesar la transcripción y diarización
        text = " ".join([segment['display'] for segment in transcript_json['recognizedPhrases']])
        utterances = []
        for phrase in transcript_json['recognizedPhrases']:
            if 'speaker' in phrase:
                utterances.append({
                    'speaker': phrase['speaker'],
                    'text': phrase['display']
                })
        scores, feedback = analyze_sales_pitch(text)
        return {
            'text': text,
            'utterances': utterances,
            'scores': scores,
            'feedback': feedback,
            'audio_duration': 0  # Azure REST no da duración directa
        } 