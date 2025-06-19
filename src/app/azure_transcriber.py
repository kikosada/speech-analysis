import azure.cognitiveservices.speech as speechsdk
import os
import tempfile
from .transcribe import analyze_company_knowledge  # Importar función de análisis

class AzureTranscriber:
    def __init__(self, speech_key=None, service_region=None):
        self.speech_key = speech_key or os.environ.get('AZURE_SPEECH_KEY')
        self.service_region = service_region or os.environ.get('AZURE_SPEECH_REGION')

    def transcribe(self, audio_path):
        speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.service_region)
        speech_config.speech_recognition_language = 'es-ES'  # Forzar español
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
        import time
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