import os
import requests
from typing import Optional, Dict, Any
from transcriber_base import BaseTranscriber

# --- Nueva función de análisis de conocimiento de empresa ---
def analyze_company_knowledge(text: str):
    text = text.lower()
    rules = [
        {
            'key': 'historia_mision',
            'name': 'Historia y Misión',
            'patterns': ['fundación', 'fundador', 'historia', 'misión', 'visión', 'origen', 'inicio', 'creación', 'objetivo', 'propósito'],
            'feedback': 'Evalúa si la persona conoce la historia, misión y visión de la empresa.'
        },
        {
            'key': 'productos_servicios',
            'name': 'Productos y Servicios',
            'patterns': ['producto', 'servicio', 'ofrece', 'ofrecemos', 'portafolio', 'catálogo', 'solución', 'soluciones', 'venta', 'comercializa', 'comercializamos'],
            'feedback': 'Evalúa si la persona conoce los productos y servicios principales.'
        },
        {
            'key': 'mercado_clientes',
            'name': 'Mercado y Clientes',
            'patterns': ['cliente', 'clientes', 'mercado', 'segmento', 'público objetivo', 'target', 'consumidor', 'usuario', 'usuarios'],
            'feedback': 'Evalúa si la persona conoce el mercado y los clientes de la empresa.'
        },
        {
            'key': 'valores_cultura',
            'name': 'Valores y Cultura',
            'patterns': ['valor', 'valores', 'cultura', 'principio', 'ética', 'responsabilidad', 'compromiso', 'integridad', 'innovación', 'excelencia'],
            'feedback': 'Evalúa si la persona conoce los valores y la cultura organizacional.'
        },
        {
            'key': 'competencia',
            'name': 'Competencia',
            'patterns': ['competencia', 'competidor', 'competidores', 'diferenciador', 'único', 'ventaja competitiva', 'comparado con', 'mejor que', 'peor que'],
            'feedback': 'Evalúa si la persona conoce la competencia y los diferenciadores.'
        }
    ]
    scores = {}
    feedback = []
    total = 0
    for rule in rules:
        count = sum(text.count(p) for p in rule['patterns'])
        score = min(10, count * 2) if count > 0 else 0
        scores[rule['key']] = score
        total += score
        if score < 5:
            feedback.append(f"Poca mención de {rule['name']}. {rule['feedback']}")
        else:
            feedback.append(f"Buen conocimiento de {rule['name']}.")
    scores['overall'] = round(total / len(rules), 1)
    return scores, feedback

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
            "properties": {
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
        scores, feedback = analyze_company_knowledge(text)
        return {
            'text': text,
            'utterances': utterances,
            'scores': scores,
            'feedback': feedback,
            'audio_duration': 0  # Azure REST no da duración directa
        } 