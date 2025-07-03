import azure.cognitiveservices.speech as speechsdk
import os
import logging
import time
from .transcribe import analyze_company_knowledge  # Importar función de análisis

logger = logging.getLogger(__name__)

class AzureTranscriber:
    def __init__(self, speech_key=None, service_region=None):
        self.speech_key = speech_key or os.environ.get('AZURE_SPEECH_KEY')
        self.service_region = service_region or os.environ.get('AZURE_SPEECH_REGION')
        if not self.speech_key or not self.service_region:
            raise ValueError("La clave de Azure Speech o la región no están configuradas.")

    def transcribe(self, audio_path):
        """
        Transcribe un archivo de audio completo usando transcripción continua.
        Este método reemplaza recognize_once() que solo transcribe hasta el primer silencio.
        """
        logger.info(f"Iniciando transcripción completa para: {audio_path}")
        
        speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.service_region)
        speech_config.speech_recognition_language = 'es-MX'
        
        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        
        # Variables para almacenar resultados
        all_results = []
        done = False
        
        def recognized(evt):
            """Callback cuando se reconoce una frase"""
            if evt.result.text:
                all_results.append(evt.result.text)
                logger.info(f"Fragmento transcrito: {evt.result.text[:50]}...")
        
        def session_stopped(evt):
            """Callback cuando termina la sesión"""
            nonlocal done
            logger.info("Sesión de transcripción terminada")
            done = True
        
        def canceled(evt):
            """Callback si se cancela la transcripción"""
            nonlocal done
            logger.error(f"Transcripción cancelada: {evt.result.reason}")
            if evt.result.reason == speechsdk.CancellationReason.Error:
                logger.error(f"Detalles del error: {evt.result.cancellation_details.error_details}")
            done = True
        
        # Conectar callbacks
        speech_recognizer.recognized.connect(recognized)
        speech_recognizer.session_stopped.connect(session_stopped)
        speech_recognizer.canceled.connect(canceled)
        
        # Iniciar transcripción continua
        logger.info("Iniciando transcripción continua...")
        speech_recognizer.start_continuous_recognition()
        
        # Esperar a que termine
        while not done:
            time.sleep(0.5)
        
        # Detener transcripción
        speech_recognizer.stop_continuous_recognition()
        
        # Combinar todos los resultados
        full_text = " ".join(all_results)
        
        if full_text:
            logger.info(f"Transcripción completa exitosa. Longitud: {len(full_text)} caracteres")
            return {'text': full_text}
        else:
            logger.warning("No se pudo transcribir ningún texto del audio")
            return {'text': ''}

    def transcribe_full(self, audio_path):
        """
        Método alternativo usando ConversationTranscriber para transcripciones con múltiples hablantes.
        """
        speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.service_region)
        speech_config.speech_recognition_language = 'es-MX'
        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
        transcriber = speechsdk.transcription.ConversationTranscriber(speech_config=speech_config, audio_config=audio_config)

        utterances = []
        speaker_map = {}
        speaker_count = 0

        def transcribed(evt):
            if evt.result.text:
                speaker = evt.result.speaker_id or 'Desconocido'
                if speaker not in speaker_map:
                    speaker_count = len(speaker_map) + 1
                    speaker_map[speaker] = f"Hablante {speaker_count}"
                utterances.append({
                    'speaker': speaker_map[speaker],
                    'text': evt.result.text
                })

        def session_stopped(evt):
            nonlocal done
            done = True

        transcriber.transcribed.connect(transcribed)
        transcriber.session_stopped.connect(session_stopped)

        done = False
        transcriber.start_transcribing_async().get()
        while not done:
            time.sleep(0.5)
        transcriber.stop_transcribing_async().get()

        # Formatear la transcripción
        transcript = ""
        for utt in utterances:
            transcript += f"{utt['speaker']}: {utt['text']}\n"

        # Análisis de conocimiento de empresa (score y feedback)
        scores, feedback = analyze_company_knowledge(transcript)

        return {
            'utterances': utterances,
            'text': transcript.strip(),
            'scores': scores,
            'feedback': feedback
        } 