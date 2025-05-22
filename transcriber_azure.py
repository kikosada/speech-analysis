import os
import azure.cognitiveservices.speech as speechsdk
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
        
        self.speech_config = speechsdk.SpeechConfig(
            subscription=self.subscription_key,
            region=self.region
        )
        self.speech_config.speech_recognition_language = "es-ES"

    def transcribe(self, audio_path: str, **kwargs) -> Dict[str, Any]:
        """
        Transcribe el audio usando Azure Speech to Text y analiza el pitch.
        Args:
            audio_path: Ruta al archivo de audio
            **kwargs: Parámetros adicionales (no usados en esta implementación)
        Returns:
            dict: Resultado de la transcripción y análisis
        """
        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )

        print("Iniciando transcripción con Azure...")
        result = speech_recognizer.recognize_once_async().get()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = result.text
            scores, feedback = analyze_sales_pitch(text)
            return {
                'text': text,
                'scores': scores,
                'feedback': feedback,
                'audio_duration': 0  # Azure no proporciona esta información directamente
            }
        else:
            error_details = result.cancellation_details
            raise RuntimeError(
                f"Error en la transcripción: {error_details.reason}\n"
                f"Error: {error_details.error_details}"
            ) 